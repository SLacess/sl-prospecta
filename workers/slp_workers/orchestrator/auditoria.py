"""Orquestração da auditoria técnica (CONSTITUICAO §7.3 Etapa 2 e §8). Roda no worker-audit.

Recebe a empresa em AUDITANDO, chama o motor (`slp_workers.audit.engine`) e grava o resultado bruto
em `auditorias`. Em seguida devolve a empresa à fila principal, onde o Auditor com IA dá a nota 0–100,
explica os achados para leigos (§8.2) e faz a passagem para QUALIFICANDO.
"""

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Engine, select

from slp_workers.audit.artefatos import Armazenamento
from slp_workers.audit.engine import Auditor, ResultadoAuditoria
from slp_workers.db import auditorias, empresas, registrar_evento
from slp_workers.settings import WorkerConfig, get_config
from slp_workers.web.fetcher import LeituraBloqueada
from slp_workers.web.ratelimit import Limitador
from slp_workers.web.safety import resolver_dns

log = logging.getLogger("slp_workers.auditoria")

AUDITANDO = "AUDITANDO"


def _enfileirador_principal(redis: Any) -> Callable[[uuid.UUID], Awaitable[bool]]:
    """A análise com IA roda no worker principal (fila padrão), pelo mesmo job do orquestrador."""

    async def enfileirar(empresa_id: uuid.UUID) -> bool:
        job = await redis.enqueue_job(
            "processar_empresa", str(empresa_id), _job_id=f"processar_empresa:{empresa_id}"
        )
        return job is not None

    return enfileirar


@dataclass
class DependenciasAuditoria:
    engine: Engine
    limitador: Limitador
    armazenamento: Armazenamento
    config: WorkerConfig
    auditor: Auditor
    enfileirar_analise: Callable[[uuid.UUID], Awaitable[bool]] | None = None

    @classmethod
    def do_ctx(cls, ctx: dict) -> "DependenciasAuditoria":
        config = ctx.get("config") or get_config()
        auditor = ctx.get("auditor") or Auditor(
            config, ctx["limitador"], ctx["armazenamento"], resolvedor=ctx.get("resolvedor", resolver_dns)
        )
        return cls(
            engine=ctx["engine"],
            limitador=ctx["limitador"],
            armazenamento=ctx["armazenamento"],
            config=config,
            auditor=auditor,
            enfileirar_analise=ctx.get("enfileirar_analise")
            or (_enfileirador_principal(ctx["redis"]) if "redis" in ctx else None),
        )


def _carregar(engine: Engine, empresa_id: uuid.UUID) -> Any:
    with engine.connect() as conn:
        empresa = conn.execute(select(empresas).where(empresas.c.id == empresa_id)).first()
        ja_auditada = conn.scalar(
            select(auditorias.c.id).where(auditorias.c.empresa_id == empresa_id).limit(1)
        )
    return empresa, ja_auditada is not None


def _gravar(engine: Engine, auditoria_id: uuid.UUID, empresa_id: uuid.UUID, r: ResultadoAuditoria) -> None:
    with engine.begin() as conn:
        conn.execute(
            auditorias.insert().values(
                id=auditoria_id,
                empresa_id=empresa_id,
                nota=None,
                totais_json=r.totais(),
                achados_json=[],
                paginas_json=r.paginas,
                artefatos_urls=r.artefatos,
                criado_em=datetime.now(UTC),
            )
        )


def mensagem_final(r: ResultadoAuditoria) -> str:
    t = r.totais()
    partes = [
        f"Auditoria técnica pronta: {t['paginas_auditadas']} página(s) testada(s);",
        f"problemas automáticos: {t['critico']} crítico(s), {t['grave']} grave(s), "
        f"{t['moderado']} moderado(s), {t['leve']} leve(s).",
    ]
    if r.plugins:
        partes.append(f"Plugin de acessibilidade detectado: {', '.join(r.plugins)}.")
    partes.append("Em seguida vem a análise com a nota e os achados explicados.")
    return " ".join(partes)


async def auditar_empresa(ctx: dict, empresa_id: str) -> str:
    deps = DependenciasAuditoria.do_ctx(ctx)
    eid = uuid.UUID(empresa_id)

    async def evento(tipo: str, mensagem: str, **dados: Any) -> None:
        await asyncio.to_thread(registrar_evento, deps.engine, eid, tipo, mensagem, **dados)

    empresa, ja_auditada = await asyncio.to_thread(_carregar, deps.engine, eid)
    if empresa is None or empresa.estado != AUDITANDO or not empresa.dominio:
        return "ignorado"
    if ja_auditada:
        return "ja_auditada"

    dominio = empresa.dominio
    auditoria_id = uuid.uuid4()

    async def progresso(i: int, total: int, caminho: str) -> None:
        await evento("auditando_pagina", f"Auditando {dominio} — página {i} de {total}: {caminho}")

    await evento("auditoria_iniciada", f"Auditoria técnica de {dominio} iniciada.")
    try:
        resultado = await asyncio.wait_for(
            deps.auditor.auditar(dominio, f"auditorias/{eid}/{auditoria_id}", progresso),
            timeout=deps.config.audit_total_timeout_s,
        )
    except LeituraBloqueada as exc:
        await evento("auditoria_bloqueada", f"Não foi possível auditar {dominio}: {exc}.")
        return "bloqueada"
    except TimeoutError:
        await evento(
            "auditoria_falhou", "A auditoria passou do tempo máximo. Reenvie a empresa para tentar de novo."
        )
        return "tempo_esgotado"
    except Exception as exc:  # noqa: BLE001 — o navegador pode falhar de muitas formas; a linha do tempo explica
        log.exception("auditoria de %s falhou", dominio)
        await evento(
            "auditoria_falhou", f"A auditoria falhou ({type(exc).__name__}). Reenvie a empresa mais tarde."
        )
        return "falhou"

    if not resultado.auditadas:
        await evento(
            "auditoria_bloqueada",
            f"Nenhuma página de {dominio} pôde ser testada.",
            paginas=[{"url": p["url"], "erro": p.get("erro")} for p in resultado.paginas],
        )
        return "bloqueada"

    await asyncio.to_thread(_gravar, deps.engine, auditoria_id, eid, resultado)
    await evento(
        "auditoria_pronta",
        mensagem_final(resultado),
        auditoria_id=str(auditoria_id),
        totais=resultado.totais(),
        plugins=resultado.plugins,
    )
    if deps.enfileirar_analise is not None:
        await deps.enfileirar_analise(eid)
    return "auditoria_pronta"
