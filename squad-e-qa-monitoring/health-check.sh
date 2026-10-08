#!/usr/bin/env bash

set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost}"

echo "CloudVote Health Check"
echo "======================"
echo

check_endpoint() {

    local endpoint="$1"
    local expected="$2"

    echo "Checking $endpoint ..."

    status=$(curl -s \
        -o /tmp/cloudvote-health-response.json \
        -w "%{http_code}" \
        "$BASE_URL$endpoint")

    if [ "$status" != "$expected" ]; then

        echo "FAIL"
        echo "Expected HTTP $expected"
        echo "Received HTTP $status"
        cat /tmp/cloudvote-health-response.json

        exit 1
    fi

    echo "PASS HTTP $status"
}


check_endpoint "/health/live" "200"
check_endpoint "/health/ready" "200"
check_endpoint "/health" "200"

echo
echo "All health endpoints passed."
