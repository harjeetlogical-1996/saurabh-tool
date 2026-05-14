# Architecture

Two services, one Mongo, one shared session cookie.

```
┌─────────────────────────────┐         ┌─────────────────────────────┐
│ saurabhbhayana.com          │         │ tools.saurabhbhayana.com    │
│ (saas-landing repo)         │         │ (saurabh-tools/web)         │
│                             │         │                             │
│ - Marketing pages           │         │ - Sidebar + canvas UI       │
│ - Sign up / log in          │         │ - Settings, billing         │
│ - Razorpay subscription     │         │ - Tool runtime UIs          │
│ - /sb-console admin         │         │                             │
│ - Better Auth issuer        │         │ - Reads SAME session cookie │
│   sets cookie on            │         │   (browser sends it for any │
│   .saurabhbhayana.com       │ ──cookie─►   subdomain automatically) │
└──────────┬──────────────────┘         └──────────────┬──────────────┘
           │                                           │
           │ both read/write the same Mongo            │
           ▼                                           ▼
        ┌──────────────────────────────────────────────────┐
        │ MongoDB Atlas — db: "saurabh"                    │
        │   user, session, posts, ...                      │
        │   tool_settings (NEW — saurabh-tools writes this)│
        └────────────────────────┬─────────────────────────┘
                                 ▲
                                 │ FastAPI service reads/writes
                                 │
                       ┌─────────┴─────────────────────────┐
                       │ api.saurabhbhayana.com            │
                       │ (saurabh-tools/api)               │
                       │                                   │
                       │ - Validates SSO cookie            │
                       │ - Encrypts/stores user API keys   │
                       │ - Runs ffmpeg / Gemini pipelines  │
                       │ - Returns rendered output URLs    │
                       └───────────────────────────────────┘
```

## Why two services

The video render pipeline is long-running, CPU-heavy, and ffmpeg-shaped.
That doesn't belong in a Next.js serverless function. The frontend at
`tools.` is just a thin Next.js app calling the FastAPI backend at `api.`.

Both deploy and scale independently.

## Why shared Mongo

So we don't run two user systems. Every subdomain reads the same `user`
and `session` documents Better Auth writes on the marketing site. New
tool-specific state (encrypted keys, render counters, billing state) lives
in a new `tool_settings` collection keyed by `userId`, leaving the
existing collections untouched.

## Auth flow on every API call

1. Browser sends `saurabh.session_token` cookie (set by marketing site,
   scoped to `.saurabhbhayana.com`).
2. FastAPI splits the token off the signature.
3. Looks up `db.session` by `token`. Confirms `expiresAt` is future.
4. Looks up `db.user` by `userId`. That's the `AuthUser` for the request.
5. If any step fails → 401.

We never re-implement Better Auth's HMAC validation here. The fact that
a matching unexpired row exists in Mongo is sufficient — Better Auth on
the marketing site is the only thing that can write that row.

## Collections we touch

- `user` — read only. Source of truth for email, role, plan.
- `session` — read only. Source of truth for active sessions.
- `tool_settings` — read/write. Owned by saurabh-tools.
  ```
  {
    userId: "<user._id as string>",
    geminiKey: "v1:<nonce>:<ciphertext>",      // AES-256-GCM
    geminiKeyUpdatedAt: Date,
    rendersUsed: number,                       // total renders ever
    renderLimit: number,                       // 1 for free, 0 = unlimited
    plan: "free" | "pro",                      // mirrored from user.plan
    createdAt: Date,
  }
  ```

## What's NOT in this repo

- Auth signup, login, password reset, admin console — those stay on the
  marketing site at saurabhbhayana.com.
- Razorpay/Stripe checkout — also marketing site. When a user upgrades,
  the marketing site flips `user.plan = "pro"`, which both subdomains see
  on the next request.
