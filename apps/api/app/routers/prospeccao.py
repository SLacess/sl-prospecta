"""Entrada de prospects, confirmação do site e andamento (CONSTITUICAO §7.2 e §12.1, tela 1)."""

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
from app.domain import Alvo, EntradaInvalida, interpretar_entrada, normalizar_dominio
from app.models import Auditoria, Dossie, Empresa, EstadoProspect, Evento, Papel, Usuario
from app.queue import Fila, FilaIndisponivel, get_fila
from app.timeline import registrar_evento

router = APIRouter(tags=["prospecção"])

LIMITE_EVENTOS = 200
# Estados em que o orquestrador ainda tem trabalho de pesquisa a fazer (Tarefa 2)
ESTADOS_EM_PESQUISA = (EstadoProspect.novo, EstadoProspect.pesquisando)
# Estados em que o orquestrador ainda tem trabalho a fazer na Fase 1 (pesquisa, auditoria e análise com IA)
ESTADOS_EM_PROCESSAMENTO = (*ESTADOS_EM_PESQUISA, EstadoProspect.auditando)


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


class DossieResumoOut(BaseModel):
    versao: int
    setor: str | None
    resumo: list[str]
    criado_em: datetime


class CandidatoDominioOut(BaseModel):
    dominio: str
    nome_oficial: str
    evidencia_url: str


class ConfirmacaoDominioOut(BaseModel):
    mensagem: str
    candidatos: list[CandidatoDominioOut]


class PaginaAuditadaOut(BaseModel):
    url: str
    status: str
    erro: str | None = None
    problemas: int = 0
    armadilha_de_foco: bool = False
    link_pular_conteudo: bool | None = None
    sem_indicador_de_foco: int = 0
    rolagem_horizontal_320: bool | None = None


class AchadoOut(BaseModel):
    titulo: str
    impacto_humano: str
    quem_e_afetado: list[str]
    criterio_wcag: str
    pagina: str
    trecho_html: str | None


class IndicioVisualOut(BaseModel):
    tipo: str
    descricao: str
    pagina: str


class AnaliseOut(BaseModel):
    """JSON do §8.2 sem os endereços dos prints, que continuam privados até a Tarefa 5."""

    top3_para_leigos: list[AchadoOut]
    plugin_resolve_parcialmente: list[str]
    exige_ajuste_no_codigo: list[str]
    indicios_visuais: list[IndicioVisualOut]
    observacao_honestidade: str


class AuditoriaResumoOut(BaseModel):
    criado_em: datetime
    nota: int | None
    totais: dict[str, int]
    plugins: list[str]
    paginas: list[PaginaAuditadaOut]
    analise: AnaliseOut | None


class EmpresaDetalheOut(EmpresaOut):
    eventos: list[EventoOut]
    dossie: DossieResumoOut | None
    auditoria: AuditoriaResumoOut | None
    confirmacao_dominio: ConfirmacaoDominioOut | None


class DominioIn(BaseModel):
    dominio: str = Field(max_length=500, description="Endereço do site oficial confirmado pelo vendedor")


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


def _ultimo_dossie(db: Session, empresa_id: uuid.UUID) -> Dossie | None:
    return db.scalar(
        select(Dossie).where(Dossie.empresa_id == empresa_id).order_by(Dossie.versao.desc()).limit(1)
    )


def _ultima_auditoria(db: Session, empresa_id: uuid.UUID) -> Auditoria | None:
    consulta = select(Auditoria).where(Auditoria.empresa_id == empresa_id)
    return db.scalar(consulta.order_by(Auditoria.criado_em.desc()).limit(1))


def _precisa_processamento(db: Session, empresa: Empresa) -> bool:
    """Ainda falta pesquisa, auditoria técnica ou análise com IA: o orquestrador decide qual etapa retomar.

    A análise com IA tira a empresa de AUDITANDO, então basta olhar o estado.
    """
    return empresa.estado in ESTADOS_EM_PROCESSAMENTO


def _resumo_auditoria(auditoria: Auditoria) -> AuditoriaResumoOut:
    paginas = []
    plugins: set[str] = set()
    for p in auditoria.paginas_json or []:
        if p.get("status") != "ok":
            paginas.append(
                PaginaAuditadaOut(url=p.get("url", ""), status=p.get("status", "erro"), erro=p.get("erro"))
            )
            continue
        plugins.update(p.get("plugins", []))
        teclado = p.get("teclado", {})
        paginas.append(PaginaAuditadaOut(
            url=p["url"], status="ok", problemas=len(p.get("axe", {}).get("violacoes", [])),
            armadilha_de_foco=bool(teclado.get("armadilha_de_foco")),
            link_pular_conteudo=teclado.get("link_pular_conteudo"),
            sem_indicador_de_foco=teclado.get("sem_indicador_aparente", 0),
            rolagem_horizontal_320=p.get("responsivo_320", {}).get("rolagem_horizontal"),
        ))
    totais = {k: int(v) for k, v in (auditoria.totais_json or {}).items() if isinstance(v, int)}
    bruto = auditoria.achados_json if isinstance(auditoria.achados_json, dict) else None
    analise = None
    if bruto:
        analise = AnaliseOut(
            top3_para_leigos=[
                AchadoOut(
                    titulo=a["titulo"], impacto_humano=a["impacto_humano"],
                    quem_e_afetado=a.get("quem_e_afetado", []), criterio_wcag=a["criterio_wcag"],
                    pagina=a["pagina"],
                    trecho_html=(a.get("evidencia") or {}).get("trecho_html"),
                )
                for a in bruto.get("top3_para_leigos", [])
            ],
            plugin_resolve_parcialmente=bruto.get("plugin_resolve_parcialmente", []),
            exige_ajuste_no_codigo=bruto.get("exige_ajuste_no_codigo", []),
            indicios_visuais=[IndicioVisualOut.model_validate(i) for i in bruto.get("indicios_visuais", [])],
            observacao_honestidade=bruto.get("observacao_honestidade", ""),
        )
    return AuditoriaResumoOut(
        criado_em=auditoria.criado_em, nota=auditoria.nota, totais=totais, plugins=sorted(plugins),
        paginas=paginas, analise=analise,
    )


async def _enfileirar(db: Session, fila: Fila, empresa_id: uuid.UUID) -> None:
    """Coloca a empresa na fila; se o Redis cair, registra a falha e responde 503."""
    try:
        novo_job = await fila.enfileirar_processamento(empresa_id)
    except FilaIndisponivel:
        await run_in_threadpool(
            _registrar_evento_sistema, db, empresa_id, "falha_enfileirar",
            "Não foi possível colocar a empresa na fila de processamento.",
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="A empresa foi registrada, mas a fila de processamento está indisponível. "
            "Tente de novo em alguns minutos.",
        ) from None
    if novo_job:
        await run_in_threadpool(
            _registrar_evento_sistema, db, empresa_id, "enfileirado", "Empresa na fila de processamento."
        )


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

    # Só entra na fila quem ainda não tem pesquisa e auditoria; o job_id fixo evita processamento em dobro
    na_fila = False
    if await run_in_threadpool(_precisa_processamento, db, empresa):
        await _enfileirar(db, fila, empresa.id)
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

    dossie = _ultimo_dossie(db, empresa.id)
    dossie_out = (
        DossieResumoOut(
            versao=dossie.versao, setor=(dossie.dados_json or {}).get("setor"),
            resumo=[linha for linha in (dossie.resumo or "").splitlines() if linha.strip()],
            criado_em=dossie.criado_em,
        )
        if dossie
        else None
    )

    # O site fica pendente enquanto o último evento for o pedido de confirmação do orquestrador
    confirmacao = None
    if empresa.dominio is None and recentes and recentes[0].tipo == "confirmacao_dominio":
        dados = recentes[0].dados_json or {}
        confirmacao = ConfirmacaoDominioOut(
            mensagem=str(dados.get("mensagem", "")),
            candidatos=[CandidatoDominioOut.model_validate(c) for c in dados.get("candidatos", [])],
        )

    return EmpresaDetalheOut(
        **EmpresaOut.model_validate(empresa).model_dump(), eventos=eventos, dossie=dossie_out,
        confirmacao_dominio=confirmacao,
        auditoria=_resumo_auditoria(auditoria) if (auditoria := _ultima_auditoria(db, empresa.id)) else None,
    )


def _confirmar_dominio(db: Session, empresa_id: uuid.UUID, texto: str, user: Usuario) -> Empresa:
    empresa = db.get(Empresa, empresa_id)
    if empresa is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Empresa não encontrada.")
    if empresa.dominio is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail=f"Esta empresa já tem o site {empresa.dominio}.")
    if empresa.estado not in ESTADOS_EM_PESQUISA:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="O site só pode ser confirmado durante a pesquisa.")
    try:
        dominio = normalizar_dominio(texto)
    except EntradaInvalida as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from None

    dono = db.scalar(select(Empresa).where(Empresa.dominio == dominio))
    if dono is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail=f"O site {dominio} já pertence à empresa {dono.nome}.")
    empresa.dominio = dominio
    registrar_evento(db, empresa.id, "dominio_confirmado", "humano",
                     f"Site oficial confirmado pelo vendedor: {dominio}.", usuario_id=str(user.id))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail=f"O site {dominio} acabou de ser cadastrado para outra empresa.") from None
    return empresa


@router.post("/empresas/{empresa_id}/dominio", response_model=EmpresaOut)
async def confirmar_dominio(
    empresa_id: uuid.UUID,
    dados: DominioIn,
    db: Session = Depends(get_db),
    user: Usuario = Depends(require_role(Papel.admin, Papel.vendedor)),
    fila: Fila = Depends(get_fila),
) -> EmpresaOut:
    """O vendedor confirma o site quando o Pesquisador não acha um único candidato claro (§7.2)."""
    empresa = await run_in_threadpool(_confirmar_dominio, db, empresa_id, dados.dominio, user)
    await _enfileirar(db, fila, empresa.id)
    return EmpresaOut.model_validate(empresa)
