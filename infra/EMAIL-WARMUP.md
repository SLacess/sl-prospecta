# Domínio de prospecção e aquecimento de e-mail — passo a passo

Tempo estimado: 1 dia de configuração + 2 a 4 semanas de aquecimento antes da Fase 3.
Pré-requisito da Fase 3 (Guia de Construção, Etapa 3): caixas aquecidas, nota alta no mail-tester
e nenhuma reclamação de spam. O critério de saída da própria Fase 3 exige bounce < 2%.

Referências na CONSTITUICAO.md: §15.2 (entregabilidade — domínio secundário, SPF/DKIM/DMARC, limite de envio)
e §13 (disjuntores automáticos que pausam todo envio uma vez em produção: bounce > 3% em 24h, reclamação
de spam > 0,1%, resposta negativa/irritada > 5% numa campanha, custo diário de IA/dados acima do teto, ou
erro de veracidade do Crítico numa mensagem já enviada). Esses disjuntores são código da Fase 3, não fazem
parte deste runbook — citados aqui só para você saber o que vem depois do aquecimento.

## 1. Domínio secundário
- Registre um domínio parecido com o principal, nunca o principal (ex.: `sinallink-acessibilidade.com.br`
  se o principal for `leadfactory.com.br`). Um domínio novo queimado por spam não compromete `app.`/`api.`/`diagnostico.`.
- Aponte esse domínio para uma página simples que redirecione para o site institucional da Sinal Link —
  um domínio de prospecção sem nenhum conteúdo parece spam para os filtros.

## 2. Google Workspace
- Crie um Workspace novo nesse domínio secundário.
- Crie 2 ou 3 caixas com nomes de pessoas reais da equipe (ex.: `marcos@`, `jose@`), nunca `contato@`/`vendas@` —
  remetente genérico cai em spam com mais facilidade.
- Essas caixas vão para a variável `OUTREACH_MAILBOXES` no `.env` (uma lista separada por vírgula).

## 3. DNS — SPF, DKIM, DMARC
No painel do Workspace (**Admin console → Apps → Google Workspace → Gmail → Autenticação de e-mail**), gere os
três registros e cadastre no DNS do domínio secundário:

| Registro | Tipo | Valor |
|---|---|---|
| SPF | TXT (raiz) | `v=spf1 include:_spf.google.com ~all` |
| DKIM | TXT (`google._domainkey`) | a chave que o Workspace gerar |
| DMARC | TXT (`_dmarc`) | `v=DMARC1; p=none; rua=mailto:dmarc@SEU_DOMINIO_SECUNDARIO` |

Comece o DMARC em `p=none` (só monitora) nas primeiras 2 semanas; depois que o volume subir sem rejeições,
suba para `p=quarantine` antes da Fase 3. Nunca comece em `p=reject` — um erro de configuração descarta
e-mails legítimos sem aviso.

## 4. OAuth para o Mensageiro (Gmail API)
O Mensageiro (Fase 3) envia pela Gmail API, não por SMTP direto — por isso o `.env` tem
`GOOGLE_OAUTH_CLIENT_ID`/`GOOGLE_OAUTH_CLIENT_SECRET` em vez de usuário/senha de e-mail.

1. No [Google Cloud Console](https://console.cloud.google.com), crie um projeto (pode ser o mesmo Workspace).
2. Ative a **Gmail API** (APIs e serviços → Biblioteca).
3. Configure a **tela de consentimento OAuth** como interna (restrita ao seu Workspace) — evita a revisão
   de app público do Google.
4. Crie uma credencial **OAuth client ID** do tipo "Aplicativo Web"; escopos mínimos: `gmail.send` (enviar) e
   `gmail.readonly` (ler respostas para o Leitor de Respostas, Fase 4).
5. Client ID e client secret vão para `GOOGLE_OAUTH_CLIENT_ID`/`GOOGLE_OAUTH_CLIENT_SECRET` no `.env` da VPS.
6. Cada caixa de `OUTREACH_MAILBOXES` autoriza o acesso uma vez (fluxo OAuth) quando o painel pedir —
   isso ainda não existe no código: é a tela que a Fase 3 (Mensageiro e Guardião) vai construir.

## 5. Aquecimento (warm-up)
- Sem aquecimento, caixa nova cai direto na caixa de spam — reserve 2 a 4 semanas antes da Fase 3.
- Duas formas, pode combinar as duas:
  - **Serviço de warm-up automático** (ex.: Mailwarm, Warmup Inbox, Instantly) — manda e simula resposta a
    e-mails reais em outras caixas, subindo o volume sozinho.
  - **Manual:** troque e-mails de verdade com contatos conhecidos (clientes, parceiros, a própria equipe em
    outro domínio), pedindo para responderem e marcarem como "não é spam" se cair no spam.
- Cronograma sugerido por caixa (ajuste pela reputação real, não é regra fixa):

| Semana | Volume por dia |
|---|---|
| 1 | 5–10 |
| 2 | 15–25 |
| 3 | 25–35 |
| 4 | 30–50 (faixa do §15.2; hoje `DAILY_SEND_LIMIT_PER_MAILBOX=40` no `.env`) |

Com várias caixas, o Mensageiro faz rodízio entre elas (§15.2) — o limite acima é por caixa, não total.

## 6. Verificar a reputação antes da Fase 3
- [mail-tester.com](https://www.mail-tester.com): mande um e-mail de teste de cada caixa, confira a nota
  (persiga 9+/10) e corrija o que ele apontar.
- **Google Postmaster Tools** (postmaster.google.com): cadastre o domínio secundário, acompanhe reputação do
  IP/domínio, taxa de spam reportada pelos próprios usuários do Gmail e entrega.
- Só avance para a Fase 3 com reputação "Alta" ou "Média-alta" no Postmaster e sem alerta de spam ativo.

## 7. Checklist final
- [ ] Domínio secundário registrado e redirecionando para o site institucional
- [ ] Workspace criado, 2–3 caixas com nomes reais
- [ ] SPF, DKIM e DMARC publicados e validados
- [ ] Projeto no Google Cloud + OAuth client criado, credenciais no `.env`
- [ ] Aquecimento rodando há pelo menos 2 semanas
- [ ] Nota 9+ no mail-tester e reputação "Alta"/"Média-alta" no Postmaster Tools
- [ ] Nenhuma reclamação de spam nas últimas 2 semanas
