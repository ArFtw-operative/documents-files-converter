# Backup and restore

For a maintenance-window backup, stop API/workers/scheduler, run `scripts/backup.sh`, restart services, and restore the archive into a disposable instance to verify it. The script captures a PostgreSQL custom dump, MinIO data archive, checksums, and `.env`; the environment copy contains sensitive secrets and must be encrypted by the operator.

For snapshot-capable storage, quiesce writes, capture database and object-volume snapshots from the same consistency point, then resume. Never combine unrelated snapshots. Use `scripts/restore.sh BACKUP_DIRECTORY` only in a maintenance window; it replaces the current database and object data. A backup is not valid until an isolated restore passes login, library, download, and conversion checks.

