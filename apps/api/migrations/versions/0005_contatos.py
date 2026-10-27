"""Fase 2 — Mapeador de decisores (CONSTITUICAO §7.3, Etapa 4, e §17): contatos, créditos do Apollo e
cargos-alvo por área na `config`.

Só aditiva: cria `contatos`, liga `eventos.contato_id` a ela, acrescenta `acoes_agentes.creditos` (créditos
de dados usados pela ação; o disjuntor do Apollo soma esta coluna) e insere `config.decisores`.

Revision ID: 0005_contatos
Revises: 0004_qualificacoes
Create Date: 2026-10-26
"""

import json

import sqlalchemy as sa
from alembic import op

revision = "0005_contatos"
down_revision = "0004_qualificacoes"
branch_labels = None
depends_on = None

# Cargos usados na busca de pessoas do Apollo (busca sem crédito) e na busca web, por área decisora (§4.1)
DECISORES = {
    "titulos": {
        "TI": ["CTO", "CIO", "Diretor de TI", "Gerente de TI", "Head de Tecnologia", "Diretor de Tecnologia"],
        "RH": [
            "CHRO", "Diretor de RH", "Gerente de Recursos Humanos", "Head de Pessoas",
            "Diretor de Gente e Gestão",
        ],
        "D&I": ["Diversidade e Inclusão", "Diversity and Inclusion", "Head de Diversidade"],
        "Marketing": ["CMO", "Diretor de Marketing", "Head de Marketing", "Gerente de Marketing Digital"],
        "ESG": ["ESG", "Sustentabilidade", "Head de Sustentabilidade"],
        "Compliance": ["Compliance", "Diretor Jurídico", "General Counsel", "Gerente Jurídico"],
    },
    "senioridades": ["c_suite", "vp", "head", "director", "manager"],
    "prioridade_por_setor": {
        "educacao": ["TI", "Marketing", "D&I", "RH", "Compliance", "ESG"],
        "saude": ["TI", "Compliance", "Marketing", "RH", "ESG", "D&I"],
        "financeiro": ["Compliance", "TI", "Marketing", "D&I", "ESG", "RH"],
        "ecommerce": ["Marketing", "TI", "D&I", "ESG", "RH", "Compliance"],
        "utilities": ["Compliance", "TI", "ESG", "Marketing", "RH", "D&I"],
        "outro": ["TI", "Marketing", "RH", "D&I", "ESG", "Compliance"],
    },
    "max_contatos": 3,
}


def upgrade() -> None:
    op.create_table(
        "contatos",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("empresa_id", sa.Uuid(), sa.ForeignKey("empresas.id", ondelete="CASCADE"), nullable=False),
        sa.Column("nome", sa.String(200), nullable=False),
        sa.Column("cargo", sa.String(200)),
        sa.Column("area", sa.String(30), nullable=False),
        sa.Column("email", sa.String(255)),
        sa.Column("email_status", sa.String(20), nullable=False),  # valido | nao_verificado | sem_email
        sa.Column("linkedin_url", sa.String(500)),
        sa.Column("telefone", sa.String(40)),  # §17; não coletado (coleta mínima, §15.1)
        sa.Column("opt_out", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("fonte", sa.String(30), nullable=False),  # apollo | web+apollo
        sa.Column("fonte_url", sa.String(500)),
        sa.Column("apollo_id", sa.String(64)),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "email_status IN ('valido', 'nao_verificado', 'sem_email')", name="ck_contatos_email_status"
        ),
        sa.UniqueConstraint("empresa_id", "email", name="uq_contatos_empresa_email"),
    )
    op.create_index("ix_contatos_empresa_id", "contatos", ["empresa_id"])
    op.create_index("ix_contatos_email", "contatos", ["email"])
    op.create_foreign_key(
        "fk_eventos_contato_id", "eventos", "contatos", ["contato_id"], ["id"], ondelete="SET NULL"
    )
    op.add_column("acoes_agentes", sa.Column("creditos", sa.Integer(), nullable=False, server_default="0"))

    conn = op.get_bind()
    existe = conn.execute(sa.text("SELECT 1 FROM config WHERE chave = 'decisores'")).first()
    if existe is None:
        conn.execute(
            sa.text("INSERT INTO config (chave, valor_json) VALUES ('decisores', CAST(:valor AS JSON))"),
            {"valor": json.dumps(DECISORES, ensure_ascii=False)},
        )


def downgrade() -> None:
    op.execute("DELETE FROM config WHERE chave = 'decisores'")
    op.drop_column("acoes_agentes", "creditos")
    op.drop_constraint("fk_eventos_contato_id", "eventos", type_="foreignkey")
    op.drop_table("contatos")
