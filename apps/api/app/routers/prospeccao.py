"""Entrada individual de prospects e linha do tempo (CONSTITUICAO §7.2 e §12.1, tela 1)."""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.budget import verificar_disjuntor
from app.db import get_db
from app.deps import get_current_user, require_role
from app.domain import Alvo, EntradaInvalida, interpretar_entrada
from app.models import Empresa, EstadoProspect, Evento, Papel, Usuario
from app.queue import Fila, FilaIndisponivel, get_fila
from app.timeline import registrar_evento

router = APIRouter(tags=["prospecção"])

LIMITE_EVENTOS = 200


class ProspeccaoIn(BaseModel):
    alvo: str = Field(max_length=500, description="Nome da empresa ou endereço do site")


class EmpresaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nome: str
    dominio: str | None
    estado: EstadoProspect
    fonte: str
    criado_em: datetime


class EventoOut(BaseModel):
    id: uuid.UUID
    tipo: str
    origem: str
    mensagem: str
    ocorrido_em: datetime


class EmpresaDetalheOut(EmpresaOut):
    eventos: list[EventoOut]


class ProspeccaoOut(BaseModel):
    empresa: EmpresaOut
    duplicada: bool
    na_fila: bool
    fila_pausada: bool
    mensagem: str


def _buscar_existente(db: Session, alvo: Alvo) -> Empresa | None:
    if alvo.dominio:
        return db.scalar(select(Empresa).where(Empresa.dominio == alvo.dominio))
    # Só pelo nome não há domínio para comparar: evita o cadastro repetido do mesmo nome pendente
    return db.scalar(
        select(Empresa)
        .where(Empresa.dominio.is_(None), func.lower(Empresa.nome) == alvo.nome.lower())
        .order_by(Empresa.criado_em)
        .limit(1)
    )


def _registrar_duplicada(db: Session, empresa: Empresa, texto: str, user: Usuario) -> Empresa:
    registrar_evento(
        db, empresa.id, "entrada_duplicada", "humano",
        "Esta empresa já estava cadastrada; a nova entrada foi registrada na linha do tempo.",
        entrada=texto, usuario_id=str(user.id),
    )
    db.commit()
    return empresa


def _registrar_entrada(db: Session, alvo: Alvo, texto: str, user: Usuario) -> tuple[Empresa, bool]:
    existente = _buscar_existente(db, alvo)
    if existente:
        return _registrar_duplicada(db, existente, texto, user), True

    empresa = Empresa(
        nome=alvo.nome, dominio=alvo.dominio, fonte="manual", estado=EstadoProspect.novo,
        responsavel_id=user.id,
    )
    db.add(empresa)
    try:
        db.flush()
    except IntegrityError:
        # Outra requisição cadastrou o mesmo domínio ao mesmo tempo
        db.rollback()
        existente = _buscar_existente(db, alvo)
        if existente is None:
            raise
        return _registrar_duplicada(db, existente, texto, user), True

    mensagem = (
        f"Empresa cadastrada a partir do site {alvo.dominio}."
        if alvo.tipo == "url"
        else "Empresa cadastrada pelo nome. O site oficial será identificado na pesquisa."
    )
    registrar_evento(
        db, empresa.id, "entrada_recebida", "humano", mensagem,
        entrada=texto, tipo_entrada=alvo.tipo, usuario_id=str(user.id),
    )
    db.commit()
    return empresa, False


def _registrar_evento_sistema(db: Session, empresa_id: uuid.UUID, tipo: str, mensagem: str) -> None:
    registrar_evento(db, empresa_id, tipo, "sistema", mensagem)
    db.commit()


@router.post("/prospeccao", response_model=ProspeccaoOut, status_code=status.HTTP_201_CREATED)
async def prospectar(
    dados: ProspeccaoIn,
    response: Response,
    db: Session = Depends(get_db),
    user: Usuario = Depends(require_role(Papel.admin, Papel.vendedor)),
    fila: Fila = Depends(get_fila),
) -> ProspeccaoOut:
    try:
        alvo = interpretar_entrada(dados.alvo)
    except EntradaInvalida as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from None

    empresa, duplicada = await run_in_threadpool(_registrar_entrada, db, alvo, dados.alvo.strip(), user)
    if duplicada:
        response.status_code = status.HTTP_200_OK

    # Só empresas ainda em NOVO entram na fila; o job_id fixo evita processamento em dobro
    na_fila = False
    if empresa.estado == EstadoProspect.novo:
        try:
            novo_job = await fila.enfileirar_processamento(empresa.id)
        except FilaIndisponivel:
            await run_in_threadpool(
                _registrar_evento_sistema, db, empresa.id, "falha_enfileirar",
                "Não foi possível colocar a empresa na fila de processamento.",
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="A empresa foi registrada, mas a fila de processamento está indisponível. "
                "Tente de novo em alguns minutos.",
            ) from None
        if novo_job:
            await run_in_threadpool(
                _registrar_evento_sistema, db, empresa.id, "enfileirado", "Empresa na fila de processamento."
            )
        na_fila = True

    disjuntor = await run_in_threadpool(verificar_disjuntor, db)
    partes = [
        "Esta empresa já está cadastrada." if duplicada else "Empresa cadastrada.",
    ]
    if na_fila:
        partes.append("Processamento na fila.")
    if na_fila and disjuntor.atingido:
        partes.append("O teto diário de IA foi atingido: o processamento começa quando o orçamento reabrir.")

    return ProspeccaoOut(
        empresa=EmpresaOut.model_validate(empresa),
        duplicada=duplicada,
        na_fila=na_fila,
        fila_pausada=disjuntor.atingido,
        mensagem=" ".join(partes),
    )


@router.get("/empresas/{empresa_id}", response_model=EmpresaDetalheOut)
def detalhar_empresa(
    empresa_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_user),
) -> EmpresaDetalheOut:
    empresa = db.get(Empresa, empresa_id)
    if empresa is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Empresa não encontrada.")

    recentes = db.scalars(
        select(Evento)
        .where(Evento.empresa_id == empresa_id)
        .order_by(Evento.ocorrido_em.desc())
        .limit(LIMITE_EVENTOS)
    ).all()
    eventos = [
        EventoOut(
            id=e.id, tipo=e.tipo, origem=e.origem,
            mensagem=str((e.dados_json or {}).get("mensagem", e.tipo)), ocorrido_em=e.ocorrido_em,
        )
        for e in reversed(recentes)
    ]
    return EmpresaDetalheOut(**EmpresaOut.model_validate(empresa).model_dump(), eventos=eventos)
