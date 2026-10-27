"""CRM Kanban (CONSTITUICAO §12.1, item 2): colunas = estados do §7.1, cartões com score (número + texto),
nota de acessibilidade, próximo passo e responsável; mudança manual de estado registrada (ADR 0011)."""

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.crm import (
    ABORDADAS,
    ORDEM_ESTADOS,
    ROTULO_ESTADO,
    destinos_manuais,
    problemas,
    proximo_passo,
    transicao_permitida,
)
from app.db import get_db
from app.deps import get_current_user, require_role
from app.models import Auditoria, Contato, Empresa, EstadoProspect, Papel, Qualificacao, Usuario
from app.timeline import registrar_evento

router = APIRouter(tags=["CRM"])

LIMITE_POR_COLUNA = 200
ROTULO_FAIXA = {"quente": "Quente", "morno": "Morno", "frio": "Frio"}
Faixa = Literal["quente", "morno", "frio"]


class DestinoOut(BaseModel):
    estado: str
    rotulo: str
    motivo_obrigatorio: bool


class CartaoOut(BaseModel):
    id: uuid.UUID
    nome: str
    dominio: str | None
    estado: str
    setor: str | None
    score: int | None
    faixa: Faixa | None
    rotulo_faixa: str | None
    nota_acessibilidade: int | None
    proximo_passo: str
    responsavel: str | None
    problema: str | None
    destinos: list[DestinoOut]


class ColunaOut(BaseModel):
    estado: str
    rotulo: str
    total: int
    fase_3: bool
    cartoes: list[CartaoOut]


class QuadroOut(BaseModel):
    colunas: list[ColunaOut]
    total: int


class MudancaEstadoIn(BaseModel):
    origem: EstadoProspect
    destino: EstadoProspect
    motivo: str | None = Field(default=None, max_length=1000)


class FunilOut(BaseModel):
    prospects: int
    qualificados: int
    com_decisores: int
    reunioes: int


def destinos_out(estado: EstadoProspect) -> list[DestinoOut]:
    return [
        DestinoOut(estado=d.estado.value, rotulo=d.rotulo, motivo_obrigatorio=d.motivo_obrigatorio)
        for d in destinos_manuais(estado)
    ]


def _ultimas_qualificacoes(db: Session, ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not ids:
        return {}
    ultima = (
        select(Qualificacao.empresa_id, func.max(Qualificacao.criado_em).label("quando"))
        .where(Qualificacao.empresa_id.in_(ids))
        .group_by(Qualificacao.empresa_id)
        .subquery()
    )
    linhas = db.execute(
        select(Qualificacao.empresa_id, Qualificacao.faixa).join(
            ultima,
            (Qualificacao.empresa_id == ultima.c.empresa_id) & (Qualificacao.criado_em == ultima.c.quando),
        )
    ).all()
    return dict(linhas)


def _ultimas_notas(db: Session, ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not ids:
        return {}
    ultima = (
        select(Auditoria.empresa_id, func.max(Auditoria.criado_em).label("quando"))
        .where(Auditoria.empresa_id.in_(ids), Auditoria.nota.is_not(None))
        .group_by(Auditoria.empresa_id)
        .subquery()
    )
    linhas = db.execute(
        select(Auditoria.empresa_id, Auditoria.nota).join(
            ultima, (Auditoria.empresa_id == ultima.c.empresa_id) & (Auditoria.criado_em == ultima.c.quando)
        )
    ).all()
    return dict(linhas)


def _contatos_validos(db: Session, ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not ids:
        return {}
    linhas = db.execute(
        select(Contato.empresa_id, func.count())
        .where(Contato.empresa_id.in_(ids), Contato.email_status == "valido", Contato.opt_out.is_(False))
        .group_by(Contato.empresa_id)
    ).all()
    return dict(linhas)


def montar_cartoes(db: Session, empresas: list[Empresa]) -> list[CartaoOut]:
    ids = [e.id for e in empresas]
    faixas = _ultimas_qualificacoes(db, ids)
    notas = _ultimas_notas(db, ids)
    validos = _contatos_validos(db, ids)
    alertas = problemas(db, ids)
    responsaveis = (
        dict(
            db.execute(
                select(Usuario.id, Usuario.nome).where(
                    Usuario.id.in_({e.responsavel_id for e in empresas if e.responsavel_id})
                )
            ).all()
        )
        if any(e.responsavel_id for e in empresas)
        else {}
    )
    cartoes = []
    for e in empresas:
        faixa = faixas.get(e.id)
        cartoes.append(
            CartaoOut(
                id=e.id,
                nome=e.nome,
                dominio=e.dominio,
                estado=e.estado.value,
                setor=e.setor,
                score=e.score,
                faixa=faixa,
                rotulo_faixa=ROTULO_FAIXA.get(faixa) if faixa else None,
                nota_acessibilidade=notas.get(e.id),
                proximo_passo=proximo_passo(e.estado, faixa, validos.get(e.id, 0), alertas.get(e.id)),
                responsavel=responsaveis.get(e.responsavel_id),
                problema=alertas.get(e.id),
                destinos=destinos_out(e.estado),
            )
        )
    return cartoes


@router.get("/crm/quadro", response_model=QuadroOut)
def quadro(
    busca: str | None = Query(default=None, max_length=120),
    setor: str | None = Query(default=None, max_length=40),
    faixa: Faixa | None = None,
    minhas: bool = False,
    lote_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),
) -> QuadroOut:
    consulta = select(Empresa)
    if busca and busca.strip():
        termo = f"%{busca.strip().lower()}%"
        consulta = consulta.where(
            or_(func.lower(Empresa.nome).like(termo), func.lower(Empresa.dominio).like(termo))
        )
    if setor:
        consulta = consulta.where(Empresa.setor == setor)
    if minhas:
        consulta = consulta.where(Empresa.responsavel_id == user.id)
    if lote_id:
        consulta = consulta.where(Empresa.lote_id == lote_id)
    empresas = list(db.scalars(consulta.order_by(Empresa.score.desc().nulls_last(), Empresa.nome)).all())
    if faixa:
        faixas = _ultimas_qualificacoes(db, [e.id for e in empresas])
        empresas = [e for e in empresas if faixas.get(e.id) == faixa]

    por_estado: dict[EstadoProspect, list[Empresa]] = {e: [] for e in ORDEM_ESTADOS}
    for e in empresas:
        por_estado[e.estado].append(e)
    exibidas = [e for estado in ORDEM_ESTADOS for e in por_estado[estado][:LIMITE_POR_COLUNA]]
    cartoes = {c.id: c for c in montar_cartoes(db, exibidas)}
    colunas = [
        ColunaOut(
            estado=estado.value,
            rotulo=ROTULO_ESTADO[estado],
            total=len(por_estado[estado]),
            fase_3=estado
            in {
                EstadoProspect.em_sequencia,
                EstadoProspect.sem_resposta,
                EstadoProspect.respondeu,
                EstadoProspect.nao_interessado,
            },
            cartoes=[cartoes[e.id] for e in por_estado[estado][:LIMITE_POR_COLUNA]],
        )
        for estado in ORDEM_ESTADOS
    ]
    return QuadroOut(colunas=colunas, total=len(empresas))


@router.post("/empresas/{empresa_id}/estado", response_model=CartaoOut)
def mudar_estado(
    empresa_id: uuid.UUID,
    dados: MudancaEstadoIn,
    db: Session = Depends(get_db),
    user: Usuario = Depends(require_role(Papel.admin, Papel.vendedor)),
) -> CartaoOut:
    empresa = db.get(Empresa, empresa_id)
    if empresa is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Empresa não encontrada.")
    if empresa.estado != dados.origem:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Esta empresa mudou de estado enquanto você olhava: agora está em "
            f"{ROTULO_ESTADO[empresa.estado]}. O quadro foi atualizado.",
        )
    if not transicao_permitida(dados.origem, dados.destino):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Não é possível mover de {ROTULO_ESTADO[dados.origem]} "
            f"para {ROTULO_ESTADO[dados.destino]} à mão.",
        )
    motivo = (dados.motivo or "").strip() or None
    destino = next(d for d in destinos_manuais(dados.origem) if d.estado == dados.destino)
    if destino.motivo_obrigatorio and not motivo:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Explique o motivo para mover para {destino.rotulo}.",
        )
    # Só muda se ainda estiver na origem: o orquestrador pode ter mudado o estado agora mesmo
    linhas = (
        db.query(Empresa)
        .filter(Empresa.id == empresa_id, Empresa.estado == dados.origem)
        .update({Empresa.estado: dados.destino}, synchronize_session="fetch")
    )
    if linhas != 1:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Esta empresa mudou de estado enquanto você olhava. O quadro foi atualizado.",
        )
    texto = f"{user.nome} moveu de {ROTULO_ESTADO[dados.origem]} para {ROTULO_ESTADO[dados.destino]}"
    registrar_evento(
        db,
        empresa_id,
        "estado_alterado_manual",
        "humano",
        texto + (f". Motivo: {motivo}" if motivo else "."),
        origem_estado=dados.origem.value,
        destino_estado=dados.destino.value,
        motivo=motivo,
        usuario_id=str(user.id),
    )
    db.commit()
    db.refresh(empresa)
    return montar_cartoes(db, [empresa])[0]


@router.get("/crm/funil", response_model=FunilOut)
def funil(db: Session = Depends(get_db), _: Usuario = Depends(get_current_user)) -> FunilOut:
    contagem = dict(db.execute(select(Empresa.estado, func.count()).group_by(Empresa.estado)).all())
    E = EstadoProspect

    def soma(*estados: EstadoProspect) -> int:
        return sum(contagem.get(e, 0) for e in estados)

    depois_da_reuniao = (E.reuniao_agendada, E.proposta_enviada, E.negociacao, E.ganho, E.perdido)
    return FunilOut(
        prospects=sum(contagem.values()) - contagem.get(E.arquivado, 0),
        qualificados=soma(E.qualificando, E.mapeando_decisores, *ABORDADAS, *depois_da_reuniao),
        com_decisores=soma(*ABORDADAS, *depois_da_reuniao),
        reunioes=soma(*depois_da_reuniao),
    )
