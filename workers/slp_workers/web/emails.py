"""Validação de e-mail dos decisores (CONSTITUICAO §7.3, Etapa 4, e §15.2).

Válido = formato correto, e-mail corporativo (§15.1), domínio com registro MX e marcado como `verified` pelo
Apollo. Corporativo é o domínio do site ou, quando o Apollo confirma que a pessoa é da empresa, outro domínio
da própria organização (ex.: site `hospitalsiriolibanes.org.br`, e-mail `@hsl.org.br`). Webmail nunca conta.
Qualquer outro status do Apollo (não verificado, extrapolado, catch-all) fica "não verificado" e não conta
como contato válido: nada é enviado a ele sem verificação.
"""

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

import dns.asyncresolver
import dns.exception
import dns.resolver

from slp_workers.web.dominio import pertence_ao_dominio

StatusEmail = Literal["valido", "nao_verificado", "sem_email"]
ResolvedorMX = Callable[[str], Awaitable[bool]]

FORMATO = re.compile(r"^[a-z0-9._%+'-]+@([a-z0-9-]+\.)+[a-z]{2,}$")
# Provedores de e-mail pessoal: nunca são o e-mail profissional da pessoa
WEBMAIL = frozenset(
    "gmail.com googlemail.com hotmail.com outlook.com live.com msn.com yahoo.com yahoo.com.br icloud.com "
    "me.com bol.com.br uol.com.br terra.com.br ig.com.br globo.com globomail.com r7.com protonmail.com "
    "proton.me zoho.com aol.com gmx.com yandex.com".split()
)


async def tem_mx(dominio: str) -> bool:
    try:
        respostas = await dns.asyncresolver.resolve(dominio, "MX", lifetime=5.0)
    except (dns.exception.DNSException, dns.resolver.NoAnswer):
        return False
    return len(respostas) > 0


@dataclass
class EmailValidado:
    email: str | None
    status: StatusEmail
    motivo: str


async def validar_email(
    email: str | None,
    dominio_empresa: str,
    status_apollo: str | None,
    resolvedor_mx: ResolvedorMX = tem_mx,
    *,
    organizacao_confirmada: bool = False,
) -> EmailValidado:
    """`organizacao_confirmada`: o Apollo garante que a pessoa trabalha na empresa (veio da busca pelo domínio
    ou o registro dela aponta para o site da empresa); aí outro domínio corporativo também vale."""
    if not email:
        return EmailValidado(None, "sem_email", "o Apollo não tem e-mail profissional desta pessoa")
    email = email.strip().lower()
    if not FORMATO.match(email):
        return EmailValidado(None, "sem_email", "e-mail em formato inválido descartado")
    dominio = email.rsplit("@", 1)[1]
    if dominio in WEBMAIL:
        return EmailValidado(None, "sem_email", f"e-mail pessoal ({dominio}) descartado")
    if not pertence_ao_dominio(dominio, dominio_empresa) and not organizacao_confirmada:
        # E-mail fora do domínio da empresa pode ser pessoal: não guardamos (coleta mínima, §15.1)
        return EmailValidado(None, "sem_email", f"e-mail de outro domínio ({dominio}) descartado")
    if not await resolvedor_mx(dominio):
        return EmailValidado(email, "nao_verificado", f"o domínio {dominio} não recebe e-mails (sem MX)")
    if (status_apollo or "").lower() != "verified":
        return EmailValidado(
            email, "nao_verificado", f"o Apollo não verificou o e-mail ({status_apollo or 'sem status'})"
        )
    return EmailValidado(email, "valido", "e-mail verificado")
