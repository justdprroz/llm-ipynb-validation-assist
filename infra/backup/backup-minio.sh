#!/usr/bin/env bash
set -euo pipefail

# Requires MinIO Client: https://min.io/docs/minio/linux/reference/minio-mc.html
# One-time setup (example):
#   mc alias set gradelab http://localhost:9000 minioadmin minioadmin
#   mc mb -p gradelab/gradelab-homeworks || true
#
# Usage: ./backup-minio.sh
# Mirrors all buckets under alias `gradelab` to BACKUP_ROOT/minio-mirror-Stamp/

ALIAS="${MC_ALIAS:-gradelab}"
BACKUP_ROOT="${BACKUP_ROOT:-./out}"
STAMP="$(date -u +%Y%m%d-%H%M%S)"
DEST="${BACKUP_ROOT}/minio-mirror-${STAMP}"

mkdir -p "${DEST}"

if ! command -v mc >/dev/null 2>&1; then
  echo "mc (MinIO Client) not found. Install mc or run this script in a container with mc." >&2
  exit 1
fi

echo "Mirroring ${ALIAS} -> ${DEST} ..."
mc mirror --overwrite "${ALIAS}" "${DEST}"
echo "Done: ${DEST}"
