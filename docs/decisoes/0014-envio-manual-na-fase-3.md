# ADR 0014 — Fase 3 sem Mensageiro automático: envio manual pelo vendedor

**Data:** 18/11/2026 · **Status:** aceita

## Contexto
A trilha comercial paralela (Guia de Construção, Etapa 3) exigia caixas de e-mail aquecidas antes da Fase 3,
porque o Mensageiro (§15.2, §13) enviaria pela Gmail API usando `OUTREACH_MAILBOXES` com OAuth. Marcos decidiu
seguir o projeto sem montar essa infraestrutura de e-mail por ora: o texto aprovado é enviado manualmente pelo
vendedor, e o restante da Fase 3 segue como planejado.

## Decisão
1. **Estrategista, Redator e Crítico continuam como planejado** (§9.1–§9.4): geram o ângulo por persona, a
   sequência de toques e passam pelo Crítico, com os evals de 30 prospects de referência.
2. **Caixa de Aprovação entrega o texto pronto, não dispara o envio.** Depois de aprovado, o painel mostra
   (ou copia) o texto final para o vendedor enviar pela própria caixa de e-mail, fora da plataforma.
3. **Mensageiro e Guardião (envio automático, limite diário por caixa, disjuntores de bounce/spam) ficam fora
   de escopo por ora.** Não há caixa aquecida, não há `GOOGLE_OAUTH_CLIENT_ID/SECRET`/`OUTREACH_MAILBOXES`
   configurados, e os disjuntores do §13 ligados a volume de envio (bounce, spam) não se aplicam a um envio
   manual, um e-mail por vez.
4. **O registro do envio em si (quando, para quem) precisa de alguma forma de confirmação manual** — a decidir
   na tarefa da Caixa de Aprovação: um botão "marquei como enviado" ou campo de data, por exemplo. Sem isso, a
   linha do tempo do prospect (§7.3) fica sem o evento de envio.
5. **Leitura de respostas (Fase 4) ainda em aberto** — decidir quando chegar nessa fase: se também fica manual
   (vendedor registra a resposta à mão) ou se passa a precisar de ao menos uma caixa conectada por leitura,
   mesmo sem aquecimento para volume.

## Consequências
- A trilha comercial de e-mail (domínio secundário, aquecimento, SPF/DKIM/DMARC — `infra/EMAIL-WARMUP.md`) não
  é mais pré-requisito bloqueante da Fase 3. Fica documentada para quando o volume justificar automatizar o
  envio.
- Critério de saída da Fase 3 ("50 e-mails aprovados... bounce abaixo de 2%, nenhuma reclamação de spam") não
  se aplica da mesma forma a envio manual — precisa ser revisto quando a tarefa 4 da Fase 3 for planejada.
- Sem Mensageiro, os disjuntores automáticos de bounce/spam do §13 não têm o que medir; o controle de volume e
  cadência passa a ser o próprio vendedor.
