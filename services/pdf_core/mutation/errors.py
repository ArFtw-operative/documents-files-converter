from __future__ import annotations

from typing import Any


class MutationError(Exception):
    """A user-recoverable mutation failure with a stable machine code.

    Codes: ``target_modified``, ``target_not_found``, ``not_editable``, ``needs_confirmation``,
    ``font_unavailable``, ``unsupported_operation``, ``encrypted``, ``validation_failed``,
    ``invalid_payload``.
    """

    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "details": self.details}
