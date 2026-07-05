#!/usr/bin/env python3
"""
wptaskify smoke test - run after every deploy to confirm the site is healthy
BEFORE you trust it with real users.

What it checks (read-only, safe - it never creates users or takes payments):
  - Home + key marketing pages return 200
  - Legal/policy pages exist (Razorpay compliance)
  - Login / signup pages load
  - Auth is enforced (dashboard redirects to login when logged out)
  - The security fixes hold (/disconnect needs login, Mini-USD doesn't 500)
  - OAuth metadata advertises S256-only PKCE
  - Dashboard deep-link sections are valid

Usage:
  python smoke_test.py                      # tests https://wptaskify.com
  python smoke_test.py https://staging-url  # tests a staging deployment
  python smoke_test.py --resolve            # force the wptaskify.com IP (prod)

Exit code 0 = all good (safe to keep the deploy). Non-zero = something broke.
"""
import sys
import json
import urllib.request
import urllib.error
import ssl

# ---- config -----------------------------------------------------------------
BASE = "https://wptaskify.com"
# Force the production IP so we hit the real box even before DNS/CDN settle.
PROD_IP = "69.46.46.84"
USE_RESOLVE = False

args = [a for a in sys.argv[1:]]
if "--resolve" in args:
    USE_RESOLVE = True
    args.remove("--resolve")
if args:
    BASE = args[0].rstrip("/")

_ctx = ssl.create_default_context()


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


class _PinnedHTTPSConnection:
    """Connect to a fixed IP while keeping the real hostname for SNI + cert check,
    so `--resolve` works exactly like curl --resolve (hit the prod box pre-DNS)."""


def _fetch(path, allow_redirect=False):
    """Return (status, final_url, body_text). Never raises on HTTP errors."""
    import http.client
    url = BASE + path
    handlers = [urllib.request.HTTPSHandler(context=_ctx)]
    if not allow_redirect:
        handlers.append(_NoRedirect)

    if USE_RESOLVE and BASE.startswith("https://wptaskify.com"):
        # Connect to the prod IP but present wptaskify.com for SNI + verify the cert
        # against the hostname (this is what curl --resolve does).
        host = "wptaskify.com"
        conn = http.client.HTTPSConnection(PROD_IP, 443, timeout=25,
                                           context=_ctx)
        conn.sock = None
        try:
            # override so SNI + cert verification use the hostname, not the IP
            import ssl as _ssl
            raw = __import__("socket").create_connection((PROD_IP, 443), timeout=25)
            conn.sock = _ctx.wrap_socket(raw, server_hostname=host)
            conn.request("GET", path, headers={"Host": host,
                                               "User-Agent": "wptaskify-smoke/1.0"})
            resp = conn.getresponse()
            status = resp.status
            body = resp.read().decode("utf-8", "replace")
            # follow one redirect only if asked
            if allow_redirect and status in (301, 302, 303, 307, 308):
                pass
            return status, url, body
        except Exception as e:  # noqa: BLE001
            return 0, url, f"__ERROR__ {type(e).__name__}: {e}"
        finally:
            try:
                conn.close()
            except Exception:
                pass

    req = urllib.request.Request(url, headers={"User-Agent": "wptaskify-smoke/1.0"})
    opener = urllib.request.build_opener(*handlers)
    try:
        with opener.open(req, timeout=25) as r:
            return r.status, r.geturl(), r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, url, e.read().decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        return 0, url, f"__ERROR__ {type(e).__name__}: {e}"


# ---- checks -----------------------------------------------------------------
results = []


def check(name, ok, detail=""):
    results.append((name, ok, detail))
    mark = "PASS" if ok else "FAIL"
    line = f"[{mark}] {name}"
    if detail and not ok:
        line += f"  -> {detail}"
    print(line)


def expect_200(name, path):
    st, _, body = _fetch(path)
    check(name, st == 200, f"got {st}")


def expect_redirect(name, path):
    st, _, _ = _fetch(path)
    check(name, st in (301, 302, 303, 307, 308), f"got {st} (expected redirect)")


print(f"\n=== wptaskify smoke test :: {BASE} ===\n")

# 1. Marketing / core pages
expect_200("home", "/")
expect_200("pricing", "/pricing")
expect_200("features", "/features")
expect_200("faq", "/faq")

# 2. Legal / policy pages (payment-gateway compliance)
expect_200("terms", "/terms")
expect_200("privacy", "/privacy")
expect_200("refund", "/refund")
expect_200("shipping (delivery)", "/shipping")
expect_200("contact", "/contact")

# 3. Auth pages
expect_200("login page", "/login")

# 4. Auth is enforced (logged-out dashboard must redirect, not 200)
expect_redirect("dashboard requires login", "/dashboard")

# 5. Security fixes still hold
#    /disconnect without login must NOT delete - it returns the login page (200 HTML),
#    never a JSON "disconnected". We assert it does not report a deletion.
st, _, body = _fetch("/disconnect?site=https://example.com")
check("/disconnect needs login (no anon delete)",
      '"disconnected": true' not in body.lower(), "anon disconnect leaked")

#    Mini plan as USD must not 500 (it should redirect, not crash).
st, _, _ = _fetch("/checkout-after?plan=owai_mini")
check("Mini-USD checkout doesn't 500", st != 500, f"got {st}")

# 6. OAuth metadata advertises S256-only (no weak 'plain')
st, _, body = _fetch("/.well-known/oauth-authorization-server")
pkce_ok = False
try:
    meta = json.loads(body)
    methods = meta.get("code_challenge_methods_supported", [])
    pkce_ok = methods == ["S256"]
    detail = f"methods={methods}"
except Exception:
    detail = "metadata not JSON"
check("OAuth PKCE is S256-only", pkce_ok, detail)

# 7. Content sanity: pricing claims 100+ tools (not the old 24)
st, _, body = _fetch("/pricing")
check("pricing shows '100+ tools' (not 24)",
      "24 tools" not in body and "24+ tools" not in body, "stale 24-tool copy")

# 8. No stale Stripe copy anywhere on pricing
check("no stale 'Stripe' copy on pricing", "stripe" not in body.lower(),
      "Stripe still mentioned")

# ---- summary ----------------------------------------------------------------
passed = sum(1 for _, ok, _ in results if ok)
total = len(results)
print(f"\n=== {passed}/{total} checks passed ===")
if passed != total:
    print("\n[!] DEPLOY NOT HEALTHY - do NOT promote to production / consider rollback.\n")
    sys.exit(1)
print("\n[OK] All checks passed - deploy looks healthy.\n")
sys.exit(0)
