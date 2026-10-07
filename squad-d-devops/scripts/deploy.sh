#!/usr/bin/env bash
set -euo pipefail

cd /opt/cloudvote

NEW_TAG="${IMAGE_TAG:?IMAGE_TAG is required}"
export DOCKERHUB_USER="${DOCKERHUB_USER:?DOCKERHUB_USER is required}"
PREV_TAG="$(cat .deployed_tag 2>/dev/null || echo "")"

health_check() {
  for i in $(seq 1 20); do
    if curl -fsk https://localhost/health >/dev/null; then
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
docker compose pull
docker compose up -d --remove-orphans

if health_check; then
  echo "$NEW_TAG" > .deployed_tag
  docker image prune -f >/dev/null
  echo "deployment $NEW_TAG succeeded"
  exit 0
fi

echo "HEALTH CHECK FAILED: rolling back"
if [ -n "$PREV_TAG" ]; then
  export IMAGE_TAG="$PREV_TAG"
  docker compose up -d --remove-orphans
  if health_check; then
    echo "rolled back to $PREV_TAG"
  else
    echo "ROLLBACK ALSO UNHEALTHY"
  fi
else
  echo "no previous version to roll back to"
fi
exit 1
