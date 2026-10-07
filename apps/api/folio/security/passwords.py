from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_hasher = PasswordHasher()
# Equalises timing for unknown accounts so login cannot enumerate users.
_DUMMY_HASH = _hasher.hash("verso-folio-dummy-password")

MIN_LENGTH = 10


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, hashed: str | None) -> bool:
    try:
        return _hasher.verify(hashed or _DUMMY_HASH, password) and hashed is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_problem(password: str, email: str = "") -> str | None:
    if len(password) < MIN_LENGTH:
        return f"Use at least {MIN_LENGTH} characters."
    if len(password) > 256:
        return "Use at most 256 characters."
    if email and password.lower() == email.lower():
        return "The password must not be your email address."
    if len(set(password)) < 4:
        return "The password is too repetitive."
    return None
