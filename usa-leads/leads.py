"""
usa-leads: lead discovery (Google Places New API) + email enrichment (website scrape).
HTTP via stdlib urllib, same style as reels-factory/research.py.
"""
import re
import json
import urllib.request
import urllib.parse
import urllib.error

import store

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) usa-leads/1.0"
PLACES_URL = "https://places.googleapis.com/v1/places:searchText"

# Field mask keeps the Places call on the cheap (Text Search Pro) tier.
FIELD_MASK = ",".join([
    "places.id",
    "places.displayName",
    "places.websiteUri",
    "places.nationalPhoneNumber",
    "places.internationalPhoneNumber",
    "places.businessStatus",
    "places.primaryType",
    "places.formattedAddress",
])

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_BAD_EMAIL_HINTS = ("noreply", "no-reply", "example.com", "sentry", "wixpress",
                    "@2x", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg",
                    "godaddy", "domain")
_PREFERRED = ("info@", "contact@", "hello@", "sales@", "admin@", "support@")


# ---------------------------------------------------------------------------
# HTTP helper (stdlib)
# ---------------------------------------------------------------------------
def _get(url: str, timeout: int = 15) -> str:
    req = urllib.request.Request(
        url, headers={"User-Agent": UA, "Accept-Language": "en-US,en"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="ignore")


# ---------------------------------------------------------------------------
# Google Places New API - Text Search
# ---------------------------------------------------------------------------
def search_places(api_key: str, query: str, limit: int = 20) -> list:
    payload = json.dumps({
        "textQuery": query,
        "pageSize": min(max(limit, 1), 20),  # API max 20 per page
    }).encode()
    req = urllib.request.Request(
        PLACES_URL,
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": FIELD_MASK,
            "User-Agent": UA,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode("utf-8", errors="ignore"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")[:500]
        raise RuntimeError(f"Google Places error {e.code}: {body}")
    return data.get("places", [])


def _pitch_for(has_website: bool, primary_type: str) -> str:
    t = (primary_type or "").lower()
    if not has_website:
        return "website"
    if any(k in t for k in ("software", "it_", "marketing", "agency", "tech")):
        return "ai tools"
    return "digital marketing"


def find_leads(env: dict, city: str, category: str,
               limit: int = 20, only_no_website: bool = False) -> dict:
    """Search, dedup against leads.json, persist new ones. Returns a summary dict."""
    store.require(env, "GOOGLE_PLACES_API_KEY")
    query = f"{category} in {city}".strip()
    places = search_places(env["GOOGLE_PLACES_API_KEY"], query, limit)

    leads = store.load_leads()
    added, skipped_known, no_site = 0, 0, 0
    for p in places:
        pid = p.get("id")
        if not pid:
            continue
        website = p.get("websiteUri", "") or ""
        has_website = bool(website)
        if only_no_website and has_website:
            continue
        if pid in leads:
            skipped_known += 1
            continue
        name = (p.get("displayName") or {}).get("text", "Unknown")
        phone = p.get("nationalPhoneNumber") or p.get("internationalPhoneNumber") or ""
        rec = store.new_lead_record(
            place_id=pid, name=name, city=city, website=website, phone=phone,
            category=category, has_website=has_website,
            service_pitch=_pitch_for(has_website, p.get("primaryType", "")),
        )
        leads[pid] = rec
        added += 1
        if not has_website:
            no_site += 1
    store.save_leads(leads)
    return {
        "query": query, "added": added, "no_website": no_site,
        "already_known": skipped_known, "returned": len(places),
    }


# ---------------------------------------------------------------------------
# Email enrichment - scrape website for a contact email
# ---------------------------------------------------------------------------
def _norm_url(website: str) -> str:
    if not website:
        return ""
    if not website.startswith(("http://", "https://")):
        website = "https://" + website
    return website


def _score_email(e: str) -> int:
    el = e.lower()
    for p in _PREFERRED:
        if el.startswith(p):
            return 0  # best
    return 1


def extract_email_from_site(website: str) -> str:
    base = _norm_url(website)
    if not base:
        return ""
    candidates = []
    # try homepage + a couple of common contact paths
    for path in ("", "/contact", "/contact-us", "/about"):
        url = base.rstrip("/") + path
        try:
            html = _get(url)
        except Exception:
            continue
        for m in EMAIL_RE.findall(html):
            ml = m.lower()
            if any(b in ml for b in _BAD_EMAIL_HINTS):
                continue
            candidates.append(m)
        if candidates:
            break  # found something on this page, good enough
    if not candidates:
        return ""
    # dedup, prefer info@/contact@ etc
    uniq = sorted(set(candidates), key=_score_email)
    return uniq[0]


def enrich_emails(env: dict, limit: int = 10) -> dict:
    leads = store.load_leads()
    enriched, dead, still_missing = 0, 0, 0
    processed = 0
    for lead in leads.values():
        if processed >= limit:
            break
        if lead.get("email") or lead.get("status") not in ("new",):
            continue
        if not lead.get("website"):
            lead["status"] = "no_email"
            dead += 1
            processed += 1
            continue
        processed += 1
        email = extract_email_from_site(lead["website"])
        if email:
            lead["email"] = email
            enriched += 1
        else:
            still_missing += 1
            lead["notes"] = "no email found on site"
    store.save_leads(leads)
    return {"enriched": enriched, "no_website_marked_dead": dead,
            "still_missing": still_missing, "processed": processed}
