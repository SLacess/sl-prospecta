"""Normalização de domínio — mesma regra de `apps/api/app/domain.py` (deduplicação por domínio).

Duplicada aqui porque API e worker são imagens separadas; os testes dos dois lados cobrem os mesmos casos.
"""

import ipaddress
import re
from urllib.parse import urlsplit

_LABEL = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)$")
_TLD = re.compile(r"^(?:[a-z]{2,63}|xn--[a-z0-9-]{1,59})$")


def normalizar_dominio(texto: str) -> str | None:
    """Devolve o domínio normalizado ou None se o texto não for um domínio válido."""
    bruto = texto.strip()
    if "://" not in bruto:
        bruto = f"http://{bruto}"
    try:
        host = (urlsplit(bruto).hostname or "").strip(".").lower()
    except ValueError:
        return None
    if host.startswith("www."):
        host = host[4:]
    try:
        ipaddress.ip_address(host)
        return None
    except ValueError:
        pass
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError:
        return None
    rotulos = host.split(".")
    if len(rotulos) < 2 or len(host) > 253 or not all(_LABEL.match(r) for r in rotulos):
        return None
    if not _TLD.match(rotulos[-1]):
        return None
    return host


def pertence_ao_dominio(host: str | None, dominio: str) -> bool:
    """`www.x.com.br` e `portal.x.com.br` pertencem a `x.com.br`; `x.com.br.golpe.io` não."""
    if not host:
        return False
    host = host.strip(".").lower()
    return host == dominio or host.endswith(f".{dominio}")
