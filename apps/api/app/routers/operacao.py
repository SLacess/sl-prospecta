"""Disjuntores de envio e botão "Pausar tudo" (CONSTITUICAO §13; ADR 0016, Tarefa 4).

Pausar bloqueia só o Mensageiro (worker) — a Caixa de Aprovação continua funcionando normalmente (editar,
aprovar, rejeitar, marcar como enviada manualmente). Pausar e reportar spam são freios de emergência:
qualquer pessoa logada (admin ou vendedor) pode acionar, sem esperar um admin estar disponível. Retomar
exige admin — é uma decisão deliberada, depois de investigar o motivo da pausa.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user, require_role
from app.models import Papel, Usuario
from app.operacao import EstadoOperacao, ler_estado, pausar, retomar

router = APIRouter(prefix="/operacao", tags=["operação"])


class EstadoOperacaoOut(BaseModel):
    pausado: bool
    motivo: str | None
    pausado_em: datetime | None
    pausado_por_nome: str | None
    origem: str | None


class PausarIn(BaseModel):
    motivo: str = Field(min_length=1, max_length=2000)


def _montar(db: Session, estado: EstadoOperacao) -> EstadoOperacaoOut:
    nome = None
    if estado.pausado_por is not None:
        usuario = db.get(Usuario, estado.pausado_por)
        nome = usuario.nome if usuario else None
    return EstadoOperacaoOut(
        pausado=estado.pausado,
        motivo=estado.motivo,
        pausado_em=estado.pausado_em,
        pausado_por_nome=nome,
        origem=estado.origem,
    )


@router.get("", response_model=EstadoOperacaoOut)
def estado(db: Session = Depends(get_db), _: Usuario = Depends(get_current_user)) -> EstadoOperacaoOut:
    return _montar(db, ler_estado(db))


@router.post("/pausar", response_model=EstadoOperacaoOut)
def pausar_rota(
    dados: PausarIn,
    db: Session = Depends(get_db),
    user: Usuario = Depends(require_role(Papel.admin, Papel.vendedor)),
) -> EstadoOperacaoOut:
    motivo = dados.motivo.strip()
    if not motivo:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Explique o motivo da pausa."
        )
    estado = pausar(db, motivo=motivo, user_id=user.id, origem="manual")
    return _montar(db, estado)


@router.post("/reportar-spam", response_model=EstadoOperacaoOut)
def reportar_spam(
    db: Session = Depends(get_db),
    user: Usuario = Depends(require_role(Papel.admin, Papel.vendedor)),
) -> EstadoOperacaoOut:
    estado = pausar(
        db,
        motivo="Reclamação de spam reportada manualmente — revise as caixas e o texto antes de retomar.",
        user_id=user.id,
        origem="spam_reportado",
    )
    return _montar(db, estado)


@router.post("/retomar", response_model=EstadoOperacaoOut)
def retomar_rota(
    db: Session = Depends(get_db), _: Usuario = Depends(require_role(Papel.admin))
) -> EstadoOperacaoOut:
    return _montar(db, retomar(db))
