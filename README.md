# SL Prospecta

Departamento de SDR autônomo da **Sinal Link Acessibilidade** — prospecção com IA baseada em diagnóstico real de acessibilidade digital.

- 📜 Visão, regras e arquitetura: [`CONSTITUICAO.md`](CONSTITUICAO.md)
- 🤖 Instruções para agentes de código: [`CLAUDE.md`](CLAUDE.md)

## Status
**Fase 1 — Auditor + Pesquisador** (em andamento).

- ✅ Fase 0 — fundação: infraestrutura, autenticação, banco e deploy automático.
- ✅ Tarefa 1 — entrada e fila: prospecção individual por nome ou site, deduplicação por domínio,
  fila no worker, linha do tempo ao vivo no painel e disjuntor de custo diário de IA
  ([ADR 0002](docs/decisoes/0002-entrada-fila-disjuntor.md)).
- ⏳ Tarefas 2 a 4: Pesquisador (dossiê), Auditor (auditoria de acessibilidade) e mini-relatório PDF.

## Rodando localmente

Pré-requisitos: Docker e Docker Compose.

```bash
cp .env.example .env          # edite as senhas e chaves
docker compose up -d --build
docker compose exec api alembic upgrade head
docker compose exec api python -m app.cli create-admin --email voce@exemplo.com --name "Seu Nome"
```

- Painel: http://localhost:3000
- API: http://localhost:8000/docs
- Saúde: http://localhost:8000/health
- MinIO: http://localhost:9001

n8n (opcional): `docker compose --profile n8n up -d`

## Testes

```bash
cd apps/api && pip install -r requirements-dev.txt && pytest          # API
cd workers && pip install -r requirements-dev.txt && pytest           # worker
cd apps/web && npm ci && npm run build && npm run test:a11y           # painel (axe + teclado)
```

Fluxo com Postgres e Redis reais: veja [`tests/README.md`](tests/README.md).

## Deploy na VPS Hostinger

Veja o passo a passo em [`infra/DEPLOY.md`](infra/DEPLOY.md).

Resumo: `push` na `main` → GitHub Actions testa, gera as imagens, publica no GitHub Container Registry e faz deploy por SSH na VPS, com rollback automático se a verificação de saúde falhar.

## Estrutura

```
apps/api        FastAPI + Alembic
apps/web        Next.js (painel, CRM, microsite)
workers/        Workers Python (fila Redis)
packages/       prompts, esquemas, base de conhecimento
templates/      modelos de relatório, microsite e proposta
infra/          Caddy, scripts da VPS, deploy, backup
docs/           ADRs e compliance (LGPD)
```
