"""Confirma que os esquemas publicados batem com os modelos Pydantic (CONSTITUICAO §18, prompts são
código). Mesmo padrão de workers/tests/test_pesquisador.py para dossie.schema.json.

Roda sempre: sem custo, sem chamada de rede. Precisa de PYTHONPATH=workers (os modelos agora moram em
slp_workers.agents, desde a Fase 3 Tarefa 2 — antes eram provisórios em tests/evals/schemas.py).
"""

import json
from pathlib import Path

from slp_workers.agents.copywriter import Redacao
from slp_workers.agents.reviewer import Critica
from slp_workers.agents.strategist import Estrategia

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
