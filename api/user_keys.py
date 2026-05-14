"""
Resolve which Gemini API key to use for a given user's render.

Resolution order:
  1. If `BYO_KEY_USERS` env contains this user id, OR the user's
     plan == "byo" — use their stored encrypted key. This is the
     code-sale path: someone bought the self-hosted/desktop tier and
     brings their own Gemini billing.
  2. Otherwise (default) — pick the next platform key from the
     rotator. We own the billing for all subscription tiers.

The platform path raises NoApiKeyError if no GEMINI_API_KEY(S) is set
on the host so misconfigured deployments fail loudly instead of
silently falling back to user keys.
"""

from __future__ import annotations

import os
from typing import Set

from keyvault import decrypt
import platform_keys


def _coll():
    from app import db
    return db().tool_settings


class NoApiKeyError(RuntimeError):
    pass


def _byo_user_ids() -> Set[str]:
    raw = os.environ.get("BYO_KEY_USERS", "")
    return {u.strip() for u in raw.split(",") if u.strip()}


def _is_byo_user(user_id: str, user_plan: str = "") -> bool:
    if user_plan == "byo":
        return True
    return user_id in _byo_user_ids()


def get_gemini_key(user_id: str, user_plan: str = "") -> str:
    """
    Resolve the Gemini key for this user's render. See module docstring
    for resolution order.
    """
    if _is_byo_user(user_id, user_plan):
        settings = _coll().find_one({"userId": user_id}) or {}
        encrypted = settings.get("geminiKey")
        if not encrypted:
            raise NoApiKeyError(
                "Bring-your-own-key mode but no key saved. "
                "Add your Gemini API key in Settings."
            )
        return decrypt(encrypted)

    try:
        return platform_keys.next_key()
    except platform_keys.NoPlatformKeyError as e:
        raise NoApiKeyError(str(e))
