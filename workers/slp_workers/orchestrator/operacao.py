"""Estado de pausa da operação de envio (CONSTITUICAO §13; ADR 0016, Tarefa 4).

Mesma chave "operacao" da tabela `config` que `app/operacao.py` da API lê/escreve para o painel — cada
lado tem sua própria cópia desta lógica, porque o worker não importa o app da API (CONSTITUICAO §6), igual
ao disjuntor de custo de IA (`orchestrator/budget.py`/`app/budget.py`).
"""

from datetime import UTC, datetime

from sqlalchemy import Engine, select, update

from slp_workers.db import config

CHAVE_OPERACAO = "operacao"


def esta_pausado(engine: Engine) -> bool:
    with engine.connect() as conn:
        valor = conn.scalar(select(config.c.valor_json).where(config.c.chave == CHAVE_OPERACAO))
    return bool(valor and valor.get("pausado"))


def pausar(engine: Engine, *, motivo: str, origem: str) -> None:
    """`pausado_por` fica nulo: quem acionou foi o disjuntor, não um humano."""
    valores = {
        "pausado": True, "motivo": motivo, "pausado_em": datetime.now(UTC).isoformat(),
        "pausado_por": None, "origem": origem,
    }
    _gravar(engine, valores)


def retomar(engine: Engine) -> None:
    _gravar(engine, {"pausado": False})


def _gravar(engine: Engine, valores: dict) -> None:
    with engine.begin() as conn:
        linhas = conn.execute(
            update(config).where(config.c.chave == CHAVE_OPERACAO).values(valor_json=valores)
        ).rowcount
        if linhas == 0:
            conn.execute(config.insert().values(chave=CHAVE_OPERACAO, valor_json=valores))
