#!/usr/bin/env bash
set -euo pipefail

# Usage: MONGO_URI='mongodb://user:pass@host:27017' ./restore-mongo.sh /backup/mongodb-YYYYMMDD-HHMM/dump

if [[ $# -lt 1 ]]; then
  echo "Usage: MONGO_URI=... $0 <path-to-dump-directory>" >&2
  exit 1
fi

DUMP="$1"
MONGO_URI="${MONGO_URI:-mongodb://root:changeme@localhost:27017}"

echo "Restoring from ${DUMP} into ${MONGO_URI} ..."
mongorestore --uri="${MONGO_URI}" --drop "${DUMP}"
echo "Restore complete."
