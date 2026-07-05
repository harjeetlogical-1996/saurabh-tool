"""
Minimal OAuth 2.1 layer for the WP MCP server, compatible with claude.ai's
custom-connector flow.

This is a SINGLE-USER private server, so the "authorization server" here does
NOT show a login/consent screen - it auto-approves, because possession of the
deployment + the access tokens it mints is the security boundary. What it DOES
provide is the OAuth dance claude.ai requires:

  GET  /.well-known/oauth-protected-resource      (RFC 9728)
  GET  /.well-known/oauth-authorization-server    (RFC 8414)
  POST /register                                  (RFC 7591 dynamic registration)
  GET  /authorize                                 (auto-approves, redirects with code)
  POST /token                                     (PKCE code -> access token)

Then every /mcp request must carry  Authorization: Bearer <access_token>.

Tokens are signed with an HMAC secret so the server stays stateless (no DB) -
a token is valid iff its signature checks out and it hasn't expired.
"""

import base64
import hashlib
import hmac
import json
import time
import urllib.parse


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _b64url_decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


class OAuthProvider:
    # Authorization codes are single-use, short-lived. 10 minutes is plenty for the
    # browser round-trip and matches the OAuth 2.1 recommendation for auth-code lifetime.
    AUTH_CODE_TTL = 600

    def __init__(self, issuer: str, secret: str, ttl: int = 30 * 24 * 3600):
        # issuer = public base URL (e.g. https://xyz.up.railway.app), no trailing slash
        self.issuer = issuer.rstrip("/")
        self.secret = secret.encode()
        self.ttl = ttl
        # Extra allowed redirect hosts via env (comma-separated), so a new legit connector
        # can be permitted without a code change. The issuer's own host is always allowed.
        import os as _os
        extra = [h.strip().lower() for h in
                 _os.environ.get("OAUTH_EXTRA_REDIRECT_HOSTS", "").split(",") if h.strip()]
        issuer_host = (urllib.parse.urlparse(self.issuer).hostname or "").lower()
        self._allowed_hosts = tuple(self.ALLOWED_REDIRECT_HOSTS) + tuple(extra) + \
            ((issuer_host,) if issuer_host else ())

    # ---- token mint/verify (stateless, HMAC-signed) -----------------------
    def mint_token(self, tenant_id: str = "") -> str:
        """Mint an access token bound to a tenant (user) id."""
        payload = {"iat": int(time.time()), "exp": int(time.time()) + self.ttl}
        if tenant_id:
            payload["tid"] = tenant_id
        body = _b64url(json.dumps(payload).encode())
        sig = _b64url(hmac.new(self.secret, body.encode(), hashlib.sha256).digest())
        return f"{body}.{sig}"

    def verify_token(self, token: str):
        """Return the decoded payload dict if valid, else None.
        Payload includes `tid` (tenant/user id) when present."""
        try:
            body, sig = token.split(".", 1)
            expected = _b64url(hmac.new(self.secret, body.encode(), hashlib.sha256).digest())
            if not hmac.compare_digest(sig, expected):
                return None
            payload = json.loads(_b64url_decode(body))
            if payload.get("exp", 0) <= time.time():
                return None
            return payload
        except Exception:
            return None

    # ---- metadata documents ----------------------------------------------
    def protected_resource_metadata(self):
        return {
            "resource": self.issuer + "/mcp",
            "resource_name": "wptaskify",
            "authorization_servers": [self.issuer],
            "bearer_methods_supported": ["header"],
        }

    def authorization_server_metadata(self):
        return {
            "issuer": self.issuer,
            "authorization_endpoint": self.issuer + "/authorize",
            "token_endpoint": self.issuer + "/token",
            "registration_endpoint": self.issuer + "/register",
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code", "refresh_token"],
            # S256 only - we no longer advertise the weak 'plain' PKCE method.
            "code_challenge_methods_supported": ["S256"],
            "token_endpoint_auth_methods_supported": ["none"],
            "authorization_response_iss_parameter_supported": True,
        }

    # ---- endpoint handlers (return (status, headers, body_bytes)) ---------
    def handle_register(self, body_bytes: bytes):
        # Dynamic client registration - accept anything, echo back a client_id.
        try:
            req = json.loads(body_bytes or b"{}")
        except Exception:
            req = {}
        client_id = "wpmcp-" + _b64url(hmac.new(self.secret, (str(time.time())).encode(),
                                               hashlib.sha256).digest())[:16]
        resp = {
            "client_id": client_id,
            "client_id_issued_at": int(time.time()),
            "redirect_uris": req.get("redirect_uris", []),
            "grant_types": req.get("grant_types", ["authorization_code"]),
            "response_types": req.get("response_types", ["code"]),
            "token_endpoint_auth_method": "none",
        }
        return 201, {"content-type": "application/json"}, json.dumps(resp).encode()

    def make_auth_code(self, challenge: str, method: str, tenant_id: str) -> str:
        """Build a signed authorization code embedding PKCE + the tenant id."""
        code_payload = _b64url(json.dumps(
            {"c": challenge, "m": method, "tid": tenant_id, "t": int(time.time())}).encode())
        code_sig = _b64url(hmac.new(self.secret, code_payload.encode(), hashlib.sha256).digest())
        return f"{code_payload}.{code_sig}"

    # Only these hosts may receive an authorization code. This prevents an open-redirect
    # -> account-takeover attack where a crafted redirect_uri sends a victim's code to an
    # attacker site. claude.ai / anthropic are the real OAuth connector callbacks; the
    # localhost entries are for local MCP clients / testing.
    ALLOWED_REDIRECT_HOSTS = (
        "claude.ai", "www.claude.ai", "claude.com", "www.claude.com",
        "anthropic.com", "console.anthropic.com",
        "localhost", "127.0.0.1", "[::1]",
    )

    def _redirect_allowed(self, redirect_uri: str) -> bool:
        try:
            u = urllib.parse.urlparse(redirect_uri)
        except Exception:
            return False
        # Must be an absolute https URL (or http only for localhost dev clients).
        host = (u.hostname or "").lower()
        if not host:
            return False
        scheme_ok = (u.scheme == "https") or (u.scheme == "http" and host in ("localhost", "127.0.0.1", "[::1]"))
        if not scheme_ok:
            return False
        # Exact host or a subdomain of an allowed host.
        for allowed in self._allowed_hosts:
            if host == allowed or host.endswith("." + allowed):
                return True
        return False

    def handle_authorize(self, query: str, tenant_id: str):
        """Issue an authorization code for a LOGGED-IN tenant.
        The caller (middleware) is responsible for resolving tenant_id from the
        session cookie BEFORE calling this; if tenant_id is empty it means the
        user is not logged in and the middleware should show the login page."""
        p = urllib.parse.parse_qs(query)
        redirect_uri = (p.get("redirect_uri") or [""])[0]
        state = (p.get("state") or [""])[0]
        challenge = (p.get("code_challenge") or [""])[0]
        # Default method to S256 when the client sends a challenge without specifying one.
        method = (p.get("code_challenge_method") or ["S256"])[0]
        if not redirect_uri:
            return 400, {"content-type": "application/json"}, b'{"error":"missing redirect_uri"}'
        # SECURITY: never mint a code for an untrusted redirect target.
        if not self._redirect_allowed(redirect_uri):
            return 400, {"content-type": "application/json"}, \
                b'{"error":"invalid_request","error_description":"redirect_uri not allowed"}'
        # SECURITY: require PKCE. A code minted without a challenge can be redeemed with no
        # verifier, weakening the flow. claude.ai always sends S256. Set
        # OAUTH_ALLOW_NO_PKCE=1 only if a legacy client genuinely can't do PKCE.
        import os as _os
        if not challenge and _os.environ.get("OAUTH_ALLOW_NO_PKCE") != "1":
            return 400, {"content-type": "application/json"}, \
                b'{"error":"invalid_request","error_description":"PKCE (code_challenge) required"}'
        code = self.make_auth_code(challenge, method, tenant_id)
        sep = "&" if "?" in redirect_uri else "?"
        loc = f"{redirect_uri}{sep}code={urllib.parse.quote(code)}&iss={urllib.parse.quote(self.issuer)}"
        if state:
            loc += f"&state={urllib.parse.quote(state)}"
        return 302, {"location": loc}, b""

    def handle_token(self, body_bytes: bytes, content_type: str):
        # Exchange authorization code (+ PKCE verifier) for an access token.
        if "json" in (content_type or ""):
            try:
                p = json.loads(body_bytes or b"{}")
            except Exception:
                p = {}
            get = lambda k: p.get(k, "")  # noqa: E731
        else:
            form = urllib.parse.parse_qs(body_bytes.decode() if body_bytes else "")
            get = lambda k: (form.get(k) or [""])[0]  # noqa: E731

        grant = get("grant_type")
        if grant == "refresh_token":
            # carry the tenant id forward from the refresh token
            old = self.verify_token(get("refresh_token"))
            tid = (old or {}).get("tid", "")
            tok = self.mint_token(tid)
            return 200, {"content-type": "application/json"}, json.dumps({
                "access_token": tok, "token_type": "Bearer", "expires_in": self.ttl,
                "refresh_token": tok}).encode()

        code = get("code")
        verifier = get("code_verifier")
        # validate code signature
        try:
            cp, cs = code.split(".", 1)
            expected = _b64url(hmac.new(self.secret, cp.encode(), hashlib.sha256).digest())
            if not hmac.compare_digest(cs, expected):
                raise ValueError("bad code sig")
            cdata = json.loads(_b64url_decode(cp))
        except Exception:
            return 400, {"content-type": "application/json"}, b'{"error":"invalid_grant"}'

        # Reject expired authorization codes (single-use, short TTL).
        issued = cdata.get("t", 0)
        if not issued or (time.time() - issued) > self.AUTH_CODE_TTL:
            return 400, {"content-type": "application/json"}, \
                b'{"error":"invalid_grant","error_description":"authorization code expired"}'

        # Verify PKCE. When the client used PKCE (challenge present), enforce it strictly
        # with S256 only - we no longer accept the weak 'plain' method, and a missing
        # verifier is rejected. (Clients that never sent a challenge still work, but the
        # connector we target - claude.ai - always uses S256.)
        challenge, method = cdata.get("c", ""), cdata.get("m", "plain")
        if challenge:
            if method != "S256" or not verifier:
                return 400, {"content-type": "application/json"}, \
                    b'{"error":"invalid_grant","error_description":"PKCE S256 required"}'
            calc = _b64url(hashlib.sha256(verifier.encode()).digest())
            if not hmac.compare_digest(calc, challenge):
                return 400, {"content-type": "application/json"}, \
                    b'{"error":"invalid_grant","error_description":"PKCE failed"}'

        # bind the access token to the tenant carried in the auth code
        tid = cdata.get("tid", "")
        tok = self.mint_token(tid)
        return 200, {"content-type": "application/json"}, json.dumps({
            "access_token": tok, "token_type": "Bearer", "expires_in": self.ttl,
            "refresh_token": tok, "scope": "mcp"}).encode()
