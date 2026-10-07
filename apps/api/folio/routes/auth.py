from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import AppSetting, Role, User
from ..security import mfa
from ..security.crypto import decrypt, encrypt
from ..security.deps import Principal, current_principal
from ..security.emails import LoginEmail
from ..security.passwords import hash_password, password_problem, verify_password
from ..security.sessions import SESSION_COOKIE, clear_cookies, client_ip, create_session, revoke_user_sessions
from ..services import audit

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class Credentials(BaseModel):
    email: LoginEmail
    password: str = Field(min_length=1, max_length=256)
    totp: str | None = Field(default=None, max_length=12)


class SetupRequest(BaseModel):
    email: LoginEmail
    password: str = Field(min_length=1, max_length=256)
    display_name: str = Field(min_length=1, max_length=120)


class PasswordChange(BaseModel):
    current_password: str = Field(max_length=256)
    new_password: str = Field(max_length=256)


class MfaCode(BaseModel):
    code: str = Field(max_length=12)
    password: str | None = Field(default=None, max_length=256)


def user_payload(user: User, csrf: str | None = None) -> dict:
    data = {"id": user.id, "email": user.email, "display_name": user.display_name, "role": user.role.value,
            "mfa_enabled": user.mfa_enabled, "must_change_password": user.must_change_password,
            "quota_bytes": user.quota_bytes, "preferences": user.preferences or {}}
    if csrf:
        data["csrf_token"] = csrf
    return data


def registration_open(db: Session) -> bool:
    setting = db.get(AppSetting, "registration")
    return bool(setting.value.get("open")) if setting else get_settings().registration_open


@router.get("/state")
def state(request: Request, db: Session = Depends(get_db)) -> dict:
    from ..security.sessions import resolve_session

    users = db.scalar(select(func.count()).select_from(User)) or 0
    resolved = resolve_session(db, request.cookies.get(SESSION_COOKIE))
    return {
        "setup_required": users == 0,
        "registration_open": registration_open(db),
        "user": user_payload(resolved[1], resolved[0].csrf_token) if resolved else None,
        "app_name": get_settings().app_name,
    }


@router.post("/setup", status_code=201)
def setup(body: SetupRequest, request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    """First-run: create the initial administrator. Disabled once any account exists."""
    if (db.scalar(select(func.count()).select_from(User)) or 0) > 0:
        raise HTTPException(status.HTTP_409_CONFLICT, "Setup has already been completed.")
    problem = password_problem(body.password, body.email)
    if problem:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, problem)
    user = User(email=body.email.lower(), display_name=body.display_name.strip(), password_hash=hash_password(body.password),
                role=Role.admin, quota_bytes=get_settings().default_quota_bytes, last_login_at=datetime.now(UTC))
    db.add(user)
    db.flush()
    session = create_session(db, user, request, response)
    audit.record(db, "auth.setup", user.id, ip=client_ip(request), session_id=session.id)
    db.commit()
    return user_payload(user, session.csrf_token)


@router.post("/register", status_code=201)
def register(body: SetupRequest, request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    if not registration_open(db):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Ask an administrator to create your account.")
    if db.scalar(select(User).where(User.email == body.email.lower())):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists.")
    problem = password_problem(body.password, body.email)
    if problem:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, problem)
    user = User(email=body.email.lower(), display_name=body.display_name.strip(), password_hash=hash_password(body.password),
                role=Role.user, quota_bytes=get_settings().default_quota_bytes)
    db.add(user)
    db.flush()
    session = create_session(db, user, request, response)
    audit.record(db, "auth.register", user.id, ip=client_ip(request), session_id=session.id)
    db.commit()
    return user_payload(user, session.csrf_token)


@router.post("/login")
def login(body: Credentials, request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    settings = get_settings()
    now = datetime.now(UTC)
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    locked = user is not None and user.locked_until is not None and \
        (user.locked_until if user.locked_until.tzinfo else user.locked_until.replace(tzinfo=UTC)) > now
    valid = verify_password(body.password, user.password_hash if user else None)
    if user is None or not user.is_active or locked or not valid:
        if user is not None and not locked and not valid:
            user.failed_logins += 1
            if user.failed_logins >= settings.login_max_failures:
                user.locked_until = now + timedelta(minutes=settings.login_lock_minutes)
                user.failed_logins = 0
        audit.record(db, "auth.login_failed", user.id if user else None, ip=client_ip(request),
                     email=body.email.lower(), locked=locked)
        db.commit()
        detail = "Too many attempts. Try again later." if locked else "Incorrect email or password."
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail)
    if user.mfa_enabled:
        secret = decrypt(user.mfa_secret_enc or "")
        if not body.totp:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, {"mfa_required": True,
                                                               "message": "Enter your authenticator code."})
        if not secret or not mfa.verify(secret, body.totp):
            user.failed_logins += 1
            db.commit()
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, {"mfa_required": True,
                                                               "message": "That code is not valid."})
    user.failed_logins = 0
    user.locked_until = None
    user.last_login_at = now
    session = create_session(db, user, request, response)
    audit.record(db, "auth.login", user.id, ip=client_ip(request), session_id=session.id)
    db.commit()
    return user_payload(user, session.csrf_token)


@router.post("/logout", status_code=204)
def logout(response: Response, principal: Principal = Depends(current_principal), db: Session = Depends(get_db)) -> None:
    principal.session.revoked_at = datetime.now(UTC)
    db.merge(principal.session)
    audit.record(db, "auth.logout", principal.user.id, session_id=principal.session.id)
    db.commit()
    clear_cookies(response)


@router.get("/me")
def me(principal: Principal = Depends(current_principal)) -> dict:
    return user_payload(principal.user, principal.session.csrf_token)


@router.post("/password", status_code=204)
def change_password(body: PasswordChange, request: Request, principal: Principal = Depends(current_principal),
                    db: Session = Depends(get_db)) -> None:
    user = db.get(User, principal.user.id)
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "The current password is incorrect.")
    problem = password_problem(body.new_password, user.email)
    if problem:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, problem)
    user.password_hash = hash_password(body.new_password)
    user.must_change_password = False
    revoke_user_sessions(db, user.id, keep=principal.session.id)
    audit.record(db, "auth.password_changed", user.id, ip=client_ip(request), session_id=principal.session.id)
    db.commit()


@router.post("/mfa/setup")
def mfa_setup(principal: Principal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    user = db.get(User, principal.user.id)
    if user.mfa_enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, "Two-step sign-in is already on.")
    secret = mfa.new_secret()
    user.mfa_secret_enc = encrypt(secret)
    db.commit()
    return {"secret": secret, "otpauth_uri": mfa.provisioning_uri(secret, user.email)}


@router.post("/mfa/enable", status_code=204)
def mfa_enable(body: MfaCode, principal: Principal = Depends(current_principal), db: Session = Depends(get_db)) -> None:
    user = db.get(User, principal.user.id)
    secret = decrypt(user.mfa_secret_enc or "")
    if not secret or not mfa.verify(secret, body.code):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "That code is not valid.")
    user.mfa_enabled = True
    audit.record(db, "auth.mfa_enabled", user.id, session_id=principal.session.id)
    db.commit()


@router.post("/mfa/disable", status_code=204)
def mfa_disable(body: MfaCode, principal: Principal = Depends(current_principal), db: Session = Depends(get_db)) -> None:
    user = db.get(User, principal.user.id)
    secret = decrypt(user.mfa_secret_enc or "")
    if not verify_password(body.password or "", user.password_hash) or not secret or not mfa.verify(secret, body.code):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Password or code is incorrect.")
    user.mfa_enabled = False
    user.mfa_secret_enc = None
    audit.record(db, "auth.mfa_disabled", user.id, session_id=principal.session.id)
    db.commit()
