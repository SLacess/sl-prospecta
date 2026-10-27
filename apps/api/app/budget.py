"""Disjuntor de custo diário de IA/dados (CONSTITUICAO §13 e §20.2).

O "dia" é o dia comercial em Brasília (00h00–23h59), não o dia UTC. `acoes_agentes.custo`
está em reais. O worker aplica a mesma regra antes de cada job de IA
(`workers/slp_workers/orchestrator/budget.py`); esta versão serve o painel e a API.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AcaoAgente


@dataclass(frozen=True)
class DisjuntorCusto:
    custo_hoje_brl: Decimal
    teto_brl: Decimal
    atingido: bool


def inicio_do_dia(agora: datetime | None = None) -> datetime:
    """Meia-noite de hoje no fuso do negócio, em UTC."""
    tz = ZoneInfo(get_settings().business_timezone)
    local = (agora or datetime.now(UTC)).astimezone(tz)
    return local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)


def custo_do_dia(db: Session, agora: datetime | None = None) -> Decimal:
    soma = func.coalesce(func.sum(AcaoAgente.custo), 0)
    total = db.scalar(select(soma).where(AcaoAgente.criado_em >= inicio_do_dia(agora)))
    return Decimal(str(total)).quantize(Decimal("0.01"))


@dataclass(frozen=True)
class DisjuntorCreditos:
    creditos_hoje: int
    teto: int
    atingido: bool


def verificar_creditos_apollo(db: Session, agora: datetime | None = None) -> DisjuntorCreditos:
    """Créditos do Apollo usados hoje (`acoes_agentes.creditos`); no teto, o worker para o Mapeador."""
    soma = func.coalesce(func.sum(AcaoAgente.creditos), 0)
    total = db.scalar(select(soma).where(AcaoAgente.criado_em >= inicio_do_dia(agora)))
    teto = get_settings().apollo_daily_credit_cap
    usados = int(total or 0)
    return DisjuntorCreditos(creditos_hoje=usados, teto=teto, atingido=usados >= teto)


def verificar_disjuntor(db: Session, agora: datetime | None = None) -> DisjuntorCusto:
    teto = get_settings().daily_ai_budget_brl
    custo = custo_do_dia(db, agora)
    return DisjuntorCusto(custo_hoje_brl=custo, teto_brl=teto, atingido=custo >= teto)
