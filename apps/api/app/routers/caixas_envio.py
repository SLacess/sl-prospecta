"""Caixas de envio conectadas (CONSTITUICAO §9, §15.2; ADR 0016 — retomada da Fase 3, Tarefa 4).

Só a conexão/cadastro das caixas por OAuth do Gmail. Nenhuma rota aqui envia e-mail — quem envia é o
worker (Mensageiro, Tarefa 3), lendo estas caixas direto do banco. `refresh_token_criptografado` nunca
aparece em nenhuma resposta.

O `GET /caixas-envio/conectar` exige login (admin) e devolve a URL de autorização do Google; o painel faz
o redirect no browser. O `GET /caixas-envio/callback` é a navegação de volta vinda do próprio Google — por
isso não exige o Bearer token da sessão (o browser não o envia numa navegação comum): a segurança do
callback vem só do `state` assinado gerado em `/conectar`.
"""

import logging
import uuid
from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from jwt import PyJWTError
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.crypto import ErroCriptografia, criptografar, descriptografar
from app.db import get_db
from app.deps import require_role
from app.google_oauth import ClienteGoogleOAuth, ErroGoogleOAuth, get_google_oauth_client
from app.models import CaixaEnvio, Papel, Usuario
from app.security import criar_state_oauth, validar_state_oauth

router = APIRouter(prefix="/caixas-envio", tags=["caixas de envio"])

log = logging.getLogger("app.caixas_envio")


class CaixaEnvioOut(BaseModel):
    id: uuid.UUID
    email: str
    nome_remetente: str
    ativa: bool
    limite_diario: int
    conectada_em: datetime
    erro_verificacao: str | None


class ConectarOut(BaseModel):
    url_autorizacao: str


class EditarLimiteIn(BaseModel):
    limite_diario: int = Field(gt=0)


def _montar(caixa: CaixaEnvio) -> CaixaEnvioOut:
    return CaixaEnvioOut(
        id=caixa.id,
        email=caixa.email,
        nome_remetente=caixa.nome_remetente,
        ativa=caixa.ativa,
        limite_diario=caixa.limite_diario,
        conectada_em=caixa.conectada_em,
        erro_verificacao=caixa.erro_verificacao,
    )


def _buscar(db: Session, caixa_id: uuid.UUID) -> CaixaEnvio:
    caixa = db.get(CaixaEnvio, caixa_id)
    if caixa is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Caixa de envio não encontrada.")
    return caixa


def _mensagem_url(mensagem: str) -> str:
    return quote(mensagem)


@router.get("", response_model=list[CaixaEnvioOut])
def listar(
    db: Session = Depends(get_db), _: Usuario = Depends(require_role(Papel.admin))
) -> list[CaixaEnvioOut]:
    caixas = db.scalars(select(CaixaEnvio).order_by(CaixaEnvio.conectada_em)).all()
    return [_montar(c) for c in caixas]


@router.get("/conectar", response_model=ConectarOut)
def conectar(
    user: Usuario = Depends(require_role(Papel.admin)),
    google: ClienteGoogleOAuth = Depends(get_google_oauth_client),
) -> ConectarOut:
    if not google.configurado:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "OAuth do Google ainda não configurado (GOOGLE_OAUTH_CLIENT_ID/SECRET/"
                "GOOGLE_OAUTH_REDIRECT_URI). Veja infra/EMAIL-WARMUP.md."
            ),
        )
    state = criar_state_oauth(str(user.id))
    return ConectarOut(url_autorizacao=google.url_autorizacao(state))


@router.get("/callback")
def callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    db: Session = Depends(get_db),
    google: ClienteGoogleOAuth = Depends(get_google_oauth_client),
) -> RedirectResponse:
    destino = f"{get_settings().app_base_url}/caixas-envio"
    if error:
        erro_url = _mensagem_url("Conexão cancelada ou recusada no Google.")
        return RedirectResponse(f"{destino}?erro={erro_url}")
    if not code or not state:
        erro_url = _mensagem_url("Faltou código ou state na resposta do Google.")
        return RedirectResponse(f"{destino}?erro={erro_url}")
    try:
        admin_id = validar_state_oauth(state)
    except (PyJWTError, KeyError, ValueError):
        erro_url = _mensagem_url("Link de conexão expirado ou inválido.")
        return RedirectResponse(f"{destino}?erro={erro_url}")

    try:
        tokens = google.trocar_codigo(code)
        email = google.email_conectado(tokens["access_token"])
        refresh_criptografado = criptografar(tokens["refresh_token"])
    except (ErroGoogleOAuth, ErroCriptografia) as e:
        log.warning("falha ao conectar caixa de envio: %s", e)
        return RedirectResponse(f"{destino}?erro=" + _mensagem_url(str(e)))

    caixa_existente = db.scalar(select(CaixaEnvio).where(CaixaEnvio.email == email))
    if caixa_existente is not None:
        caixa_existente.refresh_token_criptografado = refresh_criptografado
        caixa_existente.escopos = tokens.get("scope", "")
        caixa_existente.erro_verificacao = None
        caixa_existente.conectada_por = uuid.UUID(admin_id)
    else:
        db.add(
            CaixaEnvio(
                email=email,
                nome_remetente=email.split("@")[0],
                refresh_token_criptografado=refresh_criptografado,
                escopos=tokens.get("scope", ""),
                ativa=True,
                limite_diario=get_settings().daily_send_limit_per_mailbox,
                conectada_por=uuid.UUID(admin_id),
            )
        )
    db.commit()
    return RedirectResponse(f"{destino}?conectado=1")


@router.post("/{caixa_id}/ativar", response_model=CaixaEnvioOut)
def ativar(
    caixa_id: uuid.UUID, db: Session = Depends(get_db), _: Usuario = Depends(require_role(Papel.admin))
) -> CaixaEnvioOut:
    caixa = _buscar(db, caixa_id)
    caixa.ativa = True
    db.commit()
    db.refresh(caixa)
    return _montar(caixa)


@router.post("/{caixa_id}/desativar", response_model=CaixaEnvioOut)
def desativar(
    caixa_id: uuid.UUID, db: Session = Depends(get_db), _: Usuario = Depends(require_role(Papel.admin))
) -> CaixaEnvioOut:
    caixa = _buscar(db, caixa_id)
    caixa.ativa = False
    db.commit()
    db.refresh(caixa)
    return _montar(caixa)


@router.post("/{caixa_id}/limite", response_model=CaixaEnvioOut)
def editar_limite(
    caixa_id: uuid.UUID,
    dados: EditarLimiteIn,
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_role(Papel.admin)),
) -> CaixaEnvioOut:
    """Sobe (ou desce) o limite diário de uma caixa já conectada — a rampa do aquecimento manual
    (infra/EMAIL-WARMUP.md §5), já que `DAILY_SEND_LIMIT_PER_MAILBOX` só vale no momento da conexão."""
    caixa = _buscar(db, caixa_id)
    caixa.limite_diario = dados.limite_diario
    db.commit()
    db.refresh(caixa)
    return _montar(caixa)


@router.delete("/{caixa_id}", status_code=status.HTTP_204_NO_CONTENT)
def remover(
    caixa_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_role(Papel.admin)),
    google: ClienteGoogleOAuth = Depends(get_google_oauth_client),
) -> None:
    caixa = _buscar(db, caixa_id)
    try:
        token = descriptografar(caixa.refresh_token_criptografado)
        google.revogar(token)
    except ErroCriptografia:
        pass  # mesmo sem conseguir revogar no Google, removemos o cadastro local
    db.delete(caixa)
    db.commit()
