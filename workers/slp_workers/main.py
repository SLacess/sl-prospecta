"""Ponto de entrada dos workers (fila Redis via arq).

Todo job do pipeline passa pelo orquestrador (CONSTITUICAO §5 e §7). Fase 1:
`processar_empresa`, enfileirado pela API quando uma empresa entra (ou tem o site confirmado) e pelo
worker-audit quando a auditoria técnica termina: roda o Pesquisador e o Auditor com IA.
Fase 2: o mesmo job qualifica e mapeia decisores; `mapear_colunas_lote` identifica as colunas de uma planilha.
Fase 3: o disjuntor de bounce (ADR 0016, Tarefa 4) roda sozinho num cron — ao contrário do Mensageiro, que
dispara só manualmente (`slp_workers.cli enviar`), o disjuntor só lê e, na pior hipótese, pausa o envio.
"""

import asyncio
import logging
from datetime import UTC, datetime

from arq import cron, func
from arq.connections import RedisSettings

from slp_workers.audit.artefatos import ArmazenamentoMinio
from slp_workers.db import make_engine
from slp_workers.llm import ClienteAnthropic
from slp_workers.orchestrator.bounce import DependenciasBounce, DisjuntorBounce
from slp_workers.orchestrator.budget import MAX_TENTATIVAS_JOB_IA
from slp_workers.orchestrator.lotes import mapear_colunas_lote
from slp_workers.orchestrator.pipeline import processar_empresa
from slp_workers.outreach.gmail import ClienteGmail
from slp_workers.settings import get_config
from slp_workers.web.ratelimit import LimitadorRedis

log = logging.getLogger("slp_workers")


async def ping(ctx: dict) -> str:
    """Tarefa de teste: enfileire com `await redis.enqueue_job('ping')`."""
    return "pong"


async def heartbeat(ctx: dict) -> None:
    log.info("worker ativo — %s", datetime.now(UTC).isoformat())


async def verificar_bounce_job(ctx: dict) -> None:
    """Disjuntor de bounce (CONSTITUICAO §13; ADR 0016, Tarefa 4) — só lê e, na pior hipótese, pausa o
    envio; nunca manda e-mail, por isso é seguro automatizar (ao contrário do Mensageiro)."""
    config = ctx["config"]
    gmail = ClienteGmail(config.google_oauth_client_id, config.google_oauth_client_secret)
    deps = DependenciasBounce(engine=ctx["engine"], gmail=gmail)
    resultado = await asyncio.to_thread(DisjuntorBounce(deps).executar)
    if resultado.pausou:
        log.warning(
            "disjuntor de bounce pausou a operação: %s/%s devoluções em 24h",
            resultado.total_bounces, resultado.total_envios,
        )


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
    functions = [
        ping,
        func(processar_empresa, max_tries=MAX_TENTATIVAS_JOB_IA, keep_result=0),
        func(mapear_colunas_lote, max_tries=1, keep_result=0),
    ]
    cron_jobs = [
        cron(heartbeat, minute={0, 15, 30, 45}),
        cron(verificar_bounce_job, minute={5, 20, 35, 50}),
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_config().redis_url)
    max_jobs = get_config().max_jobs
