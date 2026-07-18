# API summary

All application endpoints are under `/api/v1`. Public endpoints are setup status, first setup, and login. Authenticated endpoints expose the current user, capabilities/engine health, upload/list/detail/download/trash/restore/purge files, list/create/cancel jobs, and server-sent job events. Bearer access tokens are sent in `Authorization`. Schemas and interactive examples are generated at `/api/docs`; the OpenAPI document is `/api/openapi.json`.

