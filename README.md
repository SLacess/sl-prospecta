# SL Prospecta

Departamento de SDR autônomo da **Sinal Link Acessibilidade** — prospecção com IA baseada em diagnóstico real de acessibilidade digital.

- 📜 Visão, regras e arquitetura: [`CONSTITUICAO.md`](CONSTITUICAO.md)
- 🤖 Instruções para agentes de código: [`CLAUDE.md`](CLAUDE.md)

## Status
**Fase 0 — Fundação.** Infraestrutura, autenticação, banco e deploy automático.

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
