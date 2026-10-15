#!/usr/bin/env bash
# =====================================================================
#  Restore a backup made by backup-db.sh.  THIS REPLACES THE CURRENT DATA.
#    ./restore-db.sh s3://<bucket>/backups/cloudvote-YYYYmmdd-HHMMSS.sql.gz
#
#  List what is available first:
#    aws s3 ls s3://<bucket>/backups/
# =====================================================================
set -euo pipefail
cd "${APP_DIR:-/opt/cloudvote}"

if [ ! -f ./.env ]; then
  echo "no .env in $PWD - run ./fetch-env.sh first" >&2
  exit 1
fi
set -a; source ./.env; set +a

: "${POSTGRES_USER:?missing from .env}"
: "${POSTGRES_DB:?missing from .env}"
: "${AWS_REGION:=us-east-1}"

SRC="${1:?usage: restore-db.sh s3://bucket/backups/file.sql.gz}"

read -r -p "This REPLACES the current database with $SRC. Type 'restore' to continue: " ok
[ "$ok" = "restore" ] || { echo "cancelled"; exit 1; }

# Stop the worker first or it writes votes into the database mid-restore.
docker compose stop worker

# `postgres`, not `db` - see the note in backup-db.sh.
aws s3 cp "$SRC" - --region "$AWS_REGION" \
  | gunzip \
  | docker compose exec -T postgres \
      psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1

# The cached results now describe the database we just replaced. Drop them so the
# next request recomputes from the restored rows rather than serving the old totals.
#
# No `-a "$REDIS_PASSWORD"` here: redis in this stack runs without requirepass
# (docker-compose.yml), and REDIS_PASSWORD was never passed to the container - so
# under `set -u` that flag aborted the restore before it could clear anything.
docker compose exec -T redis redis-cli --scan --pattern 'results:*' \
  | xargs -r -n 50 docker compose exec -T redis redis-cli DEL >/dev/null || true

docker compose start worker
echo "restore complete - verify at /health and on the results page"
