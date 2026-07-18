#!/bin/sh
set -eu
backup_dir="${1:-./backups/$(date +%Y%m%d-%H%M%S)}"
mkdir -p "$backup_dir"
docker compose exec -T postgres pg_dump -U convertvault -Fc convertvault > "$backup_dir/database.dump"
docker compose exec -T minio sh -c 'tar -C /data -czf - .' > "$backup_dir/objects.tar.gz"
cp .env "$backup_dir/environment.env"
sha256sum "$backup_dir/database.dump" "$backup_dir/objects.tar.gz" > "$backup_dir/SHA256SUMS"
echo "Backup written to $backup_dir. Protect environment.env; it contains secrets."

