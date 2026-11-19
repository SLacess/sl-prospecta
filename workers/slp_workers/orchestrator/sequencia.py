"""Geração da sequência de abordagem (CONSTITUICAO §7.3, Etapas 5-6; §9.3; §9.4).

Para uma empresa em PREPARANDO_ABORDAGEM:
1. supressão do domínio e disjuntor diário de custo de IA (§13, mesmo teto global de `orchestrator.budget`);
2. para cada contato com e-mail válido, sem opt-out e que ainda não tem `sequencias`:
   a. supressão do e-mail;
   b. Estrategista decide persona, ângulo, gancho de evidência e a cadência de toques (§9.3);
   c. grava `sequencias` e um `toques` por item da cadência (status "planejada");
   d. Redator escreve e Crítico avalia o toque de dia 0, com até 3 ciclos de reescrita — abaixo de 8 em
      qualquer critério, volta para o Redator com o motivo como pedido de revisão (§7.3 Etapa 6);
   e. grava o resultado final no toque de dia 0 (status "rascunho"), aprovado ou não — mesmo sem
      aprovação depois de 3 tentativas, o rascunho fica salvo para o vendedor revisar.

A empresa nunca muda de estado aqui: o §7.1 reserva a caixa de aprovação (Tarefa 3, ainda não construída)
entre PREPARANDO_ABORDAGEM e EM_SEQUENCIA.

Duas limitações conhecidas desta tarefa, citadas no plano:
- Não existe link público de diagnóstico ainda; o Redator escreve sem URL.
- `ja_interagiu` é sempre False — sem sinal real de interação prévia antes da Fase 4 — então o toque de
  LinkedIn do dia 5 nunca entra na cadência planejada.

Só este módulo grava; os agentes devolvem dados validados (§6).
"""

import asyncio
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Engine, func, select, update

from slp_workers.agents import copywriter, reviewer, strategist
from slp_workers.db import (
    acoes_agentes,
    auditorias,
    contatos,
    dossies,
    empresas,
    registrar_acao,
    registrar_evento,
    sequencias,
    supressao,
    toques,
)
from slp_workers.llm import ClienteIA, Consumo
from slp_workers.orchestrator.budget import verificar_disjuntor
from slp_workers.settings import WorkerConfig

PREPARANDO_ABORDAGEM = "PREPARANDO_ABORDAGEM"
MAX_TENTATIVAS = 3
ASSINATURA_PADRAO = "Equipe Sinal Link Acessibilidade"


class CustoDiarioEsgotado(Exception):
    def __init__(self, gasto_brl: Decimal, teto_brl: Decimal) -> None:
        super().__init__(f"teto diário de IA atingido (R$ {gasto_brl} de R$ {teto_brl})")
        self.gasto_brl = gasto_brl
        self.teto_brl = teto_brl


def custo_estimado_por_contato(config: WorkerConfig) -> tuple[Decimal, Decimal]:
    """Estimativa (não medição real) do custo de 1 contato: melhor caso (1 tentativa) e pior caso (3
    ciclos de reescrita), a partir dos preços já cadastrados em `config.ai_prices_usd_per_mtok`."""
    tabela = config.ai_prices_usd_per_mtok
    opus_in, opus_out = tabela.get("claude-opus-5-5", (Decimal("4.00"), Decimal("20.00")))
    sonnet_in, sonnet_out = tabela.get("claude-sonnet-5-5", (Decimal("2.00"), Decimal("10.00")))
    mtok = Decimal(1_000_000)
    taxa = config.usd_brl_rate

    def custo(tokens_in: int, tokens_out: int, preco_in: Decimal, preco_out: Decimal) -> Decimal:
        usd = (Decimal(tokens_in) * preco_in + Decimal(tokens_out) * preco_out) / mtok
        return (usd * taxa).quantize(Decimal("0.01"))

    estrategista = custo(4000, 800, opus_in, opus_out)
    redator_tentativa = custo(4000, 500, opus_in, opus_out)
    critico_tentativa = custo(3500, 400, sonnet_in, sonnet_out)
    melhor = estrategista + redator_tentativa + critico_tentativa
    pior = estrategista + MAX_TENTATIVAS * (redator_tentativa + critico_tentativa)
    return melhor, pior


@dataclass
class DependenciasSequencia:
    engine: Engine
    ia: ClienteIA
    config: WorkerConfig


@dataclass
class Sequencia:
    deps: DependenciasSequencia
    empresa_id: uuid.UUID

    # --- registro -----------------------------------------------------------

    async def evento(
        self, tipo: str, mensagem: str, *, contato_id: uuid.UUID | None = None, **dados: Any
    ) -> None:
        await asyncio.to_thread(
            registrar_evento,
            self.deps.engine,
            self.empresa_id,
            tipo,
            mensagem,
            contato_id=contato_id,
            **dados,
        )

    async def acao(
        self,
        agente: str,
        entrada_hash: str,
        saida: dict,
        raciocinio: str | None,
        *,
        consumo: Consumo,
        contato_id: uuid.UUID,
    ) -> None:
        await asyncio.to_thread(
            registrar_acao,
            self.deps.engine,
            agente=agente,
            empresa_id=self.empresa_id,
            contato_id=contato_id,
            entrada_hash=entrada_hash,
            saida=saida,
            raciocinio=raciocinio,
            modelo=consumo.modelo,
            tokens_in=consumo.tokens_in,
            tokens_out=consumo.tokens_out,
            custo_brl=consumo.custo_brl,
            duracao_ms=consumo.duracao_ms,
        )

    # --- banco ----------------------------------------------------------------

    def _empresa(self) -> Any:
        with self.deps.engine.connect() as conn:
            return conn.execute(select(empresas).where(empresas.c.id == self.empresa_id)).first()

    def _dominio_suprimido(self, dominio: str) -> bool:
        with self.deps.engine.connect() as conn:
            return (
                conn.scalar(select(supressao.c.id).where(supressao.c.dominio == dominio).limit(1)) is not None
            )

    def _email_suprimido(self, email: str) -> bool:
        with self.deps.engine.connect() as conn:
            return conn.scalar(select(supressao.c.id).where(supressao.c.email == email).limit(1)) is not None

    def _contatos_validos(self) -> list:
        with self.deps.engine.connect() as conn:
            return conn.execute(
                select(contatos).where(
                    contatos.c.empresa_id == self.empresa_id,
                    contatos.c.email_status == "valido",
                    contatos.c.opt_out.is_(False),
                )
            ).all()

    def _ja_tem_sequencia(self, contato_id: uuid.UUID) -> bool:
        with self.deps.engine.connect() as conn:
            return (
                conn.scalar(select(sequencias.c.id).where(sequencias.c.contato_id == contato_id).limit(1))
                is not None
            )

    def _ultimo_dossie(self) -> Any:
        with self.deps.engine.connect() as conn:
            return conn.execute(
                select(dossies)
                .where(dossies.c.empresa_id == self.empresa_id)
                .order_by(dossies.c.versao.desc())
                .limit(1)
            ).first()

    def _ultima_auditoria_analisada(self) -> Any:
        with self.deps.engine.connect() as conn:
            return conn.execute(
                select(auditorias)
                .where(auditorias.c.empresa_id == self.empresa_id, auditorias.c.nota.is_not(None))
                .order_by(auditorias.c.criado_em.desc())
                .limit(1)
            ).first()

    def _gasto_do_contato(self, contato_id: uuid.UUID) -> Decimal:
        with self.deps.engine.connect() as conn:
            total = conn.scalar(
                select(func.coalesce(func.sum(acoes_agentes.c.custo), 0)).where(
                    acoes_agentes.c.contato_id == contato_id
                )
            )
        return Decimal(str(total or 0)).quantize(Decimal("0.0001"))

    def _gravar_sequencia(self, contato_id: uuid.UUID, estrategia: strategist.Estrategia) -> uuid.UUID:
        sequencia_id = uuid.uuid4()
        with self.deps.engine.begin() as conn:
            conn.execute(
                sequencias.insert().values(
                    id=sequencia_id,
                    empresa_id=self.empresa_id,
                    contato_id=contato_id,
                    persona=estrategia.persona,
                    angulo=estrategia.angulo,
                    achado_titulo=estrategia.achado_titulo[:300],
                    achado_pagina_url=estrategia.achado_pagina_url[:500],
                    gancho_justificativa=estrategia.gancho_justificativa,
                    criado_em=datetime.now(UTC),
                )
            )
        return sequencia_id

    def _gravar_toques_planejados(self, sequencia_id: uuid.UUID, toques_plano: list) -> None:
        with self.deps.engine.begin() as conn:
            for t in toques_plano:
                conn.execute(
                    toques.insert().values(
                        id=uuid.uuid4(),
                        sequencia_id=sequencia_id,
                        dia=t.dia,
                        canal=t.canal,
                        status="planejada",
                        conteudo_sugerido=t.conteudo_sugerido,
                        criado_em=datetime.now(UTC),
                    )
                )

    def _atualizar_toque_dia0(self, sequencia_id: uuid.UUID, valores: dict) -> None:
        with self.deps.engine.begin() as conn:
            conn.execute(
                update(toques)
                .where(toques.c.sequencia_id == sequencia_id, toques.c.dia == 0)
                .values(**valores)
            )

    # --- fluxo ------------------------------------------------------------

    async def _gerar_para_contato(
        self, empresa: Any, contato: Any, achados: list[dict], resumo: list[str]
    ) -> str:
        estrategia, consumo, hash_e = await strategist.criar_estrategia(
            self.deps.ia,
            self.deps.config,
            empresa_nome=empresa.nome,
            resumo_dossie=resumo,
            achados=achados,
            decisor_nome=contato.nome,
            decisor_cargo=contato.cargo or "",
            decisor_area=contato.area,
            ja_interagiu=False,
        )
        await self.acao(
            strategist.AGENTE,
            hash_e,
            estrategia.model_dump(),
            estrategia.raciocinio_resumido,
            consumo=consumo,
            contato_id=contato.id,
        )
        sequencia_id = await asyncio.to_thread(self._gravar_sequencia, contato.id, estrategia)
        await asyncio.to_thread(self._gravar_toques_planejados, sequencia_id, estrategia.canal_e_cadencia)

        feedback: str | None = None
        redacao = critica = None
        tentativa = 0
        for tentativa in range(1, MAX_TENTATIVAS + 1):  # noqa: B007 — usado depois do laço
            redacao, consumo, hash_r = await copywriter.redigir(
                self.deps.ia,
                self.deps.config,
                decisor_nome=contato.nome,
                decisor_cargo=contato.cargo or "",
                empresa_nome=empresa.nome,
                resumo_dossie=resumo,
                estrategia=estrategia,
                assinatura=ASSINATURA_PADRAO,
                feedback_revisao=feedback,
            )
            await self.acao(
                copywriter.AGENTE,
                hash_r,
                redacao.model_dump(),
                redacao.raciocinio_resumido,
                consumo=consumo,
                contato_id=contato.id,
            )
            critica, consumo, hash_c = await reviewer.avaliar(
                self.deps.ia,
                self.deps.config,
                redacao=redacao,
                achados=achados,
                empresa_nome=empresa.nome,
                resumo_dossie=resumo,
            )
            await self.acao(
                reviewer.AGENTE,
                hash_c,
                critica.model_dump(),
                critica.raciocinio_resumido,
                consumo=consumo,
                contato_id=contato.id,
            )
            gasto = await asyncio.to_thread(self._gasto_do_contato, contato.id)
            if critica.aprovado or gasto > self.deps.config.sequencia_cost_cap_brl:
                break
            feedback = critica.motivo

        await asyncio.to_thread(
            self._atualizar_toque_dia0,
            sequencia_id,
            {
                "status": "rascunho",
                "assunto": redacao.assunto[:200],
                "corpo": redacao.corpo,
                "fatos_usados": redacao.fatos_usados,
                "criterios_json": critica.criterios.model_dump(),
                "nota": critica.nota,
                "aprovado": critica.aprovado,
                "motivo_critico": critica.motivo,
                "tentativas": tentativa,
            },
        )
        await self.evento(
            "sequencia_gerada",
            f"Sequência para {contato.nome} ({contato.area}): ângulo {estrategia.angulo}, "
            f"nota {critica.nota}/10{' (aprovado)' if critica.aprovado else ''}.",
            contato_id=contato.id,
            persona=estrategia.persona,
            angulo=estrategia.angulo,
            nota=critica.nota,
            aprovado=critica.aprovado,
            tentativas=tentativa,
        )
        if not critica.aprovado:
            await self.evento(
                "sequencia_sem_aprovacao",
                f"A mensagem de {contato.nome} não passou no Crítico depois de {tentativa} tentativa(s): "
                f"{critica.motivo} Vai para o vendedor revisar manualmente.",
                contato_id=contato.id,
            )
        return "sequencia_gerada"

    async def executar(self) -> dict[str, str]:
        empresa = await asyncio.to_thread(self._empresa)
        if empresa is None or empresa.estado != PREPARANDO_ABORDAGEM or not empresa.dominio:
            return {}
        if await asyncio.to_thread(self._dominio_suprimido, empresa.dominio):
            await self.evento(
                "dominio_suprimido", "O domínio está na lista de supressão: nenhuma sequência gerada."
            )
            return {}

        disjuntor = await asyncio.to_thread(verificar_disjuntor, self.deps.engine)
        if disjuntor.atingido:
            raise CustoDiarioEsgotado(disjuntor.custo_hoje_brl, disjuntor.teto_brl)

        dossie = await asyncio.to_thread(self._ultimo_dossie)
        auditoria = await asyncio.to_thread(self._ultima_auditoria_analisada)
        resumo = dossie.resumo.splitlines() if dossie and dossie.resumo else []
        achados = (auditoria.achados_json or {}).get("top3_para_leigos", []) if auditoria else []

        resultados: dict[str, str] = {}
        for contato in await asyncio.to_thread(self._contatos_validos):
            if await asyncio.to_thread(self._ja_tem_sequencia, contato.id):
                resultados[str(contato.id)] = "ja_tem_sequencia"
                continue
            if contato.email and await asyncio.to_thread(self._email_suprimido, contato.email):
                await self.evento(
                    "contato_suprimido",
                    f"O e-mail de {contato.nome} está na lista de supressão.",
                    contato_id=contato.id,
                )
                resultados[str(contato.id)] = "contato_suprimido"
                continue
            resultados[str(contato.id)] = await self._gerar_para_contato(empresa, contato, achados, resumo)
        return resultados
