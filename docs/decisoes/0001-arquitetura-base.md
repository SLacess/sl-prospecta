# ADR 0001 — Arquitetura base da Fase 0

**Data:** 23/10/2026 · **Status:** aceita

## Contexto
A Constituição (§5, §16) define monorepo, FastAPI + Next.js + workers Python, Postgres com pgvector,
Redis e deploy em VPS Hostinger via Docker Compose e GitHub Actions.

## Decisões
1. **Fila com arq** (Redis, asyncio) em vez de Celery: mais leve, nativo assíncrono, suficiente para
   o volume inicial. Reavaliar se precisarmos de roteamento complexo de filas.
2. **SQLAlchemy 2 + Alembic** para modelo e migrações. Tabelas de cada fase entram em migrações próprias.
3. **Autenticação própria com JWT** (papéis admin, vendedor, leitura). Na Fase 1, o token passa a ser
   guardado em cookie httpOnly via rota do Next, em vez de `sessionStorage`.
4. **Caddy** como proxy reverso pelo HTTPS automático e configuração mínima.
5. **Imagens no GitHub Container Registry**, marcadas pelo hash curto do commit; deploy por SSH com
   verificação de saúde e rollback automático para a tag anterior.
6. **Testes de acessibilidade no CI** (axe-core via Playwright) bloqueiam o merge se o painel tiver violações
   WCAG 2.2 AA (§2.8).

## Consequências
- Rollback não reverte migrações: migrações devem ser retrocompatíveis.
- A imagem do worker crescerá na Fase 1 (Chromium para Playwright); avaliar um serviço `worker-audit`
  separado com concorrência limitada.
