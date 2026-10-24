#!/usr/bin/env bash
# Deploy com rollback automático (CONSTITUICAO §16.3)
# Uso: ./infra/scripts/deploy.sh <tag-da-imagem>
set -euo pipefail

cd "$(dirname "$0")/../.."

NEW_TAG="${1:?informe a tag da imagem}"
STATE_FILE=".deployed_tag"
PREV_TAG="$(cat "$STATE_FILE" 2>/dev/null || echo latest)"
COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.prod.yml)

log() { echo "[deploy $(date '+%F %T')] $*"; }

health_ok() {
  for _ in $(seq 1 30); do
    if "${COMPOSE[@]}" exec -T api python -c \
      "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health', timeout=3).status==200 else 1)" \
      >/dev/null 2>&1; then
      return 0
    fi
    sleep 4
  done
  return 1
}

log "Versão atual: $PREV_TAG → nova: $NEW_TAG"
export IMAGE_TAG="$NEW_TAG"

log "Baixando imagens…"
"${COMPOSE[@]}" pull api worker web

log "Subindo banco e fila…"
"${COMPOSE[@]}" up -d postgres redis minio

log "Aplicando migrações…"
"${COMPOSE[@]}" run --rm api alembic upgrade head

log "Subindo aplicação…"
"${COMPOSE[@]}" up -d --remove-orphans

log "Verificando saúde…"
if health_ok; then
  echo "$NEW_TAG" > "$STATE_FILE"
  docker image prune -f >/dev/null
  log "✅ Deploy concluído: $NEW_TAG"
else
  log "❌ Verificação de saúde falhou. Revertendo para $PREV_TAG…"
  export IMAGE_TAG="$PREV_TAG"
  "${COMPOSE[@]}" up -d --remove-orphans
  log "Rollback aplicado. Atenção: migrações de banco NÃO são revertidas automaticamente."
  exit 1
fi
