# Deploy to Cloud Run — tool.saurabhbhayana.com

Step-by-step deploy for the tools site. Assumes the marketing site
(`saurabhbhayana.com`) is already on Cloud Run with the SSO cookie
scoped to `.saurabhbhayana.com` — that gives us cross-subdomain login
for free.

## Domains

| Service                | Domain                          | Cloud Run service name |
| ---------------------- | ------------------------------- | ---------------------- |
| Web (Next.js frontend) | `tool.saurabhbhayana.com`       | `saurabh-tool-web`     |
| API (FastAPI backend)  | `tools-api.saurabhbhayana.com`  | `saurabh-tool-api`     |

Both services live in the same Cloud Run project. Region: **us-central1**
(matches the marketing site; required for the existing domain mapping
plumbing to work cleanly).

## One-time prerequisites

1. Cloud Build API enabled (`cloudbuild.googleapis.com`).
2. Cloud Run Admin role on your account.
3. Artifact Registry repo or just rely on the default Container Registry
   that Cloud Build uses (`gcr.io/<project>/...`).
4. Custom domain verified for `saurabhbhayana.com` in Cloud Run domain
   mappings (already done if the marketing site is mapped — Google
   inherits the verification to subdomains).

## Phase 1 — Deploy the API

### 1a. Build + push the image

In **Cloud Console → Cloud Build → Triggers → Run inline build**:

- Source: upload the `saurabh-tools` folder as a zip, OR connect the
  GitHub repo + set "Repository directory" to `api/`.
- Build config: **Dockerfile**, file path `api/Dockerfile`.
- Image name: `gcr.io/<your-project-id>/saurabh-tool-api:latest`.
- Run.

Wait for the build to finish (~3-4 min — pulls Python + ffmpeg).

### 1b. Create the Cloud Run service

**Cloud Console → Cloud Run → Create service**:

- Container image: `gcr.io/<your-project-id>/saurabh-tool-api:latest`
- Service name: `saurabh-tool-api`
- Region: `us-central1`
- CPU allocation: **CPU is always allocated** (jobs run in background
  threads — request-only CPU would kill them mid-render).
- Min instances: **1** (avoids cold-start losing in-flight jobs).
- Max instances: 3 to start.
- Memory: **2 GiB** (ffmpeg + image-gen comfort).
- Concurrency: 80.

### 1c. Set env vars (Variables & Secrets tab)

| Variable                    | Value                                       |
| --------------------------- | ------------------------------------------- |
| `MONGODB_URI`               | (your Atlas connection string)              |
| `MONGODB_DB`                | `saurabh`                                   |
| `KEYVAULT_SECRET`           | (32-byte base64 secret used for at-rest enc)|
| `AUTH_COOKIE_PREFIX`        | `saurabh` (must match marketing site)       |
| `ALLOWED_ORIGINS`           | `https://tool.saurabhbhayana.com`           |
| `INVITE_GATE`               | `1`                                         |
| `GEMINI_API_KEY`            | (your Gemini key, single-key fallback)      |

> **Tip:** Most secrets are also editable from the in-app
> `/admin/keys` page (Gemini multi-keys, Razorpay creds, etc.). The
> env vars above just need to be set ONCE so the very first owner
> login can reach Mongo + decrypt anything stored in DB.

### 1d. Allow unauthenticated invocations

Required so the browser (the actual API client) can hit the service.
Auth happens INSIDE the FastAPI via the Better-Auth cookie.

### 1e. Map the custom domain

**Cloud Run → Domain Mappings → Add Mapping**:

- Service: `saurabh-tool-api`
- Domain: `tools-api.saurabhbhayana.com`
- Google will give you a **CNAME record** to add at the registrar.

### 1f. Add the DNS CNAME

In Hostinger DNS for `saurabhbhayana.com`:

```
TYPE   NAME         VALUE                       TTL
CNAME  tools-api    ghs.googlehosted.com        300
```

SSL provisions automatically in 10–30 min. Check the domain mapping page
in Cloud Run until it shows the green ✓.

## Phase 2 — Deploy the Web

### 2a. Build the image

Same as 1a but for `web/`:

- Build config: Dockerfile at `web/Dockerfile`.
- Build args: `NEXT_PUBLIC_API_URL=https://tools-api.saurabhbhayana.com`
  (this is critical — it gets baked into the client bundle at build).
- Image name: `gcr.io/<your-project-id>/saurabh-tool-web:latest`.

### 2b. Create the Cloud Run service

- Service name: `saurabh-tool-web`
- Region: `us-central1`
- Min instances: 0 (web is stateless, cold starts ~3 sec).
- Max instances: 5.
- Memory: 512 MiB.
- Concurrency: 100.
- Container port: 8080.

### 2c. Web env vars

The web service is mostly client-side, so most secrets aren't needed.
Just confirm:

| Variable                | Value                                          |
| ----------------------- | ---------------------------------------------- |
| `NEXT_PUBLIC_API_URL`   | `https://tools-api.saurabhbhayana.com` (also baked at build) |

### 2d. Map `tool.saurabhbhayana.com`

Same flow as 1e.

DNS entry:

```
TYPE   NAME    VALUE                       TTL
CNAME  tool    ghs.googlehosted.com        300
```

## Phase 3 — First-time setup after deploy

1. **Visit `https://tool.saurabhbhayana.com`** in incognito.
2. You should be auto-signed-in via the cross-subdomain Better Auth
   cookie from the marketing site. If not, sign in on
   `saurabhbhayana.com` first.
3. Open the **/admin/invites** page (only visible to your `owner`
   account). Add the emails of every person you want to give access to.
4. Open **/admin/keys** and paste your Gemini API keys. Save.
5. Run a tiny audio→video as a smoke test.

## Updating after a code change

1. Cloud Build → re-run the same trigger (or push to GitHub if you
   wired the auto-deploy).
2. Cloud Run → service → **Revisions** → deploy the new image.

Container takes <1 min to roll. In-flight job workers die mid-render
(Mongo job stays in `running`); the next API boot heals those stale
jobs into `failed` so the user can retry.

## Rollback

Cloud Run → service → Revisions → click the previous revision → "Manage
traffic" → Send 100% there.

## Cost guard

- **Min instances=1 on API** = ~₹450/mo always-on cost for a 1 CPU /
  2 GiB instance. Without min=1 you save money but lose in-flight
  jobs on cold starts. Tradeoff.
- **Min instances=0 on Web** = ~₹0 idle.
- Cloud Run egress free under 1 GiB/month; rendered videos served
  through the API count, plan accordingly.

## Things you can flip later

- `INVITE_GATE=0` opens the doors when you go fully public.
- `ALLOW_DEV_AUTH` must stay UNSET in production (otherwise the
  `?dev_user_id=...` query bypass would let anyone in).
- More Gemini keys: paste comma-separated in `/admin/keys` — they
  round-robin for higher throughput at the same cost.
