# wptaskify - Safe Deploy Guide (jab real users ho)

Jab live pe 100+ users ho, tab seedha production pe deploy = risky. Ye guide 3 cheezein
deta hai: **staging** (test copy), **smoke test** (auto-check), aur **rollback** (wapas jaana).

Rule ek hi: **Production pe kabhi bina test kiye deploy mat karo.**

---

## 1. Deploy ka safe flow (har baar yahi)

```
Code change
   |
   v
[1] Staging pe deploy    ->  railway up --service wp-mcp --environment staging --detach
   |
   v
[2] Staging pe smoke test ->  python smoke_test.py https://<staging-url>
   |
   +-- FAIL? -> ruk jao, bug fix karo, wapas [1]. Production ko haath mat lagao.
   |
   +-- PASS? -> aage
   v
[3] Khud manually check (staging pe): login, ek test payment, dashboard, coupon
   |
   v
[4] Sab OK? -> Production pe deploy  ->  railway up --service wp-mcp --environment production --detach
   |
   v
[5] Production pe smoke test  ->  python smoke_test.py --resolve
   |
   +-- FAIL? -> turant ROLLBACK (neeche section 4)
   +-- PASS? -> ho gaya. Users safe.
```

**Yaad rakho:** staging pe fail hua to users ko pata bhi nahi chalega - wo asli site pe
gaya hi nahi. Yahi poora point hai.

---

## 2. Smoke test (`smoke_test.py`)

Har deploy ke baad chalao. 16 automatic checks - site up hai, key pages, auth enforced,
security fixes hold, OAuth sahi, koi purani copy nahi.

```bash
# Production test (DNS ya IP-pin dono chalte hain)
python smoke_test.py                 # normal (DNS ke through)
python smoke_test.py --resolve       # prod IP pin (DNS/CDN settle hone se pehle bhi)

# Staging test
python smoke_test.py https://<staging-url>
```

- Exit code **0** = sab green, deploy healthy.
- Exit code **1** = kuch tuta, `[!] DEPLOY NOT HEALTHY` dikhega -> **promote mat karo / rollback karo.**

Ye test **read-only** hai - koi user nahi banata, koi payment nahi leta. Safe hai baar-baar chalao.

---

## 3. Staging environment banana (ek baar ka setup)

Railway pe staging = production ki alag copy, **alag database** ke saath. Users nahi,
sirf aap test karte ho.

### Railway dashboard me (browser, ~5 min):

1. https://railway.app -> project **wp-mcp** kholo
2. Upar environment dropdown (jahan "production" likha hai) -> **"New Environment"**
3. Naam do: `staging`. Option aaye to **"Duplicate from production"** chuno
   (isse services + env vars copy ho jaate hain).
4. Staging me ek **alag Postgres** hona chahiye (production ka DB share MAT karo -
   warna test data asli DB me chala jayega). Duplicate ne apna Postgres bana diya to
   theek; nahi to staging me "New -> Database -> PostgreSQL" add karo.
5. Staging ke `wp-mcp` service me `DATABASE_URL` staging ke Postgres ka hona chahiye
   (Railway variable reference se apne aap ho jata hai agar same environment me hai).
6. Staging ke env vars me ye SAFE rakho (asli users/paise na chhue):
   - `RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` -> **Razorpay TEST mode** ki keys
     (dashboard.razorpay.com -> Test Mode -> API Keys). Real payment na ho.
   - `RESEND_API_KEY` -> chalega, par test emails apne hi email pe bhejo.
   - `PUBLIC_URL` -> staging ka URL (jo Railway deta hai, e.g. `wp-mcp-staging.up.railway.app`).
   - `OAUTH_SECRET` -> koi bhi strong random (production se ALAG rakho).
7. Staging ko ek URL do: service -> Settings -> Networking -> "Generate Domain"
   (ya `staging.wptaskify.com` custom domain).

### Deploy commands (environment flag ke saath):

```bash
# staging pe
railway up --service wp-mcp --environment staging --detach

# production pe (jab confirm ho jaye)
railway up --service wp-mcp --environment production --detach
```

> Note: agar `--environment` flag se link issue aaye, pehle
> `railway environment staging` (ya `production`) chala ke switch karo, phir `railway up`.

---

## 4. Rollback (agar production pe kuch tut jaye)

**Railway dashboard se (sabse aasaan):**
1. Project -> `wp-mcp` service -> **Deployments** tab
2. Pichla **green/working** deployment dhundo
3. Uspe **"..." menu -> "Redeploy"** (ya "Rollback to this")
4. 1-2 min me purana working version wapas live. Users fir se theek.

**CLI se:**
```bash
railway deployments                 # list (IDs + status dekho)
railway redeploy                    # latest ko dobara; ya dashboard se specific chuno
```

Rollback ke baad hamesha `python smoke_test.py --resolve` chala ke confirm karo.

---

## 5. Database backup (users ka data bachane ke liye) - ZAROORI

Code rollback ho sakta hai, par **DB ka galat change (drop/migration) rollback nahi hota**
- isliye backup chahiye.

### Railway auto-backup ON karo (browser):
1. Project -> **Postgres** service -> **Backups** tab
2. **Scheduled backups** ON karo (daily). Retention jitne din chahiye set karo.

### Manual backup (bade change se pehle hamesha lo):
```bash
# DATABASE_URL Railway Postgres se copy karo (Postgres service -> Variables)
pg_dump "$DATABASE_URL" > backup_$(date +%Y%m%d).sql

# restore (zaroorat pade to)
psql "$DATABASE_URL" < backup_YYYYMMDD.sql
```

**Rule:** koi bhi migration / schema change / bulk data change se **pehle** manual backup lo.

---

## 6. Quick checklist (deploy se pehle print kar lo)

- [ ] Change staging pe deploy kiya
- [ ] `python smoke_test.py https://<staging>` -> 16/16 PASS
- [ ] Manually check: login + 1 test payment (Razorpay test mode) + dashboard + coupon
- [ ] (Agar DB change hai) manual backup liya
- [ ] Production pe deploy
- [ ] `python smoke_test.py --resolve` -> 16/16 PASS
- [ ] 5 min tak logs dekho: `railway logs --service wp-mcp` (koi error to nahi)
- [ ] Kuch tuta? -> Rollback (section 4)

---

## TL;DR (ek line)

**Staging pe deploy -> smoke test -> khud check -> tabhi production -> production pe fir
smoke test -> tuta to rollback.** Users kabhi bina-test wala code nahi dekhte.
