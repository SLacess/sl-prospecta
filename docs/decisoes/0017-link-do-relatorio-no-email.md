# ADR 0017 — Link do relatório no e-mail do Redator

**Data:** 21/11/2026 · **Status:** aceita

## Contexto

No teste real de ponta a ponta (envio para marcos@sinallink.com.br), Marcos pediu que o e-mail gerado
pelo Redator passe a incluir um link para o relatório de acessibilidade, com uma explicação do que é esse
relatório. Até aqui o Redator escrevia sem nenhum link — limitação já documentada no código
(`workers/slp_workers/orchestrator/sequencia.py`: "Não existe link público de diagnóstico ainda").

A CONSTITUICAO já previa exatamente isso: §17 reserva uma tabela `microsites (id, empresa_id, slug,
expira_em, metricas_json)`, e §21.1 já lista "Link do diagnóstico: {url_microsite}" como um dos dados que
o Redator deveria receber. O `copywriter.py` do worker já tinha o parâmetro `link_diagnostico` pronto, e o
prompt (`packages/prompts/copywriter.md`) já instruía usar "o link do diagnóstico (microsite ou
relatório)" como parte da "oferta do diagnóstico sem compromisso" — só nunca tinha sido preenchido.

## Decisão

1. **Fatia mínima da tabela `microsites` do §17**, sem o que ainda é Fase 5 (simuladores, vídeo de
   teclado, score de intenção, `metricas_json` de engajamento): só `id, empresa_id, auditoria_id, slug,
   expira_em, criado_em`. Isso deixa a tabela pronta para a Fase 5 crescer em cima dela, em vez de algo
   que precisaria ser refeito depois.
2. **O link aponta para o relatório que já existe** — reaproveita 100% o HTML com imagens/fontes
   embutidas que `apps/api/app/routers/ficha.py` já gera para o painel, só que atrás de uma rota nova,
   deliberadamente pública (`GET /diagnostico/{slug}`, sem login), em vez de construir uma página nova.
3. **`slug` aleatório (`secrets.token_urlsafe(24)`) em vez de login** — é assim que a CONSTITUICAO §17
   pensa o microsite: um link pessoal, não uma área autenticada. Expira em 120 dias (mesmo prazo que a
   CONSTITUICAO já define), verificado na própria consulta ao banco.
4. **Um microsite por relatório, não por contato** — o worker reaproveita o mesmo `slug` para todos os
   contatos da mesma empresa que recebem a mesma auditoria, gerado (ou reaproveitado) uma vez em
   `Sequencia.executar()`, antes do Redator escrever.
5. **Nenhuma mudança no prompt do Redator** — ele já sabia o que fazer com o link; era só wiring (`.env`
   `API_PUBLIC_BASE_URL` + a lógica de gerar o link). Sem mudança de prompt, sem necessidade de rodar os
   evals (`tests/evals`).
6. **Sem `API_PUBLIC_BASE_URL` configurada, nada muda**: `link_diagnostico` continua `None`, o Redator
   escreve sem link — mesmo comportamento de antes desta ADR.

## Lacuna conhecida e aceita por ora

A CONSTITUICAO também menciona um "link de opt-out" no microsite — isso **não** foi construído agora
(seria um fluxo de descadastro automático, tarefa maior). O e-mail já tem uma linha de descadastro em
texto (instrução já existente no prompt do Redator); é isso que vale até a Fase 5 trazer um opt-out de
verdade.

## Consequências

- Nova tabela `microsites` (migração 0012) e rota pública `/diagnostico/{slug}` na API — a primeira rota
  do projeto que não exige `Depends(get_current_user)`; qualquer alteração futura em `app/deps.py` ou
  middleware de auth global precisa continuar excluindo essa rota deliberadamente.
- `achado_pagina_url` (o link da página do achado no site do próprio prospect) continua sendo só contexto
  para o Redator/Crítico, nunca embutido no corpo como link clicável — o regex de "máximo 1 link no
  primeiro contato" do Guardião (`MAX_LINKS_PRIMEIRO_CONTATO`) já cobre o caso de ambos aparecerem juntos.
