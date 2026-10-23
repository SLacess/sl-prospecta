"""Fase 0 — fundação: usuários, empresas, eventos, ações de agentes, supressão, config.

Revision ID: 0001_fundacao
Revises:
Create Date: 2026-10-23
"""

import json

import sqlalchemy as sa
from alembic import op

revision = "0001_fundacao"
down_revision = None
branch_labels = None
depends_on = None

ESTADOS = (
    "NOVO", "PESQUISANDO", "AUDITANDO", "QUALIFICANDO", "ARQUIVADO", "MAPEANDO_DECISORES",
    "PREPARANDO_ABORDAGEM", "EM_SEQUENCIA", "SEM_RESPOSTA", "RESPONDEU", "NAO_INTERESSADO",
    "REUNIAO_AGENDADA", "PROPOSTA_ENVIADA", "NEGOCIACAO", "GANHO", "PERDIDO",
)


def upgrade() -> None:
    # pgvector: memória vetorial (Fase 1+)
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    papel = sa.Enum("admin", "vendedor", "leitura", name="papel")
    estado = sa.Enum(*ESTADOS, name="estado_prospect")

    op.create_table(
        "usuarios",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("nome", sa.String(120), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("senha_hash", sa.String(255), nullable=False),
        sa.Column("papel", papel, nullable=False),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_usuarios_email", "usuarios", ["email"], unique=True)

    op.create_table(
        "empresas",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("nome", sa.String(255), nullable=False),
        sa.Column("dominio", sa.String(255)),
        sa.Column("cnpj", sa.String(18)),
        sa.Column("setor", sa.String(80)),
        sa.Column("porte", sa.String(40)),
        sa.Column("cidade", sa.String(120)),
        sa.Column("uf", sa.String(2)),
        sa.Column("fonte", sa.String(40), nullable=False),
        sa.Column("score", sa.Integer()),
        sa.Column("estado", estado, nullable=False),
        sa.Column("responsavel_id", sa.Uuid(), sa.ForeignKey("usuarios.id")),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_empresas_dominio", "empresas", ["dominio"], unique=True)
    op.create_index("ix_empresas_cnpj", "empresas", ["cnpj"])
    op.create_index("ix_empresas_estado", "empresas", ["estado"])

    op.create_table(
        "eventos",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("empresa_id", sa.Uuid(), sa.ForeignKey("empresas.id")),
        sa.Column("contato_id", sa.Uuid()),
        sa.Column("tipo", sa.String(60), nullable=False),
        sa.Column("origem", sa.String(40), nullable=False),
        sa.Column("dados_json", sa.JSON(), nullable=False),
        sa.Column("ocorrido_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_eventos_empresa_id", "eventos", ["empresa_id"])

    op.create_table(
        "acoes_agentes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("agente", sa.String(40), nullable=False),
        sa.Column("empresa_id", sa.Uuid(), sa.ForeignKey("empresas.id")),
        sa.Column("entrada_hash", sa.String(64), nullable=False),
        sa.Column("saida_json", sa.JSON(), nullable=False),
        sa.Column("raciocinio", sa.Text()),
        sa.Column("modelo", sa.String(60)),
        sa.Column("tokens_in", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tokens_out", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("custo", sa.Numeric(10, 4), nullable=False, server_default="0"),
        sa.Column("duracao_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_acoes_agentes_agente", "acoes_agentes", ["agente"])
    op.create_index("ix_acoes_agentes_empresa_id", "acoes_agentes", ["empresa_id"])

    op.create_table(
        "supressao",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email", sa.String(255)),
        sa.Column("dominio", sa.String(255)),
        sa.Column("motivo", sa.String(120), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_supressao_email", "supressao", ["email"], unique=True)
    op.create_index("ix_supressao_dominio", "supressao", ["dominio"])

    op.create_table(
        "config",
        sa.Column("chave", sa.String(80), primary_key=True),
        sa.Column("valor_json", sa.JSON(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Valores iniciais configuráveis (CONSTITUICAO §7.3 e §13)
    valores_iniciais = [
        {"chave": "score_pesos", "valor_json": {
            "fit_icp": 0.30, "intencao": 0.25, "gravidade_barreiras": 0.20,
            "pressao_regulatoria": 0.15, "acessibilidade_decisor": 0.10}},
        {"chave": "score_faixas", "valor_json": {"quente": 70, "morno": 45}},
        {"chave": "autonomia", "valor_json": {
            "pesquisa": "L4", "auditoria": "L4", "qualificacao": "L4", "decisores": "L4",
            "primeiro_email": "L2", "respostas": "L2", "propostas": "L1"}},
        {"chave": "icp", "valor_json": {
            "setores": ["saude", "educacao", "utilities", "ecommerce", "financeiro"],
            "porte_minimo": 100, "pais": "BR",
            "areas_decisoras": ["TI", "RH", "D&I", "Marketing", "ESG", "Compliance"]}},
    ]
    for item in valores_iniciais:
        valor = json.dumps(item["valor_json"], ensure_ascii=False).replace("'", "''")
        op.execute(f"INSERT INTO config (chave, valor_json) VALUES ('{item['chave']}', '{valor}'::json)")


def downgrade() -> None:
    for tabela in ("config", "supressao", "acoes_agentes", "eventos", "empresas", "usuarios"):
        op.drop_table(tabela)
    sa.Enum(name="estado_prospect").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="papel").drop(op.get_bind(), checkfirst=True)
