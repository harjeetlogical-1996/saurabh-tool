"""
Bing Webmaster Tools client (stdlib-only).

Unlike Google (OAuth), Bing Webmaster Tools uses a simple API KEY: the user generates
one in Bing Webmaster Tools -> Settings -> API access, and pastes it into wptaskify. We
store it encrypted per (user, site) and call the JSON API with ?apikey=KEY.

API base: https://ssl.bing.com/webmaster/api.svc/json/<Method>?apikey=KEY[&params]
Docs: https://learn.microsoft.com/bingwebmaster/getting-access
"""
import json
import urllib.parse
import urllib.request
import urllib.error

_API = "https://ssl.bing.com/webmaster/api.svc/json"


def _get(method, api_key, params=None):
    """GET a Bing Webmaster JSON method. Returns (data, error)."""
    q = {"apikey": api_key}
    if params:
        q.update(params)
    url = f"{_API}/{method}?" + urllib.parse.urlencode(q)
    req = urllib.request.Request(url, headers={"User-Agent": "wptaskify"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode())
        # Bing wraps results in {"d": ...}; unwrap for convenience.
        return (data.get("d", data) if isinstance(data, dict) else data), ""
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode()[:300]
        except Exception:
            pass
        if e.code in (401, 403):
            return None, ("Bing rejected the API key (invalid or lacks access). Re-copy it "
                          "from Bing Webmaster Tools -> Settings -> API access.")
        return None, f"Bing API {e.code}: {body}"
    except Exception as e:  # noqa: BLE001
        return None, f"Bing API error: {str(e)[:200]}"


def _post(method, api_key, payload):
    """POST a Bing Webmaster JSON method (e.g. SubmitUrl). Returns (data, error)."""
    url = f"{_API}/{method}?" + urllib.parse.urlencode({"apikey": api_key})
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), method="POST",
        headers={"Content-Type": "application/json", "User-Agent": "wptaskify"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode().strip()
            data = json.loads(raw) if raw else {}
        return (data.get("d", data) if isinstance(data, dict) else data), ""
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode()[:300]
        except Exception:
            pass
        if e.code in (401, 403):
            return None, "Bing rejected the API key (invalid or lacks access)."
        return None, f"Bing API {e.code}: {body}"
    except Exception as e:  # noqa: BLE001
        return None, f"Bing API error: {str(e)[:200]}"


def verify_key(api_key):
    """Quick check that an API key is valid: list the user's sites. Returns (sites, error)
    where sites is a list of {url}. Used when the user first connects."""
    data, err = _get("GetUserSites", api_key)
    if err:
        return None, err
    sites = []
    for s in (data or []):
        u = s.get("Url") or s.get("url") or ""
        if u:
            sites.append({"url": u})
    return sites, ""


def list_sites(api_key):
    return verify_key(api_key)


def query_stats(api_key, site_url, limit=25):
    """Top search queries for a site: query, clicks, impressions, avg position.
    Returns (rows, error)."""
    data, err = _get("GetQueryStats", api_key, {"siteUrl": site_url})
    if err:
        return None, err
    rows = []
    for q in (data or []):
        rows.append({
            "query": q.get("Query", ""),
            "clicks": q.get("Clicks", 0),
            "impressions": q.get("Impressions", 0),
            "position": q.get("AvgImpressionPosition", q.get("AvgClickPosition", 0)),
        })
    rows.sort(key=lambda r: r["clicks"], reverse=True)
    return rows[:limit], ""


def page_stats(api_key, site_url, limit=25):
    """Top pages by Bing traffic: url, clicks, impressions. Returns (rows, error)."""
    data, err = _get("GetPageStats", api_key, {"siteUrl": site_url})
    if err:
        return None, err
    rows = []
    for p in (data or []):
        rows.append({
            "page": p.get("Query", p.get("Url", "")),   # GetPageStats keys the page in "Query"
            "clicks": p.get("Clicks", 0),
            "impressions": p.get("Impressions", 0),
        })
    rows.sort(key=lambda r: r["clicks"], reverse=True)
    return rows[:limit], ""


def crawl_stats(api_key, site_url):
    """Crawl / index status: crawled pages, in-index count, errors, blocked. Returns
    (summary, error). Bing's crawl reporting is its strong suit."""
    data, err = _get("GetCrawlStats", api_key, {"siteUrl": site_url})
    if err:
        return None, err
    # GetCrawlStats returns a list of daily entries; summarise the latest + totals.
    entries = data or []
    if not entries:
        return {"days": 0}, ""
    total_crawled = sum(int(e.get("CrawledPages", 0) or 0) for e in entries)
    total_errors = sum(int(e.get("CrawlErrors", 0) or 0) for e in entries)
    total_blocked = sum(int(e.get("BlockedByRobotsTxt", 0) or 0) for e in entries)
    total_in_index = max((int(e.get("InIndex", 0) or 0) for e in entries), default=0)
    return {
        "days": len(entries),
        "crawled_pages": total_crawled,
        "crawl_errors": total_errors,
        "blocked_by_robots": total_blocked,
        "in_index": total_in_index,
    }, ""


def submit_url(api_key, site_url, url):
    """Ask Bing to (re)crawl a single URL. Bing allows this instantly (unlike Google).
    Returns (ok, error)."""
    payload = {"siteUrl": site_url, "url": url}
    data, err = _post("SubmitUrl", api_key, payload)
    if err:
        return False, err
    return True, ""
