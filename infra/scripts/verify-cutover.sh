#!/usr/bin/env bash
# Smoke checks after deploy (see docs/microservices/bigbang-cutover.md).
# Run from host with stack up: ``cd gradelab && ./infra/scripts/verify-cutover.sh``
set -euo pipefail
BASE="${GRADELAB_API:-http://localhost:8000}"
echo "GET $BASE/health"
curl -fsS "$BASE/health"
echo
echo "GET $BASE/ready"
curl -fsS "$BASE/ready"
echo
echo "GET $BASE/api/v1/realms"
curl -fsS "$BASE/api/v1/realms"
echo
