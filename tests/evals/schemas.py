"""Modelos de saída do Estrategista, Redator e Crítico (Fase 3, Tarefa 1).

Provisórios: moram aqui porque o harness de evals precisa deles para chamar a API real da Claude, e a
Tarefa 2 ainda não existe. Quando os módulos `workers/slp_workers/agents/{strategist,copywriter,reviewer}.py`
forem criados, estes modelos devem ser movidos para lá (ou importados de lá) e o teste de drift deste
diretório passa a comparar contra o modelo definitivo, no mesmo padrão de
`workers/tests/test_pesquisador.py` para `Dossie`.

Os esquemas publicados ficam em packages/schemas/{estrategia,redacao,critica}.schema.json — gerados
destes modelos, nunca escritos à mão (CONSTITUICAO §18, "prompts são código").
"""

from typing import Literal

from pydantic import BaseModel, Field

Angulo = Literal[
    "experiencia_cliente",
    "inclusao_colaboradores_pcd",
    "esg_reputacao",
    "conformidade_legal",
    "conversao_alcance_mercado",
]
Persona = Literal["ti", "rh_di", "marketing_digital", "esg", "juridico_compliance"]


class Toque(BaseModel):
    dia: int
    canal: Literal["email", "linkedin", "whatsapp"]
    conteudo_sugerido: str


# Esquema publicado em packages/schemas/estrategia.schema.json (CONSTITUICAO §7.3 Etapa 5).
class Estrategia(BaseModel):
    persona: Persona
    angulo: Angulo
    achado_titulo: str
    achado_pagina_url: str
    gancho_justificativa: str
    canal_e_cadencia: list[Toque]
    raciocinio_resumido: str


# Esquema publicado em packages/schemas/redacao.schema.json (CONSTITUICAO §21.1).
class Redacao(BaseModel):
    assunto: str
    corpo: str
    fatos_usados: list[str]
    angulo: Angulo
    raciocinio_resumido: str


class CriteriosCritico(BaseModel):
    especificidade: int = Field(ge=0, le=10)
    veracidade: int = Field(ge=0, le=10)
    humanidade: int = Field(ge=0, le=10)
    clareza: int = Field(ge=0, le=10)
    valor: int = Field(ge=0, le=10)
    honestidade: int = Field(ge=0, le=10)
    brevidade: int = Field(ge=0, le=10)
    acessibilidade: int = Field(ge=0, le=10)


# Esquema publicado em packages/schemas/critica.schema.json (CONSTITUICAO §9.4, §7.3 Etapa 6).
class Critica(BaseModel):
    criterios: CriteriosCritico
    nota: int = Field(
        ge=0, le=10, description="O menor valor entre os critérios, não a média"
    )
    aprovado: bool
    motivo: str
    raciocinio_resumido: str
