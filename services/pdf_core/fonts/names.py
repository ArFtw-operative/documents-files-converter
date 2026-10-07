"""Font-name normalisation shared by the analyzer and the font resolver."""

from __future__ import annotations

import re

_SUBSET = re.compile(r"^[A-Z]{6}\+")
_STYLE_WORDS = {
    "regular", "roman", "book", "normal", "medium", "bold", "semibold", "demibold", "demi",
    "extrabold", "black", "heavy", "light", "extralight", "thin", "italic", "oblique",
    "boldItalic".lower(), "bolditalic", "boldoblique", "it", "bd", "bi", "mt", "ps", "psmt",
    "condensed", "cond", "narrow",
}


def strip_subset(name: str) -> tuple[str, bool]:
    if _SUBSET.match(name or ""):
        return name[7:], True
    return name or "", False


def is_bold_name(name: str) -> bool:
    lowered = name.lower()
    return any(word in lowered for word in ("bold", "black", "heavy", "semibold", "demi"))


def is_italic_name(name: str) -> bool:
    lowered = name.lower()
    return "italic" in lowered or "oblique" in lowered


def family_name(font_name: str) -> str:
    """Best-effort family for fontconfig: ``ABCDEE+HelveticaNeueLTStd-BoldIt`` → ``Helvetica Neue LT Std``."""
    name, _ = strip_subset(font_name)
    name = name.split(",")[0]
    base = re.split(r"[-_]", name)[0] if "-" in name or "_" in name else name
    # Split CamelCase while keeping acronyms ("LTStd" → "LT Std").
    spaced = re.sub(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", base)
    words = [w for w in spaced.split() if w.lower() not in _STYLE_WORDS]
    if words and words[-1].upper() == "MT":
        words = words[:-1]
    return " ".join(words) or name or "sans-serif"
