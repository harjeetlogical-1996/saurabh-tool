"""
WordPress MCP Server for completewaterguide.com  (FULL CONTROL)
----------------------------------------------------------------
claude.ai (browser) se connect hota hai aur WP REST API ke through
poori site manage karta hai: posts, pages, media+featured image,
categories, tags, comments, bulk find-replace, site info.

Credentials env vars se aate hain (NEVER hardcode):
  WP_SITE_URL  WP_USERNAME  WP_APP_PASSWORD

Transport: streamable HTTP at /mcp  (claude.ai remote connector)
"""

import os
import base64
import json
import time as _time
import mimetypes
import contextvars
import urllib.request
import urllib.error
import urllib.parse

from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Per-tenant config (multi-tenant SaaS)
# ---------------------------------------------------------------------------
# Each incoming request resolves ONE tenant's WordPress credentials and stores
# them in this context var for the duration of the request. The middleware in
# start.py sets it. Tools read it via _cfg(). FAIL-CLOSED: if no tenant context
# is set, _cfg() raises - we NEVER fall back to a default site.
#
# Single-tenant fallback: if WP_SITE_URL env vars are present (your own site),
# we build a default config so the server still works standalone for testing.

current_tenant: contextvars.ContextVar = contextvars.ContextVar("current_tenant", default=None)

# Per-CALL site override. When a tool is given a `site` argument, we resolve that
# site's credentials once and stash a temporary tenant config here for the duration
# of that single tool call. This lets two different chats target two different
# sites at the same time (one connector), WITHOUT changing the account-wide active
# site that `use_site` sets. _cfg() prefers this override when present.
_call_site_cfg: contextvars.ContextVar = contextvars.ContextVar("_call_site_cfg", default=None)
# Tiny cache so repeated calls with the same `site` in one chat don't re-hit the DB.
_site_cfg_cache = {}


def _apply_site(site: str):
    """If a tool was called with a non-empty `site`, switch THIS call to that site's
    credentials (per-call, does not persist). No-op when `site` is blank. Raises a
    clear error if the site name doesn't match any connected site."""
    site = (site or "").strip()
    if not site:
        _call_site_cfg.set(None)
        return
    base = current_tenant.get() or _DEFAULT_TENANT
    uid = (base or {}).get("user_id", "")
    key = (uid, site.lower())
    over = _site_cfg_cache.get(key)
    if over is None:
        import db as _db
        import base64 as _b64
        match = _db.get_site_by_ref(uid, site) if uid else None
        if not match:
            raise RuntimeError(
                f"site '{site}' is not one of your connected sites. "
                "Use list_my_sites to see the exact URLs.")
        token = _b64.b64encode(
            f"{match['wp_username']}:{match['app_password'].replace(' ', '')}".encode()).decode()
        over = dict(base or {})
        over["site_url"] = match["site_url"].rstrip("/")
        over["base_headers"] = {"Authorization": "Basic " + token, "User-Agent": "wp-mcp/3.0"}
        _site_cfg_cache[key] = over
    _call_site_cfg.set(over)


def make_tenant_config(site_url: str, username: str, app_password: str,
                       gemini_api_key: str = "", user_id: str = "", credit_hook=None,
                       toolcall_hook=None, approval_hook=None, approval_status_hook=None,
                       balance_hook=None, credit_refund_hook=None, toolcall_refund_hook=None,
                       plan: str = ""):
    """Build a tenant config dict with precomputed auth header.
    credit_hook() -> bool: consume 1 image credit (image tools).
    credit_refund_hook(): give back 1 image credit (call if generation failed).
    toolcall_hook() -> bool: consume 1 tool call (connect-own-AI plans); return
    False if the monthly tool-call limit is reached.
    toolcall_refund_hook(): give back 1 tool call (call if the WP request failed).
    balance_hook() -> dict: current {images, images_max, actions, actions_max,
    has_own_key} so tools can warn the user when a balance is running low.
    approval_hook(tool, args, summary, risk) -> id: queue a risky action for the
    user to approve in the dashboard (used by request_approval)."""
    token = base64.b64encode(f"{username}:{app_password.replace(' ', '')}".encode()).decode()
    return {
        "site_url": site_url.rstrip("/"),
        "base_headers": {"Authorization": "Basic " + token, "User-Agent": "wp-mcp/3.0"},
        "gemini_api_key": gemini_api_key or os.environ.get("GEMINI_API_KEY", ""),
        "user_id": user_id,
        "plan": plan or "free",
        "credit_hook": credit_hook,
        "credit_refund_hook": credit_refund_hook,
        "toolcall_hook": toolcall_hook,
        "toolcall_refund_hook": toolcall_refund_hook,
        "balance_hook": balance_hook,
        "approval_hook": approval_hook,
        "approval_status_hook": approval_status_hook,
    }


def _low_balance_note():
    """If the tenant's image/action balance is running low, return a short warning
    string for the AI to relay to the user. Empty string if fine. Called by tools
    after they consume a credit/action so the AI proactively tells the user."""
    cfg = _cfg()
    hook = cfg.get("balance_hook")
    if hook is None:
        return ""
    try:
        b = hook() or {}
    except Exception:
        return ""
    if b.get("has_own_key"):
        return ""
    notes = []
    img, imgx = b.get("images"), b.get("images_max")
    act, actx = b.get("actions"), b.get("actions_max")
    if img is not None and 0 < img <= 5:
        notes.append(f"NOTE FOR THE USER: only {img} AI image credit(s) left this month. "
                     "Tell them they can top up or upgrade in their wptaskify dashboard.")
    elif img == 0:
        notes.append("NOTE FOR THE USER: they are OUT of AI image credits this month. "
                     "Tell them to top up or upgrade in their wptaskify dashboard.")
    if act is not None and actx and actx < 1_000_000 and 0 < act <= 25:
        notes.append(f"NOTE FOR THE USER: only {act} AI action(s) left this month. "
                     "Tell them to upgrade in their wptaskify dashboard for more.")
    return ("\n\n" + " ".join(notes)) if notes else ""


# Optional single-tenant fallback from env (lets the server run for one site
# without a DB - used in local/standalone testing).
_DEFAULT_TENANT = None
if os.environ.get("WP_SITE_URL") and os.environ.get("WP_APP_PASSWORD"):
    _DEFAULT_TENANT = make_tenant_config(
        os.environ["WP_SITE_URL"],
        os.environ.get("WP_USERNAME", ""),
        os.environ["WP_APP_PASSWORD"],
    )


def _cfg():
    """Return the tenant config for the current tool call. Prefers a per-call
    `site` override (set by _apply_site) so one chat can target a specific site
    without affecting others; otherwise the request's resolved tenant. FAIL-CLOSED."""
    over = _call_site_cfg.get()
    if over is not None:
        return over
    cfg = current_tenant.get()
    if cfg is None:
        cfg = _DEFAULT_TENANT
    if cfg is None:
        raise RuntimeError(
            "No tenant context: this request is not bound to any WordPress site. "
            "Connect a site first (multi-tenant) or set WP_* env vars (standalone)."
        )
    # Valid account but no WordPress site connected yet -> clear, friendly guidance
    # instead of a cryptic auth failure.
    if cfg.get("no_site"):
        raise RuntimeError(
            "No WordPress site is connected to your wptaskify account yet. "
            "To use this, first add your site: install the free wptaskify plugin on "
            "your WordPress site and click Connect (or add it from your wptaskify "
            "dashboard). Then try again.")
    return cfg


mcp = FastMCP("wptaskify")


# ---------------------------------------------------------------------------
# Plan-based tool gating
# ---------------------------------------------------------------------------
# Tiers (least -> most): "free" tools work on every plan. "paid" tools need any
# paid plan (Mini/Starter/Pro). "pro" tools (Studio: file/theme/plugin editing)
# need the Pro plan. A tool with no explicit tier is treated as "free".
_PAID_PLANS = {"owai_mini", "owai_starter", "owai_pro", "pro", "agency",
               "chat_starter", "chat_pro", "chat_max"}
_PRO_PLANS = {"owai_pro", "agency", "chat_max"}


def _require_tier(tier: str):
    """Raise a friendly upgrade message if the current plan can't use this tool.
    Called at the top of gated (paid/pro) tools."""
    plan = (_cfg().get("plan") or "free").lower()
    if tier == "pro":
        if plan not in _PRO_PLANS:
            raise RuntimeError(
                "This is a Pro feature (Studio: creating/editing themes, plugins and "
                "files). Upgrade to the Pro plan in your wptaskify dashboard to use it.")
    elif tier == "paid":
        if plan == "free":
            raise RuntimeError(
                "This tool needs a paid plan. The free plan includes read-only SEO tools "
                "(list/get content, SEO audit, SEO score). Upgrade in your wptaskify "
                "dashboard to publish, run bulk actions, generate images and more.")


# ---------------------------------------------------------------------------
# REST helpers
# ---------------------------------------------------------------------------
def _request(method, path, payload=None, params=None, raw_body=None, extra_headers=None):
    cfg = _cfg()
    # Tool-call budget gate (connect-your-own-AI plans). Each WP REST action
    # counts as one tool call. Chat plans have a huge limit so they don't block.
    hook = cfg.get("toolcall_hook")
    if hook is not None and not hook():
        raise RuntimeError(
            "Monthly tool-call limit reached for your plan. Upgrade your plan, "
            "or switch to a Built-in Chat plan for token-based usage."
        )
    base = cfg["site_url"].rstrip("/")
    # Two ways WordPress serves the REST API:
    #  - pretty:  {site}/wp-json/{path}?{params}     (needs pretty permalinks)
    #  - plain:   {site}/?rest_route=/{path}&{params} (always works, even if a cache
    #             flush / plugin update broke the /wp-json/ rewrite rules)
    # We try pretty first; if it 404s (the classic "broke permalinks" symptom) we
    # transparently retry via ?rest_route= so tools keep working.
    _qs = ("?" + urllib.parse.urlencode(params)) if params else ""
    url = base + "/wp-json" + path + _qs
    _pmap = {"rest_route": path}
    if params:
        _pmap.update(params)
    url_plain = base + "/?" + urllib.parse.urlencode(_pmap)
    headers = dict(cfg["base_headers"])
    if extra_headers:
        headers.update(extra_headers)
    if raw_body is not None:
        data = raw_body
    elif payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    else:
        data = None
    def _refund_call():
        """Give back the tool call we just consumed (the WP request failed)."""
        rf = cfg.get("toolcall_refund_hook")
        if hook is not None and rf is not None:
            try:
                rf()
            except Exception:
                pass

    def _do(u):
        r = urllib.request.Request(u, data=data, headers=headers, method=method)
        with urllib.request.urlopen(r, timeout=120) as resp:
            body = resp.read().decode()
            return json.loads(body) if body else {}

    # Transient network hiccups (timeout, connection reset, temporary DNS) made
    # read-only tools like list_studio_backups fail on one call and succeed on the
    # next. Retry idempotent GETs a couple of times on NETWORK errors only - never
    # on an HTTP status (a 4xx/5xx is a real answer, not a blip) and never on
    # writes (could double-apply). Backoff is fixed & tiny to stay snappy.
    idempotent = (method.upper() == "GET")
    attempts = 3 if idempotent else 1
    last_exc = None
    for attempt in range(attempts):
        try:
            return _do(url)
        except urllib.error.HTTPError as e:
            # A 404 on /wp-json/ almost always means the permalink rewrite broke
            # (LiteSpeed/cache flush, plugin update). The ?rest_route= form doesn't
            # rely on rewrites, so try it once before giving up - keeps every tool
            # working even when the site's pretty permalinks are broken.
            if e.code == 404 and url_plain != url:
                try:
                    return _do(url_plain)
                except urllib.error.HTTPError as e2:
                    _refund_call()
                    raise RuntimeError(f"WP API {e2.code}: {e2.read().decode()[:600]}")
                except Exception as e2:  # noqa: BLE001
                    last_exc = e2
                    if attempt < attempts - 1:
                        _time.sleep(0.6 * (attempt + 1))
                        continue
                    _refund_call()
                    raise RuntimeError(f"Request failed: {type(e2).__name__}: {e2}")
            _refund_call()
            raise RuntimeError(f"WP API {e.code}: {e.read().decode()[:600]}")
        except Exception as e:  # noqa: BLE001 - network-level failure
            last_exc = e
            if attempt < attempts - 1:
                _time.sleep(0.6 * (attempt + 1))  # 0.6s, 1.2s
                continue
    _refund_call()
    raise RuntimeError(
        f"Request failed after {attempts} attempt(s): "
        f"{type(last_exc).__name__}: {last_exc}. This usually means the site was "
        "briefly unreachable (timeout/connection reset) - try again.")


def _v2(method, path, payload=None, params=None):
    return _request(method, "/wp/v2" + path, payload=payload, params=params)


def _slim_post(p):
    return {
        "id": p.get("id"),
        "title": (p.get("title") or {}).get("rendered") or (p.get("title") or {}).get("raw", ""),
        "status": p.get("status"),
        "link": p.get("link"),
        "date": p.get("date"),
        "slug": p.get("slug"),
        "featured_media": p.get("featured_media"),
        "categories": p.get("categories"),
        "tags": p.get("tags"),
    }


# ===========================================================================
# POSTS
# ===========================================================================
@mcp.tool()
def list_posts(search: str = "", status: str = "publish,draft", per_page: int = 10, page: int = 1, site: str = "") -> str:
    """List posts. Filter by `search` text and `status` (publish,draft,pending,private,future).
    Returns id, title, status, link, categories, tags. Use to find a post ID before editing."""
    _apply_site(site)
    params = {"per_page": min(per_page, 50), "page": page, "status": status, "context": "edit"}
    if search:
        params["search"] = search
    return json.dumps([_slim_post(p) for p in _v2("GET", "/posts", params=params)], indent=2, ensure_ascii=False)


@mcp.tool()
def get_post(post_id: int, site: str = "") -> str:
    """Get one post's FULL raw content (HTML) + title, excerpt, status, categories,
    tags, featured image id. Read this before editing."""
    _apply_site(site)
    p = _v2("GET", f"/posts/{post_id}", params={"context": "edit"})
    return json.dumps({
        "id": p.get("id"),
        "title": (p.get("title") or {}).get("raw", ""),
        "status": p.get("status"),
        "link": p.get("link"),
        "slug": p.get("slug"),
        "excerpt": (p.get("excerpt") or {}).get("raw", ""),
        "categories": p.get("categories"),
        "tags": p.get("tags"),
        "featured_media": p.get("featured_media"),
        "content": (p.get("content") or {}).get("raw", ""),
    }, indent=2, ensure_ascii=False)


@mcp.tool()
def create_post(title: str, content: str, status: str = "draft", excerpt: str = "",
                category_ids: str = "", tag_ids: str = "", featured_media_id: int = 0, site: str = "") -> str:
    """Create a post. status defaults to 'draft' (safe). content is HTML.
    category_ids / tag_ids = comma-separated IDs (e.g. '3,7'). featured_media_id = media ID for thumbnail."""
    _require_tier('paid')
    _apply_site(site)
    payload = {"title": title, "content": content, "status": status}
    if excerpt:
        payload["excerpt"] = excerpt
    if category_ids:
        payload["categories"] = [int(x) for x in category_ids.split(",") if x.strip()]
    if tag_ids:
        payload["tags"] = [int(x) for x in tag_ids.split(",") if x.strip()]
    if featured_media_id:
        payload["featured_media"] = featured_media_id
    return json.dumps(_slim_post(_v2("POST", "/posts", payload=payload)), indent=2, ensure_ascii=False)


@mcp.tool()
def update_post(post_id: int, title: str = "", content: str = "", status: str = "",
                excerpt: str = "", category_ids: str = "", tag_ids: str = "",
                featured_media_id: int = 0, site: str = "") -> str:
    """Edit a post by ID. Only non-empty fields change. content replaces whole body (HTML).
    Pass status='publish' to make a draft live. category_ids/tag_ids = comma-separated IDs."""
    _require_tier('paid')
    _apply_site(site)
    payload = {}
    if title:
        payload["title"] = title
    if content:
        payload["content"] = content
    if status:
        payload["status"] = status
    if excerpt:
        payload["excerpt"] = excerpt
    if category_ids:
        payload["categories"] = [int(x) for x in category_ids.split(",") if x.strip()]
    if tag_ids:
        payload["tags"] = [int(x) for x in tag_ids.split(",") if x.strip()]
    if featured_media_id:
        payload["featured_media"] = featured_media_id
    if not payload:
        return "Nothing to update."
    return json.dumps(_slim_post(_v2("POST", f"/posts/{post_id}", payload=payload)), indent=2, ensure_ascii=False)


@mcp.tool()
def delete_post(post_id: int, permanent: bool = False, site: str = "") -> str:
    """Delete a post. Default = move to Trash (recoverable). permanent=True = delete forever."""
    _require_tier('paid')
    _apply_site(site)
    _v2("DELETE", f"/posts/{post_id}", params={"force": "true"} if permanent else None)
    return json.dumps({"id": post_id, "result": "deleted" if permanent else "trashed"})


# ===========================================================================
# BULK FIND & REPLACE
# ===========================================================================
@mcp.tool()
def bulk_find_replace(find: str, replace: str, dry_run: bool = True, status: str = "publish,draft", limit: int = 200, site: str = "") -> str:
    """Find `find` text across ALL posts' content and replace with `replace`.
    dry_run=True (default) only REPORTS which posts would change (does NOT edit).
    Run with dry_run=False to actually apply. Always dry-run first, show the user, then apply."""
    _require_tier('paid')
    _apply_site(site)
    changed = []
    page = 1
    scanned = 0
    while scanned < limit:
        posts = _v2("GET", "/posts", params={"per_page": 50, "page": page, "status": status, "context": "edit"})
        if not posts:
            break
        for p in posts:
            scanned += 1
            body = (p.get("content") or {}).get("raw", "")
            if find in body:
                count = body.count(find)
                entry = {"id": p["id"], "title": (p.get("title") or {}).get("raw", ""), "occurrences": count}
                if not dry_run:
                    _v2("POST", f"/posts/{p['id']}", payload={"content": body.replace(find, replace)})
                    entry["applied"] = True
                changed.append(entry)
        if len(posts) < 50:
            break
        page += 1
    return json.dumps({
        "mode": "DRY RUN (nothing changed)" if dry_run else "APPLIED",
        "find": find, "replace": replace,
        "posts_scanned": scanned,
        "posts_matched": len(changed),
        "matches": changed,
    }, indent=2, ensure_ascii=False)


# ===========================================================================
# SCHEMA (JSON-LD) - this site embeds <script type="application/ld+json">
# INSIDE the post content. These tools let you read/replace ONLY the schema
# block without disturbing the rest of the article, and vice-versa.
# ===========================================================================
import re as _re

_SCHEMA_RE = _re.compile(
    r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>.*?</script>',
    _re.IGNORECASE | _re.DOTALL,
)

# Blocks whose TEXT is page chrome, not article prose - author byline, reviewed-by
# line, "N min read", updated date, share bars, related-posts widgets. If we don't
# remove these before extracting "first sentences" for a meta description or a GEO
# answer block, we get garbage like "By David Anderson · Reviewed by … · 13 min
# read". Matched by common class names (theme uses cwg-byline etc.).
_META_BLOCK_RE = _re.compile(
    r'(?is)<(div|span|p|section|aside|header|footer|ul|nav)\b[^>]*'
    r'class=["\'][^"\']*'
    r'(byline|by-line|post-meta|entry-meta|article-meta|author(-|_)?(box|bio|meta)?|'
    r'reviewed|read-?time|reading-?time|share|social|breadcrumb|related|meta-info|'
    r'post-info|entry-header|posted-on|timestamp)'
    r'[^"\']*["\'][^>]*>.*?</\1>')
_STYLE_SCRIPT_RE = _re.compile(r'(?is)<(script|style|noscript)\b[^>]*>.*?</\1>')
_FIGURE_RE = _re.compile(r'(?is)<figure\b[^>]*>.*?</figure>')


def _content_text(raw_html):
    """Extract ARTICLE PROSE text from post HTML, with page chrome removed
    (byline/date/read-time/share/related/figures/schema). Use this instead of a
    bare tag-strip whenever the result feeds a meta description, an answer block,
    or any 'first sentences' extraction - so bylines never leak in."""
    html = _SCHEMA_RE.sub(" ", raw_html or "")
    html = _STYLE_SCRIPT_RE.sub(" ", html)
    html = _META_BLOCK_RE.sub(" ", html)
    html = _FIGURE_RE.sub(" ", html)
    text = _re.sub(r"<[^>]+>", " ", html)
    return _re.sub(r"\s+", " ", text).strip()


@mcp.tool()
def get_post_schema(post_id: int, site: str = "") -> str:
    """Extract ONLY the JSON-LD schema block(s) from a post's content.
    Use this to read/inspect a post's structured data without the full article."""
    _apply_site(site)
    p = _v2("GET", f"/posts/{post_id}", params={"context": "edit"})
    raw = (p.get("content") or {}).get("raw", "")
    blocks = _SCHEMA_RE.findall(raw)
    if not blocks:
        return json.dumps({"post_id": post_id, "schema_blocks": 0,
                           "note": "No <script type=application/ld+json> found in content."})
    return json.dumps({"post_id": post_id, "schema_blocks": len(blocks),
                       "schema": "\n\n".join(blocks)}, indent=2, ensure_ascii=False)


@mcp.tool()
def update_post_schema(post_id: int, new_schema_script: str, site: str = "") -> str:
    """Replace ONLY the JSON-LD schema block in a post, leaving the article body
    untouched. `new_schema_script` must be a full <script type="application/ld+json">
    ... </script> tag. If the post has no schema yet, it is appended at the end."""
    _require_tier('paid')
    _apply_site(site)
    p = _v2("GET", f"/posts/{post_id}", params={"context": "edit"})
    raw = (p.get("content") or {}).get("raw", "")
    if _SCHEMA_RE.search(raw):
        new_raw = _SCHEMA_RE.sub(lambda _m: new_schema_script, raw, count=1)
        action = "replaced"
    else:
        new_raw = raw + "\n\n" + new_schema_script
        action = "appended"
    _v2("POST", f"/posts/{post_id}", payload={"content": new_raw})
    return json.dumps({"post_id": post_id, "schema": action})


@mcp.tool()
def update_post_body_keep_schema(post_id: int, new_content: str, site: str = "") -> str:
    """Replace the article body but PRESERVE the existing JSON-LD schema block.
    Pass `new_content` as the new article HTML WITHOUT schema; the post's current
    schema <script> is automatically re-appended so structured data is not lost.
    Use this for normal content edits on this site."""
    _require_tier('paid')
    _apply_site(site)
    p = _v2("GET", f"/posts/{post_id}", params={"context": "edit"})
    raw = (p.get("content") or {}).get("raw", "")
    blocks = _SCHEMA_RE.findall(raw)
    body = new_content
    if blocks and "application/ld+json" not in new_content:
        body = new_content.rstrip() + "\n\n" + "\n\n".join(blocks)
    _v2("POST", f"/posts/{post_id}", payload={"content": body})
    return json.dumps({"post_id": post_id, "result": "body updated",
                       "schema_preserved": len(blocks)})


# ===========================================================================
# MEDIA / FEATURED IMAGE
# ===========================================================================
@mcp.tool()
def list_media(search: str = "", per_page: int = 10, site: str = "") -> str:
    """List media library items (images). Returns id, title, source_url, mime_type."""
    _apply_site(site)
    params = {"per_page": min(per_page, 50), "context": "edit"}
    if search:
        params["search"] = search
    items = _v2("GET", "/media", params=params)
    return json.dumps([{"id": m["id"], "title": (m.get("title") or {}).get("rendered", ""),
                        "url": m.get("source_url"), "mime": m.get("mime_type")} for m in items],
                      indent=2, ensure_ascii=False)


@mcp.tool()
def upload_media_from_url(image_url: str, filename: str = "", alt_text: str = "", site: str = "") -> str:
    """Download an image from a public URL and upload it to the WP media library.
    Returns the new media id (use it as featured_media_id when creating/updating a post)."""
    _require_tier('paid')
    _apply_site(site)
    with urllib.request.urlopen(image_url, timeout=120) as r:
        data = r.read()
        ctype = r.headers.get("Content-Type", "image/jpeg")
    if not filename:
        filename = os.path.basename(urllib.parse.urlparse(image_url).path) or "image.jpg"
        if "." not in filename:
            ext = mimetypes.guess_extension(ctype) or ".jpg"
            filename += ext
    media = _request("POST", "/wp/v2/media", raw_body=data, extra_headers={
        "Content-Type": ctype,
        "Content-Disposition": f'attachment; filename="{filename}"',
    })
    mid = media["id"]
    if alt_text:
        _v2("POST", f"/media/{mid}", payload={"alt_text": alt_text})
    return json.dumps({"id": mid, "url": media.get("source_url"), "title": (media.get("title") or {}).get("rendered", "")},
                      indent=2, ensure_ascii=False)


@mcp.tool()
def set_featured_image(post_id: int, media_id: int, site: str = "") -> str:
    """Set a post's featured image (thumbnail) to an existing media item id."""
    _require_tier('paid')
    _apply_site(site)
    p = _v2("POST", f"/posts/{post_id}", payload={"featured_media": media_id})
    return json.dumps({"post_id": post_id, "featured_media": p.get("featured_media")})


@mcp.tool()
def delete_media(media_id: int, site: str = "") -> str:
    """Permanently delete a media item by id."""
    _require_tier('paid')
    _apply_site(site)
    _v2("DELETE", f"/media/{media_id}", params={"force": "true"})
    return json.dumps({"id": media_id, "result": "deleted"})


# ===========================================================================
# AI FEATURED IMAGE (Google Gemini -> WP media library)
# ===========================================================================
# Gemini image-generation model (latest available on this key)
_GEMINI_IMAGE_MODEL = os.environ.get("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image")


def _gemini_generate_image(prompt: str) -> bytes:
    """Call Gemini image generation and return raw PNG/JPEG bytes.
    Consumes 1 image credit first (unless the tenant uses their own key).
    Uses the tenant's Gemini key (BYOK) or the platform key from env."""
    cfg = _cfg()
    # Credit gate (multi-tenant). BYOK users bypass inside the hook.
    # Track whether we ACTUALLY consumed a platform credit - BYOK users don't, so they
    # must never be "refunded" one on failure (that would mint free platform credits).
    hook = cfg.get("credit_hook")
    consumed = False
    if hook is not None:
        bal = cfg.get("balance_hook")
        has_own_key = False
        try:
            has_own_key = bool((bal() or {}).get("has_own_key")) if bal else False
        except Exception:
            has_own_key = False
        if not hook():
            raise RuntimeError(
                "You're out of AI image credits for this month. Add your own Gemini API key "
                "in your dashboard for unlimited images, or upgrade your plan."
            )
        consumed = not has_own_key  # BYOK bypasses consumption -> nothing to refund

    def _refund():
        """Give back the credit ONLY if one was actually consumed (never for BYOK)."""
        rf = cfg.get("credit_refund_hook")
        if consumed and rf is not None:
            try:
                rf()
            except Exception:
                pass

    api_key = cfg.get("gemini_api_key", "")
    if not api_key:
        _refund()
        raise RuntimeError("No Gemini API key for this tenant (add one or set platform GEMINI_API_KEY).")
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{_GEMINI_IMAGE_MODEL}:generateContent?key={api_key}")
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
    }
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            resp = json.load(r)
    except urllib.error.HTTPError as e:
        _refund()
        raise RuntimeError(f"Gemini API {e.code}: {e.read().decode()[:500]}")
    except Exception:
        _refund()
        raise
    for cand in resp.get("candidates", []):
        for part in (cand.get("content") or {}).get("parts", []):
            inline = part.get("inlineData") or part.get("inline_data")
            if inline and inline.get("data"):
                return base64.b64decode(inline["data"])
    # No image in a 200 response -> also a failure; refund the credit.
    _refund()
    raise RuntimeError("Gemini returned no image. Response: " + json.dumps(resp)[:400])


@mcp.tool()
def generate_featured_image(post_id: int, prompt: str = "", set_as_featured: bool = True, site: str = "") -> str:
    """Generate a REALISTIC PHOTO featured image with Google Gemini and attach it
    to a post. If `prompt` is empty, an automatic prompt is built from the post's
    title (realistic water/hydration photography style). The image is uploaded to
    the WP media library and (by default) set as the post's featured image.
    Returns the new media id + url."""
    _require_tier('paid')
    _apply_site(site)
    # Build prompt from title if not provided
    p = _v2("GET", f"/posts/{post_id}", params={"context": "edit"})
    title = (p.get("title") or {}).get("raw", "") or (p.get("title") or {}).get("rendered", "")
    if not prompt:
        prompt = (
            f"A high-quality, photorealistic professional photograph for a blog article "
            f"titled '{title}'. Clean, bright, modern water/hydration theme: crystal-clear "
            f"water, glass, droplets, soft natural lighting, shallow depth of field, "
            f"editorial stock-photo quality. No text, no watermark, no logos. 16:9 composition."
        )
    img_bytes = _gemini_generate_image(prompt)

    # Upload to WP media
    safe_title = _re.sub(r"[^a-zA-Z0-9]+", "-", title.lower()).strip("-")[:60] or f"post-{post_id}"
    filename = f"{safe_title}-featured.png"
    media = _request("POST", "/wp/v2/media", raw_body=img_bytes, extra_headers={
        "Content-Type": "image/png",
        "Content-Disposition": f'attachment; filename="{filename}"',
    })
    mid = media["id"]
    # alt text from title
    _v2("POST", f"/media/{mid}", payload={"alt_text": title})

    result = {"media_id": mid, "url": media.get("source_url"), "prompt_used": prompt[:160]}
    if set_as_featured:
        _v2("POST", f"/posts/{post_id}", payload={"featured_media": mid})
        result["set_as_featured_on"] = post_id
    _note = _low_balance_note()
    if _note:
        result["notice"] = _note.strip()
    return json.dumps(result, indent=2, ensure_ascii=False)


@mcp.tool()
def generate_image_standalone(prompt: str, filename: str = "ai-image", site: str = "") -> str:
    """Generate a realistic image with Gemini from a free-text prompt and upload it
    to the media library (NOT attached to any post). Returns media id + url.
    Use when you just need an image in the library."""
    _require_tier('paid')
    _apply_site(site)
    img_bytes = _gemini_generate_image(prompt)
    safe = _re.sub(r"[^a-zA-Z0-9]+", "-", filename.lower()).strip("-")[:60] or "ai-image"
    media = _request("POST", "/wp/v2/media", raw_body=img_bytes, extra_headers={
        "Content-Type": "image/png",
        "Content-Disposition": f'attachment; filename="{safe}.png"',
    })
    out = {"media_id": media["id"], "url": media.get("source_url")}
    _note = _low_balance_note()
    if _note:
        out["notice"] = _note.strip()
    return json.dumps(out, indent=2, ensure_ascii=False)


# ===========================================================================
# CATEGORIES & TAGS
# ===========================================================================
@mcp.tool()
def list_categories(per_page: int = 100, site: str = "") -> str:
    """List all categories with id, name, count, slug. Use IDs when assigning to posts."""
    _apply_site(site)
    cats = _v2("GET", "/categories", params={"per_page": per_page})
    return json.dumps([{"id": c["id"], "name": c["name"], "count": c["count"], "slug": c["slug"]} for c in cats],
                      indent=2, ensure_ascii=False)


@mcp.tool()
def create_category(name: str, description: str = "", parent_id: int = 0, site: str = "") -> str:
    """Create a new category. Returns its id."""
    _require_tier('paid')
    _apply_site(site)
    payload = {"name": name}
    if description:
        payload["description"] = description
    if parent_id:
        payload["parent"] = parent_id
    c = _v2("POST", "/categories", payload=payload)
    return json.dumps({"id": c["id"], "name": c["name"], "slug": c["slug"]})


@mcp.tool()
def list_tags(search: str = "", per_page: int = 100, site: str = "") -> str:
    """List tags with id, name, count, slug. Optionally filter by `search`."""
    _apply_site(site)
    params = {"per_page": per_page}
    if search:
        params["search"] = search
    tags = _v2("GET", "/tags", params=params)
    return json.dumps([{"id": t["id"], "name": t["name"], "count": t["count"], "slug": t["slug"]} for t in tags],
                      indent=2, ensure_ascii=False)


@mcp.tool()
def create_tag(name: str, description: str = "", site: str = "") -> str:
    """Create a new tag. Returns its id."""
    _require_tier('paid')
    _apply_site(site)
    payload = {"name": name}
    if description:
        payload["description"] = description
    t = _v2("POST", "/tags", payload=payload)
    return json.dumps({"id": t["id"], "name": t["name"], "slug": t["slug"]})


# ===========================================================================
# PAGES
# ===========================================================================
@mcp.tool()
def list_pages(search: str = "", status: str = "publish,draft", per_page: int = 20, site: str = "") -> str:
    """List pages (About, calculators, etc.). Returns id, title, status, link."""
    _apply_site(site)
    params = {"per_page": min(per_page, 50), "status": status, "context": "edit"}
    if search:
        params["search"] = search
    return json.dumps([_slim_post(p) for p in _v2("GET", "/pages", params=params)], indent=2, ensure_ascii=False)


@mcp.tool()
def get_page(page_id: int, site: str = "") -> str:
    """Get one page's full raw HTML content + title, status."""
    _apply_site(site)
    p = _v2("GET", f"/pages/{page_id}", params={"context": "edit"})
    return json.dumps({"id": p["id"], "title": (p.get("title") or {}).get("raw", ""),
                       "status": p.get("status"), "link": p.get("link"),
                       "content": (p.get("content") or {}).get("raw", "")}, indent=2, ensure_ascii=False)


@mcp.tool()
def update_page(page_id: int, title: str = "", content: str = "", status: str = "", site: str = "") -> str:
    """Edit a page by ID. Only non-empty fields change. content replaces whole body (HTML)."""
    _require_tier('paid')
    _apply_site(site)
    payload = {}
    if title:
        payload["title"] = title
    if content:
        payload["content"] = content
    if status:
        payload["status"] = status
    if not payload:
        return "Nothing to update."
    return json.dumps(_slim_post(_v2("POST", f"/pages/{page_id}", payload=payload)), indent=2, ensure_ascii=False)


@mcp.tool()
def create_page(title: str, content: str, status: str = "draft", site: str = "") -> str:
    """Create a new page. status defaults to draft. content is HTML (Gutenberg
    block markup works too).

    DESIGN IT WELL - when building landing/service/about pages, act as a senior
    web designer: a strong hero (headline + subtext + one CTA), clear sections
    with generous vertical spacing, consistent 8px spacing, tasteful typography,
    a small cohesive palette, cards/columns with soft shadow + radius, buttons
    with hover states, SVG icons (not emoji), and a fully responsive mobile-first
    layout. Keep the style consistent and professional - not a plain wall of text."""
    _require_tier('paid')
    _apply_site(site)
    return json.dumps(_slim_post(_v2("POST", "/pages", payload={"title": title, "content": content, "status": status})),
                      indent=2, ensure_ascii=False)


@mcp.tool()
def delete_page(page_id: int, permanent: bool = False, site: str = "") -> str:
    """Delete a PAGE. Default = move to Trash (recoverable). permanent=True = delete
    forever. Use list_pages to find the page ID. (For posts, use delete_post.)"""
    _require_tier('paid')
    _apply_site(site)
    _v2("DELETE", f"/pages/{page_id}", params={"force": "true"} if permanent else None)
    return json.dumps({"id": page_id, "result": "deleted" if permanent else "trashed"})


# ===========================================================================
# COMMENTS
# ===========================================================================
@mcp.tool()
def list_comments(status: str = "hold", per_page: int = 20, site: str = "") -> str:
    """List comments. status = hold (pending), approve, spam, trash, all.
    Returns id, author, content snippet, post id, status."""
    _apply_site(site)
    params = {"per_page": min(per_page, 50), "context": "edit"}
    if status != "all":
        params["status"] = status
    cs = _v2("GET", "/comments", params=params)
    return json.dumps([{"id": c["id"], "author": c.get("author_name"),
                        "post": c.get("post"), "status": c.get("status"),
                        "content": (c.get("content") or {}).get("rendered", "")[:200]} for c in cs],
                      indent=2, ensure_ascii=False)


@mcp.tool()
def moderate_comment(comment_id: int, action: str, site: str = "") -> str:
    """Moderate a comment. action = approve, hold, spam, trash, delete."""
    _require_tier('paid')
    _apply_site(site)
    if action == "delete":
        _v2("DELETE", f"/comments/{comment_id}", params={"force": "true"})
        return json.dumps({"id": comment_id, "result": "deleted"})
    status_map = {"approve": "approved", "hold": "hold", "spam": "spam", "trash": "trash"}
    if action not in status_map:
        return "action must be: approve, hold, spam, trash, or delete"
    c = _v2("POST", f"/comments/{comment_id}", payload={"status": status_map[action]})
    return json.dumps({"id": comment_id, "status": c.get("status")})


# ===========================================================================
# AUTHORS
# ===========================================================================
@mcp.tool()
def list_authors(site: str = "") -> str:
    """List all authors/users (id, name, role). Use the id with set_post_author."""
    _apply_site(site)
    users = _v2("GET", "/users", params={"per_page": 50, "context": "edit"})
    return json.dumps([{"id": u["id"], "name": u.get("name"), "roles": u.get("roles")} for u in users],
                      indent=2, ensure_ascii=False)


@mcp.tool()
def set_post_author(post_id: int, author_id: int, site: str = "") -> str:
    """Set/change the author of a post (use list_authors to get the id).
    Good for E-E-A-T - assign the right expert to each article."""
    _require_tier('paid')
    _apply_site(site)
    p = _v2("POST", f"/posts/{post_id}", payload={"author": author_id})
    return json.dumps({"post_id": post_id, "author": p.get("author")})


# ===========================================================================
# SCHEDULED / FUTURE PUBLISH
# ===========================================================================
@mcp.tool()
def schedule_post(post_id: int, datetime_iso: str, site: str = "") -> str:
    """Schedule a post to auto-publish at a future time. `datetime_iso` must be
    site-local time in ISO format, e.g. '2026-07-15T09:00:00'. Sets status=future."""
    _require_tier('paid')
    _apply_site(site)
    p = _v2("POST", f"/posts/{post_id}", payload={"status": "future", "date": datetime_iso})
    return json.dumps({"post_id": post_id, "status": p.get("status"), "scheduled_for": p.get("date")})


@mcp.tool()
def bulk_schedule_posts(schedule_json: str, site: str = "") -> str:
    """Schedule MANY posts at once. `schedule_json` is a JSON array of
    {"post_id": N, "datetime_iso": "2026-07-15T09:00:00"} (site-local time).
    Sets each to status=future. Returns per-post result."""
    _require_tier('paid')
    _apply_site(site)
    try:
        items = json.loads(schedule_json)
    except Exception:
        return json.dumps({"error": "schedule_json must be a JSON array"})
    out = []
    for it in items if isinstance(items, list) else []:
        pid = it.get("post_id")
        dt = it.get("datetime_iso")
        if not pid or not dt:
            continue
        try:
            p = _v2("POST", f"/posts/{pid}", payload={"status": "future", "date": dt})
            out.append({"post_id": pid, "scheduled_for": p.get("date"), "status": p.get("status")})
        except Exception as e:  # noqa: BLE001
            out.append({"post_id": pid, "error": str(e)[:80]})
    return json.dumps({"scheduled": len(out), "results": out}, indent=2, ensure_ascii=False)


@mcp.tool()
def duplicate_post(post_id: int, new_title: str = "", site: str = "") -> str:
    """Clone a post (great for templates): copies title, content, excerpt,
    categories and tags into a NEW draft. Pass new_title to rename the copy.
    Returns the new post id."""
    _require_tier('paid')
    _apply_site(site)
    src = _v2("GET", f"/posts/{post_id}", params={"context": "edit"})
    payload = {
        "title": new_title or ((src.get("title") or {}).get("raw", "") + " (copy)"),
        "content": (src.get("content") or {}).get("raw", ""),
        "excerpt": (src.get("excerpt") or {}).get("raw", ""),
        "status": "draft",
        "categories": src.get("categories", []),
        "tags": src.get("tags", []),
    }
    new = _v2("POST", "/posts", payload=payload)
    return json.dumps(_slim_post(new), indent=2, ensure_ascii=False)


@mcp.tool()
def bulk_assign_terms(post_ids: str, category_ids: str = "", tag_ids: str = "",
                      replace: bool = False, site: str = "") -> str:
    """Assign categories and/or tags to MANY posts at once. `post_ids`,
    `category_ids`, `tag_ids` are comma-separated id lists. By default terms are
    ADDED; set replace=True to replace existing ones. Returns per-post result."""
    _require_tier('paid')
    _apply_site(site)
    def _ids(s):
        return [int(x) for x in str(s).split(",") if x.strip().isdigit()]
    pids = _ids(post_ids)
    cats = _ids(category_ids)
    tags = _ids(tag_ids)
    out = []
    for pid in pids:
        payload = {}
        if cats or replace:
            if replace:
                payload["categories"] = cats
            else:
                cur = _v2("GET", f"/posts/{pid}").get("categories", [])
                payload["categories"] = list(set(cur) | set(cats))
        if tags or (replace and tag_ids):
            if replace:
                payload["tags"] = tags
            else:
                cur = _v2("GET", f"/posts/{pid}").get("tags", [])
                payload["tags"] = list(set(cur) | set(tags))
        if payload:
            _v2("POST", f"/posts/{pid}", payload=payload)
            out.append({"post_id": pid, "categories": payload.get("categories"), "tags": payload.get("tags")})
    return json.dumps({"updated": len(out), "results": out}, indent=2, ensure_ascii=False)


@mcp.tool()
def list_users(per_page: int = 50, site: str = "") -> str:
    """List site users with id, name, email (if visible), and roles."""
    _apply_site(site)
    users = _v2("GET", "/users", params={"per_page": min(per_page, 100), "context": "edit"})
    return json.dumps([{"id": u.get("id"), "name": u.get("name"),
                        "email": u.get("email"), "roles": u.get("roles"),
                        "slug": u.get("slug")} for u in users], indent=2, ensure_ascii=False)


@mcp.tool()
def create_user(username: str, email: str, password: str, role: str = "author", site: str = "") -> str:
    """Create a new WordPress user. role is one of: subscriber, contributor, author,
    editor, administrator. Returns the new user id."""
    _require_tier('paid')
    _apply_site(site)
    u = _v2("POST", "/users", payload={"username": username, "email": email,
                                       "password": password, "roles": [role]})
    return json.dumps({"id": u.get("id"), "name": u.get("name"), "roles": u.get("roles")})


@mcp.tool()
def change_user_role(user_id: int, role: str, site: str = "") -> str:
    """Change a user's role (subscriber/contributor/author/editor/administrator)."""
    _require_tier('paid')
    _apply_site(site)
    u = _v2("POST", f"/users/{user_id}", payload={"roles": [role]})
    return json.dumps({"id": u.get("id"), "roles": u.get("roles")})


@mcp.tool()
def bulk_generate_meta(limit: int = 30, apply: bool = False, site: str = "") -> str:
    """For posts MISSING an SEO meta description, generate one from the post's
    content (first solid sentences, ~155 chars). apply=False previews; apply=True
    saves via the SEO backend. Pairs well with the SEO plugin. Uses update_post_seo
    under the hood when applying."""
    _require_tier('paid')
    _apply_site(site)
    posts = list(_all_posts(status="publish", limit=limit))
    out = []
    for p in posts:
        pid = p.get("id")
        # skip if it already has a description via our SEO backend
        raw = (p.get("content") or {}).get("raw", "")
        # Use prose-only text so the byline/date/read-time never becomes the meta
        # description (that produced "By David Anderson · … 13 min read" in Google).
        text = _content_text(raw)
        if len(text) < 40:
            continue
        desc = text[:157].rsplit(" ", 1)[0].strip()
        if len(text) > len(desc):
            desc += "…"
        entry = {"post_id": pid, "title": (p.get("title") or {}).get("rendered", ""),
                 "suggested_description": desc}
        if apply:
            try:
                _seo_write(pid, {"meta_description": desc})
                entry["applied"] = True
            except Exception as e:  # noqa: BLE001
                entry["error"] = str(e)[:80]
        out.append(entry)
    return json.dumps({"mode": "APPLIED" if apply else "PREVIEW",
                       "count": len(out), "items": out}, indent=2, ensure_ascii=False)


@mcp.tool()
def update_permalinks(structure: str, site: str = "") -> str:
    """Set the permalink structure (e.g. '/%postname%/', '/%year%/%monthnum%/%postname%/').
    Then flushes rewrite rules. Changing this can affect existing URLs - warn the
    user. Requires wptaskify Studio (uses option write + flush)."""
    _require_tier('paid')
    _apply_site(site)
    g = _studio_guard()
    if g:
        return g
    _request("POST", "/wpps/v1/option", payload={"key": "permalink_structure", "value": structure})
    return json.dumps({"permalink_structure": structure,
                       "note": "Set. If URLs don't update, visit Settings > Permalinks once to flush."})


@mcp.tool()
def bulk_update_category(from_category_id: int, to_category_id: int, site: str = "") -> str:
    """Move ALL posts from one category to another (merge/cleanup). Every post in
    `from_category_id` gets `to_category_id` added and the old one removed. Returns
    how many posts were moved."""
    _require_tier('paid')
    _apply_site(site)
    moved = []
    page = 1
    while True:
        batch = _v2("GET", "/posts", params={"categories": from_category_id, "per_page": 50,
                                             "page": page, "context": "edit", "status": "any"})
        if not batch:
            break
        for p in batch:
            cats = [c for c in p.get("categories", []) if c != from_category_id]
            if to_category_id not in cats:
                cats.append(to_category_id)
            _v2("POST", f"/posts/{p['id']}", payload={"categories": cats})
            moved.append(p["id"])
        if len(batch) < 50:
            break
        page += 1
    return json.dumps({"moved_posts": len(moved), "from": from_category_id,
                       "to": to_category_id}, indent=2, ensure_ascii=False)


@mcp.tool()
def find_and_replace_meta(field: str, find: str, replace: str, limit: int = 300,
                          apply: bool = False, site: str = "") -> str:
    """Find & replace text across an SEO meta field on many posts. `field` is one of:
    meta_title, meta_description, focus_keyword. apply=False previews matches;
    apply=True writes the changes. Great for bulk rebrands/typos in SEO fields."""
    if apply:
        _require_tier('paid')  # preview is free; the bulk WRITE is a paid action
    _apply_site(site)
    if field not in ("meta_title", "meta_description", "focus_keyword"):
        return json.dumps({"error": "field must be meta_title, meta_description, or focus_keyword"})
    out = []
    for p in _all_posts(limit=limit):
        pid = p.get("id")
        cur = _seo_read(pid)
        val = (cur or {}).get(field, "") if isinstance(cur, dict) else ""
        if val and find in val:
            newval = val.replace(find, replace)
            entry = {"post_id": pid, "old": val, "new": newval}
            if apply:
                _seo_write(pid, {field: newval})
                entry["applied"] = True
            out.append(entry)
    return json.dumps({"mode": "APPLIED" if apply else "PREVIEW",
                       "count": len(out), "items": out}, indent=2, ensure_ascii=False)


@mcp.tool()
def delete_unused_media(limit: int = 200, apply: bool = False, site: str = "") -> str:
    """Find media (images) NOT used as any post's featured image and NOT referenced
    in any post body. apply=False previews; apply=True deletes them (frees space).
    Be careful - deletion is permanent. Scans up to `limit` media items."""
    _require_tier('pro')
    _apply_site(site)
    media = _v2("GET", "/media", params={"per_page": min(limit, 100), "context": "edit", "media_type": "image"})
    # Gather all image URLs + featured ids used across posts.
    used_urls, used_ids = set(), set()
    for p in _all_posts(status="publish,draft,pending,private", limit=500):
        raw = (p.get("content") or {}).get("raw", "")
        for u in _re.findall(r'src=["\']([^"\']+)["\']', raw):
            used_urls.add(u.split("?")[0])
        fid = p.get("featured_media")
        if fid:
            used_ids.add(fid)
    unused = []
    for m in media:
        mid = m.get("id")
        src = (m.get("source_url") or "").split("?")[0]
        if mid in used_ids:
            continue
        if src and src in used_urls:
            continue
        entry = {"id": mid, "url": src, "title": (m.get("title") or {}).get("rendered", "")}
        if apply:
            try:
                _v2("DELETE", f"/media/{mid}", params={"force": True})
                entry["deleted"] = True
            except Exception as e:  # noqa: BLE001
                entry["error"] = str(e)[:60]
        unused.append(entry)
    return json.dumps({"mode": "DELETED" if apply else "PREVIEW",
                       "unused_count": len(unused), "items": unused}, indent=2, ensure_ascii=False)


@mcp.tool()
def generate_sitemap(site: str = "") -> str:
    """Return the site's XML sitemap URL (wptaskify serves one automatically).
    NOTE: Google (June 2023) and Bing both RETIRED the old sitemap-ping URLs, so
    there is no reliable ping endpoint anymore - reliable resubmission is done via
    Google Search Console (Site Kit). This confirms the sitemap and, if the old
    ping endpoints happen to still respond, reports that too."""
    _require_tier('paid')
    _apply_site(site)
    site = _cfg()["site_url"].rstrip("/")
    sitemap_url = site + "/wppseo-sitemap.xml"
    # Confirm the sitemap itself is actually reachable (this is the useful check).
    reachable, status = False, None
    try:
        req = urllib.request.Request(sitemap_url, method="GET")
        with urllib.request.urlopen(req, timeout=15) as r:
            status = r.status
            reachable = 200 <= r.status < 300
    except urllib.error.HTTPError as e:
        status = e.code
    except Exception as e:
        status = f"failed: {type(e).__name__}"
    return json.dumps({
        "sitemap_url": sitemap_url,
        "sitemap_reachable": reachable,
        "http_status": status,
        "ping": "Google & Bing retired their sitemap-ping endpoints (2023); "
                "there is no automatic ping anymore.",
        "how_to_resubmit": "Open Google Search Console (Site Kit) > Sitemaps and "
                           "submit /wppseo-sitemap.xml once - Google then re-crawls "
                           "it automatically whenever it changes.",
    }, indent=2, ensure_ascii=False)


# ===========================================================================
# REVISIONS / UNDO
# ===========================================================================
@mcp.tool()
def list_revisions(post_id: int, site: str = "") -> str:
    """List a post's saved revisions (id, date, snippet). Use restore_revision to
    roll back if an edit went wrong."""
    _apply_site(site)
    revs = _v2("GET", f"/posts/{post_id}/revisions", params={"per_page": 20})
    return json.dumps([{"revision_id": r["id"], "date": r.get("date"),
                        "title": (r.get("title") or {}).get("rendered", ""),
                        "excerpt": (r.get("content") or {}).get("rendered", "")[:120]} for r in revs],
                      indent=2, ensure_ascii=False)


@mcp.tool()
def restore_revision(post_id: int, revision_id: int, site: str = "") -> str:
    """Roll a post back to a previous revision (undo). Fetches that revision's
    content/title and writes it back onto the live post."""
    _require_tier('paid')
    _apply_site(site)
    rev = _v2("GET", f"/posts/{post_id}/revisions/{revision_id}", params={"context": "edit"})
    payload = {
        "title": (rev.get("title") or {}).get("raw", ""),
        "content": (rev.get("content") or {}).get("raw", ""),
    }
    p = _v2("POST", f"/posts/{post_id}", payload=payload)
    return json.dumps({"post_id": post_id, "restored_from_revision": revision_id, "status": p.get("status")})


# ===========================================================================
# SEARCH
# ===========================================================================
@mcp.tool()
def search_site(query: str, per_page: int = 15, site: str = "") -> str:
    """Search across all posts & pages by keyword. Returns id, title, url, type.
    Great for finding internal-linking targets before editing an article."""
    _apply_site(site)
    results = _v2("GET", "/search", params={"search": query, "per_page": min(per_page, 30)})
    return json.dumps([{"id": r.get("id"), "title": r.get("title"),
                        "url": r.get("url"), "type": r.get("subtype") or r.get("type")} for r in results],
                      indent=2, ensure_ascii=False)


# ===========================================================================
# NAVIGATION MENUS
# ===========================================================================
@mcp.tool()
def list_menus(site: str = "") -> str:
    """List navigation menus (id, name) and their locations."""
    _apply_site(site)
    menus = _v2("GET", "/menus", params={"per_page": 50, "context": "edit"})
    return json.dumps([{"id": m["id"], "name": m.get("name"), "slug": m.get("slug"),
                        "locations": m.get("locations")} for m in menus], indent=2, ensure_ascii=False)


@mcp.tool()
def list_menu_items(menu_id: int, site: str = "") -> str:
    """List items in a menu (id, title, url, order, parent). Use to see/plan menu edits."""
    _apply_site(site)
    items = _v2("GET", "/menu-items", params={"menus": menu_id, "per_page": 100, "context": "edit"})
    return json.dumps([{"id": i["id"], "title": (i.get("title") or {}).get("rendered", ""),
                        "url": i.get("url"), "order": i.get("menu_order"), "parent": i.get("parent")}
                       for i in items], indent=2, ensure_ascii=False)


@mcp.tool()
def add_menu_item(menu_id: int, title: str, url: str, parent_id: int = 0, site: str = "") -> str:
    """Add a custom link item to a navigation menu. Returns the new item id."""
    _require_tier('paid')
    _apply_site(site)
    payload = {"menus": menu_id, "title": title, "url": url, "type": "custom", "status": "publish"}
    if parent_id:
        payload["parent"] = parent_id
    i = _v2("POST", "/menu-items", payload=payload)
    return json.dumps({"id": i["id"], "title": (i.get("title") or {}).get("rendered", ""), "url": i.get("url")})


@mcp.tool()
def delete_menu_item(item_id: int, site: str = "") -> str:
    """Remove an item from a navigation menu."""
    _require_tier('paid')
    _apply_site(site)
    _v2("DELETE", f"/menu-items/{item_id}", params={"force": "true"})
    return json.dumps({"id": item_id, "result": "removed"})


# ===========================================================================
# SITE SETTINGS
# ===========================================================================
@mcp.tool()
def get_settings(site: str = "") -> str:
    """Get site settings: title, tagline (description), timezone, date format, etc."""
    _apply_site(site)
    s = _v2("GET", "/settings")
    return json.dumps(s, indent=2, ensure_ascii=False)


@mcp.tool()
def update_settings(title: str = "", tagline: str = "", timezone: str = "", site: str = "") -> str:
    """Update site settings. Only non-empty fields change. tagline = site description."""
    _require_tier('paid')
    _apply_site(site)
    payload = {}
    if title:
        payload["title"] = title
    if tagline:
        payload["description"] = tagline
    if timezone:
        payload["timezone_string"] = timezone
    if not payload:
        return "Nothing to update."
    s = _v2("POST", "/settings", payload=payload)
    return json.dumps({"title": s.get("title"), "tagline": s.get("description"),
                       "timezone": s.get("timezone_string")}, ensure_ascii=False)


# ===========================================================================
# SEO / CONTENT POWER TOOLS
# ===========================================================================
_HREF_RE = _re.compile(r'href=["\']([^"\']+)["\']', _re.IGNORECASE)
_IMG_RE = _re.compile(r'<img\b[^>]*>', _re.IGNORECASE)
_TAG_RE = _re.compile(r'<[^>]+>')


def _all_posts(status="publish,draft", limit=300):
    """Generator over posts (edit context) up to limit."""
    page, n = 1, 0
    while n < limit:
        batch = _v2("GET", "/posts", params={"per_page": 50, "page": page, "status": status, "context": "edit"})
        if not batch:
            break
        for p in batch:
            yield p
            n += 1
            if n >= limit:
                return
        if len(batch) < 50:
            break
        page += 1


@mcp.tool()
def check_broken_links(post_id: int = 0, limit: int = 50, site: str = "") -> str:
    """Check links inside a post (or scan many posts if post_id=0) and report any
    that return 404 / errors. Checks both internal and external links. For a full
    scan, raise `limit` carefully (each link is fetched). Returns broken links per post."""
    _apply_site(site)
    posts = [_v2("GET", f"/posts/{post_id}", params={"context": "edit"})] if post_id else list(_all_posts(limit=limit))
    report = []
    checked_cache = {}
    # A real browser UA - many sites 403 unknown bots, which we must NOT report as
    # broken (the link is alive for a human). Codes that mean "blocked, not dead".
    _BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
    _BLOCKED_CODES = {401, 403, 405, 406, 429, 503}

    def _probe(url):
        """Return an HTTP status. Try HEAD, then GET (some servers reject HEAD)."""
        for method in ("HEAD", "GET"):
            try:
                req = urllib.request.Request(
                    url, method=method,
                    headers={"User-Agent": _BROWSER_UA, "Accept": "*/*"})
                with urllib.request.urlopen(req, timeout=15) as r:
                    return r.status
            except urllib.error.HTTPError as e:
                # 405/403 on HEAD? retry with GET before trusting it.
                if method == "HEAD" and e.code in (403, 405, 406):
                    continue
                return e.code
            except Exception:
                if method == "HEAD":
                    continue  # HEAD failed outright -> try GET
                return 0  # connection failed / timeout on GET too
        return 0

    for p in posts:
        raw = (p.get("content") or {}).get("raw", "")
        links = set(_HREF_RE.findall(raw))
        bad = []
        blocked = []
        for link in links:
            if link.startswith("#") or link.startswith("mailto:") or link.startswith("tel:"):
                continue
            url = link
            if url.startswith("/"):
                url = _cfg()["site_url"] + url
            if not url.startswith("http"):
                continue
            if url in checked_cache:
                code = checked_cache[url]
            else:
                code = _probe(url)
                checked_cache[url] = code
            if code in _BLOCKED_CODES:
                # Alive but bot-blocked - flag as "verify manually", NOT broken.
                blocked.append({"url": link, "status": code,
                                "note": "blocked to bots (likely fine in a browser) - verify manually"})
            elif code == 0 or code >= 400:
                bad.append({"url": link, "status": code or "no-response"})
        if bad or blocked:
            entry = {"post_id": p["id"], "title": (p.get("title") or {}).get("raw", "")}
            if bad:
                entry["broken"] = bad
            if blocked:
                entry["needs_manual_check"] = blocked
            report.append(entry)
    return json.dumps({
        "posts_checked": len(posts),
        "posts_with_broken_links": sum(1 for r in report if r.get("broken")),
        "note": "403/401/429/503 links are marked 'needs_manual_check' (bot-blocked, "
                "usually alive in a browser), NOT counted as broken.",
        "report": report,
    }, indent=2, ensure_ascii=False)


@mcp.tool()
def suggest_internal_links(topic: str, exclude_post_id: int = 0, max_suggestions: int = 8, site: str = "") -> str:
    """Given a topic/keyword (or a draft article's subject), find the most relevant
    EXISTING posts to link to internally. Returns title + url + why (which topic
    words matched). Results are RANKED by how many topic keywords each title
    shares, so the most on-topic targets come first. Use this before
    writing/editing so you can insert internal links to these targets."""
    _apply_site(site)
    stop = {"the", "a", "an", "is", "are", "of", "for", "to", "and", "your", "you",
            "in", "on", "with", "best", "vs", "what", "how", "much", "it", "or",
            "at", "by", "from", "into", "review", "guide", "top", "systems", "system"}
    def _keywords(s):
        return {w.lower() for w in _re.sub(r"[^a-zA-Z ]", " ", s or "").split()
                if w.lower() not in stop and len(w) > 3}
    topic_kw = _keywords(topic)
    # Search per keyword (not one phrase) so we don't miss on-topic posts, then
    # RANK by shared-keyword count. Old version trusted raw /search order, which
    # buried the most relevant post below loosely-matching ones.
    seen = {}
    queries = sorted(topic_kw, key=len, reverse=True)[:6] or [topic]
    for q in queries:
        for r in _v2("GET", "/search", params={"search": q, "per_page": 20}):
            rid = r.get("id")
            if rid == exclude_post_id:
                continue
            if (r.get("subtype") or r.get("type")) not in ("post", "page"):
                continue
            seen.setdefault(rid, r)
    scored = []
    for rid, r in seen.items():
        shared = topic_kw & _keywords(r.get("title"))
        if shared:  # require an on-topic overlap
            scored.append((len(shared), sorted(shared), r))
    scored.sort(key=lambda t: t[0], reverse=True)
    out = [{"id": r.get("id"), "title": r.get("title"), "url": r.get("url"),
            "type": r.get("subtype") or r.get("type"),
            "why": "matches topic word(s): " + ", ".join(shared)}
           for _n, shared, r in scored[:max_suggestions]]
    return json.dumps({"topic": topic, "topic_keywords": sorted(topic_kw),
                       "suggested_internal_links": out}, indent=2, ensure_ascii=False)


# Filler / clickbait / grammatical words that must NEVER form an anchor on their
# own. A phrase made only of these (e.g. "stand out", "feel like", "keep them")
# is a bad SEO anchor and topically meaningless - we reject such phrases entirely.
_LINK_STOPWORDS = {
    # articles / conjunctions / prepositions / pronouns
    "the", "a", "an", "and", "or", "for", "to", "of", "in", "on", "with", "you",
    "your", "yours", "youll", "youre", "we", "our", "us", "i", "my", "me", "they",
    "them", "their", "he", "she", "his", "her", "it", "its", "this", "that",
    "these", "those", "here", "there", "into", "from", "by", "at", "as", "up",
    "out", "off", "over", "under", "about", "than", "then", "so", "such", "no",
    "not", "yes", "if", "but", "just", "only", "own", "same", "too",
    # verbs / helpers commonly left over from titles
    "is", "are", "was", "were", "be", "been", "being", "do", "does", "did",
    "have", "has", "had", "will", "would", "can", "could", "should", "shall",
    "may", "might", "must", "make", "makes", "made", "making", "get", "gets",
    "got", "keep", "keeps", "kept", "let", "lets", "stand", "stands", "look",
    "looks", "feel", "feels", "want", "need", "try", "trying", "use", "using",
    "take", "takes", "give", "go", "goes", "come", "know", "see", "find", "found",
    # clickbait / filler adjectives + nouns
    "wish", "tried", "sooner", "best", "top", "ideas", "idea", "guide", "guides",
    "tips", "tip", "ways", "way", "things", "thing", "amazing", "beautiful",
    "breathtaking", "stunning", "gorgeous", "easy", "simple", "ultimate",
    "complete", "new", "ever", "really", "very", "more", "most", "each", "every",
    "some", "any", "all", "how", "what", "why", "when", "where", "who", "which",
    "now", "today", "like", "right", "left", "great", "good", "perfect", "cute",
    "lovely", "pretty", "cool", "awesome", "creative", "fun", "unique", "quick",
    "step", "steps", "diy", "you'll", "you're",
}


def _content_words(text: str):
    """Lowercase 'content' words from text (drops stopwords, numbers, tiny words)."""
    words = _re.findall(r"[A-Za-z][A-Za-z']+", text)
    return [w.lower() for w in words
            if w.lower() not in _LINK_STOPWORDS and len(w) > 2]


def _keyword_phrases(title: str, min_words: int = 2, max_words: int = 4):
    """Turn a long/clickbait post TITLE into a few STRONG, SEO-worthy anchor phrases.

    e.g. '34 Breathtaking Watercolor Magnolia Drawing Ideas You'll Wish You Tried
    Sooner' -> ['watercolor magnolia drawing', 'magnolia drawing', ...].

    A phrase is only emitted if it survives the stopword filter AND still contains
    at least one real 'topic' word - so filler like 'stand out' or 'feel like'
    (which are ALL stopwords) never becomes an anchor. Longest/most-specific first."""
    words = _re.findall(r"[A-Za-z][A-Za-z']+", title)
    # Keep only content words (drops numbers, filler, tiny words).
    kept = [w for w in words if w.lower() not in _LINK_STOPWORDS and len(w) > 2]
    phrases = []
    seen = set()
    n = len(kept)
    for size in range(min(max_words, n), min_words - 1, -1):
        for i in range(0, n - size + 1):
            window = kept[i:i + size]
            phrase = " ".join(window)
            key = phrase.lower()
            # Require the phrase to be substantive: >=6 chars and at least one
            # word longer than 3 letters (avoids junk like "art in").
            if key in seen or len(phrase) < 6:
                continue
            if not any(len(w) >= 4 for w in window):
                continue
            seen.add(key)
            phrases.append(phrase)
    return phrases


@mcp.tool()
def bulk_internal_links(max_per_post: int = 3, min_title_words: int = 2,
                        limit: int = 300, dry_run: bool = False,
                        match_keywords: bool = True, site: str = "") -> str:
    """BULK internal linking across the WHOLE site in ONE call - no need to go
    post-by-post. For every published post it finds natural anchor phrases that
    point to OTHER posts and turns the first mention of each into an internal link.

    By default (`match_keywords=True`) it does NOT require the whole (often long,
    clickbait) title to appear verbatim. Instead it extracts short KEYWORD PHRASES
    from each post's title - e.g. 'watercolor magnolia drawing' out of '34
    Breathtaking Watercolor Magnolia Drawing Ideas You'll Wish You Tried Sooner' -
    and links those where they appear in another post's body. Set
    `match_keywords=False` to require an exact full-title match instead.

    Quality is preserved:
      - Whole-word, plain-text matches only (case-insensitive); anchors read naturally.
      - Never links text already inside an <a> tag (no double-linking).
      - At most ONE link per target per post, and at most `max_per_post` new links
        per post (avoids over-optimization / spammy linking).
      - Same target URL is never linked twice in the same post.
      - Preserves each post's JSON-LD schema block.

    Set `dry_run=True` to PREVIEW what would be linked without saving. Returns a
    per-post summary of links added (anchor text + target). Run once and it links
    the whole site; re-running only adds genuinely new links."""
    _require_tier('paid')
    _apply_site(site)
    # 1. Build targets: each = (id, title, url, [anchor phrases], {topic words}).
    posts = list(_all_posts(status="publish", limit=limit))
    targets = []
    for p in posts:
        title = (p.get("title") or {}).get("raw") or (p.get("title") or {}).get("rendered") or ""
        title = _re.sub(r"\s+", " ", title).strip()
        url = p.get("link") or ""
        if not (title and url and len(title.split()) >= min_title_words):
            continue
        if match_keywords:
            phrases = _keyword_phrases(title, min_words=min_title_words)
            # NO fallback to the full clickbait title - if a post has no strong
            # keyword phrase, skip it as a target rather than link junk anchors.
            if not phrases:
                continue
        else:
            phrases = [title]
        topic_words = set(_content_words(title))
        targets.append((p.get("id"), title, url, phrases, topic_words))
    # Try more specific (longer) phrases first, across all targets.
    targets.sort(key=lambda t: max((len(ph) for ph in t[3]), default=0), reverse=True)

    summary = []
    total_links = 0
    for p in posts:
        pid = p.get("id")
        raw = (p.get("content") or {}).get("raw", "")
        if not raw:
            continue
        # Protect existing schema + existing anchors from being touched.
        schema_blocks = _SCHEMA_RE.findall(raw)
        body = _SCHEMA_RE.sub("", raw)

        # URLs already linked in this post - so we NEVER add a link that already
        # exists (each target link appears at most once per post).
        existing_hrefs = set(_HREF_RE.findall(raw))

        # Walk matches and skip any that sit inside an anchor tag.
        def _inside_anchor(pos, text):
            before = text.rfind("<a", 0, pos)
            if before == -1:
                return False
            close = text.find("</a>", before)
            return close != -1 and close > pos

        # Topic words of THIS post - a link is only allowed to a target that
        # shares real topic vocabulary (prevents Magnolia->Duck style junk).
        src_title = (p.get("title") or {}).get("raw") or (p.get("title") or {}).get("rendered") or ""
        src_topics = set(_content_words(src_title))

        added = []
        used_targets = set()
        for tid, ttitle, turl, phrases, topic_words in targets:
            if tid == pid or tid in used_targets:
                continue
            if len(added) >= max_per_post:
                break
            # Skip if this exact target URL is already linked somewhere in the post.
            if turl in existing_hrefs or turl.rstrip("/") in {h.rstrip("/") for h in existing_hrefs}:
                continue
            # TOPICAL GATE: require at least one shared topic word between the two
            # posts' titles, so links stay relevant (magnolia<->magnolia, not
            # magnolia<->duck).
            if not (src_topics & topic_words):
                continue
            # Try each candidate phrase (longest first); link the first whole-word,
            # plain-text match that is NOT already inside an <a>...</a>.
            m = None
            for phrase in phrases:
                pattern = _re.compile(
                    r"(?<![>\w])(" + _re.escape(phrase) + r")(?![\w<])",
                    _re.IGNORECASE)
                for cand in pattern.finditer(body):
                    if not _inside_anchor(cand.start(), body):
                        m = cand
                        break
                if m:
                    break
            if not m:
                continue
            anchor = f'<a href="{turl}">{m.group(1)}</a>'
            body = body[:m.start()] + anchor + body[m.end():]
            added.append({"target_id": tid, "target_title": ttitle,
                          "anchor_text": m.group(1)})
            used_targets.add(tid)

        if not added:
            continue
        total_links += len(added)
        summary.append({"post_id": pid,
                        "post_title": (p.get("title") or {}).get("rendered", ""),
                        "links_added": len(added), "links": added})

        if not dry_run:
            new_body = body.rstrip()
            if schema_blocks:
                new_body += "\n\n" + "\n\n".join(schema_blocks)
            _v2("POST", f"/posts/{pid}", payload={"content": new_body})

    return json.dumps({
        "mode": "dry_run (nothing saved)" if dry_run else "applied",
        "posts_scanned": len(posts),
        "posts_updated": len(summary),
        "total_links_added": total_links,
        "details": summary,
    }, indent=2, ensure_ascii=False)


def _build_link_plan(max_per_post=3, min_title_words=2, limit=300, match_keywords=True):
    """Core planner: scan the whole site and decide every internal link WITHOUT
    saving anything. Returns a list of edit items, one per post that needs links:
        {post_id, post_title, links: [{target_id, target_url, anchor_text}]}
    Same quality rules as bulk_internal_links (keyword anchors, topical gate,
    no double-linking, one link per target, max_per_post cap)."""
    posts = list(_all_posts(status="publish", limit=limit))

    # Document frequency of each title topic word across the site. Words that
    # appear in MANY posts (e.g. 'drawing', 'watercolor' on an art blog) are
    # niche-wide categories, NOT distinguishing topics - we ignore them in the
    # relevance gate so only SPECIFIC shared words (magnolia, rose) count.
    from collections import Counter
    df = Counter()
    post_topic_words = {}
    for p in posts:
        t = (p.get("title") or {}).get("raw") or (p.get("title") or {}).get("rendered") or ""
        tw = set(_content_words(t))
        post_topic_words[p.get("id")] = tw
        for w in tw:
            df[w] += 1
    n_posts = max(1, len(posts))
    # A word is niche-wide "common" if it appears in many posts. Use BOTH an
    # absolute floor (>=5 posts) and a ratio (>20%), so it works on small AND
    # large sites: on a 160-post art blog 'drawing' hits the ratio; on a tiny
    # test set the absolute floor still won't fire on a genuinely specific word.
    common_words = {w for w, c in df.items()
                    if c >= 5 or c > 0.20 * n_posts}

    def _specific(words):
        return {w for w in words if w not in common_words}

    targets = []
    for p in posts:
        title = (p.get("title") or {}).get("raw") or (p.get("title") or {}).get("rendered") or ""
        title = _re.sub(r"\s+", " ", title).strip()
        url = p.get("link") or ""
        if not (title and url and len(title.split()) >= min_title_words):
            continue
        if match_keywords:
            phrases = _keyword_phrases(title, min_words=min_title_words)
            if not phrases:
                continue
        else:
            phrases = [title]
        # Gate uses SPECIFIC topic words only (drop niche-wide common words).
        targets.append((p.get("id"), title, url, phrases,
                        _specific(post_topic_words.get(p.get("id"), set()))))
    targets.sort(key=lambda t: max((len(ph) for ph in t[3]), default=0), reverse=True)

    def _inside_anchor(pos, text):
        before = text.rfind("<a", 0, pos)
        if before == -1:
            return False
        close = text.find("</a>", before)
        return close != -1 and close > pos

    plan = []
    for p in posts:
        pid = p.get("id")
        raw = (p.get("content") or {}).get("raw", "")
        if not raw:
            continue
        body = _SCHEMA_RE.sub("", raw)
        existing_hrefs = set(_HREF_RE.findall(raw))
        # Relevance gate uses the source post's SPECIFIC words from BOTH its title
        # and its body text (drop niche-wide common words). A link to a target is
        # allowed only if the source genuinely talks about that specific topic -
        # so magnolia links to tulip only if 'tulip' actually appears here.
        _body_text = _TAG_RE.sub(" ", _SCHEMA_RE.sub(" ", raw))
        src_topics = _specific(post_topic_words.get(pid, set()) | set(_content_words(_body_text)))

        # Work on a scratch copy so overlapping matches don't collide within a post.
        scratch = body
        picks, used = [], set()
        for tid, ttitle, turl, phrases, topic_words in targets:
            if tid == pid or tid in used or len(picks) >= max_per_post:
                if len(picks) >= max_per_post:
                    break
                continue
            if turl in existing_hrefs or turl.rstrip("/") in {h.rstrip("/") for h in existing_hrefs}:
                continue
            if not (src_topics & topic_words):
                continue
            m = None
            for phrase in phrases:
                pat = _re.compile(r"(?<![>\w])(" + _re.escape(phrase) + r")(?![\w<])", _re.IGNORECASE)
                for cand in pat.finditer(scratch):
                    if not _inside_anchor(cand.start(), scratch):
                        m = cand
                        break
                if m:
                    break
            if not m:
                continue
            anchor = f'<a href="{turl}">{m.group(1)}</a>'
            scratch = scratch[:m.start()] + anchor + scratch[m.end():]
            picks.append({"target_id": tid, "target_url": turl, "anchor_text": m.group(1)})
            used.add(tid)
        if picks:
            plan.append({"post_id": pid,
                         "post_title": (p.get("title") or {}).get("rendered", ""),
                         "links": picks})
    return plan


@mcp.tool()
def plan_internal_links(max_per_post: int = 3, min_title_words: int = 2,
                        limit: int = 300, site: str = "") -> str:
    """STEP 1 of bulk internal linking: scan the WHOLE site ONCE and produce a
    COMPLETE plan of every internal link to add - WITHOUT changing anything.

    Use this first, show the user the summary, then feed the returned `plan` to
    `apply_internal_links_plan` in batches so you never have to re-scan or ask
    'continue?' after every post. The plan uses keyword-rich, topically-relevant
    anchors (filler like 'stand out' is rejected; unrelated cross-links are gated).

    Returns: {total_posts, total_links, plan: [{post_id, post_title, links:[...]}]}.
    Pass the ENTIRE `plan` array back to apply_internal_links_plan."""
    _apply_site(site)
    plan = _build_link_plan(max_per_post, min_title_words, limit)
    return json.dumps({
        "total_posts": len(plan),
        "total_links": sum(len(it["links"]) for it in plan),
        "note": "Feed this plan to apply_internal_links_plan(plan_json, batch_size) "
                "to execute it batch by batch.",
        "plan": plan,
    }, indent=2, ensure_ascii=False)


@mcp.tool()
def apply_internal_links_plan(plan_json: str, batch_size: int = 25,
                              start_index: int = 0, site: str = "") -> str:
    """STEP 2 of bulk internal linking: EXECUTE a plan from `plan_internal_links`,
    one BATCH at a time - no re-scanning, no per-post confirmation.

    `plan_json`: the JSON string returned by plan_internal_links (either the whole
       object or just its `plan` array).
    `batch_size`: how many posts to update in this call (default 25).
    `start_index`: index in the plan to start from (use the `next_index` this tool
       returns to continue the next batch).

    Each targeted anchor phrase is re-located in the LIVE post body at apply time
    (so it stays correct) and linked; JSON-LD schema is preserved. Returns
    {updated, links_added, next_index, done} - keep calling with next_index until
    done=true to finish the whole site without stopping."""
    _require_tier('paid')
    _apply_site(site)
    try:
        data = json.loads(plan_json)
    except Exception:
        return json.dumps({"error": "plan_json is not valid JSON"})
    plan = data.get("plan", data) if isinstance(data, dict) else data
    if not isinstance(plan, list):
        return json.dumps({"error": "plan must be a list of {post_id, links[...]}"})

    batch = plan[start_index:start_index + batch_size]
    updated, links_added, details = 0, 0, []
    for item in batch:
        pid = item.get("post_id")
        links = item.get("links", [])
        if not pid or not links:
            continue
        p = _v2("GET", f"/posts/{pid}", params={"context": "edit"})
        raw = (p.get("content") or {}).get("raw", "")
        if not raw:
            continue
        schema_blocks = _SCHEMA_RE.findall(raw)
        body = _SCHEMA_RE.sub("", raw)

        def _inside_anchor(pos, text):
            before = text.rfind("<a", 0, pos)
            if before == -1:
                return False
            close = text.find("</a>", before)
            return close != -1 and close > pos

        existing_hrefs = set(_HREF_RE.findall(raw))
        done_here = []
        for lk in links:
            turl = lk.get("target_url", "")
            anchor_text = lk.get("anchor_text", "")
            if not turl or not anchor_text:
                continue
            if turl in existing_hrefs or turl.rstrip("/") in {h.rstrip("/") for h in existing_hrefs}:
                continue
            pat = _re.compile(r"(?<![>\w])(" + _re.escape(anchor_text) + r")(?![\w<])", _re.IGNORECASE)
            m = None
            for cand in pat.finditer(body):
                if not _inside_anchor(cand.start(), body):
                    m = cand
                    break
            if not m:
                continue
            body = body[:m.start()] + f'<a href="{turl}">{m.group(1)}</a>' + body[m.end():]
            existing_hrefs.add(turl)
            done_here.append({"anchor_text": m.group(1), "target_url": turl})

        if not done_here:
            continue
        new_body = body.rstrip()
        if schema_blocks:
            new_body += "\n\n" + "\n\n".join(schema_blocks)
        _v2("POST", f"/posts/{pid}", payload={"content": new_body})
        updated += 1
        links_added += len(done_here)
        details.append({"post_id": pid, "links_added": len(done_here), "links": done_here})

    next_index = start_index + batch_size
    done = next_index >= len(plan)
    return json.dumps({
        "updated": updated,
        "links_added": links_added,
        "processed_range": [start_index, min(next_index, len(plan))],
        "total_in_plan": len(plan),
        "next_index": None if done else next_index,
        "done": done,
        "details": details,
    }, indent=2, ensure_ascii=False)


@mcp.tool()
def find_thin_content(min_words: int = 600, limit: int = 300, site: str = "") -> str:
    """Scan posts and flag THIN content (fewer than `min_words` words of visible
    text, schema/HTML stripped). Thin pages hurt SEO. Returns id, title, word_count,
    url sorted shortest first."""
    _apply_site(site)
    flagged = []
    for p in _all_posts(status="publish", limit=limit):
        raw = (p.get("content") or {}).get("raw", "")
        # strip schema scripts + html tags
        text = _SCHEMA_RE.sub(" ", raw)
        text = _TAG_RE.sub(" ", text)
        words = len(text.split())
        if words < min_words:
            flagged.append({"id": p["id"], "title": (p.get("title") or {}).get("raw", ""),
                            "word_count": words, "link": p.get("link")})
    flagged.sort(key=lambda x: x["word_count"])
    return json.dumps({"min_words": min_words, "thin_posts": len(flagged), "posts": flagged},
                      indent=2, ensure_ascii=False)


@mcp.tool()
def find_duplicate_titles(limit: int = 300, site: str = "") -> str:
    """Find posts with identical or near-identical titles (possible duplicate/competing
    content). Returns groups of posts sharing a title."""
    _apply_site(site)
    seen = {}
    for p in _all_posts(limit=limit):
        title = (p.get("title") or {}).get("raw", "").strip().lower()
        seen.setdefault(title, []).append({"id": p["id"], "link": p.get("link")})
    dups = {t: v for t, v in seen.items() if len(v) > 1}
    return json.dumps({"duplicate_groups": len(dups), "groups": dups}, indent=2, ensure_ascii=False)


@mcp.tool()
def fix_missing_alt_text(limit: int = 100, apply: bool = False, site: str = "") -> str:
    """Find media items with empty alt text. With apply=False (default) just reports
    them. With apply=True, sets alt text from each image's title (cleaned). Good for
    accessibility + image SEO."""
    _require_tier('paid')
    _apply_site(site)
    items = _v2("GET", "/media", params={"per_page": min(limit, 100), "context": "edit", "media_type": "image"})
    fixed, missing = [], []
    for m in items:
        alt = (m.get("alt_text") or "").strip()
        if not alt:
            title = (m.get("title") or {}).get("rendered", "")
            clean = _re.sub(r"[-_]+", " ", title).strip().title()
            entry = {"id": m["id"], "title": title, "suggested_alt": clean}
            if apply and clean:
                _v2("POST", f"/media/{m['id']}", payload={"alt_text": clean})
                entry["applied"] = True
                fixed.append(entry)
            else:
                missing.append(entry)
    return json.dumps({"mode": "APPLIED" if apply else "REPORT", "images_scanned": len(items),
                       "fixed": fixed, "missing_alt": missing}, indent=2, ensure_ascii=False)


def _gemini_describe_image(image_url: str) -> str:
    """Ask Gemini (vision) for a short, descriptive alt text for an image URL."""
    cfg = _cfg()
    api_key = cfg.get("gemini_api_key", "")
    if not api_key:
        return ""
    try:
        with urllib.request.urlopen(image_url, timeout=60) as r:
            img = r.read()
            mime = r.headers.get("Content-Type", "image/jpeg")
    except Exception:
        return ""
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"gemini-flash-latest:generateContent?key={api_key}")
    payload = {
        "contents": [{"parts": [
            {"text": "Write a concise, descriptive alt text (max 120 chars, no "
                     "quotes, no 'image of') for this image, good for SEO and "
                     "accessibility. Return ONLY the alt text."},
            {"inline_data": {"mime_type": mime, "data": base64.b64encode(img).decode()}},
        ]}]
    }
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            resp = json.load(r)
        for cand in resp.get("candidates", []):
            for part in (cand.get("content") or {}).get("parts", []):
                if part.get("text"):
                    return part["text"].strip().strip('"')[:150]
    except Exception:
        return ""
    return ""


@mcp.tool()
def generate_alt_text_ai(limit: int = 30, apply: bool = False, site: str = "") -> str:
    """AI alt-text generator: for images with EMPTY alt text, use Gemini vision to
    look at each image and write a proper descriptive alt text (better than the
    title-based fix_missing_alt_text). apply=False previews; apply=True saves them.
    Needs a Gemini key. Good for accessibility + image SEO."""
    _require_tier('paid')
    _apply_site(site)
    items = _v2("GET", "/media", params={"per_page": min(limit, 50), "context": "edit", "media_type": "image"})
    out = []
    for m in items:
        if (m.get("alt_text") or "").strip():
            continue
        src = m.get("source_url")
        if not src:
            continue
        alt = _gemini_describe_image(src)
        if not alt:
            continue
        entry = {"id": m["id"], "url": src, "suggested_alt": alt}
        if apply:
            _v2("POST", f"/media/{m['id']}", payload={"alt_text": alt})
            entry["applied"] = True
        out.append(entry)
    return json.dumps({"mode": "APPLIED" if apply else "PREVIEW",
                       "count": len(out), "items": out}, indent=2, ensure_ascii=False)


@mcp.tool()
def validate_schema(post_id: int = 0, limit: int = 100, site: str = "") -> str:
    """Validate the JSON-LD structured data (schema) in a post - or scan many posts
    if post_id=0. Checks each <script type="application/ld+json"> block parses as
    valid JSON and has @context and @type. Reports posts with missing or broken
    schema. Good for rich-results health."""
    _apply_site(site)
    posts = [_v2("GET", f"/posts/{post_id}", params={"context": "edit"})] if post_id else list(_all_posts(limit=limit))
    report = []
    for p in posts:
        raw = (p.get("content") or {}).get("raw", "")
        blocks = _SCHEMA_RE.findall(raw)
        issues = []
        if not blocks:
            issues.append("no JSON-LD schema found")
        for i, blk in enumerate(blocks):
            inner = _re.sub(r"(?is)<script[^>]*>|</script>", "", blk).strip()
            try:
                data = json.loads(inner)
                nodes = data if isinstance(data, list) else [data]
                for node in nodes:
                    if not isinstance(node, dict):
                        issues.append(f"block {i+1}: not an object")
                        continue
                    # An @graph wrapper is the standard Yoast/RankMath shape: the
                    # container carries @context and the real entities (each with
                    # its own @type) live inside @graph[]. Validate those, not the
                    # wrapper - else valid @graph schema was wrongly flagged
                    # "missing @type".
                    if isinstance(node.get("@graph"), list):
                        if "@context" not in node:
                            issues.append(f"block {i+1}: missing @context")
                        graph = node["@graph"]
                        if not graph:
                            issues.append(f"block {i+1}: @graph is empty")
                        for j, g in enumerate(graph):
                            if not isinstance(g, dict):
                                issues.append(f"block {i+1} @graph[{j+1}]: not an object")
                            elif "@type" not in g:
                                issues.append(f"block {i+1} @graph[{j+1}]: missing @type")
                        continue
                    if "@context" not in node:
                        issues.append(f"block {i+1}: missing @context")
                    if "@type" not in node:
                        issues.append(f"block {i+1}: missing @type")
            except Exception as e:
                issues.append(f"block {i+1}: invalid JSON ({str(e)[:60]})")
        if issues:
            report.append({"post_id": p.get("id"),
                           "title": (p.get("title") or {}).get("rendered", ""),
                           "schema_blocks": len(blocks), "issues": issues})
    return json.dumps({"posts_checked": len(posts), "posts_with_issues": len(report),
                       "details": report}, indent=2, ensure_ascii=False)


@mcp.tool()
def find_orphan_pages(limit: int = 300, site: str = "") -> str:
    """Find ORPHAN content: published posts/pages that NO other post links to
    internally. Orphans are hard for users and search engines to discover. Returns
    the orphaned items so you can add internal links to them (e.g. with
    bulk_internal_links). Scans up to `limit` posts."""
    _apply_site(site)
    posts = list(_all_posts(status="publish", limit=limit))
    site = _cfg()["site_url"].rstrip("/")
    linked = set()
    url_of = {}
    for p in posts:
        url_of[p.get("id")] = (p.get("link") or "").rstrip("/")
    for p in posts:
        raw = (p.get("content") or {}).get("raw", "")
        for href in _HREF_RE.findall(raw):
            h = href.rstrip("/")
            if h.startswith(site):
                linked.add(h)
            elif h.startswith("/"):
                linked.add(site + h)
    orphans = []
    for p in posts:
        link = url_of.get(p.get("id"), "")
        if link and link not in linked:
            orphans.append({"id": p.get("id"),
                            "title": (p.get("title") or {}).get("rendered", ""),
                            "url": link})
    return json.dumps({"posts_scanned": len(posts), "orphan_count": len(orphans),
                       "orphans": orphans}, indent=2, ensure_ascii=False)


# ===========================================================================
# GEO / AEO - AI-citation-readiness audit (get cited by ChatGPT, Perplexity,
# Google AI Overviews, Gemini, Claude). Scores 8 dimensions + an answer-block
# test, all measured from the actual content (no external calls).
# ===========================================================================
def _geo_signals(raw_html, title=""):
    """Compute the raw signals used for GEO scoring from a post's HTML."""
    # Prose-only: strips byline/date/read-time/share/related/figure containers so
    # they never pollute density or the answer-block test.
    text = _content_text(raw_html)
    words = text.split()
    n_words = len(words)
    sentences = [s.strip() for s in _re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    # Second-line defense: drop any metadata pseudo-sentence that survived (e.g.
    # a byline not wrapped in a recognized container). These have no sentence
    # punctuation so they get merged into one long "sentence" that can be
    # mistaken for a quotable answer block. A real answer must read like prose.
    _META_RE = _re.compile(
        r"(?i)(\bby\s+[A-Z][a-z]+|reviewed by|written by|fact-?checked|"
        r"\b\d+\s*min(ute)?s?\s+read\b|updated\s*:|published\s*:|last updated|"
        r"share (this|on)|\b\d{1,2}:\d{2}\b)")
    def _is_meta(s):
        # Metadata lines are byline/date/read-time and rarely end in a period.
        if _META_RE.search(s) and not _re.search(r"[.!?]$", s.strip()):
            return True
        # A "sentence" that's really a stack of ·/|-separated metadata chips.
        if s.count("·") + s.count("|") + s.count("•") >= 2:
            return True
        return False
    prose_sentences = [s for s in sentences if not _is_meta(s)]
    lower = text.lower()

    # Headings (from HTML), question-form headings, lists, tables, FAQ.
    headings = _re.findall(r"<h([1-6])[^>]*>(.*?)</h\1>", raw_html, _re.I | _re.S)
    heading_texts = [_TAG_RE.sub("", h[1]).strip() for h in headings]
    q_headings = [h for h in heading_texts if h.endswith("?") or
                  _re.match(r"(?i)^(how|what|why|when|where|who|which|is|are|can|do|does)\b", h)]
    n_lists = len(_re.findall(r"<(ul|ol)\b", raw_html, _re.I))
    n_tables = len(_re.findall(r"<table\b", raw_html, _re.I))
    has_faq = ("faq" in lower or "frequently asked" in lower or
               '"faqpage"' in raw_html.lower())

    # Factual density: numbers, %, years, $ figures per 100 words.
    numbers = _re.findall(r"\b\d[\d,\.]*%?\b", text)
    years = _re.findall(r"\b(19|20)\d{2}\b", text)
    dollars = _re.findall(r"\$\d[\d,\.]*", text)
    fact_hits = len(numbers) + len(dollars)
    fact_density = (fact_hits / n_words * 100) if n_words else 0

    # Vague phrases that hurt citability.
    vague = sum(lower.count(v) for v in (
        "many businesses", "a lot of", "some people", "studies show",
        "experts say", "it is said", "generally", "often", "several"))

    # Source citations: outbound links + citation words + dated references.
    ext_links = _re.findall(r'href=["\']https?://([^"\'/]+)', raw_html, _re.I)
    cite_words = sum(lower.count(w) for w in (
        "according to", "source:", "study", "research", "report", "data from",
        "published", "journal", "university"))

    # Authority / E-E-A-T signals.
    authority = sum(lower.count(w) for w in (
        "author", "reviewed by", "written by", "expert", "phd", "md ",
        "certified", "years of experience", "in our experience", "we tested",
        "credential", "fact-checked"))

    # Freshness: a visible date or year in text/schema.
    fresh = bool(years) or bool(_re.search(r'"dateModified"|"datePublished"', raw_html))

    # Definition block: a 25-50 word sentence early that reads like a definition.
    # (Use prose only, so a byline/date line is never picked as the definition.)
    definition = None
    for s in prose_sentences[:8]:
        wc = len(s.split())
        if 15 <= wc <= 60 and _re.search(r"\b(is|are|refers to|means|defined as)\b", s, _re.I):
            definition = s
            break

    # Quotable statements: self-contained factual sentences (contain a number or
    # named-entity-ish capitalized run), NOT starting with a back-reference.
    quotable = []
    for s in prose_sentences:
        wc = len(s.split())
        if not (8 <= wc <= 45):
            continue
        if _re.match(r"(?i)^(this|that|these|those|it|they|as (mentioned|noted|above)|however|therefore)\b", s):
            continue
        if _re.search(r"\d", s) or _re.search(r"\b[A-Z][a-z]+ [A-Z][a-z]+\b", s):
            quotable.append(s)

    return {
        # "sentences" feeds the answer-block test -> expose PROSE only so a byline
        # ("By David Anderson · Updated: … · 13 min read") is never returned as a
        # citation-ready answer block. "all_sentences" kept for any raw needs.
        "n_words": n_words, "sentences": prose_sentences,
        "all_sentences": sentences, "headings": heading_texts,
        "q_headings": q_headings, "n_lists": n_lists, "n_tables": n_tables,
        "has_faq": has_faq, "fact_density": fact_density, "fact_hits": fact_hits,
        "vague": vague, "ext_domains": set(ext_links), "cite_words": cite_words,
        "authority": authority, "fresh": fresh, "definition": definition,
        "quotable": quotable,
    }


def _geo_score(sig):
    """Turn signals into the 8 dimension scores (0-100) + overall."""
    def clamp(x):
        return int(max(0, min(100, x)))
    dims = {}
    # 1. Clear definitions
    dims["clear_definitions"] = clamp(85 if sig["definition"] else 20)
    # 2. Quotable statements (scaled by count relative to length)
    qn = len(sig["quotable"])
    dims["quotable_statements"] = clamp(min(100, qn * 12))
    # 3. Factual density (target ~2 facts/100 words = strong). fd is facts per
    #    100 words and typically lands in 0.2-4 for real articles, so the old
    #    `fd*25` scale under-scored everything and a single vague word could zero
    #    out a fact-rich post. Use a saturating curve: ~40 pts per fact/100w,
    #    reaching a strong score around 2/100w, and cap the vagueness penalty so
    #    measured facts are never fully erased.
    fd = sig["fact_density"]
    base = min(100, fd * 40)                    # 1/100w->40, 2/100w->80, 2.5+->~100
    if sig["fact_hits"] > 0:
        base = max(base, 30)                    # any real facts => a floor, never 0
    penalty = min(sig["vague"] * 4, 30)         # vagueness hurts but can't zero facts
    dims["factual_density"] = clamp(base - penalty)
    # 4. Source citations
    dims["source_citations"] = clamp(len(sig["ext_domains"]) * 20 + sig["cite_words"] * 10)
    # 5. Q&A / structured format
    struct = len(sig["q_headings"]) * 15 + sig["n_lists"] * 10 + sig["n_tables"] * 15 + (25 if sig["has_faq"] else 0)
    dims["structured_format"] = clamp(struct)
    # 6. Authority / E-E-A-T
    dims["authority_eeat"] = clamp(sig["authority"] * 18)
    # 7. Freshness
    dims["freshness"] = clamp(80 if sig["fresh"] else 25)
    # 8. Structure clarity (headings present + reasonable length sections)
    hc = len(sig["headings"])
    clarity = 30 + hc * 12
    if sig["n_words"] and hc:
        words_per_h = sig["n_words"] / hc
        if words_per_h > 400:
            clarity -= 20  # walls of text
    dims["structure_clarity"] = clamp(clarity)

    overall = int(sum(dims.values()) / len(dims))
    return dims, overall


@mcp.tool()
def geo_audit_post(post_id: int, target_queries: str = "", site: str = "") -> str:
    """GEO / AEO audit - how CITATION-READY a post is for AI answer engines
    (ChatGPT, Perplexity, Google AI Overviews, Gemini, Claude). Scores 8 dimensions
    0-100 (clear definitions, quotable statements, factual density, source
    citations, structured Q&A format, authority/E-E-A-T, freshness, structure
    clarity), gives an overall GEO score, and runs the ANSWER-BLOCK TEST against
    your `target_queries` (comma-separated) - for each query, is there a standalone
    25-50 word answer a machine could quote? Returns measured scores + specific,
    actionable fixes. All numbers here are MEASURED from the content (not guessed);
    anything inferred is labeled."""
    _apply_site(site)
    p = _v2("GET", f"/posts/{post_id}", params={"context": "edit"})
    raw = (p.get("content") or {}).get("raw", "")
    title = (p.get("title") or {}).get("rendered", "")
    if not raw:
        return json.dumps({"error": "post has no content", "post_id": post_id})

    sig = _geo_signals(raw, title)
    dims, overall = _geo_score(sig)

    # Answer-block test per target query.
    queries = [q.strip() for q in target_queries.split(",") if q.strip()]
    coverage = []
    for q in queries:
        q_words = set(_re.findall(r"[a-z]{4,}", q.lower()))
        best = None
        for s in sig["sentences"]:
            wc = len(s.split())
            if not (20 <= wc <= 60):
                continue
            # A quotable answer must read like a real sentence, not a metadata
            # chip-stack: require terminal punctuation and reject byline/date runs.
            if not _re.search(r"[.!?]$", s.strip()):
                continue
            overlap = len(q_words & set(_re.findall(r"[a-z]{4,}", s.lower())))
            if overlap >= max(1, len(q_words) // 2):
                best = s
                break
        coverage.append({"query": q, "citation_ready": bool(best),
                         "answer_block": best[:300] if best else None})
    ready = sum(1 for c in coverage if c["citation_ready"])

    # Actionable fixes (specific, measured triggers).
    fixes = []
    if dims["clear_definitions"] < 60:
        fixes.append("Add a standalone 25-50 word definition of the topic near the top "
                     "(a sentence like 'X is …') that reads without context.")
    if dims["quotable_statements"] < 50:
        fixes.append("Add self-contained factual sentences (one complete fact per line, "
                     "no 'as mentioned above'). Aim for several quotable statements.")
    if dims["factual_density"] < 50:
        fixes.append(f"Increase factual density: replace vague phrases ({sig['vague']} found) "
                     "with specific numbers, dates, and named entities (e.g. '73% in 2024').")
    if dims["source_citations"] < 50:
        fixes.append("Cite dated, authoritative sources (studies, official data) and link out "
                     "to them - AI engines prefer content backed by trusted sources.")
    if dims["structured_format"] < 50:
        fixes.append("Break content into Q&A headings (question form) with a direct answer "
                     "underneath, plus lists/tables and an FAQ block.")
    if dims["authority_eeat"] < 50:
        fixes.append("Add author byline + credentials, 'reviewed by', and experience-based "
                     "language ('in our testing…') to strengthen E-E-A-T.")
    if dims["freshness"] < 60:
        fixes.append("Show a visible publish/updated date and reference recent data so the "
                     "content reads as current.")
    if dims["structure_clarity"] < 60:
        fixes.append("Improve H2/H3 hierarchy - one idea per section, scannable, avoid walls "
                     "of text.")
    for c in coverage:
        if not c["citation_ready"]:
            fixes.append(f"No citation-ready answer block for query: '{c['query']}'. Add a "
                         "standalone 25-50 word answer that directly answers it.")

    return json.dumps({
        "post_id": post_id, "title": title,
        "geo_score": overall,
        "dimensions": dims,
        "answer_block_coverage": f"{ready}/{len(queries)} queries citation-ready" if queries
                                 else "no target_queries provided",
        "query_details": coverage,
        "measured_signals": {
            "words": sig["n_words"], "quotable_sentences": len(sig["quotable"]),
            "fact_hits": sig["fact_hits"], "fact_density_per_100w": round(sig["fact_density"], 2),
            "vague_phrases": sig["vague"], "external_sources": len(sig["ext_domains"]),
            "question_headings": len(sig["q_headings"]), "lists": sig["n_lists"],
            "tables": sig["n_tables"], "has_faq": sig["has_faq"], "has_date": sig["fresh"],
            "has_definition": bool(sig["definition"]),
        },
        "engine_notes": {
            "google_ai_overviews": "wants schema + concise definitions + FAQ",
            "chatgpt": "wants authoritative, clearly-stated facts",
            "perplexity": "wants recent, cited, source-linked content (freshness matters most)",
            "gemini": "wants structured, entity-clear content",
            "claude": "wants nuanced, balanced content; avoid over-optimization",
        },
        "fixes": fixes,
        "note": "All dimension scores and signals are MEASURED from the content. "
                "Turn fixes into edits, or use geo_optimize_post to apply them.",
    }, indent=2, ensure_ascii=False)


@mcp.tool()
def geo_optimize_post(post_id: int, optimized_html: str = "", target_queries: str = "", site: str = "") -> str:
    """Make a post AI-CITATION-READY. Two ways to use it:

    1) PLAN MODE (optimized_html empty): returns the post's current body + a GEO
       audit + a precise rewrite brief. You (the model) then rewrite the body to
       satisfy the brief and call this again with `optimized_html`.
    2) APPLY MODE (optimized_html given): saves your rewritten body (schema
       preserved) and returns the NEW GEO score so you can confirm it improved.

    The rewrite brief follows proven GEO technique: answer-first sections, a
    standalone 25-50 word definition up top, vague claims replaced with sourced +
    dated facts, Q&A headings + lists/tables, an FAQ that matches the visible
    content, author/E-E-A-T markers, and a visible date. Keep it accurate - never
    invent facts or fake sources."""
    _require_tier('paid')
    _apply_site(site)
    p = _v2("GET", f"/posts/{post_id}", params={"context": "edit"})
    raw = (p.get("content") or {}).get("raw", "")
    title = (p.get("title") or {}).get("rendered", "")
    if not raw and not optimized_html:
        return json.dumps({"error": "post has no content", "post_id": post_id})

    if not optimized_html:
        # PLAN MODE - hand back content + audit + rewrite brief.
        audit = json.loads(geo_audit_post(post_id, target_queries))
        brief = [
            "Rewrite the body to be AI-citation-ready WITHOUT losing accuracy:",
            "1. Put a standalone 25-50 word definition of the topic near the very top "
            "(reads without context).",
            "2. Make each section ANSWER-FIRST: a direct 1-2 sentence answer, then detail.",
            "3. Turn key H2/H3 into question form; add lists/tables where useful.",
            "4. Replace vague phrases with SPECIFIC sourced, dated facts; cite/link real "
            "authoritative sources (do not fabricate).",
            "5. Add self-contained quotable sentences (one complete fact per line).",
            "6. Add an FAQ section (3-6 Q&As) that matches the visible content.",
            "7. Add/keep author + credentials and a visible published/updated date.",
            "Return ONLY the new article HTML (no schema block - it is preserved "
            "automatically), then call geo_optimize_post again with optimized_html.",
        ]
        return json.dumps({
            "mode": "PLAN", "post_id": post_id, "title": title,
            "current_audit": {"geo_score": audit.get("geo_score"),
                              "dimensions": audit.get("dimensions"),
                              "answer_block_coverage": audit.get("answer_block_coverage")},
            "priority_fixes": audit.get("fixes", []),
            "rewrite_brief": brief,
            "current_body": raw,
        }, indent=2, ensure_ascii=False)

    # APPLY MODE - save the rewrite (preserve schema), re-score.
    schema_blocks = _SCHEMA_RE.findall(raw)
    body = optimized_html.rstrip()
    if schema_blocks and "application/ld+json" not in optimized_html:
        body += "\n\n" + "\n\n".join(schema_blocks)
    _v2("POST", f"/posts/{post_id}", payload={"content": body})
    after = json.loads(geo_audit_post(post_id, target_queries))
    return json.dumps({
        "mode": "APPLIED", "post_id": post_id,
        "new_geo_score": after.get("geo_score"),
        "new_dimensions": after.get("dimensions"),
        "answer_block_coverage": after.get("answer_block_coverage"),
        "note": "Saved and re-scored. Compare new_geo_score with the previous audit.",
    }, indent=2, ensure_ascii=False)


@mcp.tool()
def ai_seo_score(limit: int = 50, site: str = "") -> str:
    """The AI SEO Score - a unified, AI-era SEO scorecard for the whole site across
    5 categories (each 0-100) plus an overall: On-Page, Technical, AEO (answer-
    engine readiness), GEO (AI-citation readiness), and Authority (E-E-A-T). Every
    score is MEASURED from real content/site signals (no external APIs). Also
    returns concrete issue COUNTS (missing meta, missing alt, no schema, orphan
    pages, thin content, broken structure) so the dashboard can show 'Fix with
    Claude' actions. This is what powers the dashboard's AI SEO widget."""
    _apply_site(site)
    posts = list(_all_posts(status="publish", limit=limit))
    n = max(1, len(posts))
    site = _cfg()["site_url"].rstrip("/")

    # Per-post accumulation.
    onpage = tech = aeo = geo = auth = 0.0
    missing_meta = missing_alt = no_schema = thin = 0
    all_hrefs = set()
    post_urls = {}

    for p in posts:
        raw = (p.get("content") or {}).get("raw", "")
        title = (p.get("title") or {}).get("rendered", "")
        sig = _geo_signals(raw, title)
        dims, _ = _geo_score(sig)

        # ON-PAGE: headings, alt coverage, internal links, content length, title/excerpt.
        imgs = _re.findall(r"<img\b[^>]*>", raw, _re.I)
        imgs_no_alt = [i for i in imgs if not _re.search(r'alt=["\'][^"\']+["\']', i, _re.I)]
        if imgs_no_alt:
            missing_alt += len(imgs_no_alt)
        internal = [h for h in _re.findall(r'href=["\']([^"\']+)', raw)
                    if h.startswith(site) or h.startswith("/")]
        op = 0
        op += 25 if sig["n_words"] >= 600 else (12 if sig["n_words"] >= 300 else 0)
        op += 20 if sig["headings"] else 0
        op += 20 if imgs and not imgs_no_alt else (8 if imgs else 0)
        op += 20 if len(internal) >= 2 else (10 if internal else 0)
        op += 15 if (p.get("excerpt") or {}).get("rendered", "").strip() else 0
        onpage += min(100, op)
        if sig["n_words"] < 300:
            thin += 1

        # SEO meta present? (via backend)
        try:
            seo = _seo_read(p.get("id"))
            if not (isinstance(seo, dict) and (seo.get("meta_description") or "").strip()):
                missing_meta += 1
        except Exception:
            missing_meta += 1

        # TECHNICAL (per-post part): schema present, clean structure.
        blocks = _SCHEMA_RE.findall(raw)
        if not blocks:
            no_schema += 1
        t = 0
        t += 40 if blocks else 0
        t += 30 if sig["headings"] else 0
        t += 30 if sig["n_words"] and (sig["n_words"] / max(1, len(sig["headings"] or [1])) < 400) else 10
        tech += min(100, t)

        # AEO: answer-ready - FAQ, question headings, lists/tables, a definition.
        a = 0
        a += 30 if sig["has_faq"] else 0
        a += 25 if sig["q_headings"] else 0
        a += 20 if (sig["n_lists"] or sig["n_tables"]) else 0
        a += 25 if sig["definition"] else 0
        aeo += min(100, a)

        # GEO: reuse the GEO dimensions average.
        geo += sum(dims.values()) / len(dims)

        # AUTHORITY / E-E-A-T.
        au = 0
        au += min(60, sig["authority"] * 20)
        au += 25 if sig["fresh"] else 0
        au += 15 if sig["cite_words"] else 0
        auth += min(100, au)

        # collect for orphan detection
        link = (p.get("link") or "").rstrip("/")
        post_urls[p.get("id")] = link
        for h in _re.findall(r'href=["\']([^"\']+)', raw):
            hh = h.rstrip("/")
            if hh.startswith(site):
                all_hrefs.add(hh)
            elif hh.startswith("/"):
                all_hrefs.add(site + hh)

    orphans = sum(1 for pid, u in post_urls.items() if u and u not in all_hrefs)

    def avg(x):
        return int(round(x / n))
    cats = {
        "on_page": avg(onpage),
        "technical": avg(tech),
        "aeo": avg(aeo),
        "geo": avg(geo),
        "authority_eeat": avg(auth),
    }
    overall = int(round(sum(cats.values()) / len(cats)))

    # Site-level llms.txt / robots signal folds a small bonus into Technical/GEO.
    return json.dumps({
        "ai_seo_score": overall,
        "categories": cats,
        "issues": {
            "missing_meta_description": missing_meta,
            "images_missing_alt": missing_alt,
            "posts_without_schema": no_schema,
            "thin_posts": thin,
            "orphan_pages": orphans,
        },
        "posts_scored": len(posts),
        "fix_actions": {
            "on_page": "Run bulk_generate_meta, generate_alt_text_ai, and add internal links.",
            "technical": "Add schema to posts, validate_schema, check_broken_links.",
            "aeo": "Add FAQ blocks, question-form headings, and concise definitions.",
            "geo": "Use geo_optimize_post on top posts; set a curated llms.txt.",
            "authority_eeat": "Add author bylines, credentials, 'reviewed by', and visible dates.",
        },
        "note": "All category scores are MEASURED from your content. Backlinks, Local "
                "SEO and Core Web Vitals are not included (they need external data).",
    }, indent=2, ensure_ascii=False)


@mcp.tool()
def request_approval(action_summary: str, tool_name: str = "", risk: str = "high", site: str = "") -> str:
    """Queue a RISKY action for the site owner to approve in their wptaskify
    dashboard, instead of doing it right away. Use this for irreversible or high-
    impact actions when the user hasn't already explicitly approved them - e.g.
    deleting many posts/pages/media, switching the active theme, editing .htaccess,
    deactivating a plugin, or big bulk find-replace on live content.

    `action_summary`: a clear, plain-language description of exactly what you want
    to do (the user sees this). `risk`: 'low' | 'medium' | 'high'. After calling
    this, TELL the user it's waiting for their approval in the dashboard's Approval
    inbox, and do NOT perform the action until they approve it there."""
    _apply_site(site)
    cfg = _cfg()
    hook = cfg.get("approval_hook")
    if hook is None:
        return json.dumps({
            "queued": False,
            "note": "Approval inbox isn't available in this context. Ask the user to "
                    "confirm directly before doing this risky action.",
        })
    action_id = hook(tool_name or "manual", {}, action_summary, risk)
    return json.dumps({
        "queued": True, "approval_id": action_id, "risk": risk,
        "message": "This action is now waiting for the user's approval in their WP "
                   "Pilot dashboard (Approvals). Do NOT perform it until they approve.",
    })


@mcp.tool()
def check_approval(approval_id: str, site: str = "") -> str:
    """Check whether a queued approval (from request_approval) has been decided by
    the user. Returns status: 'pending', 'approved', or 'rejected'. Only perform the
    action once status is 'approved'; if 'rejected', do not do it."""
    _apply_site(site)
    cfg = _cfg()
    checker = cfg.get("approval_status_hook")
    if checker is None:
        return json.dumps({"status": "unknown",
                           "note": "Cannot check approval status in this context."})
    return json.dumps(checker(approval_id))


@mcp.tool()
def insert_in_article_image(post_id: int, prompt: str, after_text: str = "", alt_text: str = "", site: str = "") -> str:
    """Generate an image with Gemini and INSERT it inside a post's body as an <img>.
    If `after_text` is given, the image is placed right after the first occurrence of
    that text; otherwise appended before the schema block. Preserves schema."""
    _require_tier('paid')
    _apply_site(site)
    p = _v2("GET", f"/posts/{post_id}", params={"context": "edit"})
    raw = (p.get("content") or {}).get("raw", "")
    img_bytes = _gemini_generate_image(prompt)
    media = _request("POST", "/wp/v2/media", raw_body=img_bytes, extra_headers={
        "Content-Type": "image/png",
        "Content-Disposition": f'attachment; filename="inline-{post_id}.png"',
    })
    mid, src = media["id"], media.get("source_url")
    if alt_text:
        _v2("POST", f"/media/{mid}", payload={"alt_text": alt_text})
    img_html = f'\n<figure class="wp-block-image size-large"><img src="{src}" alt="{alt_text}" class="wp-image-{mid}"/></figure>\n'
    if after_text and after_text in raw:
        idx = raw.find(after_text) + len(after_text)
        new_raw = raw[:idx] + img_html + raw[idx:]
    else:
        # insert before first schema script, else append
        m = _SCHEMA_RE.search(raw)
        if m:
            new_raw = raw[:m.start()] + img_html + raw[m.start():]
        else:
            new_raw = raw + img_html
    _v2("POST", f"/posts/{post_id}", payload={"content": new_raw})
    return json.dumps({"post_id": post_id, "media_id": mid, "url": src, "inserted": True}, ensure_ascii=False)


@mcp.tool()
def fix_missing_excerpts(limit: int = 100, apply: bool = False, site: str = "") -> str:
    """Find published posts with an EMPTY excerpt. With apply=False reports them.
    With apply=True, generates a ~30-word excerpt from the first paragraph of each
    (your theme uses excerpt for meta description)."""
    _require_tier('paid')
    _apply_site(site)
    flagged = []
    for p in _all_posts(status="publish", limit=limit):
        ex = (p.get("excerpt") or {}).get("raw", "").strip()
        if ex:
            continue
        raw = (p.get("content") or {}).get("raw", "")
        text = _TAG_RE.sub(" ", _SCHEMA_RE.sub(" ", raw))
        text = _re.sub(r"\s+", " ", text).strip()
        snippet = " ".join(text.split()[:30])
        entry = {"id": p["id"], "title": (p.get("title") or {}).get("raw", ""), "suggested_excerpt": snippet}
        if apply and snippet:
            _v2("POST", f"/posts/{p['id']}", payload={"excerpt": snippet})
            entry["applied"] = True
        flagged.append(entry)
    return json.dumps({"mode": "APPLIED" if apply else "REPORT", "posts_missing_excerpt": len(flagged),
                       "posts": flagged}, indent=2, ensure_ascii=False)


@mcp.tool()
def ping_search_engines(post_url: str = "", site: str = "") -> str:
    """Ask search engines to re-crawl. IMPORTANT: Google and Bing RETIRED their
    sitemap-ping endpoints in 2023, so there is no working "ping" anymore. The
    reliable way to get new content crawled is Google Search Console (Site Kit) -
    submit your sitemap once and use "Request indexing" for a specific URL. This
    tool now returns those instructions instead of hitting dead endpoints."""
    _require_tier('paid')
    _apply_site(site)
    sitemap = _cfg()["site_url"].rstrip("/") + "/wppseo-sitemap.xml"
    steps = [
        "Sitemap: in Search Console (Site Kit) > Sitemaps, submit "
        f"{sitemap} once. Google re-crawls it automatically after that.",
    ]
    if post_url:
        steps.append(
            f"This URL: in Search Console, paste {post_url} into the top search "
            "bar (URL Inspection) and click 'Request indexing' for fastest pickup.")
    return json.dumps({
        "sitemap": sitemap,
        "ping_status": "unavailable - Google & Bing removed sitemap-ping in 2023",
        "recommended_actions": steps,
    }, indent=2, ensure_ascii=False)


# ===========================================================================
# SEO AUDIT (single post - full report)
# ===========================================================================
_H_RE = _re.compile(r'<h([1-6])\b[^>]*>(.*?)</h\1>', _re.IGNORECASE | _re.DOTALL)


@mcp.tool()
def seo_audit_post(post_id: int, focus_keyword: str = "", site: str = "") -> str:
    """Full on-page SEO audit of ONE post in a single report: title length,
    excerpt/meta length, word count, heading structure (H1-H6), internal vs
    external link counts, images & missing alt, schema present?, and (if given)
    focus_keyword usage in title/first paragraph/density. Returns issues + stats."""
    _apply_site(site)
    p = _v2("GET", f"/posts/{post_id}", params={"context": "edit"})
    title = (p.get("title") or {}).get("raw", "")
    excerpt = (p.get("excerpt") or {}).get("raw", "")
    raw = (p.get("content") or {}).get("raw", "")
    text = _re.sub(r"\s+", " ", _TAG_RE.sub(" ", _SCHEMA_RE.sub(" ", raw))).strip()
    words = text.split()
    wc = len(words)

    headings = [{"level": int(l), "text": _TAG_RE.sub("", h).strip()[:80]} for l, h in _H_RE.findall(raw)]
    h_levels = [x["level"] for x in headings]
    links = _HREF_RE.findall(raw)
    _su = _cfg()["site_url"]
    internal = [l for l in links if (_su in l or l.startswith("/")) and not l.startswith("#")]
    external = [l for l in links if l.startswith("http") and _su not in l]
    imgs = _IMG_RE.findall(raw)
    imgs_no_alt = [i for i in imgs if 'alt=""' in i or "alt=''" in i or "alt=" not in i.lower()]
    # The featured image lives in post meta (featured_media), NOT in the body
    # HTML - so a post with a featured image but no inline <img> was reporting
    # "images: 0", which looks like a bug to users. Count it separately.
    has_featured = bool(p.get("featured_media"))
    total_images = len(imgs) + (1 if has_featured else 0)
    has_schema = bool(_SCHEMA_RE.search(raw))

    issues = []
    if not (40 <= len(title) <= 65):
        issues.append(f"Title length {len(title)} chars (ideal 50-60).")
    if not excerpt:
        issues.append("No excerpt/meta description (your theme uses excerpt for SEO).")
    elif len(excerpt) > 160:
        issues.append(f"Excerpt {len(excerpt)} chars (>160 may get truncated).")
    if wc < 600:
        issues.append(f"Thin content: {wc} words (<600).")
    if h_levels.count(1) > 1:
        issues.append("Multiple H1 tags in content (should be one, theme adds page H1).")
    if not internal:
        issues.append("No internal links - add links to related posts.")
    if not external:
        issues.append("No external/authority links.")
    if imgs and imgs_no_alt:
        issues.append(f"{len(imgs_no_alt)}/{len(imgs)} images missing alt text.")
    if not has_schema:
        issues.append("No JSON-LD schema found in content.")

    kw = {}
    if focus_keyword:
        fk = focus_keyword.lower()
        first_para = " ".join(words[:60]).lower()
        density = text.lower().count(fk) / max(wc, 1) * 100
        kw = {
            "keyword": focus_keyword,
            "in_title": fk in title.lower(),
            "in_first_paragraph": fk in first_para,
            "occurrences": text.lower().count(fk),
            "density_percent": round(density, 2),
            "density_ok": 0.5 <= density <= 2.5,
        }
        if not kw["in_title"]:
            issues.append(f"Focus keyword '{focus_keyword}' not in title.")
        if not kw["in_first_paragraph"]:
            issues.append(f"Focus keyword '{focus_keyword}' not in first paragraph.")

    return json.dumps({
        "post_id": post_id, "title": title, "url": p.get("link"),
        "stats": {
            "title_chars": len(title), "excerpt_chars": len(excerpt),
            "word_count": wc, "reading_time_min": max(1, round(wc / 220)),
            "headings": headings, "internal_links": len(internal),
            "external_links": len(external), "images": total_images,
            "inline_images": len(imgs), "has_featured_image": has_featured,
            "images_missing_alt": len(imgs_no_alt), "has_schema": has_schema,
        },
        "focus_keyword": kw,
        "issues": issues,
        "issue_count": len(issues),
    }, indent=2, ensure_ascii=False)


# ===========================================================================
# REDIRECTS (Redirection plugin) - fix 404s
# ===========================================================================
@mcp.tool()
def create_redirect(source_url: str, target_url: str, http_code: int = 301, site: str = "") -> str:
    """Create a redirect (e.g. fix a 404). source_url = old path like
    '/old-page/'; target_url = new path or full URL. 301 = permanent (default)."""
    _require_tier('paid')
    _apply_site(site)
    payload = {
        "url": source_url,
        "action_data": {"url": target_url},
        "match_type": "url",
        "action_type": "url",
        "action_code": http_code,
        "group_id": 1,
        "status": "enabled",
    }
    r = _request("POST", "/redirection/v1/redirect", payload=payload)
    return json.dumps({"created": True, "source": source_url, "target": target_url, "code": http_code,
                       "raw": r if isinstance(r, dict) else str(r)[:200]}, ensure_ascii=False)


@mcp.tool()
def list_redirects(search: str = "", per_page: int = 50, site: str = "") -> str:
    """List existing redirects (Redirection plugin) with their ID, source URL,
    target, and hit count. Use `search` to filter by URL. Get the ID here, then
    delete_redirect to remove a duplicate/unwanted one."""
    _apply_site(site)
    params = {"per_page": min(per_page, 100), "orderby": "id", "direction": "asc"}
    if search:
        params["filterBy[url]"] = search
    r = _request("GET", "/redirection/v1/redirect", params=params)
    items = r.get("items", []) if isinstance(r, dict) else []
    out = [{"id": i.get("id"), "source": i.get("url"),
            "target": (i.get("action_data") or {}).get("url") if isinstance(i.get("action_data"), dict)
                      else i.get("action_data"),
            "code": i.get("action_code"), "hits": i.get("hits"),
            "status": i.get("status")} for i in items]
    return json.dumps({"count": len(out), "redirects": out}, indent=2, ensure_ascii=False)


@mcp.tool()
def delete_redirect(redirect_id: int, site: str = "") -> str:
    """Delete a redirect by its ID (find it with list_redirects). Removes it from
    the Redirection plugin permanently. Use for duplicate/stale redirects."""
    _require_tier('paid')
    _apply_site(site)
    # The Redirection plugin deletes via a bulk POST action (its REST DELETE isn't
    # exposed on all versions); this bulk form is the reliable path.
    try:
        r = _request("POST", "/redirection/v1/bulk/redirect/delete",
                     params={"items": str(int(redirect_id))})
    except Exception:
        # Fallback: some versions accept a plain DELETE on the item.
        r = _request("DELETE", f"/redirection/v1/redirect/{int(redirect_id)}")
    return json.dumps({"deleted_id": redirect_id,
                       "raw": r if isinstance(r, dict) else str(r)[:200]}, ensure_ascii=False)


@mcp.tool()
def list_404_log(per_page: int = 25, site: str = "") -> str:
    """List recent 404 errors visitors hit (from Redirection plugin's 404 log).
    Great for finding broken URLs to redirect. Returns url + hit count."""
    _apply_site(site)
    r = _request("GET", "/redirection/v1/404", params={"per_page": min(per_page, 50), "orderby": "count", "direction": "desc"})
    items = r.get("items", []) if isinstance(r, dict) else []
    return json.dumps([{"url": i.get("url"), "hits": i.get("count"), "last": i.get("last_access")} for i in items],
                      indent=2, ensure_ascii=False)


# ===========================================================================
# MEGA TOOL - write a complete article end-to-end
# ===========================================================================
@mcp.tool()
def publish_full_article(title: str, content_html: str, status: str = "draft",
                         author_id: int = 0, category_ids: str = "", tag_ids: str = "",
                         excerpt: str = "", internal_link_topic: str = "",
                         generate_image: bool = True, site: str = "") -> str:
    """One-shot publisher: creates a post AND (optionally) sets author, categories,
    tags, excerpt, generates+attaches a Gemini featured image, and returns suggested
    internal links for the topic so you can weave them in. `content_html` should be
    the full article HTML (include your schema script if you have one).
    Use status='draft' to review first, 'publish' to go live."""
    _require_tier('paid')
    _apply_site(site)
    payload = {"title": title, "content": content_html, "status": status}
    if excerpt:
        payload["excerpt"] = excerpt
    if author_id:
        payload["author"] = author_id
    if category_ids:
        payload["categories"] = [int(x) for x in category_ids.split(",") if x.strip()]
    if tag_ids:
        payload["tags"] = [int(x) for x in tag_ids.split(",") if x.strip()]
    post = _v2("POST", "/posts", payload=payload)
    pid = post["id"]
    result = {"post_id": pid, "status": post.get("status"), "link": post.get("link")}

    if generate_image:
        try:
            prompt = (f"Photorealistic professional stock photo for a blog titled '{title}'. "
                      f"Clean bright water/hydration theme, natural light, no text. 16:9.")
            img = _gemini_generate_image(prompt)
            media = _request("POST", "/wp/v2/media", raw_body=img, extra_headers={
                "Content-Type": "image/png",
                "Content-Disposition": f'attachment; filename="post-{pid}-featured.png"'})
            _v2("POST", f"/posts/{pid}", payload={"featured_media": media["id"]})
            _v2("POST", f"/media/{media['id']}", payload={"alt_text": title})
            result["featured_image"] = media.get("source_url")
        except Exception as e:
            result["featured_image_error"] = str(e)[:150]

    if internal_link_topic:
        try:
            res = _v2("GET", "/search", params={"search": internal_link_topic, "per_page": 8})
            result["suggested_internal_links"] = [{"title": r.get("title"), "url": r.get("url")}
                                                  for r in res if r.get("id") != pid][:6]
        except Exception:
            pass
    return json.dumps(result, indent=2, ensure_ascii=False)


@mcp.tool()
def find_related_posts(post_id: int, max_results: int = 6, site: str = "") -> str:
    """Find posts most related to a given post (by shared title keywords). Useful
    for adding 'Related articles' internal links. Returns title + url."""
    _apply_site(site)
    p = _v2("GET", f"/posts/{post_id}", params={"context": "edit"})
    title = (p.get("title") or {}).get("raw", "")
    stop = {"the", "a", "an", "is", "are", "of", "for", "to", "and", "your", "you",
            "in", "on", "with", "actually", "best", "vs", "what", "how", "much",
            "it", "or", "at", "by", "from", "into", "review", "guide", "top"}
    def _keywords(s):
        return {w.lower() for w in _re.sub(r"[^a-zA-Z ]", " ", s).split()
                if w.lower() not in stop and len(w) > 3}
    src_kw = _keywords(title)
    # Search each meaningful keyword (not one truncated phrase), then RANK
    # candidates by how many source keywords their title actually shares. This
    # fixes the old bug where "Whole House vs Under-Sink Filter" -> query
    # "Whole House Under" (dropped "Filter") -> matched an unrelated post.
    seen = {}
    for kw in sorted(src_kw, key=len, reverse=True)[:6] or [title]:
        for r in _v2("GET", "/search", params={"search": kw, "per_page": 15}):
            rid = r.get("id")
            if rid == post_id or (r.get("subtype") or r.get("type")) != "post":
                continue
            if rid not in seen:
                seen[rid] = r
    scored = []
    for rid, r in seen.items():
        overlap = len(src_kw & _keywords(r.get("title") or ""))
        if overlap:  # require at least one shared topic word
            scored.append((overlap, r))
    scored.sort(key=lambda t: t[0], reverse=True)
    out = [{"id": r.get("id"), "title": r.get("title"), "url": r.get("url"),
            "shared_keywords": n} for n, r in scored[:max_results]]
    return json.dumps({"post_id": post_id, "source_keywords": sorted(src_kw),
                       "related": out}, indent=2, ensure_ascii=False)


# ===========================================================================
# SEO META FIELDS - UNIVERSAL
# Works on any site by auto-detecting the SEO backend in this priority:
#   1. wptaskify plugin   (wppseo/v1)        -> our own plugin, recommended
#   2. wg-seo bridge          (_cwg_seo_*)       -> the original water-guide bridge
#   3. Yoast                  (_yoast_wpseo_*)   -> read/write via core meta
#   4. Rank Math              (rank_math_*)      -> read/write via core meta
# Detection result is cached per site_url for the process lifetime.
# ===========================================================================
_seo_backend_cache = {}


def _detect_seo_backend():
    """Return one of: 'wppilot', 'wgseo', 'yoast', 'rankmath', or 'none'.
    Cached per tenant site so we don't probe on every call."""
    site = _cfg()["site_url"]
    if site in _seo_backend_cache:
        return _seo_backend_cache[site]

    backend = "none"
    # 1. wptaskify plugin?
    try:
        r = _request("GET", "/wppseo/v1/info")
        if isinstance(r, dict) and r.get("plugin") == "wp-pilot-seo":
            backend = "wppilot"
    except Exception:
        pass
    # 2. wg-seo bridge?
    if backend == "none":
        try:
            _request("GET", "/wg-seo/v1/meta", params={"post": 0, "key": "_x"})
            backend = "wgseo"
        except Exception:
            pass
    # 3/4. Yoast / Rank Math - detect via active plugins list (best effort).
    if backend == "none":
        try:
            plugins = _request("GET", "/wp/v2/plugins")
            names = " ".join((p.get("plugin", "") + p.get("name", "")).lower() for p in plugins if p.get("status") == "active")
            if "yoast" in names or "wordpress-seo" in names:
                backend = "yoast"
            elif "rank" in names and "math" in names:
                backend = "rankmath"
        except Exception:
            pass

    _seo_backend_cache[site] = backend
    return backend


# Field-name maps per backend: label -> meta key (or wppseo field name).
_SEO_MAPS = {
    "wppilot": {"meta_title": "title", "meta_description": "description",
                "focus_keyword": "focus_kw", "keywords": "keywords"},
    "wgseo":   {"meta_title": "_cwg_seo_title", "meta_description": "_cwg_seo_description",
                "focus_keyword": "_cwg_seo_focus_kw", "keywords": "_cwg_seo_keywords"},
    "yoast":   {"meta_title": "_yoast_wpseo_title", "meta_description": "_yoast_wpseo_metadesc",
                "focus_keyword": "_yoast_wpseo_focuskw", "keywords": ""},
    "rankmath": {"meta_title": "rank_math_title", "meta_description": "rank_math_description",
                 "focus_keyword": "rank_math_focus_keyword", "keywords": ""},
}


def _seo_get(post_id, key):
    """Read a raw meta value. Uses the wg-seo bridge endpoint when present,
    otherwise falls back to the core REST meta field."""
    try:
        r = _request("GET", "/wg-seo/v1/meta", params={"post": post_id, "key": key})
        return r.get("value", "") if isinstance(r, dict) else ""
    except Exception:
        p = _v2("GET", f"/posts/{post_id}", params={"context": "edit"})
        return (p.get("meta") or {}).get(key, "")


def _seo_set(post_id, key, value):
    try:
        return _request("POST", "/wg-seo/v1/meta", payload={"post": post_id, "key": key, "value": value})
    except Exception:
        return _v2("POST", f"/posts/{post_id}", payload={"meta": {key: value}})


def _seo_read(post_id):
    """Backend-aware read. Returns dict of label->value."""
    backend = _detect_seo_backend()
    out = {"_backend": backend}
    if backend == "wppilot":
        r = _request("GET", "/wppseo/v1/seo", params={"post": post_id})
        for label in ("meta_title", "meta_description", "focus_keyword", "keywords"):
            field = _SEO_MAPS["wppilot"][label]
            # wppseo returns short field names (title/description/focus_kw/keywords)
            out[label] = r.get(field, "") if isinstance(r, dict) else ""
        if isinstance(r, dict) and "score" in r:
            out["_score"] = r["score"]
        return out
    mapping = _SEO_MAPS.get(backend, _SEO_MAPS["wgseo"])
    for label, key in mapping.items():
        out[label] = _seo_get(post_id, key) if key else ""
    return out


def _seo_write(post_id, values):
    """Backend-aware write. `values` = dict label->value (non-empty only)."""
    backend = _detect_seo_backend()
    if backend == "wppilot":
        fields = {}
        for label, val in values.items():
            field = _SEO_MAPS["wppilot"].get(label)
            if field and val:
                fields[field] = val
        if not fields:
            return {}
        r = _request("POST", "/wppseo/v1/seo", payload={"post": post_id, "fields": fields})
        return r.get("updated", fields) if isinstance(r, dict) else fields
    mapping = _SEO_MAPS.get(backend, _SEO_MAPS["wgseo"])
    changed = {}
    for label, val in values.items():
        key = mapping.get(label)
        if key and val:
            _seo_set(post_id, key, val)
            changed[key] = val[:80]
    return changed


@mcp.tool()
def get_post_seo(post_id: int, site: str = "") -> str:
    """Read a post's SEO meta fields (meta title, description, focus keyword,
    keywords). Works on ANY site - auto-detects wptaskify, Yoast, Rank Math,
    or the wg-seo bridge. Returns current values + length hints (+ score if the
    wptaskify plugin is installed)."""
    _apply_site(site)
    data = _seo_read(post_id)
    data["_lengths"] = {
        "meta_title_chars": len(data.get("meta_title", "") or ""),
        "meta_description_chars": len(data.get("meta_description", "") or ""),
    }
    data["_hints"] = []
    if not (40 <= len(data.get("meta_title", "") or "") <= 65):
        data["_hints"].append("meta_title ideal 50-60 chars")
    if not (120 <= len(data.get("meta_description", "") or "") <= 160):
        data["_hints"].append("meta_description ideal 150-160 chars")
    if not data.get("focus_keyword"):
        data["_hints"].append("focus_keyword empty")
    return json.dumps({"post_id": post_id, "seo": data}, indent=2, ensure_ascii=False)


@mcp.tool()
def update_post_seo(post_id: int, meta_title: str = "", meta_description: str = "",
                    focus_keyword: str = "", keywords: str = "", site: str = "") -> str:
    """Set a post's SEO meta fields. Only non-empty values are written. Works on
    ANY site - auto-detects wptaskify, Yoast, Rank Math, or the wg-seo bridge,
    and writes to the right fields so the rendered <title>, meta description,
    Open Graph & Twitter tags update. `keywords` = comma-separated secondary keywords."""
    _require_tier('paid')
    _apply_site(site)
    values = {
        "meta_title": meta_title,
        "meta_description": meta_description,
        "focus_keyword": focus_keyword,
        "keywords": keywords,
    }
    values = {k: v for k, v in values.items() if v}
    if not values:
        return "Nothing to update - pass at least one SEO field."
    changed = _seo_write(post_id, values)
    backend = _detect_seo_backend()
    return json.dumps({"post_id": post_id, "backend": backend, "updated": changed},
                      indent=2, ensure_ascii=False)


@mcp.tool()
def update_post_aeo(post_id: int, quick_answer: str = "", key_takeaways: str = "",
                    reviewed_by: str = "", last_reviewed: str = "",
                    speakable: str = "", in_language: str = "", site: str = "") -> str:
    """Set a post's ANSWER-ENGINE (AEO/GEO) fields - the stuff that gets a page
    quoted and cited by ChatGPT, Perplexity, Google AI Overviews, Gemini & Claude.
    WordPress and most SEO plugins have none of this. Only non-empty fields change.
    Requires the wptaskify plugin. Fields:
      - quick_answer: a standalone 25-50 word direct answer (rendered at the top of
        the post + marked speakable). This is the #1 GEO lever.
      - key_takeaways: TL;DR bullets, ONE PER LINE (rendered as a list + schema abstract)
      - reviewed_by: E-E-A-T reviewer name (adds reviewedBy to Article schema)
      - last_reviewed: intentional review date YYYY-MM-DD (separate from auto-modified)
      - speakable: '1' to mark the title + quick answer as voice-readable (speakable schema)
      - in_language: BCP-47 code like 'en-US' (blank = site language)"""
    _require_tier('paid')
    _apply_site(site)
    fields = {}
    if quick_answer:
        fields["quick_answer"] = quick_answer
    if key_takeaways:
        fields["key_takeaways"] = key_takeaways
    if reviewed_by:
        fields["reviewed_by"] = reviewed_by
    if last_reviewed:
        fields["last_reviewed"] = last_reviewed
    if speakable:
        fields["speakable"] = "1" if str(speakable).strip() in ("1", "true", "True", "yes") else ""
    if in_language:
        fields["in_language"] = in_language
    if not fields:
        return "Nothing to update - pass at least one AEO field."
    r = _request("POST", "/wppseo/v1/seo", payload={"post": post_id, "fields": fields})
    return json.dumps({"post_id": post_id, "updated": r.get("updated", fields)},
                      indent=2, ensure_ascii=False)


@mcp.tool()
def seo_backend_info(site: str = "") -> str:
    """Detect which SEO system this site uses (wptaskify, Yoast, Rank Math,
    wg-seo bridge, or none). Tells you whether SEO meta tools will work here and
    suggests installing the free wptaskify plugin if nothing is detected."""
    _apply_site(site)
    backend = _detect_seo_backend()
    names = {
        "wppilot": "wptaskify plugin",
        "wgseo": "wg-seo bridge (custom)",
        "yoast": "Yoast SEO",
        "rankmath": "Rank Math",
        "none": "none detected",
    }
    out = {"backend": backend, "name": names.get(backend, backend),
           "seo_tools_available": backend != "none"}
    if backend == "none":
        out["suggestion"] = ("No SEO plugin found. Install the free wptaskify plugin "
                             "to enable SEO meta, schema, sitemap & score tools.")
    return json.dumps(out, indent=2, ensure_ascii=False)


@mcp.tool()
def get_seo_settings() -> str:
    """Read the SITE-WIDE SEO settings (wptaskify plugin): Knowledge Graph identity
    (Organization vs Person, name, logo, sameAs social profiles, knowsAbout topics),
    homepage SEO title/description, and the default social (OG) image. Requires the
    wptaskify plugin. Use update_seo_settings to change them."""
    r = _request("GET", "/wppseo/v1/settings")
    return json.dumps(r, indent=2, ensure_ascii=False)


@mcp.tool()
def update_seo_settings(entity_type: str = "", entity_name: str = "",
                        same_as: str = "", knows_about: str = "",
                        home_title: str = "", home_desc: str = "",
                        logo_id: int = 0, default_og_id: int = 0) -> str:
    """Update SITE-WIDE SEO settings (wptaskify plugin). Only non-empty fields are
    changed (partial update). Fields:
      - entity_type: 'Organization' or 'Person' (who publishes this site)
      - entity_name: brand/person name (blank = use site title)
      - same_as: social profile URLs, one per line (Facebook, X, LinkedIn, etc.)
      - knows_about: topics this site is an authority on, one per line
      - home_title / home_desc: homepage SEO title & meta description
      - logo_id / default_og_id: media library attachment IDs (upload first)
    This powers the site's Organization/Person schema + default OG image. Requires
    the wptaskify plugin (admin capability)."""
    _require_tier('paid')
    payload = {}
    if entity_type:
        et = entity_type.strip().capitalize()
        payload["entity_type"] = "Person" if et == "Person" else "Organization"
    if entity_name:
        payload["entity_name"] = entity_name
    if same_as:
        payload["same_as"] = same_as
    if knows_about:
        payload["knows_about"] = knows_about
    if home_title:
        payload["home_title"] = home_title
    if home_desc:
        payload["home_desc"] = home_desc
    if logo_id:
        payload["logo_id"] = int(logo_id)
    if default_og_id:
        payload["default_og_id"] = int(default_og_id)
    if not payload:
        return json.dumps({"error": "no fields given - pass at least one setting to update"})
    r = _request("POST", "/wppseo/v1/settings", payload=payload)
    return json.dumps(r, indent=2, ensure_ascii=False)


@mcp.tool()
def update_analytics_settings(ga4_id: str = "", gsc_verify: str = "",
                              bing_verify: str = "", head_code: str = "") -> str:
    """Set the site's analytics + search-engine verification (wptaskify plugin).
    These are added to the site's <head>. Only non-empty fields change. Fields:
      - ga4_id: Google Analytics 4 Measurement ID (G-XXXXXXX). The tracking snippet
        is built automatically; logged-in admins are not tracked.
      - gsc_verify: Google Search Console verification token (or paste the full
        meta tag - the token is extracted).
      - bing_verify: Bing Webmaster verification token.
      - head_code: extra raw head tags (meta/script/link) for other verifications
        or pixels; sanitized to safe tags on save.
    Requires the wptaskify plugin (admin capability)."""
    _require_tier('paid')
    payload = {}
    if ga4_id:
        payload["ga4_id"] = ga4_id
    if gsc_verify:
        payload["gsc_verify"] = gsc_verify
    if bing_verify:
        payload["bing_verify"] = bing_verify
    if head_code:
        payload["head_code"] = head_code
    if not payload:
        return json.dumps({"error": "no fields given - pass ga4_id, gsc_verify, bing_verify or head_code"})
    r = _request("POST", "/wppseo/v1/settings", payload=payload)
    return json.dumps(r, indent=2, ensure_ascii=False)


@mcp.tool()
def get_term_seo(term_id: int, site: str = "") -> str:
    """Read the SEO meta title + description for a TERM archive (category, tag, or
    custom taxonomy term). WordPress makes these archive pages but gives them no
    SEO meta - this does. Requires the wptaskify plugin. Use list_categories /
    list_tags to find term IDs."""
    _apply_site(site)
    r = _request("GET", "/wppseo/v1/term-seo", params={"term": term_id})
    return json.dumps(r, indent=2, ensure_ascii=False)


@mcp.tool()
def update_term_seo(term_id: int, title: str = "", description: str = "", site: str = "") -> str:
    """Set the SEO meta title and/or description for a TERM archive (category, tag,
    custom taxonomy term). Only non-empty fields change. Improves how the archive
    page ranks and appears in search. Requires the wptaskify plugin."""
    _require_tier('paid')
    _apply_site(site)
    payload = {"term": int(term_id)}
    if title:
        payload["title"] = title
    if description:
        payload["description"] = description
    if len(payload) == 1:
        return json.dumps({"error": "pass title and/or description to update"})
    r = _request("POST", "/wppseo/v1/term-seo", payload=payload)
    return json.dumps(r, indent=2, ensure_ascii=False)


@mcp.tool()
def get_author_seo(user_id: int, site: str = "") -> str:
    """Read the SEO meta title + description for an AUTHOR archive page. WordPress
    makes the author archive but gives it no SEO meta - this does. Requires the
    wptaskify plugin. Use list_authors / list_users to find user IDs."""
    _apply_site(site)
    r = _request("GET", "/wppseo/v1/author-seo", params={"user": user_id})
    return json.dumps(r, indent=2, ensure_ascii=False)


@mcp.tool()
def update_author_seo(user_id: int, title: str = "", description: str = "", site: str = "") -> str:
    """Set the SEO meta title and/or description for an AUTHOR archive page. Only
    non-empty fields change. Requires the wptaskify plugin."""
    _require_tier('paid')
    _apply_site(site)
    payload = {"user": int(user_id)}
    if title:
        payload["title"] = title
    if description:
        payload["description"] = description
    if len(payload) == 1:
        return json.dumps({"error": "pass title and/or description to update"})
    r = _request("POST", "/wppseo/v1/author-seo", payload=payload)
    return json.dumps(r, indent=2, ensure_ascii=False)


@mcp.tool()
def get_any_post_meta(post_id: int, key: str, site: str = "") -> str:
    """Low-level: read ANY custom meta field on a post by exact key name. Use the
    diagnostic /wg-seo/v1/keys endpoint names. For advanced/edge cases."""
    _apply_site(site)
    return json.dumps({"post_id": post_id, "key": key, "value": _seo_get(post_id, key)}, ensure_ascii=False)


@mcp.tool()
def set_any_post_meta(post_id: int, key: str, value: str, site: str = "") -> str:
    """Low-level: set ANY custom meta field on a post by exact key name. Use carefully."""
    _require_tier('paid')
    _apply_site(site)
    _seo_set(post_id, key, value)
    return json.dumps({"post_id": post_id, "key": key, "value": value[:120], "saved": True}, ensure_ascii=False)


@mcp.tool()
def verify_live_meta(post_id: int = 0, url: str = "", site: str = "") -> str:
    """Fetch the LIVE rendered page (cache-bypassed) and extract the ACTUAL meta tags
    Google sees: title, meta description, canonical, OG title/desc, Twitter, and which
    plugin/theme emitted them (looks for the <!-- cwg-seo --> marker). Use this to
    confirm an SEO edit really rendered. Pass post_id OR a full url."""
    _apply_site(site)
    if not url:
        if not post_id:
            return "Pass post_id or url."
        p = _v2("GET", f"/posts/{post_id}")
        url = p.get("link")
    # Cache-bust with a UNIQUE value each call - a static param (e.g. wgnocache=1)
    # can itself be cached by LiteSpeed/CDN, returning a stale page. A random,
    # never-before-seen query string forces a fresh render. Belt-and-suspenders
    # with strong no-cache headers.
    import time as _t, os as _os
    nonce = str(int(_t.time() * 1000)) + _os.urandom(4).hex()
    bust = url + ("&" if "?" in url else "?") + "wgnocache=" + nonce
    req = urllib.request.Request(bust, headers={
        "User-Agent": "Mozilla/5.0 (compatible; wptaskify-verify/1.0)",
        "Cache-Control": "no-cache, no-store, max-age=0",
        "Pragma": "no-cache",
        "X-LiteSpeed-Purge": "*",  # ask LiteSpeed to skip cache for this hit
    })
    html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "ignore")
    head = html[:html.find("</head>")] if "</head>" in html else html[:9000]

    def grab(pat, grp=1):
        m = _re.search(pat, head, _re.I | _re.S)
        return m.group(grp).strip() if m else None

    data = {
        "url": url,
        "title": grab(r"<title>(.*?)</title>"),
        "meta_description": grab(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']*)'),
        "canonical": grab(r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']*)'),
        "og_title": grab(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']*)'),
        "og_description": grab(r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']*)'),
        "twitter_title": grab(r'<meta[^>]+name=["\']twitter:title["\'][^>]+content=["\']([^"\']*)'),
        "emitted_by_cwg_theme": "<!-- cwg-seo -->" in head,
        "aioseo_present_in_head": "aioseo" in head.lower(),
    }
    return json.dumps(data, indent=2, ensure_ascii=False)


@mcp.tool()
def scan_aioseo_leftovers(site: str = "") -> str:
    """Count leftover _aioseo_* meta data still stored in the database (from the old
    All in One SEO plugin). These can conflict with your theme's _cwg_seo_* fields."""
    _apply_site(site)
    r = _request("GET", "/wg-seo/v1/aioseo-scan")
    return json.dumps(r, indent=2, ensure_ascii=False)


@mcp.tool()
def migrate_aioseo_meta(apply: bool = False, site: str = "") -> str:
    """One-shot migration: copy old All-in-One-SEO (_aioseo_*) meta into your theme's
    SEO fields (_cwg_seo_*), for ALL posts + pages in a SINGLE server-side pass (no
    per-post loop). SAFE: only fills EMPTY target fields (never overwrites SEO you
    set manually), resolves AIOSEO template tags (#post_title, #site_title,
    #separator_sa) into real text, and flags anything with an unresolved tag.

    Maps: _aioseo_title->title, _aioseo_description->description, _aioseo_keywords->
    focus keyword (first) + keywords, OG + Twitter title/description.

    apply=False (default) = DRY RUN: reports what WOULD migrate, writes nothing.
    apply=True = actually writes. After applying, verify a few posts with
    verify_live_meta, THEN run clean_aioseo_leftovers to remove the old rows.
    Requires the WaterGuide SEO bridge (mu-plugin)."""
    _require_tier('paid')
    _apply_site(site)
    r = _request("POST", "/wg-seo/v1/migrate", payload={"apply": bool(apply)})
    return json.dumps(r, indent=2, ensure_ascii=False)


@mcp.tool()
def clean_aioseo_leftovers(confirm: bool = False, site: str = "") -> str:
    """Delete ALL leftover _aioseo_* meta from every post (cleans old All in One SEO
    data so only your theme's _cwg_seo_* SEO fields remain). Pass confirm=True to run.
    This does NOT touch your _cwg_seo_* fields or post content. Run scan_aioseo_leftovers
    first to see what will be removed. IMPORTANT: if you still need the AIOSEO data,
    run migrate_aioseo_meta(apply=true) BEFORE this - cleaning is irreversible."""
    _require_tier('paid')
    _apply_site(site)
    if not confirm:
        r = _request("GET", "/wg-seo/v1/aioseo-scan")
        return json.dumps({"dry_run": True, "would_delete": r,
                           "note": "Call again with confirm=true to delete."}, indent=2, ensure_ascii=False)
    r = _request("POST", "/wg-seo/v1/aioseo-clean")
    return json.dumps({"cleaned": True, "result": r}, ensure_ascii=False)


@mcp.tool()
def audit_seo_fields(limit: int = 100, site: str = "") -> str:
    """Scan published posts and report which are MISSING SEO meta title, description,
    or focus keyword (the _cwg_seo_* fields). Great for finding posts to optimize."""
    _apply_site(site)
    problems = []
    for p in _all_posts(status="publish", limit=limit):
        pid = p["id"]
        t = _seo_get(pid, "_cwg_seo_title")
        d = _seo_get(pid, "_cwg_seo_description")
        fk = _seo_get(pid, "_cwg_seo_focus_kw")
        miss = []
        if not t:
            miss.append("title")
        if not d:
            miss.append("description")
        if not fk:
            miss.append("focus_kw")
        if miss:
            problems.append({"id": pid, "title": (p.get("title") or {}).get("raw", ""),
                             "missing": miss, "link": p.get("link")})
    return json.dumps({"posts_checked": "<=" + str(limit), "posts_with_seo_gaps": len(problems),
                       "posts": problems}, indent=2, ensure_ascii=False)


# ===========================================================================
# SITE INFO
# ===========================================================================
@mcp.tool()
def site_info(site: str = "") -> str:
    """Get site overview: name, description, URL, post/page counts, and active plugins."""
    _apply_site(site)
    root = _request("GET", "")
    counts = {}
    for t in ("posts", "pages"):
        try:
            req = urllib.request.Request(_cfg()["site_url"] + f"/wp-json/wp/v2/{t}?per_page=1",
                                         headers=_cfg()["base_headers"])
            with urllib.request.urlopen(req, timeout=30) as r:
                counts[t] = r.headers.get("X-WP-Total", "?")
        except Exception:
            counts[t] = "?"
    return json.dumps({
        "name": root.get("name"),
        "description": root.get("description"),
        "url": root.get("url") or root.get("home"),
        "total_posts": counts.get("posts"),
        "total_pages": counts.get("pages"),
    }, indent=2, ensure_ascii=False)


# ===========================================================================
# WP PILOT STUDIO - full build power (custom CSS, files, themes, plugins)
# These call the wptaskify Studio companion plugin (namespace wpps/v1), which
# backs up every file and PHP-lints before saving so edits can't crash the site.
# ===========================================================================
def _studio_available():
    """True if the wptaskify Studio plugin is installed & active on this site."""
    try:
        r = _request("GET", "/wpps/v1/info")
        return isinstance(r, dict) and r.get("plugin") == "wp-pilot-studio"
    except Exception:
        return False


def _studio_guard():
    """Return an error JSON string if Studio isn't available, else ''."""
    if _studio_available():
        return ""
    return json.dumps({
        "error": "The Studio features aren't available on this site.",
        "fix": "Make sure the wptaskify plugin is installed, active and updated to "
               "the latest version (it includes SEO + Studio: custom CSS, file "
               "editing, and theme/plugin creation).",
    })


@mcp.tool()
def studio_info(site: str = "") -> str:
    """Check whether wptaskify Studio (the build/file-editing companion plugin) is
    active, and what it can do. Use this before any CSS / file / theme / plugin
    build tool. Returns capabilities + allowed roots, or an install hint."""
    _apply_site(site)
    g = _studio_guard()
    if g:
        return g
    return json.dumps(_request("GET", "/wpps/v1/info"), indent=2, ensure_ascii=False)


@mcp.tool()
def set_custom_css(css: str, site: str = "") -> str:
    """Set the site-wide custom CSS (applies to the WHOLE site, every theme).
    This is the SAFEST way to restyle a site - colors, fonts, spacing, layout
    tweaks - because CSS can never crash PHP. REPLACES the current custom CSS;
    use get_custom_css first if you want to append. Requires wptaskify Studio.

    DESIGN WELL - apply real UI/UX craft: a small cohesive palette with strong
    contrast (WCAG AA), consistent 8px spacing, tasteful typography (readable body
    16-18px, line-height ~1.6), comfortable buttons with hover states, soft
    shadows/rounded corners, and subtle 150-250ms transitions. Keep it clean,
    modern and consistent - avoid clutter, tiny text, and clashing colors."""
    _require_tier('pro')
    _apply_site(site)
    g = _studio_guard()
    if g:
        return g
    r = _request("POST", "/wpps/v1/css", payload={"css": css})
    return json.dumps(r, indent=2, ensure_ascii=False)


@mcp.tool()
def get_custom_css(site: str = "") -> str:
    """Get the current site-wide custom CSS set via wptaskify Studio."""
    _apply_site(site)
    g = _studio_guard()
    if g:
        return g
    return json.dumps(_request("GET", "/wpps/v1/css"), indent=2, ensure_ascii=False)


@mcp.tool()
def list_theme_plugin_files(path: str, site: str = "") -> str:
    """List files/folders inside a theme, plugin or the uploads dir. `path` must
    start with 'themes/', 'plugins/' or 'uploads/' (e.g. 'themes/blocksy' or
    'plugins/wp-pilot-seo'). Use this to explore before reading/editing files.
    Requires wptaskify Studio."""
    _apply_site(site)
    g = _studio_guard()
    if g:
        return g
    r = _request("GET", "/wpps/v1/ls", params={"path": path})
    return json.dumps(r, indent=2, ensure_ascii=False)


@mcp.tool()
def read_theme_plugin_file(path: str, site: str = "") -> str:
    """Read a theme/plugin/uploads file's contents. `path` starts with 'themes/',
    'plugins/' or 'uploads/' (e.g. 'themes/blocksy/functions.php'). Requires
    wptaskify Studio. Read BEFORE editing so you preserve existing code."""
    _apply_site(site)
    g = _studio_guard()
    if g:
        return g
    r = _request("GET", "/wpps/v1/file", params={"path": path})
    return json.dumps(r, indent=2, ensure_ascii=False)


@mcp.tool()
def write_theme_plugin_file(path: str, contents: str, site: str = "") -> str:
    """Write (create or overwrite) a theme/plugin/uploads file. `path` starts with
    'themes/', 'plugins/' or 'uploads/'. The Studio plugin AUTOMATICALLY backs up
    any existing file and, for .php files, PHP-lints `contents` first - if the PHP
    is invalid the write is REFUSED (so a bad edit can't take the site down).

    ⚠️ RISKY EDIT - CONFIRM FIRST: Overwriting an EXISTING theme/plugin PHP file
    (especially functions.php, or any active theme/plugin file) can change how the
    live site behaves. Before calling this on an existing file, you MUST: (1) read
    the file first, (2) clearly WARN the user in plain language what you're about
    to change and the risk, and (3) get their explicit 'yes'. Creating a brand-new
    file, or editing CSS, is low-risk and doesn't need this ceremony. Always read
    the file first for edits. Requires wptaskify Studio."""
    _require_tier('pro')
    _apply_site(site)
    g = _studio_guard()
    if g:
        return g
    # SELF-PROTECTION (fast, client-side): wptaskify's own plugin is READ-ONLY to
    # the AI - it must never edit the plugin that powers the connection/Studio
    # guard. The plugin enforces this authoritatively too (WPPSEO_Studio_FS), but
    # we refuse early here for a clear message. Matches our known plugin slugs.
    _norm = path.replace("\\", "/").lower().lstrip("/")
    for _own in ("plugins/wp-pilot-seo/", "plugins/wptaskify-seo/", "plugins/wptaskify/"):
        if _norm.startswith(_own):
            return json.dumps({
                "error": "read_only",
                "message": "The wptaskify plugin itself is read-only. The AI cannot "
                           "modify its own plugin files (this protects the connection "
                           "and the safety guards). Edit your theme or another plugin "
                           "instead.",
                "path": path,
            }, indent=2, ensure_ascii=False)
    r = _request("POST", "/wpps/v1/file", payload={"path": path, "contents": contents})
    return json.dumps(r, indent=2, ensure_ascii=False)


@mcp.tool()
def create_plugin(slug: str, name: str = "", description: str = "", code: str = "", site: str = "") -> str:
    """Create a NEW WordPress plugin (folder + main file with a valid header).
    `slug` = folder/file name (lowercase-dashes). `code` = optional PHP body AFTER
    the header (do NOT include <?php or the header - those are added). Safe: a new
    plugin can't break existing code. Activate it separately if needed. Requires
    wptaskify Studio."""
    _require_tier('pro')
    _apply_site(site)
    g = _studio_guard()
    if g:
        return g
    r = _request("POST", "/wpps/v1/create-plugin",
                 payload={"slug": slug, "name": name or slug,
                          "description": description, "code": code})
    return json.dumps(r, indent=2, ensure_ascii=False)


@mcp.tool()
def create_theme(slug: str, name: str = "", style_css: str = "",
                 index_php: str = "", functions_php: str = "", site: str = "") -> str:
    """Create a NEW WordPress theme (style.css + index.php + functions.php).
    `slug` = folder name. `style_css` = CSS (a Theme Name header is added if
    missing). `index_php`/`functions_php` = optional PHP (lint-checked). Safe:
    creating a theme doesn't affect the active one until you activate it with
    activate_theme. Requires wptaskify Studio.

    DESIGN IT WELL - you are a senior UI/UX designer. Make it modern and
    professional, not generic: centered max-width (~1100-1280px), generous
    whitespace, an 8px spacing scale, one tasteful font pairing (16-18px body,
    line-height 1.6), a small cohesive color palette with strong contrast (WCAG
    AA), a clear hero (headline + subtext + one CTA), cards with soft shadow +
    radius, comfortable buttons with hover states, SVG icons (not emoji), subtle
    150-250ms transitions, and FULLY responsive mobile-first layout. Pick one
    consistent style that fits the site's topic."""
    _require_tier('pro')
    _apply_site(site)
    g = _studio_guard()
    if g:
        return g
    r = _request("POST", "/wpps/v1/create-theme",
                 payload={"slug": slug, "name": name or slug, "style_css": style_css,
                          "index_php": index_php, "functions_php": functions_php})
    return json.dumps(r, indent=2, ensure_ascii=False)


@mcp.tool()
def preview_theme(slug: str, site: str = "") -> str:
    """Get a SAFE PREVIEW link for a theme WITHOUT activating it - only the
    logged-in admin sees the preview; visitors keep seeing the current live theme.
    This is the 'staging' step: create_theme -> preview_theme -> (looks good?) ->
    activate_theme. ALWAYS preview a new theme and let the user confirm it looks
    right before activating. Requires wptaskify Studio."""
    _require_tier('pro')
    _apply_site(site)
    g = _studio_guard()
    if g:
        return g
    r = _request("POST", "/wpps/v1/preview-theme", payload={"slug": slug})
    return json.dumps(r, indent=2, ensure_ascii=False)


@mcp.tool()
def activate_theme(slug: str, site: str = "") -> str:
    """Activate a theme by its slug (folder name) - makes it LIVE for all visitors.

    STAGING FLOW - don't surprise the user: for a newly built theme, first call
    preview_theme and share the preview link so they can check it safely, and get
    their OK, THEN activate. The plugin remembers the previous theme, so if the new
    one looks wrong live you can call rollback_theme to restore it instantly.
    Requires wptaskify Studio."""
    _require_tier('pro')
    _apply_site(site)
    g = _studio_guard()
    if g:
        return g
    r = _request("POST", "/wpps/v1/activate-theme", payload={"slug": slug})
    return json.dumps(r, indent=2, ensure_ascii=False)


@mcp.tool()
def rollback_theme(site: str = "") -> str:
    """Instantly switch back to the theme that was active BEFORE the last
    activate_theme. Use if a newly activated theme looks broken or wrong on the
    live site. Requires wptaskify Studio."""
    _require_tier('pro')
    _apply_site(site)
    g = _studio_guard()
    if g:
        return g
    r = _request("POST", "/wpps/v1/rollback-theme", payload={})
    return json.dumps(r, indent=2, ensure_ascii=False)


@mcp.tool()
def list_themes(site: str = "") -> str:
    """List all installed themes with name, version, and which one is ACTIVE. Use
    this before activating/previewing/editing a theme. Requires wptaskify Studio."""
    _apply_site(site)
    g = _studio_guard()
    if g:
        return g
    return json.dumps(_request("GET", "/wpps/v1/themes"), indent=2, ensure_ascii=False)


@mcp.tool()
def list_plugins(site: str = "") -> str:
    """List all installed plugins with name, version, file, and active/inactive
    state. Requires wptaskify Studio."""
    _apply_site(site)
    g = _studio_guard()
    if g:
        return g
    return json.dumps(_request("GET", "/wpps/v1/plugins"), indent=2, ensure_ascii=False)


@mcp.tool()
def activate_plugin(plugin_file: str, site: str = "") -> str:
    """Activate an installed plugin by its file (e.g. 'akismet/akismet.php' - get
    it from list_plugins). Requires wptaskify Studio."""
    _require_tier('pro')
    _apply_site(site)
    g = _studio_guard()
    if g:
        return g
    r = _request("POST", "/wpps/v1/plugin-state",
                 payload={"file": plugin_file, "action": "activate"})
    return json.dumps(r, indent=2, ensure_ascii=False)


@mcp.tool()
def deactivate_plugin(plugin_file: str, site: str = "") -> str:
    """Deactivate an active plugin by its file (from list_plugins). wptaskify cannot
    deactivate itself. This can change site behaviour - WARN the user and confirm
    first. Requires wptaskify Studio."""
    _require_tier('pro')
    _apply_site(site)
    g = _studio_guard()
    if g:
        return g
    r = _request("POST", "/wpps/v1/plugin-state",
                 payload={"file": plugin_file, "action": "deactivate"})
    return json.dumps(r, indent=2, ensure_ascii=False)


@mcp.tool()
def full_site_backup(include_uploads: bool = False, site: str = "") -> str:
    """Take a FULL backup of the site's code (all themes + plugins) plus a snapshot
    of the active theme/plugins - one zip you can restore from. Set include_uploads
    True to also back up the media library (can be large). Returns a backup_id to
    use with restore_site_backup. Do this BEFORE big/risky changes. Requires WP
    Pilot Studio."""
    _require_tier('pro')
    _apply_site(site)
    g = _studio_guard()
    if g:
        return g
    r = _request("POST", "/wpps/v1/site-backup", payload={"include_uploads": include_uploads})
    return json.dumps(r, indent=2, ensure_ascii=False)


@mcp.tool()
def restore_site_backup(backup_id: str, site: str = "") -> str:
    """Restore a full-site backup by its backup_id (from full_site_backup). This
    overwrites theme/plugin files and restores the active theme/plugins. RISKY -
    WARN the user and confirm first. Requires wptaskify Studio."""
    _require_tier('pro')
    _apply_site(site)
    g = _studio_guard()
    if g:
        return g
    r = _request("POST", "/wpps/v1/site-restore", payload={"backup_id": backup_id})
    return json.dumps(r, indent=2, ensure_ascii=False)


@mcp.tool()
def install_plugin_from_repo(slug: str, activate: bool = False, site: str = "") -> str:
    """Install a plugin from the WordPress.org repository by its slug (e.g.
    'wordpress-seo', 'contact-form-7'). Set activate=True to also activate it.
    Requires wptaskify Studio."""
    _require_tier('pro')
    _apply_site(site)
    g = _studio_guard()
    if g:
        return g
    r = _request("POST", "/wpps/v1/install-plugin", payload={"slug": slug, "activate": activate})
    return json.dumps(r, indent=2, ensure_ascii=False)


@mcp.tool()
def check_site_health(site: str = "") -> str:
    """Report site health: PHP & WP version, active theme, plugin counts, DB size,
    HTTPS, debug mode, memory limit. Good for a quick diagnostic. Requires wptaskify
    Studio."""
    _apply_site(site)
    g = _studio_guard()
    if g:
        return g
    return json.dumps(_request("GET", "/wpps/v1/health"), indent=2, ensure_ascii=False)


@mcp.tool()
def get_wp_option(key: str, site: str = "") -> str:
    """Read ANY WordPress option/setting by key (e.g. 'blogname', 'posts_per_page',
    'timezone_string'). Requires wptaskify Studio."""
    _apply_site(site)
    g = _studio_guard()
    if g:
        return g
    return json.dumps(_request("GET", "/wpps/v1/option", params={"key": key}),
                      indent=2, ensure_ascii=False)


@mcp.tool()
def update_wp_option(key: str, value: str, site: str = "") -> str:
    """Write ANY WordPress option/setting by key. A few lock-out-risk options
    (siteurl, home, admin_email) are protected. Some changes affect the whole site
    - for risky ones, warn the user first. Requires wptaskify Studio."""
    _require_tier('pro')
    _apply_site(site)
    g = _studio_guard()
    if g:
        return g
    r = _request("POST", "/wpps/v1/option", payload={"key": key, "value": value})
    return json.dumps(r, indent=2, ensure_ascii=False)


@mcp.tool()
def edit_robots_txt(contents: str = "", get_only: bool = False,
                    delete_physical: bool = False, site: str = "") -> str:
    """Get or set the site's robots.txt (served via WordPress). Pass get_only=True
    to just read it. Setting it controls what search engines can crawl - be careful
    not to block the whole site.

    IMPORTANT: If a PHYSICAL robots.txt file exists at the site root, the web server
    serves THAT file and this WordPress override is ignored. get_only=True reports
    `physical_exists`; if true, tell the user, and pass delete_physical=True (when the
    file is writable) to remove it so your override takes effect. Requires wptaskify
    Studio."""
    _require_tier('pro')
    _apply_site(site)
    g = _studio_guard()
    if g:
        return g
    if get_only:
        return json.dumps(_request("GET", "/wpps/v1/robots"), indent=2, ensure_ascii=False)
    payload = {"robots": contents}
    if delete_physical:
        payload["delete_physical"] = True
    r = _request("POST", "/wpps/v1/robots", payload=payload)
    return json.dumps(r, indent=2, ensure_ascii=False)


@mcp.tool()
def edit_htaccess(contents: str = "", get_only: bool = False, site: str = "") -> str:
    """Get or set the root .htaccess file. RISKY - a wrong rule can break the whole
    site (500 error). The plugin backs up the old file first. Always read it first
    (get_only=True), WARN the user, and confirm before writing. Requires wptaskify
    Studio."""
    _require_tier('pro')
    _apply_site(site)
    g = _studio_guard()
    if g:
        return g
    if get_only:
        return json.dumps(_request("GET", "/wpps/v1/htaccess"), indent=2, ensure_ascii=False)
    r = _request("POST", "/wpps/v1/htaccess", payload={"contents": contents})
    return json.dumps(r, indent=2, ensure_ascii=False)


@mcp.tool()
def get_activity_log(site: str = "") -> str:
    """Get the recent wptaskify activity log (what the AI changed on this site).
    Requires wptaskify Studio."""
    _apply_site(site)
    g = _studio_guard()
    if g:
        return g
    return json.dumps(_request("GET", "/wpps/v1/activity"), indent=2, ensure_ascii=False)


@mcp.tool()
def edit_llms_txt(contents: str = "", get_only: bool = False, site: str = "") -> str:
    """Get or set the site's /llms.txt - the AI-friendly index (like robots.txt but
    for LLMs / AI answer engines). It tells ChatGPT, Perplexity, Gemini etc. what
    the site is about and which pages matter, so they understand and CITE it better
    (GEO/AEO). get_only=True reads current state; passing `contents` sets a custom
    llms.txt (empty string = back to auto-generated from the site). Great to write
    a curated, well-described index of your best content. Requires wptaskify Studio."""
    _require_tier('pro')
    _apply_site(site)
    g = _studio_guard()
    if g:
        return g
    if get_only:
        return json.dumps(_request("GET", "/wpps/v1/llms"), indent=2, ensure_ascii=False)
    r = _request("POST", "/wpps/v1/llms", payload={"contents": contents})
    return json.dumps(r, indent=2, ensure_ascii=False)


@mcp.tool()
def bulk_optimize_images(limit: int = 30, quality: int = 80,
                         to_webp: bool = False, apply: bool = False, site: str = "") -> str:
    """Compress the media library's JPEG/PNG images (and optionally convert to
    WebP) to speed up the site. `quality` 40-95 (default 80). to_webp=True writes
    .webp copies. apply=False previews sizes; apply=True actually processes (backs
    up originals first when compressing in place). Returns bytes saved. Requires
    wptaskify Studio."""
    _require_tier('pro')
    _apply_site(site)
    g = _studio_guard()
    if g:
        return g
    r = _request("POST", "/wpps/v1/optimize-images",
                 payload={"limit": limit, "quality": quality, "to_webp": to_webp, "apply": apply})
    return json.dumps(r, indent=2, ensure_ascii=False)


@mcp.tool()
def list_studio_backups(site: str = "") -> str:
    """List the automatic file backups wptaskify Studio has made (before each edit).
    Useful to reassure the user their originals are saved. Requires wptaskify Studio."""
    _apply_site(site)
    g = _studio_guard()
    if g:
        return g
    return json.dumps(_request("GET", "/wpps/v1/backups"), indent=2, ensure_ascii=False)


# ===========================================================================
# MULTI-SITE - a user can connect several WordPress sites. By default the AI works
# on the primary site; these tools let it see all sites and switch between them.
# ===========================================================================
@mcp.tool()
def list_my_sites() -> str:
    """List ALL WordPress sites connected to this account (URL + which one is
    active right now). If you have more than one site, use `use_site` to choose
    which one the tools act on before running commands on it. Also use this if a
    tool says no site is connected - it confirms whether any site exists."""
    import db as _db
    # Read the uid even when no site is connected (no_site context), so we can tell
    # the user "you have no sites, add one" instead of erroring.
    _raw = _call_site_cfg.get() or current_tenant.get() or {}
    uid = _raw.get("user_id")
    if not uid:
        return json.dumps({"error": "no user context"})
    sites = _db.list_user_sites(uid)
    active_sites = [s for s in sites if s.get("status", "active") == "active"]
    if not active_sites:
        return json.dumps({
            "count": 0, "sites": [],
            "message": "No WordPress site is connected to your wptaskify account yet. "
                       "Add your site first: install the free wptaskify plugin on your "
                       "WordPress site and click Connect (or add it from your wptaskify "
                       "dashboard at https://wptaskify.com/dashboard). Then your tools "
                       "will work."}, indent=2, ensure_ascii=False)
    sites = _db.list_user_sites(uid)
    active = _cfg().get("site_url", "").rstrip("/")
    out = [{"id": s["id"], "site_url": s["site_url"],
            "active": (s["site_url"] or "").rstrip("/") == active,
            "primary": s.get("is_primary")}
           for s in sites if s.get("status", "active") == "active"]
    return json.dumps({"count": len(out), "active_site": active, "sites": out},
                      indent=2, ensure_ascii=False)


@mcp.tool()
def use_site(site: str) -> str:
    """Switch which connected WordPress site the tools act on. `site` can be the
    site's URL (e.g. 'https://completewaterguide.com' or just 'completewaterguide'),
    or its id. All following tool calls in this conversation act on that site until
    you switch again. Use list_my_sites first to see your options. Essential when
    you have connected more than one site."""
    import db as _db
    import base64 as _b64
    cfg = _cfg()
    uid = cfg.get("user_id")
    if not uid:
        return json.dumps({"error": "no user context"})
    match = _db.get_site_by_ref(uid, site)
    if not match:
        sites = [s["site_url"] for s in _db.list_user_sites(uid) if s.get("status", "active") == "active"]
        return json.dumps({"error": f"no connected site matches '{site}'.",
                           "your_sites": sites}, indent=2, ensure_ascii=False)
    # 1) Persist the choice so it survives across MCP requests (each request re-
    #    resolves the tenant from the DB, so an in-memory swap alone wouldn't stick).
    try:
        _db.set_active_site(uid, match["id"])
    except Exception as e:  # noqa: BLE001
        return json.dumps({"error": f"could not save site choice: {str(e)[:80]}"})
    # 2) Also swap the CURRENT request's creds in place so THIS turn's later tool
    #    calls already hit the chosen site.
    token = _b64.b64encode(
        f"{match['wp_username']}:{match['app_password'].replace(' ', '')}".encode()).decode()
    cfg["site_url"] = match["site_url"].rstrip("/")
    cfg["base_headers"] = {"Authorization": "Basic " + token, "User-Agent": "wp-mcp/3.0"}
    return json.dumps({"switched_to": cfg["site_url"], "site_id": match["id"],
                       "note": "All tools now act on this site until you switch again."},
                      indent=2, ensure_ascii=False)


# ===========================================================================
# GOOGLE ANALYTICS (GA4) + SEARCH CONSOLE - review the user's own traffic data.
# The user connects their Google account once (Connect Google Analytics in the
# dashboard); these tools read it live. Read-only.
# ===========================================================================
def _current_site_id():
    """Best-effort: the DB id of the site the tools are currently acting on, so we
    can look up THAT site's own Google account (each site can connect a different
    Gmail for its Search Console). Returns None if it can't be resolved (then the
    user-level default Google connection is used)."""
    import db as _db
    cfg = _cfg()
    uid = cfg.get("user_id")
    su = (cfg.get("site_url") or "").rstrip("/")
    if not uid or not su:
        return None
    try:
        m = _db.get_site_by_ref(uid, su)
        return m.get("id") if m else None
    except Exception:
        return None


def _google_ctx():
    """Return (access_token, account) for the CURRENT SITE's Google connection (or
    the user-level default), or raise a friendly error."""
    import db as _db
    import google_api as _g
    uid = _cfg().get("user_id")
    if not uid:
        raise RuntimeError("No user context for this request.")
    sid = _current_site_id()
    rt = _db.get_google_refresh_token(uid, site_id=sid)
    if not rt:
        raise RuntimeError("Google Analytics is not connected for this site. Open your "
                           "wptaskify dashboard, select this site, and click "
                           "'Connect Google Analytics'.")
    at = _g.access_token(rt)
    if not at:
        raise RuntimeError("Could not refresh Google access - please reconnect Google "
                           "Analytics from your dashboard.")
    acct = _db.get_google_account(uid, site_id=sid)
    return at, acct


def _ga_property(acct):
    pid = (acct or {}).get("ga_property_id") or ""
    if not pid:
        raise RuntimeError("No GA4 property selected yet. Use ga_list_properties to see "
                           "your properties, then pick one in the dashboard (or it will "
                           "be set automatically if you have only one).")
    return pid


@mcp.tool()
def ga_status() -> str:
    """Check whether the user has connected Google Analytics + Search Console, and
    which GA4 property / Search Console site is selected. Use this first."""
    import db as _db
    import google_api as _g
    uid = _cfg().get("user_id")
    if not uid:
        return json.dumps({"connected": False, "error": "no user context"})
    sid = _current_site_id()
    acct = _db.get_google_account(uid, site_id=sid)
    acct["google_configured"] = _g.configured()
    acct["for_site"] = _cfg().get("site_url", "")
    return json.dumps(acct, indent=2, ensure_ascii=False)


@mcp.tool()
def ga_list_properties() -> str:
    """List the Google Analytics 4 properties and Search Console sites this user's
    Google account can access, so they can pick which to use. If exactly one GA4
    property exists it is auto-selected."""
    import db as _db
    import google_api as _g
    at, acct = _google_ctx()
    props, ga_err = _g.list_ga_properties(at)
    sites, sc_err = _g.list_sc_sites(at)
    uid = _cfg().get("user_id")
    sid = _current_site_id()
    # Auto-select a lone property / site for convenience.
    if len(props) == 1 and not acct.get("ga_property_id"):
        _db.set_google_selection(uid, ga_property_id=props[0]["property_id"], site_id=sid)
        acct["ga_property_id"] = props[0]["property_id"]
    if len(sites) == 1 and not acct.get("sc_site"):
        _db.set_google_selection(uid, sc_site=sites[0]["site"], site_id=sid)
        acct["sc_site"] = sites[0]["site"]
    out = {"ga4_properties": props, "search_console_sites": sites,
           "selected_property": acct.get("ga_property_id", ""),
           "selected_sc_site": acct.get("sc_site", "")}
    # Surface real errors instead of a silent empty list (the usual cause is an API
    # not enabled in the Google Cloud project, or no properties on this account).
    if ga_err:
        out["ga_error"] = ga_err
        if "SERVICE_DISABLED" in ga_err or "has not been used" in ga_err or "403" in ga_err:
            out["ga_hint"] = ("Enable the 'Google Analytics Admin API' in your Google "
                              "Cloud project (APIs & Services > Library), then reconnect.")
    if sc_err:
        out["sc_error"] = sc_err
        if "SERVICE_DISABLED" in sc_err or "has not been used" in sc_err or "403" in sc_err:
            out["sc_hint"] = ("Enable the 'Google Search Console API' in your Google "
                              "Cloud project, and make sure this Google account has a "
                              "verified Search Console site.")
    if not props and not ga_err:
        out["ga_note"] = "No GA4 properties found on this Google account."
    if not sites and not sc_err:
        out["sc_note"] = "No Search Console sites found on this Google account."
    return json.dumps(out, indent=2, ensure_ascii=False)


@mcp.tool()
def ga_select(ga_property_id: str = "", sc_site: str = "") -> str:
    """Choose WHICH Google Analytics 4 property and/or Search Console site to use
    for this account. Pass a GA4 property ID (digits, e.g. '123456789') and/or a
    Search Console site URL exactly as shown by ga_list_properties (e.g.
    'https://completewaterguide.com/'). Only non-empty values change. Requires a
    connected Google account."""
    import db as _db
    uid = _cfg().get("user_id")
    if not uid:
        return json.dumps({"error": "no user context"})
    sid = _current_site_id()
    if not _db.get_google_refresh_token(uid, site_id=sid):
        return json.dumps({"error": "Google is not connected for this site. Connect it in the dashboard first."})
    if not ga_property_id and not sc_site:
        return json.dumps({"error": "pass ga_property_id and/or sc_site to select."})
    _db.set_google_selection(uid,
                             ga_property_id=ga_property_id.strip() if ga_property_id else None,
                             sc_site=sc_site.strip() if sc_site else None, site_id=sid)
    return json.dumps(_db.get_google_account(uid, site_id=sid), indent=2, ensure_ascii=False)


@mcp.tool()
def ga_overview(days: int = 28) -> str:
    """Google Analytics traffic overview for the last `days`: users, sessions,
    pageviews, engagement, bounce, avg session duration. Requires a connected
    Google account + selected GA4 property (see ga_status / ga_list_properties)."""
    _require_tier('paid')
    import google_api as _g
    at, acct = _google_ctx()
    pid = _ga_property(acct)
    rows = _g.ga_run_report(
        at, pid, dimensions=[],
        metrics=["totalUsers", "sessions", "screenPageViews", "engagedSessions",
                 "engagementRate", "bounceRate", "averageSessionDuration"],
        start_date=f"{int(days)}daysAgo", end_date="today", limit=1)
    return json.dumps({"property": pid, "period_days": days,
                       "overview": rows[0] if rows else {}}, indent=2, ensure_ascii=False)


@mcp.tool()
def ga_top_pages(days: int = 28, limit: int = 15) -> str:
    """Top pages by pageviews in the last `days` (path, views, users, avg engagement).
    Great for finding your best content. Requires a connected GA4 property."""
    _require_tier('paid')
    import google_api as _g
    at, acct = _google_ctx()
    pid = _ga_property(acct)
    rows = _g.ga_run_report(
        at, pid, dimensions=["pagePath"],
        metrics=["screenPageViews", "totalUsers", "averageSessionDuration"],
        start_date=f"{int(days)}daysAgo", end_date="today",
        limit=limit, order_metric="screenPageViews")
    return json.dumps({"property": pid, "period_days": days, "top_pages": rows},
                      indent=2, ensure_ascii=False)


@mcp.tool()
def ga_traffic_sources(days: int = 28, limit: int = 15) -> str:
    """Where traffic comes from in the last `days`: channel + source/medium with
    users and sessions. Shows organic vs direct vs referral vs social. Requires a
    connected GA4 property."""
    _require_tier('paid')
    import google_api as _g
    at, acct = _google_ctx()
    pid = _ga_property(acct)
    rows = _g.ga_run_report(
        at, pid, dimensions=["sessionDefaultChannelGroup", "sessionSourceMedium"],
        metrics=["totalUsers", "sessions"],
        start_date=f"{int(days)}daysAgo", end_date="today",
        limit=limit, order_metric="sessions")
    return json.dumps({"property": pid, "period_days": days, "sources": rows},
                      indent=2, ensure_ascii=False)


@mcp.tool()
def ga_search_queries(days: int = 28, limit: int = 25) -> str:
    """Google Search Console: the top search QUERIES bringing you clicks in the last
    `days` (query, clicks, impressions, CTR%, avg position). This is real Google
    search data. Requires a connected Search Console site (see ga_status)."""
    _require_tier('paid')
    import google_api as _g
    import datetime as _dt  # only for formatting the date window
    at, acct = _google_ctx()
    site = (acct or {}).get("sc_site") or ""
    if not site:
        return json.dumps({"error": "No Search Console site selected. Use ga_list_properties "
                                    "then pick one in the dashboard."})
    # Search Console needs explicit YYYY-MM-DD; data lags ~2-3 days.
    end = _dt.date.today() - _dt.timedelta(days=3)
    start = end - _dt.timedelta(days=int(days))
    rows = _g.sc_query(at, site, dimensions=["query"],
                       start_date=start.isoformat(), end_date=end.isoformat(), limit=limit)
    return json.dumps({"site": site, "from": start.isoformat(), "to": end.isoformat(),
                       "top_queries": rows}, indent=2, ensure_ascii=False)


@mcp.tool()
def ga_search_pages(days: int = 28, limit: int = 25) -> str:
    """Google Search Console: the top PAGES by clicks from Google search in the last
    `days` (page, clicks, impressions, CTR%, avg position). Requires a connected
    Search Console site."""
    _require_tier('paid')
    import google_api as _g
    import datetime as _dt
    at, acct = _google_ctx()
    site = (acct or {}).get("sc_site") or ""
    if not site:
        return json.dumps({"error": "No Search Console site selected."})
    end = _dt.date.today() - _dt.timedelta(days=3)
    start = end - _dt.timedelta(days=int(days))
    rows = _g.sc_query(at, site, dimensions=["page"],
                       start_date=start.isoformat(), end_date=end.isoformat(), limit=limit)
    return json.dumps({"site": site, "from": start.isoformat(), "to": end.isoformat(),
                       "top_pages": rows}, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    mcp.settings.host = "0.0.0.0"
    mcp.settings.port = int(os.environ.get("PORT", "8000"))
    mcp.run(transport="streamable-http")
