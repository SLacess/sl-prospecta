"""Ponto de entrada do worker-audit (CONSTITUICAO §16.2): fila própria, no máximo 2 auditorias ao mesmo tempo.

Uso: arq slp_workers.main_audit.AuditWorkerSettings
"""

import logging

from arq import func
from arq.connections import RedisSettings

from slp_workers.audit.artefatos import ArmazenamentoMinio
from slp_workers.db import make_engine
from slp_workers.filas import FILA_AUDITORIA
from slp_workers.orchestrator.auditoria import auditar_empresa
from slp_workers.settings import get_config
from slp_workers.web.ratelimit import LimitadorRedis

log = logging.getLogger("slp_workers.audit")


async def startup(ctx: dict) -> None:
    config = get_config()
    ctx["config"] = config
    ctx["engine"] = make_engine(config.database_url)
    ctx["limitador"] = LimitadorRedis(ctx["redis"])  # mesma trava de 1 req/s do Pesquisador
    ctx["armazenamento"] = ArmazenamentoMinio(
        config.minio_endpoint, config.minio_root_user, config.minio_root_password, config.minio_bucket
    )
    log.info("SL Prospecta worker-audit iniciado")


async def shutdown(ctx: dict) -> None:
    engine = ctx.get("engine")
    if engine is not None:
        engine.dispose()


class AuditWorkerSettings:
    queue_name = FILA_AUDITORIA
    # keep_result=0: terminada (ou falha), a empresa pode voltar à fila ao ser reenviada pelo painel
    functions = [
        func(auditar_empresa, keep_result=0, max_tries=1, timeout=get_config().audit_total_timeout_s + 60)
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_config().redis_url)
    max_jobs = get_config().audit_max_jobs
