#!/usr/bin/env bash
# Consistent Verso Folio backup: PostgreSQL dump + content-addressed storage.
#   bash infra/deploy/backup.sh [DESTINATION_DIR]   (default: ~/folio-backups)
# Restore: see docs/verso-folio/operations.md.
set -euo pipefail

DEST="${1:-$HOME/folio-backups}"
STAMP="$(date +%Y%m%d-%H%M%S)"
TARGET="$DEST/$STAMP"
mkdir -p "$TARGET"
chmod 700 "$DEST" "$TARGET"

docker exec folio-db pg_dump -U folio -d folio --format=custom > "$TARGET/folio.pgdump"
# Blobs are immutable and written atomically, so a live copy is consistent with the dump taken
# just before it (blobs newer than the dump are simply unreferenced).
docker run --rm --user "$(id -u):$(id -g)" -v folio_storage:/data:ro -v "$TARGET":/backup alpine:3.22 \
  tar -C /data --exclude=./temp -czf /backup/storage.tar.gz .
( cd "$TARGET" && sha256sum folio.pgdump storage.tar.gz > SHA256SUMS )
echo "Backup written to $TARGET"
