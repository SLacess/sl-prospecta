"""Ficha do Prospect (CONSTITUICAO §12.1, tela 3): dossiê, auditoria, evidências, qualificação, linha do tempo
e o mini-relatório (§8.3). Tudo exige login; prints e relatórios saem do MinIO só por estas rotas."""

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.artefatos import Armazenamento, chave_de, chave_relatorio, get_armazenamento
from app.db import get_db
from app.deps import get_current_user
from app.models import Auditoria, Contato, Empresa, Evento, Papel, Usuario
from app.routers.prospeccao import (
    AuditoriaResumoOut,
    EmpresaOut,
    EventoOut,
    _resumo_auditoria,
    _ultima_auditoria,
    _ultimo_dossie,
)
from app.routers.qualificacao import QualificacaoOut, ultima_qualificacao

router = APIRouter(tags=["ficha do prospect"])

# Tamanho do print desktop do Auditor técnico (workers/slp_workers/audit/axe.py)
LARGURA_PRINT, ALTURA_PRINT = 1366, 768


class EmpresaFichaOut(EmpresaOut):
    setor: str | None
    cidade: str | None
    uf: str | None


class MencaoOut(BaseModel):
    tema: str
    trecho: str
    url: str


class SinalOut(BaseModel):
    tipo: str
    descricao: str
    url: str


class DossieCompletoOut(BaseModel):
    versao: int
    criado_em: datetime
    resumo: list[str]
    descricao: str | None
    missao: str | None
    produtos_servicos: list[str]
    publicos_atendidos: list[str]
    cidade: str | None
    uf: str | None
    porte_indicios: str | None
    mencoes_inclusao: list[MencaoOut]
    sinais: list[SinalOut]
    lacunas: list[str]
    paginas_lidas: list[str]
    tecnologias_site: list[str]
    raciocinio_resumido: str | None


class CaixaOut(BaseModel):
    """Posição do problema no print, em % da imagem."""

    left: float
    top: float
    width: float
    height: float


class EvidenciaOut(BaseModel):
    numero: int
    titulo: str
    pagina: str
    print_indice: int | None
    caixa: CaixaOut | None
    alt: str


ROTULO_EMAIL = {
    "valido": "e-mail verificado",
    "nao_verificado": "e-mail não verificado",
    "sem_email": "sem e-mail",
}


class DecisorOut(BaseModel):
    id: uuid.UUID
    nome: str
    cargo: str | None
    area: str
    email: str | None  # mascarado para o perfil leitura (coleta mínima, §15.1)
    email_status: str
    rotulo_email: str
    linkedin_url: str | None
    fonte: str
    fonte_url: str | None


def mascarar_email(email: str) -> str:
    usuario, _, dominio = email.partition("@")
    return f"{usuario[:1]}***@{dominio}"


def _decisores(db: Session, empresa_id: uuid.UUID, papel: Papel) -> list[DecisorOut]:
    linhas = db.scalars(
        select(Contato)
        .where(Contato.empresa_id == empresa_id, Contato.opt_out.is_(False))
        .order_by(Contato.criado_em, Contato.nome)
    ).all()
    return [
        DecisorOut(
            id=c.id,
            nome=c.nome,
            cargo=c.cargo,
            area=c.area,
            email=(mascarar_email(c.email) if papel == Papel.leitura else c.email) if c.email else None,
            email_status=c.email_status,
            rotulo_email=ROTULO_EMAIL.get(c.email_status, c.email_status),
            linkedin_url=c.linkedin_url,
            fonte=c.fonte,
            fonte_url=c.fonte_url,
        )
        for c in linhas
    ]


class FichaOut(BaseModel):
    empresa: EmpresaFichaOut
    dossie: DossieCompletoOut | None
    auditoria: AuditoriaResumoOut | None
    evidencias: list[EvidenciaOut]
    qualificacao: QualificacaoOut | None
    decisores: list[DecisorOut]
    relatorio_disponivel: bool
    eventos: list[EventoOut]


def _dossie(db: Session, empresa_id: uuid.UUID) -> DossieCompletoOut | None:
    d = _ultimo_dossie(db, empresa_id)
    if d is None:
        return None
    dados: dict[str, Any] = d.dados_json or {}
    local = dados.get("localizacao") or {}
    return DossieCompletoOut(
        versao=d.versao,
        criado_em=d.criado_em,
        resumo=[linha for linha in (d.resumo or "").splitlines() if linha.strip()],
        descricao=dados.get("descricao"),
        missao=dados.get("missao"),
        produtos_servicos=dados.get("produtos_servicos", []),
        publicos_atendidos=dados.get("publicos_atendidos", []),
        cidade=local.get("cidade"),
        uf=local.get("uf"),
        porte_indicios=dados.get("porte_indicios"),
        mencoes_inclusao=[MencaoOut.model_validate(m) for m in dados.get("mencoes_inclusao", [])],
        sinais=[SinalOut.model_validate(s) for s in dados.get("sinais", [])],
        lacunas=dados.get("lacunas", []),
        paginas_lidas=dados.get("paginas_lidas", []),
        tecnologias_site=dados.get("tecnologias_site", []),
        raciocinio_resumido=dados.get("raciocinio_resumido"),
    )


def _caixa(auditoria: Auditoria, pagina_url: str, problema: str) -> CaixaOut | None:
    for p in auditoria.paginas_json or []:
        if p.get("url") != pagina_url or p.get("status") != "ok":
            continue
        for v in p.get("axe", {}).get("violacoes", []):
            c = v.get("caixa") if v.get("regra") == problema else None
            if c:
                return CaixaOut(
                    left=round(c["x"] / LARGURA_PRINT * 100, 2),
                    top=round(c["y"] / ALTURA_PRINT * 100, 2),
                    width=round(c["largura"] / LARGURA_PRINT * 100, 2),
                    height=round(c["altura"] / ALTURA_PRINT * 100, 2),
                )
    return None


def _evidencias(auditoria: Auditoria | None, dominio: str | None) -> list[EvidenciaOut]:
    if auditoria is None or not isinstance(auditoria.achados_json, dict):
        return []
    urls = list(auditoria.artefatos_urls or [])
    saida = []
    for i, a in enumerate(auditoria.achados_json.get("top3_para_leigos", []), start=1):
        url_print = (a.get("evidencia") or {}).get("print")
        indice = urls.index(url_print) if url_print in urls else None
        caixa = (
            _caixa(auditoria, a.get("pagina_url", ""), a.get("problema", "")) if indice is not None else None
        )
        saida.append(
            EvidenciaOut(
                numero=i,
                titulo=a["titulo"],
                pagina=a["pagina"],
                print_indice=indice,
                caixa=caixa,
                alt=f"Print da página {a['pagina']} de {dominio or 'site'}"
                + (f", com o problema {i} destacado por uma caixa numerada." if caixa else "."),
            )
        )
    return saida


def _empresa_ou_404(db: Session, empresa_id: uuid.UUID) -> Empresa:
    empresa = db.get(Empresa, empresa_id)
    if empresa is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Empresa não encontrada.")
    return empresa


@router.get("/empresas/{empresa_id}/ficha", response_model=FichaOut)
def ficha(
    empresa_id: uuid.UUID,
    db: Session = Depends(get_db),
    armazenamento: Armazenamento = Depends(get_armazenamento),
    user: Usuario = Depends(get_current_user),
) -> FichaOut:
    empresa = _empresa_ou_404(db, empresa_id)
    auditoria = _ultima_auditoria(db, empresa_id)
    eventos = db.scalars(
        select(Evento).where(Evento.empresa_id == empresa_id).order_by(Evento.ocorrido_em)
    ).all()
    analisada = auditoria is not None and auditoria.nota is not None
    return FichaOut(
        empresa=EmpresaFichaOut.model_validate(empresa),
        dossie=_dossie(db, empresa_id),
        auditoria=_resumo_auditoria(auditoria) if auditoria else None,
        evidencias=_evidencias(auditoria, empresa.dominio),
        qualificacao=ultima_qualificacao(db, empresa_id),
        decisores=_decisores(db, empresa_id, user.papel),
        relatorio_disponivel=analisada
        and armazenamento.existe(chave_relatorio(empresa_id, auditoria.id, "pdf")),
        eventos=[
            EventoOut(
                id=e.id,
                tipo=e.tipo,
                origem=e.origem,
                ocorrido_em=e.ocorrido_em,
                mensagem=str((e.dados_json or {}).get("mensagem", e.tipo)),
            )
            for e in eventos
        ],
    )


def _arquivo_do_relatorio(
    db: Session, armazenamento: Armazenamento, empresa_id: uuid.UUID, ext: str
) -> bytes:
    _empresa_ou_404(db, empresa_id)
    auditoria = _ultima_auditoria(db, empresa_id)
    dados = armazenamento.ler(chave_relatorio(empresa_id, auditoria.id, ext)) if auditoria else None
    if dados is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="O relatório ainda não foi gerado.")
    return dados


@router.get("/empresas/{empresa_id}/relatorio.pdf")
def relatorio_pdf(
    empresa_id: uuid.UUID,
    db: Session = Depends(get_db),
    armazenamento: Armazenamento = Depends(get_armazenamento),
    _: Usuario = Depends(get_current_user),
) -> Response:
    empresa = _empresa_ou_404(db, empresa_id)
    nome = (empresa.dominio or "empresa").replace(".", "-")
    return Response(
        _arquivo_do_relatorio(db, armazenamento, empresa_id, "pdf"),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="diagnostico-acessibilidade-{nome}.pdf"'},
    )


@router.get("/empresas/{empresa_id}/relatorio")
def relatorio_web(
    empresa_id: uuid.UUID,
    db: Session = Depends(get_db),
    armazenamento: Armazenamento = Depends(get_armazenamento),
    _: Usuario = Depends(get_current_user),
) -> Response:
    """Versão web do relatório (o mesmo HTML do PDF, com imagens e fontes embutidas)."""
    return Response(
        _arquivo_do_relatorio(db, armazenamento, empresa_id, "html"), media_type="text/html; charset=utf-8"
    )


@router.get("/empresas/{empresa_id}/prints/{indice}")
def print_da_auditoria(
    empresa_id: uuid.UUID,
    indice: int,
    db: Session = Depends(get_db),
    armazenamento: Armazenamento = Depends(get_armazenamento),
    _: Usuario = Depends(get_current_user),
) -> Response:
    _empresa_ou_404(db, empresa_id)
    auditoria = _ultima_auditoria(db, empresa_id)
    urls = list(auditoria.artefatos_urls or []) if auditoria else []
    chave = chave_de(urls[indice]) if 0 <= indice < len(urls) else None
    dados = armazenamento.ler(chave) if chave else None
    if dados is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Print não encontrado.")
    return Response(dados, media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})
