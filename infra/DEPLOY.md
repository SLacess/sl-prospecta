# Deploy na VPS Hostinger — passo a passo

Tempo estimado: 40–60 minutos na primeira vez. Depois disso, todo `push` na `main` publica sozinho.

## 1. VPS
- Plano recomendado: **KVM 4** (4 vCPU, 16 GB RAM) com **Ubuntu 24.04**.
- No painel da Hostinger, cadastre sua chave SSH pessoal.

## 2. DNS
No provedor do domínio, crie registros **A** apontando para o IP da VPS:

| Nome | Tipo | Valor |
|---|---|---|
| `app` | A | IP da VPS |
| `api` | A | IP da VPS |
| `diagnostico` | A | IP da VPS |

O Caddy emite os certificados HTTPS automaticamente quando os registros propagarem.

## 3. Preparar o servidor
```bash
ssh root@IP_DA_VPS
# copie o conteúdo de infra/scripts/setup-vps.sh para o servidor e rode:
bash setup-vps.sh
```

## 4. Chave de deploy do GitHub Actions
No seu computador:
```bash
ssh-keygen -t ed25519 -f slp_deploy -C "github-actions-sl-prospecta" -N ""
```
- Conteúdo de `slp_deploy.pub` → adicione em `/home/deploy/.ssh/authorized_keys` na VPS.
- Conteúdo de `slp_deploy` (privada) → vai para o secret `VPS_SSH_KEY` (passo 6).

## 5. Clonar e configurar na VPS
```bash
ssh deploy@IP_DA_VPS
git clone https://github.com/SEU_USUARIO/sl-prospecta.git /opt/sl-prospecta
cd /opt/sl-prospecta
cp .env.example .env
nano .env
```
No `.env` de produção, ajuste pelo menos:
- `ENVIRONMENT=production`
- `DOMAIN`, `ACME_EMAIL`, `GHCR_OWNER` (seu usuário do GitHub em minúsculas)
- Todas as senhas (`POSTGRES_PASSWORD`, `MINIO_ROOT_PASSWORD`) e `DATABASE_URL` com a mesma senha do Postgres
- `JWT_SECRET` e `N8N_ENCRYPTION_KEY` → gere com `openssl rand -hex 32`
- `NEXT_PUBLIC_API_URL=https://api.SEU_DOMINIO`, `APP_BASE_URL=https://app.SEU_DOMINIO`, `CORS_ORIGINS=https://app.SEU_DOMINIO`

Se o repositório for privado, autentique o Docker no registro do GitHub (token com `read:packages`):
```bash
echo SEU_TOKEN | docker login ghcr.io -u SEU_USUARIO --password-stdin
```

## 6. Secrets e variáveis no GitHub
Repositório → **Settings → Secrets and variables → Actions**:

| Tipo | Nome | Valor |
|---|---|---|
| Secret | `VPS_HOST` | IP da VPS |
| Secret | `VPS_USER` | `deploy` |
| Secret | `VPS_SSH_KEY` | chave privada `slp_deploy` |
| Secret | `VPS_PORT` | `22` (ou a porta que você definiu) |
| Variable | `NEXT_PUBLIC_API_URL` | `https://api.SEU_DOMINIO` |

Crie também o ambiente **production** (Settings → Environments). Se quiser, exija aprovação manual antes de cada deploy.

## 7. Primeiro deploy
Faça um `push` na `main` (ou rode o workflow **Deploy** manualmente em Actions). Depois, crie o administrador:
```bash
cd /opt/sl-prospecta
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec api \
  python -m app.cli create-admin --email voce@sinallink.com.br --name "Marcos Alencar"
```
Acesse `https://app.SEU_DOMINIO/login`.

## 8. Backups
```bash
crontab -e
# adicione:
15 3 * * * /opt/sl-prospecta/infra/scripts/backup.sh >> /opt/sl-prospecta/backups/backup.log 2>&1
```
Configure uma cópia para fora da VPS (rclone → Google Drive ou S3) e teste uma restauração por mês.

## Como o deploy funciona
1. `push` na `main` → workflow **CI** roda lint, testes, build e testes de acessibilidade.
2. Se passar, **Deploy** gera 3 imagens (`api`, `worker`, `web`) e publica no GitHub Container Registry.
3. Por SSH, a VPS atualiza o código, baixa as imagens, aplica migrações e sobe os serviços.
4. Se `/health` não responder em ~2 minutos, volta sozinha para a versão anterior.

> Migrações de banco não são revertidas no rollback. Escreva migrações compatíveis com a versão anterior (adicionar antes de remover).

## Comandos úteis na VPS
```bash
alias dc='docker compose -f docker-compose.yml -f docker-compose.prod.yml'
dc ps                 # status dos serviços
dc logs -f api        # logs da API
dc logs -f worker     # logs dos workers
dc --profile n8n up -d n8n   # ligar o n8n (acesse via túnel SSH: ssh -L 5678:localhost:5678 ...)
```
