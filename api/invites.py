"""
Email whitelist for the tools subdomain.

While we're in early-access mode every API call (other than /health,
/plans, and admin endpoints) is gated on the caller's email being in
`tool_invites`. The user already authenticated through Better Auth on
saurabhbhayana.com so we trust the email field on the session-resolved
user document.

Owners and the legacy "pro" plan bypass the whitelist so the operator
never locks themselves out.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional


def _coll():
    from app import db
    return db().tool_invites


# Plans that ALWAYS pass the whitelist (operator + paid history).
BYPASS_PLANS = {"owner", "pro"}


def _normalize(email: str) -> str:
    return (email or "").strip().lower()


def is_whitelisted(email: str, plan: Optional[str] = None) -> bool:
    """True if this email may use the tools at all."""
    if plan in BYPASS_PLANS:
        return True
    e = _normalize(email)
    if not e:
        return False
    doc = _coll().find_one({"email": e, "active": True})
    return doc is not None


def list_invites(limit: int = 500) -> list[dict]:
    """Newest-first list of whitelist entries."""
    rows = list(
        _coll()
        .find({})
        .sort("createdAt", -1)
        .limit(max(1, min(2000, limit)))
    )
    out: list[dict] = []
    for r in rows:
        out.append(
            {
                "email": r.get("email"),
                "active": bool(r.get("active", True)),
                "note": r.get("note") or "",
                "addedBy": r.get("addedBy") or "",
                "createdAt": _iso(r.get("createdAt")),
                "updatedAt": _iso(r.get("updatedAt")),
            }
        )
    return out


def add_invite(email: str, *, added_by: str, note: str = "") -> dict:
    """
    Add (or re-activate) a whitelist entry. Idempotent — calling on an
    already-active email is a no-op but returns the row.
    """
    e = _normalize(email)
    if "@" not in e:
        raise ValueError("That doesn't look like a valid email.")
    now = datetime.now(timezone.utc)
    _coll().update_one(
        {"email": e},
        {
            "$set": {
                "active": True,
                "note": note.strip()[:200],
                "updatedAt": now,
            },
            "$setOnInsert": {
                "email": e,
                "addedBy": added_by,
                "createdAt": now,
            },
        },
        upsert=True,
    )
    row = _coll().find_one({"email": e}) or {}
    return {
        "email": row.get("email"),
        "active": bool(row.get("active", True)),
        "note": row.get("note") or "",
        "addedBy": row.get("addedBy") or "",
        "createdAt": _iso(row.get("createdAt")),
        "updatedAt": _iso(row.get("updatedAt")),
    }


def remove_invite(email: str) -> bool:
    """
    Deactivate a whitelist entry. We don't hard-delete so the audit log
    survives — flipping `active` is enough to revoke access on the next
    request.
    """
    e = _normalize(email)
    if not e:
        return False
    res = _coll().update_one(
        {"email": e},
        {
            "$set": {
                "active": False,
                "updatedAt": datetime.now(timezone.utc),
            }
        },
    )
    return res.modified_count > 0


def _iso(d) -> Optional[str]:
    if isinstance(d, datetime):
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d.isoformat()
    return None
