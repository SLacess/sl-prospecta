"""Caixa de Aprovação (CONSTITUICAO §12.1, item 4; ADR 0014, ponto 4; ADR 0016): edição em linha, aprovar,
rejeitar com motivo, e a confirmação manual de envio que serve de fallback para quando o Mensageiro não
está em uso (sem caixa conectada, por exemplo).

Só o toque de dia 0 chega aqui — é o único que o Redator/Crítico já escreveram (Fase 3, Tarefa 2). Aprovar e
"marcar como enviado" são ações separadas: aprovar congela o texto final (editado ou não) e mede
`percentual_editado`; o envio em si, quando há caixa conectada, é o worker (Mensageiro, Tarefa 3) que faz —
esta rota de confirmação manual existe para quando não há, ou o envio automático falhou.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.caixa_aprovacao import calcular_percentual_editado
from app.db import get_db
from app.deps import get_current_user, require_role
from app.models import Contato, Empresa, EstadoProspect, Papel, Sequencia, Toque, Usuario
from app.timeline import registrar_evento

router = APIRouter(tags=["caixa de aprovação"])

META_APROVACOES = 50
LIMITE_EDICAO_PCT = Decimal(20)

FiltroCaixa = Literal["pendentes", "aprovados", "rejeitados", "enviados"]


class ItemCaixaOut(BaseModel):
    toque_id: uuid.UUID
    sequencia_id: uuid.UUID
    empresa_id: uuid.UUID
    empresa_nome: str
    contato_nome: str
    contato_area: str
    persona: str
    angulo: str
    achado_titulo: str
    achado_pagina_url: str
    gancho_justificativa: str
    dia: int
    canal: str
    nota: int | None
    aprovado_critico: bool | None
    motivo_critico: str | None
    tentativas: int | None
    assunto: str
    corpo: str
    decisao_humana: str | None
    assunto_final: str | None
    corpo_final: str | None
    percentual_editado: Decimal | None
    motivo_rejeicao: str | None
    decidido_por_nome: str | None
    decidido_em: datetime | None
    enviado_em: datetime | None
    enviado_por_nome: str | None
    guardiao_resultado: str | None
    guardiao_motivo: str | None
    guardiao_avaliado_em: datetime | None


class AprovarIn(BaseModel):
    assunto: str = Field(min_length=1, max_length=200)
    corpo: str = Field(min_length=1)


class RejeitarIn(BaseModel):
    motivo: str = Field(min_length=1, max_length=2000)


class PlacarCaixaOut(BaseModel):
    meta: int
    aprovados: int
    aprovados_dentro_da_meta: int
    percentual_medio_editado: float | None
    atingido: bool
    pendencias: list[str]


def _condicao_filtro(filtro: FiltroCaixa):
    if filtro == "pendentes":
        return Toque.decisao_humana.is_(None)
    if filtro == "aprovados":
        return Toque.decisao_humana == "aprovado"
    if filtro == "rejeitados":
        return Toque.decisao_humana == "rejeitado"
    return Toque.enviado_em.is_not(None)  # enviados


def _nomes_usuarios(db: Session, ids: list[uuid.UUID | None]) -> dict[uuid.UUID, str]:
    validos = {i for i in ids if i is not None}
    if not validos:
        return {}
    linhas = db.execute(select(Usuario.id, Usuario.nome).where(Usuario.id.in_(validos))).all()
    return dict(linhas)


def _montar(
    toque: Toque, seq: Sequencia, contato: Contato, empresa: Empresa, nomes: dict[uuid.UUID, str]
) -> ItemCaixaOut:
    return ItemCaixaOut(
        toque_id=toque.id,
        sequencia_id=seq.id,
        empresa_id=empresa.id,
        empresa_nome=empresa.nome,
        contato_nome=contato.nome,
        contato_area=contato.area,
        persona=seq.persona,
        angulo=seq.angulo,
        achado_titulo=seq.achado_titulo,
        achado_pagina_url=seq.achado_pagina_url,
        gancho_justificativa=seq.gancho_justificativa,
        dia=toque.dia,
        canal=toque.canal,
        nota=toque.nota,
        aprovado_critico=toque.aprovado,
        motivo_critico=toque.motivo_critico,
        tentativas=toque.tentativas,
        assunto=toque.assunto or "",
        corpo=toque.corpo or "",
        decisao_humana=toque.decisao_humana,
        assunto_final=toque.assunto_final,
        corpo_final=toque.corpo_final,
        percentual_editado=toque.percentual_editado,
        motivo_rejeicao=toque.motivo_rejeicao,
        decidido_por_nome=nomes.get(toque.decidido_por) if toque.decidido_por else None,
        decidido_em=toque.decidido_em,
        enviado_em=toque.enviado_em,
        enviado_por_nome=nomes.get(toque.enviado_por) if toque.enviado_por else None,
        guardiao_resultado=toque.guardiao_resultado,
        guardiao_motivo=toque.guardiao_motivo,
        guardiao_avaliado_em=toque.guardiao_avaliado_em,
    )


def _contexto(db: Session, toque_id: uuid.UUID) -> tuple[Toque, Sequencia, Contato, Empresa]:
    linha = db.execute(
        select(Toque, Sequencia, Contato, Empresa)
        .join(Sequencia, Sequencia.id == Toque.sequencia_id)
        .join(Contato, Contato.id == Sequencia.contato_id)
        .join(Empresa, Empresa.id == Sequencia.empresa_id)
        .where(Toque.id == toque_id, Toque.dia == 0)
    ).first()
    if linha is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Toque não encontrado.")
    return linha


@router.get("/caixa-aprovacao", response_model=list[ItemCaixaOut])
def listar(
    filtro: FiltroCaixa = Query(default="pendentes"),
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_user),
) -> list[ItemCaixaOut]:
    linhas = db.execute(
        select(Toque, Sequencia, Contato, Empresa)
        .join(Sequencia, Sequencia.id == Toque.sequencia_id)
        .join(Contato, Contato.id == Sequencia.contato_id)
        .join(Empresa, Empresa.id == Sequencia.empresa_id)
        .where(Toque.dia == 0, Toque.status == "rascunho", _condicao_filtro(filtro))
        .order_by(Sequencia.criado_em)
    ).all()
    ids = [t.decidido_por for t, *_ in linhas] + [t.enviado_por for t, *_ in linhas]
    nomes = _nomes_usuarios(db, ids)
    return [_montar(t, s, c, e, nomes) for t, s, c, e in linhas]


@router.post("/toques/{toque_id}/aprovar", response_model=ItemCaixaOut)
def aprovar(
    toque_id: uuid.UUID,
    dados: AprovarIn,
    db: Session = Depends(get_db),
    user: Usuario = Depends(require_role(Papel.admin, Papel.vendedor)),
) -> ItemCaixaOut:
    toque, seq, contato, empresa = _contexto(db, toque_id)
    if toque.enviado_em is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Esta mensagem já foi marcada como enviada."
        )
    assunto = dados.assunto.strip()
    corpo = dados.corpo.strip()
    if not assunto or not corpo:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Assunto e corpo não podem ficar vazios."
        )
    percentual = calcular_percentual_editado(toque.assunto or "", toque.corpo or "", assunto, corpo)
    agora = datetime.now(UTC)
    linhas = (
        db.query(Toque)
        .filter(Toque.id == toque_id, Toque.enviado_em.is_(None))
        .update(
            {
                Toque.decisao_humana: "aprovado",
                Toque.assunto_final: assunto,
                Toque.corpo_final: corpo,
                Toque.percentual_editado: percentual,
                Toque.decidido_por: user.id,
                Toque.decidido_em: agora,
                Toque.motivo_rejeicao: None,
                # o texto pode ter mudado nesta aprovação — uma avaliação anterior do Guardião
                # (ADR 0016) não vale mais para o texto novo; o worker reavalia na próxima rodada
                Toque.guardiao_resultado: None,
                Toque.guardiao_motivo: None,
                Toque.guardiao_avaliado_em: None,
            },
            synchronize_session="fetch",
        )
    )
    if linhas != 1:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Esta mensagem já foi marcada como enviada."
        )
    mensagem = f"{user.nome} aprovou a mensagem para {contato.nome} (dia {toque.dia})."
    if percentual > 0:
        mensagem += f" Editou {percentual}% do texto."
    registrar_evento(
        db,
        empresa.id,
        "toque_aprovado",
        "humano",
        mensagem,
        contato_id=str(contato.id),
        percentual_editado=float(percentual),
        usuario_id=str(user.id),
    )
    db.commit()
    db.refresh(toque)
    return _montar(toque, seq, contato, empresa, _nomes_usuarios(db, [toque.decidido_por, toque.enviado_por]))


@router.post("/toques/{toque_id}/rejeitar", response_model=ItemCaixaOut)
def rejeitar(
    toque_id: uuid.UUID,
    dados: RejeitarIn,
    db: Session = Depends(get_db),
    user: Usuario = Depends(require_role(Papel.admin, Papel.vendedor)),
) -> ItemCaixaOut:
    toque, seq, contato, empresa = _contexto(db, toque_id)
    if toque.enviado_em is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Esta mensagem já foi marcada como enviada."
        )
    motivo = dados.motivo.strip()
    if not motivo:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Explique o motivo da rejeição."
        )
    agora = datetime.now(UTC)
    linhas = (
        db.query(Toque)
        .filter(Toque.id == toque_id, Toque.enviado_em.is_(None))
        .update(
            {
                Toque.decisao_humana: "rejeitado",
                Toque.motivo_rejeicao: motivo,
                Toque.decidido_por: user.id,
                Toque.decidido_em: agora,
            },
            synchronize_session="fetch",
        )
    )
    if linhas != 1:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Esta mensagem já foi marcada como enviada."
        )
    registrar_evento(
        db,
        empresa.id,
        "toque_rejeitado",
        "humano",
        f"{user.nome} rejeitou a mensagem para {contato.nome}: {motivo}",
        contato_id=str(contato.id),
        usuario_id=str(user.id),
    )
    db.commit()
    db.refresh(toque)
    return _montar(toque, seq, contato, empresa, _nomes_usuarios(db, [toque.decidido_por, toque.enviado_por]))


@router.post("/toques/{toque_id}/enviado", response_model=ItemCaixaOut)
def marcar_enviado(
    toque_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: Usuario = Depends(require_role(Papel.admin, Papel.vendedor)),
) -> ItemCaixaOut:
    toque, seq, contato, empresa = _contexto(db, toque_id)
    if toque.decisao_humana != "aprovado":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Só é possível marcar como enviada uma mensagem já aprovada.",
        )
    if toque.enviado_em is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Esta mensagem já foi marcada como enviada."
        )
    agora = datetime.now(UTC)
    linhas = (
        db.query(Toque)
        .filter(Toque.id == toque_id, Toque.decisao_humana == "aprovado", Toque.enviado_em.is_(None))
        .update({Toque.enviado_em: agora, Toque.enviado_por: user.id}, synchronize_session="fetch")
    )
    if linhas != 1:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Esta mensagem já foi marcada como enviada."
        )
    registrar_evento(
        db,
        empresa.id,
        "toque_marcado_enviado",
        "humano",
        f"{user.nome} marcou como enviada a mensagem para {contato.nome} ({toque.canal}).",
        contato_id=str(contato.id),
        usuario_id=str(user.id),
    )
    # Um contato por vez: o primeiro envio confirmado entra a empresa em sequência (§7.1); os seguintes
    # encontram a empresa já em EM_SEQUENCIA e esta atualização não muda nada (não é erro).
    linhas_empresa = (
        db.query(Empresa)
        .filter(Empresa.id == empresa.id, Empresa.estado == EstadoProspect.preparando_abordagem)
        .update({Empresa.estado: EstadoProspect.em_sequencia}, synchronize_session="fetch")
    )
    if linhas_empresa == 1:
        registrar_evento(
            db,
            empresa.id,
            "entrou_em_sequencia",
            "humano",
            f"Primeiro envio confirmado ({contato.nome}): a empresa entra em sequência.",
            origem_estado=EstadoProspect.preparando_abordagem.value,
            destino_estado=EstadoProspect.em_sequencia.value,
        )
    db.commit()
    db.refresh(toque)
    return _montar(toque, seq, contato, empresa, _nomes_usuarios(db, [toque.decidido_por, toque.enviado_por]))


@router.get("/caixa-aprovacao/placar", response_model=PlacarCaixaOut)
def placar(db: Session = Depends(get_db), _: Usuario = Depends(get_current_user)) -> PlacarCaixaOut:
    """Critério de saída da Fase 3 (CONSTITUICAO §19): 50 e-mails aprovados com < 20% de edição."""
    aprovados = db.scalars(
        select(Toque).where(Toque.dia == 0, Toque.decisao_humana == "aprovado")
    ).all()
    dentro_da_meta = sum(
        1 for t in aprovados if t.percentual_editado is not None and t.percentual_editado < LIMITE_EDICAO_PCT
    )
    valores = [float(t.percentual_editado) for t in aprovados if t.percentual_editado is not None]
    media = round(sum(valores) / len(valores), 1) if valores else None
    pendencias = []
    if dentro_da_meta < META_APROVACOES:
        pendencias.append(
            f"faltam {META_APROVACOES - dentro_da_meta} aprovação(ões) com menos de 20% de edição"
        )
    return PlacarCaixaOut(
        meta=META_APROVACOES,
        aprovados=len(aprovados),
        aprovados_dentro_da_meta=dentro_da_meta,
        percentual_medio_editado=media,
        atingido=dentro_da_meta >= META_APROVACOES,
        pendencias=pendencias,
    )
