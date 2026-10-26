"""Qualificação (CONSTITUICAO §7.3, Etapa 3): o score da empresa e os pesos/faixas da tabela `config`.

O cálculo é do worker (Qualificador). Aqui só se lê o resultado e se ajustam os pesos (§12.1, Configurações).
Pesos novos valem para as próximas qualificações; para recalcular as atuais, use
`python -m slp_workers.cli qualificar --todas` no worker.
"""

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user, require_role
from app.models import Config, Evento, Papel, Qualificacao, Usuario

router = APIRouter(tags=["qualificação"])

PESOS_PADRAO = {
    "fit_icp": 0.30,
    "intencao": 0.25,
    "gravidade_barreiras": 0.20,
    "pressao_regulatoria": 0.15,
    "acessibilidade_decisor": 0.10,
}
FAIXAS_PADRAO = {"quente": 70, "morno": 45}
ROTULO_FAIXA = {"quente": "Quente", "morno": "Morno", "frio": "Frio"}
PROXIMO_PASSO = {
    "quente": "abordagem prioritária",
    "morno": "abordagem padrão",
    "frio": "nutrição de longo prazo",
}

Faixa = Literal["quente", "morno", "frio"]


class Pesos(BaseModel):
    fit_icp: float = Field(ge=0, le=1)
    intencao: float = Field(ge=0, le=1)
    gravidade_barreiras: float = Field(ge=0, le=1)
    pressao_regulatoria: float = Field(ge=0, le=1)
    acessibilidade_decisor: float = Field(ge=0, le=1)


class Faixas(BaseModel):
    quente: int = Field(ge=1, le=100)
    morno: int = Field(ge=1, le=100)


class ConfigScore(BaseModel):
    pesos: Pesos
    faixas: Faixas


def _erro_de_coerencia(dados: ConfigScore) -> str | None:
    """Mesmas regras do Qualificador (workers/slp_workers/agents/qualificador.py), em texto para o painel."""
    soma = sum(dados.pesos.model_dump().values())
    if abs(soma - 1) > 0.001:
        return f"Os pesos precisam somar 100% (hoje somam {round(soma * 100, 1):g}%)."
    if not dados.faixas.morno < dados.faixas.quente:
        return "O início da faixa Morno precisa ser menor que o início da faixa Quente."
    return None


class ComponenteOut(BaseModel):
    chave: str
    rotulo: str
    valor: int
    peso: float
    contribuicao: float
    justificativa: str


class QualificacaoOut(BaseModel):
    score: int
    faixa: Faixa
    rotulo_faixa: str
    proximo_passo: str
    componentes: list[ComponenteOut]
    regra_versao: str
    criado_em: datetime


def ultima_qualificacao(db: Session, empresa_id: uuid.UUID) -> QualificacaoOut | None:
    q = db.scalars(
        select(Qualificacao)
        .where(Qualificacao.empresa_id == empresa_id)
        .order_by(Qualificacao.criado_em.desc())
        .limit(1)
    ).first()
    if q is None:
        return None
    return QualificacaoOut(
        score=q.score,
        faixa=q.faixa,
        rotulo_faixa=ROTULO_FAIXA[q.faixa],
        proximo_passo=PROXIMO_PASSO[q.faixa],
        componentes=[ComponenteOut.model_validate(c) for c in q.componentes_json or []],
        regra_versao=q.regra_versao,
        criado_em=q.criado_em,
    )


def _ler(db: Session) -> ConfigScore:
    pesos = db.get(Config, "score_pesos")
    faixas = db.get(Config, "score_faixas")
    return ConfigScore(
        pesos=Pesos.model_validate({**PESOS_PADRAO, **((pesos.valor_json if pesos else None) or {})}),
        faixas=Faixas.model_validate({**FAIXAS_PADRAO, **((faixas.valor_json if faixas else None) or {})}),
    )


def _gravar(db: Session, chave: str, valor: dict) -> None:
    linha = db.get(Config, chave)
    if linha is None:
        db.add(Config(chave=chave, valor_json=valor))
    else:
        linha.valor_json = valor


@router.get("/config/score", response_model=ConfigScore)
def ver_config_score(db: Session = Depends(get_db), _: Usuario = Depends(get_current_user)) -> ConfigScore:
    return _ler(db)


@router.put("/config/score", response_model=ConfigScore)
def salvar_config_score(
    dados: ConfigScore,
    db: Session = Depends(get_db),
    user: Usuario = Depends(require_role(Papel.admin)),
) -> ConfigScore:
    erro = _erro_de_coerencia(dados)
    if erro:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=erro)
    anterior = _ler(db)
    pesos = {k: round(v, 4) for k, v in dados.pesos.model_dump().items()}
    _gravar(db, "score_pesos", pesos)
    _gravar(db, "score_faixas", dados.faixas.model_dump())
    # Registro da mudança (sem empresa): quem mudou, de quanto para quanto
    db.add(
        Evento(
            empresa_id=None,
            tipo="config_score_alterada",
            origem="humano",
            dados_json={
                "mensagem": f"{user.nome} alterou os pesos e as faixas do score.",
                "usuario_id": str(user.id),
                "antes": anterior.model_dump(),
                "depois": {"pesos": pesos, "faixas": dados.faixas.model_dump()},
            },
        )
    )
    db.commit()
    return _ler(db)


@router.get("/empresas/{empresa_id}/qualificacao", response_model=QualificacaoOut)
def ver_qualificacao(
    empresa_id: uuid.UUID, db: Session = Depends(get_db), _: Usuario = Depends(get_current_user)
) -> QualificacaoOut:
    q = ultima_qualificacao(db, empresa_id)
    if q is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Empresa ainda não qualificada.")
    return q
