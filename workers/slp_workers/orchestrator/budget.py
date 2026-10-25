"""Disjuntor de custo diário no worker (CONSTITUICAO §13 e §20.2).

Antes de cada job de IA, soma `acoes_agentes.custo` (em reais) desde a meia-noite de Brasília.
Ao atingir `DAILY_AI_BUDGET_BRL`, o job não roda: volta para a fila adiado até o orçamento
reabrir (00h05 do dia seguinte) e a pausa é registrada na linha do tempo da empresa.
Mesma regra de `apps/api/app/budget.py`, que alimenta o aviso do painel.
"""

import asyncio
import functools
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from arq import Retry
from sqlalchemy import Engine, func, select

from slp_workers.db import acoes_agentes, registrar_evento
from slp_workers.settings import get_config

log = logging.getLogger("slp_workers.budget")

REABERTURA = timedelta(minutes=5)  # folga após a meia-noite
MAX_TENTATIVAS_JOB_IA = 45  # cada dia pausado consome uma tentativa; ~1 mês de folga


@dataclass(frozen=True)
class DisjuntorCusto:
    custo_hoje_brl: Decimal
    teto_brl: Decimal
    atingido: bool


def _tz() -> ZoneInfo:
    return ZoneInfo(get_config().business_timezone)


def inicio_do_dia(agora: datetime | None = None) -> datetime:
    local = (agora or datetime.now(UTC)).astimezone(_tz())
    return local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)


def segundos_ate_reabrir(agora: datetime | None = None) -> int:
    agora = agora or datetime.now(UTC)
    local = agora.astimezone(_tz())
    amanha = (local + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0) + REABERTURA
    return max(60, int((amanha - local).total_seconds()))


def verificar_disjuntor(engine: Engine, agora: datetime | None = None) -> DisjuntorCusto:
    with engine.connect() as conn:
        total = conn.scalar(
            select(func.coalesce(func.sum(acoes_agentes.c.custo), 0)).where(
                acoes_agentes.c.criado_em >= inicio_do_dia(agora)
            )
        )
    teto = get_config().daily_ai_budget_brl
    custo = Decimal(str(total)).quantize(Decimal("0.01"))
    return DisjuntorCusto(custo_hoje_brl=custo, teto_brl=teto, atingido=custo >= teto)


JobIA = Callable[..., Awaitable[Any]]


def requires_ai_budget(job: JobIA) -> JobIA:
    """Decora jobs que chamam IA. Assinatura esperada: `job(ctx, empresa_id, ...)`."""

    @functools.wraps(job)
    async def wrapper(ctx: dict, empresa_id: str, *args: Any, **kwargs: Any) -> Any:
        engine: Engine = ctx["engine"]
        disjuntor = await asyncio.to_thread(verificar_disjuntor, engine)
        if disjuntor.atingido:
            espera = segundos_ate_reabrir()
            log.warning(
                "disjuntor de custo atingido (R$ %s de R$ %s): %s adiado por %ss",
                disjuntor.custo_hoje_brl,
                disjuntor.teto_brl,
                job.__name__,
                espera,
            )
            await asyncio.to_thread(
                registrar_evento,
                engine,
                uuid.UUID(empresa_id),
                "fila_pausada_custo",
                "Teto diário de IA atingido: o processamento continua quando o orçamento reabrir.",
                custo_hoje_brl=str(disjuntor.custo_hoje_brl),
                teto_brl=str(disjuntor.teto_brl),
                adiado_por_s=espera,
            )
            raise Retry(defer=espera)
        return await job(ctx, empresa_id, *args, **kwargs)

    return wrapper
