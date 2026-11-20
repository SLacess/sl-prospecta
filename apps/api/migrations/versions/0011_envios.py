"""Fase 3, Tarefa 3 (retomada) — log de envio do Mensageiro (CONSTITUICAO §9, §15.2; ADR 0016).

Tabela nova e isolada. Quem grava é só o worker (CONSTITUICAO §6): para cada e-mail que o Mensageiro manda
de fato pela Gmail API, fica aqui o registro de qual caixa enviou e o id da mensagem no Gmail — é a partir
desta tabela que o rodízio entre caixas e o limite diário por caixa são calculados.

Revision ID: 0011_envios
Revises: 0010_guardiao_toques
Create Date: 2026-11-19
"""

import sqlalchemy as sa
from alembic import op

revision = "0011_envios"
down_revision = "0010_guardiao_toques"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "envios",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("toque_id", sa.Uuid(), sa.ForeignKey("toques.id", ondelete="CASCADE"), nullable=False),
        sa.Column("caixa_id", sa.Uuid(), sa.ForeignKey("caixas_envio.id", ondelete="SET NULL")),
        sa.Column("destinatario", sa.String(255), nullable=False),
        sa.Column("gmail_message_id", sa.String(100), nullable=False),
        sa.Column(
            "enviado_em", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_envios_toque_id", "envios", ["toque_id"], unique=True)
    op.create_index("ix_envios_caixa_id", "envios", ["caixa_id"])


def downgrade() -> None:
    op.drop_index("ix_envios_caixa_id", table_name="envios")
    op.drop_index("ix_envios_toque_id", table_name="envios")
    op.drop_table("envios")
