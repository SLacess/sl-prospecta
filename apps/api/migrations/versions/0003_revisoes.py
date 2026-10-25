"""Fase 1 — revisão humana dos achados (critério do §19: 20 auditorias, ≥ 90% corretos).

Só cria a tabela nova; nada da 0001/0002 muda.

Revision ID: 0003_revisoes
Revises: 0002_dossies_auditorias
Create Date: 2026-10-25
"""

import sqlalchemy as sa
from alembic import op

revision = "0003_revisoes"
down_revision = "0002_dossies_auditorias"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "revisoes_achados",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "auditoria_id", sa.Uuid(), sa.ForeignKey("auditorias.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("empresa_id", sa.Uuid(), sa.ForeignKey("empresas.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tipo", sa.String(30), nullable=False),  # achado_leigo | problema_tecnico | honestidade
        sa.Column("chave", sa.String(120), nullable=False),
        sa.Column("veredito", sa.String(20), nullable=False),  # correto | parcial | incorreto
        sa.Column("motivo", sa.Text()),
        sa.Column("revisor_id", sa.Uuid(), sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("auditoria_id", "tipo", "chave", name="uq_revisoes_auditoria_tipo_chave"),
        sa.CheckConstraint("veredito IN ('correto', 'parcial', 'incorreto')", name="ck_revisoes_veredito"),
    )
    op.create_index("ix_revisoes_achados_auditoria_id", "revisoes_achados", ["auditoria_id"])


def downgrade() -> None:
    op.drop_table("revisoes_achados")
