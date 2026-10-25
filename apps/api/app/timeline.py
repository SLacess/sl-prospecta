"""Registro na linha do tempo unificada (tabela `eventos`, CONSTITUICAO §12.1)."""

import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models import Evento


def registrar_evento(
    db: Session, empresa_id: uuid.UUID, tipo: str, origem: str, mensagem: str, **dados: object
) -> Evento:
    """`mensagem` é o texto em português mostrado no painel e anunciado ao leitor de tela.

    O horário vem do Python (e não do `now()` do banco, que é fixo dentro da transação)
    para que eventos gravados juntos mantenham a ordem.
    """
    evento = Evento(
        empresa_id=empresa_id,
        tipo=tipo,
        origem=origem,
        dados_json={"mensagem": mensagem, **dados},
        ocorrido_em=datetime.now(UTC),
    )
    db.add(evento)
    return evento
