"""Ponto de entrada dos workers (fila Redis via arq).

Todo job do pipeline passa pelo orquestrador (CONSTITUICAO §5 e §7). Fase 1:
`processar_empresa`, enfileirado pela API quando uma empresa entra (ou tem o site confirmado) e pelo
worker-audit quando a auditoria técnica termina: roda o Pesquisador e o Auditor com IA.
"""

import logging
from datetime import UTC, datetime

from arq import cron, func
from arq.connections import RedisSettings

from slp_workers.audit.artefatos import ArmazenamentoMinio
from slp_workers.db import make_engine
from slp_workers.llm import ClienteAnthropic
from slp_workers.orchestrator.budget import MAX_TENTATIVAS_JOB_IA
from slp_workers.orchestrator.pipeline import processar_empresa
from slp_workers.settings import get_config
from slp_workers.web.ratelimit import LimitadorRedis

log = logging.getLogger("slp_workers")


async def ping(ctx: dict) -> str:
    """Tarefa de teste: enfileire com `await redis.enqueue_job('ping')`."""
    return "pong"


async def heartbeat(ctx: dict) -> None:
    log.info("worker ativo — %s", datetime.now(UTC).isoformat())


async def startup(ctx: dict) -> None:
    config = get_config()
    ctx["config"] = config
    ctx["engine"] = make_engine(config.database_url)
    ctx["ia"] = ClienteAnthropic(config)
    ctx["limitador"] = LimitadorRedis(ctx["redis"])  # 1 req/s por domínio entre todos os workers
    # O Auditor com IA lê os prints salvos pelo worker-audit
    ctx["armazenamento"] = ArmazenamentoMinio(
        config.minio_endpoint, config.minio_root_user, config.minio_root_password, config.minio_bucket
    )
    log.info("SL Prospecta worker iniciado")


async def shutdown(ctx: dict) -> None:
    engine = ctx.get("engine")
    if engine is not None:
        engine.dispose()


class WorkerSettings:
    # keep_result=0: o job_id fixo evita duplicata só enquanto o job existe; terminado, a empresa pode voltar
    functions = [ping, func(processar_empresa, max_tries=MAX_TENTATIVAS_JOB_IA, keep_result=0)]
    cron_jobs = [cron(heartbeat, minute={0, 15, 30, 45})]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_config().redis_url)
    max_jobs = get_config().max_jobs
