"""Fase 2 — Qualificador (CONSTITUICAO §7.3, Etapa 3): histórico do score e tabelas de apoio na `config`.

Só aditiva: cria `qualificacoes` e insere `sinais_pesos` e `pressao_setor` sem tocar nas chaves existentes.

Revision ID: 0004_qualificacoes
Revises: 0003_revisoes
Create Date: 2026-10-26
"""

import json

import sqlalchemy as sa
from alembic import op

revision = "0004_qualificacoes"
down_revision = "0003_revisoes"
branch_labels = None
depends_on = None

# Pontos (0–100) por sinal do dossiê no componente Intenção; o total tem teto de 100
SINAIS_PESOS = {
    "vaga_pcd_ou_inclusao": 20,
    "relatorio_esg": 20,
    "pagina_acessibilidade": 20,
    "app_ou_portal": 20,
    "outro": 10,
    "mencao_inclusao": 10,
    "mencoes_teto": 20,
}
# Pressão regulatória por setor (0–100). A LBI, art. 63, vale para todos; os setores somam exigências próprias
PRESSAO_SETOR = {
    "educacao": 90,
    "utilities": 80,
    "saude": 75,
    "financeiro": 75,
    "ecommerce": 60,
    "outro": 40,
}


def upgrade() -> None:
    op.create_table(
        "qualificacoes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("empresa_id", sa.Uuid(), sa.ForeignKey("empresas.id", ondelete="CASCADE"), nullable=False),
        sa.Column("auditoria_id", sa.Uuid(), sa.ForeignKey("auditorias.id", ondelete="SET NULL")),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("faixa", sa.String(10), nullable=False),
        sa.Column("componentes_json", sa.JSON(), nullable=False),
        sa.Column("pesos_json", sa.JSON(), nullable=False),
        sa.Column("regra_versao", sa.String(20), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("score >= 0 AND score <= 100", name="ck_qualificacoes_score_0_100"),
        sa.CheckConstraint("faixa IN ('quente', 'morno', 'frio')", name="ck_qualificacoes_faixa"),
    )
    op.create_index("ix_qualificacoes_empresa_criado", "qualificacoes", ["empresa_id", "criado_em"])

    config = sa.table("config", sa.column("chave", sa.String), sa.column("valor_json", sa.JSON))
    conn = op.get_bind()
    for chave, valor in (("sinais_pesos", SINAIS_PESOS), ("pressao_setor", PRESSAO_SETOR)):
        existe = conn.execute(sa.select(config.c.chave).where(config.c.chave == chave)).first()
        if existe is None:
            conn.execute(
                sa.text("INSERT INTO config (chave, valor_json) VALUES (:chave, CAST(:valor AS JSON))"),
                {"chave": chave, "valor": json.dumps(valor)},
            )


def downgrade() -> None:
    op.execute("DELETE FROM config WHERE chave IN ('sinais_pesos', 'pressao_setor')")
    op.drop_table("qualificacoes")
