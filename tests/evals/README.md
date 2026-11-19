# Evals de prompt — Estrategista, Redator, Crítico

Roda a cada alteração de prompt em `packages/prompts/{strategist,copywriter,reviewer,voz-sinal-link}.md`
(CONSTITUICAO §18, "prompts são código"). Diferente de `workers/tests/`, que mocka toda chamada de IA,
aqui o próprio texto do prompt é o que está sob teste — por isso chama a API real da Claude e tem custo.

## Rodar

Teste de drift (sem custo, roda sempre — confirma que os `.schema.json` batem com os modelos Pydantic):
```bash
PYTHONPATH=workers pytest tests/evals/test_schemas_atualizados.py
```

Eval completo com os 30 casos (custo real de API, uns poucos reais):
```bash
ANTHROPIC_API_KEY=... PROMPT_EVALS=1 PYTHONPATH=workers pytest -s tests/evals/test_sequencia_evals.py
```

Só alguns casos, para uma verificação rápida:
```bash
ANTHROPIC_API_KEY=... PROMPT_EVALS=1 PYTHONPATH=workers pytest -s tests/evals/test_sequencia_evals.py -k "caso-01 or caso-07 or caso-26"
```

Sem `PROMPT_EVALS=1`, `test_sequencia_evals.py` nem é coletado (ver `collect_ignore_glob` em
`conftest.py`) — nunca roda em CI normal.

## O que o relatório mostra

Cada caso encadeia Estrategista → Redator → Crítico de verdade (`ClienteAnthropic`, sem mock) e confere:
limite de palavras do assunto/corpo, nenhuma das proibições do guia de voz, e se o achado escolhido pelo
Estrategista realmente aparece na mensagem. Esses checks fazem o teste falhar se quebrarem. A nota do
Crítico (0–10, o mínimo dos 8 critérios de §9.4) aparece no relatório, mas **não** falha o teste sozinha
— os `casos-armadilha` (ver `fixtures/README.md`) esperam nota baixa de propósito; quem lê o relatório
decide se algo precisa de ajuste no prompt.

Relatório completo (todos os casos, custo+tokens de cada chamada) em `relatorios/<timestamp>.json`
(git-ignorado).

## Arquivos

- `fixtures/casos-referencia.json` — os 30 prospects de referência.
- `schemas.py` — modelos Pydantic de `Estrategia`/`Redacao`/`Critica` (**provisórios**: a Tarefa 2 move
  para `workers/slp_workers/agents/{strategist,copywriter,reviewer}.py`).
- `relatorio.py` — checks determinísticos e formatação do relatório.
- `test_schemas_atualizados.py` / `test_sequencia_evals.py` — os dois testes.
