"""Orquestrador do pipeline do prospect (CONSTITUICAO §5 e §7).

Tarefa 1 da Fase 1: o job recebe a empresa recém-cadastrada, passa pelo disjuntor de custo
e registra na linha do tempo que ela está pronta para o Pesquisador. A empresa continua em
NOVO; a transição para PESQUISANDO entra junto com o Pesquisador (Tarefa 2).
"""

import asyncio
import logging
import uuid

from sqlalchemy import Engine, select

from slp_workers.db import empresas, registrar_evento
from slp_workers.orchestrator.budget import requires_ai_budget

log = logging.getLogger("slp_workers.pipeline")

NOVO = "NOVO"

# Transições automáticas permitidas (CONSTITUICAO §7.1). Mudanças manuais pelo Kanban
# são do humano e ficam fora desta tabela. Não adicione estados sem emendar a Constituição.
TRANSICOES: dict[str, frozenset[str]] = {
    "NOVO": frozenset({"PESQUISANDO"}),
    "PESQUISANDO": frozenset({"AUDITANDO"}),
    "AUDITANDO": frozenset({"QUALIFICANDO"}),
    "QUALIFICANDO": frozenset({"MAPEANDO_DECISORES", "ARQUIVADO"}),
    "MAPEANDO_DECISORES": frozenset({"PREPARANDO_ABORDAGEM"}),
    "PREPARANDO_ABORDAGEM": frozenset({"EM_SEQUENCIA"}),
    "EM_SEQUENCIA": frozenset({"RESPONDEU", "SEM_RESPOSTA"}),
    "RESPONDEU": frozenset({"REUNIAO_AGENDADA", "NAO_INTERESSADO"}),
    "REUNIAO_AGENDADA": frozenset({"PROPOSTA_ENVIADA"}),
    "PROPOSTA_ENVIADA": frozenset({"NEGOCIACAO"}),
    "NEGOCIACAO": frozenset({"GANHO", "PERDIDO"}),
}


def pode_transitar(origem: str, destino: str) -> bool:
    return destino in TRANSICOES.get(origem, frozenset())


def _carregar_estado(engine: Engine, empresa_id: uuid.UUID) -> str | None:
    with engine.connect() as conn:
        return conn.scalar(select(empresas.c.estado).where(empresas.c.id == empresa_id))


def _iniciar(engine: Engine, empresa_id: uuid.UUID) -> str:
    estado = _carregar_estado(engine, empresa_id)
    if estado is None:
        log.warning("empresa %s não encontrada; job descartado", empresa_id)
        return "empresa_inexistente"
    if estado != NOVO:
        log.info("empresa %s já está em %s; nada a fazer", empresa_id, estado)
        return "ignorado"

    registrar_evento(engine, empresa_id, "processamento_iniciado", "Processamento iniciado.")
    registrar_evento(
        engine, empresa_id, "aguardando_pesquisador",
        "Pronta para a pesquisa. A pesquisa automática ainda não está ativa nesta versão.",
    )
    return "aguardando_pesquisador"


@requires_ai_budget
async def processar_empresa(ctx: dict, empresa_id: str) -> str:
    return await asyncio.to_thread(_iniciar, ctx["engine"], uuid.UUID(empresa_id))
