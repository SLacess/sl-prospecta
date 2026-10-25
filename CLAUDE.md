# CLAUDE.md — Instruções para agentes de código

Você está trabalhando na **SL Prospecta**, o departamento de SDR autônomo da Sinal Link Acessibilidade.
A fonte da verdade é o arquivo `CONSTITUICAO.md`. Leia as seções relevantes antes de implementar algo novo.
Em caso de conflito, a Constituição vence este arquivo.

## O produto em uma frase
Recebe o nome ou o site de uma empresa (ou uma planilha), pesquisa, audita a acessibilidade real do site,
qualifica pelo ICP, encontra decisores, escreve uma abordagem humana baseada em evidência, conversa,
agenda e gera proposta — com o vendedor acompanhando tudo num CRM visual.

## Regras que você nunca quebra
1. **Honestidade técnica (§2.2):** nenhum texto gerado pode dizer que o plugin torna um site "100% acessível"
   ou garante conformidade legal. Auditorias automáticas detectam apenas parte das barreiras.
2. **Evidência antes de argumento (§2.1):** nenhuma mensagem é enviada sem um achado real da auditoria.
3. **Nada sai sem Crítico + supressão (§9.4, §15):** todo envio passa pelo agente Crítico e pela lista de supressão.
4. **Agentes não escrevem no banco (§6):** devolvem JSON validado ao orquestrador, que persiste.
5. **Toda ação de IA é registrada** em `acoes_agentes` (modelo, tokens, custo, raciocínio resumido).
6. **Acessibilidade em casa (§2.8):** toda interface segue WCAG 2.2 AA — rótulos, foco visível, contraste,
   navegação por teclado, status nunca indicado só por cor.
7. **Sem raspagem que viole termos de uso:** nada de automação no LinkedIn. Respeite `robots.txt` e 1 req/s por domínio.
8. **A IA nunca inventa preço:** propostas usam só a tabela de preços em `config`.
9. **Segredos nunca no repositório.** Use `.env` (local/VPS) e GitHub Secrets (CI).

## Mapa do repositório
| Caminho | O que é |
|---|---|
| `apps/api` | FastAPI (Python 3.12): rotas, autenticação, governança, webhooks. Migrações Alembic em `migrations/` |
| `apps/web` | Next.js (App Router, TypeScript): painel, CRM, microsite, proposta web |
| `workers/` | Workers Python com fila Redis (arq): orquestrador, agentes, auditoria, envio, documentos |
| `packages/prompts` | Prompts versionados por agente (`<agente>.md`) — prompts são código |
| `packages/schemas` | Esquemas JSON de entrada/saída dos agentes |
| `packages/knowledge` | Base regulatória e biblioteca de objeções (resumos próprios) |
| `templates/` | Modelos HTML de relatório, microsite e proposta |
| `infra/` | Caddyfile, scripts de setup da VPS, deploy com rollback, backup |
| `docs/decisoes` | ADRs — registre toda decisão arquitetural relevante |

## Comandos
```bash
cp .env.example .env                      # preencha os valores
docker compose up -d --build              # sobe tudo localmente
docker compose exec api alembic upgrade head
docker compose exec api python -m app.cli create-admin --email voce@exemplo.com --name "Seu Nome"

# testes da API (sem Docker)
cd apps/api && pip install -r requirements-dev.txt && pytest
# web
cd apps/web && npm install && npm run dev
```

## Convenções
- Código, nomes de variáveis e commits técnicos em **inglês**; interface, prompts de cliente e documentação em **português**.
- Conventional Commits (`feat:`, `fix:`, `chore:`...). PRs pequenos. `main` protegida.
- Toda saída de agente: modelo Pydantic + campo `raciocinio_resumido`.
- Modelos padrão: `claude-haiku-5-5` (triagem), `claude-sonnet-5-5` (análise), `claude-opus-5-5` (estratégia, redação, proposta).
  Sempre configuráveis, nunca fixos no código de negócio.
- Novo prompt ou alteração de prompt → rodar os evals (`tests/evals`, a partir da Fase 3).
- Estados do prospect seguem exatamente a máquina de estados do §7.1. Não crie estados novos sem emendar a Constituição.

## Fase atual
**Fase 1 — Auditor + Pesquisador** (§19): entrada por nome/URL, fila, dossiê, auditoria completa, mini-relatório PDF.
Critério para avançar: 20 auditorias revisadas por Marcos com ≥ 90% de achados corretos.
Próxima: **Fase 2 — Qualificação + Decisores + Lote**. Não antecipe funcionalidades de fases futuras sem pedido explícito.
