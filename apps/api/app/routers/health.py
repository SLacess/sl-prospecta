from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db

router = APIRouter(tags=["saúde"])


@router.get("/health")
def health(db: Session = Depends(get_db)) -> JSONResponse:
    """Usado pelo deploy (rollback automático) e pelo monitoramento."""
    componentes: dict[str, str] = {}

    try:
        db.execute(text("SELECT 1"))
        componentes["database"] = "ok"
    except Exception:  # noqa: BLE001
        componentes["database"] = "erro"

    redis_url = get_settings().redis_url
    if redis_url:
        try:
            import redis

            redis.Redis.from_url(redis_url, socket_connect_timeout=2).ping()
            componentes["redis"] = "ok"
        except Exception:  # noqa: BLE001
            componentes["redis"] = "erro"

    saudavel = all(v == "ok" for v in componentes.values())
    return JSONResponse(
        status_code=200 if saudavel else 503,
        content={"status": "ok" if saudavel else "degradado", "componentes": componentes},
    )
