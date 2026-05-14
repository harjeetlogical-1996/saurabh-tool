"""
Platform Gemini API key rotator.

We own the Gemini billing. To get higher parallel throughput we hold
multiple API keys (each one has its own rate-limit bucket on Google's
side) and round-robin between them per request.

Sources (in priority order):
  1. `tool_runtime_config.geminiApiKeys` — set from the admin UI
  2. `GEMINI_API_KEYS` env (comma-separated)
  3. `GEMINI_API_KEY` env (single)

Throughput is the only reason for multiple keys — cost is the same
because all keys roll up to one Cloud billing account.
"""

from __future__ import annotations

import itertools
import threading
from typing import Optional


class NoPlatformKeyError(RuntimeError):
    pass


_LOCK = threading.Lock()
_CYCLE: Optional[itertools.cycle] = None
_KEYS: list[str] = []


def _load_keys() -> list[str]:
    # Lazy import — runtime_config imports keyvault which imports nothing
    # heavy, but keep this pattern to avoid any chance of a startup cycle.
    try:
        from runtime_config import get_gemini_keys
        return get_gemini_keys()
    except Exception:
        import os
        multi = os.environ.get("GEMINI_API_KEYS", "").strip()
        if multi:
            return [k.strip() for k in multi.split(",") if k.strip()]
        single = os.environ.get("GEMINI_API_KEY", "").strip()
        return [single] if single else []


def _ensure_loaded() -> None:
    global _CYCLE, _KEYS
    if _CYCLE is not None:
        return
    with _LOCK:
        if _CYCLE is not None:
            return
        _KEYS = _load_keys()
        if not _KEYS:
            raise NoPlatformKeyError(
                "No platform Gemini key configured. "
                "Add one in /admin/keys or set GEMINI_API_KEYS env."
            )
        _CYCLE = itertools.cycle(_KEYS)


def reset() -> None:
    """
    Drop the cached rotator. Called when the admin UI saves new keys
    so the change takes effect on the very next request without a
    server restart.
    """
    global _CYCLE, _KEYS
    with _LOCK:
        _CYCLE = None
        _KEYS = []


def next_key() -> str:
    """Round-robin pick. Thread-safe."""
    _ensure_loaded()
    assert _CYCLE is not None
    with _LOCK:
        return next(_CYCLE)


def key_count() -> int:
    try:
        _ensure_loaded()
    except NoPlatformKeyError:
        return 0
    return len(_KEYS)
