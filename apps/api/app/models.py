"""Modelo de dados (CONSTITUICAO §17).

Fase 0: usuários, empresas, eventos, ações de agentes, supressão, config.
Fase 1: dossiês e auditorias (migração 0002); revisões dos achados (0003).
Fase 2: qualificações (0004); contatos e créditos de dados (0005).
Tabelas das fases seguintes (contatos, mensagens...) entram em migrações próprias.
"""

import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Papel(str, enum.Enum):
    admin = "admin"
    vendedor = "vendedor"
    leitura = "leitura"


class EstadoProspect(str, enum.Enum):
    """Máquina de estados do prospect — CONSTITUICAO §7.1. Não adicione estados sem emenda."""

    novo = "NOVO"
    pesquisando = "PESQUISANDO"
    auditando = "AUDITANDO"
    qualificando = "QUALIFICANDO"
    arquivado = "ARQUIVADO"
    mapeando_decisores = "MAPEANDO_DECISORES"
    preparando_abordagem = "PREPARANDO_ABORDAGEM"
    em_sequencia = "EM_SEQUENCIA"
    sem_resposta = "SEM_RESPOSTA"
    respondeu = "RESPONDEU"
    nao_interessado = "NAO_INTERESSADO"
    reuniao_agendada = "REUNIAO_AGENDADA"
    proposta_enviada = "PROPOSTA_ENVIADA"
    negociacao = "NEGOCIACAO"
    ganho = "GANHO"
    perdido = "PERDIDO"


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    nome: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    senha_hash: Mapped[str] = mapped_column(String(255))
    papel: Mapped[Papel] = mapped_column(Enum(Papel, name="papel"), default=Papel.vendedor)
    ativo: Mapped[bool] = mapped_column(default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Empresa(Base):
    __tablename__ = "empresas"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    nome: Mapped[str] = mapped_column(String(255))
    dominio: Mapped[str | None] = mapped_column(String(255), unique=True, index=True)
    cnpj: Mapped[str | None] = mapped_column(String(18), index=True)
    setor: Mapped[str | None] = mapped_column(String(80))
    porte: Mapped[str | None] = mapped_column(String(40))
    cidade: Mapped[str | None] = mapped_column(String(120))
    uf: Mapped[str | None] = mapped_column(String(2))
    fonte: Mapped[str] = mapped_column(String(40), default="manual")  # manual | lote | cacador | visitante
    score: Mapped[int | None] = mapped_column(Integer)
    estado: Mapped[EstadoProspect] = mapped_column(
        Enum(EstadoProspect, name="estado_prospect", values_callable=lambda e: [m.value for m in e]),
        default=EstadoProspect.novo,
        index=True,
    )
    responsavel_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id"))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Evento(Base):
    """Linha do tempo unificada (CONSTITUICAO §12.1)."""

    __tablename__ = "eventos"
    __table_args__ = (Index("ix_eventos_empresa_ocorrido", "empresa_id", "ocorrido_em"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    empresa_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("empresas.id"), index=True)
    contato_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("contatos.id", ondelete="SET NULL"))
    tipo: Mapped[str] = mapped_column(String(60))
    origem: Mapped[str] = mapped_column(String(40))  # agente | humano | prospect | sistema
    dados_json: Mapped[dict] = mapped_column(JSON, default=dict)
    ocorrido_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AcaoAgente(Base):
    """Registro de toda ação de IA (CONSTITUICAO §2.7 e §6)."""

    __tablename__ = "acoes_agentes"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    agente: Mapped[str] = mapped_column(String(40), index=True)
    empresa_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("empresas.id"), index=True)
    entrada_hash: Mapped[str] = mapped_column(String(64))
    saida_json: Mapped[dict] = mapped_column(JSON, default=dict)
    raciocinio: Mapped[str | None] = mapped_column(Text)
    modelo: Mapped[str | None] = mapped_column(String(60))
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    custo: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=0)
    duracao_ms: Mapped[int] = mapped_column(Integer, default=0)
    creditos: Mapped[int] = mapped_column(Integer, default=0)  # créditos de dados (Apollo) usados pela ação
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class Dossie(Base):
    """Saída do Pesquisador (CONSTITUICAO §7.3, Etapa 1). Uma versão nova a cada repesquisa."""

    __tablename__ = "dossies"
    __table_args__ = (UniqueConstraint("empresa_id", "versao", name="uq_dossies_empresa_versao"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    empresa_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("empresas.id", ondelete="CASCADE"), index=True)
    dados_json: Mapped[dict] = mapped_column(JSON, default=dict)
    resumo: Mapped[str | None] = mapped_column(Text)
    sinais_json: Mapped[dict] = mapped_column(JSON, default=dict)
    versao: Mapped[int] = mapped_column(Integer, default=1)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Auditoria(Base):
    """Saída do Auditor (CONSTITUICAO §8.2): nota 0–100, achados, páginas e artefatos (prints)."""

    __tablename__ = "auditorias"
    __table_args__ = (
        CheckConstraint("nota IS NULL OR (nota >= 0 AND nota <= 100)", name="ck_auditorias_nota_0_100"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    empresa_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("empresas.id", ondelete="CASCADE"), index=True)
    nota: Mapped[int | None] = mapped_column(Integer)
    totais_json: Mapped[dict] = mapped_column(JSON, default=dict)
    # Lista vazia até a análise com IA; depois, o JSON do §8.2 (packages/schemas/auditoria.schema.json)
    achados_json: Mapped[list | dict] = mapped_column(JSON, default=list)
    paginas_json: Mapped[list] = mapped_column(JSON, default=list)
    artefatos_urls: Mapped[list] = mapped_column(JSON, default=list)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RevisaoAchado(Base):
    """Revisão humana de um achado (critério da Fase 1, §19). Os motivos alimentam o Analista (§14.3)."""

    __tablename__ = "revisoes_achados"
    __table_args__ = (
        UniqueConstraint("auditoria_id", "tipo", "chave", name="uq_revisoes_auditoria_tipo_chave"),
        CheckConstraint("veredito IN ('correto', 'parcial', 'incorreto')", name="ck_revisoes_veredito"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    auditoria_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("auditorias.id", ondelete="CASCADE"), index=True
    )
    empresa_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("empresas.id", ondelete="CASCADE"))
    tipo: Mapped[str] = mapped_column(String(30))  # achado_leigo | problema_tecnico | honestidade
    chave: Mapped[str] = mapped_column(String(120))
    veredito: Mapped[str] = mapped_column(String(20))
    motivo: Mapped[str | None] = mapped_column(Text)
    revisor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuarios.id"))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Qualificacao(Base):
    """Saída do Qualificador (CONSTITUICAO §7.3, Etapa 3). Uma linha por cálculo; a mais recente vale."""

    __tablename__ = "qualificacoes"
    __table_args__ = (
        CheckConstraint("score >= 0 AND score <= 100", name="ck_qualificacoes_score_0_100"),
        CheckConstraint("faixa IN ('quente', 'morno', 'frio')", name="ck_qualificacoes_faixa"),
        Index("ix_qualificacoes_empresa_criado", "empresa_id", "criado_em"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    empresa_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("empresas.id", ondelete="CASCADE"))
    auditoria_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("auditorias.id", ondelete="SET NULL"))
    score: Mapped[int] = mapped_column(Integer)
    faixa: Mapped[str] = mapped_column(String(10))  # quente | morno | frio
    componentes_json: Mapped[list] = mapped_column(JSON, default=list)
    pesos_json: Mapped[dict] = mapped_column(JSON, default=dict)
    regra_versao: Mapped[str] = mapped_column(String(20))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Contato(Base):
    """Decisor da empresa (CONSTITUICAO §7.3, Etapa 4, e §17). Só dados profissionais (§15.1)."""

    __tablename__ = "contatos"
    __table_args__ = (
        CheckConstraint(
            "email_status IN ('valido', 'nao_verificado', 'sem_email')", name="ck_contatos_email_status"
        ),
        UniqueConstraint("empresa_id", "email", name="uq_contatos_empresa_email"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    empresa_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("empresas.id", ondelete="CASCADE"), index=True)
    nome: Mapped[str] = mapped_column(String(200))
    cargo: Mapped[str | None] = mapped_column(String(200))
    area: Mapped[str] = mapped_column(String(30))  # TI | RH | D&I | Marketing | ESG | Compliance
    email: Mapped[str | None] = mapped_column(String(255), index=True)
    email_status: Mapped[str] = mapped_column(String(20))  # valido | nao_verificado | sem_email
    linkedin_url: Mapped[str | None] = mapped_column(String(500))
    telefone: Mapped[str | None] = mapped_column(String(40))  # não coletado (coleta mínima)
    opt_out: Mapped[bool] = mapped_column(default=False)
    fonte: Mapped[str] = mapped_column(String(30))  # apollo | web+apollo
    fonte_url: Mapped[str | None] = mapped_column(String(500))
    apollo_id: Mapped[str | None] = mapped_column(String(64))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Supressao(Base):
    """Lista de supressão global — verificada antes de qualquer envio (CONSTITUICAO §15)."""

    __tablename__ = "supressao"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, index=True)
    dominio: Mapped[str | None] = mapped_column(String(255), index=True)
    motivo: Mapped[str] = mapped_column(String(120))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Config(Base):
    """ICP, pesos do score, tabela de preços, limites, guia de voz (CONSTITUICAO §12.1)."""

    __tablename__ = "config"

    chave: Mapped[str] = mapped_column(String(80), primary_key=True)
    valor_json: Mapped[dict] = mapped_column(JSON, default=dict)
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
