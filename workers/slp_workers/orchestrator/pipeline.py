"""Orquestrador do pipeline do prospect (CONSTITUICAO §5 e §7).

Fase 1, Tarefa 2: NOVO → PESQUISANDO e o Pesquisador monta o dossiê. A empresa fica em
PESQUISANDO com o dossiê pronto; a transição para AUDITANDO entra com o Auditor (Tarefa 3).
Os agentes devolvem dados validados; só este módulo grava no banco e na linha do tempo.
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

import httpx
from arq import Retry
from sqlalchemy import Engine, select, update
from sqlalchemy.exc import IntegrityError

from slp_workers.agents import researcher
from slp_workers.db import dossies, empresas, eventos, proxima_versao_dossie, registrar_acao, registrar_evento
from slp_workers.llm import ClienteIA, Consumo, ErroIA
from slp_workers.orchestrator.budget import requires_ai_budget
from slp_workers.settings import WorkerConfig, get_config
from slp_workers.web.fetcher import LeitorSite, LeituraBloqueada, Pagina, escolher_paginas
from slp_workers.web.ratelimit import Limitador
from slp_workers.web.safety import Resolvedor, resolver_dns

log = logging.getLogger("slp_workers.pipeline")

NOVO = "NOVO"
PESQUISANDO = "PESQUISANDO"
MAX_TENTATIVAS_TRANSITORIAS = 3

# Transições automáticas permitidas (CONSTITUICAO §7.1). Mudanças manuais pelo Kanban
# são do humano e ficam fora desta tabela. Não adicione estados sem emendar a Constituição.
TRANSICOES: dict[str, frozenset[str]] = {
    "NOVO": frozenset({"PESQUISANDO"}),
    "PESQUISANDO": frozenset({"AUDITANDO"}),
    "AUDITANDO": frozenset({"QUALIFICANDO"}),
    "QUALIFICANDO": frozenset({"MAPEANDO_DECISORES", "ARQUIVADO"}),
    "MAPEANDO_DECISORES": frozenset({"PREPARANDO_ABORDAGEM"}),
    "PREPARANDO_ABORDAGEM": frozenset({"EM_SEQUENCIA"}),
    "EM_SEQUENCIA": frozenset({"RESPONDEU", "SEM_RESPOSTA"}),
    "RESPONDEU": frozenset({"REUNIAO_AGENDADA", "NAO_INTERESSADO"}),
    "REUNIAO_AGENDADA": frozenset({"PROPOSTA_ENVIADA"}),
    "PROPOSTA_ENVIADA": frozenset({"NEGOCIACAO"}),
    "NEGOCIACAO": frozenset({"GANHO", "PERDIDO"}),
}


def pode_transitar(origem: str, destino: str) -> bool:
    return destino in TRANSICOES.get(origem, frozenset())


@dataclass
class Dependencias:
    engine: Engine
    ia: ClienteIA
    limitador: Limitador
    config: WorkerConfig
    resolvedor: Resolvedor = resolver_dns
    transport: httpx.AsyncBaseTransport | None = None

    @classmethod
    def do_ctx(cls, ctx: dict) -> "Dependencias":
        return cls(
            engine=ctx["engine"],
            ia=ctx["ia"],
            limitador=ctx["limitador"],
            config=ctx.get("config") or get_config(),
            resolvedor=ctx.get("resolvedor", resolver_dns),
            transport=ctx.get("transport"),
        )


@dataclass
class Pesquisa:
    deps: Dependencias
    empresa_id: uuid.UUID
    gasto: Consumo = field(default_factory=lambda: Consumo(modelo=""))
    etapa: str = "pesquisador"

    # --- registro ---------------------------------------------------------

    async def evento(self, tipo: str, mensagem: str, **dados: Any) -> None:
        await asyncio.to_thread(registrar_evento, self.deps.engine, self.empresa_id, tipo, mensagem, **dados)

    async def acao(
        self, agente: str, entrada_hash: str, saida: dict, raciocinio: str | None, c: Consumo
    ) -> None:
        self.gasto = self.gasto.somar(c)
        await asyncio.to_thread(
            registrar_acao,
            self.deps.engine,
            agente=agente,
            empresa_id=self.empresa_id,
            entrada_hash=entrada_hash,
            saida=saida,
            raciocinio=raciocinio,
            modelo=c.modelo,
            tokens_in=c.tokens_in,
            tokens_out=c.tokens_out,
            custo_brl=c.custo_brl,
            duracao_ms=c.duracao_ms,
        )

    # --- banco ------------------------------------------------------------

    def _carregar(self) -> Any:
        with self.deps.engine.connect() as conn:
            return conn.execute(select(empresas).where(empresas.c.id == self.empresa_id)).first()

    def _transitar(self, origem: str, destino: str) -> bool:
        if not pode_transitar(origem, destino):
            raise ValueError(f"transição {origem} → {destino} fora do §7.1")
        with self.deps.engine.begin() as conn:
            r = conn.execute(
                update(empresas)
                .where(empresas.c.id == self.empresa_id, empresas.c.estado == origem)
                .values(estado=destino)
            )
        return r.rowcount == 1

    def _tem_dossie(self) -> bool:
        with self.deps.engine.connect() as conn:
            return (
                conn.scalar(select(dossies.c.id).where(dossies.c.empresa_id == self.empresa_id).limit(1))
                is not None
            )

    def _ultimo_evento(self) -> str | None:
        with self.deps.engine.connect() as conn:
            return conn.scalar(
                select(eventos.c.tipo)
                .where(eventos.c.empresa_id == self.empresa_id)
                .order_by(eventos.c.ocorrido_em.desc())
                .limit(1)
            )

    def _dono_do_dominio(self, dominio: str) -> Any:
        with self.deps.engine.connect() as conn:
            return conn.execute(
                select(empresas.c.id, empresas.c.nome).where(empresas.c.dominio == dominio)
            ).first()

    def _gravar_dominio(self, dominio: str) -> Any:
        """Devolve None se gravou, ou a empresa que já tem esse domínio (deduplicação por domínio)."""
        outra = self._dono_do_dominio(dominio)
        if outra is not None:
            return outra
        try:
            with self.deps.engine.begin() as conn:
                conn.execute(update(empresas).where(empresas.c.id == self.empresa_id).values(dominio=dominio))
        except IntegrityError:
            # Outra empresa gravou o mesmo domínio ao mesmo tempo
            return self._dono_do_dominio(dominio)
        return None

    def _gravar_dossie(self, dados: dict, dossie: researcher.Dossie) -> int:
        with self.deps.engine.begin() as conn:
            versao = proxima_versao_dossie(conn, self.empresa_id)
            conn.execute(
                dossies.insert().values(
                    id=uuid.uuid4(),
                    empresa_id=self.empresa_id,
                    dados_json=dados,
                    resumo="\n".join(dossie.resumo_5_linhas),
                    sinais_json={
                        "sinais": [s.model_dump() for s in dossie.sinais],
                        "mencoes_inclusao": [m.model_dump() for m in dossie.mencoes_inclusao],
                    },
                    versao=versao,
                    criado_em=datetime.now(UTC),
                )
            )
            valores: dict[str, Any] = {"nome": dossie.nome_oficial[:255], "setor": dossie.setor}
            if dossie.localizacao.cidade:
                valores["cidade"] = dossie.localizacao.cidade[:120]
            if dossie.localizacao.uf and len(dossie.localizacao.uf.strip()) == 2:
                valores["uf"] = dossie.localizacao.uf.strip().upper()
            conn.execute(update(empresas).where(empresas.c.id == self.empresa_id).values(**valores))
        return versao

    # --- etapas -----------------------------------------------------------

    async def _resolver_dominio(self, nome: str) -> str | None:
        self.etapa = "pesquisador.dominio"
        await self.evento("buscando_site", f"Procurando o site oficial de {nome}.")
        resolucao, resposta = await researcher.resolver_dominio(self.deps.ia, self.deps.config, nome)
        await self.acao(
            "pesquisador.dominio",
            researcher.hash_entrada(nome),
            resolucao.model_dump(),
            resolucao.raciocinio_resumido,
            resposta.consumo,
        )
        candidatos = researcher.verificar_candidatos(resolucao, resposta.urls_consultadas)

        if len(candidatos) == 1 and candidatos[0].confianca == "alta":
            dominio = candidatos[0].dominio
            outra = await asyncio.to_thread(self._gravar_dominio, dominio)
            if outra is not None:
                await self.evento(
                    "dominio_ja_cadastrado",
                    f"O site {dominio} já pertence à empresa {outra.nome} no painel. "
                    "Esta entrada não será pesquisada.",
                    dominio=dominio,
                    empresa_existente_id=str(outra.id),
                )
                return None
            await self.evento(
                "dominio_identificado",
                f"Site oficial identificado: {dominio}.",
                dominio=dominio,
                evidencia_url=candidatos[0].evidencia_url,
            )
            return dominio

        mensagem = (
            f"Encontrei {len(candidatos)} site(s) possível(is). Confirme qual é o oficial para continuar."
            if candidatos
            else "Não encontrei o site oficial. Informe o endereço para continuar."
        )
        await self.evento("confirmacao_dominio", mensagem, candidatos=[c.model_dump() for c in candidatos])
        return None

    async def _ler_site(self, dominio: str) -> list[Pagina]:
        cfg = self.deps.config
        leitor = LeitorSite(
            dominio,
            self.deps.limitador,
            user_agent=cfg.crawler_user_agent,
            timeout_s=cfg.research_page_timeout_s,
            max_bytes=cfg.research_max_bytes,
            max_chars=cfg.research_chars_per_page,
            permitir_privados=cfg.web_allow_private_hosts,
            resolvedor=self.deps.resolvedor,
            transport=self.deps.transport,
        )
        async with leitor:
            await self.evento("lendo_pagina", f"Lendo a página inicial de {dominio}.")
            try:
                home = await leitor.ler_home()
            except LeituraBloqueada as exc:
                await self.evento("site_indisponivel", f"Não foi possível ler o site {dominio}: {exc}.")
                return []
            urls = escolher_paginas(home, cfg.research_max_pages - 1)
            paginas = [home]
            total = 1 + len(urls)
            for i, url in enumerate(urls, start=2):
                caminho = urlsplit(url).path or "/"
                await self.evento("lendo_pagina", f"Lendo página {i} de {total}: {caminho}")
                try:
                    paginas.append(await leitor.ler(url))
                except LeituraBloqueada as exc:
                    await self.evento("pagina_ignorada", f"Página {caminho} ignorada: {exc}.")
        return paginas

    async def _montar_dossie(self, dominio: str, nome: str, paginas: list[Pagina]) -> None:
        self.etapa = "pesquisador"
        await self.evento("analisando", f"Analisando {len(paginas)} página(s) para montar o dossiê.")
        dossie, consumo, entrada_hash = await researcher.montar_dossie(
            self.deps.ia, self.deps.config, dominio, nome, paginas
        )
        urls = [p.url for p in paginas]
        validado, removidos = researcher.validar_fontes(dossie, urls)
        await self.acao(
            "pesquisador", entrada_hash, validado.model_dump(), validado.raciocinio_resumido, consumo
        )
        dados = {
            **validado.model_dump(),
            "dominio": dominio,
            "paginas_lidas": urls,
            "tecnologias_site": sorted({t for p in paginas for t in p.tecnologias}),
            "modelo": consumo.modelo,
        }
        versao = await asyncio.to_thread(self._gravar_dossie, dados, validado)
        await self.evento(
            "dossie_pronto",
            "Dossiê pronto. A auditoria de acessibilidade entra na próxima versão.",
            versao=versao,
            informacoes_descartadas=removidos,
            custo_brl=str(self.gasto.custo_brl),
        )

    # --- fluxo ------------------------------------------------------------

    async def executar(self) -> str:
        empresa = await asyncio.to_thread(self._carregar)
        if empresa is None:
            log.warning("empresa %s não encontrada; job descartado", self.empresa_id)
            return "empresa_inexistente"
        if empresa.estado == NOVO:
            if await asyncio.to_thread(self._transitar, NOVO, PESQUISANDO):
                await self.evento("pesquisa_iniciada", "Pesquisa iniciada.")
        elif empresa.estado != PESQUISANDO:
            return "ignorado"
        if await asyncio.to_thread(self._tem_dossie):
            return "ja_pesquisada"

        dominio = empresa.dominio
        if not dominio:
            if await asyncio.to_thread(self._ultimo_evento) == "confirmacao_dominio":
                return "aguardando_confirmacao"
            dominio = await self._resolver_dominio(empresa.nome)
            if dominio is None:
                return "aguardando_confirmacao"

        if self.gasto.custo_brl >= self.deps.config.research_cost_cap_brl:
            await self.evento(
                "teto_por_empresa", "Teto de custo por empresa atingido; a pesquisa parou aqui."
            )
            return "teto_por_empresa"

        paginas = await self._ler_site(dominio)
        if not paginas:
            return "site_indisponivel"
        await self._montar_dossie(dominio, empresa.nome, paginas)
        return "dossie_pronto"


@requires_ai_budget
async def processar_empresa(ctx: dict, empresa_id: str) -> str:
    pesquisa = Pesquisa(Dependencias.do_ctx(ctx), uuid.UUID(empresa_id))
    try:
        return await pesquisa.executar()
    except ErroIA as exc:
        if exc.consumo is not None:
            await pesquisa.acao(pesquisa.etapa, "", {"erro": str(exc)}, None, exc.consumo)
        if exc.transitorio and ctx.get("job_try", 1) < MAX_TENTATIVAS_TRANSITORIAS:
            raise Retry(defer=120) from exc
        await pesquisa.evento("pesquisa_falhou", f"A pesquisa falhou: {exc}. Reenvie a empresa mais tarde.")
        return "falhou"
