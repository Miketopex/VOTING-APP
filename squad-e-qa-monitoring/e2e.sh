#!/usr/bin/env bash

set -euo pipefail

echo "Starting CloudVote E2E environment..."

export SECRET_KEY="${SECRET_KEY:-ci-e2e-secret-key}"
export ADMIN_USERNAME="${ADMIN_USERNAME:-admin}"
export ADMIN_PASSWORD="${ADMIN_PASSWORD:-Admin12345}"

docker compose up -d --build

cleanup() {
    echo "Stopping CloudVote..."
    docker compose down -v
}

trap cleanup EXIT

echo "Waiting for services..."

for i in $(seq 1 30); do
    if curl -fsS http://localhost/health/ready >/dev/null 2>&1; then
        echo "Application ready."
        break
    fi

    if [ "$i" -eq 30 ]; then
        echo "Application failed readiness."
        docker compose ps
        docker compose logs --tail=100
        exit 1
    fi

    sleep 3
done

echo "Running end-to-end tests..."

python3 squad-e-qa-monitoring/e2e.py

echo "E2E tests completed successfully."
