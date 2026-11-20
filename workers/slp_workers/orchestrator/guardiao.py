"""Guardião — Fase 3, Tarefa 4 (retomada; CONSTITUICAO §9, §13, §15.1, §15.2; ADR 0016).

Roda "a seco" sobre um toque já aprovado na Caixa de Aprovação e ainda não enviado: avalia o texto final
(`assunto_final`/`corpo_final`, o que o vendedor de fato aprovou, não necessariamente o que o Redator
escreveu) e só registra o resultado em `toques.guardiao_*`. Não envia nada — isso é o Mensageiro (Tarefa
3, ainda não construído); até lá, o resultado é só informativo para o vendedor na Caixa de Aprovação.

Duas regras baratas, sem gastar IA, bloqueiam antes de chamar o agente:
1. Supressão (CONSTITUICAO §15.1) — e-mail do contato ou domínio da empresa na lista de supressão.
2. No máximo 1 link no primeiro contato (CONSTITUICAO §15.2) — só se aplica ao toque de dia 0.

Passando as regras, o agente `guardiao` (claude-haiku-5-5) faz a checagem de tom/identificação/honestidade
que depende de julgamento. Só este módulo grava; o agente devolve dados validados (CONSTITUICAO §6).
"""

import asyncio
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import Engine, select, update

from slp_workers.agents import guardiao as agente_guardiao
from slp_workers.db import contatos, empresas, registrar_acao, registrar_evento, sequencias, supressao, toques
from slp_workers.llm import ClienteIA
from slp_workers.settings import WorkerConfig

MAX_LINKS_PRIMEIRO_CONTATO = 1
_PADRAO_LINK = re.compile(r"https?://\S+")

ResultadoGuardiao = Literal["aprovado", "bloqueado"]


@dataclass
class DependenciasGuardiao:
    engine: Engine
    ia: ClienteIA
    config: WorkerConfig


@dataclass
class Guardiao:
    deps: DependenciasGuardiao
    toque_id: uuid.UUID

    # --- banco --------------------------------------------------------------

    def _contexto(self) -> Any:
        with self.deps.engine.connect() as conn:
            return conn.execute(
                select(
                    toques, sequencias.c.empresa_id, sequencias.c.contato_id,
                    contatos.c.nome.label("contato_nome"), contatos.c.email,
                    empresas.c.nome.label("empresa_nome"), empresas.c.dominio,
                )
                .join(sequencias, sequencias.c.id == toques.c.sequencia_id)
                .join(contatos, contatos.c.id == sequencias.c.contato_id)
                .join(empresas, empresas.c.id == sequencias.c.empresa_id)
                .where(toques.c.id == self.toque_id)
            ).first()

    def _suprimido(self, email: str | None, dominio: str | None) -> str | None:
        with self.deps.engine.connect() as conn:
            if email and conn.scalar(select(supressao.c.id).where(supressao.c.email == email).limit(1)):
                return f"o e-mail {email} está na lista de supressão"
            if dominio and conn.scalar(select(supressao.c.id).where(supressao.c.dominio == dominio).limit(1)):
                return f"o domínio {dominio} está na lista de supressão"
            return None

    def _salvar(self, resultado: ResultadoGuardiao, motivo: str) -> None:
        with self.deps.engine.begin() as conn:
            conn.execute(
                update(toques)
                .where(toques.c.id == self.toque_id)
                .values(
                    guardiao_resultado=resultado,
                    guardiao_motivo=motivo,
                    guardiao_avaliado_em=datetime.now(UTC),
                )
            )

    # --- registro -------------------------------------------------------------

    async def evento(self, empresa_id: uuid.UUID, contato_id: uuid.UUID, tipo: str, mensagem: str) -> None:
        await asyncio.to_thread(
            registrar_evento, self.deps.engine, empresa_id, tipo, mensagem, contato_id=contato_id
        )

    # --- fluxo ------------------------------------------------------------

    async def executar(self) -> ResultadoGuardiao | None:
        linha = await asyncio.to_thread(self._contexto)
        if linha is None or linha.decisao_humana != "aprovado" or linha.enviado_em is not None:
            return None  # nada pendente: não aprovado ainda, ou já enviado

        assunto = linha.assunto_final or linha.assunto or ""
        corpo = linha.corpo_final or linha.corpo or ""

        motivo_regra = await asyncio.to_thread(self._suprimido, linha.email, linha.dominio)
        if motivo_regra is None and linha.dia == 0:
            links = len(_PADRAO_LINK.findall(corpo))
            if links > MAX_LINKS_PRIMEIRO_CONTATO:
                motivo_regra = (
                    f"{links} links no corpo — o primeiro contato permite no máximo "
                    f"{MAX_LINKS_PRIMEIRO_CONTATO} (CONSTITUICAO §15.2)"
                )

        if motivo_regra is not None:
            await asyncio.to_thread(self._salvar, "bloqueado", motivo_regra)
            await self.evento(
                linha.empresa_id, linha.contato_id,
                "guardiao_bloqueou", f"Guardião bloqueou o envio para {linha.contato_nome}: {motivo_regra}."
            )
            return "bloqueado"

        avaliacao, consumo, hash_e = await agente_guardiao.avaliar(
            self.deps.ia, self.deps.config,
            assunto=assunto, corpo=corpo, empresa_nome=linha.empresa_nome, contato_nome=linha.contato_nome,
        )
        await asyncio.to_thread(
            registrar_acao, self.deps.engine,
            agente=agente_guardiao.AGENTE, empresa_id=linha.empresa_id, contato_id=linha.contato_id,
            entrada_hash=hash_e, saida=avaliacao.model_dump(), raciocinio=avaliacao.raciocinio_resumido,
            modelo=consumo.modelo, tokens_in=consumo.tokens_in, tokens_out=consumo.tokens_out,
            custo_brl=consumo.custo_brl, duracao_ms=consumo.duracao_ms,
        )
        resultado: ResultadoGuardiao = "aprovado" if avaliacao.aprovado else "bloqueado"
        await asyncio.to_thread(self._salvar, resultado, avaliacao.motivo)
        if resultado == "bloqueado":
            await self.evento(
                linha.empresa_id, linha.contato_id, "guardiao_bloqueou",
                f"Guardião bloqueou o envio para {linha.contato_nome}: {avaliacao.motivo}",
            )
        else:
            await self.evento(
                linha.empresa_id, linha.contato_id,
                "guardiao_aprovou", f"Guardião liberou o envio para {linha.contato_nome}."
            )
        return resultado
