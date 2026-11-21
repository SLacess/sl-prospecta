"""Acesso ao banco pelo orquestrador (CONSTITUICAO §6: só o orquestrador persiste).

O worker não importa o app da API: aqui ficam só as colunas que ele usa, em SQLAlchemy Core.
O esquema oficial é o das migrações Alembic em `apps/api`; o teste de fluxo do CI roda o
worker contra o banco migrado e quebra se estas definições divergirem.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Engine,
    Enum,
    ForeignKey,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    Text,
    Uuid,
    create_engine,
    func,
    select,
)

metadata = MetaData()

ESTADOS = (
    "NOVO", "PESQUISANDO", "AUDITANDO", "QUALIFICANDO", "ARQUIVADO", "MAPEANDO_DECISORES",
    "PREPARANDO_ABORDAGEM", "EM_SEQUENCIA", "SEM_RESPOSTA", "RESPONDEU", "NAO_INTERESSADO",
    "REUNIAO_AGENDADA", "PROPOSTA_ENVIADA", "NEGOCIACAO", "GANHO", "PERDIDO",
)

empresas = Table(
    "empresas", metadata,
    Column("id", Uuid, primary_key=True),
    Column("nome", String(255)),
    Column("dominio", String(255), unique=True),
    Column("setor", String(80)),
    Column("cidade", String(120)),
    Column("uf", String(2)),
    Column("porte", String(40)),
    Column("score", Integer),
    Column("estado", Enum(*ESTADOS, name="estado_prospect")),
)

eventos = Table(
    "eventos", metadata,
    Column("id", Uuid, primary_key=True),
    Column("empresa_id", Uuid),
    Column("contato_id", Uuid),
    Column("tipo", String(60)),
    Column("origem", String(40)),
    Column("dados_json", JSON),
    Column("ocorrido_em", DateTime(timezone=True)),
)

dossies = Table(
    "dossies", metadata,
    Column("id", Uuid, primary_key=True),
    Column("empresa_id", Uuid, ForeignKey("empresas.id")),
    Column("dados_json", JSON),
    Column("resumo", Text),
    Column("sinais_json", JSON),
    Column("versao", Integer),
    Column("criado_em", DateTime(timezone=True)),
)

auditorias = Table(
    "auditorias", metadata,
    Column("id", Uuid, primary_key=True),
    Column("empresa_id", Uuid, ForeignKey("empresas.id")),
    Column("nota", Integer),
    Column("totais_json", JSON),
    Column("achados_json", JSON),
    Column("paginas_json", JSON),
    Column("artefatos_urls", JSON),
    Column("criado_em", DateTime(timezone=True)),
)

acoes_agentes = Table(
    "acoes_agentes", metadata,
    Column("id", Uuid, primary_key=True),
    Column("agente", String(40)),
    Column("empresa_id", Uuid),
    Column("contato_id", Uuid),
    Column("entrada_hash", String(64)),
    Column("saida_json", JSON),
    Column("raciocinio", Text),
    Column("modelo", String(60)),
    Column("tokens_in", Integer),
    Column("tokens_out", Integer),
    Column("custo", Numeric(10, 4)),
    Column("duracao_ms", Integer),
    Column("creditos", Integer, default=0),
    Column("criado_em", DateTime(timezone=True)),
)


qualificacoes = Table(
    "qualificacoes", metadata,
    Column("id", Uuid, primary_key=True),
    Column("empresa_id", Uuid, ForeignKey("empresas.id")),
    Column("auditoria_id", Uuid, ForeignKey("auditorias.id")),
    Column("score", Integer),
    Column("faixa", String(10)),
    Column("componentes_json", JSON),
    Column("pesos_json", JSON),
    Column("regra_versao", String(20)),
    Column("criado_em", DateTime(timezone=True)),
)

contatos = Table(
    "contatos", metadata,
    Column("id", Uuid, primary_key=True),
    Column("empresa_id", Uuid, ForeignKey("empresas.id")),
    Column("nome", String(200)),
    Column("cargo", String(200)),
    Column("area", String(30)),
    Column("email", String(255)),
    Column("email_status", String(20)),
    Column("linkedin_url", String(500)),
    Column("opt_out", Boolean, default=False),
    Column("fonte", String(30)),
    Column("fonte_url", String(500)),
    Column("apollo_id", String(64)),
    Column("criado_em", DateTime(timezone=True)),
)

sequencias = Table(
    "sequencias", metadata,
    Column("id", Uuid, primary_key=True),
    Column("empresa_id", Uuid, ForeignKey("empresas.id")),
    Column("contato_id", Uuid, ForeignKey("contatos.id")),
    Column("persona", String(30)),
    Column("angulo", String(40)),
    Column("achado_titulo", String(300)),
    Column("achado_pagina_url", String(500)),
    Column("gancho_justificativa", Text),
    Column("criado_em", DateTime(timezone=True)),
)

toques = Table(
    "toques", metadata,
    Column("id", Uuid, primary_key=True),
    Column("sequencia_id", Uuid, ForeignKey("sequencias.id")),
    Column("dia", Integer),
    Column("canal", String(20)),
    Column("status", String(20)),
    Column("conteudo_sugerido", Text),
    Column("assunto", String(200)),
    Column("corpo", Text),
    Column("fatos_usados", JSON),
    Column("criterios_json", JSON),
    Column("nota", Integer),
    Column("aprovado", Boolean),
    Column("motivo_critico", Text),
    Column("tentativas", Integer),
    Column("criado_em", DateTime(timezone=True)),
    # Caixa de Aprovação (migração 0008) — o Guardião avalia o texto final que o vendedor aprovou,
    # não o original do Redator: só ele reflete uma eventual edição em linha.
    Column("decisao_humana", String(20)),
    Column("assunto_final", String(200)),
    Column("corpo_final", Text),
    Column("enviado_em", DateTime(timezone=True)),
    # Guardião (migração 0010, Fase 3 Tarefa 4 — ADR 0016)
    Column("guardiao_resultado", String(20)),
    Column("guardiao_motivo", Text),
    Column("guardiao_avaliado_em", DateTime(timezone=True)),
)

caixas_envio = Table(
    "caixas_envio", metadata,
    Column("id", Uuid, primary_key=True),
    Column("email", String(255), unique=True),
    Column("nome_remetente", String(120)),
    Column("refresh_token_criptografado", Text),
    Column("ativa", Boolean, default=True),
    Column("limite_diario", Integer),
    Column("erro_verificacao", Text),
)

envios = Table(
    "envios", metadata,
    Column("id", Uuid, primary_key=True),
    Column("toque_id", Uuid, ForeignKey("toques.id")),
    Column("caixa_id", Uuid, ForeignKey("caixas_envio.id")),
    Column("destinatario", String(255)),
    Column("gmail_message_id", String(100)),
    Column("enviado_em", DateTime(timezone=True)),
)

microsites = Table(
    "microsites", metadata,
    Column("id", Uuid, primary_key=True),
    Column("empresa_id", Uuid, ForeignKey("empresas.id")),
    Column("auditoria_id", Uuid, ForeignKey("auditorias.id")),
    Column("slug", String(64), unique=True),
    Column("expira_em", DateTime(timezone=True)),
)

supressao = Table(
    "supressao", metadata,
    Column("id", Uuid, primary_key=True),
    Column("email", String(255)),
    Column("dominio", String(255)),
    Column("motivo", String(120)),
)

lotes = Table(
    "lotes", metadata,
    Column("id", Uuid, primary_key=True),
    Column("status", String(30)),
    Column("mapeamento_json", JSON),
    Column("mapeamento_origem", String(20)),
    Column("resumo_json", JSON),
)

config = Table(
    "config", metadata,
    Column("chave", String(80), primary_key=True),
    Column("valor_json", JSON),
)


def make_engine(database_url: str) -> Engine:
    return create_engine(database_url, pool_pre_ping=True)


def registrar_evento(
    engine: Engine,
    empresa_id: uuid.UUID,
    tipo: str,
    mensagem: str,
    *,
    contato_id: uuid.UUID | None = None,
    **dados: object,
) -> None:
    """Mesmo formato da API (`app/timeline.py`): `dados_json.mensagem` é o texto do painel."""
    with engine.begin() as conn:
        conn.execute(
            eventos.insert().values(
                id=uuid.uuid4(),
                empresa_id=empresa_id,
                contato_id=contato_id,
                tipo=tipo,
                origem="sistema",
                dados_json={"mensagem": mensagem, **dados},
                ocorrido_em=datetime.now(UTC),
            )
        )


def registrar_acao(
    engine: Engine,
    *,
    agente: str,
    empresa_id: uuid.UUID | None,
    entrada_hash: str,
    saida: dict,
    raciocinio: str | None,
    modelo: str,
    tokens_in: int,
    tokens_out: int,
    custo_brl: Decimal,
    duracao_ms: int,
    creditos: int = 0,
    contato_id: uuid.UUID | None = None,
) -> None:
    """Toda ação de IA fica registrada, inclusive as que falharam depois de gastar (CONSTITUICAO §2.7)."""
    with engine.begin() as conn:
        conn.execute(
            acoes_agentes.insert().values(
                id=uuid.uuid4(), agente=agente, empresa_id=empresa_id, contato_id=contato_id,
                entrada_hash=entrada_hash, saida_json=saida, raciocinio=raciocinio, modelo=modelo,
                tokens_in=tokens_in, tokens_out=tokens_out, custo=custo_brl, duracao_ms=duracao_ms,
                creditos=creditos, criado_em=datetime.now(UTC),
            )
        )


def ler_config(conn, *chaves: str) -> dict[str, dict]:
    """Valores da tabela `config` (ICP, pesos, faixas...). Chave ausente fica de fora e vale o padrão."""
    linhas = conn.execute(select(config.c.chave, config.c.valor_json).where(config.c.chave.in_(chaves)))
    return {chave: valor for chave, valor in linhas if isinstance(valor, dict)}


def proxima_versao_dossie(conn, empresa_id: uuid.UUID) -> int:
    atual = conn.scalar(select(func.max(dossies.c.versao)).where(dossies.c.empresa_id == empresa_id))
    return (atual or 0) + 1
