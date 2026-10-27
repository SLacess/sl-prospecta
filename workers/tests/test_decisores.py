"""Mapeador de decisores (Fase 2, Tarefa 2): Apollo e Claude simulados, sem nenhuma chamada externa."""

import asyncio
import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from sqlalchemy import select

from slp_workers.agents.mapeador import (
    BuscaWebDecisores,
    Candidato,
    Escolha,
    EscolhaMapeador,
    PessoaWeb,
    validar_escolha,
    validar_pessoas_web,
)
from slp_workers.db import acoes_agentes, auditorias, contatos, empresas, eventos, qualificacoes, supressao
from slp_workers.llm import Consumo, RespostaBusca
from slp_workers.orchestrator.decisores import (
    CreditosEsgotados,
    DependenciasDecisores,
    Mapeamento,
    uf_do_estado,
)
from slp_workers.orchestrator.pipeline import processar_empresa
from slp_workers.settings import WorkerConfig
from slp_workers.web.apollo import ClienteApollo
from slp_workers.web.emails import validar_email
from tests.conftest import inserir_empresa, montar_ctx

DOMINIO = "hospital-x.com.br"
FONTE = f"https://{DOMINIO}/diretoria"


# --- Apollo simulado ---------------------------------------------------------


class ApolloFalso:
    """Responde às três rotas usadas e registra as chamadas (para contar créditos e conferir parâmetros)."""

    def __init__(self, pessoas=None, enriquecidas=None, org=None, status_org=200):
        self.chamadas: list[tuple[str, dict]] = []
        self.pessoas = (
            pessoas
            if pessoas is not None
            else [
                {
                    "id": "a1",
                    "first_name": "Ana",
                    "last_name_obfuscated": "S***a",
                    "title": "CTO",
                    "has_email": True,
                },
                {
                    "id": "a2",
                    "first_name": "Bruno",
                    "last_name_obfuscated": "L***s",
                    "title": "CMO",
                    "has_email": True,
                },
            ]
        )
        self.enriquecidas = (
            enriquecidas
            if enriquecidas is not None
            else {
                "a1": {
                    "id": "a1",
                    "name": "Ana Souza",
                    "title": "CTO",
                    "email": f"ana@{DOMINIO}",
                    "email_status": "verified",
                    "linkedin_url": "http://www.linkedin.com/in/ana-souza",
                    "match_confidence": "high",
                },
                "a2": {
                    "id": "a2",
                    "name": "Bruno Lopes",
                    "title": "CMO",
                    "email": f"bruno@{DOMINIO}",
                    "email_status": "unverified",
                    "match_confidence": "high",
                },
            }
        )
        self.org = (
            org
            if org is not None
            else {
                "estimated_num_employees": 1600,
                "city": "Sorocaba",
                "state": "São Paulo",
                "country": "Brazil",
            }
        )
        self.status_org = status_org

    def transporte(self) -> httpx.MockTransport:
        def responder(request: httpx.Request) -> httpx.Response:
            params = {
                k: v if len(v) > 1 or k.endswith("[]") else v[0]
                for k, v in parse_qs(urlsplit(str(request.url)).query).items()
            }
            caminho = request.url.path.removeprefix("/api/v1")
            self.chamadas.append((caminho, params))
            assert request.headers["x-api-key"] == "chave-teste"
            if caminho == "/organizations/enrich":
                return httpx.Response(self.status_org, json={"organization": self.org})
            if caminho == "/mixed_people/api_search":
                return httpx.Response(200, json={"total_entries": len(self.pessoas), "people": self.pessoas})
            if caminho == "/people/match":
                assert (
                    params["reveal_personal_emails"] == "false" and params["reveal_phone_number"] == "false"
                )
                chave = params.get("id") or params.get("name")
                return httpx.Response(200, json={"person": self.enriquecidas.get(chave)})
            return httpx.Response(404)

        return httpx.MockTransport(responder)


class IAMapeadora:
    def __init__(self, escolhas: list[dict], pessoas_web: list[dict] | None = None, urls_web=None):
        self.escolhas = escolhas
        self.pessoas_web = pessoas_web or []
        self.urls_web = urls_web or [FONTE]
        self.modelos: list[str] = []
        self.buscas = 0

    async def estruturado(self, *, modelo, sistema, conteudo, formato, effort, max_tokens):
        self.modelos.append(modelo)
        escolha = EscolhaMapeador(escolhidos=[Escolha(**e) for e in self.escolhas], raciocinio_resumido="ok")
        return escolha, Consumo(modelo=modelo, tokens_in=500, tokens_out=80, custo_brl=Decimal("0.0010"))

    async def com_busca_web(self, *, modelo, sistema, conteudo, max_buscas, effort, max_tokens):
        self.buscas += 1
        assert "LinkedIn" in sistema
        texto = (
            "```json\n" + json.dumps({"pessoas": self.pessoas_web, "raciocinio_resumido": "site"}) + "\n```"
        )
        return RespostaBusca(
            texto=texto,
            urls_consultadas=self.urls_web,
            consumo=Consumo(modelo=modelo, buscas_web=1, custo_brl=Decimal("0.0800")),
        )


async def mx_ok(dominio):
    return True


def _empresa(engine, estado="MAPEANDO_DECISORES", setor="saude"):
    eid = inserir_empresa(engine, nome="Hospital X", dominio=DOMINIO, estado=estado)
    with engine.begin() as conn:
        conn.execute(empresas.update().where(empresas.c.id == eid).values(setor=setor))
        conn.execute(
            auditorias.insert().values(
                id=uuid.uuid4(),
                empresa_id=eid,
                nota=30,
                totais_json={},
                achados_json={},
                paginas_json=[],
                artefatos_urls=[],
                criado_em=datetime.now(UTC),
            )
        )
    return eid


def _deps(engine, apollo: ApolloFalso, ia, **config):
    cfg = WorkerConfig(apollo_api_key="chave-teste", **config)
    cliente = ClienteApollo("chave-teste", transport=apollo.transporte(), espera_429_s=0)
    return DependenciasDecisores(engine=engine, ia=ia, config=cfg, apollo=cliente, resolvedor_mx=mx_ok)


def _rodar(engine, apollo, ia, eid, **config):
    return asyncio.run(Mapeamento(_deps(engine, apollo, ia, **config), eid).executar())


def _contatos(engine, eid):
    with engine.connect() as conn:
        return conn.execute(
            select(contatos).where(contatos.c.empresa_id == eid).order_by(contatos.c.area)
        ).all()


def _tipos(engine, eid):
    with engine.connect() as conn:
        return [
            r.tipo
            for r in conn.execute(
                select(eventos.c.tipo).where(eventos.c.empresa_id == eid).order_by(eventos.c.ocorrido_em)
            )
        ]


ESCOLHA_PADRAO = [
    {"candidato_id": "apollo:a1", "area": "TI", "motivo": "Lidera tecnologia."},
    {"candidato_id": "apollo:a2", "area": "Marketing", "motivo": "Responde pelo site."},
]


# --- Fluxo completo ----------------------------------------------------------


def test_mapeia_decisores_valida_email_e_segue_para_preparando(engine):
    eid = _empresa(engine)
    apollo = ApolloFalso()
    ia = IAMapeadora(ESCOLHA_PADRAO)
    assert _rodar(engine, apollo, ia, eid) == "decisores_mapeados"

    ana, bruno = sorted(_contatos(engine, eid), key=lambda c: c.nome)
    assert (ana.nome, ana.area, ana.email, ana.email_status) == (
        "Ana Souza",
        "TI",
        f"ana@{DOMINIO}",
        "valido",
    )
    assert ana.linkedin_url == "http://www.linkedin.com/in/ana-souza" and ana.fonte == "apollo"
    assert (bruno.area, bruno.email_status) == ("Marketing", "nao_verificado")  # Apollo não verificou

    with engine.connect() as conn:
        e = conn.execute(select(empresas).where(empresas.c.id == eid)).one()
        q = conn.execute(select(qualificacoes).where(qualificacoes.c.empresa_id == eid)).one()
        creditos = conn.scalar(
            select(acoes_agentes.c.creditos)
            .where(acoes_agentes.c.agente == "mapeador.apollo")
            .order_by(acoes_agentes.c.criado_em)
            .limit(1)
        )
        total = sum(r.creditos for r in conn.execute(select(acoes_agentes.c.creditos)))
    assert e.estado == "PREPARANDO_ABORDAGEM"
    assert (e.porte, e.uf, e.cidade) == ("1600", "SP", "Sorocaba")  # dados da empresa no Apollo
    decisor = next(c for c in q.componentes_json if c["chave"] == "acessibilidade_decisor")
    assert decisor["valor"] == 100  # requalificada com 1 contato válido
    assert creditos == 1 and total == 3  # empresa + 2 pessoas; a busca não gasta crédito
    assert ia.modelos == ["claude-haiku-5-5"] and ia.buscas == 1  # faltou 1 área: busca web
    tipos = _tipos(engine, eid)
    assert tipos[0] == "mapeando_decisores" and tipos[-1] == "decisores_encontrados"
    assert "buscando_decisores_web" in tipos

    busca = next(p for c, p in apollo.chamadas if c == "/mixed_people/api_search")
    assert busca["q_organization_domains_list[]"] == [DOMINIO]
    assert "CTO" in busca["person_titles[]"] and "director" in busca["person_seniorities[]"]


def test_area_que_falta_vem_da_busca_web_e_tem_o_email_confirmado_no_apollo(engine):
    eid = _empresa(engine)
    apollo = ApolloFalso()
    apollo.enriquecidas["Carla Dias"] = {
        "id": "w1",
        "name": "Carla Dias",
        "title": "Diretora de Compliance",
        "email": f"carla@{DOMINIO}",
        "email_status": "verified",
        "match_confidence": "high",
    }
    web = [
        {
            "nome": "Carla Dias",
            "cargo": "Diretora de Compliance",
            "area": "Compliance",
            "fonte_url": FONTE,
            "linkedin_url": None,
        }
    ]
    assert _rodar(engine, apollo, IAMapeadora(ESCOLHA_PADRAO, web), eid) == "decisores_mapeados"
    carla = next(c for c in _contatos(engine, eid) if c.area == "Compliance")
    assert (carla.fonte, carla.fonte_url, carla.email_status) == ("web+apollo", FONTE, "valido")
    match = [p for c, p in apollo.chamadas if c == "/people/match" and "name" in p]
    assert match == [
        {
            "reveal_personal_emails": "false",
            "reveal_phone_number": "false",
            "name": "Carla Dias",
            "domain": DOMINIO,
        }
    ]


def test_sem_email_valido_fica_em_mapeando_decisores(engine):
    eid = _empresa(engine)
    apollo = ApolloFalso()
    apollo.enriquecidas["a1"]["email_status"] = "unverified"
    ia = IAMapeadora(ESCOLHA_PADRAO)
    assert _rodar(engine, apollo, ia, eid) == "sem_decisores"
    with engine.connect() as conn:
        assert conn.scalar(select(empresas.c.estado).where(empresas.c.id == eid)) == "MAPEANDO_DECISORES"
    assert _tipos(engine, eid)[-1] == "sem_decisores"


def test_apollo_sem_chave_nao_quebra(engine):
    eid = _empresa(engine)
    deps = _deps(engine, ApolloFalso(), IAMapeadora([]))
    deps.apollo = ClienteApollo("")
    assert asyncio.run(Mapeamento(deps, eid).executar()) == "apollo_nao_configurado"
    assert _tipos(engine, eid) == ["apollo_nao_configurado"]


def test_dominio_suprimido_nao_busca_ninguem(engine):
    eid = _empresa(engine)
    with engine.begin() as conn:
        conn.execute(supressao.insert().values(id=uuid.uuid4(), dominio=DOMINIO, motivo="pediu para sair"))
    apollo = ApolloFalso()
    assert _rodar(engine, apollo, IAMapeadora(ESCOLHA_PADRAO), eid) == "dominio_suprimido"
    assert apollo.chamadas == []


def test_email_suprimido_nao_e_gravado_e_nao_aparece_no_evento(engine):
    eid = _empresa(engine)
    with engine.begin() as conn:
        conn.execute(supressao.insert().values(id=uuid.uuid4(), email=f"ana@{DOMINIO}", motivo="opt-out"))
    _rodar(engine, ApolloFalso(), IAMapeadora(ESCOLHA_PADRAO), eid)
    assert [c.nome for c in _contatos(engine, eid)] == ["Bruno Lopes"]
    with engine.connect() as conn:
        msg = conn.scalar(select(eventos.c.dados_json).where(eventos.c.tipo == "contato_suprimido"))[
            "mensagem"
        ]
    assert "ana@" not in msg


def test_email_de_outro_dominio_e_descartado(engine):
    eid = _empresa(engine)
    apollo = ApolloFalso()
    apollo.enriquecidas["a1"]["email"] = "ana.pessoal@gmail.com"
    _rodar(engine, apollo, IAMapeadora(ESCOLHA_PADRAO), eid)
    ana = next(c for c in _contatos(engine, eid) if c.area == "TI")
    assert (ana.email, ana.email_status) == (None, "sem_email")


def test_teto_de_creditos_para_antes_de_chamar_o_apollo(engine):
    eid = _empresa(engine)
    apollo = ApolloFalso()
    with pytest.raises(CreditosEsgotados):
        _rodar(engine, apollo, IAMapeadora(ESCOLHA_PADRAO), eid, apollo_daily_credit_cap=3)
    assert apollo.chamadas == []


def test_reprocessar_nao_duplica_contatos(engine):
    eid = _empresa(engine)
    apollo = ApolloFalso()
    apollo.enriquecidas["a1"]["email_status"] = "unverified"  # fica em MAPEANDO_DECISORES
    ia = IAMapeadora(ESCOLHA_PADRAO)
    _rodar(engine, apollo, ia, eid)
    _rodar(engine, apollo, ia, eid)
    assert len(_contatos(engine, eid)) == 2


def test_pipeline_pausa_o_job_quando_os_creditos_acabam(engine, monkeypatch):
    from arq import Retry

    eid = _empresa(engine)
    ctx = montar_ctx(engine, IAMapeadora(ESCOLHA_PADRAO), config=WorkerConfig(apollo_daily_credit_cap=2))
    ctx["apollo"] = ClienteApollo("chave-teste", transport=ApolloFalso().transporte())
    ctx["resolvedor_mx"] = mx_ok
    with pytest.raises(Retry):
        asyncio.run(processar_empresa(ctx, str(eid)))
    assert _tipos(engine, eid) == ["fila_pausada_apollo"]


def test_pipeline_mapeia_quem_esta_em_mapeando_decisores_uma_vez(engine):
    eid = _empresa(engine)
    ctx = montar_ctx(engine, IAMapeadora(ESCOLHA_PADRAO), config=WorkerConfig(apollo_api_key="chave-teste"))
    apollo = ApolloFalso()
    apollo.enriquecidas["a1"]["email_status"] = "unverified"
    ctx["apollo"] = ClienteApollo("chave-teste", transport=apollo.transporte())
    ctx["resolvedor_mx"] = mx_ok
    assert asyncio.run(processar_empresa(ctx, str(eid))) == "sem_decisores"
    assert asyncio.run(processar_empresa(ctx, str(eid))) == "ja_mapeada"


# --- Validações --------------------------------------------------------------


def _candidato(i, origem="apollo"):
    return Candidato(id=f"{origem}:{i}", nome=f"Pessoa {i}", cargo="Diretor", origem=origem)


def test_escolha_descarta_id_inventado_area_repetida_e_excesso():
    candidatos = [_candidato(i) for i in range(1, 6)]
    escolha = EscolhaMapeador(
        escolhidos=[
            Escolha(candidato_id="apollo:1", area="TI", motivo="."),
            Escolha(candidato_id="apollo:99", area="RH", motivo="."),  # não existe
            Escolha(candidato_id="apollo:2", area="TI", motivo="."),  # área repetida
            Escolha(candidato_id="apollo:1", area="RH", motivo="."),  # pessoa repetida
            Escolha(candidato_id="apollo:3", area="RH", motivo="."),
            Escolha(candidato_id="apollo:4", area="ESG", motivo="."),
            Escolha(candidato_id="apollo:5", area="Compliance", motivo="."),  # passa do máximo
        ],
        raciocinio_resumido=".",
    )
    validas, descartadas = validar_escolha(escolha, candidatos, maximo=3)
    assert [(c.id, e.area) for c, e in validas] == [
        ("apollo:1", "TI"),
        ("apollo:3", "RH"),
        ("apollo:4", "ESG"),
    ]
    assert descartadas == 4


def test_busca_web_nao_aceita_linkedin_como_fonte_nem_url_fora_dos_resultados():
    perfil = "https://br.linkedin.com/in/carla-dias"
    busca = BuscaWebDecisores(
        pessoas=[
            PessoaWeb(
                nome="Carla Dias", cargo="Compliance", area="Compliance", fonte_url=FONTE, linkedin_url=perfil
            ),
            PessoaWeb(nome="Davi Reis", cargo="CTO", area="TI", fonte_url=perfil),  # LinkedIn como fonte
            PessoaWeb(nome="Eva Lima", cargo="RH", area="RH", fonte_url="https://inventado.com/x"),
            PessoaWeb(nome="Fabio", cargo="ESG", area="ESG", fonte_url=FONTE),  # só primeiro nome
            PessoaWeb(
                nome="Gil Melo",
                cargo="CMO",
                area="Marketing",
                fonte_url=FONTE,
                linkedin_url="https://br.linkedin.com/in/gil",
            ),  # link fora dos resultados
        ],
        raciocinio_resumido=".",
    )
    validas, descartadas = validar_pessoas_web(
        busca, [FONTE, perfil], ["Compliance", "TI", "RH", "ESG", "Marketing"]
    )
    assert [(p.nome, p.linkedin_url) for p in validas] == [("Carla Dias", perfil), ("Gil Melo", None)]
    assert descartadas == 3


@pytest.mark.parametrize(
    "email, status_apollo, esperado",
    [
        (f"ana@{DOMINIO}", "verified", ("valido", True)),
        (f"Ana@Portal.{DOMINIO}", "verified", ("valido", True)),  # subdomínio da empresa
        (f"ana@{DOMINIO}", "unverified", ("nao_verificado", True)),
        (f"ana@{DOMINIO}", "extrapolated", ("nao_verificado", True)),
        ("ana@gmail.com", "verified", ("sem_email", False)),
        ("não é e-mail", "verified", ("sem_email", False)),
        (None, None, ("sem_email", False)),
    ],
)
def test_validacao_de_email(email, status_apollo, esperado):
    r = asyncio.run(validar_email(email, DOMINIO, status_apollo, mx_ok))
    assert (r.status, r.email is not None) == esperado


def test_email_sem_mx_nao_conta_como_valido():
    async def sem_mx(dominio):
        return False

    r = asyncio.run(validar_email(f"ana@{DOMINIO}", DOMINIO, "verified", sem_mx))
    assert r.status == "nao_verificado" and "MX" in r.motivo


@pytest.mark.parametrize(
    "estado, pais, uf",
    [
        ("São Paulo", "Brazil", "SP"),
        ("State of Rio de Janeiro", "Brazil", "RJ"),
        ("Federal District", "Brazil", "DF"),
        ("MG", "Brasil", "MG"),
        ("California", "United States", None),
        (None, "Brazil", None),
    ],
)
def test_uf_do_estado_do_apollo(estado, pais, uf):
    assert uf_do_estado(estado, pais) == uf


def test_apollo_429_tenta_de_novo_e_5xx_e_transitorio():
    from slp_workers.web.apollo import ErroApollo

    respostas = [
        httpx.Response(429),
        httpx.Response(200, json={"organization": {"estimated_num_employees": 10}}),
    ]
    cliente = ClienteApollo("k", transport=httpx.MockTransport(lambda r: respostas.pop(0)), espera_429_s=0)
    assert asyncio.run(cliente.organizacao(DOMINIO)).colaboradores == 10

    falha = ClienteApollo("k", transport=httpx.MockTransport(lambda r: httpx.Response(503)))
    with pytest.raises(ErroApollo) as exc:
        asyncio.run(falha.organizacao(DOMINIO))
    assert exc.value.transitorio


ESQUEMAS = Path(__file__).resolve().parents[2] / "packages" / "schemas"


def test_esquemas_publicados_estao_atualizados():
    assert json.loads((ESQUEMAS / "mapeador.schema.json").read_text(encoding="utf-8")) == (
        EscolhaMapeador.model_json_schema()
    )
    assert json.loads((ESQUEMAS / "mapeador-web.schema.json").read_text(encoding="utf-8")) == (
        BuscaWebDecisores.model_json_schema()
    )


def test_prompts_do_mapeador_proibem_linkedin_e_dados_pessoais():
    from slp_workers.agents.researcher import carregar_prompt

    web = carregar_prompt("mapeador-web")
    assert "Não use o LinkedIn como fonte" in web and "Não procure nem informe e-mail, telefone" in web
    assert "uma pessoa por área" in carregar_prompt("mapeador")


def test_email_corporativo_em_outro_dominio_vale_quando_o_apollo_confirma_a_empresa(engine):
    # Caso real: site hospitalsiriolibanes.org.br, e-mail @hsl.org.br
    eid = _empresa(engine)
    apollo = ApolloFalso()
    apollo.enriquecidas["a1"]["email"] = "ana@hsl-corp.org.br"
    _rodar(engine, apollo, IAMapeadora(ESCOLHA_PADRAO), eid)
    ana = next(c for c in _contatos(engine, eid) if c.area == "TI")
    assert (ana.email, ana.email_status) == ("ana@hsl-corp.org.br", "valido")


def test_webmail_nunca_vale_mesmo_com_a_empresa_confirmada():
    r = asyncio.run(validar_email("ana@gmail.com", DOMINIO, "verified", mx_ok, organizacao_confirmada=True))
    assert (r.email, r.status) == (None, "sem_email")


def test_pessoa_da_web_com_outro_dominio_precisa_do_registro_apontando_para_a_empresa(engine):
    eid = _empresa(engine)
    apollo = ApolloFalso()
    apollo.enriquecidas["Carla Dias"] = {
        "id": "w1",
        "name": "Carla Dias",
        "title": "Diretora de Compliance",
        "email": "carla@outra-org.com.br",
        "email_status": "verified",
        "match_confidence": "high",
        "organization": {"primary_domain": "outra-org.com.br", "website_url": "http://www.outra-org.com.br"},
    }
    web = [
        {
            "nome": "Carla Dias",
            "cargo": "Diretora de Compliance",
            "area": "Compliance",
            "fonte_url": FONTE,
            "linkedin_url": None,
        }
    ]
    _rodar(engine, apollo, IAMapeadora(ESCOLHA_PADRAO, web), eid)
    carla = next(c for c in _contatos(engine, eid) if c.area == "Compliance")
    assert (carla.email, carla.email_status) == (None, "sem_email")


def test_reprocessar_corrige_o_contato_existente(engine):
    eid = _empresa(engine)
    apollo = ApolloFalso()
    apollo.enriquecidas["a1"]["email"] = "ana@gmail.com"
    ia = IAMapeadora(ESCOLHA_PADRAO)
    _rodar(engine, apollo, ia, eid)
    apollo.enriquecidas["a1"]["email"] = f"ana@{DOMINIO}"
    _rodar(engine, apollo, ia, eid)
    ana = [c for c in _contatos(engine, eid) if c.nome == "Ana Souza"]
    assert len(ana) == 1 and ana[0].email_status == "valido"


@pytest.mark.parametrize(
    "cargo, area, coerente",
    [
        ("Gerente Regional de TI", "Marketing", False),  # caso real da Rede Santa Catarina
        ("Gerente Regional de TI", "TI", True),
        ("Head de Auditoria, Compliance e Privacidade de Dados", "Compliance", True),
        ("Diretora Jurídico e Compliance", "Compliance", True),
        ("Head of Marketing", "Marketing", True),
        ("Superintendente", "RH", True),  # cargo sem palavra conhecida: fica com o modelo
        ("Gerente de Atividades Assistenciais", "TI", True),  # "ti" dentro de palavra não conta
    ],
)
def test_area_precisa_bater_com_o_cargo(cargo, area, coerente):
    from slp_workers.agents.mapeador import area_coerente

    assert area_coerente(cargo, area) is coerente
