"""Estado de pausa da operação de envio (CONSTITUICAO §13; ADR 0016, Tarefa 4).

Guardado em `config` (chave "operacao") em vez de uma tabela nova: é só um estado, sem histórico a
consultar. O worker (Mensageiro, disjuntor de bounce) lê e escreve a mesma chave direto no banco, com sua
própria cópia desta lógica (`workers/slp_workers/orchestrator/operacao.py`) — cada lado só fala com o
próprio banco (CONSTITUICAO §6), como já acontece com o disjuntor de custo de IA
(`app/budget.py`/`orchestrator/budget.py`).
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models import Config

CHAVE_OPERACAO = "operacao"


@dataclass(frozen=True)
class EstadoOperacao:
    pausado: bool
    motivo: str | None = None
    pausado_em: datetime | None = None
    pausado_por: uuid.UUID | None = None
    origem: str | None = None


def _ler_valor(db: Session) -> dict:
    linha = db.get(Config, CHAVE_OPERACAO)
    return linha.valor_json if linha and linha.valor_json else {}


def _gravar_valor(db: Session, valores: dict) -> None:
    linha = db.get(Config, CHAVE_OPERACAO)
    if linha is None:
        db.add(Config(chave=CHAVE_OPERACAO, valor_json=valores))
    else:
        linha.valor_json = valores
    db.commit()


def ler_estado(db: Session) -> EstadoOperacao:
    v = _ler_valor(db)
    return EstadoOperacao(
        pausado=bool(v.get("pausado")),
        motivo=v.get("motivo"),
        pausado_em=datetime.fromisoformat(v["pausado_em"]) if v.get("pausado_em") else None,
        pausado_por=uuid.UUID(v["pausado_por"]) if v.get("pausado_por") else None,
        origem=v.get("origem"),
    )


def pausar(db: Session, *, motivo: str, user_id: uuid.UUID, origem: str) -> EstadoOperacao:
    _gravar_valor(
        db,
        {
            "pausado": True,
            "motivo": motivo,
            "pausado_em": datetime.now(UTC).isoformat(),
            "pausado_por": str(user_id),
            "origem": origem,
        },
    )
    return ler_estado(db)


def retomar(db: Session) -> EstadoOperacao:
    _gravar_valor(db, {"pausado": False})
    return ler_estado(db)
