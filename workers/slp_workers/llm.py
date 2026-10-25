"""Cliente de IA dos agentes: chamadas à Claude API com custo em reais por chamada (CONSTITUICAO §2.7, §20.2).

Os agentes recebem um `ClienteIA` e nunca falam com o SDK diretamente; os testes usam um cliente falso.
"""

import json
import re
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol, TypeVar

import anthropic
from pydantic import BaseModel

from slp_workers.settings import WorkerConfig

T = TypeVar("T", bound=BaseModel)

MTOK = Decimal(1_000_000)
FATOR_CACHE_LEITURA = Decimal("0.10")
FATOR_CACHE_ESCRITA = Decimal("1.25")
BETA_FALLBACK = "server-side-fallback-2026-07-01"
MAX_CONTINUACOES = 3  # pause_turn da busca na web


@dataclass
class Consumo:
    modelo: str
    tokens_in: int = 0
    tokens_out: int = 0
    buscas_web: int = 0
    custo_usd: Decimal = Decimal("0")
    custo_brl: Decimal = Decimal("0")
    duracao_ms: int = 0

    def somar(self, outro: "Consumo") -> "Consumo":
        return Consumo(
            modelo=outro.modelo or self.modelo,
            tokens_in=self.tokens_in + outro.tokens_in,
            tokens_out=self.tokens_out + outro.tokens_out,
            buscas_web=self.buscas_web + outro.buscas_web,
            custo_usd=self.custo_usd + outro.custo_usd,
            custo_brl=self.custo_brl + outro.custo_brl,
            duracao_ms=self.duracao_ms + outro.duracao_ms,
        )


class ErroIA(Exception):
    """Falha da chamada de IA. `consumo` registra o que já foi gasto, mesmo na falha."""

    def __init__(self, mensagem: str, consumo: Consumo | None = None, transitorio: bool = False) -> None:
        super().__init__(mensagem)
        self.consumo = consumo
        self.transitorio = transitorio


def calcular_consumo(modelo: str, usage: Any, config: WorkerConfig, duracao_ms: int = 0) -> Consumo:
    tabela = config.ai_prices_usd_per_mtok
    precos = tabela.get(modelo)
    if precos is None:
        # Modelo fora da tabela (ex.: o fallback escolhido pela API): conta pelo mais caro, nunca subestima
        precos = max(tabela.values(), key=lambda p: Decimal(str(p[1])))
    preco_in, preco_out = (Decimal(str(p)) for p in precos)

    entrada = int(getattr(usage, "input_tokens", 0) or 0)
    cache_leitura = int(getattr(usage, "cache_read_input_tokens", 0) or 0)
    cache_escrita = int(getattr(usage, "cache_creation_input_tokens", 0) or 0)
    saida = int(getattr(usage, "output_tokens", 0) or 0)
    server_tool_use = getattr(usage, "server_tool_use", None)
    buscas = int(getattr(server_tool_use, "web_search_requests", 0) or 0)

    usd = (
        Decimal(entrada) * preco_in
        + Decimal(cache_leitura) * preco_in * FATOR_CACHE_LEITURA
        + Decimal(cache_escrita) * preco_in * FATOR_CACHE_ESCRITA
        + Decimal(saida) * preco_out
    ) / MTOK + Decimal(buscas) * config.web_search_usd_per_request
    return Consumo(
        modelo=modelo,
        tokens_in=entrada + cache_leitura + cache_escrita,
        tokens_out=saida,
        buscas_web=buscas,
        custo_usd=usd,
        custo_brl=(usd * config.usd_brl_rate).quantize(Decimal("0.0001")),
        duracao_ms=duracao_ms,
    )


def extrair_json(texto: str) -> dict:
    """Último objeto JSON do texto (aceita bloco ```json```). Usado onde a resposta traz citações da busca."""
    blocos = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", texto, re.S)
    candidatos = blocos or re.findall(r"(\{.*\})", texto, re.S)
    for bruto in reversed(candidatos):
        try:
            return json.loads(bruto)
        except json.JSONDecodeError:
            continue
    raise ValueError("resposta sem JSON")


@dataclass
class RespostaBusca:
    texto: str
    urls_consultadas: list[str]
    consumo: Consumo


class ClienteIA(Protocol):
    async def estruturado(
        self, *, modelo: str, sistema: str, conteudo: str, formato: type[T], effort: str, max_tokens: int
    ) -> tuple[T, Consumo]: ...

    async def com_busca_web(
        self, *, modelo: str, sistema: str, conteudo: str, max_buscas: int, effort: str, max_tokens: int
    ) -> RespostaBusca: ...


class ClienteAnthropic:
    def __init__(self, config: WorkerConfig, client: anthropic.AsyncAnthropic | None = None) -> None:
        self._config = config
        self._cliente = client

    @property
    def _client(self) -> anthropic.AsyncAnthropic:
        # Criado no primeiro uso: o worker sobe mesmo sem ANTHROPIC_API_KEY e falha só no job, com evento
        if self._cliente is None:
            try:
                self._cliente = anthropic.AsyncAnthropic(max_retries=2, timeout=180.0)
            except anthropic.AnthropicError as exc:
                raise ErroIA("ANTHROPIC_API_KEY não configurada no worker") from exc
        return self._cliente

    def _extras(self) -> dict[str, Any]:
        # Recusa por classificador de segurança é refeita no modelo indicado pela própria API
        if self._config.ai_refusal_fallback:
            return {"betas": [BETA_FALLBACK], "fallbacks": "default"}
        return {}

    async def _chamar(self, metodo, **kwargs):
        try:
            return await metodo(**kwargs, **self._extras())
        except (anthropic.RateLimitError, anthropic.InternalServerError, anthropic.APIConnectionError) as exc:
            raise ErroIA(f"Claude API indisponível ({type(exc).__name__})", transitorio=True) from exc
        except anthropic.APIStatusError as exc:
            raise ErroIA(f"Claude API recusou a chamada ({exc.status_code})") from exc

    def _checar_parada(self, resposta: Any, consumo: Consumo) -> None:
        if resposta.stop_reason == "refusal":
            raise ErroIA("o modelo recusou a tarefa", consumo)
        if resposta.stop_reason == "max_tokens":
            raise ErroIA("a resposta passou do limite de tamanho", consumo)

    async def estruturado(
        self, *, modelo: str, sistema: str, conteudo: str, formato: type[T], effort: str, max_tokens: int
    ) -> tuple[T, Consumo]:
        inicio = time.monotonic()
        resposta = await self._chamar(
            self._client.beta.messages.parse,
            model=modelo,
            max_tokens=max_tokens,
            system=sistema,
            messages=[{"role": "user", "content": conteudo}],
            output_format=formato,
            output_config={"effort": effort},
        )
        consumo = calcular_consumo(
            resposta.model, resposta.usage, self._config, int((time.monotonic() - inicio) * 1000)
        )
        self._checar_parada(resposta, consumo)
        if resposta.parsed_output is None:
            raise ErroIA("a resposta não seguiu o formato esperado", consumo)
        return resposta.parsed_output, consumo

    async def com_busca_web(
        self, *, modelo: str, sistema: str, conteudo: str, max_buscas: int, effort: str, max_tokens: int
    ) -> RespostaBusca:
        inicio = time.monotonic()
        mensagens: list[dict[str, Any]] = [{"role": "user", "content": conteudo}]
        ferramentas = [
            {
                "type": "web_search_20260209",
                "name": "web_search",
                "max_uses": max_buscas,
                "user_location": {"type": "approximate", "country": "BR", "timezone": "America/Sao_Paulo"},
            }
        ]
        consumo = Consumo(modelo=modelo)
        urls: list[str] = []
        textos: list[str] = []
        for _ in range(MAX_CONTINUACOES + 1):
            resposta = await self._chamar(
                self._client.beta.messages.create,
                model=modelo,
                max_tokens=max_tokens,
                system=sistema,
                messages=mensagens,
                tools=ferramentas,
                output_config={"effort": effort},
            )
            consumo = consumo.somar(calcular_consumo(resposta.model, resposta.usage, self._config))
            for bloco in resposta.content:
                if bloco.type == "web_search_tool_result" and isinstance(bloco.content, list):
                    urls.extend(r.url for r in bloco.content if getattr(r, "url", None))
                elif bloco.type == "text":
                    textos.append(bloco.text)
            if resposta.stop_reason != "pause_turn":
                break
            # A busca no servidor pausou: reenvia o turno para continuar de onde parou
            mensagens = [mensagens[0], {"role": "assistant", "content": resposta.content}]
        consumo.duracao_ms = int((time.monotonic() - inicio) * 1000)
        self._checar_parada(resposta, consumo)
        return RespostaBusca(texto="\n".join(textos), urls_consultadas=urls, consumo=consumo)
