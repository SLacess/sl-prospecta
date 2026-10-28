# ADR 0012 — Caminho alternativo com Apify quando o Apollo não está disponível

**Data:** 28/10/2026 · **Status:** aceita

## Contexto
No lote de 100 empresas da Fase 2, o plano do Apollo esgotou os créditos do ciclo no meio do processamento
(`BILLING.LIMIT.CREDITS_EXHAUSTED`) e 82 empresas ficaram com "mapeamento falhou". Marcos pediu usar o Apify
quando o Apollo não puder ser usado. O CLAUDE.md (regra 7) proíbe automação no LinkedIn e o LIA exige coleta
mínima (só dados profissionais).

## Decisões
1. **Quando entra:** Apollo sem chave (`APOLLO_API_KEY` vazia) ou sem créditos no plano (422/402 com código de
   créditos). O "sem créditos" deixa de virar falha. Erros passageiros do Apollo (5xx, tempo esgotado) continuam
   com novas tentativas, para um soluço não trocar de fonte. O teto diário de créditos (`APOLLO_DAILY_CREDIT_CAP`)
   continua pausando como antes.
2. **Atores avaliados no Apify:**
   - "Domínio → decisores com e-mail" (ex.: `b2bsearch/domain-to-decision-makers`, `scalelist/domain-email-finder`):
     **recusados**, porque devolvem link do LinkedIn e até e-mail pessoal, o que indica dados do LinkedIn.
   - Raspadores de contato de sites: **recusados** (e-mails genéricos e telefones, sem o decisor).
   - Verificador `bounceverify/bounceverify-email-verifier`: **adotado** (SMTP, catch-all, função, descartável e
     provedor gratuito; US$ 0,00089 por e-mail). Formato da saída conferido numa execução real.
3. **Fluxo alternativo:** quem ocupa cada cargo vem, quando há chave, da **busca de pessoas do Apollo, que não gasta
   crédito** (primeiro nome, sobrenome abreviado como "M***e" e cargo); o Haiku escolhe uma pessoa por área e uma
   busca web dirigida confirma o nome completo em fonte pública (`mapeador-nomes`), aceito só com o mesmo primeiro
   nome e um sobrenome com as letras da abreviação. Sem ninguém na busca do Apollo (ou sem chave), vale a busca web
   genérica em fontes públicas (sem LinkedIn), até 3 áreas pela prioridade do setor. Em seguida → até 5 candidatos
   de e-mail por pessoa pelos padrões comuns (`nome.sobrenome@`, `nsobrenome@`, `nome@`...) → uma execução do
   verificador para todos → contato com `fonte = "web+apify"` e a URL da fonte pública.
4. **E-mail válido** só com `status = valid`, SMTP confirmado e sem catch-all, função, descartável ou gratuito.
   Catch-all ou incerto vira "não verificado" e não serve para envio (§15.2). Os endereços testados e recusados não
   são guardados; a ação registra só contagens.
5. **Por que não verificar SMTP na nossa VPS:** provedores costumam bloquear a porta 25, e sondar SMTP do nosso IP
   prejudicaria a reputação do domínio de envio da Fase 3.
6. **Custos:** a ação `mapeador.apify` guarda o custo em reais (como a IA) e entra no disjuntor de IA. Há também o
   teto próprio `APIFY_DAILY_BUDGET_USD` (padrão US$ 2/dia): atingido, o job espera o dia seguinte com o evento
   `fila_pausada_apify`. O painel mostra o gasto do dia.
7. **Segredo:** `APIFY_TOKEN` no `.env` (local e VPS), nunca no repositório.

## Consequências
- Menos e-mails válidos do que com o Apollo: depende de o nome aparecer em fonte pública e de o domínio não ser
  catch-all (comum em empresas grandes).
- Cerca de US$ 0,013 de Apify e até R$ 0,90 de busca web por empresa (completar nome + busca genérica).
- Teste real (Rede Santa Catarina, ZF): 0 nomes confirmados em fonte pública. O caminho é rede de segurança,
  não substituto do Apollo. O domínio de e-mail corporativo pode diferir do site (ex.: redesc.org.br), e os
  candidatos usam só o domínio do site.
- O LIA registra a inferência de e-mail com verificação, só no domínio corporativo.
