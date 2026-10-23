#!/usr/bin/env bash
# Backup diário do Postgres + MinIO (CONSTITUICAO §16.2). Retenção: 30 dias.
# Agende no crontab do usuário deploy:
#   15 3 * * * /opt/sl-prospecta/infra/scripts/backup.sh >> /opt/sl-prospecta/backups/backup.log 2>&1
set -euo pipefail

cd "$(dirname "$0")/../.."
set -a; source .env; set +a

DEST="${BACKUP_DIR:-/opt/sl-prospecta/backups}"
STAMP="$(date +%F_%H%M)"
COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.prod.yml)
mkdir -p "$DEST"

echo "[$STAMP] Dump do Postgres"
"${COMPOSE[@]}" exec -T postgres pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom \
  | gzip > "$DEST/postgres_$STAMP.dump.gz"

echo "[$STAMP] Arquivos do MinIO"
docker run --rm \
  -v sl-prospecta_miniodata:/data:ro \
  -v "$DEST":/backup \
  alpine tar czf "/backup/minio_$STAMP.tar.gz" -C /data .

echo "[$STAMP] Removendo backups com mais de 30 dias"
find "$DEST" -name 'postgres_*.dump.gz' -mtime +30 -delete
find "$DEST" -name 'minio_*.tar.gz' -mtime +30 -delete

# IMPORTANTE: copie $DEST para fora da VPS (ex.: rclone para Google Drive ou S3).
# Exemplo: rclone copy "$DEST" remoto:sl-prospecta-backups --max-age 25h
echo "[$STAMP] Backup concluído"
