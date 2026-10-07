"""Secret encryption at rest (MFA seeds, AI provider keys). Key derived from FOLIO_SECRET_KEY."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from ..config import get_settings


@lru_cache
def _fernet() -> Fernet:
    key = HKDF(algorithm=hashes.SHA256(), length=32, salt=b"verso-folio", info=b"secrets-at-rest").derive(
        get_settings().secret_key.encode())
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt(value: str) -> str | None:
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken:
        return None


def token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def constant_time_equal(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())
