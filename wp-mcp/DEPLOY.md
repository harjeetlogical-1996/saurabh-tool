# wptaskify — Deploy Guide (READ THIS FIRST)

> Ye doc isliye hai taaki deploy me kabhi confusion na ho. Sab kuch yahan likha hai.

---

## ⚡ TL;DR — deploy kaise karein

**Deploy GitHub push se NAHI hota. Railway CLI se hota hai.**

```bash
cd wp-mcp
railway up --service wp-mcp --ci
```

Bas. `--ci` build log dikhata hai aur khatam pe exit ho jaata hai. "Deploy complete" aaye to ho gaya.

Verify live (naya code aaya ya nahi):
```bash
curl -s "https://wptaskify.com/?signup" | grep -o 'minlength=[0-9]*'
# ya koi aur naya marker jo tumne abhi change kiya
```

---

## 🧠 Zaroori facts (jo bhoolna nahi)

| Cheez | Value |
|---|---|
| **Live URL** | https://wptaskify.com |
| **Host** | Railway (Docker-based build) |
| **Deploy method** | `railway up --service wp-mcp` (CLI) — **NOT** git-push auto-deploy |
| **Railway account** | `logicaldottech@gmail.com` (workspace: "Logical Dottech's Projects") |
| **Railway project** | `wp-mcp` (ID `3e41cbf8-2e37-47fd-b853-fa32776f9437`) |
| **App service name** | `wp-mcp` (the Python app — has ADMIN_PASSWORD/PUBLIC_URL vars) |
| **DB service** | `Postgres` (same project, linked separately) |
| **Environment** | `production` |
| **App entry** | `start.py` (Dockerfile `CMD ["python", "start.py"]`) |
| **Git remote** | `github.com/harjeetlogical-1996/saurabh-tool.git` (branch `main`) |

### ⚠️ Sabse important galatfahmi
**GitHub pe push karne se deploy NAHI hota.** Railway is repo ke pushes se auto-connected nahi hai.
Push sirf code backup ke liye hai. **Live karne ke liye HAMESHA `railway up --service wp-mcp` chalao.**

---

## 📋 Full deploy steps (recommended order)

1. **Code change karo** (server.py / start.py / db.py / pages.py / admin.py / razorpay_pay.py etc.)

2. **Compile check** (crash-proof):
   ```bash
   cd wp-mcp
   python -m py_compile start.py db.py razorpay_pay.py admin.py pages.py server.py
   ```

3. **Git commit + push** (backup — deploy nahi):
   ```bash
   cd ..   # repo root
   git add wp-mcp/<changed files>
   git commit -m "..."
   git push origin main
   ```

4. **Railway deploy** (ye actually LIVE karta hai):
   ```bash
   cd wp-mcp
   railway up --service wp-mcp --ci
   ```

5. **Verify live** — koi marker curl karo (upar dekho).

---

## 🐳 Dockerfile — nayi file add karo to yaad rakho

Dockerfile har `.py` file ko **explicitly** COPY karta hai:
```dockerfile
COPY server.py oauth.py db.py pages.py mailer.py chat.py billing.py razorpay_pay.py admin.py blog_posts.py google_api.py start.py ./
```
**Agar koi NAYI .py file banao** (jaise pehle `google_api.py` bani thi) → us line me add karna MAT bhoolo,
warna `ModuleNotFoundError` aayega aur deploy crash. Existing file edit karo to kuch nahi karna.

---

## 🔑 Secrets — kabhi commit mat karna

- Ye files **gitignored** hain, git me kabhi nahi jaani chahiye:
  - `github-token.txt`
  - `.claude/settings.json`
  - Google credentials JSON
- GitHub ka **push protection** ON hai — agar galti se secret commit kiya to push block ho jaayega.
  Us case me: secret ko history se `git filter-branch` se hatao, phir push karo. (2026-07-08 ko aisa hua tha.)
- Railway ke saare env vars (API keys, DB URL, GOOGLE_CLIENT_SECRET, RAZORPAY keys) **Railway dashboard me**
  set hain — code me kabhi nahi. Redeploy pe safe rehte hain (DB/env me store).

### Railway env vars dekhne/badalne
```bash
railway variables --service wp-mcp                       # list
railway variables --service wp-mcp --set "KEY=value"     # set/update
```

---

## 🧪 Common issues + fixes

| Problem | Wajah | Fix |
|---|---|---|
| Push ho gaya par live purana code | Railway git-push se deploy nahi hota | `railway up --service wp-mcp` chalao |
| `Service name required in non-interactive mode` | `--service` flag chhoot gaya | `--service wp-mcp` add karo |
| `ModuleNotFoundError: No module named 'X'` | Dockerfile COPY me nayi file add nahi ki | Dockerfile ki COPY line me file add karo |
| Push `403 / permission denied` | Git credential galat account ka | Sahi account ka PAT use karo (repo owner: harjeetlogical-1996) |
| Push blocked "secret detected" | Secret commit ho gaya | filter-branch se history clean karo |
| `railway whoami` galat account | Doosre account me login | `railway login` phir sahi account |

---

## 📝 Verify checklist (deploy ke baad)

```bash
# core health
curl -s -o /dev/null -w "home:%{http_code} mcp:%{http_code}\n" https://wptaskify.com/ https://wptaskify.com/mcp
# public pages (sab 200/302 hone chahiye)
for p in / /pricing /login /services /contact /faq /about; do
  curl -s -o /dev/null -w "$p:%{http_code} " "https://wptaskify.com$p"; done; echo
# tumhara naya feature ka marker curl karo
```

`/mcp` = 401 normal hai (Bearer token chahiye). `/dashboard` = 302 (login chahiye) normal.

---

## 💳 Auto-renewal (Razorpay Subscriptions) — SETUP zaroori

Code recurring subscriptions support karta hai (auto har-mahine charge), PAR wo tabhi chalega jab
Razorpay pe **Plan objects** bana ke unke IDs env me daale jaayein. Jab tak ye nahi hota, plans
**one-time** rehte hain (31-din, phir free — auto-renew nahi).

### Enable karne ke steps:
1. **Razorpay Dashboard** → Subscriptions → **Plans** → har plan+currency ke liye ek monthly Plan banao:
   - Starter INR (₹1,699/month), Starter USD ($20/month)
   - Pro INR (₹8,299/month), Pro USD ($99/month)
   - (Mini optional, India-only)
   - Har ek ka `plan_id` copy karo (jaise `plan_QxAbc123`)
2. **Razorpay account pe "Subscriptions" / international recurring enable** hona chahiye (USD ke liye
   International + recurring dono on).
3. Railway pe env var set karo (JSON):
   ```bash
   railway variables --service wp-mcp --set 'RAZORPAY_PLAN_IDS={"owai_starter":{"INR":"plan_xxx","USD":"plan_yyy"},"owai_pro":{"INR":"plan_aaa","USD":"plan_bbb"}}'
   ```
4. **Razorpay Webhook** me ye events bhi ON karo (existing payment events ke saath):
   `subscription.charged`, `subscription.cancelled`, `subscription.completed`,
   `subscription.halted`, `subscription.expired`
5. Redeploy: `railway up --service wp-mcp --ci`

### Kaise kaam karega (enable hone ke baad):
- Naya paid user (bina discount) → subscription banega → user ek baar authorize (autopay mandate)
  → Razorpay **har mahine apne aap charge** karega → `subscription.charged` webhook → plan renew.
- First-month **discount/coupon** wale → us pehle mahine one-time link (discount subscription me
  nahi ghusta). Baad me full-price subscription le sakte hain.
- **Cancel** → Razorpay pe bhi cancel (cycle-end) + local sub_status=canceled → period-end pe free.
- Fallback: kisi plan ka plan_id nahi mila to wo one-time link se bikega (safe).

---

## 🔭 Known / watch-list (launch-blocker nahi, baad me)

- **`/pricing` kabhi slow** (2–5s, kabhi timeout). Single-threaded ASGI; koi query optimize karni ho sakti hai.
- **Built-in chat HIDDEN** hai (`ENABLE_BUILTIN_CHAT` env). On karoge to Claude token cost humpe aayega.
- **Migration tools one-time** — use ke baad delete karna (AIOSEO migrate etc.).

---

*Last updated: 2026-07-08. Deploy method confirmed: `railway up --service wp-mcp --ci`.*
