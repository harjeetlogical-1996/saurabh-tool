"""
Plan / pricing source of truth.

Every subscription tier and its limits lives here. The backend reads
from this dict to gate uploads and the frontend pulls a public-safe
copy via /plans so the pricing page stays in sync without duplication.

Pricing model (May 2026):
  - Platform-paid Gemini (we own all API keys). User pays subscription, we pay Google.
  - Minute-based metering (audio duration, not video count).
  - Hard caps with friendly top-up purchase flow.
  - GST 18% charged extra on top of listed prices (B2B-style).
  - Razorpay = 3% effective fee (incl GST on fee).

All amounts in INR (paise on the wire for Razorpay, rupees for display).
"""

from __future__ import annotations

from typing import TypedDict


class PlanDef(TypedDict):
    id: str
    name: str
    priceInr: int        # listed price, GST extra
    minutesPerMonth: int  # video minutes user can render
    maxConcurrentJobs: int
    priorityQueue: bool
    expressRenderMinutes: int  # minutes/mo eligible for instant-render mode
    commercialUse: bool
    apiAccess: bool
    description: str
    # Which tool this plan belongs to:
    #   "audio-to-video"  — Audio→Video tool plans
    #   "captions"        — Caption-your-video tool plans
    tool: str
    # Mode flag:
    #   "hosted" — we provide Gemini billing (default pricing)
    #   "byo"    — user supplies their own Gemini key (compute-only price)
    mode: str


PLANS: dict[str, PlanDef] = {
    # ===== AUDIO-TO-VIDEO TOOL — Hosted tier (we pay Gemini) =====
    "free": {
        "id": "free",
        "name": "Free",
        "priceInr": 0,
        "minutesPerMonth": 1,
        "maxConcurrentJobs": 1,
        "priorityQueue": False,
        "expressRenderMinutes": 0,
        "commercialUse": False,
        "apiAccess": False,
        "tool": "audio-to-video",
        "mode": "hosted",
        "description": "Try the tool with 1 minute of video per month.",
    },
    "starter": {
        "id": "starter",
        "name": "Starter",
        "priceInr": 299,
        "minutesPerMonth": 5,
        "maxConcurrentJobs": 1,
        "priorityQueue": False,
        "expressRenderMinutes": 0,
        "commercialUse": True,
        "apiAccess": False,
        "tool": "audio-to-video",
        "mode": "hosted",
        "description": "Perfect for individual creators starting out.",
    },
    "creator": {
        "id": "creator",
        "name": "Creator",
        "priceInr": 799,
        "minutesPerMonth": 15,
        "maxConcurrentJobs": 2,
        "priorityQueue": False,
        "expressRenderMinutes": 5,
        "commercialUse": True,
        "apiAccess": False,
        "tool": "audio-to-video",
        "mode": "hosted",
        "description": "Most popular — for regular content creators.",
    },
    "pro": {
        "id": "pro",
        "name": "Pro",
        "priceInr": 1999,
        "minutesPerMonth": 45,
        "maxConcurrentJobs": 3,
        "priorityQueue": True,
        "expressRenderMinutes": 20,
        "commercialUse": True,
        "apiAccess": False,
        "tool": "audio-to-video",
        "mode": "hosted",
        "description": "For agencies and power users.",
    },
    "studio": {
        "id": "studio",
        "name": "Studio",
        "priceInr": 4999,
        "minutesPerMonth": 120,
        "maxConcurrentJobs": 5,
        "priorityQueue": True,
        "expressRenderMinutes": 9999,  # effectively unlimited
        "commercialUse": True,
        "apiAccess": True,
        "tool": "audio-to-video",
        "mode": "hosted",
        "description": "Studios, podcasters, brands — full power.",
    },

    # ===== AUDIO-TO-VIDEO TOOL — BYO-key tier =====
    "byo_free": {
        "id": "byo_free",
        "name": "BYO Free",
        "priceInr": 0,
        "minutesPerMonth": 3,
        "maxConcurrentJobs": 1,
        "priorityQueue": False,
        "expressRenderMinutes": 0,
        "commercialUse": False,
        "apiAccess": False,
        "tool": "audio-to-video",
        "mode": "byo",
        "description": "Use your own Gemini key, 3 min of compute free.",
    },
    "byo_lite": {
        "id": "byo_lite",
        "name": "BYO Lite",
        "priceInr": 149,
        "minutesPerMonth": 30,
        "maxConcurrentJobs": 2,
        "priorityQueue": False,
        "expressRenderMinutes": 0,
        "commercialUse": True,
        "apiAccess": False,
        "tool": "audio-to-video",
        "mode": "byo",
        "description": "Bring your Gemini key. 30 min of compute / month.",
    },
    "byo_standard": {
        "id": "byo_standard",
        "name": "BYO Standard",
        "priceInr": 399,
        "minutesPerMonth": 150,
        "maxConcurrentJobs": 3,
        "priorityQueue": False,
        "expressRenderMinutes": 30,
        "commercialUse": True,
        "apiAccess": False,
        "tool": "audio-to-video",
        "mode": "byo",
        "description": "Power users with their own Gemini billing. 150 min.",
    },
    "byo_unlimited": {
        "id": "byo_unlimited",
        "name": "BYO Unlimited",
        "priceInr": 899,
        "minutesPerMonth": 500,
        "maxConcurrentJobs": 5,
        "priorityQueue": True,
        "expressRenderMinutes": 9999,
        "commercialUse": True,
        "apiAccess": True,
        "tool": "audio-to-video",
        "mode": "byo",
        "description": "Studios with own Gemini key. Fair-use 500 min.",
    },

    # ===== CAPTION-YOUR-VIDEO TOOL — standalone plans =====
    # Captions inside the audio-to-video tool (i.e. on a video the user
    # already rendered with us) are ALWAYS FREE — they live on the parent
    # job. These plans apply only when the user uploads an outside video
    # to the standalone caption tool.
    "caption_free": {
        "id": "caption_free",
        "name": "Caption Free",
        "priceInr": 0,
        "minutesPerMonth": 5,
        "maxConcurrentJobs": 1,
        "priorityQueue": False,
        "expressRenderMinutes": 0,
        "commercialUse": False,
        "apiAccess": False,
        "tool": "captions",
        "mode": "hosted",
        "description": "Try the caption tool with 5 minutes of video / month.",
    },
    "caption_pro": {
        "id": "caption_pro",
        "name": "Caption Pro",
        "priceInr": 199,
        "minutesPerMonth": 100,
        "maxConcurrentJobs": 2,
        "priorityQueue": False,
        "expressRenderMinutes": 0,
        "commercialUse": True,
        "apiAccess": False,
        "tool": "captions",
        "mode": "hosted",
        "description": "100 minutes of caption-ready video per month.",
    },
}


# Plans that fully bypass quota (admin/internal use).
UNLIMITED_PLANS = {"owner"}

# Top-up packs (one-time minute purchases).
TOPUPS: dict[str, dict] = {
    "topup_5":  {"id": "topup_5",  "minutes": 5,  "priceInr": 149,  "label": "+5 min top-up"},
    "topup_15": {"id": "topup_15", "minutes": 15, "priceInr": 399,  "label": "+15 min top-up"},
    "topup_30": {"id": "topup_30", "minutes": 30, "priceInr": 699,  "label": "+30 min top-up"},
}


def get_plan(plan_id: str) -> PlanDef:
    """Lookup a plan, defaulting to free if unknown."""
    return PLANS.get(plan_id) or PLANS["free"]


def is_unlimited_plan(plan_id: str) -> bool:
    return plan_id in UNLIMITED_PLANS


def public_plans() -> list[dict]:
    """The list the /plans endpoint serves to the frontend."""
    out = []
    for p in PLANS.values():
        out.append({
            "id": p["id"],
            "name": p["name"],
            "priceInr": p["priceInr"],
            "minutesPerMonth": p["minutesPerMonth"],
            "maxConcurrentJobs": p["maxConcurrentJobs"],
            "priorityQueue": p["priorityQueue"],
            "expressRenderMinutes": p["expressRenderMinutes"],
            "commercialUse": p["commercialUse"],
            "apiAccess": p["apiAccess"],
            "tool": p["tool"],
            "mode": p["mode"],
            "description": p["description"],
        })
    return out


def is_byo_plan(plan_id: str) -> bool:
    """True when this plan requires the user to supply their own Gemini key."""
    return get_plan(plan_id)["mode"] == "byo"


def plan_tool(plan_id: str) -> str:
    """Which tool a plan belongs to ('audio-to-video' | 'captions')."""
    return get_plan(plan_id)["tool"]


def default_plan_for(tool: str) -> str:
    """Default free plan id for a given tool."""
    return "caption_free" if tool == "captions" else "free"


def public_topups() -> list[dict]:
    return list(TOPUPS.values())
