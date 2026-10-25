"""Revisão humana das auditorias (critério da Fase 1, CONSTITUICAO §19, ADR 0007).

Critério: 20 auditorias de pelo menos 4 setores, com os 3 achados para leigos revisados, ≥ 90% de acertos
(parcial vale meio) e nenhuma marcada com promessa de conformidade total (§2.2). Só o admin revisa.
"""

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user, require_role
from app.models import Auditoria, Empresa, Papel, RevisaoAchado, Usuario
from app.timeline import registrar_evento

router = APIRouter(tags=["revisão da Fase 1"])

META_AUDITORIAS = 20
META_SETORES = 4
META_PERCENTUAL = 90.0
VALOR = {"correto": 1.0, "parcial": 0.5, "incorreto": 0.0}
CHAVE_HONESTIDADE = "textos"

ROTULO_PROPRIO = {
    "teclado:armadilha_de_foco": "O foco do teclado fica preso em parte da página.",
    "teclado:sem_indicador_de_foco": "Elementos recebem o foco sem indicação visual aparente.",
    "teclado:sem_link_pular_conteudo": "Falta o link para pular ao conteúdo.",
    "responsivo:rolagem_horizontal_320": "Em 320 px o conteúdo exige rolagem lateral.",
    "semantica:links_genericos": 'Links com texto genérico ("saiba mais", "clique aqui").',
    "semantica:salto_de_titulo": "Títulos que pulam níveis.",
}

Veredito = Literal["correto", "parcial", "incorreto"]


class ItemIn(BaseModel):
    chave: str = Field(max_length=120)
    veredito: Veredito
    motivo: str | None = Field(default=None, max_length=2000)


class RevisaoIn(BaseModel):
    achados: list[ItemIn]
    tecnicos: list[ItemIn] = []
    textos_honestos: bool


class ItemOut(BaseModel):
    chave: str
    rotulo: str
    pagina: str | None = None
    veredito: Veredito | None
    motivo: str | None


class RevisaoOut(BaseModel):
    auditoria_id: uuid.UUID
    empresa_id: uuid.UUID
    achados: list[ItemOut]
    tecnicos: list[ItemOut]
    textos_honestos: bool | None
    completa: bool
    atualizado_em: datetime | None


class LinhaPlacarOut(BaseModel):
    empresa_id: uuid.UUID
    nome: str
    setor: str | None
    nota: int | None
    revisada: bool
    percentual: float | None


class PlacarOut(BaseModel):
    meta_auditorias: int
    meta_setores: int
    meta_percentual: float
    auditorias_revisadas: int
    setores: int
    percentual_correto: float | None
    promessas_encontradas: int
    atingido: bool
    pendencias: list[str]
    lista: list[LinhaPlacarOut]


# --- Itens revisáveis --------------------------------------------------------


def _achados(auditoria: Auditoria) -> list[dict[str, Any]]:
    analise = auditoria.achados_json if isinstance(auditoria.achados_json, dict) else {}
    return analise.get("top3_para_leigos", [])


def _tecnicos(auditoria: Auditoria) -> dict[str, str]:
    """Tipos de problema encontrados (mesma chave do Auditor com IA), com uma descrição curta."""
    itens: dict[str, str] = {}
    for p in auditoria.paginas_json or []:
        if p.get("status") != "ok":
            continue
        for v in p.get("axe", {}).get("violacoes", []):
            itens.setdefault(v["regra"], v.get("descricao") or v["regra"])
        teclado = p.get("teclado", {})
        if teclado.get("armadilha_de_foco"):
            itens.setdefault("teclado:armadilha_de_foco", ROTULO_PROPRIO["teclado:armadilha_de_foco"])
        if teclado.get("sem_indicador_aparente", 0) > 0:
            itens.setdefault("teclado:sem_indicador_de_foco", ROTULO_PROPRIO["teclado:sem_indicador_de_foco"])
        if teclado.get("link_pular_conteudo") is False:
            itens.setdefault(
                "teclado:sem_link_pular_conteudo", ROTULO_PROPRIO["teclado:sem_link_pular_conteudo"]
            )
        if p.get("responsivo_320", {}).get("rolagem_horizontal"):
            itens.setdefault(
                "responsivo:rolagem_horizontal_320", ROTULO_PROPRIO["responsivo:rolagem_horizontal_320"]
            )
        semantica = p.get("semantica") or {}
        if semantica.get("links_genericos"):
            itens.setdefault("semantica:links_genericos", ROTULO_PROPRIO["semantica:links_genericos"])
        if semantica.get("saltos_de_titulo"):
            itens.setdefault("semantica:salto_de_titulo", ROTULO_PROPRIO["semantica:salto_de_titulo"])
    return itens


def _auditoria_analisada(db: Session, auditoria_id: uuid.UUID) -> Auditoria:
    auditoria = db.get(Auditoria, auditoria_id)
    if auditoria is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Auditoria não encontrada.")
    if auditoria.nota is None or not _achados(auditoria):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Só auditorias já analisadas (com nota e achados) podem ser revisadas.",
        )
    return auditoria


def _revisoes(db: Session, auditoria_id: uuid.UUID) -> dict[tuple[str, str], RevisaoAchado]:
    linhas = db.scalars(select(RevisaoAchado).where(RevisaoAchado.auditoria_id == auditoria_id)).all()
    return {(r.tipo, r.chave): r for r in linhas}


def _completa(auditoria: Auditoria, revisoes: dict[tuple[str, str], RevisaoAchado]) -> bool:
    achados = {a["problema"] for a in _achados(auditoria)}
    return (
        bool(achados)
        and all(("achado_leigo", c) in revisoes for c in achados)
        and (("honestidade", CHAVE_HONESTIDADE) in revisoes)
    )


def _montar(auditoria: Auditoria, revisoes: dict[tuple[str, str], RevisaoAchado]) -> RevisaoOut:
    def item(tipo: str, chave: str, rotulo: str, pagina: str | None = None) -> ItemOut:
        r = revisoes.get((tipo, chave))
        return ItemOut(
            chave=chave,
            rotulo=rotulo,
            pagina=pagina,
            veredito=r.veredito if r else None,
            motivo=r.motivo if r else None,
        )

    honestidade = revisoes.get(("honestidade", CHAVE_HONESTIDADE))
    datas = [r.atualizado_em for r in revisoes.values() if r.atualizado_em]
    return RevisaoOut(
        auditoria_id=auditoria.id,
        empresa_id=auditoria.empresa_id,
        achados=[
            item("achado_leigo", a["problema"], a["titulo"], a.get("pagina")) for a in _achados(auditoria)
        ],
        tecnicos=[item("problema_tecnico", c, d) for c, d in sorted(_tecnicos(auditoria).items())],
        textos_honestos=None if honestidade is None else honestidade.veredito == "correto",
        completa=_completa(auditoria, revisoes),
        atualizado_em=max(datas) if datas else None,
    )


# --- Rotas -------------------------------------------------------------------


@router.get("/auditorias/{auditoria_id}/revisao", response_model=RevisaoOut)
def ver_revisao(
    auditoria_id: uuid.UUID, db: Session = Depends(get_db), _: Usuario = Depends(get_current_user)
) -> RevisaoOut:
    auditoria = _auditoria_analisada(db, auditoria_id)
    return _montar(auditoria, _revisoes(db, auditoria_id))


@router.put("/auditorias/{auditoria_id}/revisao", response_model=RevisaoOut)
def salvar_revisao(
    auditoria_id: uuid.UUID,
    dados: RevisaoIn,
    db: Session = Depends(get_db),
    user: Usuario = Depends(require_role(Papel.admin)),
) -> RevisaoOut:
    auditoria = _auditoria_analisada(db, auditoria_id)
    achados = {a["problema"] for a in _achados(auditoria)}
    tecnicos = set(_tecnicos(auditoria))

    enviados = {i.chave for i in dados.achados}
    if enviados != achados:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Revise os 3 achados para leigos desta auditoria.",
        )
    desconhecidos = {i.chave for i in dados.tecnicos} - tecnicos
    if desconhecidos:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Problema técnico que não está na auditoria: {', '.join(sorted(desconhecidos))}.",
        )
    for i in [*dados.achados, *dados.tecnicos]:
        if i.veredito != "correto" and not (i.motivo or "").strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Explique o motivo de cada item que não está correto.",
            )

    existentes = _revisoes(db, auditoria_id)
    agora = datetime.now(UTC)

    def gravar(tipo: str, chave: str, veredito: str, motivo: str | None) -> None:
        r = existentes.get((tipo, chave))
        if r is None:
            r = RevisaoAchado(
                auditoria_id=auditoria.id,
                empresa_id=auditoria.empresa_id,
                tipo=tipo,
                chave=chave,
                veredito=veredito,
                revisor_id=user.id,
            )
            db.add(r)
            existentes[(tipo, chave)] = r
        r.veredito, r.motivo, r.revisor_id, r.atualizado_em = (
            veredito,
            (motivo or "").strip() or None,
            user.id,
            agora,
        )

    for i in dados.achados:
        gravar("achado_leigo", i.chave, i.veredito, i.motivo)
    for i in dados.tecnicos:
        gravar("problema_tecnico", i.chave, i.veredito, i.motivo)
    gravar(
        "honestidade",
        CHAVE_HONESTIDADE,
        "correto" if dados.textos_honestos else "incorreto",
        None if dados.textos_honestos else "Texto com promessa de conformidade total ou 100% acessível.",
    )

    corretos = sum(VALOR[i.veredito] for i in [*dados.achados, *dados.tecnicos])
    total = len(dados.achados) + len(dados.tecnicos)
    registrar_evento(
        db,
        auditoria.empresa_id,
        "revisao_salva",
        "humano",
        f"Auditoria revisada: {round(corretos / total * 100)}% dos itens corretos.",
        usuario_id=str(user.id),
    )
    db.commit()
    return _montar(auditoria, existentes)


@router.get("/revisao/fase1", response_model=PlacarOut)
def placar_fase1(db: Session = Depends(get_db), _: Usuario = Depends(get_current_user)) -> PlacarOut:
    ultima = (
        select(Auditoria.empresa_id, func.max(Auditoria.criado_em).label("criado_em"))
        .where(Auditoria.nota.is_not(None))
        .group_by(Auditoria.empresa_id)
        .subquery()
    )
    linhas = db.execute(
        select(Auditoria, Empresa)
        .join(
            ultima,
            (Auditoria.empresa_id == ultima.c.empresa_id) & (Auditoria.criado_em == ultima.c.criado_em),
        )
        .join(Empresa, Empresa.id == Auditoria.empresa_id)
        .order_by(Empresa.nome)
    ).all()

    lista: list[LinhaPlacarOut] = []
    soma = total = promessas = 0.0
    setores: set[str] = set()
    revisadas = 0
    for auditoria, empresa in linhas:
        revisoes = _revisoes(db, auditoria.id)
        completa = _completa(auditoria, revisoes)
        itens = [r for (tipo, _), r in revisoes.items() if tipo in ("achado_leigo", "problema_tecnico")]
        percentual = round(sum(VALOR[r.veredito] for r in itens) / len(itens) * 100, 1) if itens else None
        if completa:
            revisadas += 1
            setores.add(empresa.setor or "outro")
            soma += sum(VALOR[r.veredito] for r in itens)
            total += len(itens)
            honestidade = revisoes.get(("honestidade", CHAVE_HONESTIDADE))
            promessas += honestidade is not None and honestidade.veredito != "correto"
        lista.append(
            LinhaPlacarOut(
                empresa_id=empresa.id,
                nome=empresa.nome,
                setor=empresa.setor,
                nota=auditoria.nota,
                revisada=completa,
                percentual=percentual,
            )
        )

    percentual_geral = round(soma / total * 100, 1) if total else None
    pendencias = []
    if revisadas < META_AUDITORIAS:
        pendencias.append(f"faltam {META_AUDITORIAS - revisadas} auditoria(s) revisada(s)")
    if len(setores) < META_SETORES:
        pendencias.append(f"faltam {META_SETORES - len(setores)} setor(es) diferente(s)")
    if percentual_geral is not None and percentual_geral < META_PERCENTUAL:
        pendencias.append(f"acertos em {percentual_geral}%, abaixo de {META_PERCENTUAL:.0f}%")
    if promessas:
        pendencias.append(f"{int(promessas)} auditoria(s) com promessa de conformidade nos textos")
    return PlacarOut(
        meta_auditorias=META_AUDITORIAS,
        meta_setores=META_SETORES,
        meta_percentual=META_PERCENTUAL,
        auditorias_revisadas=revisadas,
        setores=len(setores),
        percentual_correto=percentual_geral,
        promessas_encontradas=int(promessas),
        atingido=not pendencias and percentual_geral is not None,
        pendencias=pendencias,
        lista=lista,
    )
