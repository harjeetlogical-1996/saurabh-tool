"""
Amazon Product Advertising API v5 (PA-API) client + affiliate helpers. Stdlib only.

Two modes:
  - FULL (PA-API keys): search_items / get_items return real product data (title, price,
    rating, features, images) - needs the user's Amazon Associates Access key + Secret key
    + tag, and PA-API access (Associates account with >=3 qualifying sales).
  - FALLBACK (tag only): affiliate_search_url builds a tagged Amazon SEARCH link - no API,
    works for everyone.

PA-API requires AWS Signature Version 4. We sign with stdlib hmac/hashlib (no boto3),
the same HMAC style used elsewhere in this codebase.
Docs: https://webservices.amazon.com/paapi5/documentation/
"""
import json
import hmac
import hashlib
import datetime as _dt
import urllib.parse
import urllib.request
import urllib.error

# region -> (host for PA-API, marketplace www host, marketplace domain for URLs)
_REGIONS = {
    "com":    ("webservices.amazon.com",      "www.amazon.com",      "us-east-1"),
    "in":     ("webservices.amazon.in",       "www.amazon.in",       "eu-west-1"),
    "co.uk":  ("webservices.amazon.co.uk",    "www.amazon.co.uk",    "eu-west-1"),
    "ca":     ("webservices.amazon.ca",       "www.amazon.ca",       "us-east-1"),
    "de":     ("webservices.amazon.de",       "www.amazon.de",       "eu-west-1"),
    "fr":     ("webservices.amazon.fr",       "www.amazon.fr",       "eu-west-1"),
    "co.jp":  ("webservices.amazon.co.jp",    "www.amazon.co.jp",    "us-west-2"),
    "com.au": ("webservices.amazon.com.au",   "www.amazon.com.au",   "us-west-2"),
    "es":     ("webservices.amazon.es",       "www.amazon.es",       "eu-west-1"),
    "it":     ("webservices.amazon.it",       "www.amazon.it",       "eu-west-1"),
}
DEFAULT_REGION = "com"


def region_ok(region: str) -> bool:
    return (region or "").lower() in _REGIONS


def _www(region: str) -> str:
    return _REGIONS.get((region or "").lower(), _REGIONS[DEFAULT_REGION])[1]


def affiliate_search_url(keywords: str, tag: str, region: str = "com") -> str:
    """The NO-API fallback: a tagged Amazon SEARCH link. Works with just an associate tag."""
    www = _www(region)
    q = urllib.parse.urlencode({"k": keywords or "", "tag": tag or "", "linkCode": "ll2"})
    return f"https://{www}/s?{q}"


def affiliate_product_url(asin: str, tag: str, region: str = "com") -> str:
    """A tagged product (dp) link for a known ASIN."""
    www = _www(region)
    return f"https://{www}/dp/{asin}?tag={urllib.parse.quote(tag or '')}&linkCode=ll1"


def configured(access: str, secret: str, tag: str) -> bool:
    return bool(access and secret and tag)


# ---------------------------------------------------------------------------
# AWS Signature Version 4 (stdlib)
# ---------------------------------------------------------------------------
def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _signing_key(secret: str, date_stamp: str, region: str, service: str) -> bytes:
    k_date = _sign(("AWS4" + secret).encode("utf-8"), date_stamp)
    k_region = _sign(k_date, region)
    k_service = _sign(k_region, service)
    return _sign(k_service, "aws4_request")


def _paapi_request(access, secret, region, target, path, payload, now=None):
    """SigV4-sign and POST a PA-API operation. Returns (data_dict, error_str).
    `now` (a datetime) is injectable for deterministic tests."""
    host, _wwwhost, aws_region = _REGIONS.get((region or "").lower(), _REGIONS[DEFAULT_REGION])
    service = "ProductAdvertisingAPI"
    endpoint = f"https://{host}{path}"
    body = json.dumps(payload)
    amz_target = f"com.amazon.paapi5.v1.ProductAdvertisingAPIv1.{target}"
    content_type = "application/json; charset=utf-8"

    t = now or _dt.datetime.now(_dt.timezone.utc)
    amz_date = t.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = t.strftime("%Y%m%d")

    # Canonical request
    canonical_uri = path
    canonical_querystring = ""
    canonical_headers = (
        f"content-encoding:amz-1.0\n"
        f"content-type:{content_type}\n"
        f"host:{host}\n"
        f"x-amz-date:{amz_date}\n"
        f"x-amz-target:{amz_target}\n"
    )
    signed_headers = "content-encoding;content-type;host;x-amz-date;x-amz-target"
    payload_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
    canonical_request = (
        f"POST\n{canonical_uri}\n{canonical_querystring}\n"
        f"{canonical_headers}\n{signed_headers}\n{payload_hash}"
    )

    algorithm = "AWS4-HMAC-SHA256"
    credential_scope = f"{date_stamp}/{aws_region}/{service}/aws4_request"
    string_to_sign = (
        f"{algorithm}\n{amz_date}\n{credential_scope}\n"
        + hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()
    )
    signing_key = _signing_key(secret, date_stamp, aws_region, service)
    signature = hmac.new(signing_key, string_to_sign.encode("utf-8"),
                         hashlib.sha256).hexdigest()
    authorization = (
        f"{algorithm} Credential={access}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )

    headers = {
        "content-encoding": "amz-1.0",
        "content-type": content_type,
        "host": host,
        "x-amz-date": amz_date,
        "x-amz-target": amz_target,
        "Authorization": authorization,
    }
    req = urllib.request.Request(endpoint, data=body.encode("utf-8"),
                                 headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode()), ""
    except urllib.error.HTTPError as e:
        raw = ""
        try:
            raw = e.read().decode()[:400]
        except Exception:
            pass
        if e.code in (401, 403):
            return None, ("Amazon rejected the PA-API keys (invalid, or your Associates "
                          "account isn't approved for PA-API yet - needs 3 qualifying sales).")
        if e.code == 429:
            return None, "Amazon PA-API rate limit hit. Try again shortly."
        # PA-API returns useful JSON errors in the body.
        try:
            j = json.loads(raw)
            msgs = "; ".join(x.get("Message", "") for x in j.get("Errors", []))
            if msgs:
                return None, f"Amazon PA-API: {msgs}"
        except Exception:
            pass
        return None, f"Amazon PA-API {e.code}: {raw}"
    except Exception as e:  # noqa: BLE001
        return None, f"Amazon PA-API error: {str(e)[:200]}"


# The product data we ask Amazon for.
_RESOURCES = [
    "ItemInfo.Title",
    "ItemInfo.Features",
    "ItemInfo.ProductInfo",
    "Offers.Listings.Price",
    "Images.Primary.Large",
    "Images.Variants.Large",
    "CustomerReviews.StarRating",
    "CustomerReviews.Count",
]


def _parse_item(item, tag, region):
    """Flatten a PA-API item into our simple dict."""
    info = item.get("ItemInfo", {}) or {}
    title = (((info.get("Title") or {}).get("DisplayValue")) or "").strip()
    features = [f for f in (((info.get("Features") or {}).get("DisplayValues")) or []) if f]
    price = ""
    listings = ((item.get("Offers") or {}).get("Listings") or [])
    if listings:
        price = ((listings[0].get("Price") or {}).get("DisplayAmount")) or ""
    rating = ""
    count = 0
    cr = item.get("CustomerReviews") or {}
    if cr:
        rating = ((cr.get("StarRating") or {}).get("Value")) or ""
        count = (cr.get("Count") or {}).get("Value") or 0
    images = []
    prim = (((item.get("Images") or {}).get("Primary") or {}).get("Large") or {}).get("URL")
    if prim:
        images.append(prim)
    for v in ((item.get("Images") or {}).get("Variants") or []):
        u = ((v.get("Large") or {}).get("URL"))
        if u:
            images.append(u)
    asin = item.get("ASIN", "")
    url = item.get("DetailPageURL") or affiliate_product_url(asin, tag, region)
    return {
        "asin": asin, "title": title, "url": url, "price": price,
        "rating": rating, "review_count": count,
        "features": features[:6], "images": images[:5],
    }


def search_items(access, secret, tag, region, keywords, count=3):
    """PA-API SearchItems. Returns (list_of_products, error)."""
    if not configured(access, secret, tag):
        return None, "PA-API keys not configured."
    payload = {
        "Keywords": keywords,
        "SearchIndex": "All",
        "ItemCount": max(1, min(int(count), 10)),
        "PartnerTag": tag,
        "PartnerType": "Associates",
        "Marketplace": _www(region),
        "Resources": _RESOURCES,
    }
    data, err = _paapi_request(access, secret, region, "SearchItems",
                               "/paapi5/searchitems", payload)
    if err:
        return None, err
    items = ((data or {}).get("SearchResult") or {}).get("Items") or []
    return [_parse_item(it, tag, region) for it in items], ""


def get_items(access, secret, tag, region, asins):
    """PA-API GetItems for specific ASIN(s). Returns (list_of_products, error)."""
    if not configured(access, secret, tag):
        return None, "PA-API keys not configured."
    if isinstance(asins, str):
        asins = [a.strip() for a in asins.split(",") if a.strip()]
    payload = {
        "ItemIds": asins[:10],
        "ItemIdType": "ASIN",
        "PartnerTag": tag,
        "PartnerType": "Associates",
        "Marketplace": _www(region),
        "Resources": _RESOURCES,
    }
    data, err = _paapi_request(access, secret, region, "GetItems",
                               "/paapi5/getitems", payload)
    if err:
        return None, err
    items = ((data or {}).get("ItemsResult") or {}).get("Items") or []
    return [_parse_item(it, tag, region) for it in items], ""


def verify_keys(access, secret, tag, region):
    """Validate PA-API keys by running a tiny search. Returns (ok, error)."""
    items, err = search_items(access, secret, tag, region, "usb cable", count=1)
    if err:
        return False, err
    return True, ""
