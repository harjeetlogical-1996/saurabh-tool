"""
Multi-tenant startup + ASGI middleware for the WordPress MCP SaaS.

Two modes:
  - MULTI-TENANT (DATABASE_URL set): users sign up, add their WP site, connect
    Claude/ChatGPT via OAuth. Each request resolves its tenant's credentials.
  - STANDALONE (WP_* env vars, no DB): single site, like before - for local testing.

Web routes (multi-tenant):
  GET  /                 -> simple landing/login/signup page (HTML)
  POST /signup           -> create user, set session cookie
  POST /login            -> authenticate, set session cookie
  POST /sites            -> add a WordPress site (validates + encrypts)
  GET  /dashboard        -> show user's sites + connect instructions
OAuth routes: /.well-known/*, /register, /authorize, /token  (tenant-aware)
MCP route: /mcp  (Bearer access token -> tid -> tenant credentials)
"""
import asyncio
import json
import os
import re
import sys
import time
import hmac
import hashlib
import base64
import pathlib
import urllib.request
import urllib.error
import urllib.parse

HERE = pathlib.Path(__file__).resolve().parent
CONFIG = HERE.parent / "wp-config.local.json"

cfg = json.loads(CONFIG.read_text(encoding="utf-8")) if CONFIG.exists() else {}

# Env vars fill/override the file config
for k, env in [("site_url", "WP_SITE_URL"), ("username", "WP_USERNAME"),
               ("app_password", "WP_APP_PASSWORD"), ("gemini_api_key", "GEMINI_API_KEY"),
               ("oauth_secret", "OAUTH_SECRET"), ("public_url", "PUBLIC_URL")]:
    if os.environ.get(env):
        cfg[k] = os.environ[env]

DATABASE_URL = os.environ.get("DATABASE_URL", "")
MULTI_TENANT = bool(DATABASE_URL)

# Standalone fallback needs WP creds in env for server.py's _DEFAULT_TENANT
if cfg.get("site_url"):
    os.environ.setdefault("WP_SITE_URL", cfg["site_url"])
if cfg.get("username"):
    os.environ.setdefault("WP_USERNAME", cfg["username"])
if cfg.get("app_password"):
    os.environ.setdefault("WP_APP_PASSWORD", cfg["app_password"])
if cfg.get("gemini_api_key") and "YAHAN" not in cfg.get("gemini_api_key", ""):
    os.environ.setdefault("GEMINI_API_KEY", cfg["gemini_api_key"])
os.environ.setdefault("PORT", "8000")

if not MULTI_TENANT and not cfg.get("app_password"):
    sys.exit("Need DATABASE_URL (multi-tenant) OR WP_* env vars (standalone).")

PUBLIC_URL = os.environ.get("PUBLIC_URL", cfg.get("public_url", "")).rstrip("/")
OAUTH_SECRET = cfg.get("oauth_secret") or os.environ.get("OAUTH_SECRET") or "change-me-secret"
SESSION_SECRET_RAW = os.environ.get("SESSION_SECRET") or OAUTH_SECRET
# Fail-closed: never boot a real (multi-tenant) deployment with a missing/default secret.
# The default is public in the source, so it would let anyone forge session cookies and
# OAuth tokens for any account. A strong OAUTH_SECRET / SESSION_SECRET is mandatory.
_WEAK_SECRETS = {"", "change-me-secret", "change-me", "secret", "changeme"}


def _weak_secret(s):
    return (s or "").strip().lower() in _WEAK_SECRETS or len(s or "") < 16


# Both secrets are security-critical (OAuth tokens AND session cookies). Check EACH -
# a strong OAUTH_SECRET but a weak, separately-set SESSION_SECRET would still be forgeable.
if MULTI_TENANT and (_weak_secret(OAUTH_SECRET) or _weak_secret(SESSION_SECRET_RAW)):
    sys.exit("FATAL: OAUTH_SECRET and SESSION_SECRET must each be a strong random secret "
             "(>= 16 chars, not a default). Set them in the environment before starting.")
SESSION_SECRET = SESSION_SECRET_RAW.encode()

# Maintenance mode (off by default). Set MAINTENANCE=on to enable.
MAINTENANCE_ON = os.environ.get("MAINTENANCE", "").lower() in ("on", "1", "true", "yes")

# Built-in AI chat is HIDDEN for launch - we sell only the connect-your-own-AI
# plans for now. Code is kept intact; set ENABLE_BUILTIN_CHAT=on to bring it back.
BUILTIN_CHAT_ON = os.environ.get("ENABLE_BUILTIN_CHAT", "").lower() in ("on", "1", "true", "yes")
# Email-verification gate (A1). Default ON: unverified users are held at /verify-sent.
# The gate must NOT silently disable itself just because the Resend key is missing/broken -
# that would let everyone in unverified. Set REQUIRE_EMAIL_VERIFY=0 ONLY to intentionally
# turn verification off (e.g. a deploy with no mail provider by design).
REQUIRE_EMAIL_VERIFY = os.environ.get("REQUIRE_EMAIL_VERIFY", "1").lower() not in ("0", "off", "false", "no")
# Maintenance-mode bypass key. If not explicitly set, use a random per-boot value so it
# can never be guessed (the operator sets MAINTENANCE_KEY when they need a stable bypass).
MAINT_KEY = os.environ.get("MAINTENANCE_KEY") or base64.urlsafe_b64encode(os.urandom(12)).decode().rstrip("=")
# Stripe keys are read inside billing.py from STRIPE_SECRET_KEY / STRIPE_WEBHOOK_SECRET.

# ---------------------------------------------------------------------------
# Public pages -> the SINGLE source of truth for BOTH /sitemap.xml and /llms.txt.
# Add a new public marketing/legal page HERE once, as:
#   (path, changefreq, priority, title, llms_description)
# and it AUTOMATICALLY appears in the sitemap and (if it has a title) in llms.txt.
# Leave title/description "" to keep a page out of the llms.txt "core pages" list.
# Blog articles are pulled from the DB automatically (see _build_sitemap).
# ---------------------------------------------------------------------------
PUBLIC_PAGES = [
    ("/",             "weekly",  "1.0", "Home",         "What wptaskify is and how it connects WordPress to AI."),
    ("/features",     "weekly",  "0.9", "Features",     "100+ WordPress tools the AI can use."),
    ("/services",     "weekly",  "0.9", "AI Development Services", "Custom AI tools, integrations, apps and content - built for you."),
    ("/services/custom-ai-tools",     "monthly", "0.7", "Custom AI Tool & Plugin Development", "We build custom AI tools and WordPress plugins to your spec."),
    ("/services/wordpress-ai-setup",  "monthly", "0.7", "AI Integration Services",      "Add AI to your existing site, data and workflows."),
    ("/services/ai-content-writing",  "monthly", "0.7", "AI Apps & AI Content",         "AI web apps built from scratch, plus done-for-you AI content."),
    ("/services/ai-seo-optimization", "monthly", "0.7", "AI SEO Services",              "Rank on Google and get cited by AI search engines."),
    ("/pricing",      "weekly",  "0.9", "Pricing",      "Free to start; Starter $20/mo, Pro $99/mo."),
    ("/tools",        "weekly",  "0.8", "Tools",        "The full list of WordPress tools driven by Claude or ChatGPT."),
    ("/how-it-works", "weekly",  "0.8", "How it works", "2-minute setup - connect, link your AI, ask."),
    ("/faq",          "weekly",  "0.7", "FAQ",          "Common questions about connecting WordPress to Claude/ChatGPT."),
    ("/security",     "monthly", "0.7", "Security",     "How wptaskify handles credentials, permissions and the approval workflow."),
    ("/community",    "daily",   "0.7", "Community",    "Ask questions and share tips on connecting WordPress to AI."),
    ("/blog",         "weekly",  "0.6", "Blog",         "Guides on AI, WordPress, SEO, AEO and GEO."),
    ("/about",        "monthly", "0.5", "About",        "What wptaskify is and who it's for."),
    ("/contact",      "monthly", "0.5", "Contact",      "Get support or ask a question."),
    ("/terms",        "monthly", "0.3", "Terms",        ""),
    ("/privacy",      "monthly", "0.3", "Privacy",      ""),
    ("/refund",       "monthly", "0.3", "Refund Policy", ""),
    ("/shipping",     "monthly", "0.3", "Delivery Policy", ""),
]


def _published_blog_posts():
    """Best-effort list of published blog posts as (slug, lastmod, title, desc).
    Empty if the app has no blog store yet - callers must tolerate an empty list."""
    out = []
    try:
        lister = getattr(db, "list_published_blog_slugs", None)
        if callable(lister):
            for item in (lister() or []):
                if isinstance(item, dict):
                    slug = item.get("slug", "")
                    mod = str(item.get("updated") or "")[:10]
                    title = item.get("title", "")
                    desc = item.get("description", "")
                else:
                    slug, mod, title, desc = str(item), "", "", ""
                if slug:
                    out.append((slug, mod, title, desc))
    except Exception:
        pass
    return out


def _build_sitemap():
    """Generate sitemap.xml from PUBLIC_PAGES + any published blog posts in the DB.
    Fully automatic: new static pages come from PUBLIC_PAGES, blog articles are
    discovered from the DB, and lastmod is refreshed on every request."""
    lastmod = time.strftime("%Y-%m-%d", time.gmtime())
    entries = [(p, freq, pri, lastmod) for (p, freq, pri, _t, _d) in PUBLIC_PAGES]
    for slug, mod, _t, _d in _published_blog_posts():
        entries.append((f"/blog/{slug}", "monthly", "0.6", mod or lastmod))
    # Community categories + threads (indexable for long-tail traffic).
    try:
        if db is not None:
            for c in db.forum_categories():
                entries.append((f"/community/{c['slug']}", "daily", "0.5", lastmod))
            for t in db.forum_all_thread_slugs(2000):
                entries.append((f"/community/t/{t['id']}-{t['slug']}", "weekly", "0.5",
                                t.get("updated") or lastmod))
    except Exception:
        pass  # never let the sitemap 500 over the forum lookup

    # Dedup by path (a DB blog post can share a slug with a built-in one -> one <url> only).
    seen = set()
    deduped = []
    for e in entries:
        if e[0] not in seen:
            seen.add(e[0])
            deduped.append(e)
    entries = deduped

    urls = "".join(
        f"\n  <url>"
        f"<loc>{PUBLIC_URL}{p}</loc>"
        f"<lastmod>{mod}</lastmod>"
        f"<changefreq>{freq}</changefreq>"
        f"<priority>{pri}</priority>"
        f"</url>"
        for p, freq, pri, mod in entries)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            + urls + "\n</urlset>\n")


def _build_llms():
    """Generate /llms.txt from PUBLIC_PAGES (auto). Any page with a title+description
    is listed under 'Core pages'; published blog posts are auto-added under 'Guides'."""
    core = "".join(
        f"- [{title}]({PUBLIC_URL}{p}): {desc}\n"
        for (p, _f, _pri, title, desc) in PUBLIC_PAGES if title and desc)

    guides = ""
    for slug, _mod, title, desc in _published_blog_posts():
        label = title or slug.replace("-", " ").title()
        line = f"- [{label}]({PUBLIC_URL}/blog/{slug})"
        if desc:
            line += f": {desc}"
        guides += line + "\n"
    guides_block = f"\n## Guides\n{guides}" if guides else ""

    return (
        "# wptaskify\n"
        "> Connects WordPress sites to AI assistants (Claude & ChatGPT) with 100+ tools "
        "to write SEO articles, generate images, fix on-page SEO, manage themes and plugins, "
        "and publish automatically.\n\n"
        "## Core pages\n"
        f"{core}"
        f"{guides_block}\n"
        "## Key facts\n"
        "- Works with both Claude and ChatGPT via one connector.\n"
        "- You bring your own AI account - no separate AI subscription.\n"
        "- 100+ WordPress tools: content, images, SEO, schema, themes, plugins, backups.\n"
        "- Credentials encrypted with AES-256; accounts isolated; approval inbox for risky actions.\n")

print(f"[start] Mode: {'MULTI-TENANT' if MULTI_TENANT else 'STANDALONE'}")
print(f"[start] Public URL: {PUBLIC_URL or '(none - OAuth off)'}")
print(f"[start] Port: {os.environ['PORT']}\n")

import server  # noqa: E402
import uvicorn  # noqa: E402
import pages  # noqa: E402
import mailer as email_mod  # noqa: E402
import chat as chat_mod  # noqa: E402
import billing as billing_mod  # noqa: E402
import razorpay_pay as rzp_mod  # noqa: E402
import admin as admin_mod  # noqa: E402
import google_api  # noqa: E402
from oauth import OAuthProvider  # noqa: E402


def _send_verify_email(uid, email_addr, plan=""):
    """Create a verify token and email the link (no-op if email is disabled).
    Optional `plan` carries a checkout intent through the verify link."""
    if not email_mod.enabled():
        print("[verify] email disabled (no RESEND_API_KEY)")
        return
    if not email_addr:
        print("[verify] no email address")
        return
    try:
        tok = db.create_token(uid, "verify", hours=24)
        link = f"{PUBLIC_URL}/verify?token={tok}"
        if plan:
            link += "&plan=" + urllib.parse.quote(plan)
        ok, info = email_mod.send_verify(email_addr, link)
        print(f"[verify] send to {email_addr}: ok={ok} info={str(info)[:200]}")
    except Exception as e:
        print(f"[verify] FAILED: {type(e).__name__}: {e}")


def _send_test_email(kind, to):
    """Send a preview of any notification email with sample data (admin test)."""
    try:
        if not email_mod.enabled():
            print("[test email] disabled (no RESEND_API_KEY)")
            return
        link = f"{PUBLIC_URL}/verify?token=SAMPLE"
        senders = {
            "welcome": lambda: email_mod.send_welcome(to, "Saurabh"),
            "verify": lambda: email_mod.send_verify(to, link),
            "reset": lambda: email_mod.send_reset(to, link),
            "payment": lambda: email_mod.send_payment_receipt(to, "Starter plan", 1699, "INR"),
            "renew": lambda: email_mod.send_renew_reminder(to, "Pro", 3, "2026-08-01"),
            "low_images": lambda: email_mod.send_low_images(to, 3, "Starter"),
            "low_actions": lambda: email_mod.send_low_actions(to, 20, "Starter"),
            "site_connected": lambda: email_mod.send_site_connected(to, "https://mysite.com"),
        }
        fn = senders.get(kind)
        if fn:
            ok, info = fn()
            print(f"[test email] {kind} -> {to}: ok={ok} {str(info)[:120]}")
    except Exception as e:
        print(f"[test email] FAILED: {e}")


def _notify_site_connected(uid, site_url):
    """Email the user that their WordPress site is connected (respects opt-out)."""
    try:
        if not email_mod.enabled():
            return
        prof = db.get_profile(uid)
        if prof and prof.get("notify_email", True) and prof.get("email"):
            if db.email_enabled("site_connected"):
                email_mod.send_site_connected(prof["email"], site_url)
    except Exception as e:
        print(f"[site-connected email] FAILED: {e}")

_oauth = OAuthProvider(PUBLIC_URL, OAUTH_SECRET) if PUBLIC_URL else None

# DB only in multi-tenant mode
db = None
if MULTI_TENANT:
    import db as db  # noqa: E402, PLC0414
    db.init_pool()
    db.apply_plan_config()  # load admin-edited plan prices/limits (if any)
    # Seed the starter community categories (idempotent - only creates if missing).
    try:
        for _s, _n, _d, _o in [
            ("getting-started", "Getting Started", "Connecting WordPress to Claude or ChatGPT, setup and first steps.", 1),
            ("troubleshooting", "Troubleshooting", "Connection errors, Application Passwords, REST API and fixes.", 2),
            ("seo-geo-aeo", "SEO, GEO & AEO", "Ranking, getting cited by AI answer engines, schema and content.", 3),
            ("show-and-tell", "Show & Tell", "Share what you built and workflows that work for you.", 4),
            ("feature-requests", "Feature Requests", "Ideas and requests for wptaskify.", 5),
        ]:
            db.forum_ensure_category(_s, _n, _d, _o)
    except Exception as e:  # noqa: BLE001
        print(f"[start] forum seed skipped: {e}")
    print("[start] Database connected + schema ready.")

    def _low_balance_email(uid, kind, remaining):
        """Send the low-image / low-action email (db injects this to avoid a cycle)."""
        try:
            if not email_mod.enabled():
                return
            prof = db.get_profile(uid)
            if not prof or not prof.get("notify_email", True) or not prof.get("email"):
                return
            plan = prof.get("plan", "free")
            if kind == "image" and db.email_enabled("low_images"):
                email_mod.send_low_images(prof["email"], remaining, plan)
            elif kind != "image" and db.email_enabled("low_actions"):
                email_mod.send_low_actions(prof["email"], remaining, plan)
        except Exception as e:
            print(f"[low-balance email] {e}")

    db.set_low_balance_emailer(_low_balance_email)

    # --- Daily maintenance: expire one-time (non-recurring) paid plans ---
    # A background daemon thread that downgrades paid users past their sub_renews_at
    # back to 'free'. Without this a one-time Razorpay purchase would grant the plan
    # forever (B1). Runs at boot, then every 6h. Single-instance safe; the UPDATE is
    # idempotent so even multiple instances can't double-downgrade.
    import threading as _threading

    def _expiry_worker():
        import time as _t
        while True:
            try:
                n = db.downgrade_expired_plans()
                if n:
                    print(f"[expiry] downgraded {n} expired plan(s) to free")
            except Exception as e:  # noqa: BLE001
                print(f"[expiry] downgrade job failed: {e}")
            _t.sleep(6 * 60 * 60)

    _threading.Thread(target=_expiry_worker, daemon=True, name="plan-expiry").start()
    print("[start] plan-expiry worker started.")

app = server.mcp.streamable_http_app()
_inner = app
_PORT_BYTES = str(int(os.environ["PORT"])).encode()


# ---------------------------------------------------------------------------
# Session cookies (signed): cookie value = user_id.signature
# ---------------------------------------------------------------------------
# Absolute session lifetime: a signed cookie older than this is rejected regardless.
SESSION_MAX_AGE = 60 * 60 * 24 * 30  # 30 days


def _sign(value: str) -> str:
    sig = hmac.new(SESSION_SECRET, value.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{value}.{sig}"


def _unsign(signed: str):
    """Return the signed payload string if the signature is valid, else None."""
    try:
        value, sig = signed.rsplit(".", 1)
        expected = hmac.new(SESSION_SECRET, value.encode(), hashlib.sha256).hexdigest()[:32]
        return value if hmac.compare_digest(sig, expected) else None
    except Exception:
        return None


def _sign_session(uid: str) -> str:
    """Mint a session cookie value binding the uid to an issue time + the user's current
    session version, so it can be expired by age and revoked by bumping session_ver."""
    try:
        sver = db.get_session_ver(uid)
    except Exception:
        sver = 1
    payload = f"{uid}|{int(time.time())}|{sver}"
    return _sign(payload)


def _get_session_uid(headers: dict):
    cookie = headers.get(b"cookie", b"").decode()
    raw = None
    for part in cookie.split(";"):
        part = part.strip()
        if part.startswith("sid="):
            raw = part[4:]
            break
    if raw is None:
        return None
    val = _unsign(raw)
    if val is None:
        return None
    # New format: uid|issued_ts|session_ver  (old format was just the bare uid).
    if "|" in val:
        try:
            uid, issued, sver = val.split("|", 2)
            issued = int(issued)
            sver = int(sver)
        except (ValueError, TypeError):
            return None
        # Absolute expiry.
        if time.time() - issued > SESSION_MAX_AGE:
            return None
        # Revocation: cookie's session version must still match the user's current one.
        try:
            if db.get_session_ver(uid) != sver:
                return None
        except Exception:
            pass  # fail-open on transient DB error rather than log everyone out
        return uid
    # Legacy bare-uid cookie (pre-upgrade): REJECTED. These have no expiry and no
    # revocation, so honoring them would defeat both. The new format has been live long
    # enough; anyone still holding an old cookie simply logs in again once.
    return None


def _get_active_uid(headers: dict):
    """Like _get_session_uid, but returns None for a banned/suspended user so a ban
    actually cuts off an existing session (not just future logins). Use this on
    authenticated web/chat routes that spend money, credits, or change the account."""
    uid = _get_session_uid(headers)
    if not uid:
        return None
    try:
        if db.is_banned(uid):
            return None
    except Exception:
        pass  # fail-open on a transient DB error rather than lock everyone out
    return uid


def _csrf_token(uid: str) -> str:
    """A CSRF token bound to the user's session (defense-in-depth on top of SameSite=Lax).
    Rotates when the session version changes (password change / logout-all / ban)."""
    if not uid:
        return ""
    try:
        sver = db.get_session_ver(uid)
    except Exception:
        sver = 1
    return hmac.new(SESSION_SECRET, f"csrf|{uid}|{sver}".encode(),
                    hashlib.sha256).hexdigest()[:32]


def _csrf_ok(headers: dict, form: dict) -> bool:
    """Validate the CSRF token from a POST body against the current session."""
    uid = _get_session_uid(headers)
    if not uid:
        return False
    supplied = (form.get("csrf") or "").strip()
    return bool(supplied) and hmac.compare_digest(supplied, _csrf_token(uid))


# --- In-memory IP rate limiter for unauthenticated auth endpoints (A3) ---
# A sliding-window counter keyed by (bucket, ip). Good enough for a single Railway
# instance; it throttles password-guessing, signup spam and email-bombing without a
# datastore. Not shared across instances - acceptable for these low-QPS endpoints.
_rl_hits = {}   # (bucket, ip) -> [timestamps]


def _client_ip(headers) -> str:
    fwd = headers.get(b"x-forwarded-for", b"").decode()
    if fwd:
        return fwd.split(",")[0].strip()
    return ""


def _rate_limited(bucket: str, ip: str, limit: int, window: int) -> bool:
    """Return True if (bucket, ip) has already hit `limit` requests in the last `window`
    seconds. Records this attempt. Empty IP is never limited (can't attribute it)."""
    if not ip:
        return False
    now = time.time()
    key = (bucket, ip)
    hits = [t for t in _rl_hits.get(key, []) if now - t < window]
    # Opportunistic cleanup so the dict can't grow unbounded.
    if len(_rl_hits) > 5000:
        for k in [k for k, v in list(_rl_hits.items()) if not any(now - t < 3600 for t in v)]:
            _rl_hits.pop(k, None)
    if len(hits) >= limit:
        _rl_hits[key] = hits
        return True
    hits.append(now)
    _rl_hits[key] = hits
    return False


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _valid_email(email: str) -> bool:
    email = (email or "").strip()
    return bool(email) and len(email) <= 254 and bool(_EMAIL_RE.match(email))


def _password_error(pw: str):
    """Server-side password policy (A2). The browser's minlength=6 is advisory only - a
    direct POST bypasses it - so signup and reset must re-check here. Returns an error
    string, or '' if the password is acceptable."""
    pw = pw or ""
    if len(pw) < 8:
        return "Password must be at least 8 characters."
    if len(pw) > 200:
        return "Password is too long (max 200 characters)."
    return ""


def _safe_id(s) -> int:
    """Parse a user-supplied numeric id, returning 0 if it's not a plain in-range integer.
    Bounds to a Postgres bigint so a giant number can't overflow the DB and cause a 500."""
    try:
        n = int(str(s).strip())
    except (TypeError, ValueError):
        return 0
    return n if 0 < n <= 9223372036854775807 else 0


_UUID_RE = __import__("re").compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                                    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def _safe_uuid(s):
    """Return the string only if it's a well-formed UUID, else None. Prevents a Postgres
    'invalid input syntax for type uuid' error (500) on a crafted non-UUID path segment."""
    s = str(s or "").strip()
    return s if _UUID_RE.match(s) else None


def _safe_next(nxt: str, default: str = "/dashboard") -> str:
    """Sanitize a post-login/redirect `next` target so it can ONLY point at our own site
    (a relative path). Blocks open-redirect / phishing via next=https://evil.com or
    protocol-relative //evil.com or a scheme like javascript:."""
    try:
        nxt = urllib.parse.unquote((nxt or "").strip())
    except Exception:
        return default
    # Must be a site-relative path: starts with a single '/', not '//' or '/\'.
    if not nxt.startswith("/") or nxt.startswith("//") or nxt.startswith("/\\"):
        return default
    # Reject control chars / newlines (header injection).
    if any(c in nxt for c in ("\r", "\n", "\t")):
        return default
    return nxt


# ---------------------------------------------------------------------------
# Small response helpers
# ---------------------------------------------------------------------------
async def _send_json(send, status, obj, extra_headers=None):
    h = [(b"content-type", b"application/json"), (b"access-control-allow-origin", b"*")]
    if extra_headers:
        h += extra_headers
    await send({"type": "http.response.start", "status": status, "headers": h})
    await send({"type": "http.response.body", "body": json.dumps(obj).encode()})


async def _send_html(send, status, html, extra_headers=None):
    h = [(b"content-type", b"text/html; charset=utf-8"),
         (b"cache-control", b"no-store, no-cache, must-revalidate, max-age=0")]
    if extra_headers:
        h += extra_headers
    await send({"type": "http.response.start", "status": status, "headers": h})
    await send({"type": "http.response.body", "body": html.encode()})


async def _raw_send(send, status, hdrs, body):
    h = [(k.encode() if isinstance(k, str) else k,
          v.encode() if isinstance(v, str) else v) for k, v in hdrs.items()]
    h.append((b"access-control-allow-origin", b"*"))
    await send({"type": "http.response.start", "status": status, "headers": h})
    await send({"type": "http.response.body", "body": body})


async def _read_body(receive):
    body, more = b"", True
    while more:
        msg = await receive()
        body += msg.get("body", b"")
        more = msg.get("more_body", False)
    return body


def _handle_stripe_event(event):
    """Apply a verified Stripe event: grant plans / credits on completed payments."""
    etype = event.get("type") if isinstance(event, dict) else event["type"]
    obj = (event.get("data", {}) or {}).get("object", {}) if isinstance(event, dict) \
        else event["data"]["object"]

    if etype == "checkout.session.completed":
        md = obj.get("metadata", {}) or {}
        uid = md.get("user_id") or obj.get("client_reference_id")
        if not uid:
            return
        # Idempotency: ignore duplicate Stripe deliveries/retries of the same session.
        # FAIL-CLOSED: if we can't confirm the event is new, skip rather than risk a
        # double-grant (Stripe retries, so it'll be handled once the DB is healthy).
        try:
            if not db.mark_event_processed(f"stripe:{obj.get('id','')}" if obj.get("id") else ""):
                return
        except Exception as e:  # noqa: BLE001
            print(f"[webhook] stripe idempotency check failed, skipping: {e}")
            return
        cust = obj.get("customer")
        if cust:
            try:
                db.set_stripe_customer(uid, cust)
            except Exception:
                pass
        kind = md.get("kind", "")
        item = md.get("item", "")
        if kind == "plan":
            if md.get("recurring") == "1" and obj.get("subscription"):
                # Recurring: Stripe manages renewal; no local expiry (subscription.deleted
                # downgrades). No valid_days so the plan persists until Stripe says otherwise.
                db.set_plan(uid, item)
                db.set_subscription(uid, "stripe", obj["subscription"], "active")
            else:
                # One-time Stripe payment: expire in ~1 month like the Razorpay path (B1).
                db.set_plan(uid, item, valid_days=31)
                db.set_subscription(uid, "stripe", item, "active")
            _, usd = billing_mod.PLAN_PRICES.get(item, ("", 0))
            db.record_transaction(uid, "stripe", "plan", item, usd, obj.get("id", ""))
        elif kind == "credit_pack":
            amount = int(md.get("amount", 0))
            db.add_credits(uid, amount)
            _, usd, _n = billing_mod.CREDIT_PACKS.get(item, ("", 0, 0))
            db.record_transaction(uid, "stripe", "credit_pack", item, usd, obj.get("id", ""))
        elif kind == "token_pack":
            amount = int(md.get("amount", 0))
            db.add_tokens(uid, amount)
            _, usd, _n = billing_mod.TOKEN_PACKS.get(item, ("", 0, 0))
            db.record_transaction(uid, "stripe", "token_pack", item, usd, obj.get("id", ""))

    elif etype in ("customer.subscription.deleted", "customer.subscription.canceled"):
        cust = obj.get("customer")
        uid = db.find_user_by_stripe_customer(cust) if cust else None
        if uid:
            db.set_subscription(uid, "stripe", obj.get("id", ""), "canceled")
            db.set_plan(uid, "free")  # downgrade when subscription ends


def _handle_razorpay_subscription(event, etype):
    """Handle Razorpay Subscription lifecycle events (auto-renewal).
      - subscription.charged  -> a monthly cycle was billed successfully: renew the plan
        for another ~31 days (this is what makes auto-renewal work).
      - subscription.cancelled / .completed / .halted / .expired -> stop renewing: the
        daily downgrade job drops them to free at period end (or we mark it now).
    Attribution (user_id, item) travels in the subscription's `notes`."""
    sub_id, notes = rzp_mod.extract_subscription(event)
    uid = notes.get("user_id")
    item = notes.get("item", "")
    currency = notes.get("currency", "INR")
    if not uid:
        print(f"[webhook] subscription event {etype} without user_id, skipping")
        return

    if etype == "subscription.charged":
        # Idempotency: each charge has a unique payment id; act once per charge.
        pay_id = rzp_mod.extract_payment_id(event)
        dedup = f"rzpsub:{sub_id}:{pay_id or ''}"
        try:
            if not db.mark_event_processed(dedup):
                print(f"[webhook] duplicate subscription.charged ignored ({dedup})")
                return
        except Exception as e:  # noqa: BLE001
            print(f"[webhook] sub idempotency check failed, skipping: {e}")
            return
        if not item:
            print(f"[webhook] subscription.charged missing item for uid={uid}")
            return
        # Renew: grant the plan's allowances again + push the expiry another ~31 days.
        db.set_plan(uid, item, valid_days=33)   # +2d grace over the 31d billing cycle
        db.set_subscription(uid, "razorpay", sub_id, "active")
        # Record the renewal payment + invoice (GST for INR).
        paid_amt, _cur = rzp_mod.extract_amount(event)
        table = rzp_mod.PLAN_PRICES_INR if currency == "INR" else rzp_mod.PLAN_PRICES_USD
        label, list_amt = table.get(item, (item, 0))
        total = paid_amt if paid_amt is not None else list_amt
        try:
            inv_no = db.next_invoice_no()
        except Exception:
            inv_no = ""
        try:
            db.record_transaction(uid, "razorpay", "plan", item, total,
                                  rzp_mod.extract_payment_id(event), currency=currency,
                                  base_amount=total, invoice_no=inv_no)
        except Exception:
            pass
        # Affiliate commission is credited only on the FIRST payment (convert_referral is
        # idempotent), so renewals correctly don't re-pay the referrer.
        print(f"[webhook] subscription renewed uid={uid} item={item} sub={sub_id}")
        return

    if etype in ("subscription.cancelled", "subscription.completed",
                 "subscription.expired", "subscription.halted"):
        # Stop auto-renew. Keep the plan until its current expiry (they paid for it); the
        # daily downgrade job drops them to free once sub_renews_at passes.
        try:
            db.set_subscription_status(uid, "canceled")
        except Exception as e:  # noqa: BLE001
            print(f"[webhook] mark sub canceled failed uid={uid}: {e}")
        print(f"[webhook] subscription {etype} uid={uid} sub={sub_id}")
        return


def _handle_razorpay_event(event):
    """Apply a verified Razorpay webhook: grant plan / credits on paid payment.
    We act on payment_link.paid (hosted link) and payment.captured (fallback)."""
    etype = event.get("event", "") if isinstance(event, dict) else ""
    # Recurring subscription lifecycle (auto-renewal) is handled separately.
    if etype.startswith("subscription."):
        _handle_razorpay_subscription(event, etype)
        return
    if etype not in ("payment_link.paid", "payment.captured", "order.paid"):
        return
    notes = rzp_mod.extract_notes(event)
    uid = notes.get("user_id")
    if not uid:
        return
    # Idempotency: all events for one purchase share a payment id; act only on the first.
    pay_id = rzp_mod.extract_payment_id(event)
    if not pay_id:
        # Without a stable payment id we can't dedup -> a retry would re-grant. Skip.
        print("[webhook] razorpay event has no payment id, skipping (cannot dedup)")
        return
    try:
        if not db.mark_event_processed(f"rzp:{pay_id}"):
            print(f"[webhook] duplicate razorpay event ignored (pay_id={pay_id})")
            return
    except Exception as e:  # noqa: BLE001
        # FAIL-CLOSED: if we can't confirm this event is new, do NOT process it - a retry
        # could double-grant. Razorpay retries webhooks, so we'll handle it once the DB is
        # healthy. Returning (not falling through) is the safe choice.
        print(f"[webhook] idempotency check failed, skipping to avoid double-grant: {e}")
        return
    kind = notes.get("kind", "")
    item = notes.get("item", "")
    currency = notes.get("currency", "INR")
    coupon = notes.get("coupon", "")
    if coupon:
        try:
            db.redeem_coupon(coupon, uid, item)
        except Exception:
            pass

    def _notify_ok(u):
        """Only email if notifications are on globally and for this user."""
        if not (email_mod.enabled() and db.email_enabled("payment")):
            return None
        em = db.get_email(u)
        prof = db.get_profile(u)
        if em and prof and prof.get("notify_email", True):
            return em
        return None

    def _receipt(label, amount):
        try:
            em = _notify_ok(uid)
            if em:
                email_mod.send_payment_receipt(em, label, amount, currency)
        except Exception:
            pass

    if kind == "plan":
        table = rzp_mod.PLAN_PRICES_INR if currency == "INR" else rzp_mod.PLAN_PRICES_USD
        label, list_amt = table.get(item, (item, 0))
        try:
            base = float(notes.get("base", list_amt))
        except (TypeError, ValueError):
            base = list_amt
        try:
            tax = float(notes.get("tax", 0))
        except (TypeError, ValueError):
            tax = 0
        total = base + tax
        # B2 - RECONCILE: verify the money Razorpay actually captured matches the price we
        # intended to charge for this plan+coupon+currency (from `notes`). The signature is
        # already verified, so notes aren't forged; this guards against a payment-link amount
        # that doesn't line up with what we recorded (e.g. tampering, partial capture, or a
        # notes/currency mismatch). If it doesn't reconcile, DON'T grant - log and bail.
        paid_amt, paid_cur = rzp_mod.extract_amount(event)
        if paid_amt is not None:
            expected = max(total, 1.0)  # create_plan_link floors a 0 total to 1 unit
            # Allow 1 unit of rounding slack; currency (if reported) must match.
            amount_ok = abs(paid_amt - expected) <= 1.01
            cur_ok = (not paid_cur) or (paid_cur == currency)
            if not (amount_ok and cur_ok):
                print(f"[webhook] AMOUNT MISMATCH uid={uid} item={item}: "
                      f"paid={paid_amt} {paid_cur} expected={expected} {currency} - NOT granting")
                return
        # One-time purchase -> plan valid for ~1 month, then downgrade_expired_plans() drops it.
        db.set_plan(uid, item, valid_days=31)
        db.set_subscription(uid, "razorpay", item, "active")
        gstin = notes.get("gstin", "")
        # Allocate a proper invoice number for every paid plan (GST invoice for INR).
        try:
            inv_no = db.next_invoice_no()
        except Exception:
            inv_no = ""
        try:
            db.record_transaction(uid, "razorpay", "plan", item, total, pay_id, currency=currency,
                                  base_amount=base, tax_amount=tax, gstin=gstin,
                                  invoice_no=inv_no)
        except Exception:
            pass
        # Affiliate: credit the referrer a commission on this user's FIRST paid plan.
        # Commission is on the base (pre-tax) amount; convert_referral is idempotent.
        try:
            db.convert_referral(uid, base, currency, ext_id=pay_id)
        except Exception:
            pass
        # Send a proper (tax) invoice instead of the plain receipt for plan purchases.
        try:
            em = _notify_ok(uid)
            if em:
                rate = db.get_gst_rate() if (currency == "INR" and tax) else 0
                prof = db.get_profile(uid) or {}
                date_str = time.strftime("%d %b %Y", time.gmtime())
                email_mod.send_invoice(em, inv_no or "-", date_str, f"{label} plan (1 month)",
                                       base, tax, total, rate, currency=currency,
                                       buyer_gstin=gstin, buyer_name=prof.get("name", ""))
            else:
                _receipt(f"{label} plan", total)
        except Exception as e:  # noqa: BLE001
            # Don't fail silently - log it, then still try a plain receipt so the
            # customer isn't left with no email at all.
            print(f"[invoice] send failed for uid={uid} inv={inv_no}: "
                  f"{type(e).__name__}: {e}")
            _receipt(f"{label} plan", total)
    elif kind == "credit_pack":
        amount = int(notes.get("amount", 0))
        db.add_credits(uid, amount)
        # Record the ACTUAL price paid (was hardcoded 0, so history showed "₹0").
        packs = rzp_mod.CREDIT_PACKS_INR if currency == "INR" else rzp_mod.CREDIT_PACKS_USD
        _plabel, pack_price, _pcount = packs.get(item, ("", 0, 0))
        try:
            db.record_transaction(uid, "razorpay", "credit_pack", item, pack_price, pay_id,
                                  currency=currency, base_amount=pack_price)
        except Exception:
            pass
        _receipt(f"{amount} AI images", pack_price)


# ---------------------------------------------------------------------------
# wptaskify plugin auto-update
# ---------------------------------------------------------------------------
_PLUGIN_ZIP = pathlib.Path(__file__).resolve().parent / "plugin" / "wp-pilot-seo.zip"


def _plugin_version():
    """Read the version from the plugin zip's main file header."""
    try:
        import zipfile
        with zipfile.ZipFile(_PLUGIN_ZIP) as z:
            txt = z.read("wp-pilot-seo/wp-pilot-seo.php").decode("utf-8", "ignore")
        for line in txt.splitlines():
            if "Version:" in line:
                return line.split("Version:", 1)[1].strip()
    except Exception:
        pass
    return "1.0.0"


def _plugin_manifest():
    return {
        "name": "wptaskify",
        "slug": "wp-pilot-seo",
        "version": _plugin_version(),
        "download_url": PUBLIC_URL + "/plugin/wp-pilot-seo.zip" if PUBLIC_URL
                        else "/plugin/wp-pilot-seo.zip",
        "requires": "5.6",
        "tested": "6.7",
        "requires_php": "7.4",
        "description": "Free SEO + AI tools for WordPress by wptaskify.",
    }


async def _send_plugin_zip(send):
    try:
        data = _PLUGIN_ZIP.read_bytes()
    except Exception:
        await _send_json(send, 404, {"error": "plugin zip not found"})
        return
    await send({"type": "http.response.start", "status": 200, "headers": [
        (b"content-type", b"application/zip"),
        (b"content-disposition", b'attachment; filename="wp-pilot-seo.zip"'),
        (b"access-control-allow-origin", b"*")]})
    await send({"type": "http.response.body", "body": data})


_ASSET_DIR = HERE / "assets"
_ASSET_TYPES = {".png": b"image/png", ".svg": b"image/svg+xml",
                ".ico": b"image/x-icon", ".jpg": b"image/jpeg",
                ".webp": b"image/webp"}


async def _send_asset(send, path):
    """Serve a brand asset (logo/icon) from the assets/ dir. Path-safe."""
    name = path[len("/assets/"):]
    target = (_ASSET_DIR / name).resolve()
    # Prevent path traversal: must stay inside the assets dir.
    if _ASSET_DIR not in target.parents or not target.is_file():
        await _send_json(send, 404, {"error": "not found"})
        return
    ctype = _ASSET_TYPES.get(target.suffix.lower(), b"application/octet-stream")
    await send({"type": "http.response.start", "status": 200, "headers": [
        (b"content-type", ctype),
        (b"cache-control", b"public, max-age=86400"),
        (b"access-control-allow-origin", b"*")]})
    await send({"type": "http.response.body", "body": target.read_bytes()})


def _form(body: bytes):
    # errors="replace" so a malformed/invalid-UTF-8 body can never crash the handler (500).
    try:
        text = body.decode("utf-8", "replace")
    except Exception:
        text = ""
    return {k: v[0] for k, v in urllib.parse.parse_qs(text).items()}


def _json_body(body: bytes):
    """Parse a JSON request body, returning {} on any malformed/invalid input (never 500)."""
    try:
        d = json.loads(body or b"{}")
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# WordPress credential validation (used when adding a site)
# ---------------------------------------------------------------------------
def _validate_wp(site_url, username, app_password):
    token = base64.b64encode(f"{username}:{app_password.replace(' ', '')}".encode()).decode()
    url = site_url.rstrip("/") + "/wp-json/wp/v2/users/me?context=edit"
    req = urllib.request.Request(url, headers={"Authorization": "Basic " + token})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            me = json.load(r)
            return True, me.get("roles", [])
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}"
    except Exception as e:
        return False, str(e)[:80]


async def _handle_admin(path, method, headers, query, receive, send):
    """Owner admin panel router. All paths are under admin_mod.base_path()."""
    b = admin_mod.base_path()
    sub = path[len(b):].strip("/")          # "", "users", "user/<id>", "user/<id>/plan", ...
    cookie = headers.get(b"cookie", b"").decode()
    authed = admin_mod.is_authed(cookie)
    qs = urllib.parse.parse_qs(query)
    search_q = (qs.get("q", [""])[0])

    async def html(status, body, extra=None):
        await _send_html(send, status, body, extra)

    async def redirect(to, extra=None):
        hdrs = [(b"location", (b + to).encode())]
        if extra:
            hdrs += extra
        await _send_html(send, 302, "", hdrs)

    # --- login / logout (no auth needed) ---
    if sub == "login" and method == "POST":
        f = _form(await _read_body(receive))
        if admin_mod.check_password(f.get("password", "")):
            await redirect("", [(b"set-cookie", admin_mod.make_cookie().encode())])
        else:
            await html(401, admin_mod.login_page("Wrong password."))
        return
    if sub == "logout":
        await redirect("", [(b"set-cookie", admin_mod.clear_cookie().encode())])
        return

    # --- gate everything else ---
    if not authed:
        await html(200, admin_mod.login_page())
        return

    # --- authed routes ---
    parts = sub.split("/") if sub else []

    def _int(v, default=0):
        try:
            return int(str(v).strip())
        except (ValueError, TypeError):
            return default

    # ----- POST: per-user actions -----
    if method == "POST" and len(parts) >= 3 and parts[0] == "user":
        uid, act = parts[1], parts[2]
        f = _form(await _read_body(receive))
        if act == "plan":
            db.set_plan(uid, f.get("plan", "free"))
        elif act == "credits":
            db.admin_set_credits(uid, _int(f.get("count")))
        elif act == "actions":
            db.admin_set_toolcalls(uid, _int(f.get("count")))
        elif act == "tokens":
            db.admin_set_tokens(uid, _int(f.get("count")))
        elif act == "verify":
            db.admin_set_verified(uid, f.get("verified") == "1")
        elif act == "email":
            new_email = (f.get("email") or "").strip().lower()
            if new_email and "@" in new_email:
                db.admin_set_email(uid, new_email)
        elif act == "reset":
            # email the user a password-reset link
            em = db.get_email(uid)
            if em and email_mod.enabled():
                try:
                    tok = db.create_token(uid, "reset", hours=2)
                    email_mod.send_reset(em, f"{PUBLIC_URL}/reset?token={tok}")
                except Exception:
                    pass
        elif act == "loginas":
            # impersonate: set a normal user session cookie and open their dashboard
            cookie = f"sid={_sign_session(uid)}; Path=/; HttpOnly; Secure; SameSite=Lax"
            await _send_html(send, 302, "", [(b"set-cookie", cookie.encode()),
                                             (b"location", b"/dashboard")])
            return
        elif act == "disconnect":
            db.admin_disconnect_sites(uid)
        elif act == "ban":
            db.admin_set_status(uid, "banned")
        elif act == "unban":
            db.admin_set_status(uid, "active")
        elif act == "note":
            db.admin_set_note(uid, f.get("note", ""))
        elif act == "addcredits":
            db.admin_adjust_credits(uid, _int(f.get("delta")))
        elif act == "addactions":
            db.admin_adjust_toolcalls(uid, _int(f.get("delta")))
        elif act == "delete":
            db.admin_delete_user(uid)
            await redirect("/users")
            return
        await redirect(f"/user/{uid}")
        return

    # ----- POST: bulk actions on many users -----
    if method == "POST" and sub == "bulk":
        raw = urllib.parse.parse_qs((await _read_body(receive)).decode())
        ids = raw.get("uid", [])           # checkbox name="uid" repeated
        action = (raw.get("action", [""]) or [""])[0]
        value = (raw.get("value", [""]) or [""])[0]
        db.admin_bulk(ids, action, value)
        await redirect("/users")
        return

    # ----- POST: mark a contact lead read/archived -----
    if method == "POST" and sub == "leads/status":
        f = _form(await _read_body(receive))
        try:
            db.admin_set_contact_status(int(f.get("id", "0") or 0), f.get("status", ""))
        except Exception:
            pass
        await redirect("/leads")
        return

    # ----- POST: create a coupon -----
    if method == "POST" and sub == "coupons/create":
        f = _form(await _read_body(receive))
        expires = f.get("expires", "").strip() or None
        # A bare date (YYYY-MM-DD) stores as midnight, which would kill the coupon at the
        # START of that day. Make it valid THROUGH the whole selected day (end of day).
        if expires and len(expires) == 10 and "T" not in expires and " " not in expires:
            expires = expires + " 23:59:59"
        okc, errmsg = db.create_coupon(
            code=f.get("code", ""), kind=f.get("kind", "percent"),
            value=f.get("value", "0"), currency=f.get("currency", "ANY"),
            max_uses=_int(f.get("max_uses"), 0), expires_at=expires, note=f.get("note", ""))
        if okc:
            await redirect("/coupons?ok=" + urllib.parse.quote("Coupon created."))
        else:
            await redirect("/coupons?err=" + urllib.parse.quote(errmsg))
        return

    # ----- POST: toggle / delete a coupon -----
    if method == "POST" and len(parts) >= 3 and parts[0] == "coupon":
        code, act = parts[1], parts[2]
        f = _form(await _read_body(receive))
        if act == "toggle":
            db.set_coupon_active(code, f.get("active") == "1")
        elif act == "delete":
            db.delete_coupon(code)
        await redirect("/coupons")
        return

    # ----- POST: save a plan's price/limits (live-applies) -----
    if method == "POST" and sub == "plans/save":
        f = _form(await _read_body(receive))
        key = f.get("key", "")
        cfg = db.get_plan_config()
        if key in cfg:
            cur = cfg[key]
            patch = {
                "inr": _int(f.get("inr"), cur.get("inr", 0)),
                "usd": _int(f.get("usd"), cur.get("usd", 0)),
                "images": _int(f.get("images"), cur.get("images", 0)),
                "actions": _int(f.get("actions"), cur.get("actions", 0)),
                "sites": _int(f.get("sites"), cur.get("sites", 1)),
            }
            merged = db.get_setting("plan_config") or {}
            merged[key] = {**merged.get(key, {}), **patch}
            db.save_plan_config(merged)
            await redirect("/plans?ok=" + urllib.parse.quote(f"{cur.get('name', key)} plan updated."))
        else:
            await redirect("/plans?err=" + urllib.parse.quote("Unknown plan."))
        return

    # ----- POST: save GST rate -----
    if method == "POST" and sub == "tax/rate":
        f = _form(await _read_body(receive))
        db.set_gst_rate(f.get("rate", "18"))
        await redirect("/tax?ok=" + urllib.parse.quote("GST rate updated."))
        return

    # ----- POST: save an email's subject / enabled -----
    if method == "POST" and sub == "emails/save":
        f = _form(await _read_body(receive))
        key = f.get("key", "")
        if key in db.EMAIL_KINDS:
            cfg = db.get_setting("email_config") or {}
            cfg[key] = {"subject": f.get("subject", "").strip(),
                        "enabled": f.get("enabled") == "1"}
            db.save_email_config(cfg)
            await redirect("/emails?ok=" + urllib.parse.quote("Email settings saved."))
        else:
            await redirect("/emails?err=" + urllib.parse.quote("Unknown email."))
        return

    # ----- POST: save social links (footer) -----
    if method == "POST" and sub == "social/save":
        f = _form(await _read_body(receive))
        links = {key: f.get(key, "") for key, _label in db.SOCIAL_PLATFORMS}
        db.save_social_links(links)
        await redirect("/social?ok=" + urllib.parse.quote("Social links saved."))
        return

    # ----- POST: save analytics / search-console tags -----
    if method == "POST" and sub == "seo/save":
        f = _form(await _read_body(receive))
        db.save_analytics(ga_id=f.get("ga_id", ""), gsc_verify=f.get("gsc_verify", ""),
                          head_extra=f.get("head_extra", ""))
        await redirect("/seo?ok=" + urllib.parse.quote("Analytics & SEO tags saved and applied."))
        return

    # ----- POST: admin blog create/edit + delete -----
    if method == "POST" and sub == "blog/save":
        f = _form(await _read_body(receive))
        old_slug = f.get("old_slug", "").strip() or None
        ok, res = db.blog_db_upsert(
            slug=f.get("slug", ""), title=f.get("title", ""),
            description=f.get("description", ""), keywords=f.get("keywords", ""),
            hero=f.get("hero", "hero-blog.webp").strip() or "hero-blog.webp",
            read_time=f.get("read_time", "5 min read").strip() or "5 min read",
            body_html=f.get("body_html", ""), published=(f.get("published") == "1"),
            old_slug=old_slug)
        if ok:
            await redirect("/blog?ok=" + urllib.parse.quote("Post saved."))
        else:
            # bounce back to editor with the error
            back = f"/blog/edit?err={urllib.parse.quote(res)}"
            if old_slug:
                back += "&slug=" + urllib.parse.quote(old_slug)
            await redirect(back)
        return
    if method == "POST" and sub.startswith("blog/") and sub.endswith("/delete"):
        slug = sub[len("blog/"):-len("/delete")]
        if slug:
            db.blog_db_delete(slug)
        await redirect("/blog?ok=" + urllib.parse.quote("Post deleted."))
        return

    # ----- POST: affiliate commission rate + payout approval -----
    if method == "POST" and sub == "affiliates/rate":
        f = _form(await _read_body(receive))
        db.set_commission_rate(f.get("rate", "20"))
        await redirect("/affiliates?ok=" + urllib.parse.quote("Commission rate updated."))
        return
    if method == "POST" and sub.startswith("payout/"):
        parts = sub.split("/")  # payout/<id>/<action>
        if len(parts) == 3:
            pid = _safe_id(parts[1])
            action = parts[2]
            if pid and action in ("paid", "rejected"):
                db.admin_set_payout_status(pid, action)
        await redirect("/affiliates?ok=" + urllib.parse.quote("Payout updated."))
        return

    # ----- POST: community moderation (pin/lock/delete) -----
    if method == "POST" and sub.startswith("forum/thread/"):
        parts = sub.split("/")  # forum/thread/<id>/<action>
        if len(parts) == 4:
            tid = _safe_id(parts[2])
            action = parts[3]
            th = db.forum_thread(tid) if tid else None
            if th:
                if action == "pin":
                    db.forum_set_pinned(tid, not th["pinned"])
                elif action == "lock":
                    db.forum_set_locked(tid, not th["locked"])
                elif action == "delete":
                    db.forum_delete_thread(tid)
        await redirect("/forum?ok=" + urllib.parse.quote("Community updated."))
        return
    if method == "POST" and sub.startswith("forum/post/"):
        parts = sub.split("/")  # forum/post/<id>/delete
        if len(parts) == 4 and parts[3] == "delete":
            _pid = _safe_id(parts[2])
            if _pid:
                db.forum_delete_post(_pid)
        await redirect("/forum?ok=" + urllib.parse.quote("Reply deleted."))
        return

    # ----- POST: send a test email -----
    if method == "POST" and sub == "emails/test":
        f = _form(await _read_body(receive))
        key, to = f.get("key", ""), f.get("to", "").strip()
        if not to or "@" not in to:
            await redirect("/emails?err=" + urllib.parse.quote("Enter a valid test email."))
            return
        _send_test_email(key, to)
        await redirect("/emails?ok=" + urllib.parse.quote(f"Test '{key}' sent to {to}."))
        return

    # ----- POST: transaction refund/status -----
    if method == "POST" and len(parts) >= 3 and parts[0] == "txn":
        txn_id, act = _int(parts[1]), parts[2]
        if act == "refund":
            # Full reversal: mark refunded + claw back affiliate commission + downgrade plan.
            db.admin_refund_transaction(txn_id)
        elif act == "fail":
            db.admin_set_txn_status(txn_id, "failed")
        # bounce back to the referring user page if given, else payments.
        # Only allow a relative path (no open redirect via a crafted 'back' field).
        f = _form(await _read_body(receive))
        back = f.get("back", "/payments")
        if not back.startswith("/") or back.startswith("//"):
            back = "/payments"
        await redirect(back)
        return

    # ----- CSV exports -----
    if sub == "users.csv":
        csv_data = _admin_users_csv(qs)
        await send({"type": "http.response.start", "status": 200, "headers": [
            (b"content-type", b"text/csv; charset=utf-8"),
            (b"content-disposition", b'attachment; filename="wptaskify-users.csv"')]})
        await send({"type": "http.response.body", "body": csv_data.encode()})
        return
    if sub == "payments.csv":
        csv_data = _admin_payments_csv()
        await send({"type": "http.response.start", "status": 200, "headers": [
            (b"content-type", b"text/csv; charset=utf-8"),
            (b"content-disposition", b'attachment; filename="wptaskify-payments.csv"')]})
        await send({"type": "http.response.body", "body": csv_data.encode()})
        return

    # ----- GET: pages -----
    if not sub:
        await html(200, admin_mod.dashboard_page())
    elif sub == "users":
        await html(200, admin_mod.users_page(
            search=qs.get("q", [""])[0], plan=qs.get("plan", [""])[0],
            verified=qs.get("verified", [""])[0], paid=qs.get("paid", [""])[0],
            sort=qs.get("sort", ["created_at"])[0]))
    elif sub == "leads":
        await html(200, admin_mod.leads_page(
            flash=qs.get("ok", [""])[0], status=qs.get("status", [""])[0]))
    elif parts and parts[0] == "user" and len(parts) == 2:
        await html(200, admin_mod.user_detail_page(parts[1]))
    elif sub == "payments":
        await html(200, admin_mod.payments_page())
    elif sub == "usage":
        await html(200, admin_mod.usage_page(days=qs.get("days", ["30"])[0]))
    elif sub == "system":
        await html(200, admin_mod.system_page(_admin_system_status()))
    elif sub == "coupons":
        await html(200, admin_mod.coupons_page(
            flash=qs.get("ok", [""])[0], err=qs.get("err", [""])[0]))
    elif sub == "plans":
        await html(200, admin_mod.plans_page(
            flash=qs.get("ok", [""])[0], err=qs.get("err", [""])[0]))
    elif sub == "emails":
        await html(200, admin_mod.emails_page(
            flash=qs.get("ok", [""])[0], err=qs.get("err", [""])[0]))
    elif sub == "tax":
        await html(200, admin_mod.tax_page(
            flash=qs.get("ok", [""])[0], err=qs.get("err", [""])[0]))
    elif sub == "social":
        await html(200, admin_mod.social_page(
            flash=qs.get("ok", [""])[0], err=qs.get("err", [""])[0]))
    elif sub == "seo":
        await html(200, admin_mod.analytics_page(
            flash=qs.get("ok", [""])[0], err=qs.get("err", [""])[0]))
    elif sub == "forum":
        await html(200, admin_mod.forum_page(
            flash=qs.get("ok", [""])[0], err=qs.get("err", [""])[0]))
    elif sub == "affiliates":
        await html(200, admin_mod.affiliates_page(
            flash=qs.get("ok", [""])[0], err=qs.get("err", [""])[0]))
    elif sub == "blog":
        await html(200, admin_mod.blog_list_page(
            flash=qs.get("ok", [""])[0], err=qs.get("err", [""])[0]))
    elif sub == "blog/edit":
        _slug = qs.get("slug", [""])[0]
        _post = db.blog_db_get(_slug) if _slug else None
        await html(200, admin_mod.blog_edit_page(
            post=_post, flash=qs.get("ok", [""])[0], err=qs.get("err", [""])[0]))
    else:
        await redirect("")


def _admin_system_status():
    """Live status for the admin System page (read-only monitoring)."""
    return {
        "db_ok": db.admin_db_ok(),
        "email_configured": email_mod.enabled(),
        "razorpay_configured": rzp_mod.enabled(),
        "gemini_configured": bool(os.environ.get("GEMINI_API_KEY")),
        "stripe_configured": bool(os.environ.get("STRIPE_SECRET_KEY")),
        "maintenance_on": MAINTENANCE_ON,
        "builtin_chat_on": BUILTIN_CHAT_ON,
    }


def _csv_safe(val):
    """Neutralize CSV/formula injection: a cell starting with = + - @ (or tab/CR) can be
    executed as a formula by Excel/Sheets. Prefix such cells with a single quote."""
    s = "" if val is None else str(val)
    if s and s[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + s
    return s


def _admin_users_csv(qs):
    import csv as _csv
    import io as _io
    users = db.admin_users_filtered(
        search=qs.get("q", [""])[0], plan=qs.get("plan", [""])[0],
        verified=qs.get("verified", [""])[0], paid_only=(qs.get("paid", [""])[0] == "1"),
        sort=qs.get("sort", ["created_at"])[0])
    buf = _io.StringIO()
    w = _csv.writer(buf)
    w.writerow(["email", "plan", "verified", "sites", "primary_site",
                "spent_inr", "spent_usd", "credits", "actions_left", "last_active", "joined"])
    for u in users:
        w.writerow([_csv_safe(u["email"]), u["plan"], "yes" if u["verified"] else "no", u["sites"],
                    _csv_safe(u["site_url"] or ""), f'{u["spent"]:.2f}', f'{u.get("spent_usd",0):.2f}',
                    u["credits"], u["tool_calls"],
                    (u["last_active"] or "")[:19], u["created_at"][:19]])
    return buf.getvalue()


def _admin_payments_csv():
    import csv as _csv
    import io as _io
    txns = db.admin_recent_transactions(limit=5000)
    buf = _io.StringIO()
    w = _csv.writer(buf)
    w.writerow(["date", "email", "kind", "item", "amount", "currency", "invoice_no",
                "provider", "status"])
    for t in txns:
        w.writerow([t["created_at"][:19], _csv_safe(t["email"]), t["kind"], _csv_safe(t["item"]),
                    f'{t["amount"]:.2f}', t.get("currency", "INR"), t.get("invoice_no", ""),
                    t["provider"], t["status"]])
    return buf.getvalue()


_geo_cache = {}  # ip -> country, so we don't hit the geo API on every page load


def _geo_country(headers):
    """Best-effort visitor country (2-letter). Used to show INR to India, USD to
    the rest. Order: manual currency cookie (user override) -> CDN header -> IP lookup."""
    # 0. Manual override: the user picked a currency via the switcher (cookie).
    cookie = headers.get(b"cookie", b"").decode()
    for part in cookie.split(";"):
        part = part.strip()
        if part.startswith("cur="):
            val = part[4:].strip().upper()
            if val == "IN":
                return "IN"
            if val == "US":
                return "US"   # any non-IN country shows USD
    # 1. Proxy/CDN headers (if a CDN is in front, this is instant + reliable).
    for h in (b"cf-ipcountry", b"x-vercel-ip-country", b"x-country-code"):
        v = headers.get(h, b"").decode().strip().upper()
        if v and len(v) == 2:
            return v
    # 2. Fall back to IP geolocation (free, cached per IP).
    fwd = headers.get(b"x-forwarded-for", b"").decode()
    ip = fwd.split(",")[0].strip() if fwd else ""
    if not ip:
        return ""
    if ip in _geo_cache:
        return _geo_cache[ip]
    country = ""
    try:
        with urllib.request.urlopen(f"https://ipapi.co/{ip}/country/", timeout=3) as r:
            country = r.read().decode().strip().upper()[:2]
    except Exception:
        country = ""
    _geo_cache[ip] = country
    return country


def _billing_country(headers):
    """Country for the ACTUAL CHARGE + GST decision. Unlike `_geo_country`, this
    IGNORES the user-set `cur` cookie - otherwise an Indian buyer could set cur=US and
    pay in USD with zero GST (B3). Billing currency must come from a trusted signal:
    a CDN/proxy geo header, else IP geolocation. Display pricing can still use the
    cookie via `_geo_country`; money cannot."""
    for h in (b"cf-ipcountry", b"x-vercel-ip-country", b"x-country-code"):
        v = headers.get(h, b"").decode().strip().upper()
        if v and len(v) == 2:
            return v
    fwd = headers.get(b"x-forwarded-for", b"").decode()
    ip = fwd.split(",")[0].strip() if fwd else ""
    if not ip:
        return ""
    if ip in _geo_cache:
        return _geo_cache[ip]
    country = ""
    try:
        with urllib.request.urlopen(f"https://ipapi.co/{ip}/country/", timeout=3) as r:
            country = r.read().decode().strip().upper()[:2]
    except Exception:
        country = ""
    _geo_cache[ip] = country
    return country


def _billing_currency(headers):
    """INR for India, USD for everyone else - based on TRUSTED geo only (see
    `_billing_country`). Used by /checkout and /coupon-preview so the amount charged and
    the GST applied can't be flipped by a spoofable cookie."""
    return "INR" if _billing_country(headers) == "IN" else "USD"


def _studio_fetch(uid, wpps_path):
    """Fetch a wptaskify Studio REST endpoint (wpps/v1/...) for the user's primary
    site, using its stored credentials. Returns (ok, data). Used by the dashboard
    to show the live Activity feed, Backups, and Site Health next to Claude."""
    site = db.get_primary_site(uid)
    if not site:
        return False, {"error": "no site connected"}
    token = base64.b64encode(
        f"{site['wp_username']}:{site['app_password'].replace(' ', '')}".encode()).decode()
    url = site["site_url"].rstrip("/") + "/wp-json/wpps/v1/" + wpps_path.lstrip("/")
    req = urllib.request.Request(url, headers={
        "Authorization": "Basic " + token, "User-Agent": "wp-pilot-dashboard"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return True, json.load(r)
    except Exception as e:  # noqa: BLE001
        return False, {"error": str(e)[:100],
                       "hint": "Update the wptaskify plugin on your site to enable this."}


# ---------------------------------------------------------------------------
# Main ASGI middleware
# ---------------------------------------------------------------------------
async def asgi_app(scope, receive, send):
    if scope.get("type") != "http":
        await _inner(scope, receive, send)
        return

    path = scope.get("path", "")
    method = scope.get("method", "GET")
    headers = dict(scope.get("headers", []))
    query = scope.get("query_string", b"").decode()

    # ===== Maintenance mode =====
    # MAINTENANCE=on shows a "back soon" page for marketing/dashboard pages.
    # Bypass with ?key=<MAINTENANCE_KEY> (sets a 1-day cookie so you stay in).
    # MCP, chat, OAuth and plugin endpoints stay live so connected users aren't cut off.
    if MAINTENANCE_ON:
        cookie = headers.get(b"cookie", b"").decode()
        key_in_url = bool(MAINT_KEY and ("key=" + MAINT_KEY) in query)
        bypass = key_in_url or (MAINT_KEY and ("mkey=" + MAINT_KEY) in cookie)
        allow = (path.startswith("/mcp") or path.startswith("/.well-known")
                 or path in ("/register", "/authorize", "/token")
                 or path.startswith("/plugin/") or path.startswith("/chat")
                 or path.startswith("/api/"))
        if not bypass and not allow:
            await _send_html(send, 503, pages.maintenance_page())
            return
        if key_in_url:
            # set bypass cookie then continue
            scope = scope  # cookie set on next normal response is enough; simplest: set here
            extra_cookie = f"mkey={MAINT_KEY}; Path=/; Max-Age=86400"
            await _send_html(send, 200, pages.message_page(
                "Maintenance bypass active",
                "<p class=sub>You can browse the site normally now.</p>", "/", "Continue"),
                [(b"set-cookie", extra_cookie.encode())])
            return

    # ===== Owner admin panel (secret URL + password) =====
    if admin_mod.enabled() and (path == admin_mod.base_path()
                                or path.startswith(admin_mod.base_path() + "/")):
        await _handle_admin(path, method, headers, query, receive, send)
        return

    # ===== Brand assets (logos, icons) - public, no auth =====
    if path.startswith("/assets/") and method == "GET":
        await _send_asset(send, path)
        return

    # ===== Plugin auto-update endpoints (public, no auth) =====
    if path == "/plugin/update.json":
        await _send_json(send, 200, _plugin_manifest())
        return
    if path == "/plugin/wp-pilot-seo.zip":
        await _send_plugin_zip(send)
        return

    # ===== Web routes (multi-tenant only) =====
    if MULTI_TENANT:
        if path == "/" and method == "GET":
            # Affiliate: capture ?ref=CODE into a 60-day cookie so a later signup is
            # attributed to the referrer. Only set when the code looks valid-ish.
            _extra_hdrs = []
            _refc = (urllib.parse.parse_qs(query).get("ref") or [""])[0].strip().upper()[:16]
            if _refc and _refc.isalnum():
                _extra_hdrs.append((b"set-cookie",
                    f"ref={_refc}; Path=/; Max-Age={60*24*3600}; SameSite=Lax".encode()))
            # "?signup" shows the signup page, otherwise the marketing landing.
            if "signup" in query:
                _plan = (urllib.parse.parse_qs(query).get("plan") or [""])[0]
                _next = f"/checkout-after?plan={_plan}" if _plan in ("owai_mini", "owai_starter", "owai_pro") else ""
                await _send_html(send, 200, pages.signup_page(authorize_next=_next), _extra_hdrs)
            else:
                logged_in = bool(_get_session_uid(headers))
                await _send_html(send, 200,
                                 pages.landing(logged_in=logged_in, country=_geo_country(headers)),
                                 _extra_hdrs)
            return
        # ----- Content / legal / marketing pages -----
        if path == "/features" and method == "GET":
            await _send_html(send, 200, pages.features_page())
            return
        if path == "/tools" and method == "GET":
            await _send_html(send, 200, pages.tools_page())
            return
        if path == "/how-it-works" and method == "GET":
            await _send_html(send, 200, pages.how_page())
            return
        # Done-for-you services (agency offering) - hub + 4 service pages.
        if path == "/services" and method == "GET":
            await _send_html(send, 200, pages.services_page())
            return
        if path == "/services/wordpress-ai-setup" and method == "GET":
            await _send_html(send, 200, pages.service_setup_page())
            return
        if path == "/services/custom-ai-tools" and method == "GET":
            await _send_html(send, 200, pages.service_custom_tools_page())
            return
        if path == "/services/ai-content-writing" and method == "GET":
            await _send_html(send, 200, pages.service_content_page())
            return
        if path == "/services/ai-seo-optimization" and method == "GET":
            await _send_html(send, 200, pages.service_seo_page())
            return
        if path == "/pricing" and method == "GET":
            # Affiliate visitors (ref cookie) don't get the welcome discount - they bring a
            # commission instead - so don't advertise the badge to them.
            _has_ref = any(p.strip().startswith("ref=") and len(p.strip()) > 4
                           for p in headers.get(b"cookie", b"").decode().split(";"))
            await _send_html(send, 200, pages.pricing_page(
                country=_geo_country(headers), show_welcome=not _has_ref))
            return
        if path == "/set-currency" and method == "GET":
            # manual currency switch: ?c=IN|US + ?next=/path. Sets a 1-year cookie.
            cq = urllib.parse.parse_qs(query)
            c = (cq.get("c", ["US"])[0]).upper()
            c = "IN" if c == "IN" else "US"
            nxt = _safe_next(cq.get("next", ["/pricing"])[0], "/pricing")
            ck = f"cur={c}; Path=/; Max-Age={365*24*3600}; SameSite=Lax"
            await _send_html(send, 302, "", [(b"set-cookie", ck.encode()),
                                             (b"location", nxt.encode())])
            return
        if path == "/faq" and method == "GET":
            await _send_html(send, 200, pages.faq_page())
            return
        # ----- SEO/GEO: robots.txt, sitemap.xml, llms.txt -----
        if path == "/robots.txt" and method == "GET":
            body = (
                "# wptaskify robots.txt\n"
                "User-agent: *\nAllow: /\n\n"
                "# AI search / retrieval bots (drive AI citations) - allowed\n"
                "User-agent: OAI-SearchBot\nAllow: /\n"
                "User-agent: ChatGPT-User\nAllow: /\n"
                "User-agent: PerplexityBot\nAllow: /\n"
                "User-agent: Perplexity-User\nAllow: /\n"
                "User-agent: Claude-SearchBot\nAllow: /\n"
                "User-agent: Google-Extended\nAllow: /\n\n"
                "# AI training crawlers - allowed to maximize presence\n"
                "User-agent: GPTBot\nAllow: /\n"
                "User-agent: ClaudeBot\nAllow: /\n"
                "User-agent: CCBot\nAllow: /\n\n"
                f"Sitemap: {PUBLIC_URL}/sitemap.xml\n")
            await send({"type": "http.response.start", "status": 200,
                        "headers": [(b"content-type", b"text/plain; charset=utf-8")]})
            await send({"type": "http.response.body", "body": body.encode()})
            return
        if path == "/sitemap.xml" and method == "GET":
            # Fully auto-generated from PUBLIC_PAGES + any published blog posts.
            body = _build_sitemap()
            await send({"type": "http.response.start", "status": 200,
                        "headers": [(b"content-type", b"application/xml; charset=utf-8")]})
            await send({"type": "http.response.body", "body": body.encode()})
            return
        if path == "/llms.txt" and method == "GET":
            # Auto-generated from PUBLIC_PAGES + published blog posts (same source as sitemap).
            body = _build_llms()
            await send({"type": "http.response.start", "status": 200,
                        "headers": [(b"content-type", b"text/plain; charset=utf-8")]})
            await send({"type": "http.response.body", "body": body.encode()})
            return
        if path == "/terms" and method == "GET":
            await _send_html(send, 200, pages.terms_page())
            return
        if path == "/privacy" and method == "GET":
            await _send_html(send, 200, pages.privacy_page())
            return
        if path == "/refund" and method == "GET":
            await _send_html(send, 200, pages.refund_page())
            return
        if path == "/shipping" and method == "GET":
            await _send_html(send, 200, pages.shipping_page())
            return
        if path == "/security" and method == "GET":
            await _send_html(send, 200, pages.security_page())
            return
        if path == "/about" and method == "GET":
            await _send_html(send, 200, pages.about_page())
            return
        if path == "/contact" and method == "GET":
            _qs = urllib.parse.parse_qs(query)
            _svc = (_qs.get("service") or [""])[0]
            _svc = _svc if _svc in ("wordpress-ai-setup", "custom-ai-tools",
                                    "ai-content-writing", "ai-seo-optimization") else ""
            _sent = "sent" in _qs
            await _send_html(send, 200, pages.contact_page(service=_svc, sent=_sent))
            return
        if path == "/contact" and method == "POST":
            f = _form(await _read_body(receive))
            name = (f.get("name", "") or "").strip()[:200]
            email = (f.get("email", "") or "").strip()[:200]
            msg = (f.get("message", "") or "").strip()[:5000]
            svc = (f.get("service", "") or "").strip()[:80]
            if not name or not email or not msg or "@" not in email:
                await _send_html(send, 200, pages.contact_page(
                    service=svc, error="Please fill in your name, a valid email, and a message."))
                return
            # Basic metadata for the admin (IP + short UA), no PII beyond the form.
            ua = headers.get(b"user-agent", b"").decode("utf-8", "ignore")[:200]
            ip = (headers.get(b"x-forwarded-for", b"").decode().split(",")[0].strip()
                  or headers.get(b"x-real-ip", b"").decode())[:60]
            meta = f"ip={ip}; ua={ua}"
            try:
                mid = db.save_contact_message(name, email, msg, service=svc, meta=meta)
                # Notify the owner by email (best-effort; no-op if email disabled).
                try:
                    email_mod.send_contact_notice(name, email, svc, msg, mid)
                except Exception as _e:  # noqa: BLE001
                    print("[contact] notify failed:", _e)
            except Exception as e:  # noqa: BLE001
                print("[contact] save failed:", e)
                await _send_html(send, 200, pages.contact_page(
                    service=svc, error="Something went wrong sending your message. Please email hello@wptaskify.com."))
                return
            await _send_html(send, 303, "", [(b"location", b"/contact?sent=1")])
            return
        if path == "/blog" and method == "GET":
            try:
                _dbposts = db.blog_db_list(published_only=True) if db is not None else []
            except Exception:
                _dbposts = []
            await _send_html(send, 200, pages.blog_index_page(db_posts=_dbposts))
            return
        if path.startswith("/blog/") and method == "GET":
            import blog_posts
            slug = path[len("/blog/"):].strip("/")
            # DB (admin-created) posts first, then the built-in ones.
            dbp = None
            try:
                dbp = db.blog_db_get(slug) if db is not None else None
            except Exception:
                dbp = None
            if dbp and dbp.get("published"):
                await _send_html(send, 200, pages.blog_db_post_page(dbp))
                return
            post = blog_posts.get_post(slug)
            if post:
                await _send_html(send, 200, pages.blog_post_page(post))
            else:
                await _send_html(send, 404, pages.message_page(
                    "Article not found",
                    "That guide doesn't exist or has moved.", "/blog", "See all guides"))
            return
        # ----- Community forum -----
        if path == "/community" and method == "GET":
            _cuid = _get_active_uid(headers)
            await _send_html(send, 200, pages.community_index_page(
                db.forum_categories(), logged_in=bool(_cuid),
                verified=bool(_cuid and db.is_verified(_cuid))))
            return
        if path.startswith("/community/") and method == "GET":
            rest = path[len("/community/"):].strip("/")
            uid = _get_active_uid(headers)
            can_post = bool(uid and db.is_verified(uid))
            # /community/t/<id>-<slug>  -> a single thread
            if rest.startswith("t/"):
                tid = _safe_id(rest[2:].split("-", 1)[0])
                thread = db.forum_thread(tid) if tid else None
                if not thread:
                    await _send_html(send, 404, pages.message_page(
                        "Thread not found", "That discussion doesn't exist or was removed.",
                        "/community", "Back to community"))
                    return
                qs = urllib.parse.parse_qs(query)
                await _send_html(send, 200, pages.community_thread_page(
                    thread, db.forum_posts(tid), can_post,
                    csrf=(_csrf_token(uid) if uid else ""), error=qs.get("err", [""])[0]))
                return
            # /community/<cat>/new  -> new-thread form
            if rest.endswith("/new"):
                cat = db.forum_category(rest[:-len("/new")])
                if not cat:
                    await _send_html(send, 302, "", [(b"location", b"/community")])
                    return
                if not can_post:
                    await _send_html(send, 302, "", [(b"location", b"/login?next=%2Fcommunity")])
                    return
                qs = urllib.parse.parse_qs(query)
                await _send_html(send, 200, pages.community_new_thread_page(
                    cat, csrf=_csrf_token(uid), error=qs.get("err", [""])[0]))
                return
            # /community/<cat>  -> category thread list
            cat = db.forum_category(rest)
            if not cat:
                await _send_html(send, 404, pages.message_page(
                    "Category not found", "That community category doesn't exist.",
                    "/community", "Back to community"))
                return
            await _send_html(send, 200, pages.community_category_page(
                cat, db.forum_threads(cat["id"]), can_post))
            return
        if path.startswith("/community/") and path.endswith("/new") and method == "POST":
            uid = _get_active_uid(headers)
            if not uid or not db.is_verified(uid):
                await _send_html(send, 302, "", [(b"location", b"/login?next=%2Fcommunity")])
                return
            cat_slug = path[len("/community/"):-len("/new")]
            cat = db.forum_category(cat_slug)
            if not cat:
                await _send_html(send, 302, "", [(b"location", b"/community")])
                return
            f = _form(await _read_body(receive))
            if not _csrf_ok(headers, f):
                await _send_html(send, 302, "", [(b"location",
                    f"/community/{cat_slug}/new?err=Session+expired,+please+retry".encode())])
                return
            # rate limit: max 3 new threads per minute
            if db.forum_recent_thread_count(uid, 60) >= 3:
                await _send_html(send, 302, "", [(b"location",
                    f"/community/{cat_slug}/new?err=You're+posting+too+fast.+Try+again+in+a+minute.".encode())])
                return
            tid, slug = db.forum_create_thread(uid, cat["id"], f.get("title", ""), f.get("body", ""))
            if not tid:
                await _send_html(send, 302, "", [(b"location",
                    f"/community/{cat_slug}/new?err=Please+add+a+title+and+details.".encode())])
                return
            await _send_html(send, 302, "", [(b"location",
                f"/community/t/{tid}-{slug}".encode())])
            return
        if path.startswith("/community/t/") and path.endswith("/reply") and method == "POST":
            uid = _get_active_uid(headers)
            if not uid or not db.is_verified(uid):
                await _send_html(send, 302, "", [(b"location", b"/login?next=%2Fcommunity")])
                return
            tid = _safe_id(path[len("/community/t/"):-len("/reply")].split("-", 1)[0])
            f = _form(await _read_body(receive))
            if not _csrf_ok(headers, f):
                await _send_html(send, 302, "", [(b"location",
                    f"/community/t/{tid}-x?err=Session+expired,+please+retry".encode())])
                return
            # rate limit: max 5 replies per 30s
            if db.forum_recent_post_count(uid, 30) >= 5:
                await _send_html(send, 302, "", [(b"location",
                    f"/community/t/{tid}-x?err=You're+posting+too+fast.+Slow+down+a+bit.".encode())])
                return
            ok = db.forum_create_post(uid, tid, f.get("body", ""))
            th = db.forum_thread(tid)
            dest = f"/community/t/{tid}-{th['slug']}" if th else "/community"
            if not ok and th and th.get("locked"):
                dest += "?err=This+thread+is+locked."
            await _send_html(send, 302, "", [(b"location", dest.encode())])
            return

        if path == "/login" and method == "GET":
            await _send_html(send, 200, pages.login_page())
            return
        if path == "/chat" and method == "GET":
            if not BUILTIN_CHAT_ON:
                # Built-in chat hidden for launch - send users to the dashboard.
                await _send_html(send, 302, "", [(b"location", b"/dashboard")])
                return
            uid = _get_active_uid(headers)
            if not uid:
                await _send_html(send, 302, "", [(b"location", b"/login")])
                return
            if REQUIRE_EMAIL_VERIFY and not db.is_verified(uid):
                await _send_html(send, 302, "", [(b"location", b"/verify-sent")])
                return
            sites = db.list_user_sites(uid)
            tok = db.get_token_account(uid)
            await _send_html(send, 200, pages.chat_page(
                sites, tok, chat_enabled=(BUILTIN_CHAT_ON and bool(chat_mod.ANTHROPIC_API_KEY))))
            return
        if path == "/connect-status" and method == "GET":
            # The plugin polls this to VERIFY a real connection, so it never
            # shows "connected" off a stale ?connected=1 URL param.
            qs = urllib.parse.parse_qs(query)
            site = (qs.get("site") or [""])[0]
            connected = db.site_is_registered(site)
            body = json.dumps({
                "connected": bool(connected),
                # Where the user can log in and see their connected sites.
                "dashboard_url": PUBLIC_URL + "/dashboard",
                "mcp_url": PUBLIC_URL + "/mcp",
            }).encode()
            await send({"type": "http.response.start", "status": 200,
                        "headers": [(b"content-type", b"application/json"),
                                    (b"access-control-allow-origin", b"*")]})
            await send({"type": "http.response.body", "body": body})
            return
        if path == "/disconnect" and method == "GET":
            # Plugin one-click Disconnect: remove the site from our DB so it's
            # truly disconnected. Requires the user to be logged into wptaskify in the
            # same browser, and only removes THEIR OWN site (never another tenant's) -
            # otherwise anyone could delete any site by guessing its URL.
            uid = _get_active_uid(headers)
            if not uid:
                nxt = urllib.parse.quote("/disconnect?" + query)
                await _send_html(send, 200, pages.login_page(authorize_next=nxt))
                return
            qs = urllib.parse.parse_qs(query)
            site = (qs.get("site") or [""])[0]
            removed = db.delete_site_by_url_for_user(uid, site) if site else 0
            body = json.dumps({"disconnected": bool(removed), "removed": removed}).encode()
            await send({"type": "http.response.start", "status": 200,
                        "headers": [(b"content-type", b"application/json")]})
            await send({"type": "http.response.body", "body": body})
            return
        if path == "/connect" and method == "GET":
            # One-click connect from the wptaskify plugin.
            qs = urllib.parse.parse_qs(query)
            site = (qs.get("site") or [""])[0]
            wp_user = (qs.get("user") or [""])[0]
            pw = (qs.get("pw") or [""])[0]
            ret = (qs.get("return") or [""])[0]
            uid = _get_active_uid(headers)
            if not uid:
                # not logged in -> show login, preserving the connect query
                nxt = urllib.parse.quote("/connect?" + query)
                await _send_html(send, 200, pages.login_page(authorize_next=nxt))
                return
            # logged in -> validate + store the site, then bounce back to the plugin
            if not (site and wp_user and pw):
                await _send_html(send, 400, pages.connect_error_page(
                    site or "your site",
                    "The connect link was missing the site URL, username or "
                    "application password. Please click Connect again from the "
                    "wptaskify plugin."))
                return
            ok, info = _validate_wp(site, wp_user, pw)
            if not ok:
                # DON'T silently pretend it connected - the plugin would show
                # "connected" while no site was saved (then MCP fails later).
                # Bounce the user BACK to their WordPress plugin page with an
                # honest error reason, so they see it where they clicked Connect.
                if ret:
                    err_ret = ret.replace("connected=1", "connect_err=rest_unreachable")
                    if "connect_err=" not in err_ret:
                        sep = "&" if "?" in err_ret else "?"
                        err_ret = err_ret + sep + "connect_err=rest_unreachable"
                    await _send_html(send, 302, "", [(b"location", err_ret.encode())])
                    return
                await _send_html(send, 502, pages.connect_error_page(site, (
                    "We couldn't reach your site's WordPress REST API to verify "
                    "the connection (" + str(info) + ").\n\n"
                    "This usually means the site's REST API is blocked or erroring "
                    "(a plugin, security rule, or server error). Fix that on the "
                    "site, then click Connect again.")))
                return
            # Enforce plan site limit on the one-click plugin connect too.
            _allowed, _limit, _current = db.can_add_site(uid)
            if not _allowed:
                await _send_html(send, 403, pages.connect_error_page(site, (
                    f"Your plan includes {_limit} site(s) and you've already connected "
                    f"{_current}. Upgrade your plan to connect more sites.")))
                return
            _sid = db.add_site(uid, site, wp_user, pw, max_sites=_limit)
            if not _sid:
                await _send_html(send, 403, pages.connect_error_page(site,
                    "You've reached your plan's site limit. Upgrade to connect more sites."))
                return
            _notify_site_connected(uid, site)
            dest = ret if ret else "/dashboard?added=1"
            await _send_html(send, 302, "", [(b"location", dest.encode())])
            return

        # --- Google Analytics + Search Console OAuth ---
        if path == "/google/connect" and method == "GET":
            uid = _get_active_uid(headers)
            if not uid:
                await _send_html(send, 302, "", [(b"location", b"/login?next=%2Fdashboard")])
                return
            if not google_api.configured():
                await _send_html(send, 302, "", [(b"location",
                    b"/dashboard?err=Google+is+not+configured+yet")])
                return
            # Optional ?site=<site_id> - connect a DIFFERENT Google account for that
            # specific site (each site's Search Console can live on its own Gmail).
            _gsite = (urllib.parse.parse_qs(query).get("site") or [""])[0]
            _gsite = _safe_uuid(_gsite) if _gsite else ""
            # state = signed "google|uid|site_id" so the callback binds to this user+site.
            state = _sign("google|" + uid + "|" + _gsite)
            await _send_html(send, 302, "", [(b"location", google_api.auth_url(state).encode())])
            return

        if path == "/google/callback" and method == "GET":
            qs = urllib.parse.parse_qs(query)
            state = (qs.get("state") or [""])[0]
            code = (qs.get("code") or [""])[0]
            err = (qs.get("error") or [""])[0]
            payload = _unsign(state) if state else None
            if err or not payload or not payload.startswith("google|"):
                await _send_html(send, 302, "", [(b"location",
                    b"/dashboard?err=Google+connection+was+cancelled")])
                return
            _parts = payload.split("|")
            uid = _parts[1] if len(_parts) > 1 else ""
            gsite = _parts[2] if len(_parts) > 2 and _parts[2] else None
            # The logged-in user must match the state's user (defence in depth).
            cur = _get_active_uid(headers)
            if not cur or cur != uid:
                await _send_html(send, 302, "", [(b"location", b"/login?next=%2Fdashboard")])
                return
            try:
                tok = google_api.exchange_code(code)
                if not tok.get("refresh_token"):
                    await _send_html(send, 302, "", [(b"location",
                        b"/dashboard?err=Google+did+not+return+a+refresh+token%2C+try+again")])
                    return
                db.save_google_account(uid, tok["refresh_token"], tok.get("email", ""),
                                       site_id=gsite)
                # AUTO-SELECT so the user doesn't have to pick anything: if the
                # account has exactly one GA4 property and/or one Search Console site,
                # select it automatically. (If several, they pick from the dropdown.)
                try:
                    _at = google_api.access_token(tok["refresh_token"])
                    if _at:
                        _props, _ = google_api.list_ga_properties(_at)
                        _scs, _ = google_api.list_sc_sites(_at)
                        _p = _props[0]["property_id"] if len(_props) == 1 else None
                        _s = _scs[0]["site"] if len(_scs) == 1 else None
                        if _p or _s:
                            db.set_google_selection(uid, ga_property_id=_p, sc_site=_s,
                                                    site_id=gsite)
                except Exception as _e:  # noqa: BLE001
                    print("[google] auto-select skipped:", _e)
            except Exception as e:  # noqa: BLE001
                print("[google] callback error:", e)
                await _send_html(send, 302, "", [(b"location",
                    b"/dashboard?err=Could+not+finish+Google+connection")])
                return
            await _send_html(send, 302, "", [(b"location",
                b"/dashboard?ok=Google+Analytics+connected")])
            return

        if path == "/google/disconnect" and method == "POST":
            uid = _get_active_uid(headers)
            if not uid:
                await _send_html(send, 401, "Not logged in")
                return
            f = _form(await _read_body(receive))
            if not _csrf_ok(headers, f):
                await _send_html(send, 403, "Bad CSRF token")
                return
            _gsite = _safe_uuid(f.get("site_id", "")) or None
            db.delete_google_account(uid, site_id=_gsite)
            await _send_html(send, 302, "", [(b"location", b"/dashboard?ok=Google+disconnected")])
            return

        if path == "/google/select" and method == "POST":
            uid = _get_active_uid(headers)
            if not uid:
                await _send_html(send, 401, "Not logged in")
                return
            f = _form(await _read_body(receive))
            if not _csrf_ok(headers, f):
                await _send_html(send, 403, "Bad CSRF token")
                return
            prop = (f.get("ga_property_id") or "").strip()
            site = (f.get("sc_site") or "").strip()
            _gsite = _safe_uuid(f.get("site_id", "")) or None
            db.set_google_selection(uid,
                                    ga_property_id=prop if prop else None,
                                    sc_site=site if site else None,
                                    site_id=_gsite)
            await _send_html(send, 302, "", [(b"location", b"/dashboard?ok=Analytics+settings+saved")])
            return

        if path == "/signup" and method == "POST":
            f = _form(await _read_body(receive))
            nxt = f.get("next", "")
            # A3 - throttle automated account creation (each grants free credits).
            if _rate_limited("signup", _client_ip(headers), limit=8, window=3600):
                await _send_html(send, 429, pages.signup_page(
                    error="Too many sign-ups from your network. Please try again later.",
                    authorize_next=nxt))
                return
            email_addr = f.get("email", "")
            # A plan intent may ride in via next=/checkout-after?plan=<key>.
            buy_plan = ""
            if "checkout-after" in nxt and "plan=" in nxt:
                buy_plan = urllib.parse.parse_qs(nxt.split("?", 1)[-1]).get("plan", [""])[0]
            # A2 - server-side validation (browser attributes are bypassable via direct POST).
            pw = f.get("password", "")
            if not _valid_email(email_addr):
                await _send_html(send, 400, pages.signup_page(
                    error="Please enter a valid email address.", authorize_next=nxt))
                return
            pw_err = _password_error(pw)
            if pw_err:
                await _send_html(send, 400, pages.signup_page(error=pw_err, authorize_next=nxt))
                return
            try:
                uid = db.create_user(email_addr, pw)
            except Exception as e:
                msg = "This email is already registered." if "unique" in str(e).lower() else f"Signup failed: {e}"
                await _send_html(send, 400, pages.signup_page(error=msg, authorize_next=nxt))
                return
            # Affiliate attribution: if a ref cookie is present, link this signup to the referrer.
            _refc = ""
            for _part in headers.get(b"cookie", b"").decode().split(";"):
                _part = _part.strip()
                if _part.startswith("ref="):
                    _refc = _part[4:]
                    break
            if _refc:
                try:
                    db.attach_referral(uid, _refc)
                except Exception:
                    pass
            # Send verification email (carrying the plan so verify -> checkout).
            _send_verify_email(uid, email_addr, plan=buy_plan)
            cookie = f"sid={_sign_session(uid)}; Path=/; HttpOnly; Secure; SameSite=Lax"
            # After signup go to a "check your email" page (verify required).
            extra = ("?plan=" + buy_plan) if buy_plan else (("?next=" + nxt) if nxt else "")
            await _send_html(send, 302, "", [(b"set-cookie", cookie.encode()),
                                             (b"location", ("/verify-sent" + extra).encode())])
            return
        if path == "/login" and method == "POST":
            f = _form(await _read_body(receive))
            nxt = f.get("next", "")
            # A3 - throttle online password guessing. 10 attempts / 5 min / IP is far above
            # any human's typo rate but kills brute-force. argon2 already makes each try slow.
            if _rate_limited("login", _client_ip(headers), limit=10, window=300):
                await _send_html(send, 429, pages.login_page(
                    error="Too many login attempts. Please wait a few minutes and try again.",
                    authorize_next=nxt))
                return
            uid = db.authenticate_user(f.get("email", ""), f.get("password", ""))
            if not uid:
                await _send_html(send, 401,
                                 pages.login_page(error="Incorrect email or password.", authorize_next=nxt))
                return
            if db.is_banned(uid):
                await _send_html(send, 403,
                                 pages.login_page(error="This account has been suspended. Contact support.", authorize_next=nxt))
                return
            cookie = f"sid={_sign_session(uid)}; Path=/; HttpOnly; Secure; SameSite=Lax"
            dest = _safe_next(nxt, "/dashboard")
            await _send_html(send, 302, "", [(b"set-cookie", cookie.encode()),
                                             (b"location", dest.encode())])
            return
        if path == "/logout" and method == "POST":
            # Server-side revoke: bump session_ver so the just-cleared cookie (and any
            # copy of it) can never be replayed - not just cleared in this browser.
            _luid = _get_session_uid(headers)
            if _luid and db is not None:
                try:
                    db.bump_session_ver(_luid)
                except Exception:
                    pass
            await _send_html(send, 302, "", [(b"set-cookie",
                             b"sid=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=Lax"),
                                             (b"location", b"/")])
            return

        # ----- Email verification -----
        if path == "/verify-sent" and method == "GET":
            uid = _get_active_uid(headers)
            email_addr = db.get_email(uid) if uid else ""
            _q = urllib.parse.parse_qs(query)
            resent = "resent" in _q
            toofast = "toofast" in _q
            await _send_html(send, 200, pages.verify_sent_page(email_addr, resent, toofast))
            return
        if path == "/verify-resend" and method == "POST":
            uid = _get_active_uid(headers)
            # A3 - a verification email only ever goes to the logged-in user's OWN address
            # (needs a valid session), so this can't be used to bomb a stranger. But cap it
            # so a user can't spam themselves / burn our Resend quota: 5 per 15 min, by uid
            # and by IP.
            ip = _client_ip(headers)
            if _rate_limited(f"vresend:{uid}", ip or (uid or "?"), limit=5, window=900) or \
               _rate_limited("vresend-ip", ip, limit=20, window=900):
                await _send_html(send, 302, "", [(b"location", b"/verify-sent?toofast=1")])
                return
            if uid:
                _send_verify_email(uid, db.get_email(uid))
            await _send_html(send, 302, "", [(b"location", b"/verify-sent?resent=1")])
            return
        if path == "/verify" and method == "GET":
            tok = (urllib.parse.parse_qs(query).get("token") or [""])[0]
            vid = db.consume_token(tok, "verify") if tok else None
            if not vid:
                await _send_html(send, 400, pages.message_page(
                    "Link expired", "<p class=sub>This verification link is invalid or expired. "
                    "Log in and resend it.</p>", "/login", "Go to login"))
                return
            db.mark_verified(vid)
            # Welcome email once the address is confirmed.
            try:
                prof = db.get_profile(vid)
                if prof and email_mod.enabled() and db.email_enabled("welcome"):
                    email_mod.send_welcome(prof["email"], prof.get("name", ""))
            except Exception:
                pass
            cookie = f"sid={_sign_session(vid)}; Path=/; HttpOnly; Secure; SameSite=Lax"
            # If they signed up by picking a paid plan, send them straight to checkout.
            vplan = (urllib.parse.parse_qs(query).get("plan") or [""])[0]
            dest = (f"/checkout-after?plan={vplan}"
                    if vplan in ("owai_mini", "owai_starter", "owai_pro")
                    else "/dashboard?verified=1")
            await _send_html(send, 302, "", [(b"set-cookie", cookie.encode()),
                                             (b"location", dest.encode())])
            return

        # ----- Auto-checkout after signup (GET -> shows a one-click pay page) -----
        if path == "/checkout-after" and method == "GET":
            uid = _get_active_uid(headers)
            if not uid:
                await _send_html(send, 302, "", [(b"location", b"/login")])
                return
            plan = (urllib.parse.parse_qs(query).get("plan") or [""])[0]
            if plan not in ("owai_mini", "owai_starter", "owai_pro"):
                await _send_html(send, 302, "", [(b"location", b"/dashboard")])
                return
            currency = _billing_currency(headers)
            # Guard: some plans aren't sold in every currency (e.g. Mini is India/INR only).
            # Don't render a broken "$0 / Pay $0" page - send them to pricing instead.
            if not rzp_mod.plan_supported(plan, currency):
                await _send_html(send, 302, "", [(b"location", b"/pricing")])
                return
            label, amt = rzp_mod.plan_price(plan, currency)
            sym = "₹" if currency == "INR" else "$"
            # First-month welcome discount: auto-applied for eligible first-time buyers.
            # We check by user + IP here; the device fingerprint is added at POST time
            # (JS supplies it) and re-checked, so the real gate is on /checkout.
            wpct = db.welcome_discount_percent(plan)
            welcome = 0
            base_amt = amt
            if wpct and db.welcome_eligible(uid, ip=_client_ip(headers)):
                welcome = wpct
                base_amt = round(amt * (100 - wpct) / 100.0, 2)
            tax_amt, total, rate = db.gst_on(base_amt, currency)
            await _send_html(send, 200, pages.checkout_confirm_page(
                plan, label, sym, amt, tax=tax_amt, total=total, rate=rate,
                welcome_pct=welcome, discounted=base_amt))
            return

        # ----- Password reset -----
        if path == "/forgot" and method == "GET":
            await _send_html(send, 200, pages.forgot_page())
            return
        if path == "/forgot" and method == "POST":
            f = _form(await _read_body(receive))
            target = (f.get("email", "") or "").strip().lower()
            # A3 - reset emails can be sent to ANY address (no session), so this is the main
            # email-bomb + enumeration vector. Throttle by IP and by target address. When
            # limited we skip sending but STILL show the identical success page, so an
            # attacker can't tell rate-limited from sent (keeps enumeration-safe).
            ip = _client_ip(headers)
            limited = (_rate_limited("forgot-ip", ip, limit=15, window=3600)
                       or (target and _rate_limited("forgot-to", target,
                                                     limit=4, window=3600)))
            if not limited:
                u = db.get_user_by_email(f.get("email", ""))
                if u:
                    tok = db.create_token(u["id"], "reset", hours=1)
                    link = f"{PUBLIC_URL}/reset?token={tok}"
                    email_mod.send_reset(u["email"], link)
            # Always show success (don't leak which emails exist).
            await _send_html(send, 200, pages.message_page(
                "Check your email", "<p class=sub>If that email is registered, we've sent a "
                "password reset link. It expires in 1 hour.</p>", "/login", "Back to login"))
            return
        if path == "/reset" and method == "GET":
            tok = (urllib.parse.parse_qs(query).get("token") or [""])[0]
            await _send_html(send, 200, pages.reset_page(tok))
            return
        if path == "/reset" and method == "POST":
            f = _form(await _read_body(receive))
            tok = f.get("token", "")
            pw = f.get("password", "")
            # A2 - validate the new password BEFORE consuming the (single-use) token, so a
            # weak password doesn't burn the reset link and force the user to start over.
            pw_err = _password_error(pw)
            if pw_err:
                await _send_html(send, 400, pages.reset_page(tok, error=pw_err))
                return
            vid = db.consume_token(tok, "reset") if tok else None
            if not vid:
                await _send_html(send, 400, pages.message_page(
                    "Link expired", "<p class=sub>This reset link is invalid or expired.</p>",
                    "/forgot", "Request a new one"))
                return
            db.set_password(vid, pw)
            db.mark_verified(vid)  # resetting via email also proves ownership
            cookie = f"sid={_sign_session(vid)}; Path=/; HttpOnly; Secure; SameSite=Lax"
            await _send_html(send, 302, "", [(b"set-cookie", cookie.encode()),
                                             (b"location", b"/dashboard")])
            return
        if path == "/dashboard" and method == "GET":
            uid = _get_active_uid(headers)
            if not uid:
                await _send_html(send, 302, "", [(b"location", b"/login")])
                return
            # Verify-required gate: unverified users go to the "check email" page.
            if REQUIRE_EMAIL_VERIFY and not db.is_verified(uid):
                await _send_html(send, 302, "", [(b"location", b"/verify-sent")])
                return
            sites = db.list_user_sites(uid)
            account = db.get_account(uid)
            email_addr = db.get_email(uid) or ""
            verified = db.is_verified(uid)
            flash, ok = "", False
            qs = urllib.parse.parse_qs(query)
            if "verified" in qs:
                flash, ok = "Email verified - welcome to wptaskify!", True
            elif "added" in qs:
                flash, ok = "Site connected! Now link it to your AI below.", True
            elif "ok" in qs:
                flash, ok = qs["ok"][0], True
            elif "err" in qs and qs["err"][0] and "://" not in qs["err"][0] and len(qs["err"][0]) < 120:
                flash, ok = qs["err"][0], False
            elif "err" in qs:
                flash, ok = "Couldn't connect site: " + qs["err"][0], False
            elif "keysaved" in qs:
                flash, ok = "Gemini key saved - you now have unlimited AI images.", True
            elif "removed" in qs:
                flash, ok = "Site removed.", True
            token_acct = db.get_token_account(uid)
            toolcall_acct = db.get_toolcall_account(uid)
            txns = db.list_transactions(uid, limit=20)
            usage = db.get_usage_summary(uid)
            profile = db.get_profile(uid)
            _country = _geo_country(headers)
            affiliate = {
                "code": db.get_ref_code(uid),
                "summary": db.affiliate_summary(uid),
                "referrals": db.affiliate_referrals(uid),
                "payouts": db.payout_history(uid),
                "payout_method": db.get_payout_method(uid),
                "rate": db.get_commission_rate(),
                "country": _country,
            }
            google_acct = db.get_google_account(uid)
            google_all = db.list_google_accounts(uid)
            # For each connected Google account, fetch its GA4 properties + Search
            # Console sites so the dashboard can show a DROPDOWN (no manual typing) and
            # a list of what's available. Keyed by site_id ("" = account default).
            google_opts = {}
            for _acc in google_all:
                _key = _acc.get("site_id") or ""
                try:
                    _rt = db.get_google_refresh_token(uid, site_id=_acc.get("site_id"))
                    if not _rt:
                        continue
                    _at = google_api.access_token(_rt)
                    if not _at:
                        continue
                    _props, _pe = google_api.list_ga_properties(_at)
                    _scs, _se = google_api.list_sc_sites(_at)
                    google_opts[_key] = {"properties": _props, "sites": _scs,
                                         "error": _pe or _se or ""}
                except Exception as _e:  # noqa: BLE001
                    google_opts[_key] = {"properties": [], "sites": [], "error": str(_e)[:120]}
            await _send_html(send, 200, pages.dashboard(
                sites, PUBLIC_URL, account, flash, ok, email=email_addr, verified=verified,
                token_account=token_acct, toolcall_account=toolcall_acct,
                chat_enabled=(BUILTIN_CHAT_ON and bool(chat_mod.ANTHROPIC_API_KEY)),
                country=_country, txns=txns, usage=usage, profile=profile,
                csrf=_csrf_token(uid), affiliate=affiliate,
                google=google_acct, google_configured=google_api.configured(),
                google_all=google_all, google_opts=google_opts))
            return
        # ----- Affiliate: save payout method + request payout -----
        if path == "/affiliate/payout-method" and method == "POST":
            uid = _get_active_uid(headers)
            if not uid:
                await _send_html(send, 302, "", [(b"location", b"/login")])
                return
            f = _form(await _read_body(receive))
            if not _csrf_ok(headers, f):
                await _send_html(send, 302, "", [(b"location", b"/dashboard?err=Session+expired#affiliate")])
                return
            db.set_payout_method(uid, f.get("method", ""))
            await _send_html(send, 302, "", [(b"location", b"/dashboard?ok=Payout+details+saved#affiliate")])
            return
        if path == "/affiliate/request-payout" and method == "POST":
            uid = _get_active_uid(headers)
            if not uid:
                await _send_html(send, 302, "", [(b"location", b"/login")])
                return
            f = _form(await _read_body(receive))
            if not _csrf_ok(headers, f):
                await _send_html(send, 302, "", [(b"location", b"/dashboard?err=Session+expired#affiliate")])
                return
            currency = "INR" if f.get("currency") == "INR" else "USD"
            _ok, _msg = db.request_payout(uid, currency)
            q = ("ok=" if _ok else "err=") + urllib.parse.quote(_msg)
            await _send_html(send, 302, "", [(b"location", f"/dashboard?{q}#affiliate".encode())])
            return
        # ----- Account settings (self-service) -----
        if path.startswith("/settings/") and method == "POST":
            uid = _get_active_uid(headers)
            if not uid:
                await _send_html(send, 302, "", [(b"location", b"/login")])
                return
            act = path[len("/settings/"):]
            f = _form(await _read_body(receive))
            if not _csrf_ok(headers, f):
                await _send_html(send, 302, "", [(b"location", b"/dashboard?err=Session+expired,+please+retry#settings")])
                return

            def _back(msg, ok=True):
                q = ("ok=" if ok else "err=") + urllib.parse.quote(msg)
                return [(b"location", (f"/dashboard?{q}#settings").encode())]

            if act == "name":
                db.update_name(uid, f.get("name", ""))
                await _send_html(send, 302, "", _back("Name updated."))
            elif act == "gstin":
                g = (f.get("gstin", "") or "").strip().upper()
                if g and not db.valid_gstin(g):
                    await _send_html(send, 302, "", _back("That doesn't look like a valid GSTIN.", ok=False))
                else:
                    db.set_gstin(uid, g)
                    await _send_html(send, 302, "", _back("GSTIN saved." if g else "GSTIN removed."))
            elif act == "notify":
                db.set_notify_email(uid, f.get("notify") == "1")
                on = f.get("notify") == "1"
                await _send_html(send, 302, "", _back(
                    "Email notifications turned on." if on else "Email notifications turned off."))
            elif act == "password":
                _pwerr = _password_error(f.get("new", ""))
                if not db.verify_user_password(uid, f.get("current", "")):
                    await _send_html(send, 302, "", _back("Current password is incorrect.", ok=False))
                elif _pwerr:
                    await _send_html(send, 302, "", _back(_pwerr, ok=False))
                else:
                    db.set_password(uid, f.get("new", ""))
                    # set_password bumps session_ver (revoking OTHER sessions). Re-issue a
                    # fresh cookie so THIS browser stays logged in with the new version.
                    _hdrs = _back("Password updated. Other sessions were signed out.")
                    _hdrs.append((b"set-cookie",
                                  f"sid={_sign_session(uid)}; Path=/; HttpOnly; Secure; SameSite=Lax".encode()))
                    await _send_html(send, 302, "", _hdrs)
            elif act == "email":
                if not db.verify_user_password(uid, f.get("password", "")):
                    await _send_html(send, 302, "", _back("Password is incorrect.", ok=False))
                else:
                    okc, err = db.change_email(uid, f.get("email", ""))
                    if not okc:
                        await _send_html(send, 302, "", _back(err, ok=False))
                    else:
                        _send_verify_email(uid, f.get("email", "").strip().lower())
                        await _send_html(send, 302, "", [(b"location", b"/verify-sent")])
            elif act == "delete":
                db.delete_own_account(uid)
                await _send_html(send, 302, "", [(b"set-cookie", b"sid=; Path=/; Max-Age=0"),
                                                 (b"location", b"/?deleted=1")])
            else:
                await _send_html(send, 302, "", [(b"location", b"/dashboard#settings")])
            return

        if path == "/byok" and method == "POST":
            uid = _get_active_uid(headers)
            if not uid:
                await _send_html(send, 302, "", [(b"location", b"/login")])
                return
            # BYOK is an Agency-plan perk only.
            acct = db.get_account(uid)
            if not acct or acct.get("plan") != "agency":
                await _send_html(send, 302, "", [(b"location", b"/dashboard#credits")])
                return
            f = _form(await _read_body(receive))
            key = f.get("gemini_key", "").strip()
            if key:
                db.set_user_gemini_key(uid, key)
            await _send_html(send, 302, "", [(b"location", b"/dashboard?keysaved=1")])
            return

        # ----- Billing / payments -----
        # /billing is the Razorpay/Stripe post-payment callback target. We no longer render
        # a separate billing page (it duplicated & diverged from the dashboard Plan panel -
        # D2). Redirect to the single billing surface: the dashboard Plan tab, carrying the
        # success/canceled flash so the user sees confirmation there.
        if path == "/billing" and method == "GET":
            uid = _get_active_uid(headers)
            if not uid:
                await _send_html(send, 302, "", [(b"location", b"/login")])
                return
            qs = urllib.parse.parse_qs(query)
            if "success" in qs:
                loc = b"/dashboard?ok=Payment+successful+-+your+account+is+updated#plan"
            elif "canceled" in qs:
                loc = b"/dashboard?err=Checkout+canceled#plan"
            else:
                loc = b"/dashboard#plan"
            await _send_html(send, 302, "", [(b"location", loc)])
            return
        if path == "/coupon-preview" and method == "GET":
            # Live coupon check for the review page: return the recalculated breakdown.
            uid = _get_active_uid(headers)
            if not uid:
                await _send_json(send, 401, {"ok": False, "error": "login required"})
                return
            q = urllib.parse.parse_qs(query)
            plan = (q.get("plan") or [""])[0]
            code = ((q.get("code") or [""])[0] or "").strip().upper()
            currency = _billing_currency(headers)
            if not rzp_mod.plan_supported(plan, currency):
                await _send_json(send, 400, {"ok": False, "error": "Plan not available"})
                return
            _label, list_amt = rzp_mod.plan_price(plan, currency)
            base_amt = list_amt
            if code:
                coup, cerr = db.validate_coupon(code, currency)
                if not coup:
                    await _send_json(send, 200, {"ok": False, "error": cerr or "Invalid code"})
                    return
                base_amt = db.apply_coupon_amount(coup, list_amt, currency)
            tax_amt, total, rate = db.gst_on(base_amt, currency)
            await _send_json(send, 200, {
                "ok": True, "list": list_amt, "base": base_amt,
                "tax": tax_amt, "total": total, "rate": rate, "currency": currency,
            })
            return

        if path == "/checkout" and method == "POST":
            uid = _get_active_uid(headers)
            if not uid:
                await _send_json(send, 401, {"error": "login required"})
                return
            f = _form(await _read_body(receive))
            plan = f.get("plan", "")
            recurring = f.get("recurring", "1") == "1"
            coupon_code = (f.get("coupon", "") or "").strip().upper()
            email_addr = db.get_email(uid) or ""
            # Razorpay for everyone: India -> INR, international -> USD.
            currency = _billing_currency(headers)
            try:
                if not (rzp_mod.enabled() and rzp_mod.plan_supported(plan, currency)):
                    await _send_json(send, 503, {"error": "This plan isn't available for online purchase yet."})
                    return
                # Base price (list), minus optional coupon.
                _label, base_amt = rzp_mod.plan_price(plan, currency)
                applied = ""
                welcome_claim = None  # (plan, pct) to record after we build the link
                if coupon_code:
                    coup, cerr = db.validate_coupon(coupon_code, currency)
                    if not coup:
                        await _send_html(send, 302, "", [(b"location",
                            (f"/dashboard?err={urllib.parse.quote(cerr)}#plan").encode())])
                        return
                    base_amt = db.apply_coupon_amount(coup, base_amt, currency)
                    applied = coupon_code
                else:
                    # No manual coupon -> auto first-month welcome discount for eligible
                    # first-time buyers. Re-checked SERVER-SIDE with device fingerprint + IP
                    # (the /checkout-after page only checked user+IP), so a new email on the
                    # same device/IP is caught here.
                    wpct = db.welcome_discount_percent(plan)
                    if wpct:
                        fp = (f.get("fp", "") or "").strip()[:128]
                        cip = _client_ip(headers)
                        if db.welcome_eligible(uid, fingerprint=fp, ip=cip):
                            base_amt = round(base_amt * (100 - wpct) / 100.0, 2)
                            applied = f"WELCOME{wpct}"   # shows on invoice/notes
                            welcome_claim = (plan, wpct, fp, cip)
                # GST: 18% on INR only (international USD = no tax).
                tax_amt, total, rate = db.gst_on(base_amt, currency)
                # 100%-off coupon (total is 0): grant the plan directly instead of sending
                # the user to Razorpay to pay a bogus 1-unit minimum. This keeps what they
                # were shown (Total 0) matching what actually happens (no charge).
                if total <= 0:
                    # Idempotency: a replay of this same free-checkout (same user + coupon)
                    # must not re-redeem the coupon or re-grant. Claim a one-time key first.
                    free_key = f"freecheckout:{uid}:{applied or plan}"
                    try:
                        if not db.mark_event_processed(free_key):
                            await _send_html(send, 302, "", [(b"location",
                                b"/dashboard?ok=Plan+already+active#plan")])
                            return
                    except Exception:
                        pass
                    # B4 - a coupon free-grant is still a ONE-TIME grant: give it the same
                    # ~1-month expiry so a leaked 100%-off code can't mint permanent free Pro.
                    db.set_plan(uid, plan, valid_days=31)
                    db.set_subscription(uid, "coupon", plan, "active")
                    try:
                        db.record_transaction(uid, "coupon", "plan", plan, 0, "",
                                              currency=currency, base_amount=0, tax_amount=0)
                    except Exception:
                        pass
                    if applied:
                        try:
                            db.redeem_coupon(applied, uid, plan)
                        except Exception:
                            pass
                    await _send_html(send, 302, "", [(b"location",
                        b"/dashboard?ok=Plan+activated+with+your+coupon#plan")])
                    return
                # AUTO-RENEWAL: if no first-month discount/coupon is applied AND a Razorpay
                # subscription plan is configured for this (plan,currency), sell it as a
                # recurring subscription so it renews automatically each month. A discounted
                # first month uses the one-time link (Razorpay subscriptions bill the full
                # plan amount every cycle, so we can't put a one-off discount inside one).
                use_sub = (not applied) and rzp_mod.subscriptions_available(plan, currency)
                if use_sub:
                    url, sub_id = rzp_mod.create_subscription(
                        uid, email_addr, plan, PUBLIC_URL, currency,
                        notes_extra={"base": base_amt, "tax": tax_amt,
                                     "gstin": db.get_gstin(uid)})
                    # Remember the pending subscription id; the plan is granted when the
                    # first subscription.charged webhook arrives.
                    try:
                        db.set_subscription(uid, "razorpay", sub_id, "pending")
                    except Exception:
                        pass
                else:
                    url = rzp_mod.create_plan_link(uid, email_addr, plan, PUBLIC_URL, currency,
                                                   amount=total, coupon=applied,
                                                   base=base_amt, tax=tax_amt,
                                                   gstin=db.get_gstin(uid))
                # Record the welcome claim now (at link creation) so the same user / device /
                # IP can't grab the intro price again even if they abandon this payment and
                # retry with a fresh email. One intro discount per device, period.
                if welcome_claim:
                    try:
                        _wp, _wpct, _wfp, _wip = welcome_claim
                        db.record_welcome_claim(uid, _wp, _wpct, fingerprint=_wfp, ip=_wip)
                    except Exception as _we:  # noqa: BLE001
                        print(f"[welcome] record claim failed uid={uid}: {_we}")
            except Exception as e:  # noqa: BLE001
                await _send_json(send, 400, {"error": str(e)[:150]})
                return
            await _send_html(send, 302, "", [(b"location", url.encode())])
            return
        if path == "/topup" and method == "POST":
            # Payment INITIATION (not a destructive account change): protected by
            # SameSite=Lax + login. No CSRF token needed - and requiring one broke the
            # top-up form on the /billing page which has no token injector. Worst case a
            # forged request just starts a Razorpay payment the user must actively complete.
            uid = _get_active_uid(headers)
            if not uid:
                await _send_json(send, 401, {"error": "login required"})
                return
            f = _form(await _read_body(receive))
            pack = f.get("pack", "")
            email_addr = db.get_email(uid) or ""
            currency = _billing_currency(headers)
            try:
                if rzp_mod.enabled() and rzp_mod.pack_supported(pack, currency):
                    url = rzp_mod.create_topup_link(uid, email_addr, pack, PUBLIC_URL, currency)
                else:
                    await _send_json(send, 503, {"error": "This pack isn't available for online purchase yet."})
                    return
            except Exception as e:  # noqa: BLE001
                await _send_json(send, 400, {"error": str(e)[:150]})
                return
            await _send_html(send, 302, "", [(b"location", url.encode())])
            return
        if path == "/cancel-plan" and method == "POST":
            # Self-service cancel/downgrade (D1). This is a state-changing account action,
            # so it requires the CSRF token (unlike payment INITIATION above). We cancel at
            # period end: the user keeps what they paid for until sub_renews_at, then the
            # daily expiry job drops them to Free.
            uid = _get_active_uid(headers)
            if not uid:
                await _send_html(send, 302, "", [(b"location", b"/login")])
                return
            f = _form(await _read_body(receive))
            if not _csrf_ok(headers, f):
                await _send_html(send, 302, "", [(b"location",
                    b"/dashboard?err=Session+expired,+please+try+again#plan")])
                return
            try:
                # First stop Razorpay from auto-charging again (if it's a subscription).
                # cancel_at_cycle_end -> they keep the plan for the period they already paid.
                sub_id = db.get_subscription_id(uid)
                prov = (db.get_billing_summary(uid) or {}).get("sub_provider", "")
                if sub_id and prov == "razorpay":
                    rzp_mod.cancel_subscription_remote(sub_id, at_cycle_end=True)
                end = db.cancel_subscription(uid)
                if end:
                    msg = f"Plan canceled. You keep your plan until {end}, then move to Free. No further charges."
                else:
                    msg = "Plan canceled. You are now on the Free plan."
            except Exception as e:  # noqa: BLE001
                print(f"[cancel-plan] uid={uid}: {e}")
                await _send_html(send, 302, "", [(b"location",
                    b"/dashboard?err=Could+not+cancel,+please+contact+support#plan")])
                return
            # Best-effort: let the referrer/owner know via email (non-blocking, ignore errors).
            await _send_html(send, 302, "", [(b"location",
                (f"/dashboard?ok={urllib.parse.quote(msg)}#plan").encode())])
            return
        if path == "/webhook/stripe" and method == "POST":
            raw = await _read_body(receive)
            sig = headers.get(b"stripe-signature", b"").decode()
            event = billing_mod.verify_webhook(raw, sig)
            if not event:
                await _send_json(send, 400, {"error": "bad signature"})
                return
            # Run the blocking DB/email work off the event loop so a slow provider
            # (or Resend) can't freeze the whole single-threaded ASGI server.
            await asyncio.get_running_loop().run_in_executor(None, _handle_stripe_event, event)
            await _send_json(send, 200, {"received": True})
            return
        if path == "/webhook/razorpay" and method == "POST":
            raw = await _read_body(receive)
            sig = headers.get(b"x-razorpay-signature", b"").decode()
            event = rzp_mod.verify_webhook(raw, sig)
            if not event:
                await _send_json(send, 400, {"error": "bad signature"})
                return
            await asyncio.get_running_loop().run_in_executor(None, _handle_razorpay_event, event)
            await _send_json(send, 200, {"received": True})
            return
        if path == "/sites" and method == "POST":
            uid = _get_active_uid(headers)
            if not uid:
                await _send_html(send, 302, "", [(b"location", b"/login")])
                return
            f = _form(await _read_body(receive))
            if not _csrf_ok(headers, f):
                await _send_html(send, 302, "", [(b"location", b"/dashboard?err=Session+expired,+please+retry#addsite")])
                return
            # Enforce the plan's site limit (Free 1, Starter 2, Pro 10, etc.).
            allowed, limit, current = db.can_add_site(uid)
            if not allowed:
                msg = (f"Your plan includes {limit} site{'s' if limit != 1 else ''} and you've "
                       f"connected {current}. Upgrade your plan to add more sites.")
                await _send_html(send, 302, "", [(b"location",
                    ("/dashboard?err=" + urllib.parse.quote(msg) + "#plan").encode())])
                return
            ok, info = _validate_wp(f.get("site_url", ""), f.get("wp_username", ""),
                                    f.get("app_password", ""))
            if not ok:
                loc = "/dashboard?err=" + urllib.parse.quote(str(info))
                await _send_html(send, 302, "", [(b"location", loc.encode())])
                return
            # Atomic limit re-check inside add_site closes the concurrent-connect race.
            _sid = db.add_site(uid, f.get("site_url", ""), f.get("wp_username", ""),
                               f.get("app_password", ""), max_sites=limit)
            if not _sid:
                await _send_html(send, 302, "", [(b"location",
                    ("/dashboard?err=" + urllib.parse.quote("Site limit reached.") + "#plan").encode())])
                return
            _notify_site_connected(uid, f.get("site_url", ""))
            await _send_html(send, 302, "", [(b"location", b"/dashboard?added=1")])
            return
        if path == "/sites/delete" and method == "POST":
            uid = _get_active_uid(headers)
            if not uid:
                await _send_html(send, 302, "", [(b"location", b"/login")])
                return
            f = _form(await _read_body(receive))
            if not _csrf_ok(headers, f):
                await _send_html(send, 302, "", [(b"location", b"/dashboard?err=Session+expired,+please+retry#sites")])
                return
            sid = f.get("site_id", "")
            if sid:
                db.delete_site(uid, sid)  # delete_site already scopes to this user's id
            await _send_html(send, 302, "", [(b"location", b"/dashboard?removed=1#sites")])
            return

        # ----- Conversation history API -----
        if path == "/api/conversations" and method == "GET":
            uid = _get_active_uid(headers)
            if not uid:
                await _send_json(send, 401, {"error": "not logged in"})
                return
            await _send_json(send, 200, {"conversations": db.list_conversations(uid)})
            return
        if path == "/api/conversations" and method == "POST":
            uid = _get_active_uid(headers)
            if not uid:
                await _send_json(send, 401, {"error": "not logged in"})
                return
            cid = db.create_conversation(uid)
            await _send_json(send, 200, {"id": cid, "title": "New chat"})
            return
        if path.startswith("/api/conversations/") and method == "GET":
            uid = _get_active_uid(headers)
            if not uid:
                await _send_json(send, 401, {"error": "not logged in"})
                return
            cid = _safe_uuid(path.rsplit("/", 1)[-1])
            conv = db.get_conversation(uid, cid) if cid else None
            if not conv:
                await _send_json(send, 404, {"error": "not found"})
                return
            await _send_json(send, 200, conv)
            return
        if path.startswith("/api/conversations/") and method == "POST":
            # rename: {title}
            uid = _get_active_uid(headers)
            if not uid:
                await _send_json(send, 401, {"error": "not logged in"})
                return
            cid = _safe_uuid(path.rsplit("/", 1)[-1])
            b = _json_body(await _read_body(receive))
            if cid:
                db.rename_conversation(uid, cid, b.get("title", "Chat"))
            await _send_json(send, 200, {"ok": True})
            return
        if path.startswith("/api/conversations/") and method == "DELETE":
            uid = _get_active_uid(headers)
            if not uid:
                await _send_json(send, 401, {"error": "not logged in"})
                return
            cid = _safe_uuid(path.rsplit("/", 1)[-1])
            if cid:
                db.delete_conversation(uid, cid)
            await _send_json(send, 200, {"ok": True})
            return
        if path == "/api/sites" and method == "GET":
            uid = _get_active_uid(headers)
            if not uid:
                await _send_json(send, 401, {"error": "not logged in"})
                return
            await _send_json(send, 200, {"sites": db.list_user_sites(uid)})
            return
        if path == "/api/token-balance" and method == "GET":
            uid = _get_active_uid(headers)
            if not uid:
                await _send_json(send, 401, {"error": "not logged in"})
                return
            ta = db.get_token_account(uid)
            await _send_json(send, 200, {"credits": (ta or {}).get("credits", 0)})
            return

        # ----- Dashboard live-data (paired with Claude's actions) -----
        if path == "/api/activity" and method == "GET":
            uid = _get_active_uid(headers)
            if not uid:
                await _send_json(send, 401, {"error": "not logged in"})
                return
            ok, data = _studio_fetch(uid, "activity")
            await _send_json(send, 200 if ok else 200, data)
            return
        if path == "/api/backups" and method == "GET":
            uid = _get_active_uid(headers)
            if not uid:
                await _send_json(send, 401, {"error": "not logged in"})
                return
            ok, data = _studio_fetch(uid, "backups")
            await _send_json(send, 200, data)
            return
        if path == "/api/site-health" and method == "GET":
            uid = _get_active_uid(headers)
            if not uid:
                await _send_json(send, 401, {"error": "not logged in"})
                return
            ok, data = _studio_fetch(uid, "health")
            # also report whether Studio itself is reachable (connection bar)
            ok2, info = _studio_fetch(uid, "info")
            data["studio_active"] = bool(ok2 and isinstance(info, dict)
                                         and info.get("plugin") == "wp-pilot-studio")
            await _send_json(send, 200, data)
            return
        if path == "/api/ai-seo-score" and method == "GET":
            uid = _get_active_uid(headers)
            if not uid:
                await _send_json(send, 401, {"error": "not logged in"})
                return
            site = db.get_primary_site(uid)
            if not site:
                await _send_json(send, 200, {"error": "no site connected"})
                return
            try:
                tcfg = server.make_tenant_config(
                    site["site_url"], site["wp_username"], site["app_password"], user_id=uid)
                server.current_tenant.set(tcfg)
                result = json.loads(server.ai_seo_score(limit=50))
                # Save a snapshot so the weekly report card can show before -> after.
                if "ai_seo_score" in result:
                    try:
                        db.save_score_snapshot(uid, result["ai_seo_score"],
                                               result.get("categories", {}), result.get("issues", {}))
                    except Exception:
                        pass
            except Exception as e:  # noqa: BLE001
                result = {"error": str(e)[:120]}
            finally:
                server.current_tenant.set(None)
            await _send_json(send, 200, result)
            return
        if path == "/api/report" and method == "GET":
            uid = _get_active_uid(headers)
            if not uid:
                await _send_json(send, 401, {"error": "not logged in"})
                return
            latest = db.get_latest_snapshot(uid)
            before = db.get_snapshot_before(uid, days=7)
            # Aggregate what changed from the site activity log (best-effort).
            ok, act = _studio_fetch(uid, "activity")
            events = (act or {}).get("log", []) if ok else []
            await _send_json(send, 200, {
                "latest": latest, "before": before,
                "activity_count": len(events),
                "recent_activity": events[:20],
            })
            return
        if path == "/api/approvals" and method == "GET":
            uid = _get_active_uid(headers)
            if not uid:
                await _send_json(send, 401, {"error": "not logged in"})
                return
            await _send_json(send, 200, {"pending": db.list_pending_actions(uid, "pending")})
            return
        if path == "/api/approvals/decide" and method == "POST":
            uid = _get_active_uid(headers)
            if not uid:
                await _send_json(send, 401, {"error": "not logged in"})
                return
            body = _json_body(await _read_body(receive))
            action_id = _safe_uuid(body.get("id", ""))
            decision = body.get("decision", "")  # 'approved' | 'rejected'
            if not action_id:
                await _send_json(send, 400, {"error": "invalid action id"})
                return
            if decision not in ("approved", "rejected"):
                await _send_json(send, 400, {"error": "decision must be approved or rejected"})
                return
            note = ("Approved by user - you may now perform this action."
                    if decision == "approved" else "Rejected by user - do not perform this action.")
            ok = db.decide_pending_action(uid, action_id, decision, note)
            await _send_json(send, 200, {"ok": ok, "decision": decision})
            return

        # ----- Built-in AI chat -----
        if path == "/chat" and method == "POST":
            uid = _get_active_uid(headers)
            if not uid:
                await _send_json(send, 401, {"error": "not logged in"})
                return
            if not chat_mod.ANTHROPIC_API_KEY:
                await _send_json(send, 503, {"error": "Chat is not enabled yet."})
                return

            body = _json_body(await _read_body(receive))
            msgs = body.get("messages", [])
            site_id = body.get("site_id", "")
            conv_id = _safe_uuid(body.get("conv_id", "")) or ""
            if not msgs:
                await _send_json(send, 400, {"error": "no messages"})
                return

            # Pick the requested site, else the primary one.
            site = db.get_site_by_id(uid, site_id) if site_id else None
            if not site:
                site = db.get_primary_site(uid)
            if not site:
                await _send_json(send, 400, {"error": "Connect a WordPress site first."})
                return

            tok_acct = db.get_token_account(uid)
            if not tok_acct or tok_acct["tokens"] <= 0:
                await _send_json(send, 402, {
                    "error": "out_of_credits",
                    "message": "You're out of AI credits this month. Buy more or upgrade."})
                return

            # Save the user message + auto-title the conversation from it.
            if conv_id:
                last_user = next((m["content"] for m in reversed(msgs) if m.get("role") == "user"), "")
                if last_user:
                    db.add_message(uid, conv_id, "user", last_user)
                    conv = db.get_conversation(uid, conv_id)
                    if conv and conv["title"] == "New chat":
                        db.rename_conversation(uid, conv_id, last_user[:60])

            own_key = db.get_user_gemini_key(uid) or ""
            tcfg = server.make_tenant_config(
                site["site_url"], site["wp_username"], site["app_password"],
                gemini_api_key=own_key, user_id=uid,
                credit_hook=(lambda u=uid: db.try_consume_credit(u)),
                credit_refund_hook=(lambda u=uid: db.refund_credit(u, 1)),
                approval_hook=(lambda tool, args, summary, risk, u=uid:
                               db.create_pending_action(u, tool, args, summary, risk)),
                approval_status_hook=(lambda aid, u=uid:
                                      (db.get_pending_action(u, aid) or {"status": "unknown"})))
            server.current_tenant.set(tcfg)

            try:
                reply, used, stopped, _convo = chat_mod.run_chat(
                    msgs, model=tok_acct.get("model"), budget_tokens=tok_acct["tokens"])
            except Exception as e:  # noqa: BLE001
                await _send_json(send, 500, {"error": f"chat failed: {type(e).__name__}: {e}"[:200]})
                return

            if conv_id and reply:
                db.add_message(uid, conv_id, "assistant", reply)

            remaining = db.consume_tokens(uid, used)
            await _send_json(send, 200, {
                "reply": reply,
                "tokens_used": used,
                "credits_left": remaining // db.TOKENS_PER_CREDIT,
                "stopped_early": stopped,
                "active_site": site["site_url"],
            })
            return

        # ----- Streaming chat (live tool progress, Claude-style) -----
        if path == "/chat/stream" and method == "POST":
            uid = _get_active_uid(headers)
            if not uid:
                await _send_json(send, 401, {"error": "not logged in"})
                return
            if not chat_mod.ANTHROPIC_API_KEY:
                await _send_json(send, 503, {"error": "Chat is not enabled yet."})
                return
            body = _json_body(await _read_body(receive))
            msgs = body.get("messages", [])
            site_id = body.get("site_id", "")
            conv_id = _safe_uuid(body.get("conv_id", "")) or ""
            if not msgs:
                await _send_json(send, 400, {"error": "no messages"})
                return
            site = db.get_site_by_id(uid, site_id) if site_id else None
            if not site:
                site = db.get_primary_site(uid)
            if not site:
                await _send_json(send, 400, {"error": "Connect a WordPress site first."})
                return
            tok_acct = db.get_token_account(uid)
            if not tok_acct or tok_acct["tokens"] <= 0:
                await _send_json(send, 402, {"error": "out_of_credits",
                    "message": "You're out of AI credits this month. Buy more or upgrade."})
                return
            if conv_id:
                last_user = next((m["content"] for m in reversed(msgs) if m.get("role") == "user"), "")
                if last_user:
                    db.add_message(uid, conv_id, "user", last_user)
                    conv = db.get_conversation(uid, conv_id)
                    if conv and conv["title"] == "New chat":
                        db.rename_conversation(uid, conv_id, last_user[:60])
            own_key = db.get_user_gemini_key(uid) or ""
            tcfg = server.make_tenant_config(
                site["site_url"], site["wp_username"], site["app_password"],
                gemini_api_key=own_key, user_id=uid,
                credit_hook=(lambda u=uid: db.try_consume_credit(u)),
                credit_refund_hook=(lambda u=uid: db.refund_credit(u, 1)),
                approval_hook=(lambda tool, args, summary, risk, u=uid:
                               db.create_pending_action(u, tool, args, summary, risk)),
                approval_status_hook=(lambda aid, u=uid:
                                      (db.get_pending_action(u, aid) or {"status": "unknown"})))
            server.current_tenant.set(tcfg)

            # Start SSE response.
            await send({"type": "http.response.start", "status": 200, "headers": [
                (b"content-type", b"text/event-stream"),
                (b"cache-control", b"no-cache"),
                (b"x-accel-buffering", b"no")]})

            async def _emit(obj):
                await send({"type": "http.response.body",
                            "body": ("data: " + json.dumps(obj) + "\n\n").encode(),
                            "more_body": True})

            final_reply, final_tokens, final_stopped = "", 0, False
            try:
                for ev in chat_mod.run_chat_stream(
                        msgs, model=tok_acct.get("model"), budget_tokens=tok_acct["tokens"]):
                    if ev.get("type") == "done":
                        final_reply = ev.get("reply", "")
                        final_tokens = ev.get("tokens_used", 0)
                        final_stopped = ev.get("stopped_early", False)
                    else:
                        await _emit(ev)
            except Exception as e:  # noqa: BLE001
                await _emit({"type": "error", "message": f"{type(e).__name__}: {e}"[:150]})

            if conv_id and final_reply:
                db.add_message(uid, conv_id, "assistant", final_reply)
            remaining = db.consume_tokens(uid, final_tokens)
            await _emit({"type": "done", "reply": final_reply,
                         "credits_left": remaining // db.TOKENS_PER_CREDIT,
                         "stopped_early": final_stopped, "active_site": site["site_url"]})
            await send({"type": "http.response.body", "body": b"", "more_body": False})
            return

    # ===== OAuth endpoints =====
    if _oauth:
        if path.startswith("/.well-known/oauth-protected-resource"):
            await _send_json(send, 200, _oauth.protected_resource_metadata())
            return
        if path.startswith("/.well-known/oauth-authorization-server") or \
           path == "/.well-known/openid-configuration":
            await _send_json(send, 200, _oauth.authorization_server_metadata())
            return
        if path == "/register" and method == "POST":
            status, hdrs, body = _oauth.handle_register(await _read_body(receive))
            await _raw_send(send, status, hdrs, body)
            return
        if path == "/authorize":
            q = scope.get("query_string", b"").decode()
            # Reject an untrusted redirect_uri up front - never even show the login page for
            # a phishing redirect target (defense in depth on top of handle_authorize).
            _ruri = (urllib.parse.parse_qs(q).get("redirect_uri") or [""])[0]
            if _ruri and _oauth and not _oauth._redirect_allowed(_ruri):
                await _send_json(send, 400, {"error": "invalid_request",
                                             "error_description": "redirect_uri not allowed"})
                return
            # tenant must be logged in (multi-tenant). Standalone: empty tid is fine.
            tid = ""
            if MULTI_TENANT:
                tid = _get_session_uid(headers) or ""
                if not tid:
                    # not logged in -> show login page, preserving the authorize query
                    nxt = urllib.parse.quote("/authorize?" + q)
                    await _send_html(send, 200, pages.login_page(authorize_next=nxt))
                    return
            status, hdrs, body = _oauth.handle_authorize(q, tid)
            await _raw_send(send, status, hdrs, body)
            return
        if path == "/token" and method == "POST":
            ct = headers.get(b"content-type", b"").decode()
            raw_body = await _read_body(receive)
            # Single-use authorization codes: an auth code (grant_type=authorization_code)
            # may be redeemed only ONCE. We key on the code's signature; the first redeem
            # claims it, replays are rejected. (Refresh-token grants are unaffected.)
            code_key = ""
            try:
                if b"authorization_code" in raw_body:
                    parsed = urllib.parse.parse_qs(raw_body.decode("utf-8", "replace"))
                    code_val = (parsed.get("code") or [""])[0]
                    if not code_val and b"json" in ct.encode():
                        code_val = (json.loads(raw_body or b"{}") or {}).get("code", "")
                    if code_val and "." in code_val:
                        code_key = "oauthcode:" + code_val.rsplit(".", 1)[1][:40]
            except Exception:
                code_key = ""
            if code_key and db is not None:
                try:
                    if not db.mark_event_processed(code_key):
                        await _send_json(send, 400, {"error": "invalid_grant",
                                                     "error_description": "authorization code already used"})
                        return
                except Exception:
                    pass  # DB hiccup -> fall through (PKCE + expiry still protect)
            status, hdrs, body = _oauth.handle_token(raw_body, ct)
            await _raw_send(send, status, hdrs, body)
            return

    # Browser hitting an unknown URL (no Bearer, wants HTML) -> friendly 404, not the
    # MCP 401 JSON. The MCP endpoints live under /mcp; everything else that reached here
    # unmatched is a broken link.
    _auth_hdr = headers.get(b"authorization", b"").decode()
    _accept = headers.get(b"accept", b"").decode().lower()
    if (method == "GET" and not _auth_hdr.startswith("Bearer ")
            and not path.startswith("/mcp") and "text/html" in _accept):
        await _send_html(send, 404, pages.message_page(
            "Page not found",
            "The page you're looking for doesn't exist or has moved.",
            "/", "Go to homepage"))
        return

    # ===== MCP auth gate + tenant resolution =====
    auth = headers.get(b"authorization", b"").decode()
    bearer = auth[7:].strip() if auth.startswith("Bearer ") else ""
    tenant_cfg = None

    if _oauth and bearer:
        payload = _oauth.verify_token(bearer)
        if payload:
            tid = payload.get("tid", "")
            if MULTI_TENANT:
                if tid and db.is_banned(tid):
                    # suspended account -> deny all AI/MCP access (fail closed)
                    tid = ""
                if tid:
                    site = db.get_primary_site(tid)
                    if site:
                        # BYOK Gemini key (if set) overrides the platform key
                        own_key = db.get_user_gemini_key(tid) or ""
                        _plan = ""
                        try:
                            _acct = db.get_account(tid)
                            _plan = (_acct or {}).get("plan", "") or ""
                        except Exception:
                            _plan = ""
                        tenant_cfg = server.make_tenant_config(
                            site["site_url"], site["wp_username"], site["app_password"],
                            gemini_api_key=own_key, user_id=tid, plan=_plan,
                            credit_hook=(lambda uid=tid: db.try_consume_credit(uid)),
                            credit_refund_hook=(lambda uid=tid: db.refund_credit(uid, 1)),
                            toolcall_hook=(lambda uid=tid: db.try_consume_toolcall(uid)),
                            toolcall_refund_hook=(lambda uid=tid: db.refund_toolcall(uid)),
                            balance_hook=(lambda uid=tid: db.get_balances(uid)),
                            approval_hook=(lambda tool, args, summary, risk, uid=tid:
                                           db.create_pending_action(uid, tool, args, summary, risk)),
                            approval_status_hook=(lambda aid, uid=tid:
                                                  (db.get_pending_action(uid, aid) or {"status": "unknown"})))
                    else:
                        # Valid account but NO WordPress site connected yet. Don't 401
                        # (that shows Claude a scary "Authorization failed" error and
                        # the user thinks their credentials are wrong). Instead bind a
                        # "no-site" context so the connection succeeds, and each tool
                        # returns a clear "add your site first" message.
                        tenant_cfg = {"no_site": True, "user_id": tid}
                # tid missing (banned) -> tenant_cfg stays None -> fail closed below
            else:
                # standalone: token valid -> use the default env site
                tenant_cfg = server._DEFAULT_TENANT

    # Standalone with no OAuth at all = dev mode allow
    if not MULTI_TENANT and not _oauth:
        tenant_cfg = server._DEFAULT_TENANT

    if tenant_cfg is None:
        rm = (PUBLIC_URL + "/.well-known/oauth-protected-resource") if PUBLIC_URL else ""
        await send({"type": "http.response.start", "status": 401, "headers": [
            (b"content-type", b"application/json"),
            (b"www-authenticate", f'Bearer resource_metadata="{rm}"'.encode())]})
        await send({"type": "http.response.body", "body": b'{"error":"unauthorized"}'})
        return

    # Bind tenant config for the duration of this request
    server.current_tenant.set(tenant_cfg)

    # rewrite Host so Starlette host-validation passes behind proxies
    new_headers = [
        (k, b"127.0.0.1:" + _PORT_BYTES) if k.lower() == b"host" else (k, v)
        for (k, v) in scope.get("headers", [])
    ]
    scope = dict(scope)
    scope["headers"] = new_headers
    await _inner(scope, receive, send)


uvicorn.run(
    asgi_app,
    host="0.0.0.0",
    port=int(os.environ["PORT"]),
    forwarded_allow_ips="*",
    proxy_headers=True,
)
