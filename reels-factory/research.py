"""
Research helpers for Reels Factory.

Fetch competitor / trending content from the web so Claude can analyse
patterns (hooks, topics, formats) and produce better-performing reels.

No paid APIs: uses public endpoints + simple HTML scraping. Best-effort —
if a source changes, the tool degrades gracefully instead of crashing.
"""
import json
import re
import urllib.request
import urllib.parse

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ReelsFactory/1.0"


def _get(url: str, timeout: int = 20) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept-Language": "en-US,en"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="ignore")


# ---------------------------------------------------------------------------
# 1. YOUTUBE search — titles of top videos for a query (great for hook ideas)
# ---------------------------------------------------------------------------
def youtube_titles(query: str, limit: int = 20) -> list:
    """
    Return titles + view-ish hints of YouTube results for a query by parsing
    the public results page. Titles reveal the hooks/angles that get clicks.
    """
    url = "https://www.youtube.com/results?" + urllib.parse.urlencode({
        "search_query": query, "sp": "CAMSAhAB"})  # sort by view count-ish
    html = _get(url)
    titles = []
    # ytInitialData is embedded as JSON in the page
    m = re.search(r"var ytInitialData = (\{.*?\});</script>", html)
    if not m:
        m = re.search(r'ytInitialData"\]\s*=\s*(\{.*?\});', html)
    if m:
        try:
            data = json.loads(m.group(1))
            text = json.dumps(data)
            # pull "title":{"runs":[{"text":"..."}]} occurrences
            for t in re.findall(r'"title":\{"runs":\[\{"text":"([^"]{8,120})"\}', text):
                if t not in titles:
                    titles.append(t)
                if len(titles) >= limit:
                    break
        except Exception:
            pass
    if not titles:
        # fallback: crude title scrape
        for t in re.findall(r'"label":"([^"]{12,120}) by [^"]+ [\d,]+ views', html):
            titles.append(t)
            if len(titles) >= limit:
                break
    return titles[:limit]


# ---------------------------------------------------------------------------
# 2. GOOGLE SUGGEST — what people actually search (topic + hook mining)
# ---------------------------------------------------------------------------
def search_suggestions(seed: str, limit: int = 20) -> list:
    """
    Google autocomplete suggestions for a seed phrase — reveals the exact
    questions/angles people search, perfect for reel topics + hooks.
    """
    url = "https://suggestqueries.google.com/complete/search?" + \
        urllib.parse.urlencode({"client": "firefox", "q": seed})
    try:
        raw = _get(url)
        data = json.loads(raw)
        return data[1][:limit]
    except Exception:
        return []


def expand_topic(seed: str) -> list:
    """
    Mine many suggestions by appending a..z and common question words to seed.
    Returns a de-duped list of concrete content angles.
    """
    out, seen = [], set()
    probes = [seed] + [f"{seed} {w}" for w in
                       ("how", "why", "best", "vs", "mistake", "tips", "for beginners")]
    for p in probes:
        for s in search_suggestions(p, limit=10):
            k = s.lower().strip()
            if k not in seen:
                seen.add(k)
                out.append(s)
    return out


# ---------------------------------------------------------------------------
# 3. SIMPLE PAGE TEXT — fetch readable text from a URL (transcript/article)
# ---------------------------------------------------------------------------
def page_text(url: str, max_chars: int = 6000) -> str:
    """Fetch a URL and return rough readable text (tags stripped)."""
    html = _get(url)
    html = re.sub(r"<script.*?</script>", " ", html, flags=re.S | re.I)
    html = re.sub(r"<style.*?</style>", " ", html, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_chars]


# ---------------------------------------------------------------------------
# 4. REDDIT — top posts in a subreddit (no key needed). Great for "what are
#    people actually asking/upvoting" in finance.
# ---------------------------------------------------------------------------
def reddit_top(subreddit: str = "personalfinance", period: str = "week",
               limit: int = 20) -> list:
    """
    Return top posts of a subreddit: title, upvotes, comments, url.
    period: hour | day | week | month | year | all
    """
    # Reddit blocks the .json API from many IPs, but the RSS feed stays open.
    url = f"https://www.reddit.com/r/{subreddit}/top/.rss?t={period}"
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (compatible; ReelsBot/1.0)"})
        with urllib.request.urlopen(req, timeout=20) as r:
            xml = r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        return [{"error": f"reddit fetch failed: {e}"}]
    out = []
    # each <entry> has a <title> and a <link href=...>
    for entry in re.findall(r"<entry>(.*?)</entry>", xml, flags=re.S):
        tm = re.search(r"<title>(.*?)</title>", entry, flags=re.S)
        lm = re.search(r'<link href="([^"]+)"', entry)
        if tm:
            title = re.sub(r"<[^>]+>", "", tm.group(1)).strip()
            title = (title.replace("&amp;", "&").replace("&lt;", "<")
                          .replace("&gt;", ">").replace("&#39;", "'"))
            out.append({"title": title[:150],
                        "url": lm.group(1) if lm else ""})
        if len(out) >= limit:
            break
    return out


# ---------------------------------------------------------------------------
# 5. YOUTUBE Data API (official, needs a free key) — top videos by views
# ---------------------------------------------------------------------------
def youtube_api_search(query: str, api_key: str, limit: int = 15,
                       order: str = "viewCount") -> list:
    """
    Official YouTube search: returns top videos with title + channel + id.
    order: viewCount | relevance | date | rating
    Pass a free YouTube Data API v3 key.
    """
    if not api_key:
        return [{"error": "YOUTUBE_API_KEY missing in .env"}]
    url = "https://www.googleapis.com/youtube/v3/search?" + urllib.parse.urlencode({
        "part": "snippet", "q": query, "type": "video",
        "order": order, "maxResults": min(limit, 50), "key": api_key,
    })
    try:
        data = json.loads(_get(url))
    except Exception as e:
        return [{"error": f"youtube api failed: {e}"}]
    if data.get("error"):
        return [{"error": data["error"].get("message", "api error")}]
    out = []
    for it in data.get("items", []):
        sn = it.get("snippet", {})
        vid = it.get("id", {}).get("videoId", "")
        out.append({
            "title": sn.get("title", ""),
            "channel": sn.get("channelTitle", ""),
            "published": sn.get("publishedAt", "")[:10],
            "url": f"https://youtube.com/watch?v={vid}",
        })
    return out


def youtube_video_stats(video_ids: list, api_key: str) -> list:
    """Get view/like/comment counts for video IDs (to rank what's viral)."""
    if not api_key:
        return []
    ids = ",".join(video_ids[:50])
    url = "https://www.googleapis.com/youtube/v3/videos?" + urllib.parse.urlencode({
        "part": "statistics,snippet", "id": ids, "key": api_key,
    })
    try:
        data = json.loads(_get(url))
    except Exception:
        return []
    out = []
    for it in data.get("items", []):
        st = it.get("statistics", {})
        out.append({
            "title": it.get("snippet", {}).get("title", ""),
            "views": int(st.get("viewCount", 0)),
            "likes": int(st.get("likeCount", 0)),
            "comments": int(st.get("commentCount", 0)),
        })
    out.sort(key=lambda x: x["views"], reverse=True)
    return out
