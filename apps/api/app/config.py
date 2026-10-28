from decimal import Decimal
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", protected_namespaces=("settings_",))

    environment: str = "development"
    database_url: str = "postgresql+psycopg://slprospecta:slprospecta@localhost:5432/slprospecta"
    redis_url: str = ""
    jwt_secret: str = "dev-secret-change-me"
    jwt_expires_minutes: int = 720
    cors_origins: str = "http://localhost:3000"

    # Modelos de IA — nunca fixos no código de negócio (CONSTITUICAO §6)
    model_triage: str = "claude-haiku-5-5"
    model_analysis: str = "claude-sonnet-5-5"
    model_strategy: str = "claude-opus-5-5"

    # Disjuntor de custo (CONSTITUICAO §13): teto diário de IA/dados em reais
    daily_ai_budget_brl: Decimal = Decimal("30")
    apollo_daily_credit_cap: int = 60  # mesma variável do worker (disjuntor de créditos do Apollo)
    apify_daily_budget_usd: Decimal = Decimal("2")  # mesma variável do worker (ADR 0012)
    usd_brl_rate: Decimal = Decimal("5.50")  # mesma cotação do worker (custos guardados em reais)
    business_timezone: str = "America/Sao_Paulo"

    # Arquivos dos workers (prints e mini-relatórios) no MinIO — mesmo bucket privado
    minio_endpoint: str = "http://minio:9000"
    minio_root_user: str = ""
    minio_root_password: str = ""
    minio_bucket: str = "artefatos"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
