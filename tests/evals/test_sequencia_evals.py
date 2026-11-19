"""Encadeia Estrategista → Redator → Crítico com a API real da Claude, sobre os 30 casos de
tests/evals/fixtures/casos-referencia.json (Fase 3, Tarefa 1).

    ANTHROPIC_API_KEY=... PROMPT_EVALS=1 PYTHONPATH=workers pytest -s tests/evals/test_sequencia_evals.py

Cada caso é um teste parametrizado (pytest -k "caso-01 or caso-07" roda só alguns). Chama a API de
verdade — é o que diferencia um eval de workers/tests/ (que mocka tudo): o que está sob teste é o
próprio texto do prompt, não a lógica determinística ao redor. A nota do Crítico abaixo de 8 não falha
o teste (é esperada nos casos-armadilha); só os checks deterministicos de relatorio.py falham.
"""

import asyncio
import json
from pathlib import Path

import pytest
from relatorio import avaliar_caso, falhou_determinismo
from schemas import Critica, Estrategia, Redacao

PASTA = Path(__file__).resolve().parent
CASOS = json.loads(
    (PASTA / "fixtures" / "casos-referencia.json").read_text(encoding="utf-8")
)


def _prompt(nome: str) -> str:
    from slp_workers.agents.researcher import carregar_prompt

    return carregar_prompt(nome)


def _conteudo_estrategista(caso: dict) -> str:
    achados = (
        "\n".join(
            f"{i + 1}. {a['titulo']} — {a['impacto_humano']} "
            f"(critério WCAG {a['criterio_wcag'] or 'não identificado'}, página: {a['pagina_url']})"
            for i, a in enumerate(caso["achados"])
        )
        or "(nenhum achado confirmado)"
    )
    decisor = caso["decisor"]
    resumo = "\n".join(f"- {linha}" for linha in caso["empresa"]["resumo_5_linhas"])
    return (
        f"Empresa: {caso['empresa']['nome_oficial']}\n"
        f"Resumo:\n{resumo}\n\n"
        f"Achados da auditoria:\n{achados}\n\n"
        f"Decisor:\nNome: {decisor['nome']}\nCargo: {decisor['cargo']}\nÁrea: {decisor['area']}\n"
        f"Já interagiu antes (LinkedIn/WhatsApp): {'sim' if caso['ja_interagiu'] else 'não'}"
    )


def _conteudo_redator(caso: dict, estrategia: Estrategia) -> str:
    decisor = caso["decisor"]
    resumo = "\n".join(f"- {linha}" for linha in caso["empresa"]["resumo_5_linhas"])
    return (
        f"Decisor: {decisor['nome']}, {decisor['cargo']}\n"
        f"Empresa: {caso['empresa']['nome_oficial']}\n"
        f"Resumo:\n{resumo}\n\n"
        f"Persona: {estrategia.persona}\nÂngulo escolhido: {estrategia.angulo}\n"
        f"Achado escolhido: {estrategia.achado_titulo} — {estrategia.gancho_justificativa}\n"
        f"Página do achado: {estrategia.achado_pagina_url}\n"
        f"Link do diagnóstico: {caso['microsite_url']}\n"
        f"Assinatura do remetente: Equipe Sinal Link Acessibilidade"
    )


def _conteudo_critico(caso: dict, redacao: Redacao) -> str:
    achados = (
        "\n".join(
            f"- {a['titulo']} — {a['impacto_humano']} "
            f"(critério WCAG {a['criterio_wcag'] or 'não identificado'}, página: {a['pagina_url']})"
            for a in caso["achados"]
        )
        or "(nenhum achado confirmado)"
    )
    resumo = "\n".join(f"- {linha}" for linha in caso["empresa"]["resumo_5_linhas"])
    return (
        f"Mensagem a avaliar:\nAssunto: {redacao.assunto}\nCorpo:\n{redacao.corpo}\n\n"
        f"Fatos usados pelo redator: {redacao.fatos_usados}\nÂngulo: {redacao.angulo}\n\n"
        f"Dados verificados para conferência:\n"
        f"Empresa: {caso['empresa']['nome_oficial']}\n"
        f"Resumo:\n{resumo}\n\n"
        f"Achados da auditoria:\n{achados}"
    )


async def _rodar_caso(caso: dict, cliente, config) -> dict:
    estrategia, _ = await cliente.estruturado(
        modelo=config.model_strategy,
        sistema=_prompt("strategist"),
        conteudo=_conteudo_estrategista(caso),
        formato=Estrategia,
        effort="high",
        max_tokens=4000,
    )
    redacao, _ = await cliente.estruturado(
        modelo=config.model_strategy,
        sistema=_prompt("voz-sinal-link") + "\n\n" + _prompt("copywriter"),
        conteudo=_conteudo_redator(caso, estrategia),
        formato=Redacao,
        effort="high",
        max_tokens=4000,
    )
    critica, _ = await cliente.estruturado(
        modelo=config.model_analysis,
        sistema=_prompt("reviewer"),
        conteudo=_conteudo_critico(caso, redacao),
        formato=Critica,
        effort="medium",
        max_tokens=4000,
    )
    return avaliar_caso(caso, estrategia, redacao, critica)


@pytest.mark.parametrize("caso", CASOS, ids=[c["id"] for c in CASOS])
def test_sequencia(caso, cliente, config, resultados_sessao):
    resultado = asyncio.run(_rodar_caso(caso, cliente, config))
    resultados_sessao.append(resultado)
    problemas = falhou_determinismo(resultado)
    assert not problemas, "; ".join(problemas)
