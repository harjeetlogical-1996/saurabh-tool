"""
Database + encryption layer for the multi-tenant WordPress MCP SaaS.

- Postgres (Railway) via psycopg connection pool.
- Two tables: users, wordpress_sites.
- WordPress Application Passwords are encrypted at rest with AES-256-GCM.
  Master key = ENCRYPTION_KEY env var (base64, 32 bytes). NEVER stored in DB.
- Passwords (login) hashed with argon2id.

All functions are sync (psycopg) - the MCP server is I/O light on DB
(one cached lookup per request), so a simple pooled sync layer is enough.
"""

import os
import re
import json
import base64
import uuid

import psycopg
from psycopg_pool import ConnectionPool
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from argon2 import PasswordHasher

DATABASE_URL = os.environ.get("DATABASE_URL", "")

# Master encryption key (32 raw bytes, provided base64-encoded in env).
_ENC_KEY_B64 = os.environ.get("ENCRYPTION_KEY", "")
_ENC_KEY = base64.b64decode(_ENC_KEY_B64) if _ENC_KEY_B64 else None

_ph = PasswordHasher()
_pool: ConnectionPool | None = None


# ---------------------------------------------------------------------------
# Pool + schema
# ---------------------------------------------------------------------------
def init_pool():
    """Create the connection pool and ensure schema exists. Call once at startup."""
    global _pool
    if not DATABASE_URL:
        raise SystemExit("DATABASE_URL not set (add Postgres on Railway).")
    if _ENC_KEY is None or len(_ENC_KEY) != 32:
        raise SystemExit("ENCRYPTION_KEY must be base64 of exactly 32 bytes.")
    _pool = ConnectionPool(DATABASE_URL, min_size=1, max_size=10, kwargs={"autocommit": True})
    _create_schema()


# Monthly image credits granted per plan (all plan keys).
# Images cost us ~$0.039 each (Gemini). Tuned for ~83-89% margin on paid plans:
#   Starter $20 -> 60 imgs (~$2.3 cost)   Pro $99 -> 200 imgs (~$7.8 cost).
PLAN_CREDITS = {
    "free": 5, "pro": 60, "agency": 250,
    "owai_mini": 25, "owai_starter": 60, "owai_pro": 200,
    "chat_starter": 50, "chat_pro": 150, "chat_max": 250,
}

# Monthly TOOL-CALL limit for "connect your own AI" plans (Claude/ChatGPT
# drive the MCP tools). Each tool call counts against this. These are cheap for
# us (the USER pays for their own AI), so we're generous - it's a value lever.
PLAN_TOOLCALLS = {
    "free": 100,
    "owai_mini": 800,
    "owai_starter": 2000,
    "owai_pro": 1_000_000,   # Pro = effectively unlimited AI actions
    # legacy/back-compat:
    "pro": 2000, "agency": 1_000_000,
    # chat plans: effectively unlimited tool calls (billed via tokens)
    "chat_starter": 1_000_000, "chat_pro": 1_000_000, "chat_max": 1_000_000,
}

# Built-in-chat plans: monthly token allowance + which Claude model runs.
# Shown to users as "AI credits" where 1 credit = 1000 tokens.
#   Chat Starter $30  -> Haiku  5M  (~250 articles, ~75% margin)
#   Chat Pro     $79  -> Sonnet 15M (~750 articles, ~50% margin)
#   Chat Max     $149 -> Opus   8M  (~400 articles, ~60% margin)
# "Connect your own AI" plans (free/pro/agency) get a small chat trial only.
PLAN_TOKENS = {
    "free": 200_000,          # trial
    "pro": 200_000,           # connect-own-AI: small chat trial
    "agency": 500_000,
    "chat_starter": 5_000_000,
    "chat_pro": 15_000_000,
    "chat_max": 8_000_000,
}

# Which Claude model each plan's built-in chat uses.
PLAN_MODEL = {
    "free": "claude-haiku-4-5",
    "pro": "claude-haiku-4-5",
    "agency": "claude-haiku-4-5",
    "chat_starter": "claude-haiku-4-5",
    "chat_pro": "claude-sonnet-4-6",
    "chat_max": "claude-opus-4-8",
}

# Plans where built-in chat is a real (premium) feature, not just a trial.
CHAT_PLANS = {"chat_starter", "chat_pro", "chat_max"}

TOKENS_PER_CREDIT = 1000


def _create_schema():
    with _pool.connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                email         text UNIQUE NOT NULL,
                password_hash text NOT NULL,
                plan          text NOT NULL DEFAULT 'free',
                credits       int  NOT NULL DEFAULT 5,
                credits_month text NOT NULL DEFAULT '',
                gemini_key_enc   bytea,
                gemini_key_nonce bytea,
                email_verified boolean NOT NULL DEFAULT false,
                created_at    timestamptz NOT NULL DEFAULT now()
            );
        """)
        # add columns if upgrading an existing table
        for col, ddl in [
            ("plan", "ALTER TABLE users ADD COLUMN IF NOT EXISTS plan text NOT NULL DEFAULT 'free'"),
            ("credits", "ALTER TABLE users ADD COLUMN IF NOT EXISTS credits int NOT NULL DEFAULT 5"),
            ("credits_month", "ALTER TABLE users ADD COLUMN IF NOT EXISTS credits_month text NOT NULL DEFAULT ''"),
            ("gemini_key_enc", "ALTER TABLE users ADD COLUMN IF NOT EXISTS gemini_key_enc bytea"),
            ("gemini_key_nonce", "ALTER TABLE users ADD COLUMN IF NOT EXISTS gemini_key_nonce bytea"),
            ("email_verified", "ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified boolean NOT NULL DEFAULT false"),
            ("ai_tokens", "ALTER TABLE users ADD COLUMN IF NOT EXISTS ai_tokens bigint NOT NULL DEFAULT 200000"),
            ("ai_tokens_month", "ALTER TABLE users ADD COLUMN IF NOT EXISTS ai_tokens_month text NOT NULL DEFAULT ''"),
            ("tool_calls", "ALTER TABLE users ADD COLUMN IF NOT EXISTS tool_calls int NOT NULL DEFAULT 100"),
            ("tool_calls_month", "ALTER TABLE users ADD COLUMN IF NOT EXISTS tool_calls_month text NOT NULL DEFAULT ''"),
            ("stripe_customer_id", "ALTER TABLE users ADD COLUMN IF NOT EXISTS stripe_customer_id text"),
            ("sub_status", "ALTER TABLE users ADD COLUMN IF NOT EXISTS sub_status text NOT NULL DEFAULT 'none'"),
            ("sub_provider", "ALTER TABLE users ADD COLUMN IF NOT EXISTS sub_provider text"),
            ("sub_id", "ALTER TABLE users ADD COLUMN IF NOT EXISTS sub_id text"),
            ("sub_renews_at", "ALTER TABLE users ADD COLUMN IF NOT EXISTS sub_renews_at timestamptz"),
            ("status", "ALTER TABLE users ADD COLUMN IF NOT EXISTS status text NOT NULL DEFAULT 'active'"),
            ("admin_note", "ALTER TABLE users ADD COLUMN IF NOT EXISTS admin_note text NOT NULL DEFAULT ''"),
            ("banned_at", "ALTER TABLE users ADD COLUMN IF NOT EXISTS banned_at timestamptz"),
            ("name", "ALTER TABLE users ADD COLUMN IF NOT EXISTS name text NOT NULL DEFAULT ''"),
            ("notify_email", "ALTER TABLE users ADD COLUMN IF NOT EXISTS notify_email boolean NOT NULL DEFAULT true"),
            ("low_img_notified", "ALTER TABLE users ADD COLUMN IF NOT EXISTS low_img_notified text NOT NULL DEFAULT ''"),
            ("active_site_id", "ALTER TABLE users ADD COLUMN IF NOT EXISTS active_site_id uuid"),
            ("renew_notified", "ALTER TABLE users ADD COLUMN IF NOT EXISTS renew_notified text NOT NULL DEFAULT ''"),
            # Marks the sub_renews_at value we already sent an "expiring soon" email for, so
            # each expiry period only triggers one reminder (reset when the plan is renewed).
            ("expiry_notified", "ALTER TABLE users ADD COLUMN IF NOT EXISTS expiry_notified timestamptz"),
            ("gstin", "ALTER TABLE users ADD COLUMN IF NOT EXISTS gstin text NOT NULL DEFAULT ''"),
            # Session version: bumped on password change / logout-all / ban so old signed
            # cookies stop working. A session cookie embeds the version it was minted with.
            ("session_ver", "ALTER TABLE users ADD COLUMN IF NOT EXISTS session_ver int NOT NULL DEFAULT 1"),
        ]:
            conn.execute(ddl)
        # Email verify + password reset tokens.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS auth_tokens (
                token       text PRIMARY KEY,
                user_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                kind        text NOT NULL,
                expires_at  timestamptz NOT NULL,
                created_at  timestamptz NOT NULL DEFAULT now()
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS usage_logs (
                id          bigserial PRIMARY KEY,
                user_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                kind        text NOT NULL,
                created_at  timestamptz NOT NULL DEFAULT now()
            );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_usage_user ON usage_logs(user_id, created_at);")
        # Chat history.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                title       text NOT NULL DEFAULT 'New chat',
                created_at  timestamptz NOT NULL DEFAULT now(),
                updated_at  timestamptz NOT NULL DEFAULT now()
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id          bigserial PRIMARY KEY,
                conv_id     uuid NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                role        text NOT NULL,
                content     text NOT NULL,
                created_at  timestamptz NOT NULL DEFAULT now()
            );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_conv_user ON conversations(user_id, updated_at DESC);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_msg_conv ON messages(conv_id, id);")
        # Payment transaction log.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id          bigserial PRIMARY KEY,
                user_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                provider    text NOT NULL,
                kind        text NOT NULL,
                item        text NOT NULL,
                amount_usd  numeric NOT NULL,
                ext_id      text,
                status      text NOT NULL DEFAULT 'completed',
                created_at  timestamptz NOT NULL DEFAULT now()
            );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_txn_user ON transactions(user_id, created_at DESC);")
        # currency of the stored amount (INR for India / Razorpay, USD otherwise).
        conn.execute("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS currency text NOT NULL DEFAULT 'INR'")
        # GST breakdown: amount_usd is the TOTAL charged. base + tax split for reporting.
        conn.execute("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS base_amount numeric NOT NULL DEFAULT 0")
        conn.execute("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS tax_amount numeric NOT NULL DEFAULT 0")
        conn.execute("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS gstin text NOT NULL DEFAULT ''")
        conn.execute("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS invoice_no text NOT NULL DEFAULT ''")
        # gap-free running counter for GST invoice numbers (WP-000001 ...).
        conn.execute("CREATE SEQUENCE IF NOT EXISTS invoice_seq START 1")
        # Webhook idempotency: one row per already-processed provider event/payment id.
        # A single purchase can fire several events (payment_link.paid, payment.captured,
        # order.paid) plus provider retries - we act on the first, ignore the rest.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS processed_events (
                event_key   text PRIMARY KEY,
                created_at  timestamptz NOT NULL DEFAULT now()
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS wordpress_sites (
                id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id            uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                site_url           text NOT NULL,
                wp_username        text NOT NULL,
                app_password_enc   bytea NOT NULL,
                app_password_nonce bytea NOT NULL,
                is_primary         boolean NOT NULL DEFAULT true,
                status             text NOT NULL DEFAULT 'active',
                created_at         timestamptz NOT NULL DEFAULT now()
            );
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_sites_user ON wordpress_sites(user_id);
        """)
        # Contact-form leads / queries (public /contact page).
        conn.execute("""
            CREATE TABLE IF NOT EXISTS contact_messages (
                id          bigserial PRIMARY KEY,
                name        text NOT NULL DEFAULT '',
                email       text NOT NULL DEFAULT '',
                service     text NOT NULL DEFAULT '',
                message     text NOT NULL DEFAULT '',
                meta        text NOT NULL DEFAULT '',   -- ip/user-agent, optional
                status      text NOT NULL DEFAULT 'new', -- new | read | archived
                created_at  timestamptz NOT NULL DEFAULT now()
            );
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_contact_created ON contact_messages(created_at DESC);
        """)
        # Google OAuth (Analytics + Search Console). We store the encrypted refresh
        # token per user; access tokens are short-lived and fetched on demand.
        # ga_property_id / sc_site are the user's chosen GA4 property + SC site.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS google_accounts (
                user_id            uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                site_id            uuid REFERENCES wordpress_sites(id) ON DELETE CASCADE,
                refresh_token_enc  bytea NOT NULL,
                refresh_token_nonce bytea NOT NULL,
                google_email       text NOT NULL DEFAULT '',
                ga_property_id     text NOT NULL DEFAULT '',
                sc_site            text NOT NULL DEFAULT '',
                connected_at       timestamptz NOT NULL DEFAULT now()
            );
        """)
        # Migrate the older per-user google_accounts (user_id PRIMARY KEY) to the
        # per-site shape: add site_id, drop the old single-row-per-user PK, and add a
        # unique index on (user_id, site_id) so each site gets its own Google account
        # while an existing user-level connection (site_id NULL) still works as the
        # default. Idempotent.
        conn.execute("ALTER TABLE google_accounts ADD COLUMN IF NOT EXISTS site_id uuid REFERENCES wordpress_sites(id) ON DELETE CASCADE;")
        conn.execute("ALTER TABLE google_accounts DROP CONSTRAINT IF EXISTS google_accounts_pkey;")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_google_user_site ON google_accounts (user_id, COALESCE(site_id, '00000000-0000-0000-0000-000000000000'::uuid));")
        # ----- Bing Webmaster Tools (API-key based, per (user, site)) -----
        # Same per-site shape as google_accounts. api_key stored encrypted (AES-GCM).
        # bing_site = the site URL as registered in Bing Webmaster Tools.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS bing_accounts (
                user_id       uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                site_id       uuid REFERENCES wordpress_sites(id) ON DELETE CASCADE,
                api_key_enc   bytea NOT NULL,
                api_key_nonce bytea NOT NULL,
                bing_site     text NOT NULL DEFAULT '',
                connected_at  timestamptz NOT NULL DEFAULT now()
            );
        """)
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_bing_user_site "
                     "ON bing_accounts (user_id, COALESCE(site_id, '00000000-0000-0000-0000-000000000000'::uuid));")
        # AI SEO score history - powers the weekly report card (before -> after).
        conn.execute("""
            CREATE TABLE IF NOT EXISTS score_snapshots (
                id          bigserial PRIMARY KEY,
                user_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                overall     int NOT NULL,
                categories  jsonb,
                issues      jsonb,
                created_at  timestamptz NOT NULL DEFAULT now()
            );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_snap_user ON score_snapshots(user_id, created_at DESC);")
        # Approval inbox - risky AI actions wait here for the user's OK.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pending_actions (
                id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                tool        text NOT NULL,
                args        jsonb,
                summary     text NOT NULL,
                risk        text NOT NULL DEFAULT 'medium',
                status      text NOT NULL DEFAULT 'pending',
                result      text,
                created_at  timestamptz NOT NULL DEFAULT now(),
                decided_at  timestamptz
            );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pending_user ON pending_actions(user_id, status, created_at DESC);")
        # Discount coupons (admin-created). percent OR flat amount off.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS coupons (
                code        text PRIMARY KEY,
                kind        text NOT NULL DEFAULT 'percent',   -- 'percent' | 'flat'
                value       numeric NOT NULL,                  -- 25 (%) or 500 (flat, in that currency)
                currency    text NOT NULL DEFAULT 'ANY',       -- 'ANY' | 'INR' | 'USD' (flat only)
                max_uses    int NOT NULL DEFAULT 0,            -- 0 = unlimited
                used_count  int NOT NULL DEFAULT 0,
                expires_at  timestamptz,                       -- NULL = never
                active      boolean NOT NULL DEFAULT true,
                note        text NOT NULL DEFAULT '',
                created_at  timestamptz NOT NULL DEFAULT now()
            );
        """)
        # Which coupon was applied to which paid transaction (redemption log).
        conn.execute("""
            CREATE TABLE IF NOT EXISTS coupon_redemptions (
                id          bigserial PRIMARY KEY,
                code        text NOT NULL,
                user_id     uuid REFERENCES users(id) ON DELETE SET NULL,
                plan        text,
                created_at  timestamptz NOT NULL DEFAULT now()
            );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_coupon_redeem ON coupon_redemptions(code, created_at DESC);")
        # Admin-editable settings (plan config, email templates) as JSON key-value.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS app_settings (
                key         text PRIMARY KEY,
                value       jsonb NOT NULL,
                updated_at  timestamptz NOT NULL DEFAULT now()
            );
        """)
        # ----- Community forum: categories -> threads -> posts (replies) -----
        conn.execute("""
            CREATE TABLE IF NOT EXISTS forum_categories (
                id          bigserial PRIMARY KEY,
                slug        text UNIQUE NOT NULL,
                name        text NOT NULL,
                description text NOT NULL DEFAULT '',
                sort        int NOT NULL DEFAULT 0,
                created_at  timestamptz NOT NULL DEFAULT now()
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS forum_threads (
                id          bigserial PRIMARY KEY,
                category_id bigint NOT NULL REFERENCES forum_categories(id) ON DELETE CASCADE,
                user_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                title       text NOT NULL,
                slug        text NOT NULL,
                body        text NOT NULL,
                pinned      boolean NOT NULL DEFAULT false,
                locked      boolean NOT NULL DEFAULT false,
                reply_count int NOT NULL DEFAULT 0,
                last_at     timestamptz NOT NULL DEFAULT now(),
                created_at  timestamptz NOT NULL DEFAULT now()
            );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_thread_cat ON forum_threads(category_id, pinned DESC, last_at DESC);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_thread_slug ON forum_threads(slug);")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS forum_posts (
                id          bigserial PRIMARY KEY,
                thread_id   bigint NOT NULL REFERENCES forum_threads(id) ON DELETE CASCADE,
                user_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                body        text NOT NULL,
                created_at  timestamptz NOT NULL DEFAULT now()
            );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_post_thread ON forum_posts(thread_id, id);")
        # ----- Affiliate / referral program -----
        # Each user can have a referral code; referrals link a new user to their referrer;
        # a commission is credited once, on the referred user's first paid payment.
        conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS ref_code text")
        conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS referred_by uuid")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_refcode ON users(ref_code) WHERE ref_code IS NOT NULL")
        conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS payout_method text NOT NULL DEFAULT ''")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS referrals (
                id             bigserial PRIMARY KEY,
                referrer_id    uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                referred_id    uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                status         text NOT NULL DEFAULT 'pending',   -- pending -> converted
                currency       text NOT NULL DEFAULT 'INR',
                sale_amount    numeric NOT NULL DEFAULT 0,        -- the paid amount that converted
                commission     numeric NOT NULL DEFAULT 0,        -- credited to the referrer
                rate           numeric NOT NULL DEFAULT 0,        -- % used at time of conversion
                converted_at   timestamptz,
                created_at     timestamptz NOT NULL DEFAULT now(),
                UNIQUE (referred_id)
            );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ref_referrer ON referrals(referrer_id, created_at DESC);")
        # Link a converted referral to the exact payment (ext_id) that generated it, so a
        # refund only reverses commission for THAT transaction, not later renewals.
        conn.execute("ALTER TABLE referrals ADD COLUMN IF NOT EXISTS convert_ext_id text NOT NULL DEFAULT ''")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS payout_requests (
                id           bigserial PRIMARY KEY,
                user_id      uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                amount       numeric NOT NULL,
                currency     text NOT NULL DEFAULT 'INR',
                method       text NOT NULL DEFAULT '',
                status       text NOT NULL DEFAULT 'requested',   -- requested -> paid / rejected
                note         text NOT NULL DEFAULT '',
                created_at   timestamptz NOT NULL DEFAULT now(),
                paid_at      timestamptz
            );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_payout_user ON payout_requests(user_id, created_at DESC);")
        # At most ONE open ('requested') payout per user+currency at a time. This makes the
        # duplicate check in request_payout race-safe: a concurrent second insert fails.
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_payout_open "
                     "ON payout_requests(user_id, currency) WHERE status='requested'")
        # ----- First-month welcome discount claims (abuse tracking) -----
        # One record per successful welcome-discount purchase. We block a second claim from
        # the SAME user, SAME device fingerprint, or SAME IP - so a person can't just make a
        # new email and grab the intro price again. (None of these is bullet-proof alone;
        # together they raise the bar without adding OTP/login friction.)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS welcome_claims (
                id           bigserial PRIMARY KEY,
                user_id      uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                fingerprint  text NOT NULL DEFAULT '',
                ip           text NOT NULL DEFAULT '',
                plan         text NOT NULL DEFAULT '',
                percent      int  NOT NULL DEFAULT 0,
                created_at   timestamptz NOT NULL DEFAULT now()
            );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_welcome_uid ON welcome_claims(user_id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_welcome_fp ON welcome_claims(fingerprint);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_welcome_ip ON welcome_claims(ip);")
        # ----- Admin-managed blog posts (stored in DB, alongside the built-in ones) -----
        conn.execute("""
            CREATE TABLE IF NOT EXISTS blog_posts_db (
                id           bigserial PRIMARY KEY,
                slug         text UNIQUE NOT NULL,
                title        text NOT NULL,
                description  text NOT NULL DEFAULT '',
                keywords     text NOT NULL DEFAULT '',
                hero         text NOT NULL DEFAULT 'hero-blog.webp',
                read_time    text NOT NULL DEFAULT '5 min read',
                body_html    text NOT NULL DEFAULT '',
                published    boolean NOT NULL DEFAULT true,
                created_at   timestamptz NOT NULL DEFAULT now(),
                updated_at   timestamptz NOT NULL DEFAULT now()
            );
        """)


# ---------------------------------------------------------------------------
# Encryption helpers (AES-256-GCM)
# ---------------------------------------------------------------------------
def encrypt_secret(plaintext: str) -> tuple[bytes, bytes]:
    """Return (ciphertext_with_tag, nonce)."""
    nonce = os.urandom(12)
    ct = AESGCM(_ENC_KEY).encrypt(nonce, plaintext.encode(), None)
    return ct, nonce


def decrypt_secret(ciphertext: bytes, nonce: bytes) -> str:
    return AESGCM(_ENC_KEY).decrypt(bytes(nonce), bytes(ciphertext), None).decode()


# ---------------------------------------------------------------------------
# Password hashing (login)
# ---------------------------------------------------------------------------
def hash_password(pw: str) -> str:
    return _ph.hash(pw)


def verify_password(hash_: str, pw: str) -> bool:
    try:
        return _ph.verify(hash_, pw)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------
def create_user(email: str, password: str) -> str:
    """Create a user, return user_id. Raises if email already exists."""
    uid = str(uuid.uuid4())
    with _pool.connection() as conn:
        conn.execute(
            "INSERT INTO users (id, email, password_hash) VALUES (%s, %s, %s)",
            (uid, email.lower().strip(), hash_password(password)),
        )
    return uid


def get_user_by_email(email: str):
    with _pool.connection() as conn:
        row = conn.execute(
            "SELECT id, email, password_hash FROM users WHERE email = %s",
            (email.lower().strip(),),
        ).fetchone()
    if not row:
        return None
    return {"id": str(row[0]), "email": row[1], "password_hash": row[2]}


def authenticate_user(email: str, password: str):
    """Return user_id if credentials valid, else None."""
    u = get_user_by_email(email)
    if u and verify_password(u["password_hash"], password):
        return u["id"]
    return None


# ---------------------------------------------------------------------------
# WordPress sites
# ---------------------------------------------------------------------------
def user_site_count(user_id: str) -> int:
    """How many active WordPress sites this user has connected."""
    with _pool.connection() as conn:
        n = conn.execute("SELECT count(*) FROM wordpress_sites WHERE user_id=%s AND status='active'",
                         (user_id,)).fetchone()[0]
    return int(n)


def plan_site_limit(user_id: str) -> int:
    """Max sites the user's plan allows (from plan config; defaults to 1 for free)."""
    with _pool.connection() as conn:
        r = conn.execute("SELECT plan FROM users WHERE id=%s", (user_id,)).fetchone()
    plan = r[0] if r else "free"
    if plan == "free":
        return 1
    cfg = get_plan_config().get(plan)
    return int(cfg.get("sites", 1)) if cfg else 1


def can_add_site(user_id: str) -> tuple:
    """Return (allowed, limit, current). Enforces the plan's site limit at connect time."""
    limit = plan_site_limit(user_id)
    current = user_site_count(user_id)
    return (current < limit, limit, current)


def add_site(user_id: str, site_url: str, wp_username: str, app_password: str,
             max_sites: int = None) -> str:
    """Encrypt + store a WP site for a user. Returns site_id, or None if max_sites is
    given and the user already has that many active sites (checked ATOMICALLY inside the
    same transaction, so two concurrent connects can't both slip past the limit)."""
    ct, nonce = encrypt_secret(app_password.replace(" ", ""))
    sid = str(uuid.uuid4())
    with _pool.connection() as conn:
        # Serialize concurrent connects for this user so the count+insert is atomic.
        conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (str(user_id),))
        if max_sites is not None:
            n = conn.execute("SELECT count(*) FROM wordpress_sites "
                             "WHERE user_id=%s AND status='active'", (user_id,)).fetchone()[0]
            if int(n) >= int(max_sites):
                return None
        # make any existing primary non-primary, this becomes primary
        conn.execute(
            "UPDATE wordpress_sites SET is_primary = false WHERE user_id = %s",
            (user_id,),
        )
        conn.execute(
            """INSERT INTO wordpress_sites
               (id, user_id, site_url, wp_username, app_password_enc, app_password_nonce, is_primary)
               VALUES (%s, %s, %s, %s, %s, %s, true)""",
            (sid, user_id, site_url.rstrip("/"), wp_username, ct, nonce),
        )
    return sid


def set_active_site(user_id: str, site_id):
    """Remember which site the AI is currently working on (persists across MCP
    requests). Pass None to clear (fall back to the primary/newest site)."""
    with _pool.connection() as conn:
        conn.execute("UPDATE users SET active_site_id = %s WHERE id = %s",
                     (site_id, user_id))


def get_primary_site(user_id: str):
    """Return the site the AI should act on WITH decrypted app password (runtime
    only): the user's chosen active site if set and still valid, otherwise the
    primary/newest site. Returns {site_url, wp_username, app_password} or None."""
    with _pool.connection() as conn:
        # 1) Honor an explicitly-chosen active site (set via use_site).
        active_id = conn.execute(
            "SELECT active_site_id FROM users WHERE id = %s", (user_id,)
        ).fetchone()
        if active_id and active_id[0]:
            row = conn.execute(
                """SELECT site_url, wp_username, app_password_enc, app_password_nonce
                   FROM wordpress_sites
                   WHERE id = %s AND user_id = %s AND status = 'active'""",
                (active_id[0], user_id),
            ).fetchone()
            if row:
                return {"site_url": row[0], "wp_username": row[1],
                        "app_password": decrypt_secret(row[2], row[3])}
        # 2) Fall back to primary/newest.
        row = conn.execute(
            """SELECT site_url, wp_username, app_password_enc, app_password_nonce
               FROM wordpress_sites
               WHERE user_id = %s AND status = 'active'
               ORDER BY is_primary DESC, created_at DESC LIMIT 1""",
            (user_id,),
        ).fetchone()
    if not row:
        return None
    return {
        "site_url": row[0],
        "wp_username": row[1],
        "app_password": decrypt_secret(row[2], row[3]),
    }


def delete_site_by_url(site_url: str) -> int:
    """Delete ANY site row matching this URL. INTERNAL/admin use only - NOT safe to
    expose to unauthenticated requests (it ignores ownership). Public disconnect must
    use delete_site_by_url_for_user. Returns number of rows removed."""
    if not site_url:
        return 0
    url = site_url.rstrip("/")
    with _pool.connection() as conn:
        cur = conn.execute(
            "DELETE FROM wordpress_sites WHERE site_url = %s", (url,))
        return cur.rowcount


def delete_site_by_url_for_user(user_id: str, site_url: str) -> int:
    """Delete a site by URL but ONLY if it belongs to this user. Used by the plugin's
    one-click Disconnect, which requires the user to be logged into wptaskify in the same
    browser. Returns rows removed (0 if the URL isn't one of the user's sites)."""
    if not (user_id and site_url):
        return 0
    url = site_url.rstrip("/")
    with _pool.connection() as conn:
        cur = conn.execute(
            "DELETE FROM wordpress_sites WHERE site_url = %s AND user_id = %s",
            (url, user_id))
        return cur.rowcount


# ---------------------------------------------------------------------------
# AI SEO score snapshots (weekly report card)
# ---------------------------------------------------------------------------
def save_score_snapshot(user_id: str, overall: int, categories: dict, issues: dict):
    """Store one AI-SEO-score reading. Deduped to at most one per day per user so
    the history stays clean."""
    with _pool.connection() as conn:
        recent = conn.execute(
            "SELECT id FROM score_snapshots WHERE user_id=%s AND created_at > now() - interval '20 hours' "
            "ORDER BY created_at DESC LIMIT 1", (user_id,)).fetchone()
        if recent:
            conn.execute("UPDATE score_snapshots SET overall=%s, categories=%s, issues=%s, created_at=now() "
                         "WHERE id=%s", (overall, json.dumps(categories), json.dumps(issues), recent[0]))
        else:
            conn.execute("INSERT INTO score_snapshots (user_id, overall, categories, issues) "
                         "VALUES (%s,%s,%s,%s)",
                         (user_id, overall, json.dumps(categories), json.dumps(issues)))


def get_latest_snapshot(user_id: str):
    with _pool.connection() as conn:
        row = conn.execute(
            "SELECT overall, categories, issues, created_at FROM score_snapshots "
            "WHERE user_id=%s ORDER BY created_at DESC LIMIT 1", (user_id,)).fetchone()
    if not row:
        return None
    return {"overall": row[0], "categories": row[1], "issues": row[2], "at": row[3].isoformat()}


def get_snapshot_before(user_id: str, days: int = 7):
    """The most recent snapshot at least `days` old - the 'before' side of the report."""
    with _pool.connection() as conn:
        row = conn.execute(
            "SELECT overall, categories, issues, created_at FROM score_snapshots "
            "WHERE user_id=%s AND created_at <= now() - make_interval(days => %s) "
            "ORDER BY created_at DESC LIMIT 1", (user_id, days)).fetchone()
    if not row:
        # fall back to the OLDEST snapshot we have.
        with _pool.connection() as conn:
            row = conn.execute(
                "SELECT overall, categories, issues, created_at FROM score_snapshots "
                "WHERE user_id=%s ORDER BY created_at ASC LIMIT 1", (user_id,)).fetchone()
    if not row:
        return None
    return {"overall": row[0], "categories": row[1], "issues": row[2], "at": row[3].isoformat()}


# ---------------------------------------------------------------------------
# Approval inbox (risky actions await user OK)
# ---------------------------------------------------------------------------
def create_pending_action(user_id: str, tool: str, args: dict, summary: str, risk: str = "medium") -> str:
    with _pool.connection() as conn:
        row = conn.execute(
            "INSERT INTO pending_actions (user_id, tool, args, summary, risk) "
            "VALUES (%s,%s,%s,%s,%s) RETURNING id",
            (user_id, tool, json.dumps(args or {}), summary, risk)).fetchone()
    return str(row[0])


def list_pending_actions(user_id: str, status: str = "pending"):
    with _pool.connection() as conn:
        rows = conn.execute(
            "SELECT id, tool, args, summary, risk, status, result, created_at FROM pending_actions "
            "WHERE user_id=%s AND status=%s ORDER BY created_at DESC LIMIT 50",
            (user_id, status)).fetchall()
    return [{"id": str(r[0]), "tool": r[1], "args": r[2], "summary": r[3], "risk": r[4],
             "status": r[5], "result": r[6], "created_at": r[7].isoformat()} for r in rows]


def get_pending_action(user_id: str, action_id: str):
    with _pool.connection() as conn:
        r = conn.execute(
            "SELECT id, tool, args, summary, risk, status FROM pending_actions "
            "WHERE id=%s AND user_id=%s", (action_id, user_id)).fetchone()
    if not r:
        return None
    return {"id": str(r[0]), "tool": r[1], "args": r[2], "summary": r[3], "risk": r[4], "status": r[5]}


def decide_pending_action(user_id: str, action_id: str, status: str, result: str = ""):
    """Mark a pending action approved / rejected / done. Returns True if updated."""
    with _pool.connection() as conn:
        cur = conn.execute(
            "UPDATE pending_actions SET status=%s, result=%s, decided_at=now() "
            "WHERE id=%s AND user_id=%s AND status IN ('pending','approved')",
            (status, result, action_id, user_id))
        return cur.rowcount > 0


def delete_site(user_id: str, site_id: str) -> bool:
    """Delete a site owned by this user. Returns True if a row was removed."""
    with _pool.connection() as conn:
        cur = conn.execute(
            "DELETE FROM wordpress_sites WHERE id = %s AND user_id = %s",
            (site_id, user_id),
        )
        deleted = cur.rowcount > 0
        # if we removed the primary, promote the newest remaining site
        if deleted:
            conn.execute(
                """UPDATE wordpress_sites SET is_primary = true
                   WHERE id = (SELECT id FROM wordpress_sites WHERE user_id = %s
                               ORDER BY created_at DESC LIMIT 1)
                   AND NOT EXISTS (SELECT 1 FROM wordpress_sites WHERE user_id = %s AND is_primary = true)""",
                (user_id, user_id),
            )
    return deleted


def site_is_registered(site_url: str) -> bool:
    """True if this site URL is stored + active for ANY user. Used by the
    wptaskify plugin to VERIFY a real connection (instead of trusting a
    ?connected=1 URL param that a failed connect could still carry)."""
    if not site_url:
        return False
    with _pool.connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM wordpress_sites WHERE site_url = %s AND status = 'active' LIMIT 1",
            (site_url.rstrip("/"),),
        ).fetchone()
    return bool(row)


def get_site_by_id(user_id: str, site_id: str):
    """Return a specific site (decrypted) owned by the user, or None."""
    with _pool.connection() as conn:
        row = conn.execute(
            """SELECT site_url, wp_username, app_password_enc, app_password_nonce
               FROM wordpress_sites WHERE id = %s AND user_id = %s AND status = 'active'""",
            (site_id, user_id),
        ).fetchone()
    if not row:
        return None
    return {"site_url": row[0], "wp_username": row[1],
            "app_password": decrypt_secret(row[2], row[3])}


def get_site_by_ref(user_id: str, ref: str):
    """Resolve one of the user's sites (decrypted creds) by a flexible reference:
    the site id, the exact site_url, or a domain substring (e.g. 'buyfrombest').
    Returns {id, site_url, wp_username, app_password} or None. Used so the AI can
    target a specific site when the user has several."""
    ref = (ref or "").strip()
    if not ref:
        return None
    with _pool.connection() as conn:
        rows = conn.execute(
            """SELECT id, site_url, wp_username, app_password_enc, app_password_nonce
               FROM wordpress_sites WHERE user_id = %s AND status = 'active'
               ORDER BY is_primary DESC, created_at DESC""",
            (user_id,),
        ).fetchall()
    if not rows:
        return None
    low = ref.lower().rstrip("/")
    # 1) exact id  2) exact url  3) domain substring
    best = None
    for r in rows:
        sid, url = str(r[0]), (r[1] or "")
        u = url.lower().rstrip("/")
        if sid == ref:
            best = r; break
        if u == low:
            best = r; break
    if best is None:
        for r in rows:
            if low in (r[1] or "").lower():
                best = r; break
    if best is None:
        return None
    return {"id": str(best[0]), "site_url": best[1], "wp_username": best[2],
            "app_password": decrypt_secret(best[3], best[4])}


def list_user_sites(user_id: str):
    """List a user's sites (NO password). For dashboard display."""
    with _pool.connection() as conn:
        rows = conn.execute(
            """SELECT id, site_url, wp_username, is_primary, status, created_at
               FROM wordpress_sites WHERE user_id = %s ORDER BY created_at DESC""",
            (user_id,),
        ).fetchall()
    return [
        {"id": str(r[0]), "site_url": r[1], "wp_username": r[2],
         "is_primary": r[3], "status": r[4], "created_at": str(r[5])}
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Credits + BYOK (image cost control)
# ---------------------------------------------------------------------------
def _current_month(now_iso: str) -> str:
    # now_iso = 'YYYY-MM-...'; we just need 'YYYY-MM' to detect a new month
    return now_iso[:7]


def get_account(user_id: str):
    """Return plan, credits, has_own_key, and refresh monthly credits if a new
    month started. The reset is done in a SINGLE atomic conditional UPDATE so a
    concurrent decrement can't race with (and be lost to) the month rollover."""
    with _pool.connection() as conn:
        row = conn.execute("SELECT plan FROM users WHERE id = %s", (user_id,)).fetchone()
        if not row:
            return None
        plan = row[0]
        fresh = PLAN_CREDITS.get(plan, 5)
        # Atomically: if the stored month is stale, set credits=fresh and stamp the month;
        # otherwise leave credits untouched. WHERE guards it to one winning writer.
        r = conn.execute(
            "UPDATE users SET "
            "  credits = CASE WHEN credits_month <> to_char(now(),'YYYY-MM') THEN %s ELSE credits END, "
            "  credits_month = to_char(now(),'YYYY-MM') "
            "WHERE id = %s "
            "RETURNING credits, (gemini_key_enc IS NOT NULL)",
            (fresh, user_id),
        ).fetchone()
        credits, has_key = r[0], r[1]
    return {"plan": plan, "credits": credits, "credits_max": fresh,
            "has_own_key": has_key}


def get_user_gemini_key(user_id: str):
    """Return the user's BYOK Gemini key (decrypted) or None."""
    with _pool.connection() as conn:
        row = conn.execute(
            "SELECT gemini_key_enc, gemini_key_nonce FROM users WHERE id = %s",
            (user_id,),
        ).fetchone()
    if not row or row[0] is None:
        return None
    return decrypt_secret(row[0], row[1])


def set_user_gemini_key(user_id: str, key: str):
    ct, nonce = encrypt_secret(key.strip())
    with _pool.connection() as conn:
        conn.execute(
            "UPDATE users SET gemini_key_enc = %s, gemini_key_nonce = %s WHERE id = %s",
            (ct, nonce, user_id),
        )


# ---------------------------------------------------------------------------
# Google (Analytics + Search Console) OAuth tokens
# ---------------------------------------------------------------------------
# google_accounts is now per-(user, site). site_id=None is the user-level "default"
# connection (used when a site has no Google account of its own). This lets a user
# connect a DIFFERENT Google/Gmail for each of their WordPress sites (e.g. when each
# site's Search Console lives on a different Google account).
_G_SENTINEL = "00000000-0000-0000-0000-000000000000"


def save_google_account(user_id: str, refresh_token: str, google_email: str = "",
                        site_id: str = None):
    """Store (encrypted) a Google refresh token for this user, optionally scoped to
    a specific site. Upserts on (user_id, site_id)."""
    ct, nonce = encrypt_secret(refresh_token.strip())
    sid = site_id or None
    with _pool.connection() as conn:
        # Manual upsert keyed on (user_id, COALESCE(site_id, sentinel)) to match the
        # unique index (Postgres ON CONFLICT can't target a COALESCE expression index
        # directly by column list).
        updated = conn.execute(
            """UPDATE google_accounts
               SET refresh_token_enc=%s, refresh_token_nonce=%s, google_email=%s, connected_at=now()
               WHERE user_id=%s AND COALESCE(site_id,%s::uuid)=COALESCE(%s::uuid,%s::uuid)""",
            (ct, nonce, google_email or "", user_id, _G_SENTINEL, sid, _G_SENTINEL),
        ).rowcount
        if not updated:
            conn.execute(
                """INSERT INTO google_accounts (user_id, site_id, refresh_token_enc, refresh_token_nonce, google_email)
                   VALUES (%s, %s, %s, %s, %s)""",
                (user_id, sid, ct, nonce, google_email or ""),
            )


def _google_row(conn, user_id, site_id, cols):
    """Fetch a google_accounts row for (user, site). If site_id is given but that
    site has no own connection, fall back to the user-level (site_id NULL) one."""
    sid = site_id or None
    if sid:
        row = conn.execute(
            f"SELECT {cols} FROM google_accounts WHERE user_id=%s AND site_id=%s",
            (user_id, sid),
        ).fetchone()
        if row:
            return row
    # user-level default (site_id NULL)
    return conn.execute(
        f"SELECT {cols} FROM google_accounts WHERE user_id=%s AND site_id IS NULL",
        (user_id,),
    ).fetchone()


def get_google_refresh_token(user_id: str, site_id: str = None):
    """Return the decrypted refresh token for this user (or this site), or None."""
    with _pool.connection() as conn:
        row = _google_row(conn, user_id, site_id, "refresh_token_enc, refresh_token_nonce")
    if not row or row[0] is None:
        return None
    return decrypt_secret(row[0], row[1])


def get_google_account(user_id: str, site_id: str = None):
    """Return {connected, google_email, ga_property_id, sc_site} for this user/site."""
    with _pool.connection() as conn:
        row = _google_row(conn, user_id, site_id, "google_email, ga_property_id, sc_site")
    if not row:
        return {"connected": False, "google_email": "", "ga_property_id": "", "sc_site": ""}
    return {"connected": True, "google_email": row[0], "ga_property_id": row[1], "sc_site": row[2]}


def set_google_selection(user_id: str, ga_property_id: str = None, sc_site: str = None,
                         site_id: str = None):
    """Set the chosen GA4 property and/or Search Console site for this user/site."""
    sets, vals = [], []
    if ga_property_id is not None:
        sets.append("ga_property_id = %s")
        vals.append(ga_property_id)
    if sc_site is not None:
        sets.append("sc_site = %s")
        vals.append(sc_site)
    if not sets:
        return
    sid = site_id or None
    vals += [user_id, _G_SENTINEL, sid, _G_SENTINEL]
    with _pool.connection() as conn:
        conn.execute(
            f"UPDATE google_accounts SET {', '.join(sets)} "
            f"WHERE user_id=%s AND COALESCE(site_id,%s::uuid)=COALESCE(%s::uuid,%s::uuid)",
            tuple(vals),
        )


def delete_google_account(user_id: str, site_id: str = None):
    """Disconnect Google for this user/site. site_id=None removes the user-level one."""
    sid = site_id or None
    with _pool.connection() as conn:
        if sid:
            conn.execute("DELETE FROM google_accounts WHERE user_id=%s AND site_id=%s",
                         (user_id, sid))
        else:
            conn.execute("DELETE FROM google_accounts WHERE user_id=%s AND site_id IS NULL",
                         (user_id,))


def list_google_accounts(user_id: str):
    """List all Google connections for a user, with which site (if any) each is for."""
    with _pool.connection() as conn:
        rows = conn.execute(
            """SELECT g.site_id, g.google_email, g.ga_property_id, g.sc_site, s.site_url
               FROM google_accounts g
               LEFT JOIN wordpress_sites s ON s.id = g.site_id
               WHERE g.user_id = %s ORDER BY g.connected_at DESC""",
            (user_id,),
        ).fetchall()
    return [{"site_id": str(r[0]) if r[0] else None, "google_email": r[1],
             "ga_property_id": r[2], "sc_site": r[3],
             "site_url": r[4] or "(account default)"} for r in rows]


# ---------------------------------------------------------------------------
# Bing Webmaster Tools (API-key, per (user, site)) - mirrors the Google helpers.
# ---------------------------------------------------------------------------
def save_bing_account(user_id: str, api_key: str, bing_site: str = "", site_id: str = None):
    """Store (encrypted) a Bing Webmaster API key for this user, optionally scoped to a
    specific site. Upserts on (user_id, site_id)."""
    ct, nonce = encrypt_secret(api_key.strip())
    sid = site_id or None
    with _pool.connection() as conn:
        updated = conn.execute(
            """UPDATE bing_accounts
               SET api_key_enc=%s, api_key_nonce=%s, bing_site=%s, connected_at=now()
               WHERE user_id=%s AND COALESCE(site_id,%s::uuid)=COALESCE(%s::uuid,%s::uuid)""",
            (ct, nonce, bing_site or "", user_id, _G_SENTINEL, sid, _G_SENTINEL),
        ).rowcount
        if not updated:
            conn.execute(
                """INSERT INTO bing_accounts (user_id, site_id, api_key_enc, api_key_nonce, bing_site)
                   VALUES (%s, %s, %s, %s, %s)""",
                (user_id, sid, ct, nonce, bing_site or ""),
            )


def _bing_row(conn, user_id, site_id, cols):
    """Fetch a bing_accounts row for (user, site), falling back to the user-level one."""
    sid = site_id or None
    if sid:
        row = conn.execute(
            f"SELECT {cols} FROM bing_accounts WHERE user_id=%s AND site_id=%s",
            (user_id, sid)).fetchone()
        if row:
            return row
    return conn.execute(
        f"SELECT {cols} FROM bing_accounts WHERE user_id=%s AND site_id IS NULL",
        (user_id,)).fetchone()


def get_bing_api_key(user_id: str, site_id: str = None):
    """Return the decrypted Bing API key for this user/site, or None."""
    with _pool.connection() as conn:
        row = _bing_row(conn, user_id, site_id, "api_key_enc, api_key_nonce")
    if not row or row[0] is None:
        return None
    return decrypt_secret(row[0], row[1])


def get_bing_account(user_id: str, site_id: str = None):
    """Return {connected, bing_site} for this user/site."""
    with _pool.connection() as conn:
        row = _bing_row(conn, user_id, site_id, "bing_site")
    if not row:
        return {"connected": False, "bing_site": ""}
    return {"connected": True, "bing_site": row[0]}


def set_bing_site(user_id: str, bing_site: str, site_id: str = None):
    """Set the chosen Bing site URL for this user/site."""
    sid = site_id or None
    with _pool.connection() as conn:
        conn.execute(
            "UPDATE bing_accounts SET bing_site=%s "
            "WHERE user_id=%s AND COALESCE(site_id,%s::uuid)=COALESCE(%s::uuid,%s::uuid)",
            (bing_site, user_id, _G_SENTINEL, sid, _G_SENTINEL))


def delete_bing_account(user_id: str, site_id: str = None):
    """Disconnect Bing for this user/site."""
    sid = site_id or None
    with _pool.connection() as conn:
        if sid:
            conn.execute("DELETE FROM bing_accounts WHERE user_id=%s AND site_id=%s",
                         (user_id, sid))
        else:
            conn.execute("DELETE FROM bing_accounts WHERE user_id=%s AND site_id IS NULL",
                         (user_id,))


def list_bing_accounts(user_id: str):
    """List all Bing connections for a user, with which site (if any) each is for."""
    with _pool.connection() as conn:
        rows = conn.execute(
            """SELECT b.site_id, b.bing_site, s.site_url
               FROM bing_accounts b
               LEFT JOIN wordpress_sites s ON s.id = b.site_id
               WHERE b.user_id = %s ORDER BY b.connected_at DESC""",
            (user_id,)).fetchall()
    return [{"site_id": str(r[0]) if r[0] else None, "bing_site": r[1],
             "site_url": r[2] or "(account default)"} for r in rows]


# ---------------------------------------------------------------------------
# Contact-form leads
# ---------------------------------------------------------------------------
def save_contact_message(name: str, email: str, message: str, service: str = "", meta: str = ""):
    """Store a contact/quote query from the public /contact form. Returns the id."""
    with _pool.connection() as conn:
        row = conn.execute(
            """INSERT INTO contact_messages (name, email, service, message, meta)
               VALUES (%s, %s, %s, %s, %s) RETURNING id""",
            (name[:200], email[:200], service[:80], message[:5000], meta[:400]),
        ).fetchone()
    return row[0] if row else None


def admin_list_contacts(limit: int = 100, status: str = ""):
    """List contact leads (newest first). Optional status filter."""
    with _pool.connection() as conn:
        if status:
            rows = conn.execute(
                """SELECT id, name, email, service, message, status, created_at
                   FROM contact_messages WHERE status = %s
                   ORDER BY created_at DESC LIMIT %s""",
                (status, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT id, name, email, service, message, status, created_at
                   FROM contact_messages ORDER BY created_at DESC LIMIT %s""",
                (limit,),
            ).fetchall()
    return [
        {"id": r[0], "name": r[1], "email": r[2], "service": r[3],
         "message": r[4], "status": r[5], "created_at": str(r[6])}
        for r in rows
    ]


def admin_contact_counts():
    """Return {'new': N, 'total': M} for the admin badge."""
    with _pool.connection() as conn:
        total = conn.execute("SELECT COUNT(*) FROM contact_messages").fetchone()[0]
        new = conn.execute("SELECT COUNT(*) FROM contact_messages WHERE status='new'").fetchone()[0]
    return {"new": int(new), "total": int(total)}


def admin_set_contact_status(msg_id: int, status: str):
    if status not in ("new", "read", "archived"):
        return
    with _pool.connection() as conn:
        conn.execute("UPDATE contact_messages SET status=%s WHERE id=%s", (status, msg_id))


# ---------------------------------------------------------------------------
# Email verify + password reset tokens
# ---------------------------------------------------------------------------
import secrets
from datetime import datetime, timedelta, timezone


def is_verified(user_id: str) -> bool:
    with _pool.connection() as conn:
        row = conn.execute("SELECT email_verified FROM users WHERE id = %s", (user_id,)).fetchone()
    return bool(row and row[0])


def create_token(user_id: str, kind: str, hours: int = 24) -> str:
    """kind = 'verify' or 'reset'. Returns the token string."""
    tok = secrets.token_urlsafe(32)
    exp = datetime.now(timezone.utc) + timedelta(hours=hours)
    with _pool.connection() as conn:
        # one active token per (user, kind)
        conn.execute("DELETE FROM auth_tokens WHERE user_id = %s AND kind = %s", (user_id, kind))
        conn.execute(
            "INSERT INTO auth_tokens (token, user_id, kind, expires_at) VALUES (%s,%s,%s,%s)",
            (tok, user_id, kind, exp),
        )
    return tok


def consume_token(token: str, kind: str):
    """Validate + delete a token. Returns user_id if valid, else None."""
    with _pool.connection() as conn:
        row = conn.execute(
            "SELECT user_id, expires_at FROM auth_tokens WHERE token = %s AND kind = %s",
            (token, kind),
        ).fetchone()
        if not row:
            return None
        user_id, exp = row
        conn.execute("DELETE FROM auth_tokens WHERE token = %s", (token,))
        if exp < datetime.now(timezone.utc):
            return None
    return str(user_id)


def mark_verified(user_id: str):
    with _pool.connection() as conn:
        conn.execute("UPDATE users SET email_verified = true WHERE id = %s", (user_id,))


def set_password(user_id: str, new_password: str):
    with _pool.connection() as conn:
        # Changing the password also bumps session_ver so all OTHER existing sessions
        # (e.g. an attacker holding a stolen cookie) are immediately invalidated.
        conn.execute(
            "UPDATE users SET password_hash = %s, session_ver = session_ver + 1 WHERE id = %s",
            (hash_password(new_password), user_id),
        )


def get_session_ver(user_id: str) -> int:
    """Current session version for a user (cookies minted with an older version are stale)."""
    with _pool.connection() as conn:
        row = conn.execute("SELECT session_ver FROM users WHERE id = %s", (user_id,)).fetchone()
    return int(row[0]) if row else 0


def bump_session_ver(user_id: str):
    """Invalidate all existing sessions for this user (logout-everywhere / ban)."""
    with _pool.connection() as conn:
        conn.execute("UPDATE users SET session_ver = session_ver + 1 WHERE id = %s", (user_id,))


def get_email(user_id: str):
    with _pool.connection() as conn:
        row = conn.execute("SELECT email FROM users WHERE id = %s", (user_id,)).fetchone()
    return row[0] if row else None


# ---------------------------------------------------------------------------
# Profile / account settings (user self-service)
# ---------------------------------------------------------------------------
def get_profile(user_id: str):
    """Everything the user's own Settings page needs."""
    with _pool.connection() as conn:
        r = conn.execute(
            "SELECT email, name, email_verified, notify_email, plan, created_at, "
            "(gemini_key_enc IS NOT NULL), gstin FROM users WHERE id=%s", (user_id,)).fetchone()
    if not r:
        return None
    return {"email": r[0], "name": r[1] or "", "verified": r[2], "notify_email": r[3],
            "plan": r[4], "created_at": str(r[5]), "byok": r[6], "gstin": r[7] or ""}


def update_name(user_id: str, name: str):
    with _pool.connection() as conn:
        conn.execute("UPDATE users SET name=%s WHERE id=%s", (name.strip()[:80], user_id))


def set_notify_email(user_id: str, on: bool):
    with _pool.connection() as conn:
        conn.execute("UPDATE users SET notify_email=%s WHERE id=%s", (bool(on), user_id))


def verify_user_password(user_id: str, password: str) -> bool:
    """Confirm the user's current password by user id (needed before email/password
    change). Distinct from verify_password(hash, pw) used by authenticate_user."""
    with _pool.connection() as conn:
        r = conn.execute("SELECT password_hash FROM users WHERE id=%s", (user_id,)).fetchone()
    if not r:
        return False
    try:
        _ph.verify(r[0], password)
        return True
    except Exception:
        return False


def change_email(user_id: str, new_email: str) -> tuple[bool, str]:
    """Change the user's email. Marks it unverified so they re-verify. Returns
    (ok, error). Fails if the email is already used by another account."""
    new_email = new_email.strip().lower()
    if "@" not in new_email or "." not in new_email:
        return False, "Please enter a valid email address."
    with _pool.connection() as conn:
        taken = conn.execute(
            "SELECT 1 FROM users WHERE email=%s AND id<>%s", (new_email, user_id)).fetchone()
        if taken:
            return False, "That email is already in use."
        conn.execute("UPDATE users SET email=%s, email_verified=false WHERE id=%s",
                     (new_email, user_id))
    return True, ""


def delete_own_account(user_id: str):
    """User deletes their own account (cascades sites/txns/usage)."""
    with _pool.connection() as conn:
        conn.execute("DELETE FROM users WHERE id=%s", (user_id,))


# ---------------------------------------------------------------------------
# Built-in chat: AI token budget (monthly, per plan)
# ---------------------------------------------------------------------------
def get_token_account(user_id: str):
    """Return {plan, tokens, tokens_max, credits, credits_max} with monthly reset.
    `tokens` = raw Claude tokens remaining; `credits` = tokens/1000 for display."""
    with _pool.connection() as conn:
        row = conn.execute(
            "SELECT plan, ai_tokens, ai_tokens_month, to_char(now(),'YYYY-MM') "
            "FROM users WHERE id = %s", (user_id,),
        ).fetchone()
        if not row:
            return None
        plan, tokens, tmonth, this_month = row
        token_max = PLAN_TOKENS.get(plan, PLAN_TOKENS["free"])
        if tmonth != this_month:
            tokens = token_max
            conn.execute(
                "UPDATE users SET ai_tokens = %s, ai_tokens_month = %s WHERE id = %s",
                (tokens, this_month, user_id),
            )
    return {
        "plan": plan,
        "tokens": int(tokens),
        "tokens_max": token_max,
        "credits": int(tokens) // TOKENS_PER_CREDIT,
        "credits_max": token_max // TOKENS_PER_CREDIT,
        "model": PLAN_MODEL.get(plan, "claude-haiku-4-5"),
        "is_chat_plan": plan in CHAT_PLANS,
    }


def has_tokens(user_id: str) -> bool:
    """True if the user has any chat tokens left this month."""
    acct = get_token_account(user_id)
    return bool(acct and acct["tokens"] > 0)


def consume_tokens(user_id: str, used: int) -> int:
    """Subtract `used` tokens (input+output) after a chat turn. Floors at 0.
    Returns remaining tokens."""
    if used <= 0:
        acct = get_token_account(user_id)
        return acct["tokens"] if acct else 0
    with _pool.connection() as conn:
        row = conn.execute(
            "UPDATE users SET ai_tokens = GREATEST(ai_tokens - %s, 0) WHERE id = %s "
            "RETURNING ai_tokens", (used, user_id),
        ).fetchone()
        conn.execute(
            "INSERT INTO usage_logs (user_id, kind) VALUES (%s, 'chat')", (user_id,),
        )
    return int(row[0]) if row else 0


# ---------------------------------------------------------------------------
# Chat conversations + messages
# ---------------------------------------------------------------------------
def create_conversation(user_id: str, title: str = "New chat") -> str:
    cid = str(uuid.uuid4())
    with _pool.connection() as conn:
        conn.execute(
            "INSERT INTO conversations (id, user_id, title) VALUES (%s,%s,%s)",
            (cid, user_id, title[:120]),
        )
    return cid


def list_conversations(user_id: str, limit: int = 50):
    with _pool.connection() as conn:
        rows = conn.execute(
            "SELECT id, title, updated_at FROM conversations WHERE user_id = %s "
            "ORDER BY updated_at DESC LIMIT %s", (user_id, limit),
        ).fetchall()
    return [{"id": str(r[0]), "title": r[1], "updated_at": str(r[2])} for r in rows]


def _owns_conversation(conn, user_id, conv_id):
    r = conn.execute("SELECT 1 FROM conversations WHERE id = %s AND user_id = %s",
                     (conv_id, user_id)).fetchone()
    return r is not None


def get_conversation(user_id: str, conv_id: str):
    """Return {id, title, messages:[{role,content}]} or None if not owned."""
    with _pool.connection() as conn:
        if not _owns_conversation(conn, user_id, conv_id):
            return None
        trow = conn.execute("SELECT title FROM conversations WHERE id = %s", (conv_id,)).fetchone()
        rows = conn.execute(
            "SELECT role, content FROM messages WHERE conv_id = %s ORDER BY id", (conv_id,),
        ).fetchall()
    return {"id": conv_id, "title": trow[0] if trow else "Chat",
            "messages": [{"role": r[0], "content": r[1]} for r in rows]}


def add_message(user_id: str, conv_id: str, role: str, content: str) -> bool:
    with _pool.connection() as conn:
        if not _owns_conversation(conn, user_id, conv_id):
            return False
        conn.execute(
            "INSERT INTO messages (conv_id, role, content) VALUES (%s,%s,%s)",
            (conv_id, role, content),
        )
        conn.execute("UPDATE conversations SET updated_at = now() WHERE id = %s", (conv_id,))
    return True


def rename_conversation(user_id: str, conv_id: str, title: str) -> bool:
    with _pool.connection() as conn:
        cur = conn.execute(
            "UPDATE conversations SET title = %s WHERE id = %s AND user_id = %s",
            (title[:120], conv_id, user_id),
        )
        return cur.rowcount > 0


def delete_conversation(user_id: str, conv_id: str) -> bool:
    with _pool.connection() as conn:
        cur = conn.execute(
            "DELETE FROM conversations WHERE id = %s AND user_id = %s", (conv_id, user_id),
        )
        return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Billing: plan changes, top-ups, transactions, subscriptions
# ---------------------------------------------------------------------------
def set_plan(user_id: str, plan: str, valid_days: int = 0):
    """Switch a user's plan and grant that plan's monthly allowances immediately.

    `valid_days` (when > 0) stamps `sub_renews_at` = now + valid_days. This is the
    EXPIRY for a one-time (non-recurring) purchase: `downgrade_expired_plans()` runs
    daily and drops any paid user past this date back to 'free'. Without it a one-time
    Razorpay payment would grant the plan forever. valid_days=0 leaves the existing
    renewal date untouched (used for 'free' downgrades)."""
    imgs = PLAN_CREDITS.get(plan, 5)
    toks = PLAN_TOKENS.get(plan, PLAN_TOKENS["free"])
    calls = PLAN_TOOLCALLS.get(plan, 100)
    with _pool.connection() as conn:
        this_month = conn.execute("SELECT to_char(now(),'YYYY-MM')").fetchone()[0]
        if valid_days and valid_days > 0:
            conn.execute(
                "UPDATE users SET plan=%s, credits=%s, credits_month=%s, "
                "ai_tokens=%s, ai_tokens_month=%s, tool_calls=%s, tool_calls_month=%s, "
                "sub_renews_at = now() + make_interval(days => %s), renew_notified='', "
                "expiry_notified = NULL "   # new period -> allow a fresh expiry reminder
                "WHERE id=%s",
                (plan, imgs, this_month, toks, this_month, calls, this_month,
                 int(valid_days), user_id),
            )
        else:
            conn.execute(
                "UPDATE users SET plan=%s, credits=%s, credits_month=%s, "
                "ai_tokens=%s, ai_tokens_month=%s, tool_calls=%s, tool_calls_month=%s "
                "WHERE id=%s",
                (plan, imgs, this_month, toks, this_month, calls, this_month, user_id),
            )


def downgrade_expired_plans():
    """Daily job: drop any paid, ACTIVE, non-recurring plan whose `sub_renews_at` has
    passed back to 'free'. This is what makes a one-time Razorpay purchase last exactly
    one billing period instead of forever. Returns the number of users downgraded.

    Safe to run repeatedly (idempotent): only touches rows still on a paid plan with an
    expiry in the past. Owner/unlimited and 'free' users are never affected."""
    fresh = PLAN_CREDITS.get("free", 5)
    toks = PLAN_TOKENS.get("free", PLAN_TOKENS["free"])
    calls = PLAN_TOOLCALLS.get("free", 100)
    with _pool.connection() as conn:
        this_month = conn.execute("SELECT to_char(now(),'YYYY-MM')").fetchone()[0]
        rows = conn.execute(
            "UPDATE users SET plan='free', credits=LEAST(credits,%s), credits_month=%s, "
            "  ai_tokens=LEAST(ai_tokens,%s), ai_tokens_month=%s, "
            "  tool_calls=LEAST(tool_calls,%s), tool_calls_month=%s, "
            "  sub_status='expired' "
            "WHERE plan <> 'free' AND plan <> 'unlimited' "
            "  AND sub_status IN ('active','canceled') AND sub_renews_at IS NOT NULL "
            "  AND sub_renews_at < now() "
            "RETURNING id",
            (fresh, this_month, toks, this_month, calls, this_month),
        ).fetchall()
    return len(rows)


def claim_expiring_users(within_days: int = 3):
    """Daily job helper: find paid, ACTIVE (not canceled/subscription) plans that expire
    within `within_days` and haven't been reminded yet for THIS period. Atomically stamp
    expiry_notified = the current sub_renews_at (so a re-run won't email again) and return
    the claimed rows so the caller can send the email.

    Returns list of {user_id, plan, renews_at, days_left}. Only ACTIVE one-time plans get
    reminded - a 'canceled' user chose to leave, and true subscriptions auto-renew.
    Race-safe: the stamping UPDATE ... RETURNING claims each row exactly once."""
    with _pool.connection() as conn:
        rows = conn.execute(
            "UPDATE users SET expiry_notified = sub_renews_at "
            "WHERE plan NOT IN ('free','unlimited') "
            "  AND sub_status = 'active' "
            "  AND sub_renews_at IS NOT NULL "
            "  AND sub_renews_at > now() "
            "  AND sub_renews_at <= now() + make_interval(days => %s) "
            "  AND (expiry_notified IS DISTINCT FROM sub_renews_at) "
            "RETURNING id, plan, sub_renews_at, "
            "          CEIL(EXTRACT(EPOCH FROM (sub_renews_at - now())) / 86400.0)::int",
            (int(within_days),),
        ).fetchall()
    return [{"user_id": str(r[0]), "plan": r[1], "renews_at": str(r[2]),
             "days_left": int(r[3])} for r in rows]


def cancel_subscription(user_id: str, at_period_end: bool = True):
    """User-initiated cancel. We DON'T yank the plan immediately (they paid for the
    period): we mark sub_status='canceled' so no renewal happens and the daily
    `downgrade_expired_plans` job drops them to free once `sub_renews_at` passes. If
    there's no expiry recorded (shouldn't happen for paid), downgrade right away.
    Returns the effective end date string (or '' if downgraded now)."""
    with _pool.connection() as conn:
        row = conn.execute(
            "SELECT plan, sub_renews_at FROM users WHERE id=%s", (user_id,)).fetchone()
        if not row or row[0] in ("free", "unlimited"):
            return ""
        renews_at = row[1]
        if at_period_end and renews_at:
            conn.execute(
                "UPDATE users SET sub_status='canceled' WHERE id=%s", (user_id,))
            return str(renews_at)[:10]
    # No period end on record -> downgrade immediately.
    set_plan(user_id, "free")
    with _pool.connection() as conn:
        conn.execute("UPDATE users SET sub_status='canceled' WHERE id=%s", (user_id,))
    return ""


def add_credits(user_id: str, count: int):
    """Top up image credits (does not reset monthly bucket). Used for PAID top-up packs,
    which are allowed to exceed the monthly plan allotment."""
    with _pool.connection() as conn:
        conn.execute("UPDATE users SET credits = credits + %s WHERE id=%s", (count, user_id))


def refund_credit(user_id: str, count: int = 1):
    """Give back an image credit after a FAILED generation. The refund is capped so a
    string of failures can't inflate the balance beyond where it started, but it must
    NEVER destroy paid top-up credits: the ceiling is the GREATER of the plan's monthly
    allotment and the user's current balance (which may be higher due to a top-up)."""
    with _pool.connection() as conn:
        row = conn.execute("SELECT plan, credits FROM users WHERE id=%s", (user_id,)).fetchone()
        if not row:
            return
        cap = max(PLAN_CREDITS.get(row[0], 5), int(row[1]))
        conn.execute("UPDATE users SET credits = LEAST(credits + %s, %s) WHERE id=%s",
                     (count, cap, user_id))


def add_tokens(user_id: str, count: int):
    """Top up chat AI tokens."""
    with _pool.connection() as conn:
        conn.execute("UPDATE users SET ai_tokens = ai_tokens + %s WHERE id=%s", (count, user_id))


def refund_toolcall(user_id: str, count: int = 1):
    """Give back a consumed tool call when the underlying WP request failed, so users
    aren't charged an action for an error. Capped at the plan max so it never overflows."""
    with _pool.connection() as conn:
        row = conn.execute("SELECT plan, tool_calls FROM users WHERE id=%s", (user_id,)).fetchone()
        if not row:
            return
        cap = max(PLAN_TOOLCALLS.get(row[0], 100), int(row[1]))
        conn.execute("UPDATE users SET tool_calls = LEAST(tool_calls + %s, %s) WHERE id=%s",
                     (count, cap, user_id))


def set_stripe_customer(user_id: str, customer_id: str):
    with _pool.connection() as conn:
        conn.execute("UPDATE users SET stripe_customer_id=%s WHERE id=%s", (customer_id, user_id))


def get_stripe_customer(user_id: str):
    with _pool.connection() as conn:
        r = conn.execute("SELECT stripe_customer_id FROM users WHERE id=%s", (user_id,)).fetchone()
    return r[0] if r and r[0] else None


def set_subscription(user_id: str, provider: str, sub_id: str, status: str, renews_at=None):
    with _pool.connection() as conn:
        conn.execute(
            "UPDATE users SET sub_provider=%s, sub_id=%s, sub_status=%s, sub_renews_at=%s WHERE id=%s",
            (provider, sub_id, status, renews_at, user_id),
        )


def set_subscription_status(user_id: str, status: str):
    """Update only sub_status (e.g. 'canceled' when a Razorpay subscription is cancelled),
    leaving sub_id / renews_at intact so the plan runs out its paid period."""
    with _pool.connection() as conn:
        conn.execute("UPDATE users SET sub_status=%s WHERE id=%s", (status, user_id))


def get_subscription_id(user_id: str):
    """The provider subscription id (Razorpay sub_xxx / Stripe sub_xxx), or ''."""
    with _pool.connection() as conn:
        r = conn.execute("SELECT sub_id FROM users WHERE id=%s", (user_id,)).fetchone()
    return (r[0] if r and r[0] else "") or ""


def find_user_by_stripe_customer(customer_id: str):
    with _pool.connection() as conn:
        r = conn.execute("SELECT id FROM users WHERE stripe_customer_id=%s", (customer_id,)).fetchone()
    return str(r[0]) if r else None


def next_invoice_no():
    """Allocate the next gap-free GST invoice number, e.g. WP-000042."""
    with _pool.connection() as conn:
        n = conn.execute("SELECT nextval('invoice_seq')").fetchone()[0]
    return f"WP-{int(n):06d}"


def mark_event_processed(event_key: str) -> bool:
    """Atomically claim a provider event/payment id. Returns True if THIS call is the
    first to see it (caller should process), False if it was already handled (duplicate
    webhook / retry - caller must skip). Empty key -> treated as new (can't dedup)."""
    if not event_key:
        return True
    with _pool.connection() as conn:
        row = conn.execute(
            "INSERT INTO processed_events (event_key) VALUES (%s) "
            "ON CONFLICT (event_key) DO NOTHING RETURNING event_key",
            (event_key,),
        ).fetchone()
    return row is not None


def record_transaction(user_id: str, provider: str, kind: str, item: str,
                       amount_usd: float, ext_id: str = "", status: str = "completed",
                       currency: str = "INR", base_amount=None, tax_amount=0, gstin="",
                       invoice_no=""):
    if base_amount is None:
        base_amount = amount_usd
    with _pool.connection() as conn:
        conn.execute(
            "INSERT INTO transactions (user_id, provider, kind, item, amount_usd, ext_id, "
            "status, currency, base_amount, tax_amount, gstin, invoice_no) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (user_id, provider, kind, item, amount_usd, ext_id, status, currency,
             base_amount, tax_amount, gstin, invoice_no),
        )


def list_transactions(user_id: str, limit: int = 20):
    with _pool.connection() as conn:
        rows = conn.execute(
            "SELECT kind, item, amount_usd, provider, status, created_at, currency FROM transactions "
            "WHERE user_id=%s ORDER BY created_at DESC LIMIT %s", (user_id, limit),
        ).fetchall()
    return [{"kind": r[0], "item": r[1], "amount_usd": float(r[2]), "provider": r[3],
             "status": r[4], "created_at": str(r[5]), "currency": r[6]} for r in rows]


def get_billing_summary(user_id: str):
    with _pool.connection() as conn:
        r = conn.execute(
            "SELECT plan, sub_status, sub_provider, sub_renews_at FROM users WHERE id=%s",
            (user_id,),
        ).fetchone()
    if not r:
        return None
    return {"plan": r[0], "sub_status": r[1], "sub_provider": r[2],
            "renews_at": str(r[3]) if r[3] else None}


def get_toolcall_account(user_id: str):
    """Return {plan, tool_calls, tool_calls_max}. The monthly reset is a single atomic
    conditional UPDATE so a concurrent consume can't race with the month rollover."""
    with _pool.connection() as conn:
        prow = conn.execute("SELECT plan FROM users WHERE id = %s", (user_id,)).fetchone()
        if not prow:
            return None
        plan = prow[0]
        cmax = PLAN_TOOLCALLS.get(plan, 100)
        r = conn.execute(
            "UPDATE users SET "
            "  tool_calls = CASE WHEN tool_calls_month <> to_char(now(),'YYYY-MM') THEN %s ELSE tool_calls END, "
            "  tool_calls_month = to_char(now(),'YYYY-MM') "
            "WHERE id = %s RETURNING tool_calls",
            (cmax, user_id),
        ).fetchone()
        calls = r[0]
    return {"plan": plan, "tool_calls": int(calls), "tool_calls_max": cmax}


def try_consume_toolcall(user_id: str, tool: str = "action") -> bool:
    """Atomically consume 1 tool call. Returns False if the monthly limit is hit.
    Chat plans have a huge limit so they effectively never block here.
    Logs the action (with the tool name) to usage_logs for admin analytics."""
    acct = get_toolcall_account(user_id)  # handles monthly reset
    if acct is None:
        return False
    with _pool.connection() as conn:
        row = conn.execute(
            "UPDATE users SET tool_calls = tool_calls - 1 WHERE id = %s AND tool_calls > 0 "
            "RETURNING tool_calls", (user_id,),
        ).fetchone()
        if row is not None:
            conn.execute("INSERT INTO usage_logs (user_id, kind) VALUES (%s, %s)",
                         (user_id, (tool or "action")[:60]))
    return row is not None


# How low the balance can get before we warn (email + in-chat). Fire once per month.
LOW_IMG_THRESHOLD = 5
LOW_ACT_THRESHOLD = 25

# Set by start.py at boot so db can send the low-balance email without importing it.
_low_email_cb = None


def set_low_balance_emailer(fn):
    """fn(user_id, kind, remaining) -> sends the low-balance email. Injected to
    avoid a db -> mailer import cycle."""
    global _low_email_cb
    _low_email_cb = fn


def _maybe_low_email(user_id, kind, remaining):
    """Fire the low-balance email once per month per kind (uses a marker column)."""
    if _low_email_cb is None:
        return
    col = "low_img_notified" if kind == "image" else "renew_notified"
    try:
        with _pool.connection() as conn:
            this_month = conn.execute("SELECT to_char(now(),'YYYY-MM')").fetchone()[0]
            row = conn.execute(f"SELECT {col} FROM users WHERE id=%s", (user_id,)).fetchone()
            if row and row[0] == this_month:
                return  # already warned this month
            conn.execute(f"UPDATE users SET {col}=%s WHERE id=%s", (this_month, user_id))
        _low_email_cb(user_id, kind, remaining)
    except Exception:
        pass


def try_consume_credit(user_id: str) -> bool:
    """Atomically consume 1 image credit. Returns True if consumed, False if the
    user is out of credits (and has no own key). BYOK users bypass credits."""
    acct = get_account(user_id)  # also handles monthly reset
    if acct is None:
        return False
    if acct["has_own_key"]:
        return True  # own key -> unlimited, no credit consumed
    with _pool.connection() as conn:
        # atomic decrement only if credits > 0
        row = conn.execute(
            "UPDATE users SET credits = credits - 1 WHERE id = %s AND credits > 0 "
            "RETURNING credits",
            (user_id,),
        ).fetchone()
        if row is None:
            return False
        conn.execute(
            "INSERT INTO usage_logs (user_id, kind) VALUES (%s, 'image')",
            (user_id,),
        )
    remaining = row[0]
    if 0 < remaining <= LOW_IMG_THRESHOLD:
        _maybe_low_email(user_id, "image", remaining)
    return True


def credits_left(user_id: str):
    """Current image credits + whether the user has their own key (unlimited)."""
    acct = get_account(user_id)
    if not acct:
        return None
    return {"credits": acct["credits"], "has_own_key": acct["has_own_key"],
            "max": acct.get("credits_max", 5)}


def get_balances(user_id: str):
    """Snapshot of image + action balances for the in-chat low-balance warning."""
    with _pool.connection() as conn:
        r = conn.execute(
            "SELECT plan, credits, tool_calls, (gemini_key_enc IS NOT NULL) "
            "FROM users WHERE id=%s", (user_id,)).fetchone()
    if not r:
        return {}
    plan = r[0]
    return {
        "images": r[1], "images_max": PLAN_CREDITS.get(plan, 5),
        "actions": r[2], "actions_max": PLAN_TOOLCALLS.get(plan, 100),
        "has_own_key": r[3],
    }


# ---------------------------------------------------------------------------
# Admin (owner) queries - aggregate stats + management. Read-only unless noted.
# ---------------------------------------------------------------------------
def admin_stats():
    """High-level metrics for the owner dashboard."""
    with _pool.connection() as conn:
        c = conn.execute
        total_users = c("SELECT count(*) FROM users").fetchone()[0]
        verified = c("SELECT count(*) FROM users WHERE email_verified").fetchone()[0]
        paid = c("SELECT count(*) FROM users WHERE plan <> 'free'").fetchone()[0]
        new_7d = c("SELECT count(*) FROM users WHERE created_at > now() - interval '7 days'").fetchone()[0]
        sites = c("SELECT count(*) FROM wordpress_sites WHERE status='active'").fetchone()[0]
        # revenue - kept PER CURRENCY (INR and USD are different money; never summed).
        def _rev(where):
            row = c("SELECT "
                    "coalesce(sum(amount_usd) FILTER (WHERE currency='INR'),0), "
                    "coalesce(sum(amount_usd) FILTER (WHERE currency='USD'),0) "
                    f"FROM transactions WHERE status='completed'{where}").fetchone()
            return float(row[0]), float(row[1])
        rev_inr, rev_usd = _rev("")
        rev30_inr, rev30_usd = _rev(" AND created_at > now() - interval '30 days'")
        txns = c("SELECT count(*) FROM transactions WHERE status='completed'").fetchone()[0]
        # usage
        img_30d = c("SELECT count(*) FROM usage_logs WHERE kind='image' AND created_at > now() - interval '30 days'").fetchone()[0]
        actions_30d = c("SELECT count(*) FROM usage_logs WHERE created_at > now() - interval '30 days'").fetchone()[0]
        # plan breakdown
        plan_rows = c("SELECT plan, count(*) FROM users GROUP BY plan ORDER BY count(*) DESC").fetchall()
    return {
        "total_users": total_users, "verified": verified, "paid": paid, "new_7d": new_7d,
        "sites": sites, "txns": txns,
        "rev_inr": rev_inr, "rev_usd": rev_usd,
        "rev30_inr": rev30_inr, "rev30_usd": rev30_usd,
        # back-compat: rev_total/rev_30d kept as the INR figure only (never a mixed sum).
        "rev_total": rev_inr, "rev_30d": rev30_inr,
        "img_30d": img_30d, "actions_30d": actions_30d,
        "plans": [(p, n) for p, n in plan_rows],
    }


def admin_list_users(search: str = "", limit: int = 200):
    """All users with plan, sites and last activity for the users table."""
    where, params = "", []
    if search:
        where = "WHERE u.email ILIKE %s"
        params.append(f"%{search}%")
    params.append(limit)
    with _pool.connection() as conn:
        rows = conn.execute(f"""
            SELECT u.id, u.email, u.plan, u.email_verified, u.created_at,
                   u.credits, u.tool_calls, u.sub_status,
                   (SELECT count(*) FROM wordpress_sites s WHERE s.user_id=u.id AND s.status='active'),
                   (SELECT site_url FROM wordpress_sites s WHERE s.user_id=u.id ORDER BY is_primary DESC, created_at LIMIT 1),
                   (SELECT coalesce(sum(amount_usd),0) FROM transactions t WHERE t.user_id=u.id AND t.status='completed'),
                   (SELECT max(created_at) FROM usage_logs l WHERE l.user_id=u.id),
                   u.status
            FROM users u
            {where}
            ORDER BY u.created_at DESC
            LIMIT %s
        """, params).fetchall()
    return [{
        "id": str(r[0]), "email": r[1], "plan": r[2], "verified": r[3],
        "created_at": str(r[4]), "credits": r[5], "tool_calls": r[6], "sub_status": r[7],
        "sites": r[8], "site_url": r[9], "spent": float(r[10]), "last_active": str(r[11]) if r[11] else None,
        "status": r[12],
    } for r in rows]


def admin_get_user(user_id: str):
    """Full detail for one user (detail page)."""
    with _pool.connection() as conn:
        r = conn.execute("""
            SELECT id, email, plan, email_verified, created_at, credits, tool_calls,
                   ai_tokens, sub_status, sub_provider, sub_renews_at,
                   (gemini_key_enc IS NOT NULL), status, admin_note, banned_at
            FROM users WHERE id=%s""", (user_id,)).fetchone()
        if not r:
            return None
        sites = conn.execute(
            "SELECT site_url, wp_username, status, created_at FROM wordpress_sites "
            "WHERE user_id=%s ORDER BY is_primary DESC, created_at", (user_id,)).fetchall()
        txns = conn.execute(
            "SELECT kind, item, amount_usd, provider, status, created_at, currency FROM transactions "
            "WHERE user_id=%s ORDER BY created_at DESC LIMIT 25", (user_id,)).fetchall()
        img30 = conn.execute("SELECT count(*) FROM usage_logs WHERE user_id=%s AND kind='image' AND created_at > now() - interval '30 days'", (user_id,)).fetchone()[0]
        act30 = conn.execute("SELECT count(*) FROM usage_logs WHERE user_id=%s AND created_at > now() - interval '30 days'", (user_id,)).fetchone()[0]
    return {
        "id": str(r[0]), "email": r[1], "plan": r[2], "verified": r[3], "created_at": str(r[4]),
        "credits": r[5], "tool_calls": r[6], "ai_tokens": r[7], "sub_status": r[8],
        "sub_provider": r[9], "sub_renews_at": str(r[10]) if r[10] else None, "byok": r[11],
        "status": r[12], "admin_note": r[13], "banned_at": str(r[14]) if r[14] else None,
        "sites": [{"url": s[0], "user": s[1], "status": s[2], "created_at": str(s[3])} for s in sites],
        "txns": [{"kind": t[0], "item": t[1], "amount": float(t[2]), "provider": t[3],
                  "status": t[4], "created_at": str(t[5]), "currency": t[6]} for t in txns],
        "img_30d": img30, "actions_30d": act30,
    }


def admin_recent_transactions(limit: int = 100):
    """All recent payments across users (payments page)."""
    with _pool.connection() as conn:
        rows = conn.execute("""
            SELECT t.created_at, u.email, t.kind, t.item, t.amount_usd, t.provider, t.status, u.id, t.currency, t.invoice_no
            FROM transactions t JOIN users u ON u.id=t.user_id
            ORDER BY t.created_at DESC LIMIT %s""", (limit,)).fetchall()
    return [{"created_at": str(r[0]), "email": r[1], "kind": r[2], "item": r[3],
             "amount": float(r[4]), "provider": r[5], "status": r[6], "user_id": str(r[7]),
             "currency": r[8], "invoice_no": r[9] or ""} for r in rows]


def admin_top_tools(limit: int = 15):
    """Most-used actions in the last 30 days (usage page)."""
    with _pool.connection() as conn:
        rows = conn.execute("""
            SELECT kind, count(*) FROM usage_logs
            WHERE created_at > now() - interval '30 days'
            GROUP BY kind ORDER BY count(*) DESC LIMIT %s""", (limit,)).fetchall()
    return [(r[0], r[1]) for r in rows]


def admin_delete_user(user_id: str):
    """Delete a user and all their data (cascades to sites/txns/usage)."""
    with _pool.connection() as conn:
        conn.execute("DELETE FROM users WHERE id=%s", (user_id,))


# --- Admin: per-user edits ---------------------------------------------------
def admin_set_verified(user_id: str, verified: bool):
    with _pool.connection() as conn:
        conn.execute("UPDATE users SET email_verified=%s WHERE id=%s", (verified, user_id))


def admin_set_email(user_id: str, email: str):
    with _pool.connection() as conn:
        conn.execute("UPDATE users SET email=%s WHERE id=%s", (email.strip().lower(), user_id))


def admin_set_credits(user_id: str, count: int):
    """Set image credits to an absolute value."""
    with _pool.connection() as conn:
        conn.execute("UPDATE users SET credits=%s WHERE id=%s", (max(0, count), user_id))


def admin_set_toolcalls(user_id: str, count: int):
    """Set AI-action balance to an absolute value."""
    with _pool.connection() as conn:
        this_month = conn.execute("SELECT to_char(now(),'YYYY-MM')").fetchone()[0]
        conn.execute("UPDATE users SET tool_calls=%s, tool_calls_month=%s WHERE id=%s",
                     (max(0, count), this_month, user_id))


def admin_set_tokens(user_id: str, count: int):
    """Set chat-token balance to an absolute value."""
    with _pool.connection() as conn:
        conn.execute("UPDATE users SET ai_tokens=%s WHERE id=%s", (max(0, count), user_id))


def admin_disconnect_sites(user_id: str) -> int:
    """Remove all WordPress sites for a user (revokes AI access)."""
    with _pool.connection() as conn:
        cur = conn.execute("DELETE FROM wordpress_sites WHERE user_id=%s", (user_id,))
        return cur.rowcount


def admin_user_activity(user_id: str, limit: int = 60):
    """Full activity log (usage_logs) for one user."""
    with _pool.connection() as conn:
        rows = conn.execute(
            "SELECT kind, created_at FROM usage_logs WHERE user_id=%s "
            "ORDER BY created_at DESC LIMIT %s", (user_id, limit)).fetchall()
    return [{"kind": r[0], "created_at": str(r[1])} for r in rows]


def admin_all_user_txns(user_id: str):
    """Every transaction for a user, with row id (for refund)."""
    with _pool.connection() as conn:
        rows = conn.execute(
            "SELECT id, kind, item, amount_usd, provider, status, ext_id, created_at, currency "
            "FROM transactions WHERE user_id=%s ORDER BY created_at DESC", (user_id,)).fetchall()
    return [{"id": r[0], "kind": r[1], "item": r[2], "amount": float(r[3]), "provider": r[4],
             "status": r[5], "ext_id": r[6], "created_at": str(r[7]), "currency": r[8]} for r in rows]


def admin_set_txn_status(txn_id: int, status: str):
    """Mark a transaction refunded/failed/completed."""
    with _pool.connection() as conn:
        conn.execute("UPDATE transactions SET status=%s WHERE id=%s", (status, txn_id))


# Image-credit pack item -> credit count (for refund claw-back). Matches razorpay_pay.
_CREDIT_PACK_COUNTS = {"img_100": 100, "img_300": 300, "img_500": 500}


def admin_refund_transaction(txn_id: int, downgrade=True):
    """Refund a transaction AND reverse its side effects precisely:
      - affiliate commission is reversed ONLY if THIS transaction is the one that converted
        the referral (matched by ext_id), and only if it hasn't already been paid out;
      - credit-pack refunds claw back the granted image credits;
      - plan refunds downgrade the user to Free and disconnect over-limit sites.
    Returns a short summary string."""
    with _pool.connection() as conn:
        row = conn.execute(
            "SELECT user_id, kind, item, status, ext_id FROM transactions WHERE id=%s",
            (txn_id,)).fetchone()
        if not row:
            return "Transaction not found."
        uid, kind, item, cur_status, ext_id = str(row[0]), row[1], row[2], row[3], (row[4] or "")
        if cur_status == "refunded":
            return "Already refunded."
        conn.execute("UPDATE transactions SET status='refunded' WHERE id=%s", (txn_id,))
        notes = []

        # 1) Affiliate commission: reverse ONLY the referral this exact payment converted.
        if ext_id:
            ref = conn.execute(
                "SELECT referrer_id, commission, currency FROM referrals "
                "WHERE referred_id=%s AND status='converted' AND convert_ext_id=%s",
                (uid, ext_id)).fetchone()
            if ref:
                referrer_id, commission, rcur = str(ref[0]), float(ref[1]), ref[2]
                # Has the referrer already been PAID a payout covering this? If so, don't
                # silently zero it (that would leave an unrecoverable overpayment); flag it.
                paid = conn.execute(
                    "SELECT coalesce(sum(amount),0) FROM payout_requests "
                    "WHERE user_id=%s AND currency=%s AND status='paid'",
                    (referrer_id, rcur)).fetchone()[0]
                earned = conn.execute(
                    "SELECT coalesce(sum(commission),0) FROM referrals "
                    "WHERE referrer_id=%s AND status='converted' AND currency=%s",
                    (referrer_id, rcur)).fetchone()[0]
                if float(paid) > float(earned) - commission:
                    # Reversing would push them negative (already paid out). Mark as
                    # 'clawback' so the admin can see and recover it, don't just hide it.
                    conn.execute(
                        "UPDATE referrals SET status='clawback' "
                        "WHERE referred_id=%s AND status='converted' AND convert_ext_id=%s",
                        (uid, ext_id))
                    notes.append("commission flagged for clawback (already paid out)")
                else:
                    conn.execute(
                        "UPDATE referrals SET status='reversed', commission=0, sale_amount=0 "
                        "WHERE referred_id=%s AND status='converted' AND convert_ext_id=%s",
                        (uid, ext_id))
                    notes.append("affiliate commission reversed")

        # 2) Credit-pack refund: claw back the image credits that were granted.
        if kind == "credit_pack":
            packs = {**{k: v for k, v in _CREDIT_PACK_COUNTS.items()}}
            count = packs.get(item, 0)
            if count:
                conn.execute("UPDATE users SET credits = GREATEST(0, credits - %s) WHERE id=%s",
                             (count, uid))
                notes.append(f"{count} image credits removed")

        # 3) Plan refund: downgrade to Free + end subscription + disconnect over-limit sites.
        if kind == "plan" and downgrade:
            conn.execute("UPDATE users SET plan='free', sub_status='canceled' WHERE id=%s", (uid,))
            notes.append("plan downgraded to Free")
            # Free allows 1 site; deactivate any beyond the newest primary so a downgraded
            # user can't keep using sites their (now Free) plan doesn't include.
            conn.execute("""
                UPDATE wordpress_sites SET status='inactive'
                WHERE user_id=%s AND status='active' AND id NOT IN (
                    SELECT id FROM wordpress_sites WHERE user_id=%s AND status='active'
                    ORDER BY is_primary DESC, created_at LIMIT 1)
            """, (uid, uid))
            notes.append("over-limit sites disconnected")
    return "Refunded" + (" (" + ", ".join(notes) + ")" if notes else "") + "."


# --- Admin: list filtering + CSV ---------------------------------------------
def admin_users_filtered(search="", plan="", verified="", paid_only=False,
                         sort="created_at", desc=True, limit=500):
    conds, params = [], []
    if search:
        conds.append("u.email ILIKE %s"); params.append(f"%{search}%")
    if plan:
        conds.append("u.plan = %s"); params.append(plan)
    if verified == "yes":
        conds.append("u.email_verified = true")
    elif verified == "no":
        conds.append("u.email_verified = false")
    if paid_only:
        conds.append("u.plan <> 'free'")
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    sort_col = {"created_at": "u.created_at", "email": "u.email", "plan": "u.plan",
                "spent": "spent"}.get(sort, "u.created_at")
    direction = "DESC" if desc else "ASC"
    params.append(limit)
    with _pool.connection() as conn:
        rows = conn.execute(f"""
            SELECT u.id, u.email, u.plan, u.email_verified, u.created_at,
                   u.credits, u.tool_calls, u.sub_status,
                   (SELECT count(*) FROM wordpress_sites s WHERE s.user_id=u.id AND s.status='active'),
                   (SELECT site_url FROM wordpress_sites s WHERE s.user_id=u.id ORDER BY is_primary DESC, created_at LIMIT 1),
                   (SELECT coalesce(sum(amount_usd) FILTER (WHERE currency='INR'),0) FROM transactions t WHERE t.user_id=u.id AND t.status='completed') AS spent,
                   (SELECT max(created_at) FROM usage_logs l WHERE l.user_id=u.id),
                   u.status,
                   (SELECT coalesce(sum(amount_usd) FILTER (WHERE currency='USD'),0) FROM transactions t WHERE t.user_id=u.id AND t.status='completed') AS spent_usd
            FROM users u {where}
            ORDER BY {sort_col} {direction} LIMIT %s
        """, params).fetchall()
    return [{
        "id": str(r[0]), "email": r[1], "plan": r[2], "verified": r[3], "created_at": str(r[4]),
        "credits": r[5], "tool_calls": r[6], "sub_status": r[7], "sites": r[8],
        "site_url": r[9], "spent": float(r[10]), "last_active": str(r[11]) if r[11] else None,
        "status": r[12], "spent_usd": float(r[13]),
    } for r in rows]


def admin_plan_options():
    """Distinct plans present, for the filter dropdown."""
    with _pool.connection() as conn:
        rows = conn.execute("SELECT DISTINCT plan FROM users ORDER BY plan").fetchall()
    return [r[0] for r in rows]


# --- Admin: charts -----------------------------------------------------------
def admin_signups_daily(days: int = 30):
    with _pool.connection() as conn:
        rows = conn.execute("""
            SELECT to_char(d::date,'MM-DD') AS day,
                   (SELECT count(*) FROM users u WHERE u.created_at::date = d::date)
            FROM generate_series(now()::date - (%s - 1) * interval '1 day', now()::date, interval '1 day') d
            ORDER BY d
        """, (days,)).fetchall()
    return [(r[0], r[1]) for r in rows]


def admin_revenue_daily(days: int = 30):
    with _pool.connection() as conn:
        rows = conn.execute("""
            SELECT to_char(d::date,'MM-DD') AS day,
                   (SELECT coalesce(sum(amount_usd),0) FROM transactions t
                    WHERE t.status='completed' AND t.created_at::date = d::date)
            FROM generate_series(now()::date - (%s - 1) * interval '1 day', now()::date, interval '1 day') d
            ORDER BY d
        """, (days,)).fetchall()
    return [(r[0], float(r[1])) for r in rows]


# --- Admin: system health ----------------------------------------------------
def admin_db_ok():
    try:
        with _pool.connection() as conn:
            conn.execute("SELECT 1").fetchone()
        return True
    except Exception:
        return False


# --- Admin: ban / suspend / note / relative credit ops -----------------------
def admin_set_status(user_id: str, status: str):
    """status: 'active' or 'banned'. Banned users can't log in or use the AI."""
    with _pool.connection() as conn:
        if status == "banned":
            # Bump session_ver too so the ban kills any active cookie session immediately.
            conn.execute("UPDATE users SET status='banned', banned_at=now(), "
                         "session_ver = session_ver + 1 WHERE id=%s", (user_id,))
        else:
            conn.execute("UPDATE users SET status='active', banned_at=NULL WHERE id=%s", (user_id,))


def is_banned(user_id: str) -> bool:
    if not user_id:
        return False
    with _pool.connection() as conn:
        r = conn.execute("SELECT status FROM users WHERE id=%s", (user_id,)).fetchone()
    return bool(r and r[0] == "banned")


def admin_set_note(user_id: str, note: str):
    with _pool.connection() as conn:
        conn.execute("UPDATE users SET admin_note=%s WHERE id=%s", (note[:2000], user_id))


def admin_adjust_credits(user_id: str, delta: int):
    """Add or subtract image credits (clamped at 0)."""
    with _pool.connection() as conn:
        conn.execute("UPDATE users SET credits = GREATEST(0, credits + %s) WHERE id=%s", (delta, user_id))


def admin_adjust_toolcalls(user_id: str, delta: int):
    """Add or subtract AI actions (clamped at 0)."""
    with _pool.connection() as conn:
        this_month = conn.execute("SELECT to_char(now(),'YYYY-MM')").fetchone()[0]
        conn.execute("UPDATE users SET tool_calls = GREATEST(0, tool_calls + %s), "
                     "tool_calls_month=%s WHERE id=%s", (delta, this_month, user_id))


def admin_bulk(user_ids: list, action: str, value: str = ""):
    """Apply an action to many users at once. action: ban|unban|delete|plan."""
    if not user_ids:
        return 0
    ids = [u for u in user_ids if u]
    if not ids:
        return 0
    with _pool.connection() as conn:
        ph = ",".join(["%s"] * len(ids))
        if action == "ban":
            conn.execute(f"UPDATE users SET status='banned', banned_at=now() WHERE id IN ({ph})", ids)
        elif action == "unban":
            conn.execute(f"UPDATE users SET status='active', banned_at=NULL WHERE id IN ({ph})", ids)
        elif action == "delete":
            conn.execute(f"DELETE FROM users WHERE id IN ({ph})", ids)
        elif action == "plan" and value:
            imgs = PLAN_CREDITS.get(value, 5)
            toks = PLAN_TOKENS.get(value, PLAN_TOKENS["free"])
            calls = PLAN_TOOLCALLS.get(value, 100)
            month = conn.execute("SELECT to_char(now(),'YYYY-MM')").fetchone()[0]
            conn.execute(
                f"UPDATE users SET plan=%s, credits=%s, credits_month=%s, ai_tokens=%s, "
                f"ai_tokens_month=%s, tool_calls=%s, tool_calls_month=%s WHERE id IN ({ph})",
                [value, imgs, month, toks, month, calls, month] + ids)
    return len(ids)


# --- Admin: Usage analytics --------------------------------------------------
def admin_usage_stats(days: int = 30):
    """Rich usage metrics for the Usage page over the given window."""
    with _pool.connection() as conn:
        c = conn.execute
        iv = f"{int(days)} days"
        actions = c(f"SELECT count(*) FROM usage_logs WHERE created_at > now() - interval '{iv}'").fetchone()[0]
        images = c(f"SELECT count(*) FROM usage_logs WHERE kind='image' AND created_at > now() - interval '{iv}'").fetchone()[0]
        chats = c(f"SELECT count(*) FROM usage_logs WHERE kind='chat' AND created_at > now() - interval '{iv}'").fetchone()[0]
        today = c("SELECT count(*) FROM usage_logs WHERE created_at::date = now()::date").fetchone()[0]
        active = c(f"SELECT count(DISTINCT user_id) FROM usage_logs WHERE created_at > now() - interval '{iv}'").fetchone()[0]
        total_users = c("SELECT count(*) FROM users").fetchone()[0]
        sites = c("SELECT count(*) FROM wordpress_sites WHERE status='active'").fetchone()[0]
        # peak day
        peak = c(f"""SELECT to_char(created_at::date,'Mon DD'), count(*) FROM usage_logs
                     WHERE created_at > now() - interval '{iv}'
                     GROUP BY created_at::date ORDER BY count(*) DESC LIMIT 1""").fetchone()
    avg_per_active = round(actions / active, 1) if active else 0
    avg_per_day = round(actions / days, 1) if days else 0
    return {
        "days": days, "actions": actions, "images": images, "chats": chats, "today": today,
        "active_users": active, "total_users": total_users, "sites": sites,
        "avg_per_active": avg_per_active, "avg_per_day": avg_per_day,
        "peak_day": (peak[0] if peak else "-"), "peak_count": (peak[1] if peak else 0),
    }


def admin_actions_daily(days: int = 30):
    """Daily action counts (all kinds) for the trend chart."""
    with _pool.connection() as conn:
        rows = conn.execute("""
            SELECT to_char(d::date,'MM-DD'),
                   (SELECT count(*) FROM usage_logs l WHERE l.created_at::date = d::date)
            FROM generate_series(now()::date - (%s - 1) * interval '1 day', now()::date, interval '1 day') d
            ORDER BY d
        """, (days,)).fetchall()
    return [(r[0], r[1]) for r in rows]


def admin_images_daily(days: int = 30):
    with _pool.connection() as conn:
        rows = conn.execute("""
            SELECT to_char(d::date,'MM-DD'),
                   (SELECT count(*) FROM usage_logs l WHERE l.kind='image' AND l.created_at::date = d::date)
            FROM generate_series(now()::date - (%s - 1) * interval '1 day', now()::date, interval '1 day') d
            ORDER BY d
        """, (days,)).fetchall()
    return [(r[0], r[1]) for r in rows]


def admin_top_tools_window(days: int = 30, limit: int = 25):
    """Most-used action kinds in the window, with each kind's count."""
    with _pool.connection() as conn:
        rows = conn.execute(f"""
            SELECT kind, count(*) FROM usage_logs
            WHERE created_at > now() - interval '{int(days)} days'
            GROUP BY kind ORDER BY count(*) DESC LIMIT %s""", (limit,)).fetchall()
    return [(r[0], r[1]) for r in rows]


def admin_top_users_by_usage(days: int = 30, limit: int = 10):
    """Power users - most AI actions in the window."""
    with _pool.connection() as conn:
        rows = conn.execute(f"""
            SELECT u.id, u.email, u.plan, count(l.*) AS n
            FROM usage_logs l JOIN users u ON u.id = l.user_id
            WHERE l.created_at > now() - interval '{int(days)} days'
            GROUP BY u.id, u.email, u.plan
            ORDER BY n DESC LIMIT %s""", (limit,)).fetchall()
    return [{"id": str(r[0]), "email": r[1], "plan": r[2], "count": r[3]} for r in rows]


def admin_inactive_users(days: int = 30, limit: int = 15):
    """Users who signed up but did NOTHING in the window (churn risk)."""
    with _pool.connection() as conn:
        rows = conn.execute(f"""
            SELECT u.id, u.email, u.plan, u.created_at
            FROM users u
            WHERE NOT EXISTS (
                SELECT 1 FROM usage_logs l WHERE l.user_id = u.id
                AND l.created_at > now() - interval '{int(days)} days')
            ORDER BY u.created_at DESC LIMIT %s""", (limit,)).fetchall()
    return [{"id": str(r[0]), "email": r[1], "plan": r[2], "created_at": str(r[3])} for r in rows]


def get_usage_summary(user_id: str):
    """For the user's Plan page: renewal date + this-month usage breakdown."""
    with _pool.connection() as conn:
        r = conn.execute(
            "SELECT sub_status, sub_renews_at, created_at, "
            "  CASE WHEN sub_renews_at IS NULL THEN NULL "
            "       ELSE CEIL(EXTRACT(EPOCH FROM (sub_renews_at - now())) / 86400.0)::int END "
            "FROM users WHERE id=%s", (user_id,)).fetchone()
        sub_status = r[0] if r else "none"
        renews_at = str(r[1]) if r and r[1] else None
        days_to_expiry = int(r[3]) if r and r[3] is not None else None
        # usage since the start of this calendar month (limits reset on the 1st)
        actions = conn.execute(
            "SELECT count(*) FROM usage_logs WHERE user_id=%s "
            "AND created_at >= date_trunc('month', now())", (user_id,)).fetchone()[0]
        images = conn.execute(
            "SELECT count(*) FROM usage_logs WHERE user_id=%s AND kind='image' "
            "AND created_at >= date_trunc('month', now())", (user_id,)).fetchone()[0]
        # top actions this month (breakdown of what they used)
        top = conn.execute(
            "SELECT kind, count(*) FROM usage_logs WHERE user_id=%s "
            "AND created_at >= date_trunc('month', now()) "
            "GROUP BY kind ORDER BY count(*) DESC LIMIT 12", (user_id,)).fetchall()
        # first day of NEXT month = when the monthly allowance resets
        reset = conn.execute(
            "SELECT to_char(date_trunc('month', now()) + interval '1 month', 'Mon DD, YYYY')"
        ).fetchone()[0]
    return {
        "sub_status": sub_status, "renews_at": renews_at, "resets_on": reset,
        "days_to_expiry": days_to_expiry,
        "actions_used": actions, "images_used": images,
        "top": [(k, n) for k, n in top],
    }


# ---------------------------------------------------------------------------
# Discount coupons
# ---------------------------------------------------------------------------
def create_coupon(code, kind, value, currency="ANY", max_uses=0, expires_at=None, note=""):
    """Create/replace a coupon. code is uppercased. Returns (ok, error)."""
    code = (code or "").strip().upper()
    if not code or len(code) > 40:
        return False, "Enter a code (max 40 chars)."
    # Restrict to safe, path-friendly characters. This also stops a code containing '/'
    # or spaces from breaking the admin toggle/delete routes (which route on the path).
    if not re.match(r"^[A-Z0-9_-]+$", code):
        return False, "Code can only contain letters, numbers, dashes and underscores."
    if kind not in ("percent", "flat"):
        return False, "Invalid discount type."
    try:
        value = float(value)
    except (TypeError, ValueError):
        return False, "Enter a valid discount value."
    if value <= 0 or (kind == "percent" and value > 100):
        return False, "Percent must be 1-100; flat must be > 0."
    currency = currency if currency in ("ANY", "INR", "USD") else "ANY"
    with _pool.connection() as conn:
        conn.execute("""
            INSERT INTO coupons (code, kind, value, currency, max_uses, expires_at, note, active)
            VALUES (%s,%s,%s,%s,%s,%s,%s,true)
            ON CONFLICT (code) DO UPDATE SET
              kind=EXCLUDED.kind, value=EXCLUDED.value, currency=EXCLUDED.currency,
              max_uses=EXCLUDED.max_uses, expires_at=EXCLUDED.expires_at, note=EXCLUDED.note
        """, (code, kind, value, currency, int(max_uses or 0), expires_at, note[:200]))
    return True, ""


def list_coupons():
    with _pool.connection() as conn:
        rows = conn.execute("""
            SELECT code, kind, value, currency, max_uses, used_count, expires_at, active, note, created_at
            FROM coupons ORDER BY created_at DESC""").fetchall()
    return [{
        "code": r[0], "kind": r[1], "value": float(r[2]), "currency": r[3],
        "max_uses": r[4], "used_count": r[5], "expires_at": str(r[6]) if r[6] else None,
        "active": r[7], "note": r[8], "created_at": str(r[9]),
    } for r in rows]


def set_coupon_active(code, active):
    with _pool.connection() as conn:
        conn.execute("UPDATE coupons SET active=%s WHERE code=%s", (bool(active), code.upper()))


def delete_coupon(code):
    with _pool.connection() as conn:
        conn.execute("DELETE FROM coupons WHERE code=%s", (code.upper(),))


def validate_coupon(code, currency="INR"):
    """Check a coupon for a checkout. Returns (coupon_dict|None, error_str).
    Does NOT redeem - call redeem_coupon after a successful payment."""
    code = (code or "").strip().upper()
    if not code:
        return None, "No code entered."
    with _pool.connection() as conn:
        r = conn.execute("""
            SELECT code, kind, value, currency, max_uses, used_count, expires_at, active
            FROM coupons WHERE code=%s""", (code,)).fetchone()
    if not r:
        return None, "Invalid coupon code."
    c = {"code": r[0], "kind": r[1], "value": float(r[2]), "currency": r[3],
         "max_uses": r[4], "used_count": r[5], "expires_at": r[6], "active": r[7]}
    if not c["active"]:
        return None, "This coupon is no longer active."
    if c["expires_at"] is not None:
        with _pool.connection() as conn:
            expired = conn.execute("SELECT %s < now()", (c["expires_at"],)).fetchone()[0]
        if expired:
            return None, "This coupon has expired."
    if c["max_uses"] and c["used_count"] >= c["max_uses"]:
        return None, "This coupon has reached its usage limit."
    # Currency restriction applies to ALL coupon kinds (a flat amount is obviously
    # currency-specific, but a percent coupon scoped to INR must not apply to USD carts).
    if c["currency"] not in ("ANY", "", None) and c["currency"] != currency:
        return None, f"This coupon only works with {c['currency']} pricing."
    return c, ""


def apply_coupon_amount(coupon, amount, currency="INR"):
    """Return the discounted amount (>= 0) given a validated coupon and base amount."""
    if not coupon:
        return amount
    if coupon["kind"] == "percent":
        return round(amount * (1 - coupon["value"] / 100.0), 2)
    # flat
    return max(0, round(amount - coupon["value"], 2))


def redeem_coupon(code, user_id=None, plan=""):
    """Record a redemption + bump the counter (after a successful payment). The counter
    bump is ATOMIC and re-checks the usage cap in the same statement, so concurrent
    checkouts can't push used_count past max_uses (max_uses=0 means unlimited)."""
    code = (code or "").strip().upper()
    if not code:
        return
    with _pool.connection() as conn:
        row = conn.execute(
            "UPDATE coupons SET used_count = used_count + 1 "
            "WHERE code=%s AND (max_uses = 0 OR used_count < max_uses) "
            "RETURNING used_count", (code,)).fetchone()
        # Only record the redemption if the atomic bump actually happened (within cap).
        if row is not None:
            conn.execute("INSERT INTO coupon_redemptions (code, user_id, plan) VALUES (%s,%s,%s)",
                         (code, user_id, plan))


# ---------------------------------------------------------------------------
# Admin-editable app settings (plan config + email templates)
# ---------------------------------------------------------------------------
def get_setting(key, default=None):
    with _pool.connection() as conn:
        r = conn.execute("SELECT value FROM app_settings WHERE key=%s", (key,)).fetchone()
    return r[0] if r else default


def set_setting(key, value):
    with _pool.connection() as conn:
        conn.execute("""
            INSERT INTO app_settings (key, value, updated_at) VALUES (%s,%s,now())
            ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, updated_at=now()
        """, (key, json.dumps(value)))


# --- Social links (admin-managed, shown in the site footer) ------------------
# The set of platforms the admin can fill in. Order here = order shown in the footer.
SOCIAL_PLATFORMS = [
    ("facebook",  "Facebook"),
    ("instagram", "Instagram"),
    ("youtube",   "YouTube"),
    ("pinterest", "Pinterest"),
    ("linkedin",  "LinkedIn"),
    ("reddit",    "Reddit"),
    ("twitter",   "X (Twitter)"),
    ("tiktok",    "TikTok"),
    ("threads",   "Threads"),
    ("github",    "GitHub"),
]


def list_published_blog_slugs():
    """Published blog articles for sitemap.xml + llms.txt. Combines the built-in posts
    (blog_posts.py) with admin-created DB posts; returns [] on any error."""
    out = []
    try:
        import blog_posts
        out += [{"slug": p["slug"], "updated": p.get("date", ""),
                 "title": p.get("title", ""), "description": p.get("description", "")}
                for p in blog_posts.all_posts()]
    except Exception:
        pass
    try:
        for p in blog_db_list(published_only=True):
            out.append({"slug": p["slug"], "updated": str(p["updated_at"])[:10],
                        "title": p["title"], "description": p["description"]})
    except Exception:
        pass
    return out


# --- admin-managed blog posts (DB) ---
def blog_db_list(published_only=False):
    where = "WHERE published" if published_only else ""
    with _pool.connection() as conn:
        rows = conn.execute(f"""
            SELECT id, slug, title, description, keywords, hero, read_time, body_html,
                   published, created_at, updated_at
            FROM blog_posts_db {where} ORDER BY created_at DESC
        """).fetchall()
    return [{"id": r[0], "slug": r[1], "title": r[2], "description": r[3], "keywords": r[4],
             "hero": r[5], "read_time": r[6], "body_html": r[7], "published": r[8],
             "created_at": str(r[9]), "updated_at": str(r[10])} for r in rows]


def blog_db_get(slug):
    with _pool.connection() as conn:
        r = conn.execute("""
            SELECT id, slug, title, description, keywords, hero, read_time, body_html,
                   published, created_at, updated_at
            FROM blog_posts_db WHERE slug=%s
        """, (slug,)).fetchone()
    if not r:
        return None
    return {"id": r[0], "slug": r[1], "title": r[2], "description": r[3], "keywords": r[4],
            "hero": r[5], "read_time": r[6], "body_html": r[7], "published": r[8],
            "created_at": str(r[9]), "updated_at": str(r[10])}


def blog_db_upsert(slug, title, description="", keywords="", hero="hero-blog.webp",
                   read_time="5 min read", body_html="", published=True, old_slug=None):
    """Create or update a blog post. If old_slug is given (editing), update that row and
    change its slug. Returns (ok, error)."""
    slug = _slugify(slug or title)
    title = (title or "").strip()
    if not title:
        return False, "Title is required."
    if not (body_html or "").strip():
        return False, "Body is required."
    with _pool.connection() as conn:
        try:
            if old_slug:
                cur = conn.execute("""
                    UPDATE blog_posts_db SET slug=%s, title=%s, description=%s, keywords=%s,
                      hero=%s, read_time=%s, body_html=%s, published=%s, updated_at=now()
                    WHERE slug=%s
                """, (slug, title, description, keywords, hero, read_time, body_html,
                      published, old_slug))
                # If the old_slug matched no row (already renamed/deleted), don't lose the
                # edit: fall through to an insert/upsert so the post is still saved.
                if cur.rowcount == 0:
                    old_slug = None
            if not old_slug:
                conn.execute("""
                    INSERT INTO blog_posts_db (slug, title, description, keywords, hero,
                      read_time, body_html, published)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (slug) DO UPDATE SET
                      title=EXCLUDED.title, description=EXCLUDED.description,
                      keywords=EXCLUDED.keywords, hero=EXCLUDED.hero,
                      read_time=EXCLUDED.read_time, body_html=EXCLUDED.body_html,
                      published=EXCLUDED.published, updated_at=now()
                """, (slug, title, description, keywords, hero, read_time, body_html, published))
        except Exception as e:  # noqa: BLE001
            return False, f"Could not save: {str(e)[:120]}"
    return True, slug


def blog_db_delete(slug):
    with _pool.connection() as conn:
        conn.execute("DELETE FROM blog_posts_db WHERE slug=%s", (slug,))


def get_social_links():
    """Return {platform_key: url} for every platform the admin has filled in (non-empty).
    Empty dict if none set yet."""
    raw = get_setting("social_links") or {}
    if not isinstance(raw, dict):
        return {}
    keys = {k for k, _ in SOCIAL_PLATFORMS}
    return {k: str(v).strip() for k, v in raw.items() if k in keys and str(v).strip()}


def save_social_links(links: dict):
    """Persist the admin's social links. Only known platforms with a non-empty value are
    kept; each URL is lightly normalized (adds https:// if a bare domain is entered).
    A single '#' is allowed as a deliberate placeholder."""
    keys = {k for k, _ in SOCIAL_PLATFORMS}
    clean = {}
    for k, v in (links or {}).items():
        if k not in keys:
            continue
        v = str(v or "").strip()
        if not v:
            continue
        if v != "#" and not v.startswith(("http://", "https://")):
            v = "https://" + v
        clean[k] = v
    set_setting("social_links", clean)
    return clean


# --- Analytics & Search Console (admin-managed, injected into every page <head>) ----
def get_analytics():
    """Return {ga_id, gsc_verify, head_extra} for the site <head>.
    ga_id: a GA4 Measurement ID (G-XXXXXXX) - loads the gtag.js snippet.
    gsc_verify: the value of a google-site-verification meta tag (or the full tag).
    head_extra: any raw verification/analytics tags to inject verbatim (Bing, Ahrefs, etc.)."""
    raw = get_setting("analytics") or {}
    if not isinstance(raw, dict):
        return {"ga_id": "", "gsc_verify": "", "head_extra": ""}
    return {
        "ga_id": str(raw.get("ga_id", "")).strip(),
        "gsc_verify": str(raw.get("gsc_verify", "")).strip(),
        "head_extra": str(raw.get("head_extra", "")).strip(),
    }


def save_analytics(ga_id="", gsc_verify="", head_extra=""):
    """Persist analytics settings. GA id is validated to the G-XXXX form; the Search
    Console value accepts either the bare token or the full meta tag (we extract it)."""
    ga_id = (ga_id or "").strip()
    if ga_id and not re.match(r"^(G|UA|GT|AW)-[A-Za-z0-9-]+$", ga_id):
        # not a recognizable id -> store empty rather than break the tag
        ga_id = ""
    gsc = (gsc_verify or "").strip()
    # If the admin pasted the whole <meta ...> tag, pull out just the content value.
    m = re.search(r'content=["\']([^"\']+)["\']', gsc)
    if m:
        gsc = m.group(1).strip()
    val = {"ga_id": ga_id, "gsc_verify": gsc, "head_extra": (head_extra or "").strip()}
    set_setting("analytics", val)
    return val


# ---------------------------------------------------------------------------
# Community forum queries
# ---------------------------------------------------------------------------
def _slugify(text: str, maxlen: int = 60) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return (s[:maxlen].strip("-")) or "thread"


def forum_categories():
    """All categories with thread counts, in display order."""
    with _pool.connection() as conn:
        rows = conn.execute("""
            SELECT c.id, c.slug, c.name, c.description,
                   (SELECT count(*) FROM forum_threads t WHERE t.category_id=c.id),
                   (SELECT max(t.last_at) FROM forum_threads t WHERE t.category_id=c.id)
            FROM forum_categories c ORDER BY c.sort, c.name
        """).fetchall()
    return [{"id": r[0], "slug": r[1], "name": r[2], "description": r[3],
             "threads": r[4], "last_at": str(r[5]) if r[5] else None} for r in rows]


def forum_category(slug):
    with _pool.connection() as conn:
        r = conn.execute("SELECT id, slug, name, description FROM forum_categories WHERE slug=%s",
                         (slug,)).fetchone()
    return {"id": r[0], "slug": r[1], "name": r[2], "description": r[3]} if r else None


def forum_ensure_category(slug, name, description="", sort=0):
    """Create a category if it doesn't exist (used to seed starter categories)."""
    with _pool.connection() as conn:
        conn.execute("""
            INSERT INTO forum_categories (slug, name, description, sort) VALUES (%s,%s,%s,%s)
            ON CONFLICT (slug) DO NOTHING
        """, (slug, name, description, sort))


def forum_threads(category_id=None, limit=50, offset=0):
    """Threads (optionally in one category), pinned first then most recent activity."""
    where = "WHERE t.category_id=%s" if category_id else ""
    params = ([category_id] if category_id else []) + [limit, offset]
    with _pool.connection() as conn:
        rows = conn.execute(f"""
            SELECT t.id, t.title, t.slug, t.pinned, t.locked, t.reply_count, t.last_at,
                   t.created_at, u.email, u.name, c.slug, c.name
            FROM forum_threads t
            JOIN users u ON u.id=t.user_id
            JOIN forum_categories c ON c.id=t.category_id
            {where}
            ORDER BY t.pinned DESC, t.last_at DESC
            LIMIT %s OFFSET %s
        """, params).fetchall()
    out = []
    for r in rows:
        author = (r[9] or "").strip() or (r[8].split("@")[0] if r[8] else "user")
        out.append({"id": r[0], "title": r[1], "slug": r[2], "pinned": r[3], "locked": r[4],
                    "reply_count": r[5], "last_at": str(r[6]), "created_at": str(r[7]),
                    "author": author, "cat_slug": r[10], "cat_name": r[11]})
    return out


def forum_thread(thread_id):
    """One thread with its opening post author, or None."""
    with _pool.connection() as conn:
        r = conn.execute("""
            SELECT t.id, t.title, t.slug, t.body, t.pinned, t.locked, t.reply_count,
                   t.created_at, u.email, u.name, c.id, c.slug, c.name
            FROM forum_threads t
            JOIN users u ON u.id=t.user_id
            JOIN forum_categories c ON c.id=t.category_id
            WHERE t.id=%s
        """, (thread_id,)).fetchone()
    if not r:
        return None
    author = (r[9] or "").strip() or (r[8].split("@")[0] if r[8] else "user")
    return {"id": r[0], "title": r[1], "slug": r[2], "body": r[3], "pinned": r[4],
            "locked": r[5], "reply_count": r[6], "created_at": str(r[7]), "author": author,
            "cat_id": r[10], "cat_slug": r[11], "cat_name": r[12]}


def forum_posts(thread_id):
    """All replies for a thread, oldest first."""
    with _pool.connection() as conn:
        rows = conn.execute("""
            SELECT p.id, p.body, p.created_at, u.email, u.name
            FROM forum_posts p JOIN users u ON u.id=p.user_id
            WHERE p.thread_id=%s ORDER BY p.id
        """, (thread_id,)).fetchall()
    out = []
    for r in rows:
        author = (r[4] or "").strip() or (r[3].split("@")[0] if r[3] else "user")
        out.append({"id": r[0], "body": r[1], "created_at": str(r[2]), "author": author})
    return out


def forum_create_thread(user_id, category_id, title, body):
    """Create a thread. Returns (thread_id, slug) or (None, None) on bad input."""
    title = (title or "").strip()[:160]
    body = (body or "").strip()[:20000]   # cap to prevent storage abuse
    if not title or not body:
        return None, None
    slug = _slugify(title)
    with _pool.connection() as conn:
        r = conn.execute("""
            INSERT INTO forum_threads (category_id, user_id, title, slug, body)
            VALUES (%s,%s,%s,%s,%s) RETURNING id
        """, (category_id, user_id, title, slug, body)).fetchone()
    return r[0], slug


def forum_create_post(user_id, thread_id, body):
    """Add a reply and bump the thread's counters. Returns True, or False if locked/bad."""
    body = (body or "").strip()[:20000]   # cap to prevent storage abuse
    if not body:
        return False
    with _pool.connection() as conn:
        locked = conn.execute("SELECT locked FROM forum_threads WHERE id=%s", (thread_id,)).fetchone()
        if not locked or locked[0]:
            return False
        conn.execute("INSERT INTO forum_posts (thread_id, user_id, body) VALUES (%s,%s,%s)",
                     (thread_id, user_id, body))
        conn.execute("UPDATE forum_threads SET reply_count=reply_count+1, last_at=now() WHERE id=%s",
                     (thread_id,))
    return True


def forum_recent_thread_count(user_id, seconds=60):
    """How many threads this user started in the last N seconds (rate limiting)."""
    with _pool.connection() as conn:
        n = conn.execute("SELECT count(*) FROM forum_threads WHERE user_id=%s "
                         "AND created_at > now() - (%s || ' seconds')::interval",
                         (user_id, seconds)).fetchone()[0]
    return int(n)


def forum_recent_post_count(user_id, seconds=30):
    with _pool.connection() as conn:
        n = conn.execute("SELECT count(*) FROM forum_posts WHERE user_id=%s "
                         "AND created_at > now() - (%s || ' seconds')::interval",
                         (user_id, seconds)).fetchone()[0]
    return int(n)


def forum_all_thread_slugs(limit=1000):
    """For the sitemap: (id, slug, last_at) of every thread."""
    with _pool.connection() as conn:
        rows = conn.execute("SELECT id, slug, last_at FROM forum_threads "
                           "ORDER BY last_at DESC LIMIT %s", (limit,)).fetchall()
    return [{"id": r[0], "slug": r[1], "updated": str(r[2])[:10]} for r in rows]


# --- admin moderation ---
def forum_set_pinned(thread_id, pinned):
    with _pool.connection() as conn:
        conn.execute("UPDATE forum_threads SET pinned=%s WHERE id=%s", (bool(pinned), thread_id))


def forum_set_locked(thread_id, locked):
    with _pool.connection() as conn:
        conn.execute("UPDATE forum_threads SET locked=%s WHERE id=%s", (bool(locked), thread_id))


def forum_delete_thread(thread_id):
    with _pool.connection() as conn:
        conn.execute("DELETE FROM forum_threads WHERE id=%s", (thread_id,))


def forum_delete_post(post_id):
    with _pool.connection() as conn:
        r = conn.execute("SELECT thread_id FROM forum_posts WHERE id=%s", (post_id,)).fetchone()
        if not r:
            return
        conn.execute("DELETE FROM forum_posts WHERE id=%s", (post_id,))
        conn.execute("UPDATE forum_threads SET reply_count=GREATEST(reply_count-1,0) WHERE id=%s",
                     (r[0],))


def forum_stats():
    """Totals for the admin moderation view."""
    with _pool.connection() as conn:
        c = conn.execute
        cats = c("SELECT count(*) FROM forum_categories").fetchone()[0]
        threads = c("SELECT count(*) FROM forum_threads").fetchone()[0]
        posts = c("SELECT count(*) FROM forum_posts").fetchone()[0]
    return {"categories": cats, "threads": threads, "posts": posts}


# ---------------------------------------------------------------------------
# Affiliate / referral program
# ---------------------------------------------------------------------------
DEFAULT_COMMISSION_RATE = 20.0       # percent; admin can override in settings
PAYOUT_MIN_INR = 1000.0
PAYOUT_MIN_USD = 20.0


def get_commission_rate():
    v = get_setting("commission_rate")
    try:
        return float(v) if v is not None else DEFAULT_COMMISSION_RATE
    except (TypeError, ValueError):
        return DEFAULT_COMMISSION_RATE


def set_commission_rate(rate):
    try:
        r = max(0.0, min(90.0, float(rate)))
    except (TypeError, ValueError):
        r = DEFAULT_COMMISSION_RATE
    set_setting("commission_rate", r)
    return r


def get_ref_code(user_id):
    """Return the user's referral code, generating a stable one on first use."""
    with _pool.connection() as conn:
        r = conn.execute("SELECT ref_code, email FROM users WHERE id=%s", (user_id,)).fetchone()
        if not r:
            return None
        if r[0]:
            return r[0]
        # generate from email prefix + short random suffix, ensure uniqueness
        base = re.sub(r"[^a-z0-9]", "", (r[1] or "user").split("@")[0].lower())[:10] or "ref"
        for _ in range(6):
            code = (base + base64.urlsafe_b64encode(os.urandom(4)).decode().rstrip("=")).upper()[:16]
            try:
                conn.execute("UPDATE users SET ref_code=%s WHERE id=%s", (code, user_id))
                return code
            except Exception:
                continue
    return None


def find_user_by_ref_code(code):
    if not code:
        return None
    with _pool.connection() as conn:
        r = conn.execute("SELECT id FROM users WHERE ref_code=%s", ((code or "").strip().upper(),)).fetchone()
    return str(r[0]) if r else None


def attach_referral(referred_id, ref_code):
    """When a NEW user signs up via ?ref=CODE, link them to the referrer (once).
    No self-referral; no double attribution."""
    referrer_id = find_user_by_ref_code(ref_code)
    if not referrer_id or referrer_id == str(referred_id):
        return False
    with _pool.connection() as conn:
        # only if this user isn't already referred
        existing = conn.execute("SELECT referred_by FROM users WHERE id=%s", (referred_id,)).fetchone()
        if not existing or existing[0]:
            return False
        conn.execute("UPDATE users SET referred_by=%s WHERE id=%s", (referrer_id, referred_id))
        conn.execute("INSERT INTO referrals (referrer_id, referred_id, status) "
                     "VALUES (%s,%s,'pending') ON CONFLICT (referred_id) DO NOTHING",
                     (referrer_id, referred_id))
    return True


def convert_referral(referred_id, sale_amount, currency="INR", ext_id=""):
    """Credit the referrer a commission on the referred user's FIRST paid payment.
    Idempotent: only converts a still-pending referral, once. Records the payment id
    (ext_id) that converted it so a later refund of THAT payment can reverse it precisely."""
    try:
        sale_amount = float(sale_amount or 0)
    except (TypeError, ValueError):
        return None
    if sale_amount <= 0:
        return None
    rate = get_commission_rate()
    commission = round(sale_amount * rate / 100.0, 2)
    with _pool.connection() as conn:
        row = conn.execute(
            "UPDATE referrals SET status='converted', sale_amount=%s, commission=%s, rate=%s, "
            "currency=%s, converted_at=now(), convert_ext_id=%s "
            "WHERE referred_id=%s AND status='pending' RETURNING referrer_id",
            (sale_amount, commission, rate, currency, ext_id or "", referred_id)).fetchone()
    return commission if row else None


# ---------------------------------------------------------------------------
# First-month welcome discount (auto, first-time buyers only, abuse-tracked)
# ---------------------------------------------------------------------------
# Percent off the FIRST month, by plan. One-time: the plan renews at full price
# next month (plans already expire in ~31 days, see set_plan valid_days).
WELCOME_DISCOUNT = {
    "owai_starter": 30,
    "owai_pro": 40,
}


def welcome_discount_percent(plan: str) -> int:
    """Return the intro discount % for a plan (0 if that plan has none)."""
    return int(WELCOME_DISCOUNT.get(plan, 0))


def welcome_eligible(user_id: str, fingerprint: str = "", ip: str = "") -> bool:
    """True only if this is a genuine first-time buyer who hasn't used the welcome
    discount before - checked several ways so it can't be double-dipped:
      1. the user came in through an AFFILIATE link (referred_by set) -> NOT eligible.
         The referrer already earns a commission on this sale; stacking the intro discount
         on top would make the sale unprofitable. Affiliate OR discount, never both.
      2. the user has NO prior completed paid plan transaction, AND
      3. no welcome claim exists for this user / this device fingerprint / this IP.
    Any match -> not eligible."""
    fingerprint = (fingerprint or "").strip()[:128]
    ip = (ip or "").strip()[:64]
    with _pool.connection() as conn:
        # 1) referred by an affiliate? then the discount doesn't apply (commission instead).
        ref = conn.execute(
            "SELECT referred_by FROM users WHERE id=%s", (user_id,)).fetchone()
        if ref and ref[0]:
            return False
        # 2) already bought a plan before? then not a first-time buyer.
        paid = conn.execute(
            "SELECT 1 FROM transactions WHERE user_id=%s AND kind='plan' "
            "AND status='completed' LIMIT 1", (user_id,)).fetchone()
        if paid:
            return False
        # 3) has THIS user, or this device, or this IP already claimed a welcome discount?
        row = conn.execute(
            "SELECT 1 FROM welcome_claims WHERE user_id=%s "
            "   OR (fingerprint <> '' AND fingerprint=%s) "
            "   OR (ip <> '' AND ip=%s) LIMIT 1",
            (user_id, fingerprint, ip)).fetchone()
    return row is None


def record_welcome_claim(user_id: str, plan: str, percent: int,
                         fingerprint: str = "", ip: str = ""):
    """Record that a welcome discount was granted, so the same user / device / IP can't
    claim it again. Called only after a real (discounted) checkout is initiated."""
    with _pool.connection() as conn:
        conn.execute(
            "INSERT INTO welcome_claims (user_id, fingerprint, ip, plan, percent) "
            "VALUES (%s,%s,%s,%s,%s)",
            (user_id, (fingerprint or "").strip()[:128], (ip or "").strip()[:64],
             plan, int(percent)))


def affiliate_summary(user_id):
    """Referral link stats + earnings balance for the user's dashboard."""
    with _pool.connection() as conn:
        c = conn.execute
        total_refs = c("SELECT count(*) FROM referrals WHERE referrer_id=%s", (user_id,)).fetchone()[0]
        converted = c("SELECT count(*) FROM referrals WHERE referrer_id=%s AND status='converted'",
                      (user_id,)).fetchone()[0]
        earned_inr = c("SELECT coalesce(sum(commission),0) FROM referrals WHERE referrer_id=%s "
                       "AND status='converted' AND currency='INR'", (user_id,)).fetchone()[0]
        earned_usd = c("SELECT coalesce(sum(commission),0) FROM referrals WHERE referrer_id=%s "
                       "AND status='converted' AND currency='USD'", (user_id,)).fetchone()[0]
        # payouts already requested or paid reduce the available balance
        paid_inr = c("SELECT coalesce(sum(amount),0) FROM payout_requests WHERE user_id=%s "
                     "AND currency='INR' AND status IN ('requested','paid')", (user_id,)).fetchone()[0]
        paid_usd = c("SELECT coalesce(sum(amount),0) FROM payout_requests WHERE user_id=%s "
                     "AND currency='USD' AND status IN ('requested','paid')", (user_id,)).fetchone()[0]
    return {
        "referrals": total_refs, "converted": converted,
        "earned_inr": float(earned_inr), "earned_usd": float(earned_usd),
        "balance_inr": float(earned_inr) - float(paid_inr),
        "balance_usd": float(earned_usd) - float(paid_usd),
    }


def affiliate_referrals(user_id, limit=50):
    with _pool.connection() as conn:
        rows = conn.execute(
            "SELECT r.status, r.commission, r.currency, r.created_at, r.converted_at, u.email "
            "FROM referrals r JOIN users u ON u.id=r.referred_id "
            "WHERE r.referrer_id=%s ORDER BY r.created_at DESC LIMIT %s", (user_id, limit)).fetchall()
    out = []
    for r in rows:
        em = r[5] or ""
        masked = (em[:2] + "***@" + em.split("@")[1]) if "@" in em else "user"
        out.append({"status": r[0], "commission": float(r[1]), "currency": r[2],
                    "created_at": str(r[3]), "converted_at": str(r[4]) if r[4] else None,
                    "email": masked})
    return out


def set_payout_method(user_id, method):
    with _pool.connection() as conn:
        conn.execute("UPDATE users SET payout_method=%s WHERE id=%s", ((method or "")[:300], user_id))


def get_payout_method(user_id):
    with _pool.connection() as conn:
        r = conn.execute("SELECT payout_method FROM users WHERE id=%s", (user_id,)).fetchone()
    return (r[0] if r else "") or ""


def request_payout(user_id, currency="INR"):
    """Create a payout request for the user's full available balance in that currency.
    Returns (ok, message)."""
    s = affiliate_summary(user_id)
    bal = s["balance_inr"] if currency == "INR" else s["balance_usd"]
    minimum = PAYOUT_MIN_INR if currency == "INR" else PAYOUT_MIN_USD
    if bal < minimum:
        sym = "₹" if currency == "INR" else "$"
        return False, f"You need at least {sym}{minimum:,.0f} to request a payout."
    method = get_payout_method(user_id)
    if not method.strip():
        return False, "Add your payout details (UPI / bank / PayPal) first."
    with _pool.connection() as conn:
        # The partial unique index uq_payout_open enforces at most one open request per
        # user+currency, so two concurrent requests can't both insert. Catch the conflict.
        try:
            conn.execute(
                "INSERT INTO payout_requests (user_id, amount, currency, method, status) "
                "VALUES (%s,%s,%s,%s,'requested') "
                "ON CONFLICT (user_id, currency) WHERE status='requested' DO NOTHING",
                (user_id, bal, currency, method[:300]))
            inserted = conn.execute(
                "SELECT 1 FROM payout_requests WHERE user_id=%s AND currency=%s "
                "AND status='requested'", (user_id, currency)).fetchone()
        except Exception:
            return False, "You already have a payout request pending."
    if not inserted:
        return False, "You already have a payout request pending."
    return True, "Payout requested. We'll process it soon."


def payout_history(user_id, limit=20):
    with _pool.connection() as conn:
        rows = conn.execute(
            "SELECT amount, currency, status, created_at, paid_at FROM payout_requests "
            "WHERE user_id=%s ORDER BY created_at DESC LIMIT %s", (user_id, limit)).fetchall()
    return [{"amount": float(r[0]), "currency": r[1], "status": r[2],
             "created_at": str(r[3]), "paid_at": str(r[4]) if r[4] else None} for r in rows]


# --- admin affiliate views ---
def admin_affiliate_stats():
    with _pool.connection() as conn:
        c = conn.execute
        affs = c("SELECT count(*) FROM users WHERE ref_code IS NOT NULL").fetchone()[0]
        refs = c("SELECT count(*) FROM referrals").fetchone()[0]
        conv = c("SELECT count(*) FROM referrals WHERE status='converted'").fetchone()[0]
        owed_inr = c("SELECT coalesce(sum(commission),0) FROM referrals WHERE status='converted' AND currency='INR'").fetchone()[0]
        owed_usd = c("SELECT coalesce(sum(commission),0) FROM referrals WHERE status='converted' AND currency='USD'").fetchone()[0]
        pending_payouts = c("SELECT count(*) FROM payout_requests WHERE status='requested'").fetchone()[0]
    return {"affiliates": affs, "referrals": refs, "converted": conv,
            "owed_inr": float(owed_inr), "owed_usd": float(owed_usd),
            "pending_payouts": pending_payouts}


def admin_payout_requests(status=None, limit=100):
    where = "WHERE p.status=%s" if status else ""
    params = ([status] if status else []) + [limit]
    with _pool.connection() as conn:
        rows = conn.execute(f"""
            SELECT p.id, u.email, p.amount, p.currency, p.method, p.status, p.created_at, p.paid_at, u.id
            FROM payout_requests p JOIN users u ON u.id=p.user_id
            {where} ORDER BY p.created_at DESC LIMIT %s""", params).fetchall()
    return [{"id": r[0], "email": r[1], "amount": float(r[2]), "currency": r[3], "method": r[4],
             "status": r[5], "created_at": str(r[6]), "paid_at": str(r[7]) if r[7] else None,
             "user_id": str(r[8])} for r in rows]


def admin_set_payout_status(payout_id, status):
    status = status if status in ("paid", "rejected", "requested") else "requested"
    with _pool.connection() as conn:
        if status == "paid":
            conn.execute("UPDATE payout_requests SET status='paid', paid_at=now() WHERE id=%s", (payout_id,))
        else:
            conn.execute("UPDATE payout_requests SET status=%s, paid_at=NULL WHERE id=%s", (status, payout_id))


def admin_top_affiliates(limit=20):
    with _pool.connection() as conn:
        rows = conn.execute("""
            SELECT u.email, u.ref_code,
                   count(r.*) FILTER (WHERE r.status='converted') AS conversions,
                   coalesce(sum(r.commission) FILTER (WHERE r.currency='INR'),0) AS inr,
                   coalesce(sum(r.commission) FILTER (WHERE r.currency='USD'),0) AS usd
            FROM users u JOIN referrals r ON r.referrer_id=u.id
            GROUP BY u.id, u.email, u.ref_code
            ORDER BY conversions DESC, inr DESC LIMIT %s""", (limit,)).fetchall()
    return [{"email": r[0], "ref_code": r[1], "conversions": r[2],
             "inr": float(r[3]), "usd": float(r[4])} for r in rows]


# are per-plan INR + USD; limits are monthly images / AI actions / sites.
_PLAN_DEFAULTS = {
    "owai_mini":    {"name": "Mini",    "inr": 700,  "usd": 9,  "images": 25,  "actions": 800,     "sites": 1, "india_only": True},
    "owai_starter": {"name": "Starter", "inr": 1699, "usd": 20, "images": 60,  "actions": 2000,    "sites": 2, "india_only": False},
    "owai_pro":     {"name": "Pro",     "inr": 8299, "usd": 99, "images": 200, "actions": 1000000, "sites": 10, "india_only": False},
}


def get_plan_config():
    """Merged plan config: DB overrides on top of the built-in defaults."""
    cfg = {k: dict(v) for k, v in _PLAN_DEFAULTS.items()}
    override = get_setting("plan_config") or {}
    for k, v in override.items():
        if k in cfg and isinstance(v, dict):
            cfg[k].update(v)
    return cfg


def save_plan_config(new_cfg):
    """Persist admin edits AND live-patch the in-memory pricing tables so changes
    take effect immediately without a redeploy."""
    set_setting("plan_config", new_cfg)
    apply_plan_config()


def apply_plan_config():
    """Sync the live PLAN_CREDITS / PLAN_TOOLCALLS + razorpay price tables from
    the current (DB-merged) plan config. Called at boot and after each save."""
    cfg = get_plan_config()
    for key, p in cfg.items():
        PLAN_CREDITS[key] = int(p.get("images", PLAN_CREDITS.get(key, 5)))
        PLAN_TOOLCALLS[key] = int(p.get("actions", PLAN_TOOLCALLS.get(key, 100)))
    # patch razorpay price tables if that module is importable
    try:
        import razorpay_pay as _rzp
        for key, p in cfg.items():
            _rzp.PLAN_PRICES_INR[key] = (p.get("name", key), int(p.get("inr", 0)))
            if not p.get("india_only"):
                _rzp.PLAN_PRICES_USD[key] = (p.get("name", key), int(p.get("usd", 0)))
    except Exception:
        pass


# --- Email template config (admin-editable subject/body + on-off) -------------
# key -> (label, default_subject, list of {{placeholders}} available)
EMAIL_KINDS = {
    "welcome":       ("Welcome (after email verified)", "Welcome to wptaskify 🎉", ["name"]),
    "verify":        ("Email verification", "Verify your wptaskify account", ["link"]),
    "reset":         ("Password reset", "Reset your wptaskify password", ["link"]),
    "payment":       ("Payment receipt", "Payment received - {item}", ["item", "amount", "currency"]),
    "renew":         ("Plan renewal reminder", "Your {plan} plan renews soon", ["plan", "days", "renews_on"]),
    "low_images":    ("Low image credits", "Only {left} AI image credits left", ["left", "plan"]),
    "low_actions":   ("Low AI actions", "Only {left} AI actions left", ["left", "plan"]),
    "site_connected":("Site connected", "Your site is connected ✓", ["site_url"]),
}


def get_email_config():
    """Per-email: {enabled, subject_override}. DB overrides on top of defaults."""
    override = get_setting("email_config") or {}
    out = {}
    for key, (label, subj, ph) in EMAIL_KINDS.items():
        o = override.get(key, {}) if isinstance(override.get(key), dict) else {}
        out[key] = {
            "label": label,
            "subject": o.get("subject", subj),
            "default_subject": subj,
            "enabled": o.get("enabled", True),
            "placeholders": ph,
        }
    return out


def save_email_config(new_cfg):
    set_setting("email_config", new_cfg)


def email_enabled(kind):
    cfg = get_setting("email_config") or {}
    o = cfg.get(kind, {})
    return o.get("enabled", True) if isinstance(o, dict) else True


# ---------------------------------------------------------------------------
# GST / tax (India only - 18% on INR payments; international USD = no tax)
# ---------------------------------------------------------------------------
def get_gst_rate():
    """GST percent (admin-editable). Default 18. Applies to INR payments only."""
    v = get_setting("gst_rate")
    try:
        return float(v) if v is not None else 18.0
    except (TypeError, ValueError):
        return 18.0


def set_gst_rate(rate):
    try:
        rate = float(rate)
    except (TypeError, ValueError):
        rate = 18.0
    set_setting("gst_rate", max(0.0, min(100.0, rate)))


def gst_on(base_amount, currency="INR"):
    """Return (tax_amount, total, rate). Tax only on INR; USD = no tax."""
    if currency != "INR":
        return 0.0, round(base_amount, 2), 0.0
    rate = get_gst_rate()
    tax = round(base_amount * rate / 100.0, 2)
    return tax, round(base_amount + tax, 2), rate


def get_gstin(user_id):
    with _pool.connection() as conn:
        r = conn.execute("SELECT gstin FROM users WHERE id=%s", (user_id,)).fetchone()
    return (r[0] if r else "") or ""


def set_gstin(user_id, gstin):
    """Save a user's GSTIN (for input-tax-credit claims). Basic 15-char check."""
    gstin = (gstin or "").strip().upper()
    with _pool.connection() as conn:
        conn.execute("UPDATE users SET gstin=%s WHERE id=%s", (gstin[:15], user_id))


def valid_gstin(gstin):
    """Loose GSTIN format check: 15 chars, 2 digits + 10 PAN + 3 alnum."""
    import re
    return bool(re.match(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[0-9A-Z]{1}Z[0-9A-Z]{1}$",
                         (gstin or "").strip().upper()))


def admin_tax_summary(days=None):
    """GST collected totals + recent taxed transactions for the admin tax module."""
    with _pool.connection() as conn:
        c = conn.execute
        total_tax = c("SELECT coalesce(sum(tax_amount),0) FROM transactions "
                      "WHERE status='completed' AND currency='INR'").fetchone()[0]
        total_base = c("SELECT coalesce(sum(base_amount),0) FROM transactions "
                       "WHERE status='completed' AND currency='INR'").fetchone()[0]
        tax_30 = c("SELECT coalesce(sum(tax_amount),0) FROM transactions "
                   "WHERE status='completed' AND currency='INR' "
                   "AND created_at > now() - interval '30 days'").fetchone()[0]
        n_gstin = c("SELECT count(*) FROM users WHERE gstin <> ''").fetchone()[0]
        rows = c("""
            SELECT t.created_at, u.email, u.gstin, t.item, t.base_amount, t.tax_amount,
                   t.amount_usd, t.currency
            FROM transactions t JOIN users u ON u.id=t.user_id
            WHERE t.status='completed' AND t.currency='INR' AND t.tax_amount > 0
            ORDER BY t.created_at DESC LIMIT 100""").fetchall()
        gstins = c("SELECT email, gstin FROM users WHERE gstin <> '' ORDER BY email").fetchall()
    return {
        "total_tax": float(total_tax), "total_base": float(total_base),
        "tax_30": float(tax_30), "n_gstin": n_gstin, "rate": get_gst_rate(),
        "txns": [{"created_at": str(r[0]), "email": r[1], "gstin": r[2], "item": r[3],
                  "base": float(r[4]), "tax": float(r[5]), "total": float(r[6]),
                  "currency": r[7]} for r in rows],
        "gstins": [{"email": g[0], "gstin": g[1]} for g in gstins],
    }
