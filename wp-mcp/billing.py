"""
Payments via Stripe: plan subscriptions (recurring) + one-time plan purchases,
and one-time credit / token top-up packs.

Set STRIPE_SECRET_KEY (and STRIPE_WEBHOOK_SECRET for webhooks) in the environment.
Prices are defined here in USD; we create Stripe Checkout Sessions on the fly
using price_data (no need to pre-create products in the Stripe dashboard).
"""
import os

try:
    import stripe
except Exception:  # noqa: BLE001
    stripe = None

STRIPE_SECRET = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

if stripe and STRIPE_SECRET:
    stripe.api_key = STRIPE_SECRET


def enabled():
    return bool(stripe and STRIPE_SECRET)


# --- Plan catalog: key -> (label, monthly USD) ---------------------------------
PLAN_PRICES = {
    # Bring-your-own-AI
    "owai_mini": ("Mini", 9),
    "owai_starter": ("Starter", 20),
    "owai_pro": ("Pro", 99),
    # Built-in chat
    "chat_starter": ("Chat Starter", 30),
    "chat_pro": ("Chat Pro", 79),
    "chat_max": ("Chat Max", 149),
}

# --- Credit top-up packs: id -> (label, USD, image_credits) ---------------------
CREDIT_PACKS = {
    "img_100": ("100 AI images", 8, 100),
    "img_300": ("300 AI images", 20, 300),
    "img_1000": ("1,000 AI images", 55, 1000),
}

# --- Token top-up packs: id -> (label, USD, tokens) -----------------------------
TOKEN_PACKS = {
    "tok_1m": ("1,000 AI credits (1M tokens)", 6, 1_000_000),
    "tok_5m": ("5,000 AI credits (5M tokens)", 25, 5_000_000),
    "tok_15m": ("15,000 AI credits (15M tokens)", 65, 15_000_000),
}


def _line_item(name, usd_cents, recurring):
    price_data = {"currency": "usd", "product_data": {"name": name}, "unit_amount": usd_cents}
    if recurring:
        price_data["recurring"] = {"interval": "month"}
    return {"price_data": price_data, "quantity": 1}


def create_plan_checkout(user_id, email, plan_key, recurring, base_url, customer_id=None):
    """Create a Checkout Session for a plan (subscription or one-time)."""
    if plan_key not in PLAN_PRICES:
        raise ValueError("unknown plan")
    label, usd = PLAN_PRICES[plan_key]
    mode = "subscription" if recurring else "payment"
    kwargs = dict(
        mode=mode,
        line_items=[_line_item(f"wptaskify - {label}", usd * 100, recurring)],
        success_url=f"{base_url}/billing?success=1",
        cancel_url=f"{base_url}/billing?canceled=1",
        client_reference_id=user_id,
        metadata={"user_id": user_id, "kind": "plan", "item": plan_key,
                  "recurring": "1" if recurring else "0"},
    )
    if customer_id:
        kwargs["customer"] = customer_id
    else:
        kwargs["customer_email"] = email
    sess = stripe.checkout.Session.create(**kwargs)
    return sess.url


def create_topup_checkout(user_id, email, pack_id, base_url, customer_id=None):
    """One-time checkout for a credit or token pack."""
    if pack_id in CREDIT_PACKS:
        label, usd, amount = CREDIT_PACKS[pack_id]
        kind = "credit_pack"
    elif pack_id in TOKEN_PACKS:
        label, usd, amount = TOKEN_PACKS[pack_id]
        kind = "token_pack"
    else:
        raise ValueError("unknown pack")
    kwargs = dict(
        mode="payment",
        line_items=[_line_item(f"wptaskify - {label}", usd * 100, False)],
        success_url=f"{base_url}/billing?success=1",
        cancel_url=f"{base_url}/billing?canceled=1",
        client_reference_id=user_id,
        metadata={"user_id": user_id, "kind": kind, "item": pack_id, "amount": str(amount)},
    )
    if customer_id:
        kwargs["customer"] = customer_id
    else:
        kwargs["customer_email"] = email
    sess = stripe.checkout.Session.create(**kwargs)
    return sess.url


def verify_webhook(payload: bytes, sig_header: str):
    """Return the Stripe event if the signature is valid, else None.
    FAIL-CLOSED: no secret -> reject (return None) unless ALLOW_UNSIGNED_WEBHOOKS=1
    is explicitly set for local dev. Never trust an unsigned event that grants plans."""
    if not STRIPE_WEBHOOK_SECRET:
        if os.environ.get("ALLOW_UNSIGNED_WEBHOOKS") == "1":
            import json
            try:
                return json.loads(payload)
            except Exception:
                return None
        return None
    try:
        return stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except Exception:
        return None
