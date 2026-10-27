"""Mapeamento de colunas de um lote (CONSTITUICAO §7.2, entrada 2). Enfileirado pela API quando as regras
pelo nome do cabeçalho não acham a coluna da empresa ou a do site.

Respeita o disjuntor de custo de IA: atingido o teto, fica com o mapeamento das regras e avisa na prévia.
Qualquer falha também cai nas regras: o vendedor sempre pode ajustar as colunas antes de confirmar.
"""

import asyncio
import logging
import uuid

from sqlalchemy import select, update

from slp_workers.agents import mapeador_colunas
from slp_workers.db import lotes, registrar_acao
from slp_workers.llm import ErroIA
from slp_workers.orchestrator.budget import verificar_disjuntor
from slp_workers.settings import get_config

log = logging.getLogger("slp_workers.lotes")

AVISO_SEM_IA = "A identificação automática das colunas não foi possível agora. Confira as colunas abaixo."


def _carregar(engine, lote_id: uuid.UUID):
    with engine.connect() as conn:
        return conn.execute(select(lotes).where(lotes.c.id == lote_id)).first()


def _gravar(engine, lote_id: uuid.UUID, mapa: dict | None, aviso: str | None) -> None:
    valores: dict = {"status": "aguardando_confirmacao"}
    if mapa is not None:
        valores.update(mapeamento_json=mapa, mapeamento_origem="ia")
    if aviso:
        valores["resumo_json"] = {"aviso_mapeamento": aviso}
    with engine.begin() as conn:
        # Só sai de "mapeando": se o vendedor já ajustou ou cancelou, a IA não sobrescreve
        conn.execute(
            update(lotes).where(lotes.c.id == lote_id, lotes.c.status == "mapeando").values(**valores)
        )


async def mapear_colunas_lote(ctx: dict, lote_id: str, colunas: list[dict]) -> str:
    engine = ctx["engine"]
    lid = uuid.UUID(lote_id)
    lote = await asyncio.to_thread(_carregar, engine, lid)
    if lote is None or lote.status != "mapeando":
        return "ignorado"
    if (await asyncio.to_thread(verificar_disjuntor, engine)).atingido:
        await asyncio.to_thread(_gravar, engine, lid, None, AVISO_SEM_IA)
        return "sem_orcamento"
    try:
        validado, saida, consumo, entrada_hash, descartados = await mapeador_colunas.mapear(
            ctx["ia"], ctx.get("config") or get_config(), colunas
        )
    except ErroIA as exc:
        log.warning("mapeamento de colunas do lote %s falhou: %s", lote_id, exc)
        await asyncio.to_thread(_gravar, engine, lid, None, AVISO_SEM_IA)
        return "falhou"
    await asyncio.to_thread(
        registrar_acao,
        engine,
        agente="mapeador_colunas",
        empresa_id=None,
        entrada_hash=entrada_hash,
        saida={**saida.model_dump(), "lote_id": lote_id, "descartados": descartados},
        raciocinio=saida.raciocinio_resumido,
        modelo=consumo.modelo,
        tokens_in=consumo.tokens_in,
        tokens_out=consumo.tokens_out,
        custo_brl=consumo.custo_brl,
        duracao_ms=consumo.duracao_ms,
    )
    final = mapeador_colunas.combinar(lote.mapeamento_json or {}, validado)
    await asyncio.to_thread(_gravar, engine, lid, final, None)
    return "mapeado"
