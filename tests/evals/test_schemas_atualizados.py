"""Confirma que os esquemas publicados batem com os modelos Pydantic (CONSTITUICAO §18, prompts são
código). Mesmo padrão de workers/tests/test_pesquisador.py para dossie.schema.json.

Roda sempre: sem custo, sem chamada de rede.
"""

import json
from pathlib import Path

from schemas import Critica, Estrategia, Redacao

RAIZ = Path(__file__).resolve().parents[2]


def _ler(nome: str) -> dict:
    caminho = RAIZ / "packages" / "schemas" / f"{nome}.schema.json"
    return json.loads(caminho.read_text(encoding="utf-8"))


def test_estrategia_schema_atualizado():
    assert _ler("estrategia") == Estrategia.model_json_schema()


def test_redacao_schema_atualizado():
    assert _ler("redacao") == Redacao.model_json_schema()


def test_critica_schema_atualizado():
    assert _ler("critica") == Critica.model_json_schema()
