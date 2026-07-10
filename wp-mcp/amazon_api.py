"""
Amazon Creators API client + affiliate helpers. Stdlib only.

Amazon retired the old Product Advertising API (PA-API v5, AWS SigV4) on 2026-05-15 and
replaced it with the **Creators API** (OAuth 2.0 Bearer tokens, lowerCamelCase). This module
targets the Creators API.

Two modes:
  - FULL (Creators API creds): search_items / get_items return real product data (title,
    price, features, images) - needs the user's Credential ID + Credential Secret + associate
    tag (Creators API needs an Associates account with >=10 qualifying sales in 30 days).
  - FALLBACK (tag only): affiliate_search_url builds a tagged Amazon SEARCH link - no API,
    works for everyone.

Auth: OAuth2 client_credentials at a Login-with-Amazon token endpoint -> Bearer token
(cached ~1h) -> POST to https://creatorsapi.amazon/catalog/v1/{searchItems,getItems}.
Docs: https://affiliate-program.amazon.com/creatorsapi/docs/
"""
import json
import time
import base64
import urllib.parse
import urllib.request
import urllib.error

# region -> (LwA token endpoint, marketplace host for x-marketplace + affiliate URLs)
# Token endpoint is regional (v3.1 NA / v3.2 EU / v3.3 FE); the API host is global.
_REGIONS = {
    "com":    ("https://api.amazon.com/auth/o2/token",     "www.amazon.com"),
    "ca":     ("https://api.amazon.com/auth/o2/token",     "www.amazon.ca"),
    "com.mx": ("https://api.amazon.com/auth/o2/token",     "www.amazon.com.mx"),
    "com.br": ("https://api.amazon.com/auth/o2/token",     "www.amazon.com.br"),
    "co.uk":  ("https://api.amazon.co.uk/auth/o2/token",   "www.amazon.co.uk"),
    "in":     ("https://api.amazon.co.uk/auth/o2/token",   "www.amazon.in"),
    "de":     ("https://api.amazon.co.uk/auth/o2/token",   "www.amazon.de"),
    "fr":     ("https://api.amazon.co.uk/auth/o2/token",   "www.amazon.fr"),
    "es":     ("https://api.amazon.co.uk/auth/o2/token",   "www.amazon.es"),
    "it":     ("https://api.amazon.co.uk/auth/o2/token",   "www.amazon.it"),
    "co.jp":  ("https://api.amazon.co.jp/auth/o2/token",   "www.amazon.co.jp"),
    "com.au": ("https://api.amazon.co.jp/auth/o2/token",   "www.amazon.com.au"),
    "sg":     ("https://api.amazon.co.jp/auth/o2/token",   "www.amazon.sg"),
}
DEFAULT_REGION = "com"

_API_BASE = "https://creatorsapi.amazon"
_SEARCH_PATH = "/catalog/v1/searchItems"
_GETITEMS_PATH = "/catalog/v1/getItems"
_SCOPE = "creatorsapi::default"

# The product data we ask Amazon for (lowerCamelCase resources - Creators API).
_RESOURCES = [
    "itemInfo.title",
    "itemInfo.features",
    "images.primary.large",
    "images.variants.large",
    "offersV2.listings.price",
]

# In-process Bearer-token cache: {client_id: (token, expires_at_epoch)}.
_token_cache = {}


def region_ok(region: str) -> bool:
    return (region or "").lower() in _REGIONS


def _marketplace(region: str) -> str:
    return _REGIONS.get((region or "").lower(), _REGIONS[DEFAULT_REGION])[1]


def _token_endpoint(region: str) -> str:
    return _REGIONS.get((region or "").lower(), _REGIONS[DEFAULT_REGION])[0]


def affiliate_search_url(keywords: str, tag: str, region: str = "com") -> str:
    """The NO-API fallback: a tagged Amazon SEARCH link. Works with just an associate tag."""
    www = _marketplace(region)
    q = urllib.parse.urlencode({"k": keywords or "", "tag": tag or "", "linkCode": "ll2"})
    return f"https://{www}/s?{q}"


def affiliate_product_url(asin: str, tag: str, region: str = "com") -> str:
    www = _marketplace(region)
    return f"https://{www}/dp/{asin}?tag={urllib.parse.quote(tag or '')}&linkCode=ll1"


def configured(client_id: str, client_secret: str, tag: str) -> bool:
    return bool(client_id and client_secret and tag)


# ---------------------------------------------------------------------------
# OAuth2 client-credentials -> Bearer token (cached ~1h)
# ---------------------------------------------------------------------------
def _get_token(client_id, client_secret, region, now=None):
    """Fetch (and cache) a Creators API Bearer token. Returns (token, error).
    `now` injectable for tests."""
    t = now if now is not None else time.time()
    cached = _token_cache.get(client_id)
    if cached and cached[1] - 60 > t:   # 60s safety margin
        return cached[0], ""
    endpoint = _token_endpoint(region)
    body = json.dumps({
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": _SCOPE,
    }).encode("utf-8")
    req = urllib.request.Request(
        endpoint, data=body, method="POST",
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        # Fallback: some LwA endpoints prefer form-urlencoded + HTTP Basic auth.
        if e.code in (400, 401):
            tok, err = _get_token_form(client_id, client_secret, endpoint, now=t)
            if tok:
                return tok, ""
            return None, err or _http_err(e, "token")
        return None, _http_err(e, "token")
    except Exception as e:  # noqa: BLE001
        return None, f"Amazon auth error: {str(e)[:200]}"
    tok = data.get("access_token")
    if not tok:
        return None, "Amazon returned no access token."
    expires = t + int(data.get("expires_in", 3600))
    _token_cache[client_id] = (tok, expires)
    return tok, ""


def _get_token_form(client_id, client_secret, endpoint, now=None):
    """OAuth2 form-urlencoded + Basic auth variant (goark-style fallback)."""
    t = now if now is not None else time.time()
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    body = urllib.parse.urlencode({
        "grant_type": "client_credentials", "scope": _SCOPE}).encode()
    req = urllib.request.Request(
        endpoint, data=body, method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded",
                 "Authorization": "Basic " + basic})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return None, _http_err(e, "token")
    except Exception as e:  # noqa: BLE001
        return None, f"Amazon auth error: {str(e)[:200]}"
    tok = data.get("access_token")
    if not tok:
        return None, "Amazon returned no access token."
    _token_cache[client_id] = (tok, t + int(data.get("expires_in", 3600)))
    return tok, ""


def _http_err(e, what):
    raw = ""
    try:
        raw = e.read().decode()[:400]
    except Exception:
        pass
    if e.code in (401, 403):
        return ("Amazon rejected the Creators API credentials (invalid, or your account "
                "isn't approved yet - needs ~10 qualifying sales in 30 days).")
    if e.code == 429:
        return "Amazon Creators API rate limit hit. Try again shortly."
    try:
        j = json.loads(raw)
        msg = j.get("error_description") or j.get("message") or \
            "; ".join(x.get("message", "") for x in j.get("errors", []))
        if msg:
            return f"Amazon Creators API: {msg}"
    except Exception:
        pass
    return f"Amazon Creators API {e.code}: {raw}"


# ---------------------------------------------------------------------------
# Catalog operations
# ---------------------------------------------------------------------------
def _catalog(client_id, client_secret, tag, region, path, payload):
    """Bearer-authed POST to a Creators API catalog operation. Returns (data, error)."""
    token, err = _get_token(client_id, client_secret, region)
    if err:
        return None, err
    marketplace = _marketplace(region)
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        _API_BASE + path, data=body, method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + token,
            "x-marketplace": marketplace,
        })
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode()), ""
    except urllib.error.HTTPError as e:
        # A stale/invalid token -> drop cache and let the caller retry once.
        if e.code in (401, 403):
            _token_cache.pop(client_id, None)
        return None, _http_err(e, "catalog")
    except Exception as e:  # noqa: BLE001
        return None, f"Amazon Creators API error: {str(e)[:200]}"


def _parse_item(item, tag, region):
    """Flatten a Creators API item (lowerCamelCase) into our simple dict."""
    info = item.get("itemInfo", {}) or {}
    title = (((info.get("title") or {}).get("displayValue")) or "").strip()
    features = [f for f in (((info.get("features") or {}).get("displayValues")) or []) if f]
    # offersV2.listings[0].price.money.displayAmount
    price = ""
    listings = ((item.get("offersV2") or {}).get("listings") or [])
    if listings:
        price = (((listings[0].get("price") or {}).get("money") or {}).get("displayAmount")) or ""
    # images.primary.large.url + variants
    images = []
    prim = (((item.get("images") or {}).get("primary") or {}).get("large") or {}).get("url")
    if prim:
        images.append(prim)
    for v in ((item.get("images") or {}).get("variants") or []):
        u = ((v.get("large") or {}).get("url"))
        if u:
            images.append(u)
    asin = item.get("asin", "")
    url = item.get("detailPageURL") or affiliate_product_url(asin, tag, region)
    return {
        "asin": asin, "title": title, "url": url, "price": price,
        # Creators API dropped CustomerReviews - no rating available.
        "rating": "", "review_count": 0,
        "features": features[:6], "images": images[:5],
    }


def search_items(client_id, client_secret, tag, region, keywords, count=3):
    """Creators API searchItems. Returns (list_of_products, error)."""
    if not configured(client_id, client_secret, tag):
        return None, "Creators API credentials not configured."
    payload = {
        "keywords": keywords,
        "searchIndex": "All",
        "itemCount": max(1, min(int(count), 10)),
        "partnerTag": tag,
        "marketplace": _marketplace(region),
        "resources": _RESOURCES,
    }
    data, err = _catalog(client_id, client_secret, tag, region, _SEARCH_PATH, payload)
    if err:
        return None, err
    items = ((data or {}).get("searchResult") or {}).get("items") or []
    return [_parse_item(it, tag, region) for it in items], ""


def get_items(client_id, client_secret, tag, region, asins):
    """Creators API getItems for specific ASIN(s). Returns (list_of_products, error)."""
    if not configured(client_id, client_secret, tag):
        return None, "Creators API credentials not configured."
    if isinstance(asins, str):
        asins = [a.strip() for a in asins.split(",") if a.strip()]
    payload = {
        "itemIds": asins[:10],
        "itemIdType": "ASIN",
        "partnerTag": tag,
        "marketplace": _marketplace(region),
        "resources": _RESOURCES,
    }
    data, err = _catalog(client_id, client_secret, tag, region, _GETITEMS_PATH, payload)
    if err:
        return None, err
    items = ((data or {}).get("itemsResult") or {}).get("items") or []
    return [_parse_item(it, tag, region) for it in items], ""


def verify_keys(client_id, client_secret, tag, region):
    """Validate credentials by running a tiny search. Returns (ok, error)."""
    items, err = search_items(client_id, client_secret, tag, region, "usb cable", count=1)
    if err:
        return False, err
    return True, ""
