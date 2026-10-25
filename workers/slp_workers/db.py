"""Acesso ao banco pelo orquestrador (CONSTITUICAO §6: só o orquestrador persiste).

O worker não importa o app da API: aqui ficam só as colunas que ele usa, em SQLAlchemy Core.
O esquema oficial é o das migrações Alembic em `apps/api`; o teste de fluxo do CI roda o
worker contra o banco migrado e quebra se estas definições divergirem.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Engine,
    MetaData,
    Numeric,
    String,
    Table,
    Uuid,
    create_engine,
)

metadata = MetaData()

empresas = Table(
    "empresas", metadata,
    Column("id", Uuid, primary_key=True),
    Column("nome", String(255)),
    Column("dominio", String(255)),
    Column("estado", String(40)),
)

eventos = Table(
    "eventos", metadata,
    Column("id", Uuid, primary_key=True),
    Column("empresa_id", Uuid),
    Column("contato_id", Uuid),
    Column("tipo", String(60)),
    Column("origem", String(40)),
    Column("dados_json", JSON),
    Column("ocorrido_em", DateTime(timezone=True)),
)

acoes_agentes = Table(
    "acoes_agentes", metadata,
    Column("id", Uuid, primary_key=True),
    Column("custo", Numeric(10, 4)),
    Column("criado_em", DateTime(timezone=True)),
)


def make_engine(database_url: str) -> Engine:
    return create_engine(database_url, pool_pre_ping=True)


def registrar_evento(
    engine: Engine, empresa_id: uuid.UUID, tipo: str, mensagem: str, **dados: object
) -> None:
    """Mesmo formato da API (`app/timeline.py`): `dados_json.mensagem` é o texto do painel."""
    with engine.begin() as conn:
        conn.execute(
            eventos.insert().values(
                id=uuid.uuid4(),
                empresa_id=empresa_id,
                tipo=tipo,
                origem="sistema",
                dados_json={"mensagem": mensagem, **dados},
                ocorrido_em=datetime.now(UTC),
            )
        )
