# Verso Folio — Operations

## Stack

| Container | Role | Networks |
|---|---|---|
| `folio-web` | Static editor (Caddy, port 8080) | `atlas-proxy` |
| `folio-api` | FastAPI, sessions, events (port 8000); never parses PDFs in production | `atlas-proxy`, `folio_backend` |
| `folio-worker-cpu` | The only PDF parser/writer: analysis, mutation, export, maintenance | `folio_backend` only (no internet) |
| `folio-scheduler` | Celery beat (hourly maintenance) | `folio_backend` |
| `folio-db` | PostgreSQL 17 (volume `folio_db`) | `folio_backend` |
| `folio-valkey` | Queue, results, realtime events (volume `folio_valkey`) | `folio_backend` |

Files live in the `folio_storage` volume (`blobs/<owner>/<sha[:2]>/<sha>.pdf`, `temp/`, `failed/`).
Secrets are in `.env.folio` at the repository root (mode 600, git-ignored).

## Start, update, stop

```sh
docker compose -f infra/compose.yml --env-file .env.folio up -d --build   # start or update
docker compose -f infra/compose.yml --env-file .env.folio ps
docker compose -f infra/compose.yml --env-file .env.folio logs -f folio-api folio-worker-cpu
docker compose -f infra/compose.yml --env-file .env.folio down            # stop (keeps volumes)
```

Database migrations run automatically in `folio-migrate` before the API starts.

## Publish at https://folio.local (once, requires root)

```sh
sudo bash infra/deploy/enable-folio-local.sh
```

The script adds a LAN-only `folio.local` site to the shared Caddy. It backs up the Caddyfile,
validates the config and rolls back on error. It also installs `folio-mdns.service` to publish the
name over mDNS. On first visit, create the administrator account.

## Accounts

The first visitor creates the administrator. After that, administrators add people under
**Admin → Users**; they receive a temporary password and are asked to change it. Self-registration
is off unless enabled in **Admin → Settings**. Each person sees only their own documents.

## Backup and restore

```sh
bash infra/deploy/backup.sh                # → ~/folio-backups/<timestamp>/
```

Restore into an empty stack:

```sh
docker compose -f infra/compose.yml --env-file .env.folio up -d folio-db
docker exec -i folio-db pg_restore -U folio -d folio --clean --if-exists < BACKUP/folio.pgdump
docker run --rm -v folio_storage:/data -v BACKUP:/backup alpine:3.22 sh -c 'tar -C /data -xzf /backup/storage.tar.gz && chown -R 10001:10001 /data'
docker compose -f infra/compose.yml --env-file .env.folio up -d
```

## GPU

OCR (milestone 3) runs on the RTX 3050. On 2026-10-07 the NVIDIA kernel module was not loaded for
kernel `7.0.0-38-generic` (`nvidia-smi` failed; Ollama ran on CPU). The likely fix is to rebuild
the driver for the running kernel and reboot:

```sh
sudo apt install --reinstall nvidia-dkms-595-open linux-headers-$(uname -r)
sudo reboot
nvidia-smi        # must list the RTX 3050
```

## Retiring ConvertVault

ConvertVault still runs at `documents-converter.local` from `legacy/` (its containers were
built before the move, so it is unaffected). After Verso Folio is in use:

1. Export anything needed from ConvertVault, or let the planned migration script import its PDFs into Folio accounts.
2. `docker compose -p convertvault -f legacy/docker-compose.yml --env-file .env down` (add `-v` only once data is confirmed migrated).
3. Point `documents-converter.local` at Folio with a Caddy `redir`, or remove the site and its mDNS service.
