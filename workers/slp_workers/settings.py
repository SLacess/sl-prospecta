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

    # IA — modelos nunca fixos no código de negócio (CONSTITUICAO §6). A chave vem de ANTHROPIC_API_KEY.
    model_analysis: str = "claude-sonnet-5-5"
    ai_refusal_fallback: bool = True
    usd_brl_rate: Decimal = Decimal("5.50")
    # Preço por milhão de tokens em US$ (entrada, saída). Sobrescreva com AI_PRICES_USD_PER_MTOK em JSON.
    ai_prices_usd_per_mtok: dict[str, tuple[Decimal, Decimal]] = {
        "claude-sonnet-5-5": (Decimal("2.00"), Decimal("10.00")),
        "claude-haiku-5-5": (Decimal("0.10"), Decimal("0.50")),
        "claude-opus-5-5": (Decimal("4.00"), Decimal("20.00")),
    }
    web_search_usd_per_request: Decimal = Decimal("0.01")

    # Pesquisador (CONSTITUICAO §7.3 e §8.4)
    research_max_pages: int = 6  # home + até 5 páginas institucionais
    research_page_timeout_s: float = 15.0
    research_max_bytes: int = 2_000_000
    research_chars_per_page: int = 12_000
    research_max_web_searches: int = 3
    research_cost_cap_brl: Decimal = Decimal("2.00")  # teto por empresa pesquisada
    crawler_user_agent: str = "SinalLinkA11yAudit/1.0 (+https://sinallink.com.br/auditoria)"
    # Só para testes locais: permite ler sites em 127.0.0.1/rede privada
    web_allow_private_hosts: bool = False

    # Auditor técnico (CONSTITUICAO §8.1 e §8.4) — roda no serviço worker-audit
    audit_max_jobs: int = 2  # Chromium consome memória: no máximo 2 auditorias ao mesmo tempo
    audit_max_pages: int = 5  # home + até 4 páginas-chave
    audit_page_timeout_s: float = 45.0
    audit_total_timeout_s: float = 360.0
    audit_tab_presses: int = 40
    audit_axe_path: str = "/app/vendor/axe.min.js"

    # Prints das páginas (MinIO, compatível com S3)
    minio_endpoint: str = "http://minio:9000"
    minio_root_user: str = ""
    minio_root_password: str = ""
    minio_bucket: str = "artefatos"


@lru_cache
def get_config() -> WorkerConfig:
    return WorkerConfig()
