from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.queue import fechar_fila
from app.routers import auth, ficha, governanca, health, prospeccao, revisao

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # O pool do arq é criado sob demanda (app.queue) para a API subir mesmo com o Redis fora
    yield
    await fechar_fila(app.state)


app = FastAPI(
    title="SL Prospecta API",
    description="Departamento de SDR autônomo da Sinal Link Acessibilidade.",
    version="0.2.0",
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None,
    lifespan=lifespan,
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
app.include_router(prospeccao.router)
app.include_router(governanca.router)
app.include_router(ficha.router)
app.include_router(revisao.router)


@app.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    return {"servico": "sl-prospecta-api", "fase": "1"}
