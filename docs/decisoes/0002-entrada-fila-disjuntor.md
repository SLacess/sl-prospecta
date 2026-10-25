# ADR 0002 — Entrada individual, fila e disjuntor de custo (Fase 1, Tarefa 1)

**Data:** 24/10/2026 · **Status:** aceita

## Contexto
A Fase 1 começa pela entrada "Nome da empresa ou site" (§7.2) e pela fila que levará cada empresa ao
Pesquisador e ao Auditor (tarefas 2 a 4). O §13 exige um disjuntor que pare a operação quando o custo
diário de IA/dados passar do teto configurado.

## Decisões
1. **`POST /prospeccao`** interpreta a entrada (`app/domain.py`). Um endereço vira um domínio normalizado
   (sem esquema, `www.`, porta e caminho, em minúsculas e IDNA). A empresa nasce em `NOVO`, com
   `fonte = manual`.
2. **Deduplicação por domínio**, já único no banco desde a 0001. Uma entrada repetida não cria empresa:
   registra `entrada_duplicada` na linha do tempo da existente. Quando a entrada é só o nome, o domínio
   fica vazio até o Pesquisador resolvê-lo, e a deduplicação compara o nome entre as empresas ainda sem
   domínio.
3. **Job `processar_empresa` no arq**, com `job_id` fixo por empresa. O arq ignora um segundo envio
   enquanto houver job ou resultado guardado, então reenviar não processa em dobro. Se o Redis estiver
   fora, a API responde 503 e registra `falha_enfileirar`; reenviar a mesma entrada recoloca a empresa
   na fila.
4. **Nesta tarefa a empresa continua em `NOVO`** depois do job. O orquestrador só registra
   `processamento_iniciado` e `aguardando_pesquisador`. A transição para `PESQUISANDO` entra com o
   Pesquisador: mudar de estado sem quem execute a etapa deixaria o prospect preso. A tabela de
   transições automáticas do §7.1 já existe em `orchestrator/pipeline.py`.
5. **Disjuntor de custo:**
   - O custo do dia é `SUM(acoes_agentes.custo)` desde 00h00 de Brasília, com o custo em **reais**.
     O teto vem de `DAILY_AI_BUDGET_BRL` (padrão R$ 30) e o disjuntor dispara quando o custo do dia
     é **≥ teto**.
   - **Worker:** o decorador `@requires_ai_budget` roda antes de cada job de IA. Com o teto atingido,
     o job não executa; volta para a fila com `Retry`, adiado até 00h05, e a pausa vira o evento
     `fila_pausada_custo`. Nada se perde: o job tem 45 tentativas, cerca de um mês de pausas diárias.
   - **API e painel:** `GET /governanca/disjuntores` alimenta um aviso persistente no painel, e a
     resposta de `POST /prospeccao` traz `fila_pausada`.
   - A regra existe em dois lugares (`apps/api/app/budget.py` e `workers/.../budget.py`) porque API e
     worker são imagens separadas. O teste de fluxo cobre os dois.
6. **Progresso ao vivo por consulta periódica**, a cada 2 s, por até cerca de 5 minutos, em vez de
   WebSocket (§5). Funciona com o token Bearer atual e não exige nada novo no Caddy. O WebSocket (ou
   SSE) entra quando houver lotes (Fase 2), em que o volume de consultas pesaria.
7. **Acesso do worker ao banco** por tabelas mínimas em SQLAlchemy Core (`slp_workers/db.py`), sem
   importar o app da API. O job `fluxo` do CI roda o worker contra o banco migrado pelo Alembic e
   falha se essas definições divergirem.
8. **O token continua em `sessionStorage`.** A migração para cookie httpOnly, prevista no ADR 0001,
   vira uma tarefa própria de segurança, para manter este PR pequeno.

## Consequências
- A migração 0002 só cria `dossies` e `auditorias` (mais índices em `acoes_agentes.criado_em` e
  `eventos(empresa_id, ocorrido_em)`), então o rollback de imagem para a Fase 0 continua seguro.
- Os textos da linha do tempo ficam em `eventos.dados_json.mensagem`, escritos por quem registra o
  evento. O painel só os exibe e anuncia.
- Com teto `0`, o disjuntor fica sempre aberto, o que serve para testar o comportamento sem gerar custo
  fictício.
