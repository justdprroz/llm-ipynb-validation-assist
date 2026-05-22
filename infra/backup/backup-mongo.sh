#!/usr/bin/env bash
set -euo pipefail

# Usage: MONGO_URI='mongodb://user:pass@host:27017' BACKUP_ROOT=/backup ./backup-mongo.sh
# Requires: mongodump in PATH (or run inside mongodb/mongodb-community-client image).

MONGO_URI="${MONGO_URI:-mongodb://root:changeme@localhost:27017}"
BACKUP_ROOT="${BACKUP_ROOT:-./out}"
STAMP="$(date -u +%Y%m%d-%H%M%S)"
OUT="${BACKUP_ROOT}/mongodb-${STAMP}"

mkdir -p "${OUT}"

echo "Dumping to ${OUT} ..."
mongodump --uri="${MONGO_URI}" --out="${OUT}/dump"

echo "Done: ${OUT}"
