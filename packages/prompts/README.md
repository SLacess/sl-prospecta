# Prompts

Prompts versionados por agente — **prompts são código** (CONSTITUICAO §18).

- Um arquivo por agente: `researcher.md`, `auditor.md`, `strategist.md`, `copywriter.md`, `reviewer.md`, etc.
- Cabeçalho obrigatório em cada arquivo: versão, modelo padrão, esquema de saída (em `packages/schemas`), teto de custo.
- O guia de voz Sinal Link (§9.1) fica em `voz-sinal-link.md` e é injetado em todos os prompts de redação (com prompt caching).
- Nenhuma alteração vai para produção sem rodar os evals (`tests/evals`, a partir da Fase 3).

Ponto de partida do Redator: CONSTITUICAO §21.1.
