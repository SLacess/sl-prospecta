"""Agente Estrategista (CONSTITUICAO §6 e §7.3, Etapa 5).

Escolhe, por decisor: persona, ângulo, gancho de evidência e canal/cadência. Devolve um modelo
validado ao orquestrador; nunca grava no banco. Esquema publicado em
packages/schemas/estrategia.schema.json.
"""

from typing import Literal

from pydantic import BaseModel

from slp_workers.agents.researcher import carregar_prompt, hash_entrada
from slp_workers.llm import ClienteIA, Consumo
from slp_workers.settings import WorkerConfig

AGENTE = "estrategista"

Persona = Literal["ti", "rh_di", "marketing_digital", "esg", "juridico_compliance"]
Angulo = Literal[
    "experiencia_cliente",
    "inclusao_colaboradores_pcd",
    "esg_reputacao",
    "conformidade_legal",
    "conversao_alcance_mercado",
]


class Toque(BaseModel):
    dia: int
    canal: Literal["email", "linkedin", "whatsapp"]
    conteudo_sugerido: str


class Estrategia(BaseModel):
    persona: Persona
    angulo: Angulo
    achado_titulo: str
    achado_pagina_url: str
    gancho_justificativa: str
    canal_e_cadencia: list[Toque]
    raciocinio_resumido: str


def _conteudo(
    empresa_nome: str,
    resumo_dossie: list[str],
    achados: list[dict],
    decisor_nome: str,
    decisor_cargo: str,
    decisor_area: str,
    ja_interagiu: bool,
) -> str:
    lista_achados = (
        "\n".join(
            f"{i + 1}. {a['titulo']} — {a['impacto_humano']} "
            f"(critério WCAG {a.get('criterio_wcag') or 'não identificado'}, página: {a['pagina_url']})"
            for i, a in enumerate(achados)
        )
        or "(nenhum achado confirmado)"
    )
    resumo = "\n".join(f"- {linha}" for linha in resumo_dossie)
    return (
        f"Empresa: {empresa_nome}\n"
        f"Resumo:\n{resumo}\n\n"
        f"Achados da auditoria:\n{lista_achados}\n\n"
        f"Decisor:\nNome: {decisor_nome}\nCargo: {decisor_cargo}\nÁrea: {decisor_area}\n"
        f"Já interagiu antes (LinkedIn/WhatsApp): {'sim' if ja_interagiu else 'não'}"
    )


async def criar_estrategia(
    ia: ClienteIA,
    config: WorkerConfig,
    *,
    empresa_nome: str,
    resumo_dossie: list[str],
    achados: list[dict],
    decisor_nome: str,
    decisor_cargo: str,
    decisor_area: str,
    ja_interagiu: bool,
) -> tuple[Estrategia, Consumo, str]:
    conteudo = _conteudo(
        empresa_nome, resumo_dossie, achados, decisor_nome, decisor_cargo, decisor_area, ja_interagiu
    )
    estrategia, consumo = await ia.estruturado(
        modelo=config.model_strategy,
        sistema=carregar_prompt("strategist"),
        conteudo=conteudo,
        formato=Estrategia,
        effort="high",
        max_tokens=4000,
    )
    return estrategia, consumo, hash_entrada(conteudo)
