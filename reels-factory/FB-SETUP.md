# 📘 Facebook Setup — Page banana + Token lena (step-by-step)

Ye guide do hisson me hai:
- **PART A:** Facebook Page banana (API se nahi banta, manual — 2 min)
- **PART B:** Access token lena (taaki tool page manage kar sake)

> ⚠️ Yaad rahe: Facebook **API se page create/delete nahi** hone deta. Page
> ek baar manually banao, uske baad **sab kuch** tool se manage hoga:
> post, schedule, analytics, edit info, comments, auto-reply.

---

## PART A — Facebook Page banao (2 minute, free)

1. Apne personal Facebook account se login karo (page isi se manage hoga)
2. Jao: **https://www.facebook.com/pages/create**
3. Page ka **naam** do — niche ke hisaab se, jaise:
   - `Amazing Space Facts`
   - `Daily Motivation Quotes`
4. **Category** chuno: "Media", "Education", ya "Entertainment"
5. **Create Page** dabao — bas, page ban gaya ✅
6. (Optional) Profile + cover photo laga do — baad me tool se bhi ho jayega

> 💡 Tip: Niche-specific naam rakho. "Facts + Quotes mix" mat karo —
> ek page = ek topic = algorithm khush.

---

## PART B — Access token lena

### Step 1: Developer account (1 baar)
1. Jao: **https://developers.facebook.com/**
2. Top-right "Log In" → apne FB se login
3. "Get Started" → developer banno (free, bas confirm karna hai)

### Step 2: App banao
1. **https://developers.facebook.com/apps/** → "Create App"
2. Use case: **"Other"** → type: **"Business"** → Next
3. App ka naam do (kuch bhi, jaise "MyReelsBot") → Create
4. App ban gayi

### Step 3: Graph API Explorer se token
1. Jao: **https://developers.facebook.com/tools/explorer/**
2. Top-right me apni **app select** karo
3. "User or Page" dropdown → **"Get Page Access Token"**
4. Page select karo (jo Part A me banaya) → allow karo
5. **"Add a Permission"** — ye saari add karo (zaroori):
   ```
   pages_show_list
   pages_read_engagement
   pages_manage_posts
   pages_manage_metadata
   pages_manage_engagement
   pages_read_user_content
   read_insights
   publish_video
   ```
6. **"Generate Access Token"** → window me allow → token copy ho gaya

### Step 4: Token ko long-lived banao (zaroori — warna 1-2 ghante me expire)
Short token se direct kaam to chalega par 1-2 ghante me khatam.
Long-lived token ~60 din chalta hai.

**Asaan tarika — tool se hi:**
1. Upar wala short token copy karo
2. Claude ko bolo: *"fb_verify_token se ye token check karo: <token>"*
   - ye tumhare page ka **PAGE_ID** + **page_token** dono dikha dega
3. Wo page_token `.env` me daalo

**Ya manual (browser me ye URL kholo, values bharke):**
```
https://graph.facebook.com/v21.0/oauth/access_token?grant_type=fb_exchange_token&client_id=APP_ID&client_secret=APP_SECRET&fb_exchange_token=SHORT_TOKEN
```
(APP_ID + APP_SECRET → app ke Settings → Basic me milte hain)

### Step 5: Page ID nikalo
- Page → About → niche "Page ID" milega
- YA: `fb_verify_token` tool chalao, wo ID khud bata dega

### Step 6: .env me daalo
```
FB_PAGE_ID=tumhara_page_id
FB_PAGE_ACCESS_TOKEN=tumhara_long_lived_page_token
```

---

## ✅ Test karo

Claude ko bolo:
> "fb_verify_token chalao"  → user + pages list dikhega
> "fb_get_page_info chalao" → page ki current info
> "fb_insights chalao"      → analytics (naye page pe 0 hoga, normal)

Sab chal gaya = setup done! 🎉

---

## 🛠️ Ab ye sab tool se hoga

| Tool | Kaam |
|------|------|
| `post_to_facebook` | Reel publish |
| `create_and_post` | Script → reel → publish (ek call) |
| `fb_post_text` | Text post |
| `fb_schedule_post` | Future time pe schedule |
| `fb_insights` | Analytics (reach/views/fans) |
| `fb_top_posts` | Kaunsa post chala |
| `fb_get_page_info` / `fb_edit_page` | Page info padho / badlo |
| `fb_list_posts` / `fb_delete_post` | Posts list / delete |
| `fb_get_comments` / `fb_reply_comment` | Comments padho / reply |
| `fb_auto_reply` | Sab comments pe auto-reply |

---

## ⚠️ App Review (baad me, monetize karne se pehle)

Shuru me "Development mode" me bhi tum **apne hi page** pe sab kar sakte ho.
Jab page bade paimane pe chalana ho, to app ko **"Live mode"** karna +
kuch permissions ke liye **App Review** submit karna pad sakta hai
(Facebook ki normal process). Tab tak development mode kaafi hai.
