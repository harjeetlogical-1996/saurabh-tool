# Google Analytics + Search Console — OAuth Setup (for wptaskify)

This lets any wptaskify user connect THEIR own Google Analytics 4 + Search Console,
so the AI can review their real traffic, top pages, and search queries. One-time
setup on YOUR Google account (the app owner). ~10 minutes.

You give me two values at the end: **Client ID** and **Client Secret**. I put them in
Railway (`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`) — the secret never goes in code.

---

## Step 1 — Google Cloud project
1. Go to https://console.cloud.google.com/
2. Top bar → project dropdown → **New Project** → name it `wptaskify` → Create.
3. Make sure that project is selected (top bar).

## Step 2 — Enable the two APIs
Go to **APIs & Services → Library**, search and **Enable** each:
1. **Google Analytics Data API**  (the GA4 reporting API)
2. **Google Search Console API**

## Step 3 — OAuth consent screen
1. **APIs & Services → OAuth consent screen**
2. User type: **External** → Create.
3. Fill:
   - App name: **wptaskify**
   - User support email: your email
   - App logo: optional
   - App domain → Application home page: `https://wptaskify.com`
   - Authorized domains: add `wptaskify.com`
   - Developer contact email: your email
4. **Scopes** → Add or Remove Scopes → add these two (paste in the filter):
   - `https://www.googleapis.com/auth/analytics.readonly`
   - `https://www.googleapis.com/auth/webmasters.readonly`
   Save.
5. **Test users**: while the app is in "Testing" mode, add the Google accounts that
   will connect (your own + any early users). Save.
   - NOTE: In Testing mode only listed test users can connect, and refresh tokens
     expire after 7 days. To remove both limits, later click **Publish App**
     (Google may ask for verification if you have many users; for a handful of
     users Testing mode is fine to start).

## Step 4 — OAuth Client ID
1. **APIs & Services → Credentials → Create Credentials → OAuth client ID**
2. Application type: **Web application**
3. Name: `wptaskify web`
4. **Authorized redirect URIs** → Add URI (EXACTLY this, no trailing slash):
   ```
   https://wptaskify.com/google/callback
   ```
5. Create. A popup shows your **Client ID** and **Client Secret**.

## Step 5 — Give me the two values
Send me:
- **Client ID**  (looks like `1234-abcd.apps.googleusercontent.com`)
- **Client Secret**  (a shortish random string)

I add them to Railway and deploy. Then any user can click **Connect Google
Analytics** in their wptaskify dashboard, authorize, and the AI can review their data.

---

## What the user experiences after setup
1. Dashboard → **Connect Google Analytics** → Google consent → back to wptaskify.
2. Pick which GA4 property (and Search Console site) to use.
3. Ask the AI: "how's my traffic this month?", "top 10 pages", "which search
   queries bring clicks?" — it reads live GA4 + Search Console data.

## Scopes are READ-ONLY
Both scopes end in `.readonly` — wptaskify can only READ analytics/search data,
never change anything in the user's Google account.
