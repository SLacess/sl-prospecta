"""Ponto de entrada dos workers (fila Redis via arq).

Todo job do pipeline passa pelo orquestrador (CONSTITUICAO §5 e §7). Fase 1, Tarefa 1:
`processar_empresa`, enfileirado pela API quando uma empresa entra em NOVO.
"""

import logging
from datetime import UTC, datetime

from arq import cron, func
from arq.connections import RedisSettings

from slp_workers.db import make_engine
from slp_workers.orchestrator.budget import MAX_TENTATIVAS_JOB_IA
from slp_workers.orchestrator.pipeline import processar_empresa
from slp_workers.settings import get_config

log = logging.getLogger("slp_workers")


async def ping(ctx: dict) -> str:
    """Tarefa de teste: enfileire com `await redis.enqueue_job('ping')`."""
    return "pong"


async def heartbeat(ctx: dict) -> None:
    log.info("worker ativo — %s", datetime.now(UTC).isoformat())


async def startup(ctx: dict) -> None:
    ctx["engine"] = make_engine(get_config().database_url)
    log.info("SL Prospecta worker iniciado")


async def shutdown(ctx: dict) -> None:
    engine = ctx.get("engine")
    if engine is not None:
        engine.dispose()


class WorkerSettings:
    functions = [ping, func(processar_empresa, max_tries=MAX_TENTATIVAS_JOB_IA)]
    cron_jobs = [cron(heartbeat, minute={0, 15, 30, 45})]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_config().redis_url)
    max_jobs = get_config().max_jobs
