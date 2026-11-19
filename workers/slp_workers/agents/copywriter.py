"""Agente Redator (CONSTITUICAO §6, §9.1 e §21.1).

Escreve a mensagem de abordagem a partir da estratégia do Estrategista. Devolve um modelo validado ao
orquestrador; nunca grava no banco. Esquema publicado em packages/schemas/redacao.schema.json.

`link_diagnostico` é opcional e hoje sempre `None` — não existe ainda nenhuma página pública de
relatório/microsite (as rotas de `apps/api/app/routers/ficha.py` exigem login). Quando essa página
existir, passe a URL aqui.
"""

from pydantic import BaseModel

from slp_workers.agents.researcher import carregar_prompt, hash_entrada
from slp_workers.agents.strategist import Angulo, Estrategia
from slp_workers.llm import ClienteIA, Consumo
from slp_workers.settings import WorkerConfig

AGENTE = "redator"


class Redacao(BaseModel):
    assunto: str
    corpo: str
    fatos_usados: list[str]
    angulo: Angulo
    raciocinio_resumido: str


def _conteudo(
    decisor_nome: str,
    decisor_cargo: str,
    empresa_nome: str,
    resumo_dossie: list[str],
    estrategia: Estrategia,
    assinatura: str,
    link_diagnostico: str | None,
    feedback_revisao: str | None,
) -> str:
    resumo = "\n".join(f"- {linha}" for linha in resumo_dossie)
    partes = [
        f"Decisor: {decisor_nome}, {decisor_cargo}",
        f"Empresa: {empresa_nome}",
        f"Resumo:\n{resumo}",
        f"Persona: {estrategia.persona}\nÂngulo escolhido: {estrategia.angulo}",
        f"Achado escolhido: {estrategia.achado_titulo} — {estrategia.gancho_justificativa}",
        f"Página do achado: {estrategia.achado_pagina_url}",
    ]
    if link_diagnostico:
        partes.append(f"Link do diagnóstico: {link_diagnostico}")
    partes.append(f"Assinatura do remetente: {assinatura}")
    if feedback_revisao:
        partes.append(f"Revisão pedida pelo Crítico na tentativa anterior: {feedback_revisao}")
    return "\n".join(partes)


async def redigir(
    ia: ClienteIA,
    config: WorkerConfig,
    *,
    decisor_nome: str,
    decisor_cargo: str,
    empresa_nome: str,
    resumo_dossie: list[str],
    estrategia: Estrategia,
    assinatura: str,
    link_diagnostico: str | None = None,
    feedback_revisao: str | None = None,
) -> tuple[Redacao, Consumo, str]:
    conteudo = _conteudo(
        decisor_nome,
        decisor_cargo,
        empresa_nome,
        resumo_dossie,
        estrategia,
        assinatura,
        link_diagnostico,
        feedback_revisao,
    )
    sistema = carregar_prompt("voz-sinal-link") + "\n\n" + carregar_prompt("copywriter")
    redacao, consumo = await ia.estruturado(
        modelo=config.model_strategy,
        sistema=sistema,
        conteudo=conteudo,
        formato=Redacao,
        effort="high",
        max_tokens=4000,
    )
    return redacao, consumo, hash_entrada(conteudo)
