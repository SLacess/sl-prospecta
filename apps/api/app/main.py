from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import auth, health

settings = get_settings()

app = FastAPI(
    title="SL Prospecta API",
    description="Departamento de SDR autônomo da Sinal Link Acessibilidade.",
    version="0.1.0",
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router)


@app.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    return {"servico": "sl-prospecta-api", "fase": "0"}
