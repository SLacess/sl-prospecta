"""1 requisição por segundo por domínio (CONSTITUICAO §8.4), valendo para todos os workers."""

import asyncio
import time
from typing import Protocol

INTERVALO_S = 1.0


class Limitador(Protocol):
    async def aguardar(self, dominio: str) -> None: ...


class LimitadorRedis:
    """Uma chave por domínio com expiração de 1 s: quem consegue criar a chave pode requisitar."""

    def __init__(self, redis, intervalo_s: float = INTERVALO_S) -> None:
        self._redis = redis
        self._intervalo_ms = int(intervalo_s * 1000)

    async def aguardar(self, dominio: str) -> None:
        chave = f"slp:ratelimit:{dominio}"
        while not await self._redis.set(chave, "1", nx=True, px=self._intervalo_ms):
            ttl = await self._redis.pttl(chave)
            await asyncio.sleep(max(ttl, 50) / 1000)


class LimitadorMemoria:
    """Para testes e execução sem Redis: vale só dentro do processo."""

    def __init__(self, intervalo_s: float = INTERVALO_S) -> None:
        self._intervalo_s = intervalo_s
        self._ultimo: dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def aguardar(self, dominio: str) -> None:
        async with self._lock:
            espera = self._ultimo.get(dominio, 0) + self._intervalo_s - time.monotonic()
            if espera > 0:
                await asyncio.sleep(espera)
            self._ultimo[dominio] = time.monotonic()
