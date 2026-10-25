"""Estado dos disjuntores automáticos (CONSTITUICAO §13). Fase 1: só o de custo."""

from decimal import Decimal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.budget import verificar_disjuntor
from app.db import get_db
from app.deps import get_current_user
from app.models import Usuario

router = APIRouter(prefix="/governanca", tags=["governança"])


class DisjuntorCustoOut(BaseModel):
    custo_hoje_brl: Decimal
    teto_brl: Decimal
    atingido: bool
    mensagem: str


class DisjuntoresOut(BaseModel):
    custo: DisjuntorCustoOut


def _brl(valor: Decimal) -> str:
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


@router.get("/disjuntores", response_model=DisjuntoresOut)
def disjuntores(db: Session = Depends(get_db), _: Usuario = Depends(get_current_user)) -> DisjuntoresOut:
    d = verificar_disjuntor(db)
    mensagem = (
        f"Teto diário de IA atingido ({_brl(d.custo_hoje_brl)} de {_brl(d.teto_brl)}). "
        "Novas empresas ficam na fila e o processamento recomeça amanhã."
        if d.atingido
        else f"Custo de IA hoje: {_brl(d.custo_hoje_brl)} de {_brl(d.teto_brl)}."
    )
    return DisjuntoresOut(
        custo=DisjuntorCustoOut(
            custo_hoje_brl=d.custo_hoje_brl, teto_brl=d.teto_brl, atingido=d.atingido, mensagem=mensagem
        )
    )
