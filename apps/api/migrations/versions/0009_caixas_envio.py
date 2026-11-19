"""Fase 3, Tarefa 4 (retomada) — Caixas de envio conectadas (CONSTITUICAO §9, §15.2; ADR 0016).

Tabela nova e isolada: nenhuma coluna de `toques`/`empresas` muda aqui. O Mensageiro (Tarefa 3) é quem vai
ler `caixas_envio` para escolher a caixa da vez e gravar o rodízio/limite diário.

Revision ID: 0009_caixas_envio
Revises: 0008_caixa_aprovacao
Create Date: 2026-11-19
"""

import sqlalchemy as sa
from alembic import op

revision = "0009_caixas_envio"
down_revision = "0008_caixa_aprovacao"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "caixas_envio",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("nome_remetente", sa.String(120), nullable=False),
        sa.Column("refresh_token_criptografado", sa.Text(), nullable=False),
        sa.Column("escopos", sa.String(255), nullable=False),
        sa.Column("ativa", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("limite_diario", sa.Integer(), nullable=False),
        sa.Column("conectada_por", sa.Uuid(), sa.ForeignKey("usuarios.id", ondelete="SET NULL")),
        sa.Column(
            "conectada_em", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("erro_verificacao", sa.Text()),
    )
    op.create_index("ix_caixas_envio_email", "caixas_envio", ["email"])


def downgrade() -> None:
    op.drop_index("ix_caixas_envio_email", table_name="caixas_envio")
    op.drop_table("caixas_envio")
