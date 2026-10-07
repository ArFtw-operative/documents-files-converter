from datetime import UTC, datetime, timedelta
import uuid

import jwt
from argon2 import PasswordHasher
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .models import AuthSession, User

hasher = PasswordHasher()
bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return hasher.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return hasher.verify(hashed, password)
    except Exception:
        return False


def create_token(user: User, token_type: str, lifetime: timedelta, session_id: str | None = None) -> str:
    now = datetime.now(UTC)
    claims = {"sub": user.id, "role": user.role.value, "type": token_type, "iat": now, "exp": now + lifetime,
              "jti": str(uuid.uuid4())}
    if session_id: claims["sid"] = session_id
    return jwt.encode(
        claims,
        settings.secret_key,
        algorithm="HS256",
    )


def token_pair(user: User, session_id: str | None = None) -> tuple[str, str]:
    return (
        create_token(user, "access", timedelta(minutes=settings.access_token_minutes), session_id),
        create_token(user, "refresh", timedelta(days=settings.refresh_token_days), session_id),
    )


def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    unauthorized = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    if credentials is None:
        raise unauthorized
    try:
        payload = jwt.decode(credentials.credentials, settings.secret_key, algorithms=["HS256"])
        if payload.get("type") != "access":
            raise unauthorized
        user = db.get(User, payload.get("sub"))
        session_id = payload.get("sid")
        if session_id:
            auth_session = db.get(AuthSession, session_id)
            if not auth_session or auth_session.user_id != payload.get("sub") or auth_session.revoked_at:
                raise unauthorized
    except InvalidTokenError as exc:
        raise unauthorized from exc
    if user is None or not user.is_active:
        raise unauthorized
    return user


def require_admin(user: User = Depends(current_user)) -> User:
    if user.role.value != "admin":
        raise HTTPException(status_code=403, detail="Administrator permission required")
    return user
