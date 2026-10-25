import asyncio
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from arq import Retry
from sqlalchemy import func, select

from slp_workers.db import acoes_agentes, auditorias, dossies, empresas, eventos
from slp_workers.llm import Consumo, ErroIA
from slp_workers.main import WorkerSettings
from slp_workers.orchestrator.budget import segundos_ate_reabrir, verificar_disjuntor
from slp_workers.orchestrator.pipeline import TRANSICOES, pode_transitar, processar_empresa
from slp_workers.settings import get_config
from tests.conftest import DOMINIO, SITE_PADRAO, IAFalsa, inserir_empresa, montar_ctx

BUSCA_UM_SITE = (
    '```json\n{"candidatos": [{"dominio": "exemplo.com.br", "nome_oficial": "Hospital Exemplo", '
    '"evidencia_url": "https://exemplo.com.br/", "confianca": "alta"}], "raciocinio_resumido": "ok"}\n```'
)
BUSCA_DOIS_SITES = (
    '{"candidatos": ['
    '{"dominio": "unimed-a.com.br", "nome_oficial": "Unimed A", "evidencia_url": "https://unimed-a.com.br/", '
    '"confianca": "media"}, {"dominio": "unimed-b.com.br", "nome_oficial": "Unimed B", '
    '"evidencia_url": "https://unimed-b.com.br/", "confianca": "media"}], "raciocinio_resumido": "duas"}'
)


def _rodar(ctx, empresa_id):
    return asyncio.run(processar_empresa(ctx, str(empresa_id)))


def _eventos(engine, empresa_id):
    with engine.connect() as conn:
        return conn.execute(
            select(eventos.c.tipo, eventos.c.origem, eventos.c.dados_json)
            .where(eventos.c.empresa_id == empresa_id)
            .order_by(eventos.c.ocorrido_em)
        ).all()


def _tipos(engine, empresa_id):
    return [e.tipo for e in _eventos(engine, empresa_id)]


def _empresa(engine, empresa_id):
    with engine.connect() as conn:
        return conn.execute(select(empresas).where(empresas.c.id == empresa_id)).first()


def _contar(engine, tabela, empresa_id):
    with engine.connect() as conn:
        return conn.scalar(select(func.count()).select_from(tabela).where(tabela.c.empresa_id == empresa_id))


def _gastar(engine, custo):
    with engine.begin() as conn:
        conn.execute(
            acoes_agentes.insert().values(id=uuid.uuid4(), custo=Decimal(custo), criado_em=datetime.now(UTC))
        )


# --- Caminho principal -------------------------------------------------------


def test_site_informado_vira_dossie_e_segue_para_auditoria(engine, empresa_id):
    ia = IAFalsa()
    ctx = montar_ctx(engine, ia)
    assert _rodar(ctx, empresa_id) == "auditoria_enfileirada"

    tipos = _tipos(engine, empresa_id)
    assert tipos[0] == "pesquisa_iniciada"
    assert tipos[-2:] == ["dossie_pronto", "auditoria_enfileirada"]
    assert ctx["enfileirar_auditoria"].enviados == [empresa_id]
    assert "pagina_ignorada" in tipos  # /trabalhe-conosco respondeu 404
    assert all(e.origem == "sistema" and e.dados_json["mensagem"] for e in _eventos(engine, empresa_id))
    assert ia.chamadas == ["estruturado"]  # domínio já conhecido: nenhuma busca na web
    assert '<pagina url="https://exemplo.com.br/quem-somos">' in ia.conteudos[0]

    empresa = _empresa(engine, empresa_id)
    assert empresa.estado == "AUDITANDO"
    assert (empresa.nome, empresa.setor, empresa.cidade, empresa.uf) == (
        "Hospital Exemplo S.A.",
        "saude",
        "Sorocaba",
        "SP",
    )
    with engine.connect() as conn:
        d = conn.execute(select(dossies).where(dossies.c.empresa_id == empresa_id)).one()
        acao = conn.execute(select(acoes_agentes).where(acoes_agentes.c.empresa_id == empresa_id)).one()
    assert d.versao == 1
    assert d.resumo.splitlines() == ["Linha 1", "Linha 2", "Linha 3", "Linha 4", "Linha 5"]
    assert d.dados_json["dominio"] == DOMINIO
    assert len(d.dados_json["paginas_lidas"]) == 3
    assert d.dados_json["tecnologias_site"] == ["WordPress"]
    assert d.sinais_json["mencoes_inclusao"][0]["tema"] == "pcd"
    assert acao.agente == "pesquisador"
    assert acao.custo == Decimal("0.2100")
    assert acao.tokens_in == 12000
    assert acao.raciocinio


def test_rodar_de_novo_nao_repete_a_pesquisa(engine, empresa_id):
    ia = IAFalsa()
    ctx = montar_ctx(engine, ia)
    _rodar(ctx, empresa_id)
    assert _rodar(ctx, empresa_id) == "auditoria_enfileirada"
    assert ia.chamadas == ["estruturado"]
    assert ctx["enfileirar_auditoria"].enviados == [empresa_id]  # a fila não duplica
    assert _tipos(engine, empresa_id).count("auditoria_enfileirada") == 1


def test_empresa_com_dossie_de_antes_do_auditor_segue_para_auditoria(engine):
    """Empresas que ficaram em PESQUISANDO com dossiê (Tarefa 2) entram na auditoria ao serem retomadas."""
    eid = inserir_empresa(engine, estado="PESQUISANDO")
    with engine.begin() as conn:
        conn.execute(
            dossies.insert().values(
                id=uuid.uuid4(),
                empresa_id=eid,
                dados_json={},
                resumo="x",
                sinais_json={},
                versao=1,
                criado_em=datetime.now(UTC),
            )
        )
    ia = IAFalsa()
    ctx = montar_ctx(engine, ia)
    assert _rodar(ctx, eid) == "auditoria_enfileirada"
    assert _empresa(engine, eid).estado == "AUDITANDO"
    assert ia.chamadas == []


def test_empresa_ja_auditada_e_analisada_nao_volta_para_a_fila(engine):
    eid = inserir_empresa(engine, estado="AUDITANDO")
    with engine.begin() as conn:
        conn.execute(
            auditorias.insert().values(
                id=uuid.uuid4(),
                empresa_id=eid,
                nota=70,
                totais_json={},
                achados_json=[],
                paginas_json=[],
                artefatos_urls=[],
                criado_em=datetime.now(UTC),
            )
        )
    ctx = montar_ctx(engine, IAFalsa())
    assert _rodar(ctx, eid) == "ja_analisada"
    assert ctx["enfileirar_auditoria"].enviados == []


def test_empresa_fora_do_fluxo_da_pesquisa_e_ignorada(engine):
    eid = inserir_empresa(engine, estado="QUALIFICANDO")
    assert _rodar(montar_ctx(engine, IAFalsa()), eid) == "ignorado"
    assert _tipos(engine, eid) == []


def test_empresa_inexistente_nao_quebra(engine):
    assert _rodar(montar_ctx(engine, IAFalsa()), uuid.uuid4()) == "empresa_inexistente"


# --- Resolução de domínio ----------------------------------------------------


def test_nome_com_um_site_claro_resolve_e_pesquisa(engine):
    eid = inserir_empresa(engine, nome="Hospital Exemplo", dominio=None)
    ia = IAFalsa(busca_texto=BUSCA_UM_SITE, urls=["https://www.exemplo.com.br/", "https://g1.globo.com/x"])
    assert _rodar(montar_ctx(engine, ia), eid) == "auditoria_enfileirada"
    assert ia.chamadas == ["busca", "estruturado"]
    assert _empresa(engine, eid).dominio == DOMINIO
    assert "dominio_identificado" in _tipos(engine, eid)
    assert _contar(engine, acoes_agentes, eid) == 2  # resolução de domínio + dossiê


def test_nome_ambiguo_pede_confirmacao_e_espera(engine):
    eid = inserir_empresa(engine, nome="Unimed", dominio=None)
    ia = IAFalsa(busca_texto=BUSCA_DOIS_SITES, urls=["https://unimed-a.com.br/", "https://unimed-b.com.br/"])
    assert _rodar(montar_ctx(engine, ia), eid) == "aguardando_confirmacao"

    ultimo = _eventos(engine, eid)[-1]
    assert ultimo.tipo == "confirmacao_dominio"
    assert [c["dominio"] for c in ultimo.dados_json["candidatos"]] == ["unimed-a.com.br", "unimed-b.com.br"]
    assert _contar(engine, dossies, eid) == 0

    # Enquanto o vendedor não confirma, rodar de novo não gasta outra busca
    assert _rodar(montar_ctx(engine, ia), eid) == "aguardando_confirmacao"
    assert ia.chamadas == ["busca"]


def test_dominio_inventado_pela_ia_nao_e_aceito(engine):
    eid = inserir_empresa(engine, nome="Hospital Exemplo", dominio=None)
    ia = IAFalsa(busca_texto=BUSCA_UM_SITE, urls=["https://g1.globo.com/noticia"])
    assert _rodar(montar_ctx(engine, ia), eid) == "aguardando_confirmacao"
    assert _eventos(engine, eid)[-1].dados_json["candidatos"] == []
    assert _empresa(engine, eid).dominio is None


def test_dominio_de_outra_empresa_nao_duplica(engine):
    inserir_empresa(engine, nome="Hospital Exemplo (já cadastrado)", dominio=DOMINIO, estado="PESQUISANDO")
    eid = inserir_empresa(engine, nome="Hospital Exemplo", dominio=None)
    ia = IAFalsa(busca_texto=BUSCA_UM_SITE, urls=["https://exemplo.com.br/"])
    assert _rodar(montar_ctx(engine, ia), eid) == "aguardando_confirmacao"
    assert _tipos(engine, eid)[-1] == "dominio_ja_cadastrado"
    assert _empresa(engine, eid).dominio is None
    assert ia.chamadas == ["busca"]


# --- Falhas ------------------------------------------------------------------


def test_site_que_proibe_robos_nao_gera_dossie(engine, empresa_id):
    site = dict(SITE_PADRAO)
    site[f"https://{DOMINIO}/robots.txt"] = (
        200,
        {"content-type": "text/plain"},
        "User-agent: *\nDisallow: /\n",
    )
    ia = IAFalsa()
    assert _rodar(montar_ctx(engine, ia, site), empresa_id) == "site_indisponivel"
    assert _tipos(engine, empresa_id)[-1] == "site_indisponivel"
    assert "robots.txt" in _eventos(engine, empresa_id)[-1].dados_json["mensagem"]
    assert ia.chamadas == []  # sem páginas, sem gasto de IA


def test_falha_da_ia_registra_gasto_e_avisa(engine, empresa_id):
    erro = ErroIA(
        "o modelo recusou a tarefa",
        Consumo(modelo="claude-sonnet-5-5", tokens_in=5000, custo_brl=Decimal("0.0500")),
    )
    assert _rodar(montar_ctx(engine, IAFalsa(erro=erro)), empresa_id) == "falhou"
    assert _tipos(engine, empresa_id)[-1] == "pesquisa_falhou"
    with engine.connect() as conn:
        acao = conn.execute(select(acoes_agentes).where(acoes_agentes.c.empresa_id == empresa_id)).one()
    assert acao.custo == Decimal("0.0500")
    assert acao.saida_json == {"erro": "o modelo recusou a tarefa"}


def test_falha_transitoria_tenta_de_novo(engine, empresa_id):
    ctx = montar_ctx(engine, IAFalsa(erro=ErroIA("Claude API indisponível", transitorio=True)))
    ctx["job_try"] = 1
    with pytest.raises(Retry):
        _rodar(ctx, empresa_id)


# --- Disjuntor de custo ------------------------------------------------------


def test_disjuntor_atingido_adia_o_job_e_avisa(engine, empresa_id):
    _gastar(engine, "30.00")
    ia = IAFalsa()
    with pytest.raises(Retry) as exc:
        _rodar(montar_ctx(engine, ia), empresa_id)
    assert exc.value.defer_score > 0
    assert _tipos(engine, empresa_id) == ["fila_pausada_custo"]
    assert ia.chamadas == []


def test_abaixo_do_teto_roda(engine, empresa_id):
    _gastar(engine, "29.99")
    assert verificar_disjuntor(engine).atingido is False
    assert _rodar(montar_ctx(engine, IAFalsa()), empresa_id) == "auditoria_enfileirada"


def test_teto_zero_pausa_tudo(engine, empresa_id, monkeypatch):
    monkeypatch.setattr(get_config(), "daily_ai_budget_brl", Decimal("0"))
    with pytest.raises(Retry):
        _rodar(montar_ctx(engine, IAFalsa()), empresa_id)


def test_reabre_as_00h05_de_brasilia():
    # 23h00 de 24/10 em Brasília = 02h00 UTC de 25/10 → reabre 00h05 de 25/10 (65 min)
    assert segundos_ate_reabrir(datetime(2026, 10, 25, 2, 0, tzinfo=UTC)) == 65 * 60


def test_job_registrado_com_tentativas_e_sem_guardar_resultado():
    jobs = {getattr(f, "name", getattr(f, "__name__", "")): f for f in WorkerSettings.functions}
    assert jobs["processar_empresa"].max_tries >= 30
    assert jobs["processar_empresa"].keep_result_s == 0


def test_transicoes_seguem_a_constituicao():
    estados = {
        "NOVO",
        "PESQUISANDO",
        "AUDITANDO",
        "QUALIFICANDO",
        "ARQUIVADO",
        "MAPEANDO_DECISORES",
        "PREPARANDO_ABORDAGEM",
        "EM_SEQUENCIA",
        "SEM_RESPOSTA",
        "RESPONDEU",
        "NAO_INTERESSADO",
        "REUNIAO_AGENDADA",
        "PROPOSTA_ENVIADA",
        "NEGOCIACAO",
        "GANHO",
        "PERDIDO",
    }
    usados = set(TRANSICOES) | {d for ds in TRANSICOES.values() for d in ds}
    assert usados == estados
    assert pode_transitar("NOVO", "PESQUISANDO")
    assert not pode_transitar("NOVO", "AUDITANDO")
    assert not pode_transitar("GANHO", "NOVO")
