from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ..models import AppSetting, AuditLog


def privacy_mode(db: Session) -> bool:
    """§45: optionally suppress old/new text values in the audit log."""
    setting = db.get(AppSetting, "audit")
    return bool(setting and setting.value.get("privacy_mode"))


def record(db: Session, action: str, actor_id: str | None, *, document_id: str | None = None,
           ip: str | None = None, session_id: str | None = None, **details: Any) -> None:
    if privacy_mode(db):
        details = {k: v for k, v in details.items() if k not in ("old_text", "new_text")}
    db.add(AuditLog(action=action, actor_id=actor_id, document_id=document_id, ip=ip,
                    session_id=session_id, details=details))
