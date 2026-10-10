#!/usr/bin/env bash
# =====================================================================
#  Nightly PostgreSQL backup to S3 (cron 02:40 UTC).
#  Uses the EC2 IAM role (s3:PutObject on backups/* only) – no keys.
#  Restore:  ./scripts/restore-db.sh s3://<bucket>/backups/<file>.sql.gz
# =====================================================================
set -euo pipefail
cd "${APP_DIR:-/opt/cloudvote}"
set -a; source ./deploy.env; source ./.env; set +a
export IMAGE_TAG=$(cat .current_tag 2>/dev/null || echo latest)
: "${BACKUP_BUCKET:?set BACKUP_BUCKET in deploy.env}"

file="cloudvote-$(date -u +%Y%m%d-%H%M%S).sql.gz"
docker compose exec -T db pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists \
  | gzip | aws s3 cp - "s3://$BACKUP_BUCKET/backups/$file" --region "$AWS_REGION" --sse AES256
echo "$(date -u +%FT%TZ) backup uploaded: s3://$BACKUP_BUCKET/backups/$file"