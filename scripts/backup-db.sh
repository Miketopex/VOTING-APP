#!/usr/bin/env bash
# =====================================================================
#  Nightly PostgreSQL backup to S3. Installed as a cron job by deploy.sh
#  (02:40 UTC) - see the install_backup_cron function there.
#
#  Uploads through the EC2 instance role, which is allowed s3:PutObject on
#  backups/* and nothing else. No access keys anywhere.
#
#  Restore:  ./restore-db.sh s3://<bucket>/backups/<file>.sql.gz
# =====================================================================
set -euo pipefail
cd "${APP_DIR:-/opt/cloudvote}"

# fetch-env.sh writes this from SSM on every deploy. It carries POSTGRES_USER,
# POSTGRES_DB, BACKUP_BUCKET and AWS_REGION among the rest.
#
# It used to also source ./deploy.env, a file nothing in this repo ever created -
# under `set -e` that aborted the script on line 9, every night, silently.
if [ ! -f ./.env ]; then
  echo "no .env in $PWD - run ./fetch-env.sh first" >&2
  exit 1
fi
set -a; source ./.env; set +a

: "${POSTGRES_USER:?missing from .env}"
: "${POSTGRES_DB:?missing from .env}"
: "${BACKUP_BUCKET:?missing from .env - is it set in ssm.tf?}"
: "${AWS_REGION:=us-east-1}"

file="cloudvote-$(date -u +%Y%m%d-%H%M%S).sql.gz"

# The service is `postgres` (see docker-compose.yml). This said `db`, which is not
# a service in this stack, so the command failed with "no such service" every time.
#
# Piping straight into `aws s3 cp -` keeps the dump off the instance disk, which
# matters on a t3.micro with an 8GB root volume.
docker compose exec -T postgres \
  pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists \
  | gzip \
  | aws s3 cp - "s3://$BACKUP_BUCKET/backups/$file" --region "$AWS_REGION" --sse AES256

echo "$(date -u +%FT%TZ) backup uploaded: s3://$BACKUP_BUCKET/backups/$file"
