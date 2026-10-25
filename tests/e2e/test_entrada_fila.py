"""Fluxo API → fila → worker (Pesquisador) com Postgres e Redis reais.

A Claude API e o site da empresa são simulados (nenhuma chamada externa no CI); o resto é real:
migrações, fila arq, trava de 1 req/s no Redis, gravação do dossiê e de acoes_agentes.
"""

import asyncio
import os
import time
import uuid
from decimal import Decimal

import httpx
from arq.connections import RedisSettings, create_pool
from arq.worker import Worker

from app.config import get_settings
from app.queue import job_id_processamento
from slp_workers import main as worker_main
from slp_workers.agents.auditor import AchadoIA, AnaliseIA
from slp_workers.agents.researcher import Dossie, Localizacao
from slp_workers.llm import Consumo, RespostaBusca
from slp_workers.settings import get_config


def _dossie(nome: str) -> Dossie:
    return Dossie(
        nome_oficial=nome, setor="saude", subsetor=None, descricao="Hospital.", missao=None,
        produtos_servicos=[], publicos_atendidos=[], localizacao=Localizacao(cidade=None, uf=None, url=None),
        porte_indicios=None, mencoes_inclusao=[], sinais=[], lacunas=["o site não informa a cidade"],
        resumo_5_linhas=[f"Linha {i} sobre {nome}." for i in range(1, 6)],
        raciocinio_resumido="Teste de fluxo.",
    )


class IAFluxo:
    """Claude simulada: um candidato ambíguo na busca e um dossiê fixo."""

    async def estruturado(self, *, modelo, sistema, conteudo, formato, effort, max_tokens):
        if formato is AnaliseIA:
            analise = AnaliseIA(
                top3_para_leigos=[AchadoIA(
                    problema="image-alt", pagina="https://auditada.com.br/", titulo="Imagens sem descrição",
                    impacto_humano="Quem usa leitor de tela não sabe o que as imagens mostram.",
                    quem_e_afetado=["pessoas cegas"], criterio_wcag="1.1.1", trecho_html="<img src=x>",
                )],
                indicios_visuais=[], raciocinio_resumido="Teste de fluxo.",
            )
            return analise, Consumo(modelo=modelo, tokens_in=15000, tokens_out=600, custo_brl=Decimal("0.4000"))
        return _dossie("Hospital do Fluxo"), Consumo(modelo=modelo, tokens_in=9000, tokens_out=700,
                                                    custo_brl=Decimal("0.3000"))

    async def com_busca_web(self, *, modelo, sistema, conteudo, max_buscas, effort, max_tokens):
        texto = ('{"candidatos": [{"dominio": "rede-a.com.br", "nome_oficial": "Rede A", '
                 '"evidencia_url": "https://rede-a.com.br/", "confianca": "media"}], "raciocinio_resumido": "x"}')
        return RespostaBusca(texto=texto, urls_consultadas=["https://rede-a.com.br/"],
                             consumo=Consumo(modelo=modelo, tokens_in=5000, tokens_out=200, buscas_web=1,
                                             custo_brl=Decimal("0.1000")))


def _site(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/robots.txt":
        return httpx.Response(200, text="User-agent: *\nAllow: /\n")
    if request.url.path == "/":
        return httpx.Response(200, headers={"content-type": "text/html"},
                              text='<html lang="pt-BR"><title>Hospital</title><body><p>Somos um hospital.</p>'
                                   '<a href="/quem-somos">Quem somos</a></body></html>')
    if request.url.path == "/quem-somos":
        return httpx.Response(200, headers={"content-type": "text/html"}, text="<p>Fundado em 1950.</p>")
    return httpx.Response(404)


async def _startup_simulado(ctx: dict) -> None:
    await worker_main.startup(ctx)
    ctx["ia"] = IAFluxo()
    ctx["transport"] = httpx.MockTransport(_site)

    async def publico(host):
        return ["93.184.216.34"]

    ctx["resolvedor"] = publico


def _rodar_worker(max_jobs: int = 1) -> None:
    async def _rodar():
        worker = Worker(
            functions=worker_main.WorkerSettings.functions,
            redis_settings=RedisSettings.from_dsn(os.environ["REDIS_URL"]),
            on_startup=_startup_simulado,
            on_shutdown=worker_main.shutdown,
            burst=True,
            max_burst_jobs=max_jobs,
            poll_delay=0.1,
            handle_signals=False,
        )
        try:
            await worker.main()
        finally:
            await worker.close()

    asyncio.run(_rodar())


def _agendado_para_ms(job_id: str, fila: str = "arq:queue") -> float | None:
    async def _ler():
        pool = await create_pool(RedisSettings.from_dsn(os.environ["REDIS_URL"]))
        try:
            return await pool.zscore(fila, job_id)
        finally:
            await pool.aclose()

    return asyncio.run(_ler())


def _detalhe(client, headers, empresa_id):
    return client.get(f"/empresas/{empresa_id}", headers=headers).json()


def _tipos(client, headers, empresa_id):
    return [e["tipo"] for e in _detalhe(client, headers, empresa_id)["eventos"]]


def test_site_informado_vira_dossie(client, headers):
    dominio = f"fluxo-{uuid.uuid4().hex[:8]}.com.br"

    r = client.post("/prospeccao", json={"alvo": f"https://{dominio}/contato"}, headers=headers)
    assert r.status_code == 201, r.text
    empresa_id = r.json()["empresa"]["id"]
    custo_antes = Decimal(client.get("/governanca/disjuntores", headers=headers).json()["custo"]["custo_hoje_brl"])

    _rodar_worker()

    detalhe = _detalhe(client, headers, empresa_id)
    tipos = [e["tipo"] for e in detalhe["eventos"]]
    assert tipos[:3] == ["entrada_recebida", "enfileirado", "pesquisa_iniciada"]
    assert tipos[-2:] == ["dossie_pronto", "auditoria_enfileirada"]
    assert detalhe["estado"] == "AUDITANDO"
    assert detalhe["nome"] == "Hospital do Fluxo"
    assert detalhe["dossie"]["setor"] == "saude"
    assert len(detalhe["dossie"]["resumo"]) == 5

    # O custo da ação de IA entrou no disjuntor do dia
    custo_depois = Decimal(client.get("/governanca/disjuntores", headers=headers).json()["custo"]["custo_hoje_brl"])
    assert custo_depois - custo_antes == Decimal("0.30")

    # A auditoria entrou na fila do worker-audit (fila própria no Redis)
    assert _agendado_para_ms(f"auditar_empresa:{empresa_id}", "arq:queue:auditoria") is not None

    # Mesma empresa por outra forma do endereço: deduplica sem refazer a pesquisa
    r2 = client.post("/prospeccao", json={"alvo": f"WWW.{dominio.upper()}"}, headers=headers)
    assert r2.status_code == 200
    assert r2.json()["duplicada"] is True
    # Ainda sem auditoria, a reentrada volta ao orquestrador, que não duplica a auditoria já na fila
    _rodar_worker()
    assert _tipos(client, headers, empresa_id).count("auditoria_enfileirada") == 1


def test_nome_ambiguo_espera_o_vendedor_confirmar_o_site(client, headers):
    nome = f"Rede Fluxo {uuid.uuid4().hex[:6]}"
    r = client.post("/prospeccao", json={"alvo": nome}, headers=headers)
    empresa_id = r.json()["empresa"]["id"]

    _rodar_worker()
    detalhe = _detalhe(client, headers, empresa_id)
    assert detalhe["confirmacao_dominio"]["candidatos"][0]["dominio"] == "rede-a.com.br"
    assert detalhe["dossie"] is None

    dominio = f"rede-{uuid.uuid4().hex[:6]}.com.br"
    c = client.post(f"/empresas/{empresa_id}/dominio", json={"dominio": dominio}, headers=headers)
    assert c.status_code == 200, c.text

    _rodar_worker()
    detalhe = _detalhe(client, headers, empresa_id)
    assert detalhe["dominio"] == dominio
    assert detalhe["confirmacao_dominio"] is None
    assert detalhe["dossie"] is not None
    assert "dominio_confirmado" in [e["tipo"] for e in detalhe["eventos"]]


def test_auditoria_pronta_vira_analise_e_qualificando(client, headers):
    from app.db import SessionLocal
    from app.models import Auditoria, Empresa, EstadoProspect

    dominio = f"auditada-{uuid.uuid4().hex[:6]}.com.br"
    paginas = [{
        "url": "https://auditada.com.br/", "status": "ok", "prints": {"desktop": None},
        "axe": {"violacoes": [{"regra": "image-alt", "gravidade": "critico", "ocorrencias": 3, "descricao": "alt",
                               "criterios_wcag": ["wcag111"], "exemplos": [{"alvo": "img", "html": "<img src=x>"}]}]},
        "teclado": {"armadilha_de_foco": None, "link_pular_conteudo": True, "sem_indicador_aparente": 0},
        "responsivo_320": {"rolagem_horizontal": False},
    }]
    with SessionLocal() as db:
        empresa = Empresa(nome="Auditada", dominio=dominio, fonte="manual", estado=EstadoProspect.auditando)
        db.add(empresa)
        db.flush()
        db.add(Auditoria(empresa_id=empresa.id, totais_json={"critico": 1, "grave": 0, "moderado": 0, "leve": 0,
                                                             "paginas_auditadas": 1},
                         achados_json=[], paginas_json=paginas, artefatos_urls=[]))
        db.commit()
        empresa_id = str(empresa.id)

    # Reenviar pelo painel recoloca a empresa na fila; o worker principal faz a análise com IA
    r = client.post("/prospeccao", json={"alvo": dominio}, headers=headers)
    assert r.json()["na_fila"] is True
    _rodar_worker()

    detalhe = _detalhe(client, headers, empresa_id)
    assert detalhe["estado"] == "QUALIFICANDO"
    assert detalhe["auditoria"]["nota"] == 88  # 100 - 12 (imagem sem texto alternativo)
    assert detalhe["auditoria"]["analise"]["top3_para_leigos"][0]["titulo"] == "Imagens sem descrição"
    assert detalhe["auditoria"]["analise"]["exige_ajuste_no_codigo"] == ["imagens sem texto alternativo"]
    assert detalhe["eventos"][-1]["tipo"] == "analise_pronta"


def test_disjuntor_de_custo_pausa_o_job_no_worker(client, headers, monkeypatch):
    monkeypatch.setattr(get_settings(), "daily_ai_budget_brl", Decimal("0"))
    monkeypatch.setattr(get_config(), "daily_ai_budget_brl", Decimal("0"))

    assert client.get("/governanca/disjuntores", headers=headers).json()["custo"]["atingido"] is True

    r = client.post("/prospeccao", json={"alvo": f"pausa-{uuid.uuid4().hex[:8]}.com.br"}, headers=headers)
    assert r.status_code == 201
    assert r.json()["fila_pausada"] is True
    empresa_id = r.json()["empresa"]["id"]

    _rodar_worker()

    tipos = _tipos(client, headers, empresa_id)
    assert "fila_pausada_custo" in tipos
    assert "pesquisa_iniciada" not in tipos
    # O job continua na fila, adiado para quando o orçamento reabrir
    agendado = _agendado_para_ms(job_id_processamento(uuid.UUID(empresa_id)))
    assert agendado is not None and agendado > time.time() * 1000 + 60_000
