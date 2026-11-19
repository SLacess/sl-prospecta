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
**Decisão (2026-11-18):** usar um subdomínio dedicado do `acessibilizardigital.com.br` só para prospecção
(ex.: `prospeccao.acessibilizardigital.com.br`), em vez de um domínio totalmente novo.

> **Risco que isso não elimina, só reduz:** `acessibilizardigital.com.br` já é um domínio ativo, com site e
> provavelmente e-mail de verdade. O Gmail/Outlook isolam parte da reputação por subdomínio (registro DKIM
> e IP de envio próprios), mas sinais de spam no nível do domínio organizacional (a raiz) tendem a vazar
> para o subdomínio e vice-versa — isso contraria o §15.2 da Constituição, que pede um domínio **exclusivo**.
> Se o aquecimento dar problema (volume alto demais, lista ruim, reclamação de spam), existe chance real de
> isso respingar na entrega de e-mails reais do Acessibilizar Digital. Se notar qualquer queda de entrega do
> domínio principal depois de começar a enviar pelo subdomínio, pare o envio e volte a avaliar um domínio
> separado.

O DNS de `acessibilizardigital.com.br` está no **Cloudflare** (nameservers `carmelo`/`annalise.ns.cloudflare.com`).
Hoje a raiz já usa esse DNS para e-mail de verdade — Cloudflare Email Routing (MX `route1-3.mx.cloudflare.net`,
SPF `include:_spf.mx.cloudflare.net`) e Brevo (`_dmarc` reportando para `dmarc.brevo.com`). **Nenhum passo abaixo
toca nesses registros** — tudo que você vai criar leva `prospeccao` no nome, nunca a raiz sozinha.

- No painel do Cloudflare → o domínio → **DNS → Records**: não é preciso "criar" o subdomínio como uma coisa
  separada — ele passa a existir no momento em que você cadastra o primeiro registro com `prospeccao` no nome
  (ex.: o TXT de verificação do Google, no próximo passo).
- Não crie registro **A/AAAA/CNAME** para `prospeccao` — sem isso, o subdomínio não abre como site (não precisa
  abrir), só funciona para e-mail.

## 2. Google Workspace
Esse domínio não tem Workspace hoje (o e-mail da raiz é Cloudflare Email Routing). Crie um Workspace novo:

1. Em [workspace.google.com](https://workspace.google.com), comece a assinatura informando
   `prospeccao.acessibilizardigital.com.br` como domínio — não a raiz.
2. O Google vai pedir para **verificar a propriedade do domínio**: ele dá um TXT tipo
   `google-site-verification=...`. Cadastre no Cloudflare: **Type** `TXT`, **Name** `prospeccao`, **Content**
   o valor que o Google deu, proxy desligado (TXT não proxeia mesmo, o Cloudflare já cuida disso).
3. Depois de verificar, o Google mostra os **registros MX** a cadastrar — hoje é um único registro
   `smtp.google.com`, prioridade 1 (versões mais antigas do Workspace mostram 5 registros `ASPMX.L.GOOGLE.COM`
   e afins; siga o que a tela do seu Workspace mostrar). Cadastre no Cloudflare: **Type** `MX`, **Name**
   `prospeccao`, **Content/Mail server** o que o Google deu, **Priority** o número que o Google deu.
4. Crie 2 ou 3 caixas com nomes de pessoas reais da equipe (ex.:
   `marcos@prospeccao.acessibilizardigital.com.br`), nunca `contato@`/`vendas@` — remetente genérico cai em
   spam com mais facilidade.
5. Essas caixas vão para a variável `OUTREACH_MAILBOXES` no `.env` (uma lista separada por vírgula).

## 3. DNS — SPF, DKIM, DMARC
Ainda no Admin console do Workspace novo (**Apps → Google Workspace → Gmail → Autenticação de e-mail**), gere
os três registros e cadastre no Cloudflare:

| Registro | Tipo | Name (Cloudflare) | Content |
|---|---|---|---|
| SPF | TXT | `prospeccao` | `v=spf1 include:_spf.google.com ~all` |
| DKIM | TXT | `google._domainkey.prospeccao` | a chave que o Workspace gerar |
| DMARC | TXT | `_dmarc.prospeccao` | `v=DMARC1; p=none; rua=mailto:dmarc@acessibilizardigital.com.br` |

O Cloudflare monta o nome completo a partir do que você digita em **Name** — `prospeccao` vira
`prospeccao.acessibilizardigital.com.br`, e `_dmarc.prospeccao` vira
`_dmarc.prospeccao.acessibilizardigital.com.br`. É crítico usar `_dmarc.prospeccao`, não `_dmarc` sozinho —
a raiz já tem um `_dmarc` (Brevo, `p=none`) e sobrescrever esse registro quebraria o monitoramento que já
existe lá. Comece seu DMARC em `p=none` (só monitora) nas primeiras 2 semanas; depois que o volume subir sem
rejeições, suba para `p=quarantine` antes da Fase 3. Nunca comece em `p=reject` — um erro de configuração
descarta e-mails legítimos sem aviso.

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
- [ ] Workspace novo criado com `prospeccao.acessibilizardigital.com.br`, domínio verificado no Google
- [ ] TXT de verificação e MX do Google cadastrados no Cloudflare (Name `prospeccao`)
- [ ] 2–3 caixas criadas com nomes reais
- [ ] SPF, DKIM e `_dmarc.prospeccao` (não `_dmarc` sozinho) publicados no Cloudflare e validados
- [ ] Projeto no Google Cloud + OAuth client criado, credenciais no `.env`
- [ ] Aquecimento rodando há pelo menos 2 semanas
- [ ] Nota 9+ no mail-tester e reputação "Alta"/"Média-alta" no Postmaster Tools
- [ ] Nenhuma reclamação de spam nas últimas 2 semanas
