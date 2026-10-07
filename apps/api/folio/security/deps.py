from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import AuthSession, Role, User
from .crypto import constant_time_equal
from .sessions import CSRF_HEADER, SESSION_COOKIE, resolve_session

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


@dataclass
class Principal:
    user: User
    session: AuthSession


def current_principal(request: Request, db: Session = Depends(get_db)) -> Principal:
    resolved = resolve_session(db, request.cookies.get(SESSION_COOKIE))
    if resolved is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in to continue.")
    session, user = resolved
    if request.method in UNSAFE_METHODS:
        supplied = request.headers.get(CSRF_HEADER) or ""
        if not supplied or not constant_time_equal(supplied, session.csrf_token):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Missing or invalid CSRF token.")
    return Principal(user, session)


def current_user(principal: Principal = Depends(current_principal)) -> User:
    return principal.user


def require_admin(principal: Principal = Depends(current_principal)) -> Principal:
    if principal.user.role != Role.admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Administrator permission required.")
    return principal
