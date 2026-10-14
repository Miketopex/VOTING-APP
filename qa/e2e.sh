#!/usr/bin/env bash
# End-to-end check: brings the whole stack up and drives a real vote through it —
# register, vote, wait for the worker, read the count back, try to vote twice.
#
# The unit suites prove each service on its own. This is the only thing that proves
# the four of them agree: that the Redis key Flask writes is the one the worker reads,
# that nginx can reach the app, and that a vote actually lands in Postgres. A key
# rename between the two services passes every unit test and fails here.
#
#   bash qa/e2e.sh                 # build, test, tear down
#   HTTP_PORT=8080 bash qa/e2e.sh  # when something else already owns port 80
#   KEEP_STACK=1 bash qa/e2e.sh    # leave it running to poke at
#
# Exits non-zero at the first failed step, naming the step.
set -euo pipefail

BASE="${BASE_URL:-http://localhost:${HTTP_PORT:-80}}"
COMPOSE="docker compose"
JAR="$(mktemp)"
BODY="$(mktemp)"
USERNAME="e2e_$RANDOM$RANDOM"
PASSWORD="e2e-Passw0rd-$RANDOM"
PASSED=0

cleanup() {
  local code=$?
  rm -f "$JAR" "$BODY"
  if [ "$code" != "0" ]; then
    echo
    echo "--- vote-service logs (last 40) ---"; $COMPOSE logs --tail 40 vote-service 2>/dev/null || true
    echo "--- worker logs (last 40) ---";       $COMPOSE logs --tail 40 worker       2>/dev/null || true
  fi
  if [ "${KEEP_STACK:-0}" != "1" ]; then
    $COMPOSE down -v --remove-orphans >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

step() { printf '\n==> %s\n' "$1"; }
pass() { PASSED=$((PASSED + 1)); printf '    ok: %s\n' "$1"; }
fail() { printf '    FAILED: %s\n' "$1" >&2; exit 1; }

# One curl with the session cookie jar. Body lands in $BODY, status in $STATUS.
req() {
  local method="$1" path="$2"; shift 2
  STATUS="$(curl -sS -o "$BODY" -w '%{http_code}' -b "$JAR" -c "$JAR" -X "$method" "$BASE$path" "$@")"
}

# CSRF is on in the production config, so every POST needs the token out of the form
# that precedes it. Fetching it is also a check in itself: it proves the page rendered.
csrf_from() {
  req GET "$1"
  grep -o 'name="csrf_token" value="[^"]*"' "$BODY" | head -1 | cut -d'"' -f4
}

json_int() { grep -oE "\"$1\"[[:space:]]*:[[:space:]]*[0-9]+" "$BODY" | head -1 | grep -oE '[0-9]+$'; }

# ------------------------------------------------------------------ bring it up
step "Starting the stack"
: "${SECRET_KEY:=e2e-secret-key-not-for-production}"
: "${POSTGRES_PASSWORD:=e2e-postgres-password}"
: "${ADMIN_PASSWORD:=e2e-Admin-Passw0rd}"
export SECRET_KEY POSTGRES_PASSWORD ADMIN_PASSWORD
$COMPOSE up -d --build --remove-orphans

step "Waiting for nginx and the vote service"
for i in $(seq 1 40); do
  curl -fsS "$BASE/health/ready" >/dev/null 2>&1 && break
  [ "$i" = 40 ] && fail "the stack never became ready"
  sleep 3
done
pass "ready after ${i}x3s"

# --------------------------------------------------------------------- checks
step "nginx answers its own liveness check without touching the app"
req GET /nginx-health
[ "$STATUS" = "200" ] || fail "/nginx-health returned $STATUS"
pass "/nginx-health"

step "/health reports every dependency"
req GET /health
for dep in database redis worker; do
  grep -q "\"$dep\"" "$BODY" || fail "/health does not report $dep: $(cat "$BODY")"
done
pass "database, redis and worker all reported"

step "A new user can register and lands signed in"
TOKEN="$(csrf_from /register)"
[ -n "$TOKEN" ] || fail "no csrf_token on the register form"
req POST /register \
  --data-urlencode "csrf_token=$TOKEN" \
  --data-urlencode "username=$USERNAME" \
  --data-urlencode "password=$PASSWORD" \
  --data-urlencode "confirm=$PASSWORD"
[ "$STATUS" = "302" ] || fail "register returned $STATUS, expected a redirect"
pass "registered $USERNAME"

step "The seeded demo poll is on the index"
req GET /
POLL_ID="$(grep -oE '/polls/[0-9]+' "$BODY" | head -1 | grep -oE '[0-9]+')"
[ -n "$POLL_ID" ] || fail "no poll link on the index — was the demo poll seeded?"
pass "poll #$POLL_ID"

step "The poll page offers options"
TOKEN="$(csrf_from "/polls/$POLL_ID")"
[ -n "$TOKEN" ] || fail "no csrf_token on the vote form"
OPTION_ID="$(grep -oE 'name="option_id"[^>]*value="[0-9]+"' "$BODY" | head -1 | grep -oE '[0-9]+')"
[ -n "$OPTION_ID" ] || fail "poll #$POLL_ID rendered no options"
pass "option #$OPTION_ID"

step "A vote is accepted and queued"
req POST "/polls/$POLL_ID/vote" --data-urlencode "csrf_token=$TOKEN" --data-urlencode "option_id=$OPTION_ID"
[ "$STATUS" = "302" ] || fail "vote returned $STATUS, expected a redirect"
grep -qi "location:" /dev/null 2>&1 || true
pass "vote queued"

step "The worker drains the queue and the vote is counted"
# The step that catches a Redis key mismatch: if the vote service queues under one
# key and the worker reads another, this never moves off zero.
COUNTED=0
for i in $(seq 1 20); do
  req GET "/api/polls/$POLL_ID/results"
  TOTAL="$(json_int total || true)"
  if [ -n "${TOTAL:-}" ] && [ "$TOTAL" -ge 1 ]; then COUNTED=1; break; fi
  sleep 3
done
[ "$COUNTED" = "1" ] \
  || fail "the vote was queued but never counted — check that vote and worker agree on the Redis keys"
pass "counted, total is $TOTAL"

step "The same user cannot vote twice"
TOKEN="$(csrf_from "/polls/$POLL_ID")"
req POST "/polls/$POLL_ID/vote" --data-urlencode "csrf_token=$TOKEN" --data-urlencode "option_id=$OPTION_ID"
req GET "/polls/$POLL_ID"
grep -qi "already" "$BODY" || fail "a second vote was not refused"
pass "duplicate refused"

step "A POST without a CSRF token is rejected"
req POST "/polls/$POLL_ID/vote" --data-urlencode "option_id=$OPTION_ID"
[ "$STATUS" = "400" ] || fail "a token-less POST returned $STATUS, expected 400"
pass "CSRF enforced"

step "Signing out ends the session"
TOKEN="$(csrf_from "/polls/$POLL_ID")"
req POST /logout --data-urlencode "csrf_token=$TOKEN"
req GET "/polls/$POLL_ID"
[ "$STATUS" = "302" ] || fail "a signed-out user still reached the poll page"
pass "signed out"

printf '\nAll %s end-to-end checks passed.\n' "$PASSED"
