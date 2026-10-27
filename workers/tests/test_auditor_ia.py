"""Auditor com IA (Tarefa 4): regras fixas, validação da saída do modelo e orquestração até a qualificação."""

import asyncio
import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select

from slp_workers.agents.auditor import (
    AchadoIA,
    AnaliseIA,
    ErroHonestidade,
    IndicioVisual,
    ResultadoAuditoriaIA,
    analisar,
    montar_conteudo,
    validar_analise,
)
from slp_workers.audit.artefatos import ArmazenamentoMemoria
from slp_workers.audit.regras import (
    calcular_nota,
    classificar,
    frases_proibidas,
    problemas_da_auditoria,
    separar_plugin_codigo,
    tabela_plugin,
)
from slp_workers.db import acoes_agentes, auditorias, empresas, eventos
from slp_workers.llm import Consumo
from slp_workers.orchestrator.auditoria import auditar_empresa
from slp_workers.orchestrator.pipeline import processar_empresa
from slp_workers.settings import WorkerConfig
from tests.conftest import inserir_empresa, montar_ctx

ESQUEMA = Path(__file__).resolve().parents[2] / "packages" / "schemas" / "auditoria.schema.json"
HOME = "https://exemplo.com.br/"
CONTATO = "https://exemplo.com.br/contato"


def _violacao(regra, gravidade, n=1, html="<img src=x>", criterios=("wcag111",)):
    return {
        "regra": regra,
        "gravidade": gravidade,
        "ocorrencias": n,
        "descricao": regra,
        "criterios_wcag": list(criterios),
        "exemplos": [{"alvo": "x", "html": html}],
    }


def _pagina(url, violacoes, armadilha=None, pular=True, sem_indicador=0, rolagem=False, semantica=None):
    return {
        "url": url,
        "status": "ok",
        "prints": {"desktop": f"s3://teste/{url[-7:]}.png"},
        "axe": {"violacoes": violacoes},
        "teclado": {
            "armadilha_de_foco": armadilha,
            "link_pular_conteudo": pular,
            "sem_indicador_aparente": sem_indicador,
        },
        "responsivo_320": {"rolagem_horizontal": rolagem},
        "semantica": semantica,
    }


PAGINAS = [
    _pagina(
        HOME,
        [_violacao("image-alt", "critico", 4), _violacao("color-contrast", "grave", 9, html="<p>x</p>")],
        pular=False,
        semantica={"links_genericos": [{"texto": "saiba mais"}], "saltos_de_titulo": []},
    ),
    _pagina(
        CONTATO,
        [
            _violacao("label", "critico", 2, html='<input id="nome">', criterios=("wcag131", "wcag412")),
            _violacao("color-contrast", "grave", 1, html="<p>y</p>"),
        ],
        armadilha={"elementos": ["input#a"]},
    ),
    {"url": "https://exemplo.com.br/vagas", "status": "bloqueada", "erro": "robots.txt"},
]


# --- Problemas e nota --------------------------------------------------------


def test_agrupa_problemas_por_tipo_entre_paginas():
    problemas = {p.chave: p for p in problemas_da_auditoria(PAGINAS)}
    assert problemas["color-contrast"].paginas == (HOME, CONTATO)
    assert problemas["color-contrast"].ocorrencias == 10
    assert problemas["teclado:armadilha_de_foco"].gravidade == "critico"
    assert problemas["teclado:sem_link_pular_conteudo"].paginas == (HOME,)
    assert problemas["semantica:links_genericos"].gravidade == "moderado"
    # Do mais grave para o mais leve
    ordem = [p.gravidade for p in problemas_da_auditoria(PAGINAS)]
    assert ordem == sorted(ordem, key=["critico", "grave", "moderado", "leve"].index)


def test_nota_reproduzivel_e_explicada():
    problemas = problemas_da_auditoria(PAGINAS)
    nota, descontos = calcular_nota(problemas)
    # image-alt 12, label 12, armadilha 12, contraste 6+1 (2 páginas), pular 3, links genéricos 3
    assert nota == 100 - (12 + 12 + 12 + 7 + 3 + 3)
    assert calcular_nota(problemas) == (nota, descontos)
    assert {"problema": "color-contrast", "gravidade": "grave", "pontos": 7} in descontos


def test_nota_entre_0_e_100():
    assert calcular_nota([])[0] == 100
    muitos = problemas_da_auditoria([_pagina(HOME, [_violacao(f"regra-{i}", "critico") for i in range(20)])])
    assert calcular_nota(muitos)[0] == 0


# --- Plugin × código ---------------------------------------------------------


def test_separacao_plugin_codigo_pela_tabela():
    assert classificar("color-contrast")[0] == "plugin_parcial"
    assert classificar("image-alt") == ("codigo", "imagens sem texto alternativo")
    assert classificar("aria-required-attr")[0] == "codigo"
    assert classificar("regra-nova-do-axe") == ("codigo", "regra-nova-do-axe")  # na dúvida, código
    plugin, codigo = separar_plugin_codigo(problemas_da_auditoria(PAGINAS))
    assert plugin == ["contraste de cores"]
    assert "campos de formulário sem rótulo" in codigo
    assert "foco do teclado preso em parte da página" in codigo


@pytest.mark.parametrize(
    "regra",
    [
        "image-alt",
        "color-contrast",
        "label-content-name-mismatch",
        "link-name",
        "target-size",
        "label",
        "button-name",
    ],
)
def test_regras_vistas_nas_auditorias_reais_estao_na_tabela(regra):
    assert regra in tabela_plugin()["problemas"]


# --- Honestidade (§2.2) ------------------------------------------------------


@pytest.mark.parametrize(
    "texto",
    [
        "Com o plugin o site fica 100% acessível.",
        "Deixe seu site TOTALMENTE ACESSÍVEL",
        "Isso garante a conformidade com a LBI",
        "adequação total à lei",
        "resolve todas as barreiras do site",
    ],
)
def test_barra_promessas_proibidas(texto):
    assert frases_proibidas(texto)


def test_texto_honesto_passa():
    assert (
        frases_proibidas("O plugin ajuda com contraste, mas imagens sem descrição exigem ajuste no código.")
        == []
    )


# --- Validação da saída do modelo --------------------------------------------


def _achado(problema="label", pagina=CONTATO, trecho='<input id="nome">'):
    return AchadoIA(
        problema=problema,
        pagina=pagina,
        titulo="Formulário sem rótulos",
        impacto_humano="Quem usa leitor de tela não sabe o que digitar.",
        quem_e_afetado=["pessoas cegas"],
        criterio_wcag="1.3.1",
        trecho_html=trecho,
    )


def _analise(*achados, indicios=()):
    return AnaliseIA(
        top3_para_leigos=list(achados), indicios_visuais=list(indicios), raciocinio_resumido="ok"
    )


def test_descarta_achado_inventado_e_corrige_trecho():
    problemas = problemas_da_auditoria(PAGINAS)
    analise = _analise(
        _achado(),
        _achado(problema="regra-inventada"),
        _achado(problema="image-alt", pagina=CONTATO),  # imagem sem alt não está no contato
        _achado(problema="image-alt", pagina="https://exemplo.com.br", trecho="<img inventada>"),
        _achado(),  # repetido
        indicios=[
            IndicioVisual(tipo="texto_em_imagem", descricao="banner", pagina=HOME),
            IndicioVisual(tipo="outro", descricao="x", pagina="https://outro.com/"),
        ],
    )
    validada, descartados = validar_analise(analise, problemas, PAGINAS)
    assert [a.problema for a in validada.top3_para_leigos] == ["label", "image-alt"]
    assert validada.top3_para_leigos[0].trecho_html == '<input id="nome">'
    assert validada.top3_para_leigos[1].trecho_html is None  # trecho inventado é apagado
    assert validada.top3_para_leigos[1].pagina == HOME
    assert descartados == 3
    assert len(validada.indicios_visuais) == 1


def test_no_maximo_3_achados():
    problemas = problemas_da_auditoria(PAGINAS)
    analise = _analise(
        _achado(),
        _achado("image-alt", HOME, None),
        _achado("color-contrast", HOME, None),
        _achado("teclado:armadilha_de_foco", CONTATO, None),
    )
    assert len(validar_analise(analise, problemas, PAGINAS)[0].top3_para_leigos) == 3


def test_envia_prints_como_imagem_ao_modelo():
    blocos = montar_conteudo(
        "Hospital", "saude", PAGINAS, problemas_da_auditoria(PAGINAS), [(HOME, b"\x89PNG")]
    )
    assert [b["type"] for b in blocos] == ["text", "image", "text"]
    assert blocos[1]["source"]["media_type"] == "image/png"
    dados = json.loads(blocos[2]["text"].split("<problemas>\n")[1].split("\n</problemas>")[0])
    assert dados[0]["problema"] in {"image-alt", "label", "teclado:armadilha_de_foco"}
    assert all("exemplos_html" in d for d in dados)


class IAAuditora:
    """Claude simulada para o Auditor: devolve as análises na ordem dada."""

    def __init__(self, *respostas):
        self.respostas = list(respostas)
        self.chamadas = []

    async def estruturado(self, *, modelo, sistema, conteudo, formato, effort, max_tokens):
        assert formato is AnaliseIA
        self.chamadas.append(sistema)
        return self.respostas.pop(0), Consumo(
            modelo=modelo, tokens_in=20000, tokens_out=800, custo_brl=Decimal("0.30")
        )


def test_promessa_proibida_forca_nova_tentativa():
    desonesta = _analise(_achado().model_copy(update={"titulo": "Com o plugin o site fica 100% acessível"}))
    ia = IAAuditora(desonesta, _analise(_achado()))
    validada, _, gasto, _, _ = asyncio.run(analisar(ia, WorkerConfig(), "H", "saude", PAGINAS, []))
    assert len(ia.chamadas) == 2
    assert "ATENÇÃO" in ia.chamadas[1]
    assert gasto.custo_brl == Decimal("0.60")
    assert validada.top3_para_leigos[0].titulo == "Formulário sem rótulos"


def test_duas_respostas_desonestas_falham_com_o_gasto():
    desonesta = _analise(_achado().model_copy(update={"impacto_humano": "garante a conformidade total"}))
    with pytest.raises(ErroHonestidade) as exc:
        asyncio.run(analisar(IAAuditora(desonesta, desonesta), WorkerConfig(), "H", None, PAGINAS, []))
    assert exc.value.consumo.custo_brl == Decimal("0.60")


def test_esquema_publicado_esta_atualizado():
    assert json.loads(ESQUEMA.read_text(encoding="utf-8")) == ResultadoAuditoriaIA.model_json_schema()


# --- Orquestração ------------------------------------------------------------


def _com_auditoria(engine, nota=None):
    eid = inserir_empresa(engine, estado="AUDITANDO")
    aid = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(empresas.update().where(empresas.c.id == eid).values(setor="saude"))
        conn.execute(
            auditorias.insert().values(
                id=aid,
                empresa_id=eid,
                nota=nota,
                totais_json={"critico": 2, "grave": 1, "moderado": 0, "leve": 0, "paginas_auditadas": 2},
                achados_json=[],
                paginas_json=PAGINAS,
                artefatos_urls=[],
                criado_em=datetime.now(UTC),
            )
        )
    return eid, aid


def test_analise_grava_o_json_do_8_2_e_passa_para_qualificando(engine, monkeypatch):
    # O PDF do relatório tem testes próprios (test_relatorio.py); aqui só importa que ele é gerado
    monkeypatch.setattr("slp_workers.orchestrator.relatorio.gerar_pdf", lambda html: b"%PDF-teste")
    eid, aid = _com_auditoria(engine)
    armazenamento = ArmazenamentoMemoria()
    # Prints salvos pelo Auditor técnico (ver _pagina: s3://teste/<fim da url>.png)
    armazenamento.arquivos["com.br/.png"] = b"\x89PNG-home"
    armazenamento.arquivos["contato.png"] = b"\x89PNG-contato"
    ctx = montar_ctx(engine, IAAuditora(_analise(_achado(), _achado("image-alt", HOME, None))))
    ctx["armazenamento"] = armazenamento

    assert asyncio.run(processar_empresa(ctx, str(eid))) == "analise_pronta"

    with engine.connect() as conn:
        a = conn.execute(select(auditorias).where(auditorias.c.id == aid)).one()
        estado = conn.scalar(select(empresas.c.estado).where(empresas.c.id == eid))
        acao = conn.execute(
            select(acoes_agentes).where(
                acoes_agentes.c.empresa_id == eid, acoes_agentes.c.agente == "auditor"
            )
        ).one()
        ultimo = conn.execute(
            select(eventos.c.tipo, eventos.c.dados_json).where(
                eventos.c.empresa_id == eid, eventos.c.tipo == "analise_pronta"
            )
        ).first()
        tipos = [
            r.tipo
            for r in conn.execute(
                select(eventos.c.tipo).where(eventos.c.empresa_id == eid).order_by(eventos.c.ocorrido_em)
            )
        ]
    # Nota 51, saúde, sem dossiê: score 48 (morno) → segue para o mapeamento de decisores (Fase 2)
    assert estado == "MAPEANDO_DECISORES"
    assert a.nota == 100 - (12 + 12 + 12 + 7 + 3 + 3)
    resultado = ResultadoAuditoriaIA.model_validate(a.achados_json)
    assert [x.problema for x in resultado.top3_para_leigos] == ["label", "image-alt"]
    assert resultado.top3_para_leigos[0].pagina == "/contato"
    assert resultado.top3_para_leigos[0].evidencia.print == "s3://teste/contato.png"
    assert resultado.plugin_resolve_parcialmente == ["contraste de cores"]
    assert resultado.totais.critico == 2
    assert "só parte das barreiras" in resultado.observacao_honestidade
    assert (acao.agente, acao.custo) == ("auditor", Decimal("0.3000"))
    assert ultimo.tipo == "analise_pronta"
    assert f"nota {a.nota} de 100" in ultimo.dados_json["mensagem"]
    assert ultimo.dados_json["prints_analisados"] == 2
    # Fim da análise: Qualificador e mini-relatório; sem chave do Apollo, o Mapeador só registra que espera
    assert tipos[-4:] == ["analise_pronta", "qualificado", "relatorio_pronto", "apollo_nao_configurado"]
    assert any(k.startswith(f"relatorios/{eid}/") and k.endswith(".pdf") for k in armazenamento.arquivos)


def test_auditoria_ja_analisada_nao_gasta_de_novo(engine):
    eid, _ = _com_auditoria(engine, nota=70)
    ia = IAAuditora()
    assert asyncio.run(processar_empresa(montar_ctx(engine, ia), str(eid))) == "ja_analisada"
    assert ia.chamadas == []


def test_falha_na_analise_vira_evento_proprio(engine):
    eid, _ = _com_auditoria(engine)
    desonesta = _analise(_achado().model_copy(update={"titulo": "site 100% acessível"}))
    assert (
        asyncio.run(processar_empresa(montar_ctx(engine, IAAuditora(desonesta, desonesta)), str(eid)))
        == "falhou"
    )
    with engine.connect() as conn:
        tipos = [r.tipo for r in conn.execute(select(eventos.c.tipo).where(eventos.c.empresa_id == eid))]
        estado = conn.scalar(select(empresas.c.estado).where(empresas.c.id == eid))
        gasto = conn.scalar(select(acoes_agentes.c.custo).where(acoes_agentes.c.empresa_id == eid))
    assert "analise_falhou" in tipos
    assert estado == "AUDITANDO"
    assert gasto == Decimal("0.6000")


def test_auditoria_tecnica_pronta_chama_a_analise(engine):
    from tests.test_auditor import RESULTADO, AuditorFalso

    eid = inserir_empresa(engine, estado="AUDITANDO")
    chamados = []

    async def enfileirar(empresa_id):
        chamados.append(empresa_id)
        return True

    ctx = {
        "engine": engine,
        "limitador": None,
        "armazenamento": None,
        "config": WorkerConfig(),
        "auditor": AuditorFalso(RESULTADO),
        "enfileirar_analise": enfileirar,
    }
    assert asyncio.run(auditar_empresa(ctx, str(eid))) == "auditoria_pronta"
    assert chamados == [eid]


def test_analise_vai_para_a_fila_do_worker_principal():
    # O redis do worker-audit tem a fila de auditoria como padrão; a análise precisa ir para a fila principal
    from arq.constants import default_queue_name

    from slp_workers.filas import FILA_PRINCIPAL
    from slp_workers.orchestrator.auditoria import _enfileirador_principal

    assert FILA_PRINCIPAL == default_queue_name
    chamadas = []

    class RedisFalso:
        async def enqueue_job(self, funcao, *args, **kwargs):
            chamadas.append((funcao, args, kwargs))
            return object()

    eid = uuid.uuid4()
    assert asyncio.run(_enfileirador_principal(RedisFalso())(eid)) is True
    funcao, args, kwargs = chamadas[0]
    assert funcao == "processar_empresa" and args == (str(eid),)
    assert kwargs["_queue_name"] == FILA_PRINCIPAL
    assert kwargs["_job_id"] == f"processar_empresa:{eid}"
