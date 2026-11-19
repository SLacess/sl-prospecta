"""Evals de prompt: chamam a API real da Claude (custo), por isso não rodam por padrão.

    ANTHROPIC_API_KEY=... PROMPT_EVALS=1 PYTHONPATH=workers pytest tests/evals

`test_schemas_atualizados.py` é a exceção: roda sempre (sem custo, sem chamada de rede), igual aos
testes do worker — confirma que os três `.schema.json` batem com os modelos Pydantic deste diretório.
"""

import json
import os
from pathlib import Path

import pytest

PASTA = Path(__file__).resolve().parent

collect_ignore_glob = [] if os.getenv("PROMPT_EVALS") else ["test_sequencia_evals.py"]


@pytest.fixture(scope="session")
def config():
    from slp_workers.settings import WorkerConfig

    return WorkerConfig()


@pytest.fixture(scope="session")
def cliente(config):
    from slp_workers.llm import ClienteAnthropic

    return ClienteAnthropic(config)


@pytest.fixture(scope="session")
def casos() -> list[dict]:
    texto = (PASTA / "fixtures" / "casos-referencia.json").read_text(encoding="utf-8")
    return json.loads(texto)


@pytest.fixture(scope="session")
def resultados_sessao():
    """Acumula o resultado de cada caso rodado para imprimir e salvar um relatório agregado ao final."""
    lista: list[dict] = []
    yield lista
    if lista:
        from relatorio import imprimir_relatorio, salvar_relatorio

        imprimir_relatorio(lista)
        caminho = salvar_relatorio(lista)
        print(f"\nRelatório completo em {caminho}")
