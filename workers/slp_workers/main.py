"""Ponto de entrada dos workers (fila Redis via arq).

Fase 0: apenas tarefas de verificação. As tarefas reais (pesquisa, auditoria,
redação, envio, propostas) entram nos subpacotes a partir da Fase 1, sempre
coordenadas pelo orquestrador (CONSTITUICAO §5 e §7).
"""

import logging
from datetime import UTC, datetime

from arq import cron
from arq.connections import RedisSettings

from slp_workers.settings import get_config

log = logging.getLogger("slp_workers")


async def ping(ctx: dict) -> str:
    """Tarefa de teste: enfileire com `await redis.enqueue_job('ping')`."""
    return "pong"


async def heartbeat(ctx: dict) -> None:
    log.info("worker ativo — %s", datetime.now(UTC).isoformat())


async def startup(ctx: dict) -> None:
    log.info("SL Prospecta worker iniciado")


class WorkerSettings:
    functions = [ping]
    cron_jobs = [cron(heartbeat, minute={0, 15, 30, 45})]
    on_startup = startup
    redis_settings = RedisSettings.from_dsn(get_config().redis_url)
    max_jobs = get_config().max_jobs
