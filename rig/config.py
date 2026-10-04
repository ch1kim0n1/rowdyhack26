"""One parser for every env knob.

Modules used to re-roll os.environ.get + try/except at every call site, and
a typo in one place crashed (int("abc") on CAM_INDEX) or silently parsed
differently from its neighbors. Everything funnels through here now. Reads
stay lazy — call time, not import time — so .env loads and test env patches
land no matter when a module was first imported.
"""
from __future__ import annotations

import os

_ON = {"1", "true", "yes", "on"}
_OFF = {"0", "false", "no", "off"}


def env_str(name: str, default: str = "") -> str:
    return os.environ.get(name, "").strip() or default


def env_flag(name: str, default: bool = False) -> bool:
    """1/true/yes/on -> True, 0/false/no/off -> False, unset or junk -> default."""
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    if raw in _ON:
        return True
    if raw in _OFF:
        return False
    return default


def env_int(name: str, default: int, lo: int | None = None, hi: int | None = None) -> int:
    try:
        value = int(os.environ.get(name, "").strip() or default)
    except (TypeError, ValueError):
        return default
    if lo is not None:
        value = max(lo, value)
    if hi is not None:
        value = min(hi, value)
    return value


def env_float(name: str, default: float, lo: float | None = None, hi: float | None = None) -> float:
    try:
        value = float(os.environ.get(name, "").strip() or default)
    except (TypeError, ValueError):
        return default
    if lo is not None:
        value = max(lo, value)
    if hi is not None:
        value = min(hi, value)
    return value


def env_ints(name: str, default: str = "") -> list[int]:
    """Comma-separated ints (pin lists). Unparseable -> []."""
    raw = os.environ.get(name, "").strip() or default
    try:
        return [int(p) for p in raw.split(",") if p.strip()]
    except ValueError:
        return []
