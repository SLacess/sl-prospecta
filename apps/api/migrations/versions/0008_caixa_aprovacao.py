"""Fase 3 — Caixa de Aprovação (CONSTITUICAO §12.1, item 4; ADR 0014): decisão humana sobre o toque de dia 0.

Só aditiva: acrescenta a `toques` as colunas da decisão humana (aprovar/rejeitar com motivo, texto final
editado em linha e confirmação manual de envio — ADR 0014, ponto 4). `assunto`/`corpo` continuam sendo o
texto original do Redator/Crítico, intocado; `assunto_final`/`corpo_final` guardam o que o vendedor realmente
aprovou (igual ao original quando não editou nada), para medir o critério de saída da Fase 3 (50 aprovados
com < 20% de edição) via `percentual_editado`.

Revision ID: 0008_caixa_aprovacao
Revises: 0007_sequencias
Create Date: 2026-11-19
"""

import sqlalchemy as sa
from alembic import op

revision = "0008_caixa_aprovacao"
down_revision = "0007_sequencias"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("toques", sa.Column("decisao_humana", sa.String(20)))  # aprovado | rejeitado
    op.add_column(
        "toques",
        sa.Column("decidido_por", sa.Uuid(), sa.ForeignKey("usuarios.id", ondelete="SET NULL")),
    )
    op.add_column("toques", sa.Column("decidido_em", sa.DateTime(timezone=True)))
    op.add_column("toques", sa.Column("motivo_rejeicao", sa.Text()))
    op.add_column("toques", sa.Column("assunto_final", sa.String(200)))
    op.add_column("toques", sa.Column("corpo_final", sa.Text()))
    op.add_column("toques", sa.Column("percentual_editado", sa.Numeric(5, 2)))
    op.add_column("toques", sa.Column("enviado_em", sa.DateTime(timezone=True)))
    op.add_column(
        "toques",
        sa.Column("enviado_por", sa.Uuid(), sa.ForeignKey("usuarios.id", ondelete="SET NULL")),
    )
    op.create_check_constraint(
        "ck_toques_decisao_humana",
        "toques",
        "decisao_humana IS NULL OR decisao_humana IN ('aprovado', 'rejeitado')",
    )
    op.create_index("ix_toques_decisao_humana", "toques", ["decisao_humana"])


def downgrade() -> None:
    op.drop_index("ix_toques_decisao_humana", table_name="toques")
    op.drop_constraint("ck_toques_decisao_humana", "toques", type_="check")
    for coluna in (
        "enviado_por",
        "enviado_em",
        "percentual_editado",
        "corpo_final",
        "assunto_final",
        "motivo_rejeicao",
        "decidido_em",
        "decidido_por",
        "decisao_humana",
    ):
        op.drop_column("toques", coluna)
