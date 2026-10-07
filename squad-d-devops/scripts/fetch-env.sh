#!/usr/bin/env bash
set -euo pipefail

REGION="${AWS_REGION:-us-east-1}"
OUT="${1:-/opt/cloudvote/.env}"

umask 077
TMP="$(mktemp)"

aws ssm get-parameters-by-path \
  --path /cloudvote/prod/ \
  --with-decryption \
  --region "$REGION" \
  --query 'Parameters[*].[Name,Value]' \
  --output text |
while IFS=$'\t' read -r name value; do
  echo "$(basename "$name")=$value"
done > "$TMP"

mv "$TMP" "$OUT"
chmod 600 "$OUT"
echo "Wrote $(wc -l < "$OUT") variables to $OUT"
