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

# Field mask - capture as much useful data as the Places API gives us.
FIELD_MASK = ",".join([
    "places.id",
    "places.displayName",
    "places.websiteUri",
    "places.nationalPhoneNumber",
    "places.internationalPhoneNumber",
    "places.businessStatus",
    "places.primaryType",
    "places.types",
    "places.formattedAddress",
    "places.rating",
    "places.userRatingCount",
    "places.googleMapsUri",
    "places.regularOpeningHours",
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


# ---------------------------------------------------------------------------
# Normalized lead row that every source returns:
#   {"id", "name", "website", "phone", "type"}
# id must be stable + unique per business (we prefix by source).
# ---------------------------------------------------------------------------
def _from_google(env, city, category, limit):
    store.require(env, "GOOGLE_PLACES_API_KEY")
    rows = []
    for p in search_places(env["GOOGLE_PLACES_API_KEY"], f"{category} in {city}", limit):
        if not p.get("id"):
            continue
        hrs = (p.get("regularOpeningHours") or {}).get("weekdayDescriptions") or []
        rows.append({
            "id": "g:" + p["id"],
            "name": (p.get("displayName") or {}).get("text", "Unknown"),
            "website": p.get("websiteUri", "") or "",
            "phone": p.get("nationalPhoneNumber") or p.get("internationalPhoneNumber") or "",
            "type": p.get("primaryType", ""),
            "address": p.get("formattedAddress", "") or "",
            "rating": p.get("rating"),
            "rating_count": p.get("userRatingCount"),
            "maps_url": p.get("googleMapsUri", "") or "",
            "hours": "; ".join(hrs) if hrs else "",
        })
    return rows


# ---- OpenStreetMap via Overpass API (no key, totally free) ----
OVERPASS_URL = "https://overpass-api.de/api/interpreter"

def _geocode_osm(place: str):
    """Get a bounding box for a city/area name via free Nominatim.
    Nominatim's usage policy requires a descriptive User-Agent with contact info."""
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(
        {"q": place, "format": "json", "limit": 1})
    req = urllib.request.Request(url, headers={
        "User-Agent": "usa-leads/1.0 (saurabhbhayana1996@gmail.com)",
        "Referer": "https://github.com/logicaldottech/usa-leads",
        "Accept": "application/json",
        "Accept-Language": "en-US,en",
    })
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.loads(r.read().decode("utf-8", errors="ignore"))
    if not data:
        raise RuntimeError(f"OSM could not find location '{place}'.")
    bb = data[0]["boundingbox"]  # [south, north, west, east]
    return float(bb[0]), float(bb[2]), float(bb[1]), float(bb[3])  # s,w,n,e


def _from_osm(env, city, category, limit):
    s, w, n, e = _geocode_osm(city)
    cat = category.strip().rstrip("s")  # crude singularise, e.g. "plumbers"->"plumber"
    bbox = f"{s},{w},{n},{e}"
    # Query several tag families that hold businesses, plus a name regex match.
    # nwr = nodes + ways + relations (many businesses are mapped as ways).
    q = f"""
    [out:json][timeout:30];
    (
      nwr["name"~"{cat}",i]({bbox});
      nwr["craft"~"{cat}",i]({bbox});
      nwr["shop"~"{cat}",i]({bbox});
      nwr["office"~"{cat}",i]({bbox});
      nwr["amenity"~"{cat}",i]({bbox});
    );
    out tags center {min(limit * 6, 300)};
    """
    req = urllib.request.Request(
        OVERPASS_URL,
        data=urllib.parse.urlencode({"data": q}).encode(),
        headers={
            "User-Agent": "usa-leads/1.0 (saurabhbhayana1996@gmail.com)",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=40) as r:
        data = json.loads(r.read().decode("utf-8", errors="ignore"))
    rows, seen = [], set()
    catl = category.lower().rstrip("s")
    for el in data.get("elements", []):
        t = el.get("tags", {})
        name = t.get("name", "")
        if not name:
            continue
        # keep only ones plausibly matching the category (name or any business tag)
        blob = " ".join([name, t.get("shop", ""), t.get("office", ""),
                         t.get("amenity", ""), t.get("craft", ""),
                         t.get("healthcare", ""), t.get("cuisine", "")]).lower()
        if catl and catl not in blob:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        rows.append({
            "id": "osm:" + str(el.get("id")),
            "name": name,
            "website": t.get("website", "") or t.get("contact:website", "") or "",
            "phone": t.get("phone", "") or t.get("contact:phone", "") or "",
            "type": t.get("shop") or t.get("office") or t.get("amenity") or "",
        })
        if len(rows) >= limit:
            break
    return rows


# ---- Yelp Fusion API (free 5000/day) ----
def _from_yelp(env, city, category, limit):
    key = env.get("YELP_API_KEY", "").strip()
    if not key:
        raise RuntimeError("YELP_API_KEY not set. Add it to .env (free at yelp.com/developers).")
    url = "https://api.yelp.com/v3/businesses/search?" + urllib.parse.urlencode(
        {"term": category, "location": city, "limit": min(limit, 50)})
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}", "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode("utf-8", errors="ignore"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Yelp error {e.code}: {e.read().decode('utf-8','ignore')[:300]}")
    rows = []
    for b in data.get("businesses", []):
        rows.append({
            "id": "yelp:" + b.get("id", ""),
            "name": b.get("name", "Unknown"),
            "website": b.get("url", ""),   # Yelp page; real site found during enrich
            "phone": b.get("display_phone", "") or b.get("phone", ""),
            "type": ", ".join(c.get("title", "") for c in b.get("categories", [])),
        })
    return rows


# ---- Yellow Pages scrape (free, no key) ----
def _from_yellowpages(env, city, category, limit):
    base = "https://www.yellowpages.com/search?" + urllib.parse.urlencode(
        {"search_terms": category, "geo_location_terms": city})
    try:
        html = _get(base, timeout=25)
    except Exception as e:
        raise RuntimeError(f"Yellow Pages fetch failed: {e}")
    rows, seen = [], set()
    # business names sit in <a class="business-name"><span>NAME</span></a>
    names = re.findall(r'class="business-name"[^>]*>\s*(?:<span>)?([^<]+)', html)
    # websites appear as track-visit-website hrefs
    sites = re.findall(r'class="track-visit-website"\s+href="([^"]+)"', html)
    phones = re.findall(r'class="phones[^"]*">([^<]+)', html)
    for i, name in enumerate(names):
        name = name.strip()
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        rows.append({
            "id": "yp:" + re.sub(r"\W+", "-", name.lower())[:50],
            "name": name,
            "website": sites[i].strip() if i < len(sites) else "",
            "phone": phones[i].strip() if i < len(phones) else "",
            "type": category,
        })
        if len(rows) >= limit:
            break
    return rows


_SOURCES = {
    "google": _from_google,
    "osm": _from_osm,
    "yelp": _from_yelp,
    "yellowpages": _from_yellowpages,
}


def find_leads(env: dict, city: str, category: str, limit: int = 20,
               only_no_website: bool = False, source: str = "osm") -> dict:
    """
    Search one or all sources, dedup against leads.json + each other, persist new.
    source: "google" | "osm" | "yelp" | "yellowpages" | "all".
    Default "osm" (no API key needed).
    """
    if source == "all":
        chosen = list(_SOURCES.keys())
    elif source in _SOURCES:
        chosen = [source]
    else:
        return {"error": f"Unknown source '{source}'. Use: "
                + ", ".join(list(_SOURCES) + ['all'])}

    leads = store.load_leads()
    # dedup by name to avoid the same business from two sources
    known_names = {(l.get("name") or "").strip().lower() for l in leads.values()}
    added, skipped_known, no_site, per_source, errors = 0, 0, 0, {}, []

    for src in chosen:
        try:
            rows = _SOURCES[src](env, city, category, limit)
        except Exception as e:
            errors.append(f"{src}: {e}")
            continue
        per_source[src] = 0
        for row in rows:
            website = row.get("website", "") or ""
            has_website = bool(website)
            if only_no_website and has_website:
                continue
            pid = row["id"]
            nm = (row.get("name") or "").strip().lower()
            if pid in leads or nm in known_names:
                skipped_known += 1
                continue
            known_names.add(nm)
            leads[pid] = store.new_lead_record(
                place_id=pid, name=row["name"], city=city, website=website,
                phone=row.get("phone", ""), category=category, has_website=has_website,
                service_pitch=_pitch_for(has_website, row.get("type", "")),
                address=row.get("address", ""), rating=row.get("rating"),
                rating_count=row.get("rating_count"), maps_url=row.get("maps_url", ""),
                hours=row.get("hours", ""), source=src,
            )
            added += 1
            per_source[src] += 1
            if not has_website:
                no_site += 1
    store.save_leads(leads)
    return {
        "query": f"{category} in {city}", "sources": chosen, "per_source": per_source,
        "added": added, "no_website": no_site, "already_known": skipped_known,
        "errors": errors,
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


# Directory/aggregator domains are NOT the business's own site - scraping them
# for an email is pointless, so skip them during enrichment.
_AGGREGATOR_DOMAINS = ("yelp.com", "yellowpages.com", "facebook.com",
                       "instagram.com", "google.com", "maps.google")


def extract_email_from_site(website: str) -> str:
    base = _norm_url(website)
    if not base:
        return ""
    if any(d in base.lower() for d in _AGGREGATOR_DOMAINS):
        return ""  # not the real business site
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
