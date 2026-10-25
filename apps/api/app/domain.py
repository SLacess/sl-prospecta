"""Interpretação da entrada "Nome da empresa ou site" (CONSTITUICAO §7.2, entrada 1).

A deduplicação depende de todas as formas de um mesmo site virarem o mesmo domínio:
`https://www.Hospital.com.br/contato`, `hospital.com.br` e `HOSPITAL.COM.BR:443` → `hospital.com.br`.
"""

import ipaddress
import re
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit

_LABEL = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)$")
_TLD = re.compile(r"^(?:[a-z]{2,63}|xn--[a-z0-9-]{1,59})$")
# Sem esquema (`://`), texto sem espaços com ponto no host parece endereço de site
_PARECE_SITE = re.compile(r"^[^\s/?#]+\.[^\s/?#.]{2,}\.?(?:[/?#:].*)?$")

NOME_MIN, NOME_MAX = 2, 255


class EntradaInvalida(ValueError):
    """Mensagem em português, pronta para mostrar ao usuário."""


@dataclass(frozen=True)
class Alvo:
    tipo: Literal["url", "nome"]
    nome: str
    dominio: str | None


def normalizar_dominio(texto: str) -> str:
    bruto = texto.strip()
    if "://" not in bruto:
        bruto = f"http://{bruto}"
    try:
        host = urlsplit(bruto).hostname or ""
    except ValueError:
        raise EntradaInvalida("Endereço de site inválido.") from None

    host = host.strip(".").lower()
    if host.startswith("www."):
        host = host[4:]

    try:
        ipaddress.ip_address(host)
        eh_ip = True
    except ValueError:
        eh_ip = False
    if eh_ip:
        raise EntradaInvalida("Informe o domínio do site, não um endereço IP.")

    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError:
        raise EntradaInvalida("Endereço de site inválido.") from None

    rotulos = host.split(".")
    if len(rotulos) < 2 or len(host) > 253 or not all(_LABEL.match(r) for r in rotulos):
        raise EntradaInvalida("Endereço de site inválido.")
    if not _TLD.match(rotulos[-1]):
        raise EntradaInvalida("Endereço de site inválido.")
    return host


def normalizar_nome(texto: str) -> str:
    nome = " ".join(texto.split())
    if len(nome) < NOME_MIN:
        raise EntradaInvalida("Digite o nome da empresa ou o endereço do site.")
    if len(nome) > NOME_MAX:
        raise EntradaInvalida(f"O nome pode ter no máximo {NOME_MAX} caracteres.")
    if not any(c.isalnum() for c in nome):
        raise EntradaInvalida("O nome da empresa precisa ter letras ou números.")
    return nome


def interpretar_entrada(texto: str) -> Alvo:
    """Decide se o texto é um site ou um nome. Nome fica sem domínio: quem resolve é o Pesquisador."""
    limpo = texto.strip()
    if not limpo:
        raise EntradaInvalida("Digite o nome da empresa ou o endereço do site.")

    if "://" in limpo or _PARECE_SITE.match(limpo):
        dominio = normalizar_dominio(limpo)
        # Nome provisório; o Pesquisador grava o nome oficial no dossiê (Tarefa 2)
        return Alvo(tipo="url", nome=dominio, dominio=dominio)

    return Alvo(tipo="nome", nome=normalizar_nome(limpo), dominio=None)
