#!/bin/sh
set -eu
backup_dir="${1:?Usage: scripts/restore.sh BACKUP_DIRECTORY}"
(cd "$backup_dir" && sha256sum -c SHA256SUMS)
docker compose stop api worker-image worker-pdf worker-office worker-general scheduler
docker compose exec -T postgres dropdb -U convertvault --if-exists convertvault
docker compose exec -T postgres createdb -U convertvault convertvault
docker compose exec -T postgres pg_restore -U convertvault -d convertvault --clean --if-exists < "$backup_dir/database.dump"
docker compose exec -T minio sh -c 'rm -rf /data/* && tar -C /data -xzf -' < "$backup_dir/objects.tar.gz"
docker compose start api worker-image worker-pdf worker-office worker-general scheduler
echo "Restore completed. Run acceptance checks before treating this backup as verified."
