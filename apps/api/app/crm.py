"""Regras do CRM (CONSTITUICAO §7.1 e §12.1, item 2): mudança manual de estado, próximo passo e alertas.

O orquestrador faz as transições automáticas (workers/slp_workers/orchestrator/pipeline.py). Aqui ficam só as
mudanças que o humano pode fazer pelo Kanban ou pela Ficha. Os passos que o sistema executa (pesquisa,
auditoria, mapeamento de decisores) e os da Fase 3 (sequência e respostas) não são destino manual.
Toda mudança manual vira evento na linha do tempo, com quem, de onde, para onde e por quê.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import EstadoProspect as E
from app.models import Evento

# Ordem das colunas do Kanban: a do §7.1
ORDEM_ESTADOS: tuple[E, ...] = (
    E.novo,
    E.pesquisando,
    E.auditando,
    E.qualificando,
    E.mapeando_decisores,
    E.preparando_abordagem,
    E.em_sequencia,
    E.sem_resposta,
    E.respondeu,
    E.nao_interessado,
    E.reuniao_agendada,
    E.proposta_enviada,
    E.negociacao,
    E.ganho,
    E.perdido,
    E.arquivado,
)
ROTULO_ESTADO = {
    E.novo: "Novo",
    E.pesquisando: "Pesquisando",
    E.auditando: "Auditando",
    E.qualificando: "Qualificando",
    E.arquivado: "Arquivado",
    E.mapeando_decisores: "Mapeando decisores",
    E.preparando_abordagem: "Preparando abordagem",
    E.em_sequencia: "Em sequência",
    E.sem_resposta: "Sem resposta",
    E.respondeu: "Respondeu",
    E.nao_interessado: "Não interessado",
    E.reuniao_agendada: "Reunião agendada",
    E.proposta_enviada: "Proposta enviada",
    E.negociacao: "Negociação",
    E.ganho: "Ganho",
    E.perdido: "Perdido",
}
# Colunas da Fase 3 (abordagem e conversa): aparecem no quadro, mas ninguém entra nelas à mão nesta fase
ESTADOS_DA_FASE_3 = {E.em_sequencia, E.sem_resposta, E.respondeu, E.nao_interessado}

ABORDADAS = {E.preparando_abordagem, *ESTADOS_DA_FASE_3}
_A_PARTIR_DE_ABORDAGEM = {*ABORDADAS}

# Mudanças manuais permitidas (ADR 0011). Arquivar vale de quase todo estado e entra à parte.
TRANSICOES_MANUAIS: dict[E, set[E]] = {
    E.arquivado: {E.qualificando},  # reabrir
    E.qualificando: {E.mapeando_decisores},  # seguir com uma empresa fria
    **{e: {E.reuniao_agendada} for e in _A_PARTIR_DE_ABORDAGEM},
    E.reuniao_agendada: {E.proposta_enviada},
    E.proposta_enviada: {E.negociacao, E.ganho, E.perdido},
    E.negociacao: {E.ganho, E.perdido},
}
NAO_ARQUIVAVEIS = {E.arquivado, E.ganho}
MOTIVO_OBRIGATORIO = {E.arquivado, E.perdido}

EVENTOS_DE_PROBLEMA = {
    "site_indisponivel": "site não pôde ser lido",
    "auditoria_bloqueada": "auditoria bloqueada",
    "pesquisa_falhou": "pesquisa falhou",
    "analise_falhou": "análise falhou",
    "mapeamento_falhou": "busca de decisores falhou",
    "confirmacao_dominio": "aguarda confirmação do site",
    "dominio_ja_cadastrado": "site já pertence a outra empresa",
    "falha_enfileirar": "não entrou na fila",
}


@dataclass(frozen=True)
class Destino:
    estado: E
    rotulo: str
    motivo_obrigatorio: bool


def destinos_manuais(origem: E) -> list[Destino]:
    alvos = set(TRANSICOES_MANUAIS.get(origem, set()))
    if origem not in NAO_ARQUIVAVEIS:
        alvos.add(E.arquivado)
    return [
        Destino(estado=e, rotulo=ROTULO_ESTADO[e], motivo_obrigatorio=e in MOTIVO_OBRIGATORIO)
        for e in ORDEM_ESTADOS
        if e in alvos
    ]


def transicao_permitida(origem: E, destino: E) -> bool:
    return any(d.estado == destino for d in destinos_manuais(origem))


def proximo_passo(estado: E, faixa: str | None, contatos_validos: int, problema: str | None) -> str:
    if problema:
        return f"Ver na ficha: {problema}"
    passos = {
        E.novo: "Na fila de processamento",
        E.pesquisando: "Pesquisa em andamento",
        E.auditando: "Auditoria em andamento",
        E.qualificando: ("Decidir: seguir ou arquivar" if faixa == "frio" else "Aguardando a qualificação"),
        E.mapeando_decisores: (
            "Sem decisor com e-mail verificado: decidir" if contatos_validos == 0 else "Buscando decisores"
        ),
        E.preparando_abordagem: "Aguarda a Fase 3 (abordagem)",
        E.reuniao_agendada: "Fazer a reunião e registrar o resultado",
        E.proposta_enviada: "Acompanhar a proposta",
        E.negociacao: "Fechar: ganho ou perdido",
        E.ganho: "Cliente",
        E.perdido: "Encerrado",
        E.arquivado: "Arquivado; pode ser reaberto",
    }
    return passos.get(estado, "Aguarda a Fase 3")


def problemas(db: Session, ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
    """Último evento de cada empresa: se for de problema, o vendedor precisa olhar."""
    if not ids:
        return {}
    ultimo = (
        select(Evento.empresa_id, func.max(Evento.ocorrido_em).label("quando"))
        .where(Evento.empresa_id.in_(ids))
        .group_by(Evento.empresa_id)
        .subquery()
    )
    linhas = db.execute(
        select(Evento.empresa_id, Evento.tipo).join(
            ultimo, (Evento.empresa_id == ultimo.c.empresa_id) & (Evento.ocorrido_em == ultimo.c.quando)
        )
    ).all()
    return {e: EVENTOS_DE_PROBLEMA[t] for e, t in linhas if t in EVENTOS_DE_PROBLEMA}
