"""Bloqueio de endereços internos (SSRF).

O domínio vem de um texto digitado no painel ou de uma busca na web. Sem esta verificação,
um domínio público que aponte para 127.0.0.1 ou para a rede privada da VPS faria o worker ler
serviços internos (Postgres, Redis, MinIO). Toda URL, inclusive as de redirecionamento, passa aqui.
"""

import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable

Resolvedor = Callable[[str], Awaitable[list[str]]]


class HostBloqueado(Exception):
    pass


async def resolver_dns(host: str) -> list[str]:
    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    return sorted({info[4][0] for info in infos})


async def exigir_host_publico(host: str, resolvedor: Resolvedor = resolver_dns) -> None:
    try:
        ips = await resolvedor(host)
    except OSError as exc:
        raise HostBloqueado(f"não foi possível resolver {host}") from exc
    if not ips:
        raise HostBloqueado(f"{host} não tem endereço")
    for ip in ips:
        if not ipaddress.ip_address(ip.split("%")[0]).is_global:
            raise HostBloqueado(f"{host} aponta para endereço não público ({ip})")
