# Testes de ponta a ponta e evals

- Testes unitários ficam junto de cada app (`apps/api/tests`, `apps/web/tests`).
- `tests/evals/` (Fase 3): conjunto de 30 prospects de referência com saídas esperadas, rodado a cada
  alteração de prompt (CONSTITUICAO §18).
- `tests/e2e/`: fluxos com Postgres e Redis reais (job `fluxo` do CI).
  - Fase 1: entrada → fila → Pesquisador (Claude e site simulados) → dossiê, confirmação do site e disjuntor de custo.
  - Fase 2: fluxo completo URL → dossiê → auditoria → score.

```bash
docker compose up -d postgres redis
cd apps/api && alembic upgrade head && cd ../..
FLOW_TESTS=1 PYTHONPATH=apps/api:workers pytest tests/e2e
```
