# Deployment

Order matters: deploy the API first (so the frontend has something to call), then the frontend, then update the marketing site's trusted origins.

## 1. Deploy the API → `api.saurabhbhayana.com`

Recommended host: Fly.io or Render. We need long-running ffmpeg jobs, so Vercel/Cloudflare Pages won't work for this part.

Required env vars on the API:

```
MONGODB_URI=mongodb+srv://...                # SAME as marketing site
MONGODB_DB=saurabh                           # SAME as marketing site
AUTH_COOKIE_PREFIX=saurabh                   # SAME as marketing site
KEY_VAULT_SECRET=<32-byte base64>            # generate once, store in secrets
ALLOWED_ORIGINS=https://tools.saurabhbhayana.com
```

Generate `KEY_VAULT_SECRET` once with:

```
python -c "import os, base64; print(base64.b64encode(os.urandom(32)).decode())"
```

Save it somewhere safe — losing it means every encrypted user API key in Mongo becomes garbage.

DNS: CNAME `api` → your provider's hostname. Add a TLS cert.

## 2. Deploy the Frontend → `tools.saurabhbhayana.com`

Vercel works perfectly for this part.

Required env vars:

```
MONGODB_URI=mongodb+srv://...                # SAME
MONGODB_DB=saurabh                           # SAME
BETTER_AUTH_SECRET=<base64>                  # SAME as marketing site
BETTER_AUTH_URL=https://tools.saurabhbhayana.com
AUTH_COOKIE_DOMAIN=.saurabhbhayana.com       # leading dot
NEXT_PUBLIC_API_URL=https://api.saurabhbhayana.com
KEY_VAULT_SECRET=<same base64 as the API>    # MUST match
```

DNS: CNAME `tools` → Vercel.

## 3. Update the marketing site

On the saas-landing repo's deployment, append the two new origins to `AUTH_TRUSTED_ORIGINS`:

```
AUTH_TRUSTED_ORIGINS=https://tools.saurabhbhayana.com,https://api.saurabhbhayana.com
```

Then redeploy the marketing site. This step lets the auth API on the marketing site accept calls from the new subdomains (e.g. for sign-out propagation).

## 4. Smoke test

1. Sign in at `https://saurabhbhayana.com/login`.
2. Open `https://tools.saurabhbhayana.com` in the same browser. You should land on the workspace already signed in (no re-login).
3. Hit `https://api.saurabhbhayana.com/health` — should return `{ ok: true }`.
4. Hit `https://api.saurabhbhayana.com/me` from the browser console with `credentials: "include"` — should return your user document. If it 401s, the cookie isn't reaching the API host (most often: missing `AUTH_COOKIE_DOMAIN` on the marketing site, or the API is on a different parent domain than the cookie).

## Common gotchas

- **Cookie won't cross subdomains in dev.** Browsers won't set a `.saurabhbhayana.com` cookie on `localhost`. Dev runs with `AUTH_COOKIE_DOMAIN=` (blank) and the cookie stays host-scoped to `localhost:3000` / `localhost:3010`. If you actually need to test SSO locally, edit `hosts` to add `.test` versions and run a local HTTPS proxy.

- **`BETTER_AUTH_SECRET` mismatched.** Different secrets across services means each one issues different signatures and rejects each other's cookies. The marketing site is the *only* one that signs cookies, but the secret must still match everywhere that uses Better Auth client helpers.

- **`KEY_VAULT_SECRET` mismatched.** API and frontend both need it (the frontend will need it once we add a "test key" client-side preview). If they don't match, decrypt fails.

- **R2/S3 not wired.** The dev API writes uploads/outputs to local disk. In production those folders disappear on every redeploy. Switch to R2 before opening the tool to real users.
