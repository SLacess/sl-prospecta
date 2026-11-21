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

## 2. Caixa de envio — duas opções

O Mensageiro fala com a **Gmail API** (CONSTITUICAO §9), não SMTP genérico — então as duas opções abaixo
usam exatamente o mesmo código e a mesma tela `/caixas-envio`; a diferença é só de onde vem a caixa. Um
serviço de e-mail não-Google (Zoho Mail, Migadu etc.) exigiria reescrever o Mensageiro para SMTP e também
o disjuntor de bounce, que hoje lê `gmail.readonly` — por isso não entra aqui como opção "simples".

Pode misturar: uma caixa pela 2a, outra pela 2b — o rodízio do Mensageiro não diferencia.

### 2a. Google Workspace (melhor entregabilidade, ~R$30-35/mês por caixa)
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

### 2b. Gmail grátis + alias verificado (sem custo, zero código novo, entregabilidade levemente inferior)
Sem Workspace: cria-se uma conta Gmail comum por caixa e verifica-se um alias "Enviar como" no endereço do
subdomínio. Como não há servidor de SMTP próprio, o Google assina com o DKIM dele (`d=gmail.com`), não com
o do seu domínio — por isso o DMARC só alinha pelo SPF, não pelo DKIM (funciona, mas é um alinhamento mais
frágil que o Workspace; teste no mail-tester antes de confiar).

1. **MX do subdomínio, só para receber** (não precisa de Workspace nenhum): no Cloudflare → o domínio →
   **Email → Email Routing**, crie uma regra de roteamento para um endereço do tipo
   `marcos@prospeccao.acessibilizardigital.com.br`, apontando para uma caixa que você já tem (sua mesma
   conta pessoal, por exemplo) — é só para receber o código de verificação do Google e as devoluções
   (bounces). O Cloudflare propõe os registros **MX** (`route1-3.mx.cloudflare.net`) a cadastrar com
   **Name** `prospeccao` — ele mesmo oferece para criar; confirme. Se ele também sugerir um TXT junto
   (às vezes aparece como parte do mesmo passo), cadastre; o SPF que realmente importa para o envio é o
   `include:_spf.google.com` da seção 3, cadastrado à parte.
2. Crie a conta Gmail nova (ex. `slprospecta.envio1@gmail.com` — o nome dessa conta não aparece para quem
   recebe, só o alias abaixo aparece). Ative a verificação em 2 etapas por segurança (não interfere no
   OAuth, que não usa senha).
3. **Use por alguns dias normalmente antes de conectar no painel** — conta nova demais já fazendo coisa
   automatizada é o tipo de sinal que o próprio Google usa para desconfiar.
4. Em **Configurações → Ver todas as configurações → Contas e importação → Enviar e-mail como → Adicionar
   outro endereço de e-mail seu**: nome "Marcos" (ou quem for), endereço
   `marcos@prospeccao.acessibilizardigital.com.br`, deixe **"Tratar como alias"** marcado (é a única opção
   sem servidor SMTP próprio) e confirme.
5. O Google manda um e-mail de verificação para esse endereço → cai na caixa que você apontou no passo 1 →
   abra e clique no link (ou cole o código na tela do Gmail). O alias passa a aparecer em "Enviar e-mail
   como".
6. Repita os passos 2-5 para a 2ª/3ª caixa, com outra conta Gmail e outro endereço do subdomínio.

Em qualquer uma das opções: essas caixas **não vão em `.env`** — depois que o OAuth do passo 4 (seção
seguinte) estiver configurado, você conecta cada uma pelo painel (`/caixas-envio` → "Conectar nova caixa",
autentica com aquela conta do Google — a do Workspace ou a do Gmail grátis — e autoriza) — ADR 0016.
Nenhum e-mail sai antes de alguém rodar o Mensageiro manualmente (`python -m slp_workers.cli enviar`)
depois do aquecimento.

## 3. DNS — SPF, DKIM, DMARC
SPF e DMARC valem para as duas opções da seção 2; **DKIM só existe na 2a** (Workspace) — na 2b (Gmail
grátis) o Google assina com o DKIM dele mesmo (`d=gmail.com`), não há nada seu para gerar/cadastrar.

| Registro | Tipo | Name (Cloudflare) | Content | Opção |
|---|---|---|---|---|
| SPF | TXT | `prospeccao` | `v=spf1 include:_spf.google.com ~all` | 2a e 2b |
| DKIM | TXT | `google._domainkey.prospeccao` | a chave que o Admin console do Workspace gerar (**Apps → Google Workspace → Gmail → Autenticação de e-mail**) | só 2a |
| DMARC | TXT | `_dmarc.prospeccao` | `v=DMARC1; p=none; rua=mailto:dmarc@acessibilizardigital.com.br` | 2a e 2b |

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
   autorizar são as contas das caixas (do Workspace novo, na opção 2a, ou as contas Gmail comuns, na 2b) —
   nenhuma delas é a mesma conta do projeto. Em modo de teste, adicione cada uma como "usuário de teste"
   (evita a revisão pública do Google).
4. Crie uma credencial **OAuth client ID** do tipo "Aplicativo Web". Em **Authorized redirect URIs**,
   cadastre exatamente `https://api.leadfactory.com.br/caixas-envio/callback` (ou o domínio real da VPS,
   se mudou) — tem que bater byte a byte com `GOOGLE_OAUTH_REDIRECT_URI` no `.env` da VPS.
5. Client ID e client secret vão para `GOOGLE_OAUTH_CLIENT_ID`/`GOOGLE_OAUTH_CLIENT_SECRET` no
   `.env.production` da VPS (`/opt/sl-prospecta/.env`); gere também `FIELD_ENCRYPTION_KEY`
   (`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`) se ainda
   não tiver uma. Depois de editar, reinicie o serviço `api` para ele carregar os valores novos.
6. Com isso no ar, conecte cada caixa pelo painel (`/caixas-envio`, logado como admin) — é aí que o fluxo
   OAuth de verdade acontece (escopos `gmail.send` e `gmail.readonly`, já embutidos no botão "Conectar
   nova caixa"). Se o navegador já estiver logado em outra conta Google, a tela de escolha de conta do
   Google aparece — confira que está escolhendo a caixa certa antes de autorizar.

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
A conexão (`/caixas-envio/conectar`) começa com o valor de `DAILY_SEND_LIMIT_PER_MAILBOX` do `.env`, mas
dá para subir o limite de uma caixa já conectada a qualquer momento — o link "Editar" ao lado de "Limite
diário", no card da caixa em `/caixas-envio` — sem precisar reconectar nem mexer no `.env`.

## 6. Verificar a reputação antes da Fase 3
- [mail-tester.com](https://www.mail-tester.com): mande um e-mail de teste de cada caixa, confira a nota
  (persiga 9+/10) e corrija o que ele apontar.
- **Google Postmaster Tools** (postmaster.google.com): cadastre o domínio secundário, acompanhe reputação do
  IP/domínio, taxa de spam reportada pelos próprios usuários do Gmail e entrega.
- Só avance para a Fase 3 com reputação "Alta" ou "Média-alta" no Postmaster e sem alerta de spam ativo.

## 7. Checklist final
- [ ] Decidido 2a (Workspace) ou 2b (Gmail grátis) por caixa — pode misturar
- [ ] **2a:** Workspace novo criado com `prospeccao.acessibilizardigital.com.br`, domínio verificado,
  TXT de verificação e MX do Google cadastrados no Cloudflare (Name `prospeccao`)
- [ ] **2b:** MX de Email Routing do Cloudflare cadastrado para `prospeccao`, conta(s) Gmail criada(s) e
  usada(s) por alguns dias, alias "Enviar e-mail como" verificado em cada uma
- [ ] 2–3 caixas no total, com nomes reais
- [ ] SPF e `_dmarc.prospeccao` (não `_dmarc` sozinho) publicados no Cloudflare e validados; DKIM também,
  se houver alguma caixa pela 2a
- [ ] Projeto no Google Cloud + OAuth client criado, redirect URI cadastrado, credenciais no
  `.env.production` da VPS
- [ ] Cada caixa conectada pelo painel (`/caixas-envio`) e aparecendo "Ativa", sem `erro_verificacao`
- [ ] Limite diário de cada caixa ajustado pelo "Editar" em `/caixas-envio` conforme a semana do
  cronograma acima (começa em 5-10, não no valor padrão de conexão)
- [ ] Aquecimento rodando há pelo menos 2 semanas
- [ ] Nota 9+ no mail-tester e reputação "Alta"/"Média-alta" no Postmaster Tools
- [ ] Nenhuma reclamação de spam nas últimas 2 semanas
