"""Acesso ao banco pelo orquestrador (CONSTITUICAO §6: só o orquestrador persiste).

O worker não importa o app da API: aqui ficam só as colunas que ele usa, em SQLAlchemy Core.
O esquema oficial é o das migrações Alembic em `apps/api`; o teste de fluxo do CI roda o
worker contra o banco migrado e quebra se estas definições divergirem.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Engine,
    Enum,
    ForeignKey,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    Text,
    Uuid,
    create_engine,
    func,
    select,
)

metadata = MetaData()

ESTADOS = (
    "NOVO", "PESQUISANDO", "AUDITANDO", "QUALIFICANDO", "ARQUIVADO", "MAPEANDO_DECISORES",
    "PREPARANDO_ABORDAGEM", "EM_SEQUENCIA", "SEM_RESPOSTA", "RESPONDEU", "NAO_INTERESSADO",
    "REUNIAO_AGENDADA", "PROPOSTA_ENVIADA", "NEGOCIACAO", "GANHO", "PERDIDO",
)

empresas = Table(
    "empresas", metadata,
    Column("id", Uuid, primary_key=True),
    Column("nome", String(255)),
    Column("dominio", String(255), unique=True),
    Column("setor", String(80)),
    Column("cidade", String(120)),
    Column("uf", String(2)),
    Column("estado", Enum(*ESTADOS, name="estado_prospect")),
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

dossies = Table(
    "dossies", metadata,
    Column("id", Uuid, primary_key=True),
    Column("empresa_id", Uuid, ForeignKey("empresas.id")),
    Column("dados_json", JSON),
    Column("resumo", Text),
    Column("sinais_json", JSON),
    Column("versao", Integer),
    Column("criado_em", DateTime(timezone=True)),
)

acoes_agentes = Table(
    "acoes_agentes", metadata,
    Column("id", Uuid, primary_key=True),
    Column("agente", String(40)),
    Column("empresa_id", Uuid),
    Column("entrada_hash", String(64)),
    Column("saida_json", JSON),
    Column("raciocinio", Text),
    Column("modelo", String(60)),
    Column("tokens_in", Integer),
    Column("tokens_out", Integer),
    Column("custo", Numeric(10, 4)),
    Column("duracao_ms", Integer),
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


def registrar_acao(
    engine: Engine,
    *,
    agente: str,
    empresa_id: uuid.UUID,
    entrada_hash: str,
    saida: dict,
    raciocinio: str | None,
    modelo: str,
    tokens_in: int,
    tokens_out: int,
    custo_brl: Decimal,
    duracao_ms: int,
) -> None:
    """Toda ação de IA fica registrada, inclusive as que falharam depois de gastar (CONSTITUICAO §2.7)."""
    with engine.begin() as conn:
        conn.execute(
            acoes_agentes.insert().values(
                id=uuid.uuid4(), agente=agente, empresa_id=empresa_id, entrada_hash=entrada_hash,
                saida_json=saida, raciocinio=raciocinio, modelo=modelo, tokens_in=tokens_in,
                tokens_out=tokens_out, custo=custo_brl, duracao_ms=duracao_ms, criado_em=datetime.now(UTC),
            )
        )


def proxima_versao_dossie(conn, empresa_id: uuid.UUID) -> int:
    atual = conn.scalar(select(func.max(dossies.c.versao)).where(dossies.c.empresa_id == empresa_id))
    return (atual or 0) + 1
