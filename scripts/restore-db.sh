#!/usr/bin/env bash
# Restore a backup made by backup-db.sh.  ⚠ Replaces the current data.
#   ./scripts/restore-db.sh s3://<bucket>/backups/cloudvote-YYYYmmdd-HHMMSS.sql.gz
set -euo pipefail
cd "${APP_DIR:-/opt/cloudvote}"
set -a; source ./deploy.env; source ./.env; set +a
export IMAGE_TAG=$(cat .current_tag 2>/dev/null || echo latest)
SRC="${1:?usage: restore-db.sh s3://bucket/backups/file.sql.gz}"
read -r -p "This REPLACES the current database with $SRC. Type 'restore' to continue: " ok
[ "$ok" = "restore" ] || { echo "cancelled"; exit 1; }
docker compose stop worker
aws s3 cp "$SRC" - --region "$AWS_REGION" | gunzip | docker compose exec -T db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1
docker compose exec -T redis redis-cli -a "$REDIS_PASSWORD" --no-auth-warning --scan --pattern 'results:*' \
  | xargs -r docker compose exec -T redis redis-cli -a "$REDIS_PASSWORD" --no-auth-warning DEL >/dev/null || true
docker compose start worker
echo "restore complete"