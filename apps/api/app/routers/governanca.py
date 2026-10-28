"""Estado dos disjuntores automáticos (CONSTITUICAO §13): custo de IA e créditos do Apollo."""

from decimal import Decimal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.budget import verificar_creditos_apollo, verificar_disjuntor, verificar_gasto_apify
from app.db import get_db
from app.deps import get_current_user
from app.models import Usuario

router = APIRouter(prefix="/governanca", tags=["governança"])


class DisjuntorCustoOut(BaseModel):
    custo_hoje_brl: Decimal
    teto_brl: Decimal
    atingido: bool
    mensagem: str


class DisjuntorApolloOut(BaseModel):
    creditos_hoje: int
    teto: int
    atingido: bool
    mensagem: str


class DisjuntorApifyOut(BaseModel):
    gasto_hoje_usd: Decimal
    teto_usd: Decimal
    atingido: bool
    mensagem: str


class DisjuntoresOut(BaseModel):
    custo: DisjuntorCustoOut
    apollo: DisjuntorApolloOut
    apify: DisjuntorApifyOut


def _usd(valor: Decimal) -> str:
    return f"US$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


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
    a = verificar_creditos_apollo(db)
    mensagem_apollo = (
        f"Teto diário de créditos do Apollo atingido ({a.creditos_hoje} de {a.teto}). "
        "A busca de decisores recomeça amanhã."
        if a.atingido
        else f"Créditos do Apollo hoje: {a.creditos_hoje} de {a.teto}."
    )
    p = verificar_gasto_apify(db)
    gasto, teto = _usd(p.gasto_hoje_usd), _usd(p.teto_usd)
    mensagem_apify = (
        f"Teto diário do Apify atingido ({gasto} de {teto}). "
        "A verificação alternativa de e-mails recomeça amanhã."
        if p.atingido
        else f"Apify hoje: {gasto} de {teto}."
    )
    return DisjuntoresOut(
        custo=DisjuntorCustoOut(
            custo_hoje_brl=d.custo_hoje_brl, teto_brl=d.teto_brl, atingido=d.atingido, mensagem=mensagem
        ),
        apollo=DisjuntorApolloOut(
            creditos_hoje=a.creditos_hoje, teto=a.teto, atingido=a.atingido, mensagem=mensagem_apollo
        ),
        apify=DisjuntorApifyOut(
            gasto_hoje_usd=p.gasto_hoje_usd, teto_usd=p.teto_usd, atingido=p.atingido, mensagem=mensagem_apify
        ),
    )
