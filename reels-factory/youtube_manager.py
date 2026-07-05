"""
YouTube Shorts upload + schedule via the YouTube Data API v3.

Auth: OAuth 2.0 (user consent) — a one-time browser login creates a saved
token (yt_token.json). After that, uploads are automatic.

Quota note: default project quota is 10,000 units/day; each upload costs
~1,600 units => about 6 uploads/day. Request more from Google if needed.

A 1080x1920 vertical mp4 under 60s with #Shorts in the title/description is
treated as a Short automatically.
"""
import os
from pathlib import Path

BASE = Path(__file__).parent
YT_DIR = BASE / "yt_tokens"          # one token file per channel
YT_DIR.mkdir(exist_ok=True)
CLIENT_SECRET_FILE = BASE / "yt_client_secret.json"  # downloaded from Google
SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube"]


def _token_path(channel: str = "default") -> Path:
    safe = "".join(c for c in channel if c.isalnum() or c in "-_") or "default"
    return YT_DIR / f"{safe}.json"


def list_channels() -> list:
    """Nicknames of all authorized channels (token files present)."""
    return sorted(p.stem for p in YT_DIR.glob("*.json"))


def _get_service(channel: str = "default"):
    """Build an authenticated YouTube service for a given channel nickname."""
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    tok = _token_path(channel)
    if not tok.exists():
        avail = list_channels()
        raise RuntimeError(
            f"Channel '{channel}' not authorized. Authorized: {avail or 'none'}. "
            f"Run yt_authorize(channel='{channel}') first.")
    creds = Credentials.from_authorized_user_file(str(tok), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        tok.write_text(creds.to_json())
    return build("youtube", "v3", credentials=creds)


def authorize(channel: str = "default") -> str:
    """
    One-time OAuth for ONE channel. Opens a browser — pick the channel you
    want in Google's account chooser, consent, and the token is saved under
    that nickname. Repeat with a different `channel` for each channel.
    """
    from google_auth_oauthlib.flow import InstalledAppFlow
    if not CLIENT_SECRET_FILE.exists():
        raise RuntimeError(
            "yt_client_secret.json missing. Download an OAuth Client (Desktop "
            "app) from Google Cloud -> Credentials, save it here.")
    flow = InstalledAppFlow.from_client_secrets_file(
        str(CLIENT_SECRET_FILE), SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent")
    tok = _token_path(channel)
    tok.write_text(creds.to_json())
    # confirm which channel got linked
    try:
        from googleapiclient.discovery import build
        svc = build("youtube", "v3", credentials=creds)
        r = svc.channels().list(part="snippet", mine=True).execute()
        name = r["items"][0]["snippet"]["title"] if r.get("items") else "?"
        return f"Authorized '{channel}' -> YouTube channel: {name}"
    except Exception:
        return f"Authorized and saved as '{channel}'"


def upload_short(video_path: str, title: str, description: str = "",
                 tags: list = None, privacy: str = "public",
                 publish_at: str = "", category_id: str = "22",
                 channel: str = "default") -> dict:
    """
    Upload a vertical mp4 as a YouTube Short.

    title:       video title (append #Shorts to help classification)
    description: description text (hashtags ok)
    tags:        list of tag strings
    privacy:     public | unlisted | private
    publish_at:  RFC3339 UTC time to SCHEDULE (e.g. "2026-07-01T13:00:00Z").
                 If set, privacy is forced to 'private' until that time.
    category_id: 22 = People & Blogs (safe default)
    """
    from googleapiclient.http import MediaFileUpload

    yt = _get_service(channel)
    if "#Shorts" not in title and "#shorts" not in title:
        title = f"{title} #Shorts"
    status = {"privacyStatus": privacy,
              "selfDeclaredMadeForKids": False}
    if publish_at:
        status["privacyStatus"] = "private"
        status["publishAt"] = publish_at  # RFC3339, must be future UTC

    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:4900],
            "tags": (tags or [])[:30],
            "categoryId": category_id,
        },
        "status": status,
    }
    media = MediaFileUpload(video_path, chunksize=-1, resumable=True,
                            mimetype="video/mp4")
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    vid = resp.get("id")
    return {"video_id": vid, "url": f"https://youtube.com/shorts/{vid}",
            "scheduled": bool(publish_at)}


def set_thumbnail(video_id: str, image_path: str,
                  channel: str = "default") -> dict:
    from googleapiclient.http import MediaFileUpload
    yt = _get_service(channel)
    yt.thumbnails().set(videoId=video_id,
                        media_body=MediaFileUpload(image_path)).execute()
    return {"ok": True}


def channel_info(channel: str = "default") -> dict:
    yt = _get_service(channel)
    r = yt.channels().list(part="snippet,statistics", mine=True).execute()
    items = r.get("items", [])
    if not items:
        return {"error": "no channel"}
    c = items[0]
    return {"title": c["snippet"]["title"],
            "subs": c["statistics"].get("subscriberCount", "0"),
            "videos": c["statistics"].get("videoCount", "0")}
