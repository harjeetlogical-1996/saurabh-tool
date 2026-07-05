"""
Google OAuth + Analytics (GA4 Data API) + Search Console client.

Uses only the standard library (urllib/json) so there are no extra dependencies.
Read-only scopes. Per-user refresh tokens are stored (encrypted) in db.py; here we
exchange codes, refresh access tokens, and call the two Google APIs.

Env:
  GOOGLE_CLIENT_ID
  GOOGLE_CLIENT_SECRET
  PUBLIC_URL (to build the redirect URI: {PUBLIC_URL}/google/callback)
"""
import os
import json
import time
import urllib.parse
import urllib.request
import urllib.error

CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
_PUBLIC = os.environ.get("PUBLIC_URL", "https://wptaskify.com").rstrip("/")
REDIRECT_URI = _PUBLIC + "/google/callback"

# Read-only: analytics + search console. Also request email/openid to label the account.
SCOPES = [
    "https://www.googleapis.com/auth/analytics.readonly",
    "https://www.googleapis.com/auth/webmasters.readonly",
    "openid",
    "email",
]

_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_URL = "https://oauth2.googleapis.com/token"

# Simple per-process access-token cache: {refresh_token: (access_token, expiry_ts)}
_ACCESS_CACHE = {}


def configured() -> bool:
    return bool(CLIENT_ID and CLIENT_SECRET)


def _post_form(url, data):
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def _get_json(url, access_token, params=None):
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + access_token})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def _post_json(url, access_token, payload):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), method="POST",
        headers={"Authorization": "Bearer " + access_token, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


# ---------------------------------------------------------------------------
# OAuth
# ---------------------------------------------------------------------------
def auth_url(state: str) -> str:
    """Build the Google consent URL. `state` ties the callback to the user/session."""
    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",     # get a refresh token
        "prompt": "consent",          # ensure a refresh token even on re-connect
        "include_granted_scopes": "true",
        "state": state,
    }
    return _AUTH_URL + "?" + urllib.parse.urlencode(params)


def exchange_code(code: str) -> dict:
    """Exchange an auth code for tokens. Returns {refresh_token, access_token, email}."""
    tok = _post_form(_TOKEN_URL, {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": REDIRECT_URI,
    })
    email = ""
    idt = tok.get("id_token")
    if idt:
        email = _email_from_id_token(idt)
    return {
        "refresh_token": tok.get("refresh_token", ""),
        "access_token": tok.get("access_token", ""),
        "email": email,
    }


def _email_from_id_token(id_token: str) -> str:
    """Decode the (unverified) JWT payload just to read the email claim. We trust it
    because it came straight from Google's token endpoint over TLS."""
    try:
        import base64
        payload = id_token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload).decode())
        return data.get("email", "")
    except Exception:
        return ""


def access_token(refresh_token: str) -> str:
    """Return a valid access token for a refresh token (cached until ~1 min before expiry)."""
    cached = _ACCESS_CACHE.get(refresh_token)
    if cached and cached[1] > time.time() + 60:
        return cached[0]
    tok = _post_form(_TOKEN_URL, {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    })
    at = tok.get("access_token", "")
    exp = time.time() + int(tok.get("expires_in", 3600))
    if at:
        _ACCESS_CACHE[refresh_token] = (at, exp)
    return at


# ---------------------------------------------------------------------------
# Discovery: list the user's GA4 properties + Search Console sites
# ---------------------------------------------------------------------------
def list_ga_properties(access_tok: str) -> list:
    """List GA4 properties the user can access (via the Admin API account summaries)."""
    out = []
    try:
        data = _get_json("https://analyticsadmin.googleapis.com/v1beta/accountSummaries",
                         access_tok, {"pageSize": 200})
        for acc in data.get("accountSummaries", []):
            for p in acc.get("propertySummaries", []):
                # property is like "properties/123456789"
                pid = p.get("property", "").split("/")[-1]
                out.append({"property_id": pid,
                            "display_name": p.get("displayName", ""),
                            "account": acc.get("displayName", "")})
    except Exception:
        pass
    return out


def list_sc_sites(access_tok: str) -> list:
    """List Search Console sites the user can access."""
    out = []
    try:
        data = _get_json("https://www.googleapis.com/webmasters/v3/sites", access_tok)
        for s in data.get("siteEntry", []):
            out.append({"site": s.get("siteUrl", ""), "permission": s.get("permissionLevel", "")})
    except Exception:
        pass
    return out


# ---------------------------------------------------------------------------
# GA4 Data API (runReport)
# ---------------------------------------------------------------------------
def ga_run_report(access_tok: str, property_id: str, dimensions, metrics,
                  start_date="28daysAgo", end_date="today", limit=20, order_metric=None):
    """Run a GA4 report. dimensions/metrics are lists of API names. Returns rows."""
    body = {
        "dateRanges": [{"startDate": start_date, "endDate": end_date}],
        "dimensions": [{"name": d} for d in dimensions],
        "metrics": [{"name": m} for m in metrics],
        "limit": int(limit),
    }
    if order_metric:
        body["orderBys"] = [{"metric": {"metricName": order_metric}, "desc": True}]
    url = "https://analyticsdata.googleapis.com/v1beta/properties/%s:runReport" % property_id
    data = _post_json(url, access_tok, body)
    dim_names = [d["name"] for d in body["dimensions"]]
    met_names = [m["name"] for m in body["metrics"]]
    rows = []
    for r in data.get("rows", []):
        row = {}
        for i, dv in enumerate(r.get("dimensionValues", [])):
            row[dim_names[i]] = dv.get("value")
        for i, mv in enumerate(r.get("metricValues", [])):
            row[met_names[i]] = mv.get("value")
        rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# Search Console (searchAnalytics.query)
# ---------------------------------------------------------------------------
def sc_query(access_tok: str, site: str, dimensions, start_date, end_date, limit=25):
    body = {
        "startDate": start_date,
        "endDate": end_date,
        "dimensions": dimensions,
        "rowLimit": int(limit),
    }
    url = "https://www.googleapis.com/webmasters/v3/sites/%s/searchAnalytics/query" % urllib.parse.quote(site, safe="")
    data = _post_json(url, access_tok, body)
    rows = []
    for r in data.get("rows", []):
        row = {}
        keys = r.get("keys", [])
        for i, d in enumerate(dimensions):
            row[d] = keys[i] if i < len(keys) else None
        row["clicks"] = r.get("clicks")
        row["impressions"] = r.get("impressions")
        row["ctr"] = round(r.get("ctr", 0) * 100, 2)
        row["position"] = round(r.get("position", 0), 1)
        rows.append(row)
    return rows
