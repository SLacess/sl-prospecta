"""Cliente OAuth do Google para conectar caixas de envio (Mensageiro — CONSTITUICAO §9, §15.2; ADR 0016).

httpx puro, sem biblioteca pesada do Google — mesmo espírito do cliente do Apollo no worker
(`workers/slp_workers/web/apollo.py`): uma classe fina, transporte injetável para os testes, exceção de
domínio própria em vez de deixar escapar `httpx.HTTPError`.
"""

from urllib.parse import urlencode

import httpx

from app.config import get_settings

URL_AUTORIZACAO = "https://accounts.google.com/o/oauth2/v2/auth"
URL_TOKEN = "https://oauth2.googleapis.com/token"  # noqa: S105 (endpoint público, não é segredo)
URL_PERFIL_GMAIL = "https://gmail.googleapis.com/gmail/v1/users/me/profile"
URL_REVOGACAO = "https://oauth2.googleapis.com/revoke"  # noqa: S105
ESCOPOS = "https://www.googleapis.com/auth/gmail.send https://www.googleapis.com/auth/gmail.readonly"


class ErroGoogleOAuth(Exception):
    """Falha ao falar com o Google — nunca inclui o client_secret/token na mensagem."""


class ClienteGoogleOAuth:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        *,
        transport: httpx.BaseTransport | None = None,
        timeout_s: float = 10.0,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri
        self._transport = transport
        self._timeout_s = timeout_s

    @property
    def configurado(self) -> bool:
        return bool(self._client_id and self._client_secret and self._redirect_uri)

    def url_autorizacao(self, state: str) -> str:
        parametros = {
            "client_id": self._client_id,
            "redirect_uri": self._redirect_uri,
            "response_type": "code",
            "scope": ESCOPOS,
            "access_type": "offline",
            "prompt": "consent",  # garante um refresh_token novo mesmo numa reconexão
            "state": state,
        }
        return f"{URL_AUTORIZACAO}?{urlencode(parametros)}"

    def trocar_codigo(self, code: str) -> dict:
        """Troca o `code` do callback por tokens. Levanta se o Google não devolver refresh_token."""
        with httpx.Client(transport=self._transport, timeout=self._timeout_s) as cliente:
            r = cliente.post(
                URL_TOKEN,
                data={
                    "code": code,
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "redirect_uri": self._redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
        if r.status_code != 200:
            raise ErroGoogleOAuth(f"O Google recusou o código de autorização (status {r.status_code}).")
        dados = r.json()
        if "refresh_token" not in dados or "access_token" not in dados:
            raise ErroGoogleOAuth(
                "O Google não devolveu um refresh_token. Desconecte a caixa no "
                "myaccount.google.com/permissions e conecte de novo."
            )
        return dados

    def email_conectado(self, access_token: str) -> str:
        with httpx.Client(transport=self._transport, timeout=self._timeout_s) as cliente:
            r = cliente.get(URL_PERFIL_GMAIL, headers={"Authorization": f"Bearer {access_token}"})
        if r.status_code != 200:
            raise ErroGoogleOAuth(f"Não foi possível obter o e-mail conectado (status {r.status_code}).")
        return r.json()["emailAddress"]

    def revogar(self, refresh_token: str) -> bool:
        """Melhor esforço: a remoção da caixa não falha se o Google recusar a revogação."""
        try:
            with httpx.Client(transport=self._transport, timeout=self._timeout_s) as cliente:
                r = cliente.post(URL_REVOGACAO, data={"token": refresh_token})
            return r.status_code == 200
        except httpx.HTTPError:
            return False


def get_google_oauth_client() -> ClienteGoogleOAuth:
    s = get_settings()
    return ClienteGoogleOAuth(
        s.google_oauth_client_id, s.google_oauth_client_secret, s.google_oauth_redirect_uri
    )
