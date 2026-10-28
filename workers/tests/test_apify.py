"""Caminho alternativo do Mapeador (ADR 0012): Apollo sem créditos ou sem chave → fontes públicas + Apify.
Apollo, Apify e Claude simulados, sem nenhuma chamada externa."""

import asyncio
import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import select

from slp_workers.agents.padroes_email import candidatos
from slp_workers.db import acoes_agentes, contatos, empresas, eventos, supressao
from slp_workers.orchestrator.decisores import DependenciasDecisores, Mapeamento, OrcamentoApifyEsgotado
from slp_workers.orchestrator.pipeline import processar_empresa
from slp_workers.settings import WorkerConfig
from slp_workers.web.apify import ClienteApify, ErroApify
from slp_workers.web.apollo import ApolloSemCreditos, ClienteApollo
from tests.conftest import montar_ctx
from tests.test_decisores import DOMINIO, FONTE, ApolloFalso, IAMapeadora, _contatos, _empresa, _tipos, mx_ok

WEB = [
    {"nome": "Ana Souza", "cargo": "Diretora de TI", "area": "TI", "fonte_url": FONTE, "linkedin_url": None},
    {
        "nome": "Carla Dias",
        "cargo": "Gerente de Compliance",
        "area": "Compliance",
        "fonte_url": FONTE,
        "linkedin_url": None,
    },
    {
        "nome": "Bruno Lopes",
        "cargo": "Head de Marketing",
        "area": "Marketing",
        "fonte_url": FONTE,
        "linkedin_url": None,
    },
]


def _item(email, status="valid", smtp=True, catch_all=False, funcao=False):
    return {
        "email": email,
        "status": status,
        "smtp_valid": smtp,
        "is_catch_all": catch_all,
        "is_role_based": funcao,
        "is_disposable": False,
        "is_free_provider": False,
        "reason": "x",
    }


class ApifyFalso:
    def __init__(self, respostas: dict[str, dict] | None = None, status: int = 200):
        self.respostas = respostas or {}
        self.status = status
        self.chamadas: list[dict] = []

    def transporte(self) -> httpx.MockTransport:
        def responder(request: httpx.Request) -> httpx.Response:
            assert request.headers["authorization"] == "Bearer token-teste"
            assert request.url.path.endswith(
                "/acts/bounceverify~bounceverify-email-verifier/run-sync-get-dataset-items"
            )
            corpo = json.loads(request.content)
            self.chamadas.append(corpo)
            if self.status != 200:
                return httpx.Response(self.status)
            itens = [self.respostas.get(e) or _item(e, status="invalid", smtp=False) for e in corpo["emails"]]
            return httpx.Response(201, json=itens)

        return httpx.MockTransport(responder)


def _apollo_sem_creditos() -> ApolloFalso:
    apollo = ApolloFalso()
    corpo = {
        "error": "You have insufficient credits!",
        "error_details": {"code": "BILLING.LIMIT.CREDITS_EXHAUSTED"},
    }
    original = apollo.transporte

    def transporte():
        base = original()

        def responder(request):
            if "/organizations/enrich" in request.url.path or "/people/match" in request.url.path:
                return httpx.Response(422, json=corpo)
            return base.handler(request)

        return httpx.MockTransport(responder)

    apollo.transporte = transporte
    return apollo


def _deps(engine, apollo, apify, ia, **config):
    cfg = WorkerConfig(apollo_api_key="chave-teste", apify_token="token-teste", **config)
    return DependenciasDecisores(
        engine=engine,
        ia=ia,
        config=cfg,
        apollo=ClienteApollo("chave-teste", transport=apollo.transporte(), espera_429_s=0),
        resolvedor_mx=mx_ok,
        apify=ClienteApify("token-teste", transport=apify.transporte()),
    )


def _rodar(engine, apollo, apify, ia, eid, **config):
    return asyncio.run(Mapeamento(_deps(engine, apollo, apify, ia, **config), eid).executar())


# --- Padrões de e-mail -------------------------------------------------------


def test_candidatos_tiram_acento_e_particulas():
    assert candidatos("João da Silva", "x.com.br") == [
        "joao.silva@x.com.br",
        "jsilva@x.com.br",
        "joao@x.com.br",
        "joaosilva@x.com.br",
        "joao_silva@x.com.br",
    ]


def test_candidatos_com_nome_composto_incluem_o_penultimo_sobrenome():
    assert "ana.souza@x.com.br" in candidatos("Ana Paula Souza Lima", "x.com.br")


def test_so_primeiro_nome_nao_gera_candidato():
    assert candidatos("Ana", "x.com.br") == []


# --- Caminho alternativo -----------------------------------------------------


def test_apollo_sem_creditos_troca_para_o_apify_e_nao_falha(engine):
    eid = _empresa(engine)
    apify = ApifyFalso(
        {
            f"ana.souza@{DOMINIO}": _item(f"ana.souza@{DOMINIO}"),
            f"carla.dias@{DOMINIO}": _item(f"carla.dias@{DOMINIO}", status="risky", catch_all=True),
        }
    )
    ia = IAMapeadora([], WEB)
    assert _rodar(engine, _apollo_sem_creditos(), apify, ia, eid) == "decisores_mapeados"

    por_area = {c.area: c for c in _contatos(engine, eid)}
    assert (por_area["TI"].email, por_area["TI"].email_status, por_area["TI"].fonte) == (
        f"ana.souza@{DOMINIO}",
        "valido",
        "web+apify",
    )
    assert por_area["TI"].fonte_url == FONTE
    # Catch-all: o servidor aceita qualquer endereço, então não conta como válido
    assert (por_area["Compliance"].email_status, por_area["Compliance"].email) == (
        "nao_verificado",
        f"carla.dias@{DOMINIO}",
    )
    assert (por_area["Marketing"].email, por_area["Marketing"].email_status) == (None, "sem_email")

    tipos = _tipos(engine, eid)
    assert "buscando_decisores_alternativo" in tipos and tipos[-1] == "decisores_encontrados"
    assert "mapeamento_falhou" not in tipos
    assert len(apify.chamadas) == 1 and len(apify.chamadas[0]["emails"]) == 15  # 3 pessoas × 5 padrões
    with engine.connect() as conn:
        e = conn.execute(select(empresas.c.estado).where(empresas.c.id == eid)).scalar()
        acao = conn.execute(select(acoes_agentes).where(acoes_agentes.c.agente == "mapeador.apify")).one()
    assert e == "PREPARANDO_ABORDAGEM"
    assert acao.saida_json == {"verificados": 15, "entregaveis": 1, "catch_all": 1}  # sem os endereços
    assert acao.custo == Decimal("0.0734")  # 15 × US$ 0,00089 × 5,50


def test_sem_chave_do_apollo_usa_o_apify_direto(engine):
    eid = _empresa(engine)
    apify = ApifyFalso({f"ana.souza@{DOMINIO}": _item(f"ana.souza@{DOMINIO}")})
    deps = _deps(engine, ApolloFalso(), apify, IAMapeadora([], WEB))
    deps.apollo = ClienteApollo("")
    assert asyncio.run(Mapeamento(deps, eid).executar()) == "decisores_mapeados"
    assert "mapeando_decisores" not in _tipos(engine, eid)


def test_sem_apollo_e_sem_apify_espera_com_evento(engine):
    eid = _empresa(engine)
    deps = _deps(engine, _apollo_sem_creditos(), ApifyFalso(), IAMapeadora([], WEB))
    deps.apify = ClienteApify("")
    assert asyncio.run(Mapeamento(deps, eid).executar()) == "apollo_sem_creditos"
    assert _tipos(engine, eid)[-1] == "apollo_sem_creditos"
    assert _contatos(engine, eid) == []


def test_email_de_funcao_ou_suprimido_nao_conta(engine):
    eid = _empresa(engine)
    with engine.begin() as conn:
        conn.execute(
            supressao.insert().values(id=uuid.uuid4(), email=f"ana.souza@{DOMINIO}", motivo="opt-out")
        )
    apify = ApifyFalso(
        {
            f"ana.souza@{DOMINIO}": _item(f"ana.souza@{DOMINIO}"),
            f"carla@{DOMINIO}": _item(f"carla@{DOMINIO}", funcao=True),
        }
    )
    _rodar(engine, _apollo_sem_creditos(), apify, IAMapeadora([], WEB), eid)
    nomes = {c.nome: c for c in _contatos(engine, eid)}
    assert "Ana Souza" not in nomes  # suprimida
    assert nomes["Carla Dias"].email_status != "valido"


def test_teto_do_apify_pausa_antes_de_gastar(engine):
    eid = _empresa(engine)
    with engine.begin() as conn:
        conn.execute(
            acoes_agentes.insert().values(
                id=uuid.uuid4(),
                agente="mapeador.apify",
                empresa_id=None,
                entrada_hash="x",
                saida_json={},
                modelo="apify:verificador",
                tokens_in=0,
                tokens_out=0,
                custo=Decimal("11"),
                duracao_ms=0,
                creditos=0,
                criado_em=datetime.now(UTC),
            )
        )
    apify = ApifyFalso()
    with pytest.raises(OrcamentoApifyEsgotado):
        _rodar(engine, _apollo_sem_creditos(), apify, IAMapeadora([], WEB), eid)
    assert apify.chamadas == []


def test_pipeline_registra_a_pausa_do_apify(engine):
    from arq import Retry

    eid = _empresa(engine)
    ctx = montar_ctx(
        engine,
        IAMapeadora([], WEB),
        config=WorkerConfig(apollo_api_key="k", apify_token="t", apify_daily_budget_usd=Decimal("0")),
    )
    ctx["apollo"] = ClienteApollo(
        "chave-teste", transport=_apollo_sem_creditos().transporte(), espera_429_s=0
    )
    ctx["apify"] = ClienteApify("token-teste", transport=ApifyFalso().transporte())
    ctx["resolvedor_mx"] = mx_ok
    with pytest.raises(Retry):
        asyncio.run(processar_empresa(ctx, str(eid)))
    with engine.connect() as conn:
        tipos = [r.tipo for r in conn.execute(select(eventos.c.tipo).where(eventos.c.empresa_id == eid))]
    assert "fila_pausada_apify" in tipos


def test_apollo_responde_sem_creditos_com_erro_proprio():
    corpo = {
        "error": "You have insufficient credits!",
        "error_details": {"code": "BILLING.LIMIT.CREDITS_EXHAUSTED"},
    }
    cliente = ClienteApollo("k", transport=httpx.MockTransport(lambda r: httpx.Response(422, json=corpo)))
    with pytest.raises(ApolloSemCreditos):
        asyncio.run(cliente.organizacao(DOMINIO))


@pytest.mark.parametrize("status, transitorio", [(402, False), (401, False), (503, True), (408, True)])
def test_erros_do_apify(status, transitorio):
    cliente = ClienteApify("token-teste", transport=ApifyFalso(status=status).transporte())
    with pytest.raises(ErroApify) as exc:
        asyncio.run(cliente.verificar(["a@b.com.br"]))
    assert exc.value.transitorio is transitorio


def test_contato_valido_de_rodada_anterior_conta_na_conclusao(engine):
    # Caso real: a Rede Santa Catarina já tinha decisores verificados pelo Apollo; a rodada alternativa não
    # achou ninguém novo e a empresa não pode voltar a "sem decisores"
    eid = _empresa(engine)
    with engine.begin() as conn:
        conn.execute(
            contatos.insert().values(
                id=uuid.uuid4(),
                empresa_id=eid,
                nome="Sandro M",
                area="TI",
                email=f"sandro@{DOMINIO}",
                email_status="valido",
                opt_out=False,
                fonte="apollo",
                criado_em=datetime.now(UTC),
            )
        )
    resultado = _rodar(engine, _apollo_sem_creditos(), ApifyFalso(), IAMapeadora([], []), eid)
    assert resultado == "decisores_mapeados"
    with engine.connect() as conn:
        assert conn.scalar(select(empresas.c.estado).where(empresas.c.id == eid)) == "PREPARANDO_ABORDAGEM"


class IAComNomes(IAMapeadora):
    """Responde à busca de nome completo (prompt mapeador-nomes) com `nomes`; à busca genérica, com `WEB`."""

    def __init__(self, escolhas, nomes, urls=None):
        super().__init__(escolhas, WEB, urls)
        self.nomes = nomes
        self.sistemas: list[str] = []

    async def com_busca_web(self, *, modelo, sistema, conteudo, max_buscas, effort, max_tokens):
        self.sistemas.append(sistema)
        if "nome completo" in sistema:
            from slp_workers.llm import Consumo, RespostaBusca

            texto = "```json\n" + json.dumps({"pessoas": self.nomes, "raciocinio_resumido": "site"}) + "\n```"
            return RespostaBusca(texto=texto, urls_consultadas=self.urls_web, consumo=Consumo(modelo=modelo))
        return await super().com_busca_web(
            modelo=modelo,
            sistema=sistema,
            conteudo=conteudo,
            max_buscas=max_buscas,
            effort=effort,
            max_tokens=max_tokens,
        )


ESCOLHA_APOLLO = [
    {"candidato_id": "apollo:a1", "area": "TI", "motivo": "Lidera tecnologia."},
    {"candidato_id": "apollo:a2", "area": "Marketing", "motivo": "Responde pelo site."},
]


def test_sem_creditos_usa_a_busca_gratis_do_apollo_e_completa_o_nome_na_web(engine):
    eid = _empresa(engine)
    nomes = [
        {"id": "apollo:a1", "nome": "Ana Souza", "fonte_url": FONTE, "linkedin_url": None},
        # O Apollo abreviou "L***s": "Silva" não confere e é descartado (pode ser homônimo)
        {"id": "apollo:a2", "nome": "Bruno Silva", "fonte_url": FONTE, "linkedin_url": None},
    ]
    ia = IAComNomes(ESCOLHA_APOLLO, nomes)
    apify = ApifyFalso({f"ana.souza@{DOMINIO}": _item(f"ana.souza@{DOMINIO}")})
    assert _rodar(engine, _apollo_sem_creditos(), apify, ia, eid) == "decisores_mapeados"

    salvos = _contatos(engine, eid)
    assert [(c.nome, c.area, c.email_status, c.fonte) for c in salvos] == [
        ("Ana Souza", "TI", "valido", "web+apify")
    ]
    assert len(ia.sistemas) == 1 and "nome completo" in ia.sistemas[0]  # sem a busca genérica
    assert len(apify.chamadas[0]["emails"]) == 5  # só a Ana teve o nome confirmado


class IAQueAnotaModelos(IAComNomes):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.modelos_busca: list[str] = []

    async def com_busca_web(self, *, modelo, **kwargs):
        self.modelos_busca.append(modelo)
        return await super().com_busca_web(modelo=modelo, **kwargs)


def test_busca_web_do_mapeador_usa_o_haiku_por_padrao(engine):
    # ADR 0013: os resultados da busca são ~37 mil tokens; no Haiku custam 1/20 do Sonnet
    assert WorkerConfig().model_web_search == "claude-haiku-5-5"
    eid = _empresa(engine)
    apollo = _apollo_sem_creditos()
    apollo.pessoas = []
    ia = IAQueAnotaModelos([], [])
    _rodar(engine, apollo, ApifyFalso(), ia, eid)
    assert ia.modelos_busca == ["claude-haiku-5-5"]


def test_modelo_da_busca_web_vem_da_configuracao(engine):
    eid = _empresa(engine)
    nomes = [{"id": "apollo:a1", "nome": "Ana Souza", "fonte_url": FONTE, "linkedin_url": None}]
    ia = IAQueAnotaModelos(ESCOLHA_APOLLO, nomes)
    _rodar(engine, _apollo_sem_creditos(), ApifyFalso(), ia, eid, model_web_search="claude-sonnet-5-5")
    assert ia.modelos_busca and set(ia.modelos_busca) == {"claude-sonnet-5-5"}


def test_sem_ninguem_na_busca_do_apollo_cai_na_busca_generica(engine):
    eid = _empresa(engine)
    apollo = _apollo_sem_creditos()
    apollo.pessoas = []
    ia = IAComNomes([], [])
    apify = ApifyFalso({f"ana.souza@{DOMINIO}": _item(f"ana.souza@{DOMINIO}")})
    assert _rodar(engine, apollo, apify, ia, eid) == "decisores_mapeados"
    assert all("nome completo" not in s for s in ia.sistemas)


@pytest.mark.parametrize(
    "nome, primeiro, ofuscado, ok",
    [
        ("Sandro Marchette", "Sandro", "M***e", True),
        ("Sandro Luiz Marchette", "Sandro", "M***e", True),
        ("Sandro Silva", "Sandro", "M***e", False),
        ("Sândro Marchette", "Sandro", "M***e", True),  # acento não atrapalha
        ("Carlos Marchette", "Sandro", "M***e", False),
        ("Sandro", "Sandro", "M***e", False),
    ],
)
def test_nome_completo_precisa_bater_com_a_abreviacao_do_apollo(nome, primeiro, ofuscado, ok):
    from slp_workers.agents.mapeador import nome_confere

    assert nome_confere(nome, primeiro, ofuscado) is ok


def test_esquema_dos_nomes_completos_esta_atualizado():
    from pathlib import Path

    from slp_workers.agents.mapeador import NomesCompletos

    esquema = Path(__file__).resolve().parents[2] / "packages" / "schemas" / "mapeador-nomes.schema.json"
    assert json.loads(esquema.read_text(encoding="utf-8")) == NomesCompletos.model_json_schema()

