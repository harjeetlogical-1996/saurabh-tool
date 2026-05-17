"""
Read the Better Auth session cookie shared across .saurabhbhayana.com and
resolve it to a user document. We don't verify Better Auth's HMAC signature
ourselves; we trust the value only after we've found a matching live row in
the `session` collection.

Better Auth's session cookie is named:
    {AUTH_COOKIE_PREFIX}.session_token

The value is "<token>.<signature>". The token half (before the dot) is what
gets stored in `session.token` in Mongo.

If something looks suspicious — token missing, no row, or expired — we 401.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, Request

# Lazy import so this file can be imported during static analysis without
# Mongo being configured.
def _db():
    from app import db  # local import to avoid circular at startup
    return db()


COOKIE_PREFIX = os.environ.get("AUTH_COOKIE_PREFIX", "saurabh")
SESSION_COOKIE_NAME = f"{COOKIE_PREFIX}.session_token"


@dataclass
class AuthUser:
    id: str
    email: str
    name: Optional[str]
    role: str
    plan: str


def _extract_token(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    # Better Auth shape is "<token>.<signature>". We index by the token half.
    # If the cookie is URL-encoded (some proxies do this), strip the encoding.
    raw = raw.replace("%2E", ".").replace("%2e", ".")
    if "." in raw:
        return raw.split(".", 1)[0]
    return raw


def current_user(request: Request) -> AuthUser:
    db = _db()

    # ---- DEV ONLY: ?dev_user_id=<id> bypass --------------------------------
    # Activated only when ALLOW_DEV_AUTH=1 in env. Lets us test the API
    # locally without setting up cross-subdomain hosts files. Strip this
    # block in production by leaving the env var unset.
    #
    # When the dev shortcut hits we set `user` and skip session lookup,
    # but we still fall through to the whitelist gate below so the
    # invite-only behavior is testable locally.
    user = None
    if os.environ.get("ALLOW_DEV_AUTH") == "1":
        dev_id = request.query_params.get("dev_user_id")
        if dev_id:
            user = db.user.find_one({"_id": _maybe_object_id(dev_id)})

    if user is None:
        # Better Auth auto-prefixes the cookie with __Secure- when the
        # site runs on HTTPS (RFC 6265bis cookie-prefixes spec). The
        # plain name is used on http://localhost. Check both so the
        # same code works in dev and prod without a separate config.
        cookie = (
            request.cookies.get(f"__Secure-{SESSION_COOKIE_NAME}")
            or request.cookies.get(SESSION_COOKIE_NAME)
        )
        token = _extract_token(cookie)
        if not token:
            raise HTTPException(status_code=401, detail="Not signed in.")

        session = db.session.find_one({"token": token})
        if not session:
            raise HTTPException(status_code=401, detail="Session not found.")

        expires_at = session.get("expiresAt")
        if isinstance(expires_at, datetime):
            # Better Auth stores tz-aware datetimes; normalize for comparison.
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at < datetime.now(timezone.utc):
                raise HTTPException(status_code=401, detail="Session expired.")

        user_id = session.get("userId")
        if not user_id:
            raise HTTPException(status_code=401, detail="Session has no user.")

        user = db.user.find_one({"_id": _maybe_object_id(user_id)})
        if not user:
            raise HTTPException(status_code=401, detail="User not found.")

    resolved = AuthUser(
        id=str(user["_id"]),
        email=str(user.get("email") or ""),
        name=user.get("name"),
        role=str(user.get("role") or "user"),
        plan=str(user.get("plan") or "free"),
    )

    # Early-access whitelist gate. While `INVITE_GATE=1` is set we deny
    # every authenticated request whose email isn't in tool_invites.
    # Owners (and the legacy "pro" plan) always bypass. The check is
    # opt-in so local dev without the env flag keeps working unchanged.
    if os.environ.get("INVITE_GATE", "1") == "1":
        try:
            from invites import is_whitelisted
            if not is_whitelisted(resolved.email, plan=resolved.plan):
                raise HTTPException(
                    status_code=403,
                    detail=(
                        "Tools are invite-only right now. "
                        "Email saurabhbhayana1996@gmail.com to request access."
                    ),
                )
        except HTTPException:
            raise
        except Exception as e:
            # Anything other than a clean denial: log and let through so
            # a bad whitelist read can't lock everyone out. Operator can
            # tighten this once we trust the index.
            print(f"[auth] whitelist read failed, allowing through: {e}")

    return resolved


def _maybe_object_id(value):
    """
    Better Auth sometimes stores userId as a string and sometimes as an
    ObjectId depending on adapter version. Try both.
    """
    from bson import ObjectId  # type: ignore
    from bson.errors import InvalidId  # type: ignore

    if isinstance(value, ObjectId):
        return value
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        return value
