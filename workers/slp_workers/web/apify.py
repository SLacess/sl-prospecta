"""Cliente do Apify (ADR 0012): só o verificador de e-mail, no caminho alternativo do Mapeador.

Roda o ator `bounceverify/bounceverify-email-verifier` de forma síncrona (`run-sync-get-dataset-items`)
com a lista de candidatos de e-mail. O ator faz a checagem SMTP fora da nossa VPS (provedores bloqueiam a
porta 25, e sondar SMTP do nosso IP prejudicaria a reputação do domínio de envio) e marca catch-all, e-mail de
função, descartável e provedor gratuito. Não usamos atores que leem LinkedIn nem que raspam o Apollo
(CLAUDE.md, regra 7).

Formato da saída conferido numa execução real em 28/10/2026: `email`, `status` (valid | invalid | risky |
unknown), `smtp_valid`, `is_catch_all`, `is_role_based`, `is_disposable`, `is_free_provider`, `reason`.
"""

from dataclasses import dataclass
from decimal import Decimal

import httpx


class ErroApify(Exception):
    def __init__(self, mensagem: str, transitorio: bool = False) -> None:
        super().__init__(mensagem)
        self.transitorio = transitorio


@dataclass
class Verificacao:
    email: str
    status: str
    smtp_valido: bool
    catch_all: bool
    funcao: bool
    descartavel: bool
    provedor_gratuito: bool
    motivo: str | None

    @property
    def entregavel(self) -> bool:
        """Só conta como válido o que o servidor confirmou e não é catch-all, de função ou pessoal (§15.2)."""
        return (
            self.status == "valid"
            and self.smtp_valido
            and not (self.catch_all or self.funcao or self.descartavel or self.provedor_gratuito)
        )


class ClienteApify:
    def __init__(
        self,
        token: str,
        *,
        ator: str = "bounceverify~bounceverify-email-verifier",
        base_url: str = "https://api.apify.com/v2",
        timeout_s: float = 150.0,
        preco_por_email_usd: Decimal = Decimal("0.00089"),
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._token = token.strip()
        self._ator = ator
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s
        self.preco_por_email_usd = preco_por_email_usd
        self._transport = transport

    @property
    def configurado(self) -> bool:
        return bool(self._token)

    def custo_usd(self, quantidade: int) -> Decimal:
        return (self.preco_por_email_usd * quantidade).quantize(Decimal("0.000001"))

    async def verificar(self, emails: list[str]) -> dict[str, Verificacao]:
        if not self.configurado:
            raise ErroApify("APIFY_TOKEN não configurado no worker")
        unicos = list(dict.fromkeys(e.strip().lower() for e in emails if e.strip()))
        if not unicos:
            return {}
        url = f"{self._base_url}/acts/{self._ator}/run-sync-get-dataset-items"
        corpo = {"emails": unicos, "concurrency": 5, "timeoutSecs": 60, "skipInvalidSyntax": True}
        params = {
            "timeout": int(self._timeout_s) - 10,
            "maxTotalChargeUsd": str(self.custo_usd(len(unicos)) * 2),
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout_s, transport=self._transport) as cliente:
                r = await cliente.post(
                    url, params=params, json=corpo, headers={"Authorization": f"Bearer {self._token}"}
                )
        except httpx.HTTPError as exc:
            raise ErroApify(f"Apify indisponível ({type(exc).__name__})", transitorio=True) from exc
        if r.status_code in (401, 403):
            raise ErroApify(f"Apify recusou o token ({r.status_code}); confira o APIFY_TOKEN")
        if r.status_code == 402:
            raise ErroApify("a conta do Apify está sem saldo")
        if r.status_code == 408 or r.status_code == 429 or r.status_code >= 500:
            raise ErroApify(f"Apify indisponível ({r.status_code})", transitorio=True)
        if r.status_code >= 400:
            raise ErroApify(f"Apify recusou a execução ({r.status_code})")
        try:
            itens = r.json()
        except ValueError as exc:
            raise ErroApify("Apify devolveu uma resposta que não é JSON", transitorio=True) from exc
        resultado: dict[str, Verificacao] = {}
        for item in itens if isinstance(itens, list) else []:
            email = str(item.get("email") or "").lower()
            if not email:
                continue
            resultado[email] = Verificacao(
                email=email,
                status=str(item.get("status") or "unknown").lower(),
                smtp_valido=bool(item.get("smtp_valid")),
                catch_all=bool(item.get("is_catch_all")),
                funcao=bool(item.get("is_role_based")),
                descartavel=bool(item.get("is_disposable")),
                provedor_gratuito=bool(item.get("is_free_provider")),
                motivo=item.get("reason"),
            )
        return resultado
