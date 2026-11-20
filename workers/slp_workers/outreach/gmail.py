"""Cliente Gmail para o Mensageiro enviar e-mails e para o disjuntor de bounce ler devoluções
(CONSTITUICAO §9, §13, §15.2; ADR 0016, Tarefas 3 e 4).

httpx puro, no mesmo espírito do `app/google_oauth.py` da API e do `web/apollo.py` do worker: client fino,
transporte injetável para os testes, exceção de domínio própria em vez de deixar escapar `httpx.HTTPError`.

O access_token da conexão original (Tarefa 1) expira em ~1h e não é guardado; a cada rodada o Mensageiro
(ou o disjuntor de bounce) renova um novo a partir do refresh_token (que não expira, a menos que a caixa
seja desconectada no myaccount.google.com — é esse o erro que `renovar_access_token` sinaliza).
"""

import base64
from datetime import datetime
from email.message import EmailMessage

import httpx

URL_TOKEN = "https://oauth2.googleapis.com/token"  # noqa: S105 (endpoint público, não é segredo)
URL_MENSAGENS = "https://gmail.googleapis.com/gmail/v1/users/me/messages"
URL_ENVIO = f"{URL_MENSAGENS}/send"


class ErroGmail(Exception):
    """Falha ao falar com o Gmail — nunca inclui o refresh_token/access_token na mensagem."""


class ClienteGmail:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        *,
        transport: httpx.BaseTransport | None = None,
        timeout_s: float = 15.0,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._transport = transport
        self._timeout_s = timeout_s

    def renovar_access_token(self, refresh_token: str) -> str:
        with httpx.Client(transport=self._transport, timeout=self._timeout_s) as cliente:
            r = cliente.post(
                URL_TOKEN,
                data={
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
            )
        if r.status_code != 200:
            raise ErroGmail(f"o Google recusou a renovação do token (status {r.status_code})")
        access_token = r.json().get("access_token")
        if not access_token:
            raise ErroGmail("o Google não devolveu access_token na renovação")
        return access_token

    def enviar(
        self,
        access_token: str,
        *,
        remetente_nome: str,
        remetente_email: str,
        destinatario: str,
        assunto: str,
        corpo: str,
    ) -> str:
        """Devolve o id da mensagem no Gmail (para o log em `envios`)."""
        mensagem = EmailMessage()
        mensagem["From"] = f"{remetente_nome} <{remetente_email}>"
        mensagem["To"] = destinatario
        mensagem["Subject"] = assunto
        mensagem.set_content(corpo)
        bruto = base64.urlsafe_b64encode(mensagem.as_bytes()).decode()
        with httpx.Client(transport=self._transport, timeout=self._timeout_s) as cliente:
            r = cliente.post(
                URL_ENVIO,
                headers={"Authorization": f"Bearer {access_token}"},
                json={"raw": bruto},
            )
        if r.status_code != 200:
            raise ErroGmail(f"o Gmail recusou o envio (status {r.status_code})")
        return r.json()["id"]

    def listar_bounces(self, access_token: str, *, desde: datetime) -> list[str]:
        """Devolve o `snippet` (prévia em texto puro, já decodificada pelo Gmail) de cada notificação de
        devolução recebida desde `desde`. Sem Postmaster Tools (lacuna aceita na ADR 0016), isso é uma
        aproximação — o snippet costuma trazer o endereço que rejeitou, mas não é garantido.
        """
        query = f"from:mailer-daemon after:{int(desde.timestamp())}"
        with httpx.Client(transport=self._transport, timeout=self._timeout_s) as cliente:
            r = cliente.get(
                URL_MENSAGENS,
                headers={"Authorization": f"Bearer {access_token}"},
                params={"q": query, "maxResults": 50},
            )
            if r.status_code != 200:
                raise ErroGmail(f"o Gmail recusou a busca de devoluções (status {r.status_code})")
            snippets = []
            for item in r.json().get("messages", []):
                r2 = cliente.get(
                    f"{URL_MENSAGENS}/{item['id']}",
                    headers={"Authorization": f"Bearer {access_token}"},
                    params={"format": "metadata"},
                )
                if r2.status_code == 200:
                    snippets.append(r2.json().get("snippet", ""))
        return snippets
