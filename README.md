# Saurabh Tools

Self-serve tools sub-product for `tools.saurabhbhayana.com`. First tool: audio → video. Built to slot under the same SSO as `saurabhbhayana.com`.

## Layout

```
saurabh-tools/
  web/      Next.js 16 frontend (tools.saurabhbhayana.com)
  api/      FastAPI backend (api.saurabhbhayana.com)
  docs/     Architecture + deployment notes
```

Two independent services that share the same Mongo for users + sessions.

## How users experience this

1. Sign up at `saurabhbhayana.com` (the marketing site, already exists).
2. Land on `tools.saurabhbhayana.com` — auto-signed-in via the parent-domain SSO cookie.
3. Open Settings, paste their own Gemini API key.
4. Use the audio → video tool. **One free render per account, lifetime.**
5. To render again, subscribe at ₹100/month on the marketing site.

You never pay for Gemini compute. The user's API key bills their own Google Cloud account.

## Local dev

```bash
# Frontend
cd web
npm install
npm run dev   # http://localhost:3010

# Backend
cd api
python -m venv .venv
.venv\Scripts\activate     # Windows
pip install -r requirements.txt
uvicorn app:app --reload --port 8001
```

Both services read the same `MONGODB_URI` and `BETTER_AUTH_SECRET` as the main marketing site so SSO works.

## Production

See `docs/deploy.md` for the full deployment guide. Short version:

- `web/` → Vercel, custom domain `tools.saurabhbhayana.com`
- `api/` → Fly.io or Render, custom domain `api.saurabhbhayana.com`
- Set `AUTH_COOKIE_DOMAIN=.saurabhbhayana.com` everywhere
- Add both new origins to `AUTH_TRUSTED_ORIGINS` on the marketing site and redeploy it

## Status

- [x] Repo skeleton
- [ ] Next.js frontend scaffold with sidebar+canvas layout
- [ ] Brand tokens copied from main site
- [ ] FastAPI backend with health endpoint
- [ ] SSO cookie validation
- [ ] Audio → video pipeline ported in
- [ ] BYO API key storage (encrypted)
- [ ] Free-render gate + Razorpay subscription
