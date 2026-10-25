"""Geração e guarda do mini-relatório (CONSTITUICAO §8.3). Chamado ao fim da análise com IA e pelo comando
`python -m slp_workers.cli relatorios --faltantes`. Não usa IA.

O PDF e a versão web ficam no MinIO, em caminho derivado da auditoria (sem coluna nova no banco):
`relatorios/<empresa>/<auditoria>.pdf` e `.html`. A API lê do mesmo caminho.
"""

import asyncio
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Engine, func, select

from slp_workers.audit.artefatos import Armazenamento
from slp_workers.db import auditorias, empresas, registrar_evento
from slp_workers.documents.relatorio import DadosRelatorio, gerar_html, gerar_pdf

log = logging.getLogger("slp_workers.relatorio")


def chave_relatorio(empresa_id: uuid.UUID | str, auditoria_id: uuid.UUID | str, extensao: str) -> str:
    return f"relatorios/{empresa_id}/{auditoria_id}.{extensao}"


def _carregar(engine: Engine, empresa_id: uuid.UUID) -> tuple[Any, Any, float | None, int]:
    with engine.connect() as conn:
        empresa = conn.execute(select(empresas).where(empresas.c.id == empresa_id)).first()
        auditoria = conn.execute(
            select(auditorias)
            .where(auditorias.c.empresa_id == empresa_id, auditorias.c.nota.is_not(None))
            .order_by(auditorias.c.criado_em.desc())
            .limit(1)
        ).first()
        media, quantidade = None, 0
        if empresa is not None and empresa.setor:
            # Média do setor na base própria, sem contar a empresa do relatório (§8.3, item 1)
            ultima_por_empresa = (
                select(auditorias.c.empresa_id, func.max(auditorias.c.criado_em).label("criado_em"))
                .where(auditorias.c.nota.is_not(None))
                .group_by(auditorias.c.empresa_id)
                .subquery()
            )
            media, quantidade = conn.execute(
                select(func.avg(auditorias.c.nota), func.count())
                .join(
                    ultima_por_empresa,
                    (auditorias.c.empresa_id == ultima_por_empresa.c.empresa_id)
                    & (auditorias.c.criado_em == ultima_por_empresa.c.criado_em),
                )
                .join(empresas, empresas.c.id == auditorias.c.empresa_id)
                .where(empresas.c.setor == empresa.setor, empresas.c.id != empresa_id)
            ).one()
    return empresa, auditoria, (float(media) if media is not None else None), int(quantidade or 0)


async def gerar_e_salvar(engine: Engine, armazenamento: Armazenamento, empresa_id: uuid.UUID) -> str | None:
    """Gera o relatório da última auditoria analisada. Devolve o caminho do PDF ou None se não há análise."""
    empresa, auditoria, media, quantidade = await asyncio.to_thread(_carregar, engine, empresa_id)
    if empresa is None or auditoria is None or not isinstance(auditoria.achados_json, dict):
        return None

    prints: dict[str, bytes] = {}
    for achado in auditoria.achados_json.get("top3_para_leigos", []):
        url = (achado.get("evidencia") or {}).get("print")
        if url and url not in prints:
            dados = await armazenamento.ler(url)
            if dados:
                prints[url] = dados

    dados = DadosRelatorio(
        nome=empresa.nome,
        dominio=empresa.dominio or "",
        setor=empresa.setor,
        nota=auditoria.nota,
        analise=auditoria.achados_json,
        paginas=auditoria.paginas_json or [],
        prints=prints,
        media_setor=media,
        sites_no_setor=quantidade,
        gerado_em=datetime.now(UTC),
    )
    html = gerar_html(dados)
    pdf = await asyncio.to_thread(gerar_pdf, html)
    await armazenamento.salvar(
        chave_relatorio(empresa_id, auditoria.id, "html"), html.encode(), "text/html; charset=utf-8"
    )
    return await armazenamento.salvar(
        chave_relatorio(empresa_id, auditoria.id, "pdf"), pdf, "application/pdf"
    )


async def gerar_com_evento(
    engine: Engine, armazenamento: Armazenamento | None, empresa_id: uuid.UUID
) -> bool:
    """Ao fim da análise: falha no relatório não desfaz a análise; fica registrada na linha do tempo."""

    async def evento(tipo: str, mensagem: str) -> None:
        await asyncio.to_thread(registrar_evento, engine, empresa_id, tipo, mensagem)

    if armazenamento is None:
        return False
    try:
        caminho = await gerar_e_salvar(engine, armazenamento, empresa_id)
    except Exception as exc:  # noqa: BLE001 — PDF, fontes ou MinIO: a linha do tempo explica
        log.exception("relatório de %s falhou", empresa_id)
        await evento("relatorio_falhou", f"Não foi possível gerar o relatório ({type(exc).__name__}).")
        return False
    if caminho is None:
        return False
    await evento("relatorio_pronto", "Mini-relatório em PDF pronto para baixar na ficha da empresa.")
    return True
