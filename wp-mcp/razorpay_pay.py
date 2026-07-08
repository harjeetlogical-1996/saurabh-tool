"""
Payments via Razorpay (India / INR) using hosted Payment Links.

We use Razorpay Payment Links (a Razorpay-hosted checkout page) so we don't need
a frontend widget: create a link -> redirect the user -> Razorpay collects the
payment -> a webhook (payment_link.paid) tells us to grant the plan.

Set RAZORPAY_KEY_ID + RAZORPAY_KEY_SECRET (and RAZORPAY_WEBHOOK_SECRET for
webhook verification) in the environment. INR prices are defined here.
"""
import os
import json
import hmac
import hashlib
import base64
import urllib.request
import urllib.error

RZP_KEY_ID = os.environ.get("RAZORPAY_KEY_ID", "")
RZP_KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET", "")
RZP_WEBHOOK_SECRET = os.environ.get("RAZORPAY_WEBHOOK_SECRET", "")

_API = "https://api.razorpay.com/v1"


def enabled():
    return bool(RZP_KEY_ID and RZP_KEY_SECRET)


# --- INR plan prices (paise = INR * 100). Match the landing-page INR prices. ---
PLAN_PRICES_INR = {
    "owai_mini": ("Mini", 700),
    "owai_starter": ("Starter", 1699),
    "owai_pro": ("Pro", 8299),
}

# --- USD plan prices (cents = USD * 100). Razorpay charges international cards in
# USD too (needs "International payments" enabled on the Razorpay account). ---
PLAN_PRICES_USD = {
    "owai_starter": ("Starter", 20),
    "owai_pro": ("Pro", 99),
}

# One-time INR top-up packs (image credits). 500 is the largest single pack -
# for bulk, buy it multiple times (keeps a healthy per-image margin).
CREDIT_PACKS_INR = {
    "img_100": ("100 AI images", 699, 100),
    "img_300": ("300 AI images", 1699, 300),
    "img_500": ("500 AI images", 2699, 500),
}

# One-time USD top-up packs.
CREDIT_PACKS_USD = {
    "img_100": ("100 AI images", 8, 100),
    "img_300": ("300 AI images", 20, 300),
    "img_500": ("500 AI images", 30, 500),
}


def _auth_header():
    tok = base64.b64encode(f"{RZP_KEY_ID}:{RZP_KEY_SECRET}".encode()).decode()
    return {"Authorization": "Basic " + tok, "Content-Type": "application/json"}


def _post(path, payload):
    req = urllib.request.Request(_API + path, data=json.dumps(payload).encode(),
                                 headers=_auth_header(), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Razorpay API {e.code}: {e.read().decode()[:400]}")


def plan_supported(plan_key, currency="INR"):
    table = PLAN_PRICES_INR if currency == "INR" else PLAN_PRICES_USD
    return plan_key in table


def plan_price(plan_key, currency="INR"):
    """Return (label, amount) for a plan, or (None, 0)."""
    table = PLAN_PRICES_INR if currency == "INR" else PLAN_PRICES_USD
    return table.get(plan_key, (None, 0))


def create_plan_link(user_id, email, plan_key, base_url, currency="INR",
                     amount=None, coupon="", base=None, tax=0, gstin=""):
    """Create a Razorpay Payment Link for a plan (INR for India, USD for international).
    `amount` is the FINAL charged total (after coupon + GST). base/tax are recorded
    in notes for GST reporting. Returns the short_url."""
    currency = "USD" if currency == "USD" else "INR"
    table = PLAN_PRICES_INR if currency == "INR" else PLAN_PRICES_USD
    if plan_key not in table:
        raise ValueError(f"plan {plan_key} not available in {currency}")
    label, list_amt = table[plan_key]
    amt = list_amt if amount is None else amount
    if amt <= 0:
        amt = 1  # Razorpay needs a positive charge; guard against 100%-off edge
    desc = f"wptaskify - {label} plan (1 month)"
    if tax:
        desc += " (incl. GST)"
    if coupon:
        desc += f" [{coupon}]"
    notes = {"user_id": user_id, "kind": "plan", "item": plan_key, "currency": currency,
             "base": str(base if base is not None else amt), "tax": str(tax)}
    if coupon:
        notes["coupon"] = coupon
    if gstin:
        notes["gstin"] = gstin
    payload = {
        "amount": int(round(amt * 100)),   # smallest unit (paise / cents)
        "currency": currency,
        "accept_partial": False,
        "description": desc,
        "customer": {"email": email or ""},
        "notify": {"email": bool(email), "sms": False},
        "reminder_enable": False,
        "notes": notes,
        "callback_url": f"{base_url}/billing?success=1",
        "callback_method": "get",
    }
    res = _post("/payment_links", payload)
    return res.get("short_url")


def pack_supported(pack_id, currency="INR"):
    table = CREDIT_PACKS_INR if currency == "INR" else CREDIT_PACKS_USD
    return pack_id in table


def create_topup_link(user_id, email, pack_id, base_url, currency="INR"):
    """Create a Payment Link for a one-time image-credit pack (INR or USD)."""
    currency = "USD" if currency == "USD" else "INR"
    table = CREDIT_PACKS_INR if currency == "INR" else CREDIT_PACKS_USD
    if pack_id not in table:
        raise ValueError("unknown pack")
    label, amt, count = table[pack_id]
    payload = {
        "amount": amt * 100,
        "currency": currency,
        "accept_partial": False,
        "description": f"wptaskify - {label}",
        "customer": {"email": email or ""},
        "notify": {"email": bool(email), "sms": False},
        "notes": {"user_id": user_id, "kind": "credit_pack", "item": pack_id,
                  "amount": str(count), "currency": currency},
        "callback_url": f"{base_url}/billing?success=1",
        "callback_method": "get",
    }
    res = _post("/payment_links", payload)
    return res.get("short_url")


def verify_webhook(payload: bytes, sig_header: str):
    """Verify a Razorpay webhook signature (HMAC-SHA256 with the webhook secret).
    Returns the parsed event dict if valid, else None.

    FAIL-CLOSED: if no webhook secret is configured we REJECT the webhook (return
    None) rather than trusting an unsigned body - otherwise anyone could POST a
    forged 'payment succeeded' event and grant themselves paid plans / credits.
    An unverified parse is only allowed when ALLOW_UNSIGNED_WEBHOOKS=1 is explicitly
    set (local dev only)."""
    if not RZP_WEBHOOK_SECRET:
        if os.environ.get("ALLOW_UNSIGNED_WEBHOOKS") == "1":
            try:
                return json.loads(payload)
            except Exception:
                return None
        # Production / misconfig: no secret -> do not trust the payload.
        return None
    expected = hmac.new(RZP_WEBHOOK_SECRET.encode(), payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig_header or ""):
        return None
    try:
        return json.loads(payload)
    except Exception:
        return None


def extract_notes(event):
    """Pull our `notes` (user_id, kind, item, amount) out of a payment_link.paid or
    payment.captured event, whichever shape Razorpay sent."""
    entity = (event.get("payload", {}) or {})
    # payment_link.paid -> payload.payment_link.entity.notes
    pl = (entity.get("payment_link", {}) or {}).get("entity", {})
    if pl.get("notes"):
        return pl["notes"]
    # payment.captured -> payload.payment.entity.notes
    pay = (entity.get("payment", {}) or {}).get("entity", {})
    if pay.get("notes"):
        return pay["notes"]
    return {}


def extract_amount(event):
    """Return the ACTUALLY captured amount as (major_units, currency) e.g. (99.0, 'USD'),
    or (None, '') if not present. Razorpay amounts are in the smallest unit (paise/cents)."""
    entity = (event.get("payload", {}) or {})
    pay = (entity.get("payment", {}) or {}).get("entity", {})
    if pay.get("amount") is not None:
        cur = (pay.get("currency") or "").upper()
        try:
            return (int(pay["amount"]) / 100.0, cur)
        except (TypeError, ValueError):
            pass
    pl = (entity.get("payment_link", {}) or {}).get("entity", {})
    # payment_link.paid carries amount_paid (smallest unit)
    amt = pl.get("amount_paid", pl.get("amount"))
    if amt is not None:
        cur = (pl.get("currency") or "").upper()
        try:
            return (int(amt) / 100.0, cur)
        except (TypeError, ValueError):
            pass
    return (None, "")


def extract_payment_id(event):
    """A stable id identifying the underlying PAYMENT, so all events for one purchase
    (payment_link.paid, payment.captured, order.paid) dedupe to the same key. Prefer the
    Razorpay payment id; fall back to the payment-link id, then the order id."""
    entity = (event.get("payload", {}) or {})
    pay = (entity.get("payment", {}) or {}).get("entity", {})
    if pay.get("id"):
        return str(pay["id"])
    pl = (entity.get("payment_link", {}) or {}).get("entity", {})
    # payment_link.paid carries the id of the payment that settled it
    if pl.get("payment_id"):
        return str(pl["payment_id"])
    if pl.get("id"):
        return str(pl["id"])
    order = (entity.get("order", {}) or {}).get("entity", {})
    if order.get("id"):
        return str(order["id"])
    return ""
