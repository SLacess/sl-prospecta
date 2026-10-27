"""Prospecção em lote por planilha (CONSTITUICAO §7.2, entrada 2; §12.1, Painel de Prospecção).

Fluxo: envio → mapeamento de colunas (regras; o que faltar, IA no worker) → prévia com deduplicação por
domínio e CNPJ → confirmação humana → empresas na fila → progresso. As linhas da planilha ficam guardadas
só até a confirmação ou o cancelamento (coleta mínima, §15.1).
"""

import math
import re
import unicodedata
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import get_current_user, require_role
from app.models import Contato, Empresa, EstadoProspect, Evento, Lote, Papel, Usuario
from app.planilha import (
    CAMPOS,
    MAX_BYTES,
    ROTULO_CAMPO,
    LinhaInterpretada,
    PlanilhaInvalida,
    amostra_para_ia,
    classificar,
    ler_planilha,
    mapeamento_suficiente,
    mapear_por_regras,
    validar_mapeamento,
)
from app.queue import Fila, FilaIndisponivel, get_fila
from app.timeline import registrar_evento

router = APIRouter(tags=["lotes"])

# Estimativa por empresa nova (média do que a produção gastou na Fase 1 e nas Tarefas 1 e 2)
CUSTO_IA_POR_EMPRESA = Decimal("1.00")
CREDITOS_POR_EMPRESA = 4
PREVIA_LINHAS = 10
EM_ANDAMENTO = {EstadoProspect.novo, EstadoProspect.pesquisando, EstadoProspect.auditando}
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
ROTULO_STATUS = {
    "mapeando": "Identificando as colunas",
    "aguardando_confirmacao": "Aguardando sua confirmação",
    "processando": "Em processamento",
    "concluido": "Concluído",
    "cancelado": "Cancelado",
}
ROTULO_SITUACAO = {
    "nova": "Nova",
    "ja_cadastrada": "Já cadastrada",
    "repetida": "Repetida na planilha",
    "invalida": "Inválida",
}
AREAS_POR_CARGO = {
    "TI": r"\b(ti|it|tecnologia|technology|cio|cto|sistemas?)\b",
    "RH": r"\b(rh|hr|recursos humanos|pessoas|people|gente)\b",
    "D&I": r"(diversidade|diversity|inclusao|inclusion|acessibilidade)",
    "Marketing": r"\b(marketing|cmo|comunicacao|marca|brand)\b",
    "ESG": r"\b(esg|sustentabilidade|sustainability)\b",
    "Compliance": r"\b(compliance|juridic[oa]|legal|riscos?|ouvidoria)\b",
}
WEBMAIL = frozenset(
    "gmail.com hotmail.com outlook.com live.com yahoo.com yahoo.com.br icloud.com bol.com.br uol.com.br "
    "terra.com.br ig.com.br globo.com".split()
)


# --- Esquemas -------------------------------------------------------------------


class ColunaOut(BaseModel):
    indice: int
    cabecalho: str


class CampoOut(BaseModel):
    campo: str
    rotulo: str
    coluna: int | None


class LinhaPreviaOut(BaseModel):
    numero: int
    empresa: str | None
    site: str | None
    cnpj: str | None
    situacao: Literal["nova", "ja_cadastrada", "repetida", "invalida"]
    rotulo_situacao: str
    motivo: str | None
    avisos: list[str]


class ResumoOut(BaseModel):
    total: int
    novas: int
    ja_cadastradas: int
    repetidas: int
    invalidas: int
    com_avisos: int


class EstimativaOut(BaseModel):
    custo_ia_brl: Decimal
    creditos_apollo: int
    dias_pelos_tetos: int
    texto: str


class EtapaOut(BaseModel):
    chave: str
    rotulo: str
    quantidade: int


class EmpresaLoteOut(BaseModel):
    id: uuid.UUID
    nome: str
    dominio: str | None
    estado: str
    score: int | None
    problema: str | None


class ProgressoOut(BaseModel):
    total: int
    finalizadas: int
    percentual: int
    etapas: list[EtapaOut]
    texto: str


class LoteOut(BaseModel):
    id: uuid.UUID
    nome_arquivo: str
    status: str
    rotulo_status: str
    total_linhas: int
    criado_em: datetime
    confirmado_em: datetime | None


class LoteDetalheOut(LoteOut):
    colunas: list[ColunaOut]
    campos: list[CampoOut]
    mapeamento_origem: str
    aviso_mapeamento: str | None
    resumo: ResumoOut | None
    previa: list[LinhaPreviaOut]
    estimativa: EstimativaOut | None
    progresso: ProgressoOut | None
    empresas: list[EmpresaLoteOut]
    linhas_ignoradas: list[dict]


class MapeamentoIn(BaseModel):
    mapeamento: dict[str, int | None]


# --- Apoio ----------------------------------------------------------------------


def _lote_ou_404(db: Session, lote_id: uuid.UUID) -> Lote:
    lote = db.get(Lote, lote_id)
    if lote is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lote não encontrado.")
    return lote


def _exigir_status(lote: Lote, *validos: str) -> None:
    if lote.status not in validos:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Este lote está {ROTULO_STATUS.get(lote.status, lote.status).lower()}.",
        )


def _existentes(db: Session, linhas: list[list[str]], mapa: dict) -> tuple[dict, dict]:
    """Empresas já no banco com os domínios e CNPJs da planilha (uma consulta cada, não uma por linha)."""
    from app.planilha import interpretar_linha

    interpretadas = [
        interpretar_linha(i, linha, mapa) for i, linha in enumerate(linhas, start=2) if any(linha)
    ]
    dominios = {r.dominio for r in interpretadas if r.dominio}
    cnpjs = {r.cnpj for r in interpretadas if r.cnpj}
    por_dominio = (
        {
            d: (str(i), n)
            for i, n, d in db.execute(
                select(Empresa.id, Empresa.nome, Empresa.dominio).where(Empresa.dominio.in_(dominios))
            )
        }
        if dominios
        else {}
    )
    por_cnpj = (
        {
            c: (str(i), n)
            for i, n, c in db.execute(
                select(Empresa.id, Empresa.nome, Empresa.cnpj).where(Empresa.cnpj.in_(cnpjs))
            )
        }
        if cnpjs
        else {}
    )
    return por_dominio, por_cnpj


def _classificar(db: Session, lote: Lote) -> list[LinhaInterpretada]:
    linhas = lote.linhas_json or []
    por_dominio, por_cnpj = _existentes(db, linhas, lote.mapeamento_json)
    return classificar(linhas, lote.mapeamento_json, por_dominio, por_cnpj, lote.linha_cabecalho)


def _resumo(classificadas: list[LinhaInterpretada]) -> ResumoOut:
    def conta(s: str) -> int:
        return sum(1 for r in classificadas if r.situacao == s)

    return ResumoOut(
        total=len(classificadas),
        novas=conta("nova"),
        ja_cadastradas=conta("ja_cadastrada"),
        repetidas=conta("repetida"),
        invalidas=conta("invalida"),
        com_avisos=sum(1 for r in classificadas if r.avisos and r.situacao != "invalida"),
    )


def _estimativa(novas: int) -> EstimativaOut:
    s = get_settings()
    custo = (CUSTO_IA_POR_EMPRESA * novas).quantize(Decimal("0.01"))
    creditos = CREDITOS_POR_EMPRESA * novas
    dias = max(
        math.ceil(custo / s.daily_ai_budget_brl) if s.daily_ai_budget_brl else 1,
        math.ceil(creditos / s.apollo_daily_credit_cap) if s.apollo_daily_credit_cap else 1,
        1,
    )

    def brl(v: Decimal) -> str:
        return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    texto = (
        f"Estimativa para {novas} empresa(s) nova(s): cerca de {brl(custo)} de IA e até {creditos} "
        "crédito(s) "
        f"do Apollo. Com os tetos diários atuais ({brl(s.daily_ai_budget_brl)} de IA e "
        f"{s.apollo_daily_credit_cap} créditos), o lote leva cerca de {dias} dia(s); a fila segue sozinha."
    )
    return EstimativaOut(custo_ia_brl=custo, creditos_apollo=creditos, dias_pelos_tetos=dias, texto=texto)


def _area_do_cargo(cargo: str | None) -> str:
    texto = unicodedata.normalize("NFKD", cargo or "").encode("ascii", "ignore").decode().lower()
    for area, padrao in AREAS_POR_CARGO.items():
        if re.search(padrao, texto):
            return area
    return "Não informada"


def _status_exibido(db: Session, lote: Lote) -> str:
    if lote.status != "processando":
        return lote.status
    em_andamento = db.scalar(
        select(func.count()).where(Empresa.lote_id == lote.id, Empresa.estado.in_(EM_ANDAMENTO))
    )
    return "processando" if em_andamento else "concluido"


def _lote_out(db: Session, lote: Lote) -> LoteOut:
    st = _status_exibido(db, lote)
    return LoteOut(
        id=lote.id,
        nome_arquivo=lote.nome_arquivo,
        status=st,
        rotulo_status=ROTULO_STATUS[st],
        total_linhas=lote.total_linhas,
        criado_em=lote.criado_em,
        confirmado_em=lote.confirmado_em,
    )


def _problemas(db: Session, ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
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


def _progresso(db: Session, lote: Lote) -> tuple[ProgressoOut, list[EmpresaLoteOut]]:
    empresas = db.scalars(select(Empresa).where(Empresa.lote_id == lote.id).order_by(Empresa.nome)).all()
    problemas = _problemas(db, [e.id for e in empresas])
    grupos = {
        "na_fila": ("Na fila", lambda e: e.estado == EstadoProspect.novo),
        "pesquisando": ("Pesquisando", lambda e: e.estado == EstadoProspect.pesquisando),
        "auditando": ("Auditando", lambda e: e.estado == EstadoProspect.auditando),
        "qualificadas": (
            "Qualificadas",
            lambda e: e.estado in (EstadoProspect.qualificando, EstadoProspect.mapeando_decisores),
        ),
        "com_decisores": ("Com decisores", lambda e: e.estado == EstadoProspect.preparando_abordagem),
        "com_problema": ("Precisam de atenção", None),
    }
    etapas = []
    for chave, (rotulo, teste) in grupos.items():
        if teste is None:
            qtd = sum(1 for e in empresas if e.id in problemas)
        else:
            qtd = sum(1 for e in empresas if e.id not in problemas and teste(e))
        etapas.append(EtapaOut(chave=chave, rotulo=rotulo, quantidade=qtd))
    total = len(empresas)
    finalizadas = sum(1 for e in empresas if e.estado not in EM_ANDAMENTO or e.id in problemas)
    pct = round(finalizadas * 100 / total) if total else 100
    texto = f"{finalizadas} de {total} empresa(s) já passaram da pesquisa e da auditoria ({pct}%)."
    lista = [
        EmpresaLoteOut(
            id=e.id,
            nome=e.nome,
            dominio=e.dominio,
            estado=e.estado.value,
            score=e.score,
            problema=problemas.get(e.id),
        )
        for e in empresas
    ]
    return ProgressoOut(
        total=total, finalizadas=finalizadas, percentual=pct, etapas=etapas, texto=texto
    ), lista


def _detalhe(db: Session, lote: Lote) -> LoteDetalheOut:
    base = _lote_out(db, lote)
    colunas = [ColunaOut(indice=i, cabecalho=c) for i, c in enumerate(lote.cabecalhos_json or [])]
    campos = [
        CampoOut(campo=c, rotulo=ROTULO_CAMPO[c], coluna=(lote.mapeamento_json or {}).get(c)) for c in CAMPOS
    ]
    resumo = previa = estimativa = progresso = None
    empresas: list[EmpresaLoteOut] = []
    ignoradas: list[dict] = []
    if lote.status == "aguardando_confirmacao" and lote.linhas_json is not None:
        classificadas = _classificar(db, lote)
        resumo = _resumo(classificadas)
        previa = [
            LinhaPreviaOut(
                numero=r.numero,
                empresa=r.nome,
                site=r.dominio,
                cnpj=r.cnpj,
                situacao=r.situacao,
                rotulo_situacao=ROTULO_SITUACAO[r.situacao],
                motivo=r.motivo,
                avisos=r.avisos,
            )
            for r in classificadas[:PREVIA_LINHAS]
        ]
        estimativa = _estimativa(resumo.novas)
    elif lote.resumo_json:
        resumo = ResumoOut.model_validate(lote.resumo_json["contagem"])
        ignoradas = lote.resumo_json.get("ignoradas", [])
    if lote.status == "processando":
        progresso, empresas = _progresso(db, lote)
    return LoteDetalheOut(
        **base.model_dump(),
        colunas=colunas,
        campos=campos,
        mapeamento_origem=lote.mapeamento_origem,
        aviso_mapeamento=(lote.resumo_json or {}).get("aviso_mapeamento")
        if lote.status != "processando"
        else None,
        resumo=resumo,
        previa=previa or [],
        estimativa=estimativa,
        progresso=progresso,
        empresas=empresas,
        linhas_ignoradas=ignoradas,
    )


# --- Rotas ----------------------------------------------------------------------


@router.post("/lotes", response_model=LoteDetalheOut, status_code=status.HTTP_201_CREATED)
async def enviar_planilha(
    arquivo: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: Usuario = Depends(require_role(Papel.admin, Papel.vendedor)),
    fila: Fila = Depends(get_fila),
) -> LoteDetalheOut:
    dados = await arquivo.read(MAX_BYTES + 1)
    nome = (arquivo.filename or "planilha").rsplit("/", 1)[-1].rsplit("\\", 1)[-1][:255]
    try:
        planilha = await run_in_threadpool(ler_planilha, nome, dados)
    except PlanilhaInvalida as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from None

    mapa = mapear_por_regras(planilha)
    precisa_ia = not mapeamento_suficiente(mapa) or mapa.get("empresa") is None or mapa.get("site") is None
    lote = Lote(
        nome_arquivo=nome,
        criado_por=user.id,
        status="mapeando" if precisa_ia else "aguardando_confirmacao",
        total_linhas=planilha.total,
        linha_cabecalho=planilha.linha_cabecalho,
        cabecalhos_json=planilha.cabecalhos,
        linhas_json=planilha.linhas,
        mapeamento_json=mapa,
        mapeamento_origem="regras",
    )
    db.add(lote)
    db.commit()

    if precisa_ia:
        try:
            await fila.enfileirar_mapeamento_colunas(
                lote.id, amostra_para_ia(planilha.cabecalhos, planilha.linhas)
            )
        except FilaIndisponivel:
            # Sem fila, segue com o que as regras acharam; o vendedor ajusta na prévia
            lote.status = "aguardando_confirmacao"
            lote.resumo_json = {
                "aviso_mapeamento": "A identificação automática das colunas não está disponível agora. "
                "Confira as colunas abaixo."
            }
            db.commit()
    return _detalhe(db, lote)


@router.get("/lotes", response_model=list[LoteOut])
def listar_lotes(db: Session = Depends(get_db), _: Usuario = Depends(get_current_user)) -> list[LoteOut]:
    lotes = db.scalars(select(Lote).order_by(Lote.criado_em.desc()).limit(50)).all()
    return [_lote_out(db, lote) for lote in lotes]


@router.get("/lotes/{lote_id}", response_model=LoteDetalheOut)
def ver_lote(
    lote_id: uuid.UUID, db: Session = Depends(get_db), _: Usuario = Depends(get_current_user)
) -> LoteDetalheOut:
    return _detalhe(db, _lote_ou_404(db, lote_id))


@router.put("/lotes/{lote_id}/mapeamento", response_model=LoteDetalheOut)
def ajustar_mapeamento(
    lote_id: uuid.UUID,
    dados: MapeamentoIn,
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_role(Papel.admin, Papel.vendedor)),
) -> LoteDetalheOut:
    lote = _lote_ou_404(db, lote_id)
    _exigir_status(lote, "aguardando_confirmacao", "mapeando")
    desconhecidos = set(dados.mapeamento) - set(CAMPOS)
    if desconhecidos:
        raise HTTPException(
            status_code=422, detail=f"Campo desconhecido: {', '.join(sorted(desconhecidos))}."
        )
    try:
        lote.mapeamento_json = validar_mapeamento(dados.mapeamento, len(lote.cabecalhos_json or []))
    except PlanilhaInvalida as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from None
    lote.mapeamento_origem = "humano"
    lote.status = "aguardando_confirmacao"
    db.commit()
    return _detalhe(db, lote)


def _gravar_confirmacao(db: Session, lote: Lote, user: Usuario) -> tuple[list[uuid.UUID], list[dict]]:
    classificadas = _classificar(db, lote)
    resumo = _resumo(classificadas)
    novas: list[uuid.UUID] = []
    ignoradas: list[dict] = []
    for r in classificadas:
        if r.situacao == "nova":
            empresa = Empresa(
                nome=r.nome or r.dominio,
                dominio=r.dominio,
                cnpj=r.cnpj,
                cidade=r.cidade,
                uf=r.uf,
                fonte="lote",
                estado=EstadoProspect.novo,
                responsavel_id=user.id,
                lote_id=lote.id,
            )
            db.add(empresa)
            db.flush()
            registrar_evento(
                db,
                empresa.id,
                "entrada_recebida",
                "humano",
                f"Empresa cadastrada pela planilha {lote.nome_arquivo} (linha {r.numero})."
                + (" O site oficial será identificado na pesquisa." if not r.dominio else ""),
                lote_id=str(lote.id),
                linha=r.numero,
                usuario_id=str(user.id),
            )
            _contato_da_planilha(db, empresa.id, r)
            novas.append(empresa.id)
        elif r.situacao == "ja_cadastrada" and r.empresa_existente_id:
            registrar_evento(
                db,
                uuid.UUID(r.empresa_existente_id),
                "entrada_duplicada",
                "humano",
                f"Esta empresa também veio na planilha {lote.nome_arquivo} (linha {r.numero}); "
                "não foi cadastrada de novo.",
                lote_id=str(lote.id),
                linha=r.numero,
                usuario_id=str(user.id),
            )
            ignoradas.append({"linha": r.numero, "motivo": r.motivo})
        else:
            ignoradas.append({"linha": r.numero, "motivo": r.motivo})
    lote.status = "processando"
    lote.confirmado_em = datetime.now(UTC)
    lote.linhas_json = None  # coleta mínima: depois da confirmação, só o resumo
    lote.resumo_json = {"contagem": resumo.model_dump(), "ignoradas": ignoradas}
    db.commit()
    return novas, ignoradas


def _contato_da_planilha(db: Session, empresa_id: uuid.UUID, r: LinhaInterpretada) -> None:
    """Contato que veio na planilha: guardado como não verificado até o Apollo confirmar o e-mail."""
    if not r.contato_nome and not r.contato_email:
        return
    email = r.contato_email
    if email and email.rsplit("@", 1)[-1] in WEBMAIL:
        email = None  # e-mail pessoal não é guardado (§15.1)
    db.add(
        Contato(
            empresa_id=empresa_id,
            nome=(r.contato_nome or (email or "").split("@")[0] or "Contato da planilha")[:200],
            cargo=r.contato_cargo,
            area=_area_do_cargo(r.contato_cargo),
            email=email,
            email_status="nao_verificado" if email else "sem_email",
            fonte="planilha",
        )
    )


@router.post("/lotes/{lote_id}/confirmar", response_model=LoteDetalheOut)
async def confirmar_lote(
    lote_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: Usuario = Depends(require_role(Papel.admin, Papel.vendedor)),
    fila: Fila = Depends(get_fila),
) -> LoteDetalheOut:
    lote = _lote_ou_404(db, lote_id)
    _exigir_status(lote, "aguardando_confirmacao")
    if not mapeamento_suficiente(lote.mapeamento_json or {}):
        raise HTTPException(status_code=422, detail="Escolha pelo menos a coluna da empresa ou a do site.")
    novas, _ = await run_in_threadpool(_gravar_confirmacao, db, lote, user)

    sem_fila = 0
    for empresa_id in novas:
        try:
            if await fila.enfileirar_processamento(empresa_id):
                registrar_evento(
                    db, empresa_id, "enfileirado", "sistema", "Empresa na fila de processamento."
                )
        except FilaIndisponivel:
            sem_fila += 1
            registrar_evento(
                db,
                empresa_id,
                "falha_enfileirar",
                "sistema",
                "Não foi possível colocar a empresa na fila de processamento.",
            )
    db.commit()
    if sem_fila:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"O lote foi registrado, mas {sem_fila} empresa(s) não entraram na fila. "
            "Use 'retomar' no worker quando a fila voltar.",
        )
    return _detalhe(db, lote)


@router.post("/lotes/{lote_id}/cancelar", response_model=LoteDetalheOut)
def cancelar_lote(
    lote_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_role(Papel.admin, Papel.vendedor)),
) -> LoteDetalheOut:
    lote = _lote_ou_404(db, lote_id)
    _exigir_status(lote, "mapeando", "aguardando_confirmacao")
    lote.status = "cancelado"
    lote.linhas_json = None
    db.commit()
    return _detalhe(db, lote)
