"""Administration (D2): accounts and settings. Admins never browse other users' documents."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import AppSetting, AuditLog, Blob, Document, DocumentStatus, Role, User
from ..security.deps import Principal, require_admin
from ..security.emails import LoginEmail
from ..security.passwords import hash_password, password_problem
from ..security.sessions import revoke_user_sessions
from ..services import audit

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


class NewUser(BaseModel):
    email: LoginEmail
    display_name: str = Field(min_length=1, max_length=120)
    password: str = Field(max_length=256)
    role: Role = Role.user
    quota_bytes: int | None = Field(default=None, ge=0)


class UserUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=120)
    role: Role | None = None
    is_active: bool | None = None
    quota_bytes: int | None = Field(default=None, ge=0)
    new_password: str | None = Field(default=None, max_length=256)
    reset_mfa: bool = False


class SettingsUpdate(BaseModel):
    registration_open: bool | None = None
    audit_privacy_mode: bool | None = None


def _row(db: Session, user: User) -> dict:
    used = db.scalar(select(func.coalesce(func.sum(Blob.size), 0)).where(Blob.owner_id == user.id)) or 0
    documents = db.scalar(select(func.count()).select_from(Document).where(
        Document.owner_id == user.id, Document.status != DocumentStatus.deleted)) or 0
    return {"id": user.id, "email": user.email, "display_name": user.display_name, "role": user.role.value,
            "is_active": user.is_active, "mfa_enabled": user.mfa_enabled, "quota_bytes": user.quota_bytes,
            "used_bytes": int(used), "documents": documents, "created_at": user.created_at,
            "last_login_at": user.last_login_at}


@router.get("/users")
def list_users(_: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> list[dict]:
    return [_row(db, user) for user in db.scalars(select(User).order_by(User.created_at))]


@router.post("/users", status_code=201)
def create_user(body: NewUser, admin: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    if db.scalar(select(User).where(User.email == body.email.lower())):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists.")
    problem = password_problem(body.password, body.email)
    if problem:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, problem)
    user = User(email=body.email.lower(), display_name=body.display_name.strip(),
                password_hash=hash_password(body.password), role=body.role, must_change_password=True,
                quota_bytes=body.quota_bytes if body.quota_bytes is not None else get_settings().default_quota_bytes)
    db.add(user)
    db.flush()
    audit.record(db, "admin.user_created", admin.user.id, target_user=user.id, role=user.role.value)
    db.commit()
    return _row(db, user)


@router.patch("/users/{user_id}")
def update_user(user_id: str, body: UserUpdate, admin: Principal = Depends(require_admin),
                db: Session = Depends(get_db)) -> dict:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found.")
    if user.id == admin.user.id and (body.role == Role.user or body.is_active is False):
        raise HTTPException(status.HTTP_409_CONFLICT, "You cannot demote or disable your own account.")
    changes: dict = {}
    if body.display_name is not None:
        user.display_name = body.display_name.strip()
        changes["display_name"] = True
    if body.role is not None:
        user.role = body.role
        changes["role"] = body.role.value
    if body.quota_bytes is not None:
        user.quota_bytes = body.quota_bytes
        changes["quota_bytes"] = body.quota_bytes
    if body.is_active is not None:
        user.is_active = body.is_active
        changes["is_active"] = body.is_active
        if not body.is_active:
            revoke_user_sessions(db, user.id)
    if body.new_password:
        problem = password_problem(body.new_password, user.email)
        if problem:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, problem)
        user.password_hash = hash_password(body.new_password)
        user.must_change_password = True
        user.failed_logins, user.locked_until = 0, None
        revoke_user_sessions(db, user.id)
        changes["password_reset"] = True
    if body.reset_mfa:
        user.mfa_enabled, user.mfa_secret_enc = False, None
        changes["mfa_reset"] = True
    audit.record(db, "admin.user_updated", admin.user.id, target_user=user.id, **changes)
    db.commit()
    return _row(db, user)


@router.get("/settings")
def get_app_settings(_: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    registration = db.get(AppSetting, "registration")
    audit_setting = db.get(AppSetting, "audit")
    return {
        "registration_open": bool(registration.value.get("open")) if registration else get_settings().registration_open,
        "audit_privacy_mode": bool(audit_setting and audit_setting.value.get("privacy_mode")),
    }


@router.patch("/settings")
def update_app_settings(body: SettingsUpdate, admin: Principal = Depends(require_admin),
                        db: Session = Depends(get_db)) -> dict:
    if body.registration_open is not None:
        db.merge(AppSetting(key="registration", value={"open": body.registration_open}))
    if body.audit_privacy_mode is not None:
        db.merge(AppSetting(key="audit", value={"privacy_mode": body.audit_privacy_mode}))
    audit.record(db, "admin.settings_updated", admin.user.id, **body.model_dump(exclude_none=True))
    db.commit()
    return get_app_settings(admin, db)


@router.get("/audit")
def audit_log(limit: int = 200, _: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(min(max(limit, 1), 1000)))
    return [{"id": r.id, "at": r.created_at, "actor_id": r.actor_id, "action": r.action,
             "document_id": r.document_id, "ip": r.ip, "details": r.details} for r in rows]
