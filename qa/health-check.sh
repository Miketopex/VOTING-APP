#!/usr/bin/env bash
# Monitoring probe. Point it at a running deployment and it reports what is up.
#
#   bash qa/health-check.sh                        # localhost
#   bash qa/health-check.sh http://my-ec2-host     # a deployment
#
# Exit codes are what a cron job or an alert rule reads:
#   0  everything healthy
#   1  degraded — serving, but something behind it is wrong (worker stalled, cache down)
#   2  down — not serving
#
# The old version ran `curl -I | grep "HTTP/1.1 200 OK"` under `set -e`, which fails
# the whole script on a redirect and tells an operator nothing about why.
set -uo pipefail

BASE="${1:-${BASE_URL:-http://localhost}}"
RED=$'\033[31m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; OFF=$'\033[0m'
[ -t 1 ] || { RED=""; GREEN=""; YELLOW=""; OFF=""; }

printf 'CloudVote health — %s\n\n' "$BASE"

probe() {
  local label="$1" path="$2" status
  status="$(curl -sS -o /tmp/hc.body -w '%{http_code}' --max-time 10 "$BASE$path" 2>/dev/null || echo 000)"
  printf '  %-22s %s' "$label" "$status"
  case "$status" in
    200) printf ' %sok%s\n'            "$GREEN"  "$OFF"; return 0 ;;
    000) printf ' %sno response%s\n'   "$RED"    "$OFF"; return 2 ;;
    503) printf ' %sunavailable%s\n'   "$RED"    "$OFF"; return 2 ;;
    *)   printf ' %sunexpected%s\n'    "$YELLOW" "$OFF"; return 1 ;;
  esac
}

worst=0
note() { [ "$1" -gt "$worst" ] && worst="$1"; return 0; }

probe "nginx"            /nginx-health  ; note $?
probe "vote (liveness)"  /health/live   ; note $?
probe "vote (readiness)" /health/ready  ; note $?
probe "full health"      /health        ; note $?

# The full endpoint carries per-dependency detail. Print it, because "degraded" on its
# own does not tell an operator which dependency to go and look at.
if [ -s /tmp/hc.body ]; then
  printf '\n  dependencies:\n'
  for dep in database redis worker; do
    line="$(grep -o "\"$dep\"[[:space:]]*:[[:space:]]*{[^}]*}" /tmp/hc.body | head -1)"
    if [ -z "$line" ]; then
      printf '    %-10s %snot reported%s\n' "$dep" "$YELLOW" "$OFF"; note 1
    elif printf '%s' "$line" | grep -q '"status"[[:space:]]*:[[:space:]]*"ok"'; then
      printf '    %-10s %sok%s\n' "$dep" "$GREEN" "$OFF"
    else
      printf '    %-10s %s%s%s\n' "$dep" "$RED" "$line" "$OFF"
      # Only the database makes the service unfit to serve; the rest are degradation.
      [ "$dep" = database ] && note 2 || note 1
    fi
  done
fi

printf '\n'
case "$worst" in
  0) printf '%shealthy%s\n'   "$GREEN"  "$OFF" ;;
  1) printf '%sdegraded%s\n'  "$YELLOW" "$OFF" ;;
  *) printf '%sdown%s\n'      "$RED"    "$OFF" ;;
esac
exit "$worst"
