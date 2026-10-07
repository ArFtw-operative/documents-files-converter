"""Login identifiers for an internal deployment.

Pydantic's EmailStr rejects special-use domains such as ``.local`` and ``.lan``, which are normal on
private networks, so only syntax is checked here. Nothing is ever sent to these addresses.
"""

from __future__ import annotations

import re
from typing import Annotated

from pydantic import AfterValidator

_PATTERN = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,253}$")


def _normalise(value: str) -> str:
    value = value.strip().lower()
    if len(value) > 320 or not _PATTERN.match(value):
        raise ValueError("Enter an email address like name@example.org")
    return value


LoginEmail = Annotated[str, AfterValidator(_normalise)]
