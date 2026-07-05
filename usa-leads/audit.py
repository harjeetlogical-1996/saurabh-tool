"""
usa-leads: full website SEO + technical audit (5 categories, scored 0-100).

Categories (weights): Crawlability 20%, Technical 25%, On-Page 25%,
Content 15%, Authority 15%. Follows the oc-seo-audit methodology.

Returns a structured dict that report.py turns into a branded PDF and
emailcopy.py turns into a pitch. All fetching is stdlib urllib.
PageSpeed is optional (PAGESPEED_API_KEY) and degrades gracefully.
"""
import re
import json
import urllib.request
import urllib.parse
import urllib.error

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) usa-leads-audit/1.0"
SOCIALS = ("facebook.com", "instagram.com", "twitter.com", "x.com",
           "linkedin.com", "youtube.com", "tiktok.com")

# severity -> point penalty
PEN = {"critical": 25, "high": 15, "medium": 8, "low": 3}


def _norm(url):
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


def _fetch(url, timeout=20):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept-Language": "en-US,en",
        "Accept": "text/html,application/xhtml+xml",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read(), r.geturl(), dict(r.headers)


def _ok(url, timeout=12):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, len(r.read())
    except Exception:
        return None, 0


def _score(issues):
    """issues: list of dicts with 'sev'. Returns 0-100."""
    s = 100
    for i in issues:
        s -= PEN.get(i.get("sev", "low"), 3)
    return max(0, s)


def _pagespeed(url, key, strategy="mobile"):
    if not key:
        return None
    try:
        u = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed?" + \
            urllib.parse.urlencode({"url": url, "strategy": strategy, "key": key})
        with urllib.request.urlopen(u, timeout=60) as r:
            d = json.loads(r.read().decode("utf-8", errors="ignore"))
        lh = d.get("lighthouseResult", {})
        au = lh.get("audits", {})
        def dv(k):
            return au.get(k, {}).get("displayValue", "")
        perf = lh.get("categories", {}).get("performance", {}).get("score")
        return {
            "score": int(perf * 100) if perf is not None else None,
            "lcp": dv("largest-contentful-paint"),
            "cls": dv("cumulative-layout-shift"),
            "tbt": dv("total-blocking-time"),
            "fcp": dv("first-contentful-paint"),
            "si": dv("speed-index"),
        }
    except Exception:
        return None


def _extract_social_links(html: str) -> dict:
    """Find social profile URLs in the page. Returns {platform: url}."""
    found = {}
    for plat in SOCIALS:
        m = re.search(r'href=["\'](https?://(?:www\.)?' + re.escape(plat) + r'[^"\']*)["\']',
                      html, re.I)
        if m:
            key = plat.split(".")[0]
            if key == "x":
                key = "twitter"
            found.setdefault(key, m.group(1))
    return found


def _check_social_active(url: str) -> dict:
    """Best-effort: is the profile reachable + does it hint at recent activity?
    Social sites block bots heavily, so this is a soft signal, not gospel."""
    out = {"url": url, "reachable": None, "active_hint": None}
    try:
        status, raw, final, _ = _fetch(url, timeout=12)
        out["reachable"] = (status == 200)
        body = raw.decode("utf-8", errors="ignore").lower()
        # crude recency hints that survive on public pages / meta
        hints = ("hours ago", "minutes ago", "1 day ago", "2 days ago", "3 days ago",
                 "this week", "yesterday", "2024", "2025", "2026")
        out["active_hint"] = any(h in body for h in hints)
    except Exception:
        out["reachable"] = False
    return out


# Map a business niche/keywords to the AI tools + app ideas that actually help it.
_AI_RULES = [
    (("groom", "salon", "spa", "barber", "clinic", "dentist", "therapy", "fitness", "gym"),
     ["AI appointment booking + reminders (cut no-shows)",
      "AI chatbot to answer FAQs and book 24/7",
      "AI that auto-replies to reviews and DMs"],
     "a booking app so repeat customers rebook in one tap"),
    (("restaurant", "cafe", "food", "pizza", "bar", "catering"),
     ["AI chatbot for menu questions and reservations",
      "AI that turns photos into social posts automatically",
      "AI review-response assistant"],
     "an ordering / loyalty app for repeat diners"),
    (("plumb", "hvac", "electric", "roof", "clean", "junk", "haul", "pressure",
      "landscap", "contractor", "repair", "mechanic", "detail", "solar"),
     ["AI phone/chat assistant that captures leads 24/7",
      "AI quote/estimate generator from a photo or form",
      "AI follow-up that texts leads who did not book"],
     "a job-booking app with scheduling and reminders"),
    (("real estate", "realtor", "property", "mortgage", "insurance", "law", "account"),
     ["AI lead-qualifying chatbot",
      "AI that drafts listings / documents",
      "AI email + SMS nurture sequences"],
     "a client portal app for documents and updates"),
]


def _ai_app_opportunities(business_name: str, category: str, html_low: str) -> dict:
    blob = (business_name + " " + category + " " + html_low[:2000]).lower()
    ai, app = [], ""
    for keys, tools, app_idea in _AI_RULES:
        if any(k in blob for k in keys):
            ai, app = tools, app_idea
            break
    if not ai:  # generic fallback
        ai = ["AI chatbot to answer questions and capture leads 24/7",
              "AI that auto-generates social posts from your services",
              "AI follow-up assistant for leads who do not convert"]
        app = "a simple customer app for bookings and offers"
    # detect if they already have live chat (then chatbot is an upgrade, not new)
    has_chat = any(c in html_low for c in ("livechat", "tawk.to", "intercom",
                                           "drift", "tidio", "crisp.chat", "zendesk"))
    return {"ai_tools": ai, "app_idea": app, "has_live_chat": has_chat}


def audit_site(website: str, pagespeed_key: str = "",
               business_name: str = "", category: str = "",
               check_social: bool = True) -> dict:
    base = _norm(website)
    R = {
        "url": base, "reachable": False, "https": False, "title": "",
        "categories": {}, "overall": 0, "rating": "", "issues": [],
        "good": [], "quick_wins": [], "pagespeed": None, "size_kb": None,
        "social": {}, "social_summary": "", "ai_tools": [], "app_idea": "",
        "business_name": business_name, "category": category,
    }
    if not base:
        R["issues"] = [{"sev": "critical", "cat": "Technical",
                        "title": "No website at all",
                        "why": "Customers searching online find your competitors instead.",
                        "fix": "Launch a fast, modern website."}]
        R["overall"] = 0
        R["rating"] = "Critical"
        R["categories"] = {k: 0 for k in
                           ("Crawlability", "Technical", "On-Page", "Content", "Authority")}
        return R

    try:
        status, raw, final_url, headers = _fetch(base)
    except Exception:
        try:
            status, raw, final_url, headers = _fetch(base.replace("https://", "http://"))
        except Exception:
            R["issues"] = [{"sev": "critical", "cat": "Technical",
                            "title": "Website does not load",
                            "why": "Visitors hit an error and leave.",
                            "fix": "Fix hosting / DNS so the site loads reliably."}]
            R["rating"] = "Critical"
            R["categories"] = {k: 0 for k in
                               ("Crawlability", "Technical", "On-Page", "Content", "Authority")}
            return R

    R["reachable"] = True
    html = raw.decode("utf-8", errors="ignore")
    low = html.lower()
    R["https"] = final_url.startswith("https://")
    R["size_kb"] = round(len(raw) / 1024.0, 1)
    domain = urllib.parse.urlparse(base).scheme + "://" + urllib.parse.urlparse(base).netloc

    # ---------------- Category 1: Crawlability ----------------
    crawl = []
    rb_status, _ = _ok(domain + "/robots.txt")
    if rb_status != 200:
        crawl.append({"sev": "high", "cat": "Crawlability", "title": "No robots.txt",
                      "why": "Search engines have no crawl guidance.",
                      "fix": "Add a robots.txt that allows crawling and points to your sitemap."})
    sm_status = None
    for sm in ("/sitemap.xml", "/sitemap_index.xml"):
        s, _ = _ok(domain + sm)
        if s == 200:
            sm_status = sm
            break
    if not sm_status:
        crawl.append({"sev": "critical", "cat": "Crawlability", "title": "No XML sitemap",
                      "why": "Google may miss your pages, so they never rank.",
                      "fix": "Generate and submit an XML sitemap in Google Search Console."})
    if "rel=\"canonical\"" not in low and "rel='canonical'" not in low:
        crawl.append({"sev": "high", "cat": "Crawlability", "title": "No canonical tag",
                      "why": "Risk of duplicate-content confusion in Google.",
                      "fix": "Add a self-referencing canonical link on each page."})
    if "noindex" in low:
        crawl.append({"sev": "critical", "cat": "Crawlability", "title": "Page may be set to noindex",
                      "why": "A noindex tag hides the page from Google entirely.",
                      "fix": "Remove noindex from pages you want to rank."})
    R["categories"]["Crawlability"] = _score(crawl)

    # ---------------- Category 2: Technical ----------------
    tech = []
    if not R["https"]:
        tech.append({"sev": "critical", "cat": "Technical", "title": "No HTTPS / SSL",
                     "why": "Browsers warn visitors and Google downranks the site.",
                     "fix": "Install a free SSL certificate and force HTTPS."})
    if 'name="viewport"' not in low and "name='viewport'" not in low:
        tech.append({"sev": "critical", "cat": "Technical", "title": "Not mobile-friendly",
                     "why": "Most visitors are on phones and see a broken layout.",
                     "fix": "Add a responsive viewport and mobile-first design."})
    ps = _pagespeed(base, pagespeed_key, "mobile")
    R["pagespeed"] = ps
    if ps and ps.get("score") is not None:
        sc = ps["score"]
        if sc < 50:
            tech.append({"sev": "high", "cat": "Technical",
                         "title": f"Poor mobile speed score ({sc}/100)",
                         "why": "Slow sites lose roughly half their mobile visitors.",
                         "fix": "Compress images to WebP, defer JS, enable caching/CDN."})
        elif sc < 80:
            tech.append({"sev": "medium", "cat": "Technical",
                         "title": f"Mediocre mobile speed score ({sc}/100)",
                         "why": "Speed affects both ranking and conversions.",
                         "fix": "Optimize largest images and reduce render-blocking scripts."})
    if R["size_kb"] and R["size_kb"] > 2500:
        tech.append({"sev": "medium", "cat": "Technical",
                     "title": f"Heavy homepage ({int(R['size_kb'])} KB)",
                     "why": "Large pages load slowly on mobile data.",
                     "fix": "Compress images and remove unused scripts/fonts."})
    R["categories"]["Technical"] = _score(tech)

    # ---------------- Category 3: On-Page ----------------
    onpage = []
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    title = (m.group(1).strip() if m else "")[:150]
    R["title"] = title
    if not title:
        onpage.append({"sev": "critical", "cat": "On-Page", "title": "Missing title tag",
                       "why": "Google shows nothing useful in search results.",
                       "fix": "Add a unique 50-60 char title with your main keyword."})
    elif len(title) < 15 or len(title) > 65:
        onpage.append({"sev": "medium", "cat": "On-Page",
                       "title": f"Title length not ideal ({len(title)} chars)",
                       "why": "Too short wastes ranking space; too long gets cut off.",
                       "fix": "Aim for a 50-60 character title."})
    if 'name="description"' not in low and "name='description'" not in low:
        onpage.append({"sev": "high", "cat": "On-Page", "title": "No meta description",
                       "why": "Google guesses your search snippet, lowering click rate.",
                       "fix": "Add a 150-160 char meta description with a call to action."})
    h1s = re.findall(r"<h1\b", low)
    if len(h1s) == 0:
        onpage.append({"sev": "critical", "cat": "On-Page", "title": "No H1 heading",
                       "why": "A basic SEO signal is missing.",
                       "fix": "Add exactly one H1 with your primary keyword."})
    elif len(h1s) > 1:
        onpage.append({"sev": "medium", "cat": "On-Page",
                       "title": f"Multiple H1 tags ({len(h1s)})",
                       "why": "Dilutes the page's main topic signal.",
                       "fix": "Keep a single H1 per page."})
    imgs = re.findall(r"<img\b[^>]*>", html, re.I)
    no_alt = [i for i in imgs if "alt=" not in i.lower()]
    if imgs and len(no_alt) >= max(3, len(imgs) // 2):
        onpage.append({"sev": "medium", "cat": "On-Page",
                       "title": f"{len(no_alt)} images missing alt text",
                       "why": "Hurts SEO and accessibility.",
                       "fix": "Add descriptive alt text to images."})
    if "og:title" not in low:
        onpage.append({"sev": "medium", "cat": "On-Page", "title": "No Open Graph tags",
                       "why": "Links shared on social look plain and get fewer clicks.",
                       "fix": "Add og:title, og:description, og:image."})
    R["categories"]["On-Page"] = _score(onpage)

    # ---------------- Category 4: Content ----------------
    text = re.sub(r"<[^>]+>", " ", html)
    words = len(text.split())
    content = []
    if words < 300:
        content.append({"sev": "high", "cat": "Content",
                        "title": f"Thin content ({words} words on homepage)",
                        "why": "Thin pages rarely rank for competitive terms.",
                        "fix": "Add helpful, keyword-rich content (services, FAQs, areas served)."})
    if not re.search(r"(blog|news|article|/posts?/)", low):
        content.append({"sev": "low", "cat": "Content", "title": "No blog / fresh content",
                        "why": "Fresh content drives ongoing organic traffic.",
                        "fix": "Start a simple blog answering customer questions."})
    R["categories"]["Content"] = _score(content)

    # ---------------- Category 5: Authority ----------------
    authority = []
    socials = sorted({s for s in SOCIALS if s in low})
    R["socials"] = socials
    if not socials:
        authority.append({"sev": "medium", "cat": "Authority", "title": "No social media links",
                          "why": "Visitors cannot verify or follow your brand.",
                          "fix": "Link your active social profiles in the header/footer."})
    internal = len(re.findall(r'href="' + re.escape(domain), html)) + \
        len(re.findall(r'href="/', html))
    if internal < 5:
        authority.append({"sev": "medium", "cat": "Authority", "title": "Few internal links",
                          "why": "Weak internal linking limits SEO and navigation.",
                          "fix": "Link related pages with descriptive anchor text."})
    if not re.search(r"(review|testimonial|rating|stars?)", low):
        authority.append({"sev": "low", "cat": "Authority", "title": "No visible reviews/testimonials",
                          "why": "Trust signals lift conversions.",
                          "fix": "Show customer reviews or testimonials on the homepage."})
    R["categories"]["Authority"] = _score(authority)

    # ---------------- Social media presence (for the automation pitch) ----------------
    links = _extract_social_links(html)
    social = {}
    if not links:
        R["social_summary"] = ("No social media links found on the site. You are missing "
                               "an easy, free channel to win local customers.")
    else:
        active, dead = [], []
        for plat, url in links.items():
            if check_social:
                chk = _check_social_active(url)
                social[plat] = chk
                if chk.get("reachable") and chk.get("active_hint"):
                    active.append(plat)
                else:
                    dead.append(plat)
            else:
                social[plat] = {"url": url}
        if check_social:
            parts = []
            if active:
                parts.append("active on " + ", ".join(active))
            if dead:
                parts.append("but " + ", ".join(dead) +
                             " looks inactive or rarely posts")
            R["social_summary"] = ("You have social profiles (" + "; ".join(parts) +
                                   "). Consistent posting is where most local businesses "
                                   "drop off, and that is exactly what we can automate.")
        else:
            R["social_summary"] = "Has social links: " + ", ".join(links.keys())
    R["social"] = social

    # ---------------- AI tools + app opportunities ----------------
    opp = _ai_app_opportunities(business_name, category, low)
    R["ai_tools"] = opp["ai_tools"]
    R["app_idea"] = opp["app_idea"]
    R["has_live_chat"] = opp["has_live_chat"]
    if not opp["has_live_chat"]:
        R["ai_tools"].insert(0, "an AI website chatbot (you currently have none, "
                                "so visitors with questions just leave)")

    # ---------------- combine ----------------
    all_issues = crawl + tech + onpage + content + authority
    R["issues"] = all_issues
    cats = R["categories"]
    R["overall"] = round(
        cats["Crawlability"] * 0.20 + cats["Technical"] * 0.25 +
        cats["On-Page"] * 0.25 + cats["Content"] * 0.15 + cats["Authority"] * 0.15)
    o = R["overall"]
    R["rating"] = ("Excellent" if o >= 90 else "Good" if o >= 75 else
                   "Needs Improvement" if o >= 50 else "Poor" if o >= 25 else "Critical")
    # quick wins = low-effort high-impact (high/critical that are simple)
    easy = ("meta description", "alt text", "Open Graph", "canonical", "robots.txt",
            "title", "social media")
    R["quick_wins"] = [i for i in all_issues
                       if any(e.lower() in i["title"].lower() for e in easy)][:5]
    # short list for the email pitch (most severe first)
    sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    R["top_issues"] = [i["title"] for i in
                       sorted(all_issues, key=lambda x: sev_order.get(x["sev"], 9))][:3]
    R["good"] = []
    if R["https"]:
        R["good"].append("HTTPS enabled")
    if socials:
        R["good"].append("links to " + ", ".join(s.split(".")[0] for s in socials))
    if sm_status:
        R["good"].append("has XML sitemap")
    return R
