# Testes de ponta a ponta e evals

- Testes unitários ficam junto de cada app (`apps/api/tests`, `apps/web/tests`).
- `tests/evals/` (Fase 3): conjunto de 30 prospects de referência com saídas esperadas, rodado a cada
  alteração de prompt (CONSTITUICAO §18).
- `tests/e2e/` (Fase 2): fluxo completo URL → dossiê → auditoria → score em ambiente de teste.
