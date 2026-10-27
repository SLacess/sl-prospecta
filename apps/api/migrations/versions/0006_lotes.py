"""Fase 2 — Upload de planilha (CONSTITUICAO §7.2, entrada 2, e §12.1): lotes de empresas.

Só aditiva: cria `lotes` e acrescenta `empresas.lote_id`. As linhas lidas da planilha ficam em
`lotes.linhas_json` só até a confirmação ou o cancelamento (coleta mínima, §15.1); depois fica o resumo.

Revision ID: 0006_lotes
Revises: 0005_contatos
Create Date: 2026-10-27
"""

import sqlalchemy as sa
from alembic import op

revision = "0006_lotes"
down_revision = "0005_contatos"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lotes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("nome_arquivo", sa.String(255), nullable=False),
        sa.Column("criado_por", sa.Uuid(), sa.ForeignKey("usuarios.id"), nullable=False),
        # mapeando | aguardando_confirmacao | processando | cancelado
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("total_linhas", sa.Integer(), nullable=False),
        sa.Column("linha_cabecalho", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("cabecalhos_json", sa.JSON(), nullable=False),
        sa.Column("linhas_json", sa.JSON()),  # apagado na confirmação ou no cancelamento
        sa.Column("mapeamento_json", sa.JSON(), nullable=False),
        sa.Column("mapeamento_origem", sa.String(20), nullable=False),  # regras | ia | humano
        sa.Column("resumo_json", sa.JSON()),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("confirmado_em", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('mapeando', 'aguardando_confirmacao', 'processando', 'cancelado')",
            name="ck_lotes_status",
        ),
    )
    op.add_column("empresas", sa.Column("lote_id", sa.Uuid(), sa.ForeignKey("lotes.id", ondelete="SET NULL")))
    op.create_index("ix_empresas_lote_id", "empresas", ["lote_id"])


def downgrade() -> None:
    op.drop_index("ix_empresas_lote_id", "empresas")
    op.drop_column("empresas", "lote_id")
    op.drop_table("lotes")
