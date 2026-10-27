# ADR 0009 — Mapeador de decisores: Apollo + fontes públicas (Fase 2, Tarefa 2)

**Data:** 26/10/2026 · **Status:** aceita

## Contexto
O §7.3 (Etapa 4) pede até 3 contatos por empresa, com função, e-mail validado e LinkedIn só como link, e a regra
de multithreading (cada pessoa recebe o ângulo da sua área). O §6 indica o Haiku com busca de pessoas do Apollo e
validação de e-mail. Marcos pediu também a busca de decisores na internet. O CLAUDE.md (regra 7) e o §7.3 proíbem
automação no LinkedIn, e os extratores de perfis do LinkedIn (ex.: atores do Apify) violam os termos de uso;
por isso ficaram de fora (decisão de Marcos, 26/10/2026).

## Decisões
1. **Fluxo** (`workers/slp_workers/orchestrator/decisores.py`), para cada empresa em MAPEANDO_DECISORES:
   1. supressão do domínio (§15) e disjuntor de créditos;
   2. `organizations/enrich` (1 crédito, desligável por `APOLLO_ENRICH_ORG`): porte, UF e cidade;
   3. `mixed_people/api_search` (sem crédito): pessoas pelo domínio e pelos cargos de cada área (`config.decisores`);
   4. o Haiku (`MODEL_TRIAGE`) escolhe até 3, **uma por área**, na prioridade do setor;
   5. se faltarem áreas, **busca web em fontes públicas** (`MODEL_ANALYSIS` com `web_search`, até
      `DECISORES_MAX_WEB_SEARCHES` buscas) só para as áreas que faltam;
   6. `people/match` (1 crédito por pessoa) traz o e-mail profissional, sem e-mail pessoal nem telefone;
   7. grava em `contatos`, requalifica a empresa e, com ao menos 1 e-mail válido, passa para PREPARANDO_ABORDAGEM.
      Sem nenhum válido, fica em MAPEANDO_DECISORES com o evento `sem_decisores`.
2. **Anti-alucinação:** a escolha do Haiku só vale para `id`s da lista; área repetida, pessoa repetida e excesso
   são descartados. Da busca web só vale quem tem nome e sobrenome e `fonte_url` vista nos resultados, fora do
   LinkedIn. Um link de perfil do LinkedIn só é guardado se apareceu nos resultados.
3. **E-mail válido** = formato correto, no domínio da empresa (ou subdomínio), domínio com MX e `email_status`
   `verified` no Apollo. Outro status (não verificado, extrapolado, catch-all) vira `nao_verificado` e não conta.
   E-mail de outro domínio não é guardado (pode ser pessoal). E-mail na supressão não é gravado, e o evento não
   mostra o endereço.
4. **Créditos:** nova coluna `acoes_agentes.creditos`; cada chamada ao Apollo é uma ação registrada.
   `APOLLO_DAILY_CREDIT_CAP` (padrão 60, dia de Brasília) para o Mapeador antes de gastar: o job é adiado para
   o dia seguinte com o evento `fila_pausada_apollo`. Teto por empresa: 1 + 3 créditos.
5. **Sem chave do Apollo** o Mapeador registra `apollo_nao_configurado` e a empresa espera; nada quebra.
6. **Haiku sem fallback de recusa no servidor:** o cliente de IA não envia `fallbacks` para modelos Haiku.
7. **Painel:** seção "Decisores" na Ficha (situação do e-mail sempre em texto; LinkedIn e fonte pública como
   links). O perfil leitura vê o e-mail mascarado. Os créditos do dia aparecem ao lado do custo de IA.
8. **CLI:** `python -m slp_workers.cli decisores --pendentes [--listar]` e `--empresa <id>`; o `--listar`
   estima os créditos antes.

## Consequências
- O componente Acesso ao decisor do score passa a refletir os contatos válidos.
- Empresas sem e-mail verificado ficam em MAPEANDO_DECISORES; adicionar contatos à mão e os pedidos de titular
  (§15.1) ficam para uma tarefa própria.
- A busca web acrescenta cerca de R$ 0,05 a 0,15 por empresa quando acionada.
