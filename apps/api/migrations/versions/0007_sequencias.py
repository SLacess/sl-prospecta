"""Fase 3 — Geração da sequência (CONSTITUICAO §7.3, Etapas 5-6; §9.3; §9.4): sequencias e toques.

Só aditiva: cria `sequencias` (a decisão do Estrategista, uma por contato) e `toques` (um por dia
planejado da cadência — só o toque de dia 0 é escrito e revisado nesta tarefa; os demais ficam
"planejada"). Acrescenta `acoes_agentes.contato_id` (Estrategista/Redator/Crítico chamam a IA uma vez por
contato, não por empresa — sem essa coluna não dá para saber de qual contato foi cada chamada). Não move
a empresa para EM_SEQUENCIA: a caixa de aprovação do §7.1 (Tarefa 3) fica entre PREPARANDO_ABORDAGEM e
EM_SEQUENCIA.

Revision ID: 0007_sequencias
Revises: 0006_lotes
Create Date: 2026-11-19
"""

import sqlalchemy as sa
from alembic import op

revision = "0007_sequencias"
down_revision = "0006_lotes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sequencias",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("empresa_id", sa.Uuid(), sa.ForeignKey("empresas.id", ondelete="CASCADE"), nullable=False),
        sa.Column("contato_id", sa.Uuid(), sa.ForeignKey("contatos.id", ondelete="CASCADE"), nullable=False),
        # ti | rh_di | marketing_digital | esg | juridico_compliance (CONSTITUICAO §9.2)
        sa.Column("persona", sa.String(30), nullable=False),
        # experiencia_cliente | inclusao_colaboradores_pcd | esg_reputacao | conformidade_legal |
        # conversao_alcance_mercado (CONSTITUICAO §7.3 Etapa 5)
        sa.Column("angulo", sa.String(40), nullable=False),
        sa.Column("achado_titulo", sa.String(300), nullable=False),
        sa.Column("achado_pagina_url", sa.String(500), nullable=False),
        sa.Column("gancho_justificativa", sa.Text(), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "persona IN ('ti', 'rh_di', 'marketing_digital', 'esg', 'juridico_compliance')",
            name="ck_sequencias_persona",
        ),
        sa.CheckConstraint(
            "angulo IN ('experiencia_cliente', 'inclusao_colaboradores_pcd', 'esg_reputacao', "
            "'conformidade_legal', 'conversao_alcance_mercado')",
            name="ck_sequencias_angulo",
        ),
        sa.UniqueConstraint("contato_id", name="uq_sequencias_contato_id"),
    )
    op.create_index("ix_sequencias_empresa_id", "sequencias", ["empresa_id"])

    op.create_table(
        "toques",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "sequencia_id", sa.Uuid(), sa.ForeignKey("sequencias.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("dia", sa.Integer(), nullable=False),
        sa.Column("canal", sa.String(20), nullable=False),  # email | linkedin | whatsapp
        # planejada | rascunho
        sa.Column("status", sa.String(20), nullable=False, server_default="planejada"),
        sa.Column("conteudo_sugerido", sa.Text(), nullable=False),
        sa.Column("assunto", sa.String(200)),  # só o toque de dia 0 (Redator)
        sa.Column("corpo", sa.Text()),
        sa.Column("fatos_usados", sa.JSON()),
        sa.Column("criterios_json", sa.JSON()),
        sa.Column("nota", sa.Integer()),
        sa.Column("aprovado", sa.Boolean()),
        sa.Column("motivo_critico", sa.Text()),
        sa.Column("tentativas", sa.Integer()),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("canal IN ('email', 'linkedin', 'whatsapp')", name="ck_toques_canal"),
        sa.CheckConstraint("status IN ('planejada', 'rascunho')", name="ck_toques_status"),
        sa.UniqueConstraint("sequencia_id", "dia", name="uq_toques_sequencia_dia"),
    )
    op.create_index("ix_toques_sequencia_id", "toques", ["sequencia_id"])

    op.add_column(
        "acoes_agentes",
        sa.Column("contato_id", sa.Uuid(), sa.ForeignKey("contatos.id", ondelete="SET NULL")),
    )


def downgrade() -> None:
    op.drop_column("acoes_agentes", "contato_id")
    op.drop_table("toques")
    op.drop_table("sequencias")
