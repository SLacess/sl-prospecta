from decimal import Decimal
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkerConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", protected_namespaces=("settings_",))

    redis_url: str = "redis://localhost:6379/0"
    database_url: str = ""
    max_jobs: int = 4  # auditorias com navegador consomem memória — ajuste à VPS

    # Disjuntor de custo (CONSTITUICAO §13) — mesma variável lida pela API
    daily_ai_budget_brl: Decimal = Decimal("30")
    business_timezone: str = "America/Sao_Paulo"


@lru_cache
def get_config() -> WorkerConfig:
    return WorkerConfig()
