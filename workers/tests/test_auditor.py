"""Auditor técnico sem navegador: regras de análise, filtro de rede e orquestração."""

import asyncio
import uuid
from datetime import UTC, datetime

from sqlalchemy import select

from slp_workers.audit.axe import resumir
from slp_workers.audit.engine import FiltroRede, ResultadoAuditoria
from slp_workers.audit.plugins import detectar_plugins
from slp_workers.audit.teclado import analisar_sequencia
from slp_workers.db import auditorias, empresas, eventos
from slp_workers.filas import FILA_AUDITORIA
from slp_workers.main_audit import AuditWorkerSettings
from slp_workers.orchestrator.auditoria import auditar_empresa
from slp_workers.settings import WorkerConfig
from slp_workers.web.fetcher import LeituraBloqueada
from slp_workers.web.ratelimit import LimitadorMemoria
from tests.conftest import inserir_empresa

# --- Teclado -----------------------------------------------------------------


def _foco(seletor, tag="a", texto="", href=None, indicador=True):
    return {
        "seletor": seletor,
        "tag": tag,
        "texto": texto,
        "href": href,
        "indicador": indicador,
        "visivel": True,
    }


def test_link_pular_conteudo_no_primeiro_tab():
    r = analisar_sequencia([_foco("a#pular", texto="Pular para o conteúdo", href="#main"), _foco("a#x")], 10)
    assert r["link_pular_conteudo"] is True
    assert r["armadilha_de_foco"] is None


def test_sem_link_pular_quando_o_primeiro_foco_e_outro():
    r = analisar_sequencia(
        [_foco("a#logo", texto="Início", href="/"), _foco("a#pular", texto="Pular", href="#m")], 10
    )
    assert r["link_pular_conteudo"] is False


def test_detecta_armadilha_de_foco():
    paradas = [_foco("a#1"), _foco("a#2")] + [_foco(f"input#{c}", "input") for c in "abc" * 5]
    r = analisar_sequencia(paradas, focaveis=10)
    assert r["armadilha_de_foco"]["elementos"] == ["input#a", "input#b", "input#c"]


def test_poucos_focaveis_nao_e_armadilha():
    paradas = [_foco("a#1"), _foco("a#2"), None] * 6
    assert analisar_sequencia(paradas, focaveis=2)["armadilha_de_foco"] is None


def test_conta_elementos_sem_indicador_sem_repetir():
    paradas = [_foco("a#1", indicador=False), _foco("a#2"), _foco("a#1", indicador=False)]
    r = analisar_sequencia(paradas, focaveis=2)
    assert r["sem_indicador_aparente"] == 1
    assert r["elementos_alcancados"] == 2


# --- axe e plugins -----------------------------------------------------------


def test_resume_o_axe_com_os_nomes_do_paragrafo_8_2():
    bruto = {
        "versao": "4.14.0",
        "incompletos": 2,
        "violations": [
            {
                "id": "image-alt",
                "impact": "critical",
                "help": "Imagens precisam de texto alternativo",
                "helpUrl": "https://dequeuniversity.com/rules/axe/4.14/image-alt",
                "tags": ["cat.text-alternatives", "wcag2a", "wcag111", "section508"],
                "nodes": [{"target": ["img"], "html": "<img src=x>" + "a" * 500}] * 5,
            }
        ],
    }
    r = resumir(bruto)
    v = r["violacoes"][0]
    assert (v["gravidade"], v["ocorrencias"], v["criterios_wcag"]) == ("critico", 5, ["wcag111"])
    assert len(v["exemplos"]) == 3
    assert len(v["exemplos"][0]["html"]) == 300


def test_detecta_plugins_conhecidos():
    assert detectar_plugins(
        "https://cdn.userway.org/widget.js\nhttps://vlibras.gov.br/app/vlibras-plugin.js"
    ) == ["UserWay", "VLibras"]
    assert detectar_plugins("https://www.googletagmanager.com/gtm.js") == []


# --- Filtro de rede (SSRF) ---------------------------------------------------


async def _resolvedor(host):
    return {"site.com.br": ["93.184.216.34"], "interno.com.br": ["10.0.0.7"]}.get(host, ["93.184.216.34"])


def test_filtro_bloqueia_endereco_interno_e_libera_o_publico():
    filtro = FiltroRede(False, set(), _resolvedor)

    async def checar():
        return [
            await filtro.permitido("https://site.com.br/x.css"),
            await filtro.permitido("http://interno.com.br/"),
            await filtro.permitido("http://169.254.169.254/latest/meta-data"),
            await filtro.permitido("http://10.0.0.5:9000/artefatos"),
            await filtro.permitido("data:image/png;base64,AAAA"),
            await filtro.permitido("file:///etc/passwd"),
        ]

    assert asyncio.run(checar()) == [True, False, False, False, True, False]
    assert "http://interno.com.br" in filtro.bloqueadas


def test_filtro_libera_so_os_hosts_indicados():
    filtro = FiltroRede(False, {"127.0.0.1"}, _resolvedor)
    assert asyncio.run(filtro.permitido("http://127.0.0.1:8080/")) is True
    assert asyncio.run(filtro.permitido("http://10.0.0.1/")) is False


# --- Orquestração ------------------------------------------------------------


def _pagina_ok(url, violacoes, armadilha=None, pular=True, rolagem=False):
    return {
        "url": url,
        "status": "ok",
        "titulo": "t",
        "prints": {"desktop": "s3://t/1.png", "320px": "s3://t/2.png"},
        "axe": {"violacoes": violacoes, "incompletos": 0, "versao_axe": "4.14.0"},
        "teclado": {"armadilha_de_foco": armadilha, "link_pular_conteudo": pular},
        "responsivo_320": {"rolagem_horizontal": rolagem},
        "plugins": [],
    }


def _violacao(regra, gravidade, n=1):
    return {"regra": regra, "gravidade": gravidade, "ocorrencias": n}


RESULTADO = ResultadoAuditoria(
    dominio="exemplo.com.br",
    paginas=[
        _pagina_ok(
            "https://exemplo.com.br/",
            [_violacao("image-alt", "critico", 4), _violacao("color-contrast", "grave", 9)],
            pular=False,
            rolagem=True,
        ),
        _pagina_ok(
            "https://exemplo.com.br/contato", [_violacao("label", "critico", 2)], armadilha={"elementos": []}
        ),
        {"url": "https://exemplo.com.br/vagas", "status": "bloqueada", "erro": "robots.txt", "prints": {}},
    ],
    plugins=["UserWay"],
    artefatos=["s3://t/1.png", "s3://t/2.png"],
)


def test_totais_por_gravidade():
    t = RESULTADO.totais()
    assert (t["critico"], t["grave"], t["moderado"], t["leve"]) == (2, 1, 0, 0)
    assert (t["ocorrencias"], t["regras_distintas"], t["paginas_auditadas"]) == (15, 3, 2)
    assert t["paginas_com_armadilha_de_foco"] == 1
    assert t["paginas_sem_link_pular_conteudo"] == 1
    assert t["paginas_com_rolagem_horizontal_320"] == 1


class AuditorFalso:
    def __init__(self, resultado=None, erro=None):
        self.resultado = resultado
        self.erro = erro
        self.chamadas = []

    async def auditar(self, dominio, prefixo, ao_progresso):
        self.chamadas.append((dominio, prefixo))
        if self.erro:
            raise self.erro
        for i, p in enumerate(self.resultado.paginas, start=1):
            await ao_progresso(i, len(self.resultado.paginas), p["url"].split(".br")[1] or "/")
        return self.resultado


def _ctx(engine, auditor):
    return {
        "engine": engine,
        "limitador": LimitadorMemoria(0),
        "armazenamento": None,
        "config": WorkerConfig(),
        "auditor": auditor,
    }


def _tipos(engine, eid):
    with engine.connect() as conn:
        return [
            r.tipo
            for r in conn.execute(
                select(eventos.c.tipo).where(eventos.c.empresa_id == eid).order_by(eventos.c.ocorrido_em)
            )
        ]


def test_auditoria_grava_resultado_bruto_e_avisa(engine):
    eid = inserir_empresa(engine, estado="AUDITANDO")
    auditor = AuditorFalso(RESULTADO)
    assert asyncio.run(auditar_empresa(_ctx(engine, auditor), str(eid))) == "auditoria_pronta"

    tipos = _tipos(engine, eid)
    assert tipos[0] == "auditoria_iniciada"
    assert tipos.count("auditando_pagina") == 3
    assert tipos[-1] == "auditoria_pronta"
    with engine.connect() as conn:
        a = conn.execute(select(auditorias).where(auditorias.c.empresa_id == eid)).one()
        msg = conn.execute(select(eventos.c.dados_json).where(eventos.c.tipo == "auditoria_pronta")).scalar()
        progresso = conn.execute(
            select(eventos.c.dados_json).where(eventos.c.tipo == "auditando_pagina")
        ).first()[0]
        estado = conn.scalar(select(empresas.c.estado).where(empresas.c.id == eid))
    assert a.nota is None and a.achados_json == []  # nota e achados para leigos: Tarefa 4
    assert a.totais_json["critico"] == 2
    assert len(a.paginas_json) == 3
    assert a.artefatos_urls == ["s3://t/1.png", "s3://t/2.png"]
    assert estado == "AUDITANDO"  # QUALIFICANDO entra com o Auditor com IA (Tarefa 4)
    assert "2 crítico(s)" in msg["mensagem"] and "UserWay" in msg["mensagem"]
    assert progresso["mensagem"] == "Auditando exemplo.com.br — página 1 de 3: /"
    assert auditor.chamadas[0][1].startswith(f"auditorias/{eid}/")


def test_site_bloqueado_nao_grava_auditoria(engine):
    eid = inserir_empresa(engine, estado="AUDITANDO")
    erro = LeituraBloqueada("o robots.txt do site não permite a leitura automática desta página")
    assert asyncio.run(auditar_empresa(_ctx(engine, AuditorFalso(erro=erro)), str(eid))) == "bloqueada"
    assert _tipos(engine, eid)[-1] == "auditoria_bloqueada"
    with engine.connect() as conn:
        assert conn.scalar(select(auditorias.c.id).where(auditorias.c.empresa_id == eid)) is None


def test_nenhuma_pagina_testada_e_tratado_como_bloqueio(engine):
    eid = inserir_empresa(engine, estado="AUDITANDO")
    vazio = ResultadoAuditoria(dominio="exemplo.com.br", paginas=[RESULTADO.paginas[2]])
    assert asyncio.run(auditar_empresa(_ctx(engine, AuditorFalso(vazio)), str(eid))) == "bloqueada"


def test_falha_inesperada_do_navegador_vira_evento(engine):
    eid = inserir_empresa(engine, estado="AUDITANDO")
    assert (
        asyncio.run(auditar_empresa(_ctx(engine, AuditorFalso(erro=RuntimeError("crash"))), str(eid)))
        == "falhou"
    )
    assert _tipos(engine, eid)[-1] == "auditoria_falhou"


def test_so_audita_empresa_em_auditando_e_uma_vez(engine):
    fora = inserir_empresa(engine, nome="a.com.br", dominio="a.com.br", estado="PESQUISANDO")
    assert asyncio.run(auditar_empresa(_ctx(engine, AuditorFalso(RESULTADO)), str(fora))) == "ignorado"

    eid = inserir_empresa(engine, estado="AUDITANDO")
    with engine.begin() as conn:
        conn.execute(
            auditorias.insert().values(
                id=uuid.uuid4(),
                empresa_id=eid,
                totais_json={},
                achados_json=[],
                paginas_json=[],
                artefatos_urls=[],
                criado_em=datetime.now(UTC),
            )
        )
    auditor = AuditorFalso(RESULTADO)
    assert asyncio.run(auditar_empresa(_ctx(engine, auditor), str(eid))) == "ja_auditada"
    assert auditor.chamadas == []


def test_worker_audit_usa_fila_propria_e_no_maximo_2_jobs():
    assert AuditWorkerSettings.queue_name == FILA_AUDITORIA
    assert AuditWorkerSettings.max_jobs == 2
    job = AuditWorkerSettings.functions[0]
    assert job.name == "auditar_empresa"
    assert job.timeout_s >= 360
