# 🎬 Reels Factory — Setup Guide

Faceless "Did You Know" fact reels banao aur Facebook pe auto-post karo.
100% original content (Claude script + free AI voice + royalty-free stock video)
= safe to monetize, koi copyright strike nahi.

---

## ✅ Kya already ho chuka hai

- Python + FFmpeg installed ✔️
- Edge-TTS free voice working ✔️
- Video pipeline tested (1080x1920 reel banta hai) ✔️
- MCP server (`server.py`) ready with 6 tools ✔️

Bas 2 free keys chahiye aur server Claude me add karna hai.

---

## STEP 1 — Pexels free API key (2 minute, free)

1. Jao: https://www.pexels.com/api/
2. "Get Started" → email se sign up (free, no card)
3. API key copy karo
4. Is folder me `.env.example` ko copy karke `.env` banao
5. `.env` me daalo:
   ```
   PEXELS_API_KEY=yaha_apni_key_paste_karo
   ```

> Free limit: 200 requests/hour, 20,000/month. Daily 20-30 reels ke liye kaafi.

---

## STEP 2 — Facebook Page + token (10 minute, free)

Auto-post ke liye chahiye. Agar abhi sirf reel banana hai (manual post),
to ye step baad me kar sakte ho.

1. Ek **Facebook Page** banao (agar nahi hai): https://facebook.com/pages/create
2. Jao **Meta for Developers**: https://developers.facebook.com/
3. "My Apps" → "Create App" → type **"Business"**
4. App me add karo product: **"Facebook Login"** + permissions
5. Jao **Graph API Explorer**: https://developers.facebook.com/tools/explorer/
6. Apni app select karo, ye permissions add karo:
   - `pages_show_list`
   - `pages_read_engagement`
   - `pages_manage_posts`
   - `publish_video`
7. "Generate Access Token" → page select karo → token copy karo
8. (Recommended) Is short token ko **long-lived** banao taaki baar-baar na badle.
   Guide: https://developers.facebook.com/docs/facebook-login/guides/access-tokens/get-long-lived
9. Apna **Page ID** nikalo (page → About → Page ID)
10. `.env` me daalo:
    ```
    FB_PAGE_ID=yaha_page_id
    FB_PAGE_ACCESS_TOKEN=yaha_long_lived_token
    ```

---

## STEP 3 — MCP server Claude me add karo

Claude Code me ye command chalao (is folder se):

```
claude mcp add reels-factory -- python "c:\Users\Admin\Desktop\saurabh-tools\reels-factory\server.py"
```

Phir Claude restart karo. Ab Claude ke paas ye tools aa jayenge:

| Tool | Kaam |
|------|------|
| `generate_voiceover` | Script -> English voice mp3 |
| `fetch_visual` | Keyword -> stock video download |
| `assemble_reel` | Voice + video + captions -> reel |
| `make_reel` | One-shot: script + keyword -> finished reel |
| `post_to_facebook` | Reel -> Facebook pe publish |
| `create_and_post` | Full pipeline: script -> reel -> Facebook |

---

## STEP 4 — Pehla reel banao

Claude ko bolo:

> "Ek 'Did you know' fact reel banao space ke baare me aur Facebook pe post karo"

Claude khud:
1. Script likhega
2. `create_and_post` tool call karega
3. Voice + video + captions banayega
4. Facebook pe post kar dega

Ya sirf test ke liye (bina post kiye):

> "make_reel se ek octopus fact ka reel banao, keyword 'ocean deep'"

---

## 📂 Folder structure

```
reels-factory/
├── server.py        # MCP server (6 tools)
├── helpers.py       # actual logic (voice/video/fb)
├── .env             # tumhari keys (ye git me mat daalo)
├── .env.example     # template
├── output/          # finished reels yaha aate hain
├── temp/            # intermediate files
└── SETUP.md         # ye file
```

---

## 💰 Cost

| Item | Cost |
|------|------|
| Claude, Edge-TTS, FFmpeg, MCP | FREE |
| Pexels stock video | FREE (200/hour) |
| Facebook posting | FREE |
| **Total** | **₹0** |

Optional paid (abhi zaroorat nahi): ElevenLabs premium voice.

---

## ⚠️ Monetization rules (yaad rakho)

- Content original rakhо (Claude script + AI voice + stock = original ✔️)
- Copyrighted movie clips MAT daalo (page ban ho jayega)
- Facebook Reels monetization ke liye: page eligibility check karo
  (followers + watch-time requirements Meta ki policy ke hisaab se)
- Consistent post karo (daily 1-3 reels) = algorithm boost
