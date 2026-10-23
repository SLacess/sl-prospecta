#!/usr/bin/env bash
# Preparação inicial da VPS Hostinger (Ubuntu 24.04). Rode UMA vez como root:
#   curl -fsSL <url-raw-deste-arquivo> | bash   — ou copie e rode: sudo bash setup-vps.sh
set -euo pipefail

DEPLOY_USER="${DEPLOY_USER:-deploy}"
APP_DIR="/opt/sl-prospecta"

echo "==> Atualizando o sistema"
apt-get update -y && apt-get upgrade -y
apt-get install -y ca-certificates curl git ufw fail2ban unattended-upgrades

echo "==> Instalando Docker"
if ! command -v docker >/dev/null; then
  curl -fsSL https://get.docker.com | sh
fi

echo "==> Criando usuário de deploy: $DEPLOY_USER"
if ! id "$DEPLOY_USER" >/dev/null 2>&1; then
  adduser --disabled-password --gecos "" "$DEPLOY_USER"
fi
usermod -aG docker "$DEPLOY_USER"
mkdir -p "/home/$DEPLOY_USER/.ssh"
touch "/home/$DEPLOY_USER/.ssh/authorized_keys"
chmod 700 "/home/$DEPLOY_USER/.ssh"
chmod 600 "/home/$DEPLOY_USER/.ssh/authorized_keys"
chown -R "$DEPLOY_USER:$DEPLOY_USER" "/home/$DEPLOY_USER/.ssh"

echo "==> Firewall: apenas SSH, HTTP e HTTPS"
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

echo "==> SSH: somente chave, sem login de root por senha"
sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config
# Opcional: altere a porta SSH (lembre de liberar no ufw e atualizar o secret VPS_PORT)
systemctl restart ssh || systemctl restart sshd

echo "==> Atualizações automáticas de segurança e fail2ban"
dpkg-reconfigure -f noninteractive unattended-upgrades
systemctl enable --now fail2ban

echo "==> Pasta da aplicação"
mkdir -p "$APP_DIR"
chown "$DEPLOY_USER:$DEPLOY_USER" "$APP_DIR"

cat <<EOF

✅ VPS pronta.
Próximos passos (veja infra/DEPLOY.md):
  1. Coloque a chave pública do GitHub Actions em /home/$DEPLOY_USER/.ssh/authorized_keys
  2. Copie o .env de produção para $APP_DIR/.env (dono $DEPLOY_USER, chmod 600)
  3. Cadastre os secrets no GitHub e faça push na main — o deploy baixa código e imagens sozinho
EOF
