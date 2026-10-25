import asyncio
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from arq import Retry
from sqlalchemy import select

from slp_workers.db import acoes_agentes, empresas, eventos
from slp_workers.main import WorkerSettings
from slp_workers.orchestrator.budget import segundos_ate_reabrir, verificar_disjuntor
from slp_workers.orchestrator.pipeline import TRANSICOES, pode_transitar, processar_empresa
from slp_workers.settings import get_config


def _rodar(engine, empresa_id):
    return asyncio.run(processar_empresa({"engine": engine}, str(empresa_id)))


def _eventos(engine, empresa_id):
    with engine.connect() as conn:
        return conn.execute(
            select(eventos.c.tipo, eventos.c.origem, eventos.c.dados_json)
            .where(eventos.c.empresa_id == empresa_id)
            .order_by(eventos.c.ocorrido_em)
        ).all()


def _gastar(engine, custo):
    with engine.begin() as conn:
        conn.execute(acoes_agentes.insert().values(id=uuid.uuid4(), custo=Decimal(custo),
                                                   criado_em=datetime.now(UTC)))


def test_job_registra_eventos_e_mantem_novo(engine, empresa_id):
    assert _rodar(engine, empresa_id) == "aguardando_pesquisador"

    tipos = [e.tipo for e in _eventos(engine, empresa_id)]
    assert tipos == ["processamento_iniciado", "aguardando_pesquisador"]
    assert all(e.origem == "sistema" and e.dados_json["mensagem"] for e in _eventos(engine, empresa_id))
    with engine.connect() as conn:
        assert conn.scalar(select(empresas.c.estado).where(empresas.c.id == empresa_id)) == "NOVO"


def test_empresa_fora_de_novo_e_ignorada(engine, empresa_id):
    with engine.begin() as conn:
        conn.execute(empresas.update().where(empresas.c.id == empresa_id).values(estado="AUDITANDO"))
    assert _rodar(engine, empresa_id) == "ignorado"
    assert _eventos(engine, empresa_id) == []


def test_empresa_inexistente_nao_quebra(engine):
    assert _rodar(engine, uuid.uuid4()) == "empresa_inexistente"


def test_disjuntor_atingido_adia_o_job_e_avisa(engine, empresa_id):
    _gastar(engine, "30.00")

    with pytest.raises(Retry) as exc:
        _rodar(engine, empresa_id)

    assert exc.value.defer_score > 0
    eventos_ = _eventos(engine, empresa_id)
    assert [e.tipo for e in eventos_] == ["fila_pausada_custo"]
    assert eventos_[0].dados_json["teto_brl"] == "30"


def test_abaixo_do_teto_roda(engine, empresa_id):
    _gastar(engine, "29.99")
    assert verificar_disjuntor(engine).atingido is False
    assert _rodar(engine, empresa_id) == "aguardando_pesquisador"


def test_teto_zero_pausa_tudo(engine, empresa_id, monkeypatch):
    monkeypatch.setattr(get_config(), "daily_ai_budget_brl", Decimal("0"))
    with pytest.raises(Retry):
        _rodar(engine, empresa_id)


def test_reabre_as_00h05_de_brasilia():
    # 23h00 de 24/10 em Brasília = 02h00 UTC de 25/10 → reabre 00h05 de 25/10 (65 min)
    assert segundos_ate_reabrir(datetime(2026, 10, 25, 2, 0, tzinfo=UTC)) == 65 * 60


def test_job_registrado_com_tentativas_suficientes_para_pausas():
    jobs = {getattr(f, "name", getattr(f, "__name__", "")): f for f in WorkerSettings.functions}
    assert jobs["processar_empresa"].max_tries >= 30


def test_transicoes_seguem_a_constituicao():
    estados = {
        "NOVO", "PESQUISANDO", "AUDITANDO", "QUALIFICANDO", "ARQUIVADO", "MAPEANDO_DECISORES",
        "PREPARANDO_ABORDAGEM", "EM_SEQUENCIA", "SEM_RESPOSTA", "RESPONDEU", "NAO_INTERESSADO",
        "REUNIAO_AGENDADA", "PROPOSTA_ENVIADA", "NEGOCIACAO", "GANHO", "PERDIDO",
    }
    usados = set(TRANSICOES) | {d for ds in TRANSICOES.values() for d in ds}
    assert usados == estados
    assert pode_transitar("NOVO", "PESQUISANDO")
    assert not pode_transitar("NOVO", "AUDITANDO")
    assert not pode_transitar("GANHO", "NOVO")
