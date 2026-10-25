"""Fila de processamento (arq/Redis). Os jobs rodam em `workers/` (CONSTITUICAO §5)."""

import uuid

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings
from fastapi import Request

from app.config import get_settings

JOB_PROCESSAR_EMPRESA = "processar_empresa"


class FilaIndisponivel(RuntimeError):
    pass


def job_id_processamento(empresa_id: uuid.UUID) -> str:
    """ID fixo por empresa: o arq ignora um segundo envio enquanto o primeiro existir."""
    return f"{JOB_PROCESSAR_EMPRESA}:{empresa_id}"


class Fila:
    def __init__(self, request: Request) -> None:
        self._state = request.app.state

    async def _pool(self) -> ArqRedis:
        pool = getattr(self._state, "arq_pool", None)
        if pool is None:
            redis_url = get_settings().redis_url
            if not redis_url:
                raise FilaIndisponivel("REDIS_URL não configurada.")
            try:
                settings = RedisSettings.from_dsn(redis_url)
                settings.conn_retries = 1
                pool = await create_pool(settings)
            except Exception as exc:  # noqa: BLE001
                raise FilaIndisponivel(str(exc)) from exc
            self._state.arq_pool = pool
        return pool

    async def enfileirar_processamento(self, empresa_id: uuid.UUID) -> bool:
        """Devolve False se já havia um job para esta empresa (nada é duplicado)."""
        pool = await self._pool()
        try:
            job = await pool.enqueue_job(
                JOB_PROCESSAR_EMPRESA, str(empresa_id), _job_id=job_id_processamento(empresa_id)
            )
        except Exception as exc:  # noqa: BLE001
            raise FilaIndisponivel(str(exc)) from exc
        return job is not None


def get_fila(request: Request) -> Fila:
    return Fila(request)


async def fechar_fila(state: object) -> None:
    pool = getattr(state, "arq_pool", None)
    if pool is not None:
        await pool.aclose()
        state.arq_pool = None
