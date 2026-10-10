#!/usr/bin/env bash
set -euo pipefail
echo "Running Squad E automated endpoint health check..."
curl -I -s http://localhost:80 | grep "HTTP/1.1 200 OK" && echo "SUCCESS: Nginx and Vote-Service are responding perfectly!"
