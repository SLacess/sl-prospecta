"""Fase 1 — dossiês e auditorias (CONSTITUICAO §17).

Só cria tabelas novas; nada da 0001 é alterado, então o rollback de imagem
para a Fase 0 continua funcionando com o banco já migrado.

Revision ID: 0002_dossies_auditorias
Revises: 0001_fundacao
Create Date: 2026-10-24
"""

import sqlalchemy as sa
from alembic import op

revision = "0002_dossies_auditorias"
down_revision = "0001_fundacao"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dossies",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("empresa_id", sa.Uuid(), sa.ForeignKey("empresas.id", ondelete="CASCADE"), nullable=False),
        sa.Column("dados_json", sa.JSON(), nullable=False),
        sa.Column("resumo", sa.Text()),
        sa.Column("sinais_json", sa.JSON(), nullable=False),
        sa.Column("versao", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("empresa_id", "versao", name="uq_dossies_empresa_versao"),
    )
    op.create_index("ix_dossies_empresa_id", "dossies", ["empresa_id"])

    op.create_table(
        "auditorias",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("empresa_id", sa.Uuid(), sa.ForeignKey("empresas.id", ondelete="CASCADE"), nullable=False),
        sa.Column("nota", sa.Integer()),
        sa.Column("totais_json", sa.JSON(), nullable=False),
        sa.Column("achados_json", sa.JSON(), nullable=False),
        sa.Column("paginas_json", sa.JSON(), nullable=False),
        sa.Column("artefatos_urls", sa.JSON(), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("nota IS NULL OR (nota >= 0 AND nota <= 100)", name="ck_auditorias_nota_0_100"),
    )
    op.create_index("ix_auditorias_empresa_id", "auditorias", ["empresa_id"])

    # A soma diária do disjuntor de custo filtra por data
    op.create_index("ix_acoes_agentes_criado_em", "acoes_agentes", ["criado_em"])
    # A linha do tempo é lida em ordem cronológica por empresa
    op.create_index("ix_eventos_empresa_ocorrido", "eventos", ["empresa_id", "ocorrido_em"])


def downgrade() -> None:
    op.drop_index("ix_eventos_empresa_ocorrido", table_name="eventos")
    op.drop_index("ix_acoes_agentes_criado_em", table_name="acoes_agentes")
    op.drop_table("auditorias")
    op.drop_table("dossies")
