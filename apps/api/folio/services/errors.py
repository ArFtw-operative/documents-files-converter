from __future__ import annotations

from typing import Any


class ServiceError(Exception):
    """Domain error translated to an HTTP response by the API layer."""

    status = 400

    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None, status: int | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}
        if status is not None:
            self.status = status

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "details": self.details}


class NotFound(ServiceError):
    status = 404

    def __init__(self, message: str = "Not found."):
        super().__init__("not_found", message)


class Conflict(ServiceError):
    status = 409


# Engine error code -> HTTP status
ENGINE_STATUS = {
    "target_modified": 409, "target_not_found": 409, "not_editable": 422, "needs_confirmation": 422,
    "font_unavailable": 422, "unsupported_operation": 422, "encrypted": 423, "invalid_payload": 422,
    "validation_failed": 500, "signed_document": 428,
}
