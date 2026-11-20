# Domínio de prospecção e aquecimento de e-mail — passo a passo

Tempo estimado: 1 dia de configuração + 2 a 4 semanas de aquecimento antes da Fase 3.
Pré-requisito da Fase 3 (Guia de Construção, Etapa 3): caixas aquecidas, nota alta no mail-tester
e nenhuma reclamação de spam. O critério de saída da própria Fase 3 exige bounce < 2%.

Referências na CONSTITUICAO.md: §15.2 (entregabilidade — domínio secundário, SPF/DKIM/DMARC, limite de envio)
e §13 (disjuntores). O código já existe (ADR 0016): o disjuntor de bounce (>3% em 24h) é automático e
suprime quem rejeitou; o botão "Pausar tudo"/"Reportar reclamação de spam" fica sempre visível no painel.
Resposta negativa/irritada só é manual por ora (sem Leitor de Respostas — Fase 4).

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
5. Essas caixas **não vão em `.env`** — depois que o OAuth do passo 4 abaixo estiver configurado, você
   conecta cada uma pelo painel (`/caixas-envio` → "Conectar nova caixa", autentica com aquela conta do
   Google e autoriza) — ADR 0016. Nenhum e-mail sai antes de alguém rodar o Mensageiro manualmente
   (`python -m slp_workers.cli enviar`) depois do aquecimento.

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
O Mensageiro envia pela Gmail API, não por SMTP direto — por isso o `.env` tem
`GOOGLE_OAUTH_CLIENT_ID`/`GOOGLE_OAUTH_CLIENT_SECRET` em vez de usuário/senha de e-mail. Este client é do
SL Prospecta (a ferramenta interna, hoje em `leadfactory.com.br`) — não precisa ser criado dentro do
Workspace novo de `prospeccao.acessibilizardigital.com.br`; só precisa poder enviar/ler pelas caixas
daquele domínio, o que o fluxo OAuth do passo 4 garante.

1. No [Google Cloud Console](https://console.cloud.google.com), crie um projeto (qualquer conta Google
   serve — não precisa ser a do Workspace novo).
2. Ative a **Gmail API** (APIs e serviços → Biblioteca).
3. Configure a **tela de consentimento OAuth**: tipo "Externo" é o mais simples aqui, já que quem vai
   autorizar são contas de `prospeccao.acessibilizardigital.com.br`, de um Workspace diferente do projeto —
   em modo de teste, adicione essas caixas como "usuários de teste" (evita a revisão pública do Google).
4. Crie uma credencial **OAuth client ID** do tipo "Aplicativo Web". Em **Authorized redirect URIs**,
   cadastre exatamente `https://api.leadfactory.com.br/caixas-envio/callback` (ou o domínio real da VPS,
   se mudou) — tem que bater byte a byte com `GOOGLE_OAUTH_REDIRECT_URI` no `.env` da VPS.
5. Client ID e client secret vão para `GOOGLE_OAUTH_CLIENT_ID`/`GOOGLE_OAUTH_CLIENT_SECRET` no
   `.env.production` da VPS (`/opt/sl-prospecta/.env`); gere também `FIELD_ENCRYPTION_KEY`
   (`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`) se ainda
   não tiver uma. Depois de editar, reinicie o serviço `api` para ele carregar os valores novos.
6. Com isso no ar, conecte cada caixa pelo painel (`/caixas-envio`, logado como admin) — é aí que o fluxo
   OAuth de verdade acontece (escopos `gmail.send` e `gmail.readonly`, já embutidos no botão "Conectar
   nova caixa").

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
Hoje o limite diário de uma caixa é fixado na conexão (`DAILY_SEND_LIMIT_PER_MAILBOX` no `.env`, no momento
em que ela é conectada) — não há ainda uma tela para subir o limite de uma caixa já conectada semana a
semana. Enquanto isso não existir, suba `DAILY_SEND_LIMIT_PER_MAILBOX`, reconecte a caixa (reconectar
atualiza só o token, não o limite — então seria preciso remover e conectar de novo) ou peça para editar
direto no banco. Avise antes de precisar disso na prática (por volta da semana 2) para priorizarmos uma
tela simples de ajuste.

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
- [ ] Projeto no Google Cloud + OAuth client criado, redirect URI cadastrado, credenciais no
  `.env.production` da VPS
- [ ] Cada caixa conectada pelo painel (`/caixas-envio`) e aparecendo "Ativa", sem `erro_verificacao`
- [ ] Aquecimento rodando há pelo menos 2 semanas
- [ ] Nota 9+ no mail-tester e reputação "Alta"/"Média-alta" no Postmaster Tools
- [ ] Nenhuma reclamação de spam nas últimas 2 semanas
