"""Opaque server-side sessions in an HttpOnly cookie + double-submit CSRF token.

No bearer tokens are exposed to JavaScript. WebSockets and PDF.js range requests authenticate with
the same cookie. Unsafe methods must echo the ``folio_csrf`` cookie in ``X-CSRF-Token``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import AuthSession, User
from .crypto import digest, token

SESSION_COOKIE = "folio_session"
CSRF_COOKIE = "folio_csrf"
CSRF_HEADER = "x-csrf-token"


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def create_session(db: Session, user: User, request: Request, response: Response) -> AuthSession:
    settings = get_settings()
    raw = token(32)
    now = datetime.now(UTC)
    session = AuthSession(
        user_id=user.id, token_hash=digest(raw), csrf_token=token(24), ip=client_ip(request),
        user_agent=(request.headers.get("user-agent") or "")[:300],
        expires_at=now + timedelta(days=settings.session_absolute_days), last_seen_at=now,
    )
    db.add(session)
    db.flush()
    set_cookies(response, raw, session.csrf_token)
    return session


def set_cookies(response: Response, raw: str, csrf: str) -> None:
    settings = get_settings()
    max_age = settings.session_absolute_days * 86400
    response.set_cookie(SESSION_COOKIE, raw, max_age=max_age, httponly=True, secure=settings.cookie_secure,
                        samesite="lax", path="/")
    response.set_cookie(CSRF_COOKIE, csrf, max_age=max_age, httponly=False, secure=settings.cookie_secure,
                        samesite="strict", path="/")


def clear_cookies(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")


def resolve_session(db: Session, raw: str | None) -> tuple[AuthSession, User] | None:
    if not raw:
        return None
    session = db.scalar(select(AuthSession).where(AuthSession.token_hash == digest(raw)))
    if session is None or session.revoked_at is not None:
        return None
    now = datetime.now(UTC)
    idle = timedelta(hours=get_settings().session_idle_hours)
    if _aware(session.expires_at) <= now or _aware(session.last_seen_at) + idle <= now:
        return None
    user = db.get(User, session.user_id)
    if user is None or not user.is_active:
        return None
    if (now - _aware(session.last_seen_at)).total_seconds() > 60:
        session.last_seen_at = now
        db.commit()
    return session, user


def revoke_user_sessions(db: Session, user_id: str, keep: str | None = None) -> None:
    now = datetime.now(UTC)
    for session in db.scalars(select(AuthSession).where(AuthSession.user_id == user_id,
                                                        AuthSession.revoked_at.is_(None))):
        if session.id != keep:
            session.revoked_at = now
