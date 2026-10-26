"""Qualificação no orquestrador (CONSTITUICAO §7.3, Etapa 3, e §7.1).

Chamada logo depois da análise da auditoria e pelo comando `python -m slp_workers.cli qualificar`.
Lê dossiê, auditoria e `config`, chama o Qualificador (regra fixa, sem IA) e grava: linha em `qualificacoes`,
`empresas.score`, a ação em `acoes_agentes` (custo zero) e o evento `qualificado`.

Quente e morno passam de QUALIFICANDO para MAPEANDO_DECISORES; frio fica em QUALIFICANDO até o vendedor
decidir no Kanban. Recalcular nunca faz a empresa voltar de estado.
"""

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import Engine, select, update

from slp_workers.agents.qualificador import EntradaQualificacao, Qualificacao, qualificar
from slp_workers.db import (
    auditorias,
    dossies,
    empresas,
    ler_config,
    qualificacoes,
    registrar_acao,
    registrar_evento,
)

QUALIFICANDO = "QUALIFICANDO"
MAPEANDO_DECISORES = "MAPEANDO_DECISORES"
ROTULO_FAIXA = {"quente": "Quente", "morno": "Morno", "frio": "Frio"}
PROXIMO_PASSO = {
    "quente": "abordagem prioritária; segue para o mapeamento de decisores",
    "morno": "abordagem padrão; segue para o mapeamento de decisores",
    "frio": "fica em qualificação para o vendedor decidir (nutrição ou arquivo)",
}


@dataclass
class ResultadoQualificacao:
    qualificacao: Qualificacao
    novo_estado: str | None  # None quando a empresa não mudou de estado


def _carregar(engine: Engine, empresa_id: uuid.UUID):
    with engine.connect() as conn:
        empresa = conn.execute(select(empresas).where(empresas.c.id == empresa_id)).first()
        auditoria = conn.execute(
            select(auditorias.c.id, auditorias.c.nota)
            .where(auditorias.c.empresa_id == empresa_id, auditorias.c.nota.is_not(None))
            .order_by(auditorias.c.criado_em.desc())
            .limit(1)
        ).first()
        dossie = conn.execute(
            select(dossies.c.dados_json, dossies.c.sinais_json)
            .where(dossies.c.empresa_id == empresa_id)
            .order_by(dossies.c.versao.desc())
            .limit(1)
        ).first()
        cfg = ler_config(conn, "score_pesos", "score_faixas", "icp", "sinais_pesos", "pressao_setor")
    return empresa, auditoria, dossie, cfg


def calcular(engine: Engine, empresa_id: uuid.UUID) -> tuple[Qualificacao, uuid.UUID] | None:
    """Só calcula. None quando ainda não há auditoria analisada (sem nota, não há o que qualificar)."""
    empresa, auditoria, dossie, cfg = _carregar(engine, empresa_id)
    if empresa is None or auditoria is None:
        return None
    dados = (dossie.dados_json if dossie else None) or {}
    sinais = (dossie.sinais_json if dossie else None) or {}
    entrada = EntradaQualificacao(
        setor=empresa.setor or dados.get("setor"),
        uf=empresa.uf,
        dominio=empresa.dominio,
        porte=empresa.porte,
        porte_indicios=dados.get("porte_indicios"),
        sinais=list(sinais.get("sinais") or dados.get("sinais") or []),
        mencoes_inclusao=list(sinais.get("mencoes_inclusao") or dados.get("mencoes_inclusao") or []),
        nota_auditoria=int(auditoria.nota),
        contatos_validos=0,  # a tabela `contatos` chega com o Mapeador de decisores (Fase 2, Tarefa 2)
    )
    q = qualificar(
        entrada,
        pesos=cfg.get("score_pesos"),
        faixas=cfg.get("score_faixas"),
        icp=cfg.get("icp"),
        sinais_pesos=cfg.get("sinais_pesos"),
        pressao_setor=cfg.get("pressao_setor"),
    )
    return q, auditoria.id


def _gravar(engine: Engine, empresa_id: uuid.UUID, auditoria_id: uuid.UUID, q: Qualificacao) -> str | None:
    with engine.begin() as conn:
        conn.execute(
            qualificacoes.insert().values(
                id=uuid.uuid4(),
                empresa_id=empresa_id,
                auditoria_id=auditoria_id,
                score=q.score,
                faixa=q.faixa,
                componentes_json=[c.model_dump() for c in q.componentes],
                pesos_json=q.pesos,
                regra_versao=q.regra_versao,
                criado_em=datetime.now(UTC),
            )
        )
        conn.execute(update(empresas).where(empresas.c.id == empresa_id).values(score=q.score))
        if q.faixa == "frio":
            return None
        r = conn.execute(
            update(empresas)
            .where(empresas.c.id == empresa_id, empresas.c.estado == QUALIFICANDO)
            .values(estado=MAPEANDO_DECISORES)
        )
        return MAPEANDO_DECISORES if r.rowcount == 1 else None


def qualificar_e_gravar(engine: Engine, empresa_id: uuid.UUID) -> ResultadoQualificacao | None:
    calculado = calcular(engine, empresa_id)
    if calculado is None:
        return None
    q, auditoria_id = calculado
    novo_estado = _gravar(engine, empresa_id, auditoria_id, q)
    entrada = {"componentes": [c.valor for c in q.componentes], "pesos": q.pesos}
    entrada_hash = hashlib.sha256(json.dumps(entrada, sort_keys=True).encode()).hexdigest()
    registrar_acao(
        engine,
        agente="qualificador",
        empresa_id=empresa_id,
        entrada_hash=entrada_hash,
        saida=q.model_dump(),
        raciocinio=q.raciocinio_resumido,
        modelo=q.regra_versao,
        tokens_in=0,
        tokens_out=0,
        custo_brl=Decimal("0"),
        duracao_ms=0,
    )
    registrar_evento(
        engine,
        empresa_id,
        "qualificado",
        f"Qualificada: score {q.score} de 100, {ROTULO_FAIXA[q.faixa]} — {PROXIMO_PASSO[q.faixa]}.",
        score=q.score,
        faixa=q.faixa,
        novo_estado=novo_estado,
    )
    return ResultadoQualificacao(q, novo_estado)
