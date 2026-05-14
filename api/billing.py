"""
Subscription + minute-metering layer.

Each user has ONE subscription PER TOOL — currently:
  - audio-to-video tool subscription (free | starter | creator | pro | studio | byo_*)
  - captions tool subscription (caption_free | caption_pro)

Mongo collection `tool_subscriptions` (one doc per (userId, tool)):
  {
    userId: str,
    tool: "audio-to-video" | "captions",
    plan: "<plan id>",
    minutesUsedThisCycle: int,      // seconds used in current billing cycle
    minutesLimitThisCycle: int,     // plan minutes converted to seconds
    topUpMinutesRemaining: int,     // seconds bought via one-time top-ups
    cycleStartAt: datetime,         // start of current billing cycle (UTC)
    cycleEndAt: datetime,           // when cycleStartAt rolls over
    razorpaySubscriptionId: str|None,
    status: "active"|"cancelled"|"past_due",
    updatedAt: datetime,
  }

All durations stored in SECONDS internally; minutes-on-the-wire is
seconds/60.

Legacy: pre-multi-tool docs had no `tool` field. We treat those as
the audio-to-video subscription so existing data keeps working.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from plans import PLANS, UNLIMITED_PLANS, get_plan, default_plan_for, plan_tool


# How much of the underlying media duration each tool "costs" in minutes.
# Audio-to-video pays full duration (1.0). Captioning ops are way cheaper
# on our side (no Gemini image gen — only ffmpeg + cheap transcription),
# so we charge a fraction.
TOOL_COST_MULTIPLIERS: dict[str, float] = {
    "audio-to-video":        1.0,
    "captions":              0.0,   # follow-up on a paid audio-to-video — FREE
    "bulk-captions":         0.5,   # standalone transcribe
    "bulk-captions-render":  0.25,  # caption burn-in only
}


def cost_multiplier(tool: str) -> float:
    """Multiplier applied to media duration to get billable seconds."""
    return TOOL_COST_MULTIPLIERS.get(tool, 1.0)


# Which subscription bucket a job tool draws from.
#   audio-to-video, captions (follow-up)  → audio-to-video subscription
#   bulk-captions, bulk-captions-render   → captions subscription
JOB_TOOL_TO_SUB_TOOL: dict[str, str] = {
    "audio-to-video":        "audio-to-video",
    "captions":              "audio-to-video",
    "bulk-captions":         "captions",
    "bulk-captions-render":  "captions",
}


def sub_tool_for_job(job_tool: str) -> str:
    """Which subscription tool a render job should consume from."""
    return JOB_TOOL_TO_SUB_TOOL.get(job_tool, "audio-to-video")


def _coll():
    from app import db
    return db().tool_subscriptions


# ---- Cycle helpers --------------------------------------------------------

def _start_of_month(now: datetime) -> datetime:
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _next_month(d: datetime) -> datetime:
    if d.month == 12:
        return d.replace(year=d.year + 1, month=1)
    return d.replace(month=d.month + 1)


def _new_cycle_bounds(now: datetime) -> tuple[datetime, datetime]:
    start = _start_of_month(now)
    return start, _next_month(start)


# ---- Core API -------------------------------------------------------------

def _query(user_id: str, tool: str) -> dict:
    """
    The query used to look up a subscription. For audio-to-video, we
    also match legacy docs that have no `tool` field (early users).
    """
    if tool == "audio-to-video":
        return {
            "userId": user_id,
            "$or": [{"tool": "audio-to-video"}, {"tool": {"$exists": False}}],
        }
    return {"userId": user_id, "tool": tool}


def get_or_create_subscription(
    user_id: str,
    plan: str = "free",
    tool: str = "audio-to-video",
) -> dict:
    """
    Read the user's subscription for `tool`. Creates a default-free row
    on first call. Auto-rolls the cycle if the month boundary has passed.

    `plan` is the FALLBACK plan if no row exists yet — typically the
    plan stored on the user document. Pass the user's a2v plan when
    looking up a2v subscriptions; captions defaults to caption_free.
    """
    now = datetime.now(timezone.utc)
    doc = _coll().find_one(_query(user_id, tool))

    if not doc:
        plan_id = plan if plan_tool(plan) == tool else default_plan_for(tool)
        start, end = _new_cycle_bounds(now)
        limit_seconds = get_plan(plan_id)["minutesPerMonth"] * 60
        doc = {
            "userId": user_id,
            "tool": tool,
            "plan": plan_id,
            "minutesUsedThisCycle": 0,
            "minutesLimitThisCycle": limit_seconds,
            "topUpMinutesRemaining": 0,
            "cycleStartAt": start,
            "cycleEndAt": end,
            "razorpaySubscriptionId": None,
            "status": "active",
            "updatedAt": now,
        }
        _coll().insert_one(doc)
        return doc

    # Backfill `tool` on legacy docs so future queries hit the indexed path.
    if doc.get("tool") is None:
        _coll().update_one({"_id": doc["_id"]}, {"$set": {"tool": tool}})
        doc["tool"] = tool

    # Auto-roll cycle if we've crossed cycleEndAt.
    cycle_end = doc.get("cycleEndAt")
    if isinstance(cycle_end, datetime) and cycle_end.tzinfo is None:
        cycle_end = cycle_end.replace(tzinfo=timezone.utc)
    if not cycle_end or cycle_end <= now:
        start, end = _new_cycle_bounds(now)
        plan_id = doc.get("plan") or default_plan_for(tool)
        limit_seconds = get_plan(plan_id)["minutesPerMonth"] * 60
        _coll().update_one(
            {"_id": doc["_id"]},
            {"$set": {
                "minutesUsedThisCycle": 0,
                "minutesLimitThisCycle": limit_seconds,
                "cycleStartAt": start,
                "cycleEndAt": end,
                "updatedAt": now,
            }},
        )
        doc["minutesUsedThisCycle"] = 0
        doc["minutesLimitThisCycle"] = limit_seconds
        doc["cycleStartAt"] = start
        doc["cycleEndAt"] = end

    return doc


def remaining_seconds(sub: dict) -> int:
    """Seconds the user can still render. Includes top-up pool."""
    if sub.get("plan") in UNLIMITED_PLANS:
        return 10 ** 9
    used = int(sub.get("minutesUsedThisCycle", 0))
    limit = int(sub.get("minutesLimitThisCycle", 0))
    topup = int(sub.get("topUpMinutesRemaining", 0))
    return max(0, limit - used) + max(0, topup)


def can_render(sub: dict, want_seconds: float) -> bool:
    return remaining_seconds(sub) >= int(want_seconds)


def consume_seconds(
    user_id: str,
    seconds: float,
    tool: str = "audio-to-video",
) -> dict:
    """
    Burn `seconds` from the cycle bucket first, top-up bucket as fallback.
    Caller must guard against double-consume per job (use the
    `creditConsumed` flag on the job doc).
    """
    sub = get_or_create_subscription(user_id, tool=tool)
    if sub.get("plan") in UNLIMITED_PLANS:
        return sub

    sec = max(0, int(round(seconds)))
    used = int(sub.get("minutesUsedThisCycle", 0))
    limit = int(sub.get("minutesLimitThisCycle", 0))
    topup = int(sub.get("topUpMinutesRemaining", 0))

    headroom_cycle = max(0, limit - used)
    take_cycle = min(sec, headroom_cycle)
    take_topup = sec - take_cycle

    new_used = used + take_cycle
    new_topup = max(0, topup - max(0, take_topup))

    _coll().update_one(
        {"_id": sub["_id"]},
        {"$set": {
            "minutesUsedThisCycle": new_used,
            "topUpMinutesRemaining": new_topup,
            "updatedAt": datetime.now(timezone.utc),
        }},
    )
    sub["minutesUsedThisCycle"] = new_used
    sub["topUpMinutesRemaining"] = new_topup
    return sub


def refund_seconds(
    user_id: str,
    seconds: float,
    tool: str = "audio-to-video",
) -> None:
    """Reverse a consume_seconds call after a failed render."""
    sec = max(0, int(round(seconds)))
    if sec == 0:
        return
    sub = _coll().find_one(_query(user_id, tool))
    if not sub or sub.get("plan") in UNLIMITED_PLANS:
        return
    used = int(sub.get("minutesUsedThisCycle", 0))
    new_used = max(0, used - sec)
    _coll().update_one(
        {"_id": sub["_id"]},
        {"$set": {
            "minutesUsedThisCycle": new_used,
            "updatedAt": datetime.now(timezone.utc),
        }},
    )


def set_plan(
    user_id: str,
    plan_id: str,
    razorpay_sub_id: Optional[str] = None,
) -> dict:
    """
    Flip the user's plan. Tool is inferred from `plan_id`. Resets the
    cycle to start-of-month so they get the new minute allowance now.
    Unused minutes from the OLD plan migrate into the top-up bucket so
    the user doesn't lose them on a mid-cycle switch.
    """
    now = datetime.now(timezone.utc)
    start, end = _new_cycle_bounds(now)
    new_plan = get_plan(plan_id)
    tool = new_plan["tool"]
    limit_seconds = new_plan["minutesPerMonth"] * 60

    prev = _coll().find_one(_query(user_id, tool))
    carry_over_seconds = 0
    if prev and prev.get("plan") not in UNLIMITED_PLANS:
        prev_used = int(prev.get("minutesUsedThisCycle", 0))
        prev_limit = int(prev.get("minutesLimitThisCycle", 0))
        carry_over_seconds = max(0, prev_limit - prev_used)

    update = {
        "tool": tool,
        "plan": plan_id,
        "minutesUsedThisCycle": 0,
        "minutesLimitThisCycle": limit_seconds,
        "cycleStartAt": start,
        "cycleEndAt": end,
        "status": "active",
        "updatedAt": now,
    }
    if razorpay_sub_id is not None:
        update["razorpaySubscriptionId"] = razorpay_sub_id

    write: dict[str, Any] = {
        "$set": update,
        "$setOnInsert": {"userId": user_id, "topUpMinutesRemaining": 0},
    }
    if carry_over_seconds > 0:
        write["$inc"] = {"topUpMinutesRemaining": carry_over_seconds}

    if prev:
        _coll().update_one({"_id": prev["_id"]}, write)
    else:
        _coll().update_one(
            {"userId": user_id, "tool": tool},
            write,
            upsert=True,
        )
    return get_or_create_subscription(user_id, plan_id, tool=tool)


def add_topup_minutes(
    user_id: str,
    minutes: int,
    tool: str = "audio-to-video",
) -> dict:
    """One-time top-up pack credited to top-up bucket (rolls over indefinitely)."""
    secs = max(0, int(minutes)) * 60
    if secs == 0:
        return get_or_create_subscription(user_id, tool=tool)
    _coll().update_one(
        _query(user_id, tool),
        {
            "$inc": {"topUpMinutesRemaining": secs},
            "$set": {
                "tool": tool,
                "updatedAt": datetime.now(timezone.utc),
            },
            "$setOnInsert": {
                "userId": user_id,
                "plan": default_plan_for(tool),
                "minutesUsedThisCycle": 0,
                "minutesLimitThisCycle": get_plan(default_plan_for(tool))["minutesPerMonth"] * 60,
                "cycleStartAt": _start_of_month(datetime.now(timezone.utc)),
                "cycleEndAt": _next_month(_start_of_month(datetime.now(timezone.utc))),
                "status": "active",
            },
        },
        upsert=True,
    )
    return get_or_create_subscription(user_id, tool=tool)


def serialize_subscription(sub: dict) -> dict[str, Any]:
    """Public-safe view sent to the frontend."""
    plan_id = sub.get("plan") or "free"
    plan = get_plan(plan_id)
    return {
        "plan": plan_id,
        "planName": plan["name"],
        "tool": plan["tool"],
        "minutesUsed": round(int(sub.get("minutesUsedThisCycle", 0)) / 60, 2),
        "minutesLimit": round(int(sub.get("minutesLimitThisCycle", 0)) / 60, 2),
        "topUpMinutesRemaining": round(int(sub.get("topUpMinutesRemaining", 0)) / 60, 2),
        "cycleStartAt": _iso(sub.get("cycleStartAt")),
        "cycleEndAt": _iso(sub.get("cycleEndAt")),
        "status": sub.get("status") or "active",
        "unlimited": plan_id in UNLIMITED_PLANS,
    }


def _iso(d: Any) -> Optional[str]:
    if isinstance(d, datetime):
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d.isoformat()
    return None


# ---- Admin / cron ---------------------------------------------------------

def force_reset_all_cycles() -> int:
    """Force monthly cycle rollover for every subscription due for reset."""
    now = datetime.now(timezone.utc)
    start, end = _new_cycle_bounds(now)
    n = 0
    for doc in _coll().find({"cycleEndAt": {"$lte": now}}):
        plan_id = doc.get("plan") or default_plan_for(doc.get("tool") or "audio-to-video")
        limit_seconds = get_plan(plan_id)["minutesPerMonth"] * 60
        _coll().update_one(
            {"_id": doc["_id"]},
            {"$set": {
                "minutesUsedThisCycle": 0,
                "minutesLimitThisCycle": limit_seconds,
                "cycleStartAt": start,
                "cycleEndAt": end,
                "updatedAt": now,
            }},
        )
        n += 1
    return n
