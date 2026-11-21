"""Link público do relatório para o e-mail do Redator (CONSTITUICAO §9.1, §17, §21.1).

Fatia mínima da tabela `microsites` que a CONSTITUICAO §17 já reserva para a Fase 5 — hoje só guarda o
`slug` aleatório e a expiração de 120 dias; `metricas_json` (engajamento) fica para quando o microsite
completo existir.

Revision ID: 0012_microsites
Revises: 0011_envios
Create Date: 2026-11-21
"""

import sqlalchemy as sa
from alembic import op

revision = "0012_microsites"
down_revision = "0011_envios"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "microsites",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("empresa_id", sa.Uuid(), sa.ForeignKey("empresas.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "auditoria_id", sa.Uuid(), sa.ForeignKey("auditorias.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("slug", sa.String(64), nullable=False, unique=True),
        sa.Column("expira_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("empresa_id", "auditoria_id", name="uq_microsites_empresa_auditoria"),
    )
    op.create_index("ix_microsites_empresa_id", "microsites", ["empresa_id"])
    op.create_index("ix_microsites_slug", "microsites", ["slug"])


def downgrade() -> None:
    op.drop_index("ix_microsites_slug", table_name="microsites")
    op.drop_index("ix_microsites_empresa_id", table_name="microsites")
    op.drop_table("microsites")
