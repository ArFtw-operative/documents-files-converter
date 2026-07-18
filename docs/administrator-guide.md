# Administrator guide

The first successful `/api/v1/setup` request creates the sole initial administrator and permanently closes setup. Keep registration private until this is complete. Engine health is available at `/api/v1/engines`; API documentation is at `/api/docs`.

Monitor `docker compose ps`, API logs, queue-specific worker logs, volume capacity, PostgreSQL backups, Redis persistence, MinIO health, and failed job counts. Keep Office/OCR concurrency at one until hardware testing supports an increase. Never publish MinIO, PostgreSQL, Redis, or Flower without independent authentication and network controls.

Upgrade by making and restoring a test backup, reading release notes, pulling/building images, running `docker compose run --rm migrate`, and recreating services. Database downgrade support is limited; restore is the safest rollback. Run the tests and key conversions after every engine or font update.

