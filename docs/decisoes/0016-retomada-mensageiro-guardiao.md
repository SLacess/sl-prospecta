# ADR 0016 — Retomada do Mensageiro/Guardião com caixa conectada

**Data:** 19/11/2026 · **Status:** aceita

## Contexto

A ADR 0014 (18/11/2026) tirou o Mensageiro e o Guardião do escopo da Fase 3 porque não havia caixa de
e-mail aquecida: o vendedor aprova o texto na Caixa de Aprovação e envia manualmente, clicando em "Marcar
como enviada" só para registrar o evento na linha do tempo (§7.1). O ponto 5 daquela ADR deixou em aberto o
que fazer na Fase 4 (leitura de resposta) quando chegasse a hora.

Marcos decidiu retomar agora essa parte da Fase 3 com uma caixa conectada por OAuth, mesmo sem o
aquecimento/Workspace do runbook `infra/EMAIL-WARMUP.md` prontos do lado dele — o código fica pronto e a
conexão real é testada quando o Workspace existir.

## Decisão

1. **Mensageiro e Guardião voltam ao escopo**, divididos em 4 tarefas pequenas (cada uma com seu próprio
   plano e PR, mesmo ritmo das Fases 1-3):
   - Tarefa 1 (esta PR): caixa conectada por OAuth do Gmail — tabela `caixas_envio`, fluxo de conexão,
     painel para ver/ativar/desativar/remover. **Nenhum e-mail é enviado nesta tarefa.**
   - Tarefa 2: Guardião (supressão, opt-out, janela de horário, limite diário, checagem leve com
     `claude-haiku-5-5`).
   - Tarefa 3: Mensageiro (client de envio da Gmail API, log de envio, atualização de
     `Toque.enviado_em`/transição de estado que hoje só `marcar_enviado` faz).
   - Tarefa 4: disjuntores de envio e botão "Pausar tudo" (§13).
2. **A conexão é por OAuth guardado em banco (`caixas_envio`), não mais pela variável `OUTREACH_MAILBOXES`**
   do `.env` que o runbook original previa — o painel passa a ser a fonte da verdade de quais caixas
   existem, e dá para ativar/desativar sem reimplantar a aplicação. `refresh_token_criptografado` nunca sai
   em nenhuma resposta da API; criptografia em repouso com `cryptography.fernet` (nova dependência,
   `FIELD_ENCRYPTION_KEY` no `.env`), conforme CONSTITUICAO §15.1.
3. **Resolvendo o ponto 5 da ADR 0014:** o escopo OAuth já pede `gmail.send` **e** `gmail.readonly` na mesma
   conexão (como o runbook já antecipava) — a leitura serve, por ora, só para o disjuntor de bounce
   (Tarefa 4), não para classificar respostas. Classificar resposta (§9.5) continua sendo Fase 4.
4. **Lacuna conhecida e aceita por ora:** sem Google Postmaster Tools e sem Leitor de Respostas, os
   disjuntores de "reclamação de spam" e de "taxa de resposta negativa" (§13) não têm como ser 100%
   automáticos ainda. A Tarefa 4 implementa bounce automático (lendo a própria caixa) e um botão manual de
   "reportar reclamação de spam" que pausa tudo na hora — não um disjuntor automático de spam/resposta
   negativa. Revisitar quando a Fase 4 (Leitor de Respostas) ou o Postmaster Tools entrarem.
   - **O disjuntor de bounce também suprime** (CONSTITUICAO §15.1): ao detectar uma devolução, extrai o
     endereço do corpo da notificação (via `snippet` do Gmail — aproximação, sem Postmaster Tools) e, se
     bater com um destinatário recente da mesma caixa, adiciona à lista de supressão. Decisão confirmada
     com Marcos ao iniciar a Tarefa 4, para não insistir num e-mail morto enquanto a Fase 4 não resolve
     isso de forma mais robusta.

## Atualização (Tarefa 3)

O envio real pela Gmail API **não roda num job periódico automático** — dispara manualmente via
`python -m slp_workers.cli enviar`, mesmo padrão de `gerar-sequencia` e `avaliar-guardiao`, sempre
pré-visualizável com `--listar`. Decisão confirmada com Marcos ao iniciar a Tarefa 3: sem os disjuntores de
envio da Tarefa 4 ("Pausar tudo" incluído), um job automático enviaria e-mails reais sem rede de segurança
nenhuma. O disparo manual é a rede de segurança até a Tarefa 4 existir; revisitar automatizar depois dela.

## Atualização (Tarefa 4 — fecha a retomada)

Diferente da Tarefa 3 (envio manual via CLI), o disjuntor de bounce roda sozinho num cron do worker a
cada 15 minutos: ele só lê a caixa e, na pior hipótese, pausa o envio — nunca manda e-mail, então
automatizar aqui não tem o mesmo risco. "Pausar tudo" e "reportar spam" ficam disponíveis a qualquer
pessoa logada (admin ou vendedor) — é um freio de emergência, não deve esperar um admin estar disponível;
só retomar exige admin, por ser uma decisão deliberada depois de investigar o motivo.

## Consequências

- O runbook `infra/EMAIL-WARMUP.md` continua válido para o aquecimento e o projeto OAuth no Google Cloud
  Console; o item "cada caixa de `OUTREACH_MAILBOXES` autoriza o acesso uma vez" passa a ser, na prática, o
  fluxo `/caixas-envio/conectar` desta tarefa.
- Até a Tarefa 3 existir, a Caixa de Aprovação continua exatamente como está (texto "nada é enviado pela
  plataforma", botão "Marcar como enviada") — conectar uma caixa aqui não muda esse comportamento.
- Esta ADR não revoga a ADR 0014 por completo: os pontos 1-2 dela (Estrategista/Redator/Crítico, Caixa de
  Aprovação como está hoje) continuam valendo até a Tarefa 3 mudar o fluxo de envio.
