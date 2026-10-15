#!/usr/bin/env bash
set -euo pipefail

cd /opt/cloudvote

NEW_TAG="${IMAGE_TAG:?IMAGE_TAG is required}"
export DOCKERHUB_USER="${DOCKERHUB_USER:?DOCKERHUB_USER is required}"
PREV_TAG="$(cat .deployed_tag 2>/dev/null || echo "")"

# Both files, always: the base one describes the stack, the overlay swaps the two
# built services for the images CD pushed. Without the overlay `docker compose up`
# tries to build from ./vote, which does not exist on this box.
COMPOSE="docker compose -f docker-compose.yml -f docker-compose.prod.yml"

health_check() {
  for i in $(seq 1 20); do
    # http, not https: nginx.conf only has a :80 server block. The old check used
    # https, which never answered, so every deploy failed its own health check and
    # rolled itself back.
    if curl -fs http://localhost/health >/dev/null; then
      return 0
    fi
    echo "waiting for health ($i/20)..."
    sleep 6
  done
  return 1
}

./fetch-env.sh /opt/cloudvote/.env
echo "Deploying $NEW_TAG (previous: ${PREV_TAG:-none})"

export IMAGE_TAG="$NEW_TAG"
$COMPOSE pull
$COMPOSE up -d --remove-orphans

# backup-db.sh documented itself as a nightly cron job, but nothing ever installed
# one - so there were no backups, only a comment saying there were. Done here rather
# than in ec2-bootstrap.sh because at first boot the script does not exist yet; CD
# copies it. Writing the whole file each time keeps it idempotent.
install_backup_cron() {
  cat > /etc/cron.d/cloudvote-backup <<'CRON'
# Nightly database backup to S3. Managed by scripts/deploy.sh - edits are overwritten.
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
40 2 * * * ubuntu cd /opt/cloudvote && ./backup-db.sh >> /var/log/cloudvote-backup.log 2>&1
CRON
  chmod 644 /etc/cron.d/cloudvote-backup
}

if health_check; then
  echo "$NEW_TAG" > .deployed_tag
  # Needs root; the deploy user has passwordless sudo via cloud-init's default.
  sudo bash -c "$(declare -f install_backup_cron); install_backup_cron" \
    && echo "backup cron installed (02:40 UTC)" \
    || echo "WARNING: could not install backup cron - backups will not run"
  docker image prune -f >/dev/null
  echo "deployment $NEW_TAG succeeded"
  exit 0
fi

echo "HEALTH CHECK FAILED: rolling back"
if [ -n "$PREV_TAG" ]; then
  export IMAGE_TAG="$PREV_TAG"
  $COMPOSE up -d --remove-orphans
  if health_check; then
    echo "rolled back to $PREV_TAG"
  else
    echo "ROLLBACK ALSO UNHEALTHY"
  fi
else
  echo "no previous version to roll back to"
fi
exit 1
