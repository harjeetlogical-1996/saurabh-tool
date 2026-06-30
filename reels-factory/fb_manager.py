"""
Facebook Page management via Graph API.

Covers everything the Graph API allows for a Page you own:
  - verify token / list pages
  - publish reel / photo / text (and schedule)
  - page insights (analytics)
  - edit page info (about, bio, website, phone, etc.)
  - list / delete posts
  - read comments, reply, auto-reply

NOTE: Facebook does NOT allow creating or deleting a Page via API — that is
done manually on facebook.com. Everything else below works once you have a
Page access token with the right permissions.

Required permissions on the token:
  pages_show_list, pages_read_engagement, pages_manage_posts,
  pages_manage_metadata, pages_manage_engagement,
  pages_read_user_content, read_insights, publish_video
"""
import os
import time

GRAPH = "https://graph.facebook.com/v21.0"


def _requests():
    import requests
    return requests


def _check(resp):
    """Raise a readable error if the Graph API returned one."""
    data = resp.json()
    if isinstance(data, dict) and data.get("error"):
        err = data["error"]
        raise RuntimeError(f"FB API error: {err.get('message')} "
                           f"(code {err.get('code')}, type {err.get('type')})")
    resp.raise_for_status()
    return data


# ---------------------------------------------------------------------------
# TOKEN / PAGE DISCOVERY
# ---------------------------------------------------------------------------
def verify_token(token: str) -> dict:
    """Check a token and return the user + the pages it can manage."""
    requests = _requests()
    me = _check(requests.get(f"{GRAPH}/me",
                             params={"access_token": token}, timeout=30))
    pages = _check(requests.get(f"{GRAPH}/me/accounts",
                                params={"access_token": token, "limit": 100},
                                timeout=30))
    return {"user": me, "pages": pages.get("data", [])}


def get_page_token(user_token: str, page_id: str) -> str:
    """Exchange a user token for the specific Page's access token."""
    requests = _requests()
    data = _check(requests.get(f"{GRAPH}/me/accounts",
                               params={"access_token": user_token, "limit": 100},
                               timeout=30))
    for p in data.get("data", []):
        if str(p.get("id")) == str(page_id):
            return p["access_token"]
    raise RuntimeError(f"Page {page_id} not found among managed pages")


# ---------------------------------------------------------------------------
# PUBLISH:  reel / photo / text  (+ optional schedule)
# ---------------------------------------------------------------------------
def publish_reel(video_path: str, caption: str, page_id: str, token: str,
                 scheduled_time: int = 0) -> dict:
    """
    Upload + publish a reel (resumable upload protocol).
    If scheduled_time (future UNIX timestamp) is given, the reel is SCHEDULED
    on Facebook's servers (so it posts even if your PC is off).
    Range: 10 minutes to 75 days in the future.
    """
    requests = _requests()
    base = f"{GRAPH}/{page_id}/video_reels"
    size = os.path.getsize(video_path)

    start = _check(requests.post(base, data={
        "upload_phase": "start", "access_token": token}, timeout=30))
    video_id = start["video_id"]
    upload_url = start["upload_url"]

    with open(video_path, "rb") as f:
        up = requests.post(upload_url, data=f.read(), headers={
            "Authorization": f"OAuth {token}",
            "offset": "0", "file_size": str(size)}, timeout=600)
    up.raise_for_status()

    fin_data = {
        "upload_phase": "finish", "video_id": video_id,
        "description": caption, "access_token": token,
    }
    if scheduled_time:
        # SCHEDULED publish on FB servers
        fin_data["video_state"] = "SCHEDULED"
        fin_data["scheduled_publish_time"] = str(int(scheduled_time))
    else:
        fin_data["video_state"] = "PUBLISHED"

    fin = _check(requests.post(base, data=fin_data, timeout=60))
    return {"video_id": video_id, "scheduled": bool(scheduled_time), "result": fin}


def publish_text(message: str, page_id: str, token: str,
                 link: str = "", scheduled_time: int = 0) -> dict:
    """Publish a text (optionally with a link) post, or schedule it."""
    requests = _requests()
    data = {"message": message, "access_token": token}
    if link:
        data["link"] = link
    if scheduled_time:
        data["published"] = "false"
        data["scheduled_publish_time"] = str(int(scheduled_time))
    return _check(requests.post(f"{GRAPH}/{page_id}/feed", data=data, timeout=60))


def publish_photo(photo_path: str, caption: str, page_id: str, token: str,
                  scheduled_time: int = 0) -> dict:
    """Publish (or schedule) a photo post."""
    requests = _requests()
    data = {"caption": caption, "access_token": token}
    if scheduled_time:
        data["published"] = "false"
        data["scheduled_publish_time"] = str(int(scheduled_time))
    with open(photo_path, "rb") as f:
        return _check(requests.post(f"{GRAPH}/{page_id}/photos",
                                    data=data, files={"source": f}, timeout=120))


# ---------------------------------------------------------------------------
# ANALYTICS / INSIGHTS
# ---------------------------------------------------------------------------
def page_insights(page_id: str, token: str, period: str = "day") -> dict:
    """
    Return key page metrics. period: day | week | days_28
    """
    requests = _requests()
    metrics = ",".join([
        "page_impressions", "page_impressions_unique",
        "page_post_engagements", "page_fans", "page_fan_adds",
        "page_views_total", "page_video_views",
    ])
    data = _check(requests.get(f"{GRAPH}/{page_id}/insights",
                  params={"metric": metrics, "period": period,
                          "access_token": token}, timeout=30))
    out = {}
    for m in data.get("data", []):
        vals = m.get("values", [])
        out[m["name"]] = vals[-1]["value"] if vals else None
    return out


def top_posts(page_id: str, token: str, limit: int = 10) -> list:
    """Recent posts with engagement counts, best for spotting winners."""
    requests = _requests()
    data = _check(requests.get(f"{GRAPH}/{page_id}/posts",
                  params={"fields": "message,created_time,permalink_url,"
                          "shares,reactions.summary(true),comments.summary(true)",
                          "limit": limit, "access_token": token}, timeout=30))
    rows = []
    for p in data.get("data", []):
        rows.append({
            "id": p.get("id"),
            "message": (p.get("message") or "")[:80],
            "created": p.get("created_time"),
            "reactions": p.get("reactions", {}).get("summary", {}).get("total_count", 0),
            "comments": p.get("comments", {}).get("summary", {}).get("total_count", 0),
            "shares": p.get("shares", {}).get("count", 0),
            "url": p.get("permalink_url"),
        })
    return rows


# ---------------------------------------------------------------------------
# EDIT PAGE INFO
# ---------------------------------------------------------------------------
def update_page_info(page_id: str, token: str, **fields) -> dict:
    """
    Update page fields. Supported keys include:
      about, description, phone, website, emails,
      general_info, company_overview, mission
    Pass only the ones you want to change.
    """
    requests = _requests()
    allowed = {"about", "description", "phone", "website", "emails",
               "general_info", "company_overview", "mission"}
    data = {k: v for k, v in fields.items() if k in allowed and v}
    if not data:
        raise RuntimeError("No valid page fields to update")
    data["access_token"] = token
    return _check(requests.post(f"{GRAPH}/{page_id}", data=data, timeout=30))


def get_page_info(page_id: str, token: str) -> dict:
    """Read current page info."""
    requests = _requests()
    return _check(requests.get(f"{GRAPH}/{page_id}",
                  params={"fields": "name,about,description,phone,website,"
                          "emails,fan_count,followers_count,link",
                          "access_token": token}, timeout=30))


# ---------------------------------------------------------------------------
# POSTS:  list / delete
# ---------------------------------------------------------------------------
def list_posts(page_id: str, token: str, limit: int = 25) -> list:
    requests = _requests()
    data = _check(requests.get(f"{GRAPH}/{page_id}/posts",
                  params={"fields": "message,created_time,permalink_url",
                          "limit": limit, "access_token": token}, timeout=30))
    return data.get("data", [])


def delete_post(post_id: str, token: str) -> dict:
    requests = _requests()
    return _check(requests.delete(f"{GRAPH}/{post_id}",
                  params={"access_token": token}, timeout=30))


# ---------------------------------------------------------------------------
# COMMENTS:  read / reply / auto-reply
# ---------------------------------------------------------------------------
def get_comments(post_id: str, token: str, limit: int = 50) -> list:
    requests = _requests()
    data = _check(requests.get(f"{GRAPH}/{post_id}/comments",
                  params={"fields": "message,from,created_time,like_count",
                          "limit": limit, "order": "reverse_chronological",
                          "access_token": token}, timeout=30))
    return data.get("data", [])


def reply_to_comment(comment_id: str, message: str, token: str) -> dict:
    requests = _requests()
    return _check(requests.post(f"{GRAPH}/{comment_id}/comments",
                  data={"message": message, "access_token": token}, timeout=30))


def auto_reply_post(post_id: str, token: str, reply_text: str,
                    only_unreplied: bool = True, limit: int = 50) -> dict:
    """
    Reply to every top-level comment on a post with reply_text.
    Simple engagement booster. Returns count of replies sent.
    """
    comments = get_comments(post_id, token, limit=limit)
    sent = 0
    for c in comments:
        try:
            reply_to_comment(c["id"], reply_text, token)
            sent += 1
            time.sleep(0.5)  # be gentle with rate limits
        except Exception:
            pass
    return {"comments_seen": len(comments), "replies_sent": sent}
