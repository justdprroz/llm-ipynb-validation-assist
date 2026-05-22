#!/usr/bin/env bash
set -euo pipefail

# Triggers BGSAVE on Redis and documents copying dump.rdb.
# In Docker: exec into redis container and copy /data/dump.rdb to a mounted backup volume.
#
# Usage:
#   REDIS_HOST=localhost REDIS_PORT=6379 ./backup-redis.sh
# Or: docker compose exec redis redis-cli BGSAVE

REDIS_HOST="${REDIS_HOST:-localhost}"
REDIS_PORT="${REDIS_PORT:-6379}"

if command -v redis-cli >/dev/null 2>&1; then
  echo "Triggering BGSAVE on ${REDIS_HOST}:${REDIS_PORT} ..."
  redis-cli -h "${REDIS_HOST}" -p "${REDIS_PORT}" BGSAVE
  echo "Copy /data/dump.rdb from the Redis data volume to your backup store when LASTSAVE matches."
else
  echo "redis-cli not in PATH. Run: docker compose exec redis redis-cli BGSAVE" >&2
  exit 1
fi
