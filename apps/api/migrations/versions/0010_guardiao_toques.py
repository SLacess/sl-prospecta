"""Fase 3, Tarefa 4 (retomada) — resultado do Guardião em `toques` (CONSTITUICAO §9, §13; ADR 0016).

Só aditiva. O worker roda o Guardião "a seco" sobre toques já aprovados e não enviados, e grava aqui o
resultado — a Caixa de Aprovação só exibe; quem avalia e grava é o worker (CONSTITUICAO §6).

Revision ID: 0010_guardiao_toques
Revises: 0009_caixas_envio
Create Date: 2026-11-19
"""

import sqlalchemy as sa
from alembic import op

revision = "0010_guardiao_toques"
down_revision = "0009_caixas_envio"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("toques", sa.Column("guardiao_resultado", sa.String(20)))  # aprovado | bloqueado
    op.add_column("toques", sa.Column("guardiao_motivo", sa.Text()))
    op.add_column("toques", sa.Column("guardiao_avaliado_em", sa.DateTime(timezone=True)))
    op.create_check_constraint(
        "ck_toques_guardiao_resultado",
        "toques",
        "guardiao_resultado IS NULL OR guardiao_resultado IN ('aprovado', 'bloqueado')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_toques_guardiao_resultado", "toques", type_="check")
    for coluna in ("guardiao_avaliado_em", "guardiao_motivo", "guardiao_resultado"):
        op.drop_column("toques", coluna)
