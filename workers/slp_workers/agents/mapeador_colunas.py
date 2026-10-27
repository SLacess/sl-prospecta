"""Mapeador de colunas da planilha (CONSTITUICAO §7.2, entrada 2: "a IA identifica sozinha quais colunas são
empresa, site, CNPJ, cidade, contato").

Vê só os cabeçalhos e até 3 exemplos por coluna, com e-mails mascarados (coleta mínima, §15.1). A saída é
validada aqui: índice fora da planilha ou coluna repetida é descartado.
"""

import json

from pydantic import BaseModel

from slp_workers.agents.researcher import carregar_prompt, hash_entrada
from slp_workers.llm import ClienteIA, Consumo
from slp_workers.settings import WorkerConfig

CAMPOS = ("empresa", "site", "cnpj", "cidade", "uf", "contato_nome", "contato_cargo", "contato_email")


class MapeamentoColunas(BaseModel):
    empresa: int | None
    site: int | None
    cnpj: int | None
    cidade: int | None
    uf: int | None
    contato_nome: int | None
    contato_cargo: int | None
    contato_email: int | None
    raciocinio_resumido: str


def validar(mapa: MapeamentoColunas, colunas: int) -> tuple[dict[str, int | None], int]:
    limpo: dict[str, int | None] = {}
    usadas: set[int] = set()
    descartados = 0
    for campo in CAMPOS:
        valor = getattr(mapa, campo)
        if valor is not None and (not 0 <= valor < colunas or valor in usadas):
            descartados += 1
            valor = None
        if valor is not None:
            usadas.add(valor)
        limpo[campo] = valor
    return limpo, descartados


def combinar(regras: dict, ia: dict) -> dict[str, int | None]:
    """A IA completa o que as regras não acharam; o que as regras acharam pelo cabeçalho fica."""
    final = {c: regras.get(c) for c in CAMPOS}
    usadas = {v for v in final.values() if v is not None}
    for campo in CAMPOS:
        valor = ia.get(campo)
        if final[campo] is None and valor is not None and valor not in usadas:
            final[campo] = valor
            usadas.add(valor)
    return final


async def mapear(
    ia: ClienteIA, config: WorkerConfig, colunas: list[dict]
) -> tuple[dict[str, int | None], MapeamentoColunas, Consumo, str, int]:
    conteudo = "Colunas da planilha:\n" + json.dumps(colunas, ensure_ascii=False, indent=1)
    mapa, consumo = await ia.estruturado(
        modelo=config.model_triage,
        sistema=carregar_prompt("mapeador-colunas"),
        conteudo=conteudo,
        formato=MapeamentoColunas,
        effort="low",
        max_tokens=1500,
    )
    validado, descartados = validar(mapa, len(colunas))
    return validado, mapa, consumo, hash_entrada(conteudo), descartados
