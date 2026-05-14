"""
Runtime-mutable config (Gemini keys, Razorpay creds, feature flags) that
the owner can edit from the admin UI without touching the .env file.

Storage
-------
A single Mongo document at `tool_runtime_config._id = "singleton"`.
Secret fields (API keys, Razorpay secret, webhook secret) are encrypted
at rest using the existing keyvault.encrypt/decrypt helpers — same
mechanism we use for user Gemini keys.

Read path
---------
`get_config_value(name)` returns DB value if present, else env fallback.
This lets the operator stage credentials in .env for boot-time tests
and then move them to the DB without code changes.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from keyvault import decrypt, encrypt, mask


_SINGLETON_ID = "singleton"

# Names of fields we treat as secrets. They're encrypted at rest and we
# only ever return a masked preview to the frontend.
SECRET_FIELDS = {
    "geminiApiKeys",       # comma-separated list of platform Gemini keys
    "razorpayKeyId",       # technically not secret but we keep it grouped
    "razorpayKeySecret",
    "razorpayWebhookSecret",
    # Cheap FLUX-schnell providers — used in cost-ascending fallback chain
    # before Gemini. See image_providers.py.
    "togetherApiKey",
    "replicateApiKey",
    "fireworksApiKey",
}

# Non-secret toggles / values stored alongside the secrets.
PUBLIC_FIELDS = {
    "razorpayEnabled",
    "byoKeyUserIds",       # comma-separated user ids that must BYO
    "imageProviderOrder",  # comma-sep: e.g. "together,replicate,fireworks"
}


def _coll():
    from app import db
    return db().tool_runtime_config


def _get_doc() -> dict:
    doc = _coll().find_one({"_id": _SINGLETON_ID}) or {}
    return doc


def get_config_value(name: str) -> Optional[str]:
    """
    Resolve a config value. DB first (decrypted if secret), then env.
    Returns None if neither has it.
    """
    doc = _get_doc()
    raw = doc.get(name)
    if raw:
        if name in SECRET_FIELDS:
            try:
                return decrypt(raw)
            except Exception:
                # Stored value is garbage; fall through to env so we don't
                # silently break boot.
                pass
        else:
            return str(raw)
    env_name = _env_name_for(name)
    return os.environ.get(env_name)


def _env_name_for(name: str) -> str:
    """Map a runtime-config name to its .env equivalent."""
    return {
        "geminiApiKeys": "GEMINI_API_KEYS",
        "razorpayKeyId": "RAZORPAY_KEY_ID",
        "razorpayKeySecret": "RAZORPAY_KEY_SECRET",
        "razorpayWebhookSecret": "RAZORPAY_WEBHOOK_SECRET",
        "razorpayEnabled": "RAZORPAY_ENABLED",
        "byoKeyUserIds": "BYO_KEY_USERS",
        "togetherApiKey": "TOGETHER_API_KEY",
        "replicateApiKey": "REPLICATE_API_TOKEN",
        "fireworksApiKey": "FIREWORKS_API_KEY",
        "imageProviderOrder": "IMAGE_PROVIDER_ORDER",
    }.get(name, name.upper())


def get_gemini_keys() -> list[str]:
    """
    Resolved list of Gemini keys. DB > GEMINI_API_KEYS env > GEMINI_API_KEY env.
    """
    raw = get_config_value("geminiApiKeys")
    if raw:
        keys = [k.strip() for k in raw.split(",") if k.strip()]
        if keys:
            return keys
    single = os.environ.get("GEMINI_API_KEY", "").strip()
    return [single] if single else []


def get_byo_user_ids() -> set[str]:
    raw = get_config_value("byoKeyUserIds") or ""
    return {u.strip() for u in raw.split(",") if u.strip()}


def get_razorpay_creds() -> dict[str, str]:
    return {
        "keyId": get_config_value("razorpayKeyId") or "",
        "keySecret": get_config_value("razorpayKeySecret") or "",
        "webhookSecret": get_config_value("razorpayWebhookSecret") or "",
    }


# ---- Admin write path -----------------------------------------------------

def set_config_values(updates: dict[str, Any]) -> dict:
    """
    Bulk set config fields. Secret fields are encrypted before write.
    Empty string clears a field (back to env fallback).

    Returns the *masked* view of the current config (safe for the admin UI).
    """
    now = datetime.now(timezone.utc)
    op_set: dict[str, Any] = {"updatedAt": now}
    op_unset: dict[str, str] = {}

    for name, value in updates.items():
        if name not in SECRET_FIELDS and name not in PUBLIC_FIELDS:
            continue  # silently ignore unknown keys — defense against typos
        if value is None or value == "":
            op_unset[name] = ""
            continue
        if name in SECRET_FIELDS:
            op_set[name] = encrypt(str(value))
        else:
            op_set[name] = str(value)

    update: dict[str, Any] = {"$set": op_set}
    if op_unset:
        update["$unset"] = op_unset

    _coll().update_one(
        {"_id": _SINGLETON_ID},
        update,
        upsert=True,
    )
    # Reset the platform-key rotator so the new keys take effect immediately
    # without a server restart.
    try:
        import platform_keys
        platform_keys.reset()
    except Exception:
        pass

    return masked_view()


def masked_view() -> dict[str, Any]:
    """
    What the admin UI sees. Secrets show as their mask; non-secrets show
    plain. Always includes an indication of whether a value is sourced
    from DB vs env.
    """
    doc = _get_doc()
    out: dict[str, Any] = {}

    for name in SECRET_FIELDS:
        db_val = doc.get(name)
        env_val = os.environ.get(_env_name_for(name)) if name in SECRET_FIELDS else None
        if db_val:
            try:
                plain = decrypt(db_val)
            except Exception:
                plain = ""
            out[name] = {
                "source": "db",
                "mask": mask(plain) if plain else None,
                "set": bool(plain),
            }
        elif env_val:
            out[name] = {
                "source": "env",
                "mask": mask(env_val),
                "set": True,
            }
        else:
            out[name] = {"source": None, "mask": None, "set": False}

    for name in PUBLIC_FIELDS:
        db_val = doc.get(name)
        env_val = os.environ.get(_env_name_for(name))
        if db_val:
            out[name] = {"source": "db", "value": str(db_val), "set": True}
        elif env_val:
            out[name] = {"source": "env", "value": str(env_val), "set": True}
        else:
            out[name] = {"source": None, "value": "", "set": False}

    # Resolved view — what the rest of the app will actually use.
    out["resolved"] = {
        "geminiKeyCount": len(get_gemini_keys()),
        "razorpayConfigured": bool(
            get_config_value("razorpayKeyId") and get_config_value("razorpayKeySecret")
        ),
        "byoUserCount": len(get_byo_user_ids()),
        "togetherReady": bool(get_config_value("togetherApiKey")),
        "replicateReady": bool(get_config_value("replicateApiKey")),
        "fireworksReady": bool(get_config_value("fireworksApiKey")),
    }
    return out
