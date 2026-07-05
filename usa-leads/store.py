"""
usa-leads: config + JSON persistence.
Mirrors reels-factory/helpers.py conventions (manual .env loader, JSON files).
"""
import os
import json
from pathlib import Path
from datetime import date

BASE = Path(__file__).parent
DATA = BASE / "data"
DATA.mkdir(exist_ok=True)

LEADS_FILE = DATA / "leads.json"
SENT_LOG_FILE = DATA / "sent_log.json"

# Keys we recognise from .env / OS environment
_ENV_KEYS = (
    "GOOGLE_PLACES_API_KEY",
    "PAGESPEED_API_KEY",   # optional, free - real Google mobile speed score in audits
    "YELP_API_KEY",
    "COMPANY_NAME",        # your company shown in emails (e.g. digitograffi)
    "EXPERIENCE_YEARS",    # e.g. "15+"
    # --- mail (provider-agnostic; Hostinger/Gmail/Zoho/...) ---
    "MAIL_ADDRESS",
    "MAIL_PASSWORD",
    "SMTP_HOST",
    "SMTP_PORT",
    "IMAP_HOST",
    "IMAP_PORT",
    "BREVO_API_KEY",       # if set, send via Brevo HTTP API (works on Render)
    # --- legacy Gmail keys (still supported as fallback) ---
    "GMAIL_ADDRESS",
    "GMAIL_APP_PASSWORD",
    "SENDER_NAME",
    "SENDER_CITY",
    "SUMMARY_EMAIL",       # where daily summaries go (default: the sending account)
    "BOOKING_LINK",
    "DAILY_SEND_CAP",
    "FULL_AUTO_REPLY",
    # --- hosting / remote access ---
    "MCP_AUTH_TOKEN",      # Bearer token to protect the public HTTP endpoint
    "PUBLIC_URL",          # the public https URL Render gives you (for OAuth, optional)
    "PORT",                # Render sets this automatically
    # --- background scheduler (auto-run) ---
    "AUTO_RUN",            # true => run the daily job in the background
    "AUTO_CITY",           # default city for daily find_leads, e.g. "Austin TX"
    "AUTO_CATEGORY",       # default category, e.g. "plumbers"
    "AUTO_SOURCE",         # which lead source the daily job uses (osm/google/yelp/all)
    "AUTO_FIND_LIMIT",     # how many leads to pull per day
    "AUTO_SEND_LIMIT",     # how many outreach emails to send per day
    "AUTO_HOUR_UTC",       # hour (UTC, 0-23) to run the daily job
)


# ---------------------------------------------------------------------------
# .env loader (no external dependency) - same pattern as reels-factory
# ---------------------------------------------------------------------------
def load_env():
    env = {}
    envfile = BASE / ".env"
    if envfile.exists():
        for line in envfile.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    # OS env wins over file
    for k in _ENV_KEYS:
        if os.environ.get(k):
            env[k] = os.environ[k]
    # sensible defaults
    env.setdefault("SENDER_NAME", "Saurabh Bhayana")
    env.setdefault("SENDER_CITY", "Jaipur, India")
    env.setdefault("SUMMARY_EMAIL", "")
    env.setdefault("COMPANY_NAME", "digitograffi")
    env.setdefault("EXPERIENCE_YEARS", "15+")
    env.setdefault("PAGESPEED_API_KEY", "")
    env.setdefault("BOOKING_LINK", "")
    env.setdefault("DAILY_SEND_CAP", "40")
    env.setdefault("FULL_AUTO_REPLY", "false")
    env.setdefault("MCP_AUTH_TOKEN", "")
    env.setdefault("PUBLIC_URL", "")
    env.setdefault("AUTO_RUN", "false")
    env.setdefault("AUTO_CITY", "")
    env.setdefault("AUTO_CATEGORY", "")
    env.setdefault("AUTO_SOURCE", "osm")
    env.setdefault("AUTO_FIND_LIMIT", "20")
    env.setdefault("AUTO_SEND_LIMIT", "20")
    env.setdefault("AUTO_HOUR_UTC", "14")  # ~9am US Eastern
    return env


def mail_address(env: dict) -> str:
    return env.get("MAIL_ADDRESS") or env.get("GMAIL_ADDRESS") or ""


def require_mail(env: dict):
    """Ensure a mail address + password are configured (MAIL_* or GMAIL_* fallback)."""
    addr = env.get("MAIL_ADDRESS") or env.get("GMAIL_ADDRESS")
    pw = env.get("MAIL_PASSWORD") or env.get("GMAIL_APP_PASSWORD")
    if not addr or not pw:
        raise RuntimeError(
            "Mail not configured. Set MAIL_ADDRESS + MAIL_PASSWORD (and SMTP_HOST/"
            "IMAP_HOST) in .env. See .env.example."
        )


def require(env: dict, *keys):
    """Raise a clear error if any required key is missing/empty."""
    missing = [k for k in keys if not env.get(k)]
    if missing:
        raise RuntimeError(
            "Missing config: " + ", ".join(missing)
            + ". Add them to usa-leads/.env (see .env.example)."
        )


# ---------------------------------------------------------------------------
# leads.json  (place_id -> lead record)
# ---------------------------------------------------------------------------
def load_leads() -> dict:
    if not LEADS_FILE.exists():
        return {}
    try:
        return json.loads(LEADS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_leads(leads: dict):
    LEADS_FILE.write_text(
        json.dumps(leads, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def get_lead(place_id: str):
    return load_leads().get(place_id)


def upsert_lead(lead: dict):
    leads = load_leads()
    leads[lead["place_id"]] = lead
    save_leads(leads)
    return lead


def find_lead_by_email(email: str):
    email = (email or "").strip().lower()
    if not email:
        return None
    for lead in load_leads().values():
        if (lead.get("email") or "").strip().lower() == email:
            return lead
    return None


def new_lead_record(place_id, name, city, website="", phone="",
                    category="", has_website=False, service_pitch="website",
                    address="", rating=None, rating_count=None, maps_url="",
                    hours="", source=""):
    return {
        "place_id": place_id,
        "name": name,
        "city": city,
        "website": website,
        "email": "",
        "phone": phone,
        "category": category,
        "has_website": has_website,
        # extra data captured at discovery (Claude uses this for personalization)
        "address": address,
        "rating": rating,
        "rating_count": rating_count,
        "maps_url": maps_url,
        "hours": hours,
        "source": source,
        "status": "new",          # new->emailed->replied->drafted->answered->booked
        "service_pitch": service_pitch,
        "last_outreach": None,
        "message_id": None,        # our outgoing Message-ID for reply threading
        "reply_snippet": "",
        "draft_reply": "",
        "notes": "",
    }


# ---------------------------------------------------------------------------
# sent_log.json  (YYYY-MM-DD -> count)  enforces the daily safety cap
# ---------------------------------------------------------------------------
def _load_sent_log() -> dict:
    if not SENT_LOG_FILE.exists():
        return {}
    try:
        return json.loads(SENT_LOG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def sent_today() -> int:
    return int(_load_sent_log().get(str(date.today()), 0))


def bump_sent(n: int = 1):
    log = _load_sent_log()
    key = str(date.today())
    log[key] = int(log.get(key, 0)) + n
    SENT_LOG_FILE.write_text(
        json.dumps(log, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return log[key]


def remaining_quota(env: dict) -> int:
    cap = int(env.get("DAILY_SEND_CAP", "40") or "40")
    return max(0, cap - sent_today())
