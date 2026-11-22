# ADR 0018 — Automatizar os catch-up jobs e checar a janela de horário do Mensageiro

**Data:** 22/11/2026 · **Status:** aceita

## Contexto

Um levantamento completo dos pontos onde o pipeline para e exige intervenção humana (pedido do Marcos,
depois de corrigirmos três lacunas pontuais na mesma sessão: decisor manual, confirmação de domínio na
ficha, e o botão "Tentar novamente") encontrou um padrão maior: quatro etapas do pipeline — qualificação,
mapeamento de decisores, geração de sequência e geração do mini-relatório em PDF — só avançavam se alguém
entrasse por SSH e rodasse o comando correspondente do `slp_workers.cli`. Nenhuma delas tem risco de loop
de falha (processam só o que nunca foi tentado) nem manda e-mail; cada uma já para sozinha no teto de
custo/crédito que já existia (`CustoDiarioEsgotado`, `CreditosEsgotados`, `OrcamentoApifyEsgotado`).

O mesmo levantamento também achou dois descuidos de escopo do trabalho anterior nesta sessão:
`auditoria_falhou` e `qualificacao_falhou` deveriam estar na lista de falhas retentáveis pela ficha
("Tentar novamente"), mas ficaram de fora por engano.

Por fim, confirmou que o Mensageiro (envio real de e-mail) nunca checa a janela de horário do §9.1
(terça a quinta, 8h–10h30 e 14h–16h) — nem no disparo manual de hoje.

## Decisão

1. **Cronar os quatro catch-up jobs sem risco** (`workers/slp_workers/main.py`): `qualificar_faltantes_job`,
   `mapear_decisores_job`, `gerar_sequencias_job`, `gerar_relatorios_job`. Cada um reaproveita a mesma
   lógica (consulta + laço) já testada do `slp_workers.cli`, importada diretamente — sem duplicar código
   de negócio, só a wiring do cron. Os dois sem custo de IA (`qualificar`, `relatorios`) rodam a cada 15
   min; os dois que gastam crédito do Apollo/Apify ou orçamento de IA (`decisores`, `gerar-sequencia`)
   rodam a cada 30 min, para não martelar as APIs externas.
2. **`auditoria_falhou` e `qualificacao_falhou` entram em `EVENTOS_DE_PROBLEMA`**
   (`apps/api/app/crm.py`) — e, por consequência, em `EVENTOS_RETENTAVEIS` (`apps/api/app/routers/ficha.py`,
   que já exclui explicitamente `confirmacao_dominio`/`dominio_ja_cadastrado` por terem resolução própria).
   Correção de escopo, não mudança de regra.
3. **Mensageiro passa a checar a janela de horário do §9.1** antes de avaliar o Guardião ou tentar enviar
   (`workers/slp_workers/orchestrator/mensageiro.py:dentro_da_janela_de_envio`) — mesmo no disparo manual
   de hoje. Fora da janela, o toque continua pendente (`"fora_da_janela_de_envio"`) para a próxima rodada;
   nada muda no texto nem é perdido. Usa `business_timezone` (fuso único, `America/Sao_Paulo`) — o §9.1
   fala em "horário do destinatário", mas não há hoje nenhum dado de fuso por contato; documentado como
   simplificação deliberada, não como o ideal final.
4. **O Mensageiro continua disparando só manualmente** (`python -m slp_workers.cli enviar`) — decisão já
   tomada conscientemente na ADR 0016 ("rede de segurança a mais além dos disjuntores"); este ADR não a
   reabre.
5. **Nenhum cron para `retomar`** (reenfileirar empresas travadas por falha de processamento). Sem um
   teto de tentativas novo, um cron martelaria para sempre uma empresa genuinamente bloqueada (ex.: um WAF
   recusando o identificador do Pesquisador, caso real encontrado com a Drogasil) a cada tick — o botão
   manual "Tentar novamente" já cobre esse caso por ora.

## Consequências

- O worker passa a ter 6 cron jobs em vez de 2; todos idempotentes e sem efeito colateral visível ao rodar
  "à toa" (processam só o que está pendente).
- A primeira vez que `mapear_decisores_job`/`gerar_sequencias_job` rodam sozinhos, o consumo de crédito do
  Apollo/orçamento de IA deixa de ser 100% dirigido por quando alguém lembra de rodar o comando — passa a
  acontecer em até 30 min depois que a empresa fica elegível. Vale acompanhar o painel de disjuntores nos
  primeiros dias.
- `teto_por_empresa` (adicionado a `EVENTOS_DE_PROBLEMA` numa mudança anterior desta mesma sessão) também
  ficou retentável por este ADR, sem ação extra — já estava coberto pela regra geral de
  `EVENTOS_RETENTAVEIS`.
