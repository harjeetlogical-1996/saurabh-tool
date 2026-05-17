"""
FastAPI backend for tools.saurabhbhayana.com.

Auth model
----------
The marketing site (saurabhbhayana.com) runs Better Auth with a session
cookie scoped to the parent domain ".saurabhbhayana.com" in production.
Every subdomain — including this one — reads the same cookie. We don't
re-implement auth here; we just validate the incoming session against the
shared Mongo `session` collection.

Cookie name: f"{AUTH_COOKIE_PREFIX}.session_token"
  Default Better Auth shape is "<value>.<signature>" — we trust the
  signature only because the user already presented it AND the row exists
  in Mongo with a matching token + unexpired `expiresAt`.
"""

from __future__ import annotations

import os
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Depends, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pymongo import MongoClient
from pymongo.collection import Collection

# Load .env if present (no-op when env is supplied by the host)
load_dotenv()

from auth import current_user, AuthUser  # noqa: E402
from keyvault import encrypt, decrypt, mask  # noqa: E402
import jobs  # noqa: E402
import billing  # noqa: E402
import plans as plans_mod  # noqa: E402
from media_probe import audio_duration_seconds  # noqa: E402
from tools import (  # noqa: E402
    audio_to_video,
    bulk_captions,
    bulk_captions_render,
    captions,
    voice_pair,
)

ROOT = Path(__file__).parent
UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR", ROOT / "uploads"))
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", ROOT / "outputs"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_ORIGINS = [
    o.strip()
    for o in os.environ.get("ALLOWED_ORIGINS", "http://localhost:3010").split(",")
    if o.strip()
]


def _mongo() -> MongoClient:
    uri = os.environ.get("MONGODB_URI")
    if not uri:
        raise RuntimeError("MONGODB_URI is not set")
    return MongoClient(uri)


_client: Optional[MongoClient] = None


def db():
    """Lazy Mongo client, cached for the process lifetime."""
    global _client
    if _client is None:
        _client = _mongo()
    return _client[os.environ.get("MONGODB_DB", "saurabh")]


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Start the job worker once FastAPI is ready, and clean up on exit."""
    jobs.register_handler("audio-to-video", audio_to_video.handle)
    jobs.register_handler("captions", captions.handle)
    jobs.register_handler("bulk-captions", bulk_captions.handle)
    jobs.register_handler("bulk-captions-render", bulk_captions_render.handle)
    jobs.register_handler("voice-pair", voice_pair.handle)
    jobs.start_worker_thread()
    yield


app = FastAPI(title="Saurabh Tools API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,  # required so the Better Auth cookie travels
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


# ---------- Public ----------------------------------------------------------


@app.get("/health")
def health():
    return {
        "ok": True,
        "service": "saurabh-tools-api",
        "ts": datetime.now(timezone.utc).isoformat(),
    }


# ---------- Authenticated --------------------------------------------------


@app.get("/me")
def me(user: AuthUser = Depends(current_user)):
    """
    Return the signed-in user with plan + minute usage. Frontend hits
    this on every page load to render usage bars and gate UI.
    """
    settings = db().tool_settings.find_one({"userId": user.id}) or {}
    a2v_sub = billing.get_or_create_subscription(user.id, user.plan, tool="audio-to-video")
    cap_sub = billing.get_or_create_subscription(user.id, "caption_free", tool="captions")
    a2v_view = billing.serialize_subscription(a2v_sub)
    cap_view = billing.serialize_subscription(cap_sub)
    plan_def = plans_mod.get_plan(a2v_view["plan"])
    is_byo = _user_is_byo(user)
    gemini_mask = (
        mask(settings.get("geminiKey"))
        if is_byo and settings.get("geminiKey")
        else None
    )
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "role": user.role,
        # ---- audio-to-video tool subscription ----
        "plan": a2v_view["plan"],
        "planName": a2v_view["planName"],
        "planMode": plan_def["mode"],
        "minutesUsed": a2v_view["minutesUsed"],
        "minutesLimit": a2v_view["minutesLimit"],
        "topUpMinutesRemaining": a2v_view["topUpMinutesRemaining"],
        "cycleStartAt": a2v_view["cycleStartAt"],
        "cycleEndAt": a2v_view["cycleEndAt"],
        "subscriptionStatus": a2v_view["status"],
        "unlimited": a2v_view["unlimited"],
        # ---- captions tool subscription ----
        "captionPlan": cap_view["plan"],
        "captionPlanName": cap_view["planName"],
        "captionMinutesUsed": cap_view["minutesUsed"],
        "captionMinutesLimit": cap_view["minutesLimit"],
        "captionTopUpMinutesRemaining": cap_view["topUpMinutesRemaining"],
        "captionCycleEndAt": cap_view["cycleEndAt"],
        # ---- BYO key (only for BYO-mode users) ----
        "geminiKeyMask": gemini_mask,
        "byoMode": is_byo,
    }


@app.get("/me/subscription")
def my_subscription(user: AuthUser = Depends(current_user)):
    """
    Detailed subscription view — used by the billing settings screen.
    Returns both audio-to-video and captions subscriptions side-by-side.
    """
    a2v = billing.get_or_create_subscription(user.id, user.plan, tool="audio-to-video")
    cap = billing.get_or_create_subscription(user.id, "caption_free", tool="captions")
    return {
        "audioToVideo": billing.serialize_subscription(a2v),
        "captions": billing.serialize_subscription(cap),
    }


@app.get("/plans")
def list_plans():
    """Public — list of plans + top-ups for the pricing page."""
    return {
        "plans": plans_mod.public_plans(),
        "topups": plans_mod.public_topups(),
        "currency": "INR",
        "gstPercent": 18,
        "gstNote": "GST 18% extra on listed prices.",
    }


@app.post("/me/api-key")
async def save_api_key(
    request: Request,
    user: AuthUser = Depends(current_user),
):
    """
    Encrypt and store the user's Gemini API key. Stores the encrypted
    payload only — we never log the plaintext, and we never echo it back.
    The frontend can only see a masked preview ("AIza••••••8tU").
    """
    if not _user_is_byo(user):
        raise HTTPException(
            status_code=403,
            detail="API keys are only relevant on bring-your-own-key plans.",
        )
    body = await request.json()
    raw = (body.get("key") or "").strip()
    if not raw or len(raw) < 20:
        raise HTTPException(status_code=400, detail="That doesn't look like a valid Gemini API key.")

    encrypted = encrypt(raw)
    db().tool_settings.update_one(
        {"userId": user.id},
        {
            "$set": {
                "userId": user.id,
                "geminiKey": encrypted,
                "geminiKeyUpdatedAt": datetime.now(timezone.utc),
            },
            "$setOnInsert": {
                "rendersUsed": 0,
                "renderLimit": 1,
                "createdAt": datetime.now(timezone.utc),
            },
        },
        upsert=True,
    )
    return {"ok": True, "geminiKeyMask": mask(encrypted)}


@app.delete("/me/api-key")
def delete_api_key(user: AuthUser = Depends(current_user)):
    if not _user_is_byo(user):
        raise HTTPException(
            status_code=403,
            detail="API keys are only relevant on bring-your-own-key plans.",
        )
    db().tool_settings.update_one(
        {"userId": user.id},
        {"$unset": {"geminiKey": "", "geminiKeyUpdatedAt": ""}},
    )
    return {"ok": True}


@app.post("/me/api-key/test")
def test_api_key(user: AuthUser = Depends(current_user)):
    """
    Hits Gemini's models.list endpoint with the user's stored key. Cheap,
    no compute charged, and conclusively proves the key works. We never
    return or log the plaintext key.
    """
    if not _user_is_byo(user):
        raise HTTPException(
            status_code=403,
            detail="API keys are only relevant on bring-your-own-key plans.",
        )
    settings = db().tool_settings.find_one({"userId": user.id})
    if not settings or not settings.get("geminiKey"):
        raise HTTPException(status_code=400, detail="No Gemini API key saved yet.")
    try:
        plaintext = decrypt(settings["geminiKey"])
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Stored key could not be decrypted. Re-save your key.",
        )

    import requests as _req

    try:
        r = _req.get(
            "https://generativelanguage.googleapis.com/v1beta/models",
            params={"key": plaintext, "pageSize": 1},
            timeout=15,
        )
    except _req.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Couldn't reach Gemini: {e}")

    if r.status_code == 200:
        body = r.json() if r.content else {}
        sample_model = (body.get("models") or [{}])[0].get("name", "unknown")
        return {"ok": True, "sampleModel": sample_model}

    if r.status_code in (400, 401, 403):
        try:
            err = r.json().get("error", {}).get("message", "Invalid key.")
        except Exception:
            err = "Invalid key."
        raise HTTPException(status_code=400, detail=f"Gemini rejected the key: {err}")

    raise HTTPException(
        status_code=502,
        detail=f"Gemini responded with HTTP {r.status_code}.",
    )


# ---------- Render jobs -----------------------------------------------------


# Plans that fully bypass minute quotas (admin / internal).
UNLIMITED_PLANS = plans_mod.UNLIMITED_PLANS


def _is_unlimited(user: AuthUser) -> bool:
    return user.plan in UNLIMITED_PLANS


def _user_is_byo(user: AuthUser) -> bool:
    """
    True if this user must supply their own Gemini key. Triggers when:
      - User is on any byo_* plan tier
      - User id is in the BYO_KEY_USERS env list (or runtime config)
      - Legacy: plan == "byo" string match
    """
    import os as _os
    if user.plan == "byo" or plans_mod.is_byo_plan(user.plan):
        return True
    byo_set = {u.strip() for u in _os.environ.get("BYO_KEY_USERS", "").split(",") if u.strip()}
    if user.id in byo_set:
        return True
    # Runtime config override (admin UI)
    try:
        import runtime_config as _rc
        if user.id in _rc.get_byo_user_ids():
            return True
    except Exception:
        pass
    return False


def _user_has_api_key(user: AuthUser) -> bool:
    settings = db().tool_settings.find_one({"userId": user.id}) or {}
    return bool(settings.get("geminiKey"))


ALLOWED_AUDIO_EXTS = {".mp3", ".m4a", ".wav", ".aac", ".ogg", ".flac"}
MAX_AUDIO_BYTES = 50 * 1024 * 1024
MAX_BULK_FILES = 50


def _make_project(
    name: Optional[str],
    *,
    user_id: Optional[str] = None,
    existing_project_id: Optional[str] = None,
) -> tuple[str, str]:
    """Generate (projectId, projectName) for a submit.

    Modes:
      - existing_project_id supplied: look up the project's existing
        name on any prior job belonging to this user and reuse both,
        so new uploads merge into the same group.
      - name supplied: create a NEW project with that name.
      - neither: create a new project with a "Project · <date>" name.
    """
    if existing_project_id and user_id:
        # Pull the project name from any of this user's jobs that
        # already carry this projectId. If no match, treat as new.
        doc = db().tool_jobs.find_one(
            {"userId": user_id, "projectId": existing_project_id},
            {"projectName": 1},
        )
        if doc and doc.get("projectName"):
            return existing_project_id, str(doc["projectName"])
        # Fell through (invalid id from client) — fall through to new project.
    project_id = str(uuid.uuid4())
    if name and name.strip():
        clean_name = name.strip()[:80]
    else:
        # Local-ish date+time so the user sees their timezone in the UI.
        # Mongo timestamps are still UTC; this is just a label.
        now = datetime.now(timezone.utc).astimezone()
        clean_name = f"Project · {now.strftime('%b %d, %I:%M %p')}"
    return project_id, clean_name

# Bulk caption tool: accepts already-edited videos.
ALLOWED_VIDEO_EXTS = {".mp4", ".mov", ".webm", ".mkv", ".m4v"}
MAX_VIDEO_BYTES = 200 * 1024 * 1024  # 200 MB per video — most reels are <50 MB

# Voice Pair tool: image OR video on the media side, audio on the voice side.
ALLOWED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_IMAGE_BYTES = 25 * 1024 * 1024
# Reuse audio + video constants above for the rest. Pair upload caps at
# MAX_BULK_FILES per request (50), same as a2v.


# Languages we explicitly support for the scene-planning prompt hint.
# Anything else falls back to "auto" which lets Gemini detect the language
# itself. Mirrors AUDIO_LANGUAGE_HINTS in tools/audio_to_video.py.
ALLOWED_AUDIO_LANGUAGES = {
    "auto", "english", "hindi", "hinglish", "marathi", "tamil", "bengali",
    "gujarati", "punjabi", "telugu", "kannada", "malayalam",
    "spanish", "french", "german", "portuguese",
    "japanese", "korean", "arabic", "other",
}


def _normalize_options(
    size: str,
    style_preset: str,
    segment_seconds,  # may be a float OR the string "auto"
    animation_style: str,
    audio_language: str = "auto",
) -> dict:
    if size not in {"9:16", "16:9", "1:1", "4:5"}:
        size = "9:16"
    if style_preset not in {"photoreal", "cinematic", "3d_pixar", "anime", "watercolor", "comic"}:
        style_preset = "photoreal"
    if animation_style not in {
        "ken_burns", "zoom_in", "zoom_out", "pan_lr", "pan_rl", "pulse",
        "mixed", "none",
    }:
        animation_style = "ken_burns"
    # segment_seconds can be the literal "auto" (Gemini decides per-scene
    # length) or a number in [1.5, 8.0] for fixed-length scenes.
    seg_val: Any
    raw = segment_seconds
    if isinstance(raw, str) and raw.strip().lower() == "auto":
        seg_val = "auto"
    else:
        try:
            seg_val = max(1.5, min(8.0, float(raw)))
        except (TypeError, ValueError):
            seg_val = "auto"
    lang = (audio_language or "auto").lower().strip()
    if lang not in ALLOWED_AUDIO_LANGUAGES:
        lang = "auto"
    return {
        "size": size,
        "style_preset": style_preset,
        "segment_seconds": seg_val,
        "animation_style": animation_style,
        "audio_language": lang,
    }


async def _save_audio_upload(user_id: str, audio: UploadFile) -> tuple[Path, int]:
    """Stream an upload to a per-job folder. Returns (path, byte_count)."""
    if not audio.filename:
        raise HTTPException(status_code=400, detail="No file uploaded.")
    ext = (Path(audio.filename).suffix or ".mp3").lower()
    if ext not in ALLOWED_AUDIO_EXTS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format: {ext}. Use mp3, m4a, wav, aac, ogg, or flac.",
        )

    job_uuid = str(uuid.uuid4())
    job_dir = UPLOAD_DIR / user_id / job_uuid
    job_dir.mkdir(parents=True, exist_ok=True)
    audio_path = job_dir / f"input{ext}"

    size_bytes = 0
    with audio_path.open("wb") as f:
        while True:
            chunk = await audio.read(1024 * 1024)
            if not chunk:
                break
            size_bytes += len(chunk)
            if size_bytes > MAX_AUDIO_BYTES:
                f.close()
                audio_path.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail=f"{audio.filename}: file too large (50 MB max).")
            f.write(chunk)
    return audio_path, size_bytes


@app.post("/me/jobs/audio-to-video")
async def submit_audio_to_video(
    audio: list[UploadFile] = File(...),
    label: str = Form(""),
    size: str = Form("9:16"),
    style_preset: str = Form("photoreal"),
    segment_seconds: str = Form("auto"),
    animation_style: str = Form("ken_burns"),
    audio_language: str = Form("auto"),
    projectName: str = Form(""),
    projectId: str = Form(""),
    user: AuthUser = Depends(current_user),
):
    """
    Bulk-friendly submit. Accepts 1..MAX_BULK_FILES audio files in one
    request. Files that fit under the user's render quota are queued
    immediately. Files beyond the quota are saved and recorded as
    'blocked' so the user doesn't have to re-upload after subscribing.

    Response shape:
      {
        "queued":  [job, ...],
        "blocked": [job, ...],
        "rejected": [{filename, reason}, ...]   # malformed files only
      }
    """
    # BYO-key users (code-sale tier) must supply their Gemini key. Platform
    # subscribers rely on the rotator — no key needed.
    if _user_is_byo(user) and not _user_has_api_key(user):
        raise HTTPException(
            status_code=400,
            detail="Save your Gemini API key in Settings before rendering.",
        )
    if not audio:
        raise HTTPException(status_code=400, detail="No files uploaded.")
    if len(audio) > MAX_BULK_FILES:
        raise HTTPException(
            status_code=400,
            detail=f"Too many files in one submit ({len(audio)} > {MAX_BULK_FILES}).",
        )

    options = _normalize_options(
        size, style_preset, segment_seconds, animation_style, audio_language,
    )

    # Minute-budget snapshot. We drain `remaining_seconds` as we accept
    # each upload so a bulk submit that exceeds the budget blocks the
    # overflow but still queues what fits. BYO plans still meter
    # minutes (compute is the limit), only owner truly bypasses.
    sub = billing.get_or_create_subscription(user.id, user.plan, tool="audio-to-video")
    unlimited = _is_unlimited(user)
    remaining_sec = 10 ** 9 if unlimited else billing.remaining_seconds(sub)

    queued: list[dict] = []
    blocked: list[dict] = []
    rejected: list[dict] = []

    # Group all jobs in this submit under a single project for the UI.
    # If projectId is supplied, append to that existing project.
    project_id, project_name = _make_project(
        projectName, user_id=user.id, existing_project_id=projectId or None,
    )

    for idx, file in enumerate(audio):
        # Save first so blocked jobs still have the audio on disk.
        try:
            audio_path, size_bytes = await _save_audio_upload(user.id, file)
        except HTTPException as e:
            rejected.append({"filename": file.filename or "?", "reason": e.detail})
            continue

        # Probe duration NOW so we know how much budget this clip costs.
        # If ffprobe can't read it we still accept (the worker will fail
        # cleanly and we won't burn the user's minutes).
        duration_sec = audio_duration_seconds(audio_path)

        params = {
            "audioPath": str(audio_path),
            "audioFilename": file.filename,
            "audioBytes": size_bytes,
            "audioDurationSec": duration_sec,
            "label": (label[:80]) if label else "",
            "options": options,
            "userPlan": user.plan,
        }

        # A clip costs ceil(duration). If duration unknown we use a 0
        # placeholder — failing fast in the worker is better than refusing
        # to queue a valid audio file because ffprobe choked.
        cost_sec = int(round(duration_sec))

        if unlimited or remaining_sec >= cost_sec:
            jid = jobs.create_job(
                user_id=user.id, tool="audio-to-video", params=params,
                project_id=project_id, project_name=project_name,
            )
            jobs.enqueue(jid, user.id)
            if not unlimited:
                remaining_sec -= cost_sec
            doc = jobs.get_job(jid, user_id=user.id)
            if doc:
                queued.append(jobs.serialize_job(doc))
        else:
            jid = jobs.create_blocked_job(
                user_id=user.id,
                tool="audio-to-video",
                params=params,
                reason=(
                    f"Needs {cost_sec}s but only {remaining_sec}s left this cycle. "
                    "Upgrade your plan or buy a top-up to render this video."
                ),
                project_id=project_id,
                project_name=project_name,
            )
            doc = jobs.get_job(jid, user_id=user.id)
            if doc:
                blocked.append(jobs.serialize_job(doc))

    return {
        "queued": queued,
        "blocked": blocked,
        "rejected": rejected,
        "summary": {
            "uploaded": len(audio),
            "queued": len(queued),
            "blocked": len(blocked),
            "rejected": len(rejected),
        },
        "projectId": project_id,
        "projectName": project_name,
    }


async def _save_video_upload(user_id: str, video: UploadFile) -> tuple[Path, int]:
    """Stream a video upload to a per-job folder. Returns (path, bytes)."""
    if not video.filename:
        raise HTTPException(status_code=400, detail="No file uploaded.")
    ext = (Path(video.filename).suffix or ".mp4").lower()
    if ext not in ALLOWED_VIDEO_EXTS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported video format: {ext}. Use mp4, mov, webm, mkv, or m4v.",
        )

    job_uuid = str(uuid.uuid4())
    job_dir = UPLOAD_DIR / user_id / job_uuid
    job_dir.mkdir(parents=True, exist_ok=True)
    video_path = job_dir / f"input{ext}"

    size_bytes = 0
    with video_path.open("wb") as f:
        while True:
            chunk = await video.read(1024 * 1024)
            if not chunk:
                break
            size_bytes += len(chunk)
            if size_bytes > MAX_VIDEO_BYTES:
                f.close()
                video_path.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=413,
                    detail=f"{video.filename}: file too large (200 MB max).",
                )
            f.write(chunk)
    return video_path, size_bytes


def _normalize_caption_options(
    style: str,
    position: str,
    words_per_line: float,
    uppercase: bool,
    pos_x_frac: Optional[float] = None,
    pos_y_frac: Optional[float] = None,
    # Customize tab overrides (any subset).
    primary_color: Optional[str] = None,
    outline_color: Optional[str] = None,
    outline_width: Optional[int] = None,
    bg_color: Optional[str] = None,
    bg_alpha: Optional[int] = None,
    font_size: Optional[int] = None,
    font_family: Optional[str] = None,
    shadow: Optional[int] = None,
) -> dict:
    if style not in {
        # Original 8
        "plain", "bold", "highlight", "karaoke",
        "outline", "neon", "gradient", "typewriter",
        # 10 new (classic / trendy / minimal / decorative)
        "news", "cinema",
        "mrbeast", "reels", "tiktok",
        "whisper", "underline",
        "sticker", "comic", "retro",
    }:
        style = "bold"
    if position not in {"top", "middle", "bottom"}:
        position = "bottom"
    try:
        wpl = int(words_per_line)
    except (TypeError, ValueError):
        wpl = 2
    wpl = max(1, min(8, wpl))

    def _frac(v: Optional[float]) -> Optional[float]:
        if v is None:
            return None
        try:
            f = float(v)
        except (TypeError, ValueError):
            return None
        return max(0.0, min(1.0, f))

    out = {
        "style": style,
        "position": position,
        "wordsPerLine": wpl,
        "uppercase": bool(uppercase),
    }
    px = _frac(pos_x_frac)
    py = _frac(pos_y_frac)
    if px is not None:
        out["posXFrac"] = px
    if py is not None:
        out["posYFrac"] = py

    # Customize-tab overrides. Stored only when explicitly provided so
    # the worker still falls back to preset values for fields the user
    # didn't touch.
    def _int_in(v, lo, hi) -> Optional[int]:
        if v is None:
            return None
        try:
            return max(lo, min(hi, int(v)))
        except (TypeError, ValueError):
            return None

    def _color(v) -> Optional[str]:
        if v is None:
            return None
        s = str(v).strip()
        return s or None

    pc = _color(primary_color)
    if pc:
        out["primaryColor"] = pc
    oc = _color(outline_color)
    if oc:
        out["outlineColor"] = oc
    bc = _color(bg_color)
    if bc:
        out["bgColor"] = bc
    ff = _color(font_family)
    if ff:
        out["fontFamily"] = ff
    ow = _int_in(outline_width, 0, 20)
    if ow is not None:
        out["outlineWidth"] = ow
    ba = _int_in(bg_alpha, 0, 255)
    if ba is not None:
        out["bgAlpha"] = ba
    fs = _int_in(font_size, 12, 200)
    if fs is not None:
        out["fontSize"] = fs
    sh = _int_in(shadow, 0, 20)
    if sh is not None:
        out["shadow"] = sh
    return out


@app.post("/me/jobs/captions-bulk")
async def submit_bulk_captions(
    video: list[UploadFile] = File(...),
    projectName: str = Form(""),
    # Pass an existing projectId to add these videos to that project
    # instead of creating a new one. Otherwise a new project is created.
    projectId: str = Form(""),
    # Optional language hint for the transcriber. Hindi/Urdu are
    # phonetically close enough that Whisper's auto-detect frequently
    # flips between them on short clips. "auto" lets the engine choose.
    language: str = Form("auto"),
    user: AuthUser = Depends(current_user),
):
    """
    STAGE 1 of the bulk caption tool: upload + transcribe only.

    Each file becomes a `bulk-captions` job that extracts audio,
    transcribes via Gemini Flash, and saves the word-level transcript
    on the job. NO captions are burned at this stage — the user opens
    each transcribed video in the editor screen and tunes
    style/position/X-Y/words-per-line on top of the live video, then
    triggers `/me/jobs/captions-render` when satisfied.

    Quota: transcription is free. The render step is what burns a credit.
    """
    # Only BYO-key plans need a personal key; Hosted users get the platform key.
    if _user_is_byo(user) and not _user_has_api_key(user):
        raise HTTPException(
            status_code=400,
            detail="Save your Gemini API key in Settings before captioning videos.",
        )
    if not video:
        raise HTTPException(status_code=400, detail="No files uploaded.")
    if len(video) > MAX_BULK_FILES:
        raise HTTPException(
            status_code=400,
            detail=f"Too many files in one submit ({len(video)} > {MAX_BULK_FILES}).",
        )

    # Pre-flight: how much budget the caller has. We can't probe video
    # duration up-front (videos can be huge — that's a worker step) so
    # the worker re-checks at start; this initial gate is just so we
    # don't accept uploads from a user with literally 0 minutes left.
    sub = billing.get_or_create_subscription(user.id, "caption_free", tool="captions")
    has_budget = _is_unlimited(user) or billing.remaining_seconds(sub) > 0

    queued: list[dict] = []
    blocked: list[dict] = []
    rejected: list[dict] = []

    # Group all jobs in this submit under a single project for the UI.
    # If projectId is supplied AND matches one of the user's existing
    # projects, append to that project instead of creating a new one.
    project_id, project_name = _make_project(
        projectName, user_id=user.id, existing_project_id=projectId or None,
    )

    for file in video:
        try:
            video_path, size_bytes = await _save_video_upload(user.id, file)
        except HTTPException as e:
            rejected.append({"filename": file.filename or "?", "reason": e.detail})
            continue

        params = {
            "videoPath": str(video_path),
            "videoFilename": file.filename,
            "videoBytes": size_bytes,
            "label": file.filename or "Video",
            "userPlan": user.plan,
            "language": (language or "auto").lower(),
        }
        if has_budget:
            jid = jobs.create_job(
                user_id=user.id, tool="bulk-captions", params=params,
                project_id=project_id, project_name=project_name,
            )
            jobs.enqueue(jid, user.id)
            doc = jobs.get_job(jid, user_id=user.id)
            if doc:
                queued.append(jobs.serialize_job(doc))
        else:
            jid = jobs.create_blocked_job(
                user_id=user.id,
                tool="bulk-captions",
                params=params,
                reason="Out of minutes this cycle. Upgrade or buy a top-up.",
                project_id=project_id,
                project_name=project_name,
            )
            doc = jobs.get_job(jid, user_id=user.id)
            if doc:
                blocked.append(jobs.serialize_job(doc))

    return {
        "queued": queued,
        "blocked": blocked,
        "rejected": rejected,
        "summary": {
            "uploaded": len(video),
            "queued": len(queued),
            "blocked": len(blocked),
            "rejected": len(rejected),
        },
        "projectId": project_id,
        "projectName": project_name,
    }


@app.post("/me/jobs/captions-render")
def submit_captions_render(
    payload: dict,
    user: AuthUser = Depends(current_user),
):
    """
    STAGE 2: burn the chosen caption style onto a transcribed video.

    Body: {
      "parentJobId": "<bulk-captions transcribe job id>",
      "style": "...", "position": "top|middle|bottom",
      "wordsPerLine": int, "uppercase": bool,
      "posXFrac": float (0..1, optional), "posYFrac": float (0..1, optional)
    }
    `posXFrac`/`posYFrac` express the caption center as a fraction of
    source frame width/height — produced by the editor's drag handle.

    Quota: each render burns one credit on first download. Re-rendering
    the same parent (e.g. user wants a different style) creates a new
    render job — that's a fresh credit charge.
    """
    parent_id = (payload or {}).get("parentJobId")
    if not parent_id or not isinstance(parent_id, str):
        raise HTTPException(status_code=400, detail="parentJobId is required.")

    parent = jobs.get_job(parent_id, user_id=user.id)
    if not parent:
        raise HTTPException(status_code=404, detail="Parent transcribe job not found.")
    if parent.get("tool") != "bulk-captions":
        raise HTTPException(
            status_code=400,
            detail="Parent job is not a bulk-caption transcribe job.",
        )
    if parent.get("status") != "done":
        raise HTTPException(status_code=400, detail="Parent job isn't ready.")
    if not parent.get("transcriptWords"):
        raise HTTPException(status_code=400, detail="Parent has no transcript.")

    options = _normalize_caption_options(
        payload.get("style") or "bold",
        payload.get("position") or "bottom",
        payload.get("wordsPerLine") or 2,
        bool(payload.get("uppercase", False)),
        payload.get("posXFrac"),
        payload.get("posYFrac"),
        primary_color=payload.get("primaryColor"),
        outline_color=payload.get("outlineColor"),
        outline_width=payload.get("outlineWidth"),
        bg_color=payload.get("bgColor"),
        bg_alpha=payload.get("bgAlpha"),
        font_size=payload.get("fontSize"),
        font_family=payload.get("fontFamily"),
        shadow=payload.get("shadow"),
    )

    # Quota: captioning a transcribed video costs its full duration in
    # minutes (same as a fresh audio-to-video render — the heavy work is
    # the burn-in). Owners + BYO skip.
    video_dur = float(parent.get("videoDuration") or 0)
    # Captioned render is much cheaper than audio-to-video — apply the
    # bulk-captions-render multiplier (0.25x) so we don't burn the user's
    # whole monthly allowance on a single caption pass.
    mult = billing.cost_multiplier("bulk-captions-render")
    cost_sec = int(round(video_dur * mult)) if video_dur > 0 else 0
    if not _is_unlimited(user):
        sub = billing.get_or_create_subscription(user.id, "caption_free", tool="captions")
        if cost_sec > 0 and billing.remaining_seconds(sub) < cost_sec:
            raise HTTPException(
                status_code=402,
                detail=(
                    f"Needs {cost_sec}s but only {billing.remaining_seconds(sub)}s "
                    "left this cycle on your Caption plan. Upgrade your captions plan."
                ),
            )

    db_job_id = jobs.create_job(
        user_id=user.id,
        tool="bulk-captions-render",
        params={
            "parentJobId": parent_id,
            "videoFilename": (parent.get("params") or {}).get("videoFilename"),
            "videoDurationSec": video_dur,
            "label": f"Captioned · {options['style']}",
            "options": options,
            "userPlan": user.plan,
        },
    )
    jobs.enqueue(db_job_id, user.id)

    doc = jobs.get_job(db_job_id, user_id=user.id)
    return jobs.serialize_job(doc) if doc else {"id": db_job_id, "status": "queued"}


@app.post("/me/jobs/captions-render-bulk")
def submit_captions_render_bulk(
    payload: dict,
    user: AuthUser = Depends(current_user),
):
    """
    Apply the same caption style to MANY transcribed videos at once.

    Body: {
      "parentJobIds": ["<id1>", "<id2>", ...],   # all must be bulk-captions
      "style": "...", "position": "top|middle|bottom",
      "wordsPerLine": int, "uppercase": bool,
      ...all the Customize-tab overrides too...
    }

    Per-video the cost is captions-render multiplier × source duration.
    We pre-check the COMBINED cost against the user's caption-tool budget
    before enqueuing anything. Either the whole batch fits, or we 402 the
    request so the user upgrades / drops a few videos first.

    Returns: { queued: [job, ...], rejected: [{parentJobId, reason}, ...],
               summary: { uploaded, queued, rejected, totalSeconds } }
    """
    ids = (payload or {}).get("parentJobIds")
    if not isinstance(ids, list) or not ids:
        raise HTTPException(status_code=400, detail="parentJobIds is required.")
    if len(ids) > MAX_BULK_FILES:
        raise HTTPException(
            status_code=400,
            detail=f"Too many videos in one batch ({len(ids)} > {MAX_BULK_FILES}).",
        )

    options = _normalize_caption_options(
        payload.get("style") or "bold",
        payload.get("position") or "bottom",
        payload.get("wordsPerLine") or 2,
        bool(payload.get("uppercase", False)),
        payload.get("posXFrac"),
        payload.get("posYFrac"),
        primary_color=payload.get("primaryColor"),
        outline_color=payload.get("outlineColor"),
        outline_width=payload.get("outlineWidth"),
        bg_color=payload.get("bgColor"),
        bg_alpha=payload.get("bgAlpha"),
        font_size=payload.get("fontSize"),
        font_family=payload.get("fontFamily"),
        shadow=payload.get("shadow"),
    )

    # First pass: validate every parent + total budget needed.
    rejected: list[dict] = []
    valid_parents: list[dict] = []
    total_cost_sec = 0
    mult = billing.cost_multiplier("bulk-captions-render")
    for pid in ids:
        if not isinstance(pid, str):
            rejected.append({"parentJobId": str(pid), "reason": "Bad id."})
            continue
        parent = jobs.get_job(pid, user_id=user.id)
        if not parent:
            rejected.append({"parentJobId": pid, "reason": "Not found."})
            continue
        if parent.get("tool") != "bulk-captions":
            rejected.append({"parentJobId": pid, "reason": "Not a transcribed video."})
            continue
        if parent.get("status") != "done":
            rejected.append({"parentJobId": pid, "reason": "Transcription not ready."})
            continue
        if not parent.get("transcriptWords"):
            rejected.append({"parentJobId": pid, "reason": "No transcript."})
            continue
        dur = float(parent.get("videoDuration") or 0)
        total_cost_sec += int(round(dur * mult)) if dur > 0 else 0
        valid_parents.append(parent)

    # Single budget check across the whole batch — friendlier than failing
    # halfway through and leaving the user with a partial result.
    if not _is_unlimited(user) and valid_parents:
        sub = billing.get_or_create_subscription(user.id, "caption_free", tool="captions")
        remaining = billing.remaining_seconds(sub)
        if total_cost_sec > remaining:
            raise HTTPException(
                status_code=402,
                detail=(
                    f"This batch needs {total_cost_sec}s but only {remaining}s "
                    "left on your Caption plan. Upgrade or remove some videos."
                ),
            )

    queued: list[dict] = []
    for parent in valid_parents:
        pid = str(parent["_id"])
        video_dur = float(parent.get("videoDuration") or 0)
        db_job_id = jobs.create_job(
            user_id=user.id,
            tool="bulk-captions-render",
            params={
                "parentJobId": pid,
                "videoFilename": (parent.get("params") or {}).get("videoFilename"),
                "videoDurationSec": video_dur,
                "label": f"Captioned · {options['style']}",
                "options": options,
                "userPlan": user.plan,
            },
        )
        jobs.enqueue(db_job_id, user.id)
        doc = jobs.get_job(db_job_id, user_id=user.id)
        if doc:
            queued.append(jobs.serialize_job(doc))

    return {
        "queued": queued,
        "rejected": rejected,
        "summary": {
            "uploaded": len(ids),
            "queued": len(queued),
            "rejected": len(rejected),
            "totalSeconds": total_cost_sec,
        },
    }


@app.get("/me/jobs/captions-bulk-zip")
def captions_bulk_zip(
    ids: str,
    user: AuthUser = Depends(current_user),
):
    """
    Stream a single ZIP containing every captioned mp4 the caller asks
    for. `ids` is a comma-separated list of bulk-captions-render job ids.
    Only jobs in `status="done"` and owned by the caller are included;
    missing/forbidden ids are silently skipped (frontend already showed
    them).

    Filename strategy: prefer the parent's original videoFilename so the
    user gets `interview.captioned.mp4` rather than `<jobid>.mp4`.
    Collisions get a numeric suffix.
    """
    import io
    import zipfile

    from fastapi.responses import StreamingResponse

    id_list = [s.strip() for s in (ids or "").split(",") if s.strip()]
    if not id_list:
        raise HTTPException(status_code=400, detail="ids query param is required.")
    if len(id_list) > MAX_BULK_FILES:
        raise HTTPException(status_code=400, detail="Too many ids.")

    files: list[tuple[str, Path]] = []
    used_names: set[str] = set()

    for jid in id_list:
        doc = jobs.get_job(jid, user_id=user.id)
        if not doc or doc.get("status") != "done":
            continue
        if doc.get("tool") != "bulk-captions-render":
            continue
        out_path = doc.get("outputPath")
        if not out_path:
            continue
        p = Path(out_path)
        if not p.exists():
            continue
        # Pick a friendly filename from the parent's original upload.
        parent_id = (doc.get("params") or {}).get("parentJobId")
        original_name: Optional[str] = None
        if parent_id:
            parent = jobs.get_job(str(parent_id), user_id=user.id)
            if parent:
                original_name = (parent.get("params") or {}).get("videoFilename")
        stem = Path(original_name).stem if original_name else p.stem
        candidate = f"{stem}.captioned.mp4"
        i = 1
        while candidate in used_names:
            i += 1
            candidate = f"{stem} ({i}).captioned.mp4"
        used_names.add(candidate)
        files.append((candidate, p))

    if not files:
        raise HTTPException(status_code=404, detail="No completed renders to zip.")

    def _stream():
        # Build the zip in-memory but yield chunks so very large batches
        # don't peak RAM. zipfile doesn't natively stream, so we keep the
        # buffer growing then flush per-file.
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:
            for name, path in files:
                zf.write(path, arcname=name)
                buf.seek(0)
                chunk = buf.read()
                if chunk:
                    yield chunk
                    buf.seek(0)
                    buf.truncate(0)
        buf.seek(0)
        tail = buf.read()
        if tail:
            yield tail

    return StreamingResponse(
        _stream(),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="captions-batch.zip"'},
    )


@app.get("/me/jobs/{job_id}/transcript")
def get_job_transcript(
    job_id: str,
    user: AuthUser = Depends(current_user),
):
    """
    Return the cached word-level transcript for a transcribe job along
    with the video dimensions/duration the editor needs to position
    overlays. The frontend calls this once when opening the editor.
    """
    doc = jobs.get_job(job_id, user_id=user.id)
    if not doc:
        raise HTTPException(status_code=404, detail="Job not found.")
    words = doc.get("transcriptWords")
    if not isinstance(words, list) or not words:
        raise HTTPException(status_code=409, detail="Transcript not ready.")
    return {
        "words": words,
        "videoWidth": int(doc.get("videoWidth") or 0),
        "videoHeight": int(doc.get("videoHeight") or 0),
        "videoDuration": float(doc.get("videoDuration") or 0),
    }


@app.post("/me/jobs/captions")
def submit_captions(
    payload: dict,
    user: AuthUser = Depends(current_user),
):
    """
    Generate captioned video for an existing finished audio-to-video job.
    Doesn't burn a render credit — captions are a follow-up action on
    work the user already paid for.

    Body:
      {
        "parentJobId": "<jobId of finished audio-to-video>",
        "style":        "plain"|"bold"|"highlight"|"karaoke",
        "position":     "top"|"middle"|"bottom",
        "wordsPerLine": int,
        "uppercase":    bool (optional)
      }
    """
    parent_id = (payload or {}).get("parentJobId")
    if not parent_id or not isinstance(parent_id, str):
        raise HTTPException(status_code=400, detail="parentJobId is required.")

    parent = jobs.get_job(parent_id, user_id=user.id)
    if not parent:
        raise HTTPException(status_code=404, detail="Parent video job not found.")
    if parent.get("status") != "done":
        raise HTTPException(status_code=400, detail="Parent video isn't done yet.")
    # Only BYO-key users need a personal key; Hosted users use the
    # platform rotator.
    if _user_is_byo(user) and not _user_has_api_key(user):
        raise HTTPException(
            status_code=400,
            detail="Save your Gemini API key in Settings before adding captions.",
        )

    style = payload.get("style") or "bold"
    if style not in {
        # Original 8
        "plain", "bold", "highlight", "karaoke",
        "outline", "neon", "gradient", "typewriter",
        # 10 new (classic / trendy / minimal / decorative)
        "news", "cinema",
        "mrbeast", "reels", "tiktok",
        "whisper", "underline",
        "sticker", "comic", "retro",
    }:
        style = "bold"
    position = payload.get("position") or "bottom"
    if position not in {"top", "middle", "bottom"}:
        position = "bottom"
    try:
        wpl = int(payload.get("wordsPerLine") or 2)
    except (TypeError, ValueError):
        wpl = 2
    wpl = max(1, min(8, wpl))
    uppercase = bool(payload.get("uppercase", False))

    options = _normalize_caption_options(
        style,
        position,
        wpl,
        uppercase,
        payload.get("posXFrac"),
        payload.get("posYFrac"),
        primary_color=payload.get("primaryColor"),
        outline_color=payload.get("outlineColor"),
        outline_width=payload.get("outlineWidth"),
        bg_color=payload.get("bgColor"),
        bg_alpha=payload.get("bgAlpha"),
        font_size=payload.get("fontSize"),
        font_family=payload.get("fontFamily"),
        shadow=payload.get("shadow"),
    )

    db_job_id = jobs.create_job(
        user_id=user.id,
        tool="captions",
        params={
            "parentJobId": parent_id,
            "audioFilename": (parent.get("params") or {}).get("audioFilename"),
            "label": f"Captions · {style}",
            "options": options,
            "userPlan": user.plan,
        },
    )
    jobs.enqueue(db_job_id, user.id)

    doc = jobs.get_job(db_job_id, user_id=user.id)
    return jobs.serialize_job(doc) if doc else {"id": db_job_id, "status": "queued"}


@app.post("/me/jobs/{job_id}/captions/clear")
def clear_active_captions(job_id: str, user: AuthUser = Depends(current_user)):
    """
    Unset the active-captions pointer on a parent video job. The
    captions mp4 file stays on disk so re-applying with a different style
    is a fresh render, but switching back to the original is instant.
    """
    parent = jobs.get_job(job_id, user_id=user.id)
    if not parent:
        raise HTTPException(status_code=404, detail="Job not found.")
    from bson import ObjectId as _OID
    db().tool_jobs.update_one(
        {"_id": _OID(job_id), "userId": user.id},
        {"$unset": {"activeCaptionsJobId": "", "activeCaptionsStyle": ""}},
    )
    return {"ok": True}


async def _save_image_upload(user_id: str, image: UploadFile) -> tuple[Path, int]:
    """Stream an image upload to a per-job folder. Returns (path, bytes)."""
    if not image.filename:
        raise HTTPException(status_code=400, detail="No file uploaded.")
    ext = (Path(image.filename).suffix or ".jpg").lower()
    if ext not in ALLOWED_IMAGE_EXTS:
        raise HTTPException(
            status_code=400,
            detail=f"{image.filename}: unsupported image format ({ext}). Use jpg, png, or webp.",
        )
    job_uuid = str(uuid.uuid4())
    job_dir = UPLOAD_DIR / user_id / job_uuid
    job_dir.mkdir(parents=True, exist_ok=True)
    img_path = job_dir / f"input{ext}"

    size_bytes = 0
    with img_path.open("wb") as f:
        while True:
            chunk = await image.read(1024 * 1024)
            if not chunk:
                break
            size_bytes += len(chunk)
            if size_bytes > MAX_IMAGE_BYTES:
                f.close()
                img_path.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=413,
                    detail=f"{image.filename}: file too large (25 MB max).",
                )
            f.write(chunk)
    return img_path, size_bytes


@app.post("/me/jobs/voice-pair")
async def submit_voice_pair(
    # Flat list of all media files across all pairs. The frontend groups
    # them per pair using `mediaCounts`: mediaCounts[i] = how many media
    # files belong to pair i, in order. Pair i also has voice[i] and
    # animations[i].
    media: list[UploadFile] = File(...),
    voice: list[UploadFile] = File(...),
    mediaCounts: list[str] = Form(default=[]),
    mode: str = Form("single"),
    animations: list[str] = Form(default=[]),
    label: str = Form(""),
    projectName: str = Form(""),
    projectId: str = Form(""),
    # Language hint for the auto-chained captions transcribe. "auto"
    # lets Whisper detect; "hi"/"ur"/etc. routes to the medium model
    # that handles Devanagari/Nastaliq correctly. Stored on each
    # voice-pair job's params and passed to the chained captions job.
    language: str = Form("auto"),
    user: AuthUser = Depends(current_user),
):
    """
    Bulk submit for the Voice Pair tool. Two modes:
      - mode="single":     each media file pairs with one voice file
                           (mediaCounts = [1, 1, 1, ...] implicitly).
      - mode="slideshow":  each pair takes N media files + 1 voice,
                           where N is given by mediaCounts[i]. Sum of
                           mediaCounts must equal len(media).

    `voice` length always equals the number of PAIRS — one voice per
    pair regardless of how many media files that pair has.

    Free tool — no billing/minute check.
    """
    mode = (mode or "single").lower()
    if mode not in {"single", "slideshow"}:
        raise HTTPException(status_code=400, detail=f"Unknown mode: {mode}")

    if not media or not voice:
        raise HTTPException(status_code=400, detail="Upload at least one media + voice pair.")

    # Resolve mediaCounts: in single mode default is [1, 1, ...].
    if not mediaCounts:
        counts = [1] * len(voice)
    else:
        try:
            counts = [int(c) for c in mediaCounts]
        except ValueError:
            raise HTTPException(status_code=400, detail="mediaCounts must be integers.")

    if len(counts) != len(voice):
        raise HTTPException(
            status_code=400,
            detail=f"mediaCounts length ({len(counts)}) must equal voice count ({len(voice)}).",
        )
    if sum(counts) != len(media):
        raise HTTPException(
            status_code=400,
            detail=f"mediaCounts sum ({sum(counts)}) must equal total media count ({len(media)}).",
        )
    if len(voice) > MAX_BULK_FILES:
        raise HTTPException(
            status_code=400,
            detail=f"Too many pairs in one submit ({len(voice)} > {MAX_BULK_FILES}).",
        )

    queued: list[dict] = []
    rejected: list[dict] = []

    # Group every job in this submit under a single project so the UI
    # can show them nested. Default name = timestamp if user didn't type.
    # projectId merges into that existing project when supplied.
    project_id, project_name = _make_project(
        projectName, user_id=user.id, existing_project_id=projectId or None,
    )

    # Random offset so a single-image submit doesn't always get the
    # same animation variant (m=0, centered zoom). The pair_idx is
    # still added on top, so a slideshow gets sequential variety.
    import random as _random
    anim_seed_offset = _random.randint(0, 7)

    # Walk media list in chunks defined by counts[i].
    media_idx = 0
    for pair_idx, v_file in enumerate(voice):
        v_name = v_file.filename or f"voice-{pair_idx}"
        count = counts[pair_idx]
        pair_media: list[tuple[Path, str]] = []  # (saved_path, original_name)
        pair_rejected = False

        for _ in range(count):
            m_file = media[media_idx]
            media_idx += 1
            m_name = m_file.filename or f"media-{pair_idx}"
            try:
                m_ext = (Path(m_name).suffix or "").lower()
                if m_ext in ALLOWED_IMAGE_EXTS:
                    saved, _m_bytes = await _save_image_upload(user.id, m_file)
                elif m_ext in ALLOWED_VIDEO_EXTS:
                    saved, _m_bytes = await _save_video_upload(user.id, m_file)
                else:
                    rejected.append({
                        "filename": m_name,
                        "reason": f"Unsupported media format: {m_ext}. Use image (jpg/png/webp) or video (mp4/mov/webm).",
                    })
                    pair_rejected = True
                    continue
                pair_media.append((saved, m_name))
            except HTTPException as e:
                rejected.append({"filename": m_name, "reason": e.detail})
                pair_rejected = True

        if pair_rejected or not pair_media:
            continue

        try:
            voice_path, _v_bytes = await _save_audio_upload(user.id, v_file)
        except HTTPException as e:
            rejected.append({"filename": v_name, "reason": e.detail})
            continue

        animation = "static"
        if pair_idx < len(animations):
            a = (animations[pair_idx] or "").strip().lower()
            if a in {"static", "ken_burns"}:
                animation = a

        voice_dur = audio_duration_seconds(voice_path)

        if mode == "slideshow" or len(pair_media) > 1:
            params = {
                "mode": "slideshow",
                "mediaPaths": [str(p) for p, _ in pair_media],
                "mediaFilenames": [n for _, n in pair_media],
                "voicePath": str(voice_path),
                "voiceFilename": v_name,
                "pairIndex": pair_idx + anim_seed_offset,
                "voiceDurationSec": voice_dur,
                "label": label[:80] if label else "",
                "userPlan": user.plan,
                # Carried into the auto-chained captions transcribe so
                # Hindi/Urdu audio uses the medium whisper model.
                "captionsLanguage": (language or "auto").lower(),
            }
            display_name = f"Slideshow · {len(pair_media)} items"
        else:
            saved, m_name = pair_media[0]
            params = {
                "mode": "single",
                "mediaPath": str(saved),
                "mediaFilename": m_name,
                "voicePath": str(voice_path),
                "voiceFilename": v_name,
                "animation": animation,
                "pairIndex": pair_idx + anim_seed_offset,
                "voiceDurationSec": voice_dur,
                "label": label[:80] if label else "",
                "userPlan": user.plan,
                # Carried into the auto-chained captions transcribe so
                # Hindi/Urdu audio uses the medium whisper model.
                "captionsLanguage": (language or "auto").lower(),
            }
            display_name = m_name

        job_id = jobs.create_job(
            user_id=user.id,
            tool="voice-pair",
            params=params,
            project_id=project_id,
            project_name=project_name,
        )
        jobs.enqueue(job_id, user.id)
        queued.append({
            "id": job_id,
            "filename": display_name,
            "voiceFilename": v_name,
            "voiceDurationSec": voice_dur,
            "animation": animation,
            "mode": params["mode"],
        })

    return {
        "queued": queued,
        "rejected": rejected,
        "summary": {"queued": len(queued), "rejected": len(rejected)},
        "projectId": project_id,
        "projectName": project_name,
    }


@app.get("/me/jobs")
def list_my_jobs(
    status: Optional[str] = None,
    limit: int = 50,
    user: AuthUser = Depends(current_user),
):
    """
    Newest-first list of the caller's jobs. Use ?status=running to poll
    only active jobs, ?status=blocked to show what's waiting on a plan
    upgrade, etc.
    """
    if status and status not in {"queued", "running", "done", "failed", "blocked", "cancelled"}:
        raise HTTPException(status_code=400, detail=f"Unknown status: {status}")
    return {
        "items": jobs.list_user_jobs(user.id, limit=max(1, min(200, limit)), status=status),
    }


@app.post("/me/jobs/requeue-blocked")
def requeue_my_blocked(user: AuthUser = Depends(current_user)):
    """
    Flip every 'blocked' job back to 'queued' and start running them.
    Frontend should call this after a successful plan upgrade or top-up.
    Quota gets re-checked at job pickup; if there still isn't enough
    budget the worker will mark the job blocked again.
    """
    if not _is_unlimited(user):
        sub = billing.get_or_create_subscription(user.id, user.plan)
        if billing.remaining_seconds(sub) <= 0:
            raise HTTPException(
                status_code=402,
                detail="Quota still empty. Upgrade your plan or buy a top-up first.",
            )
    n = jobs.requeue_blocked(user.id)
    return {"requeued": n}


@app.get("/me/jobs/{job_id}")
def get_job_status(job_id: str, user: AuthUser = Depends(current_user)):
    doc = jobs.get_job(job_id, user_id=user.id)
    if not doc:
        raise HTTPException(status_code=404, detail="Job not found.")
    return jobs.serialize_job(doc)


@app.post("/me/jobs/{job_id}/cancel")
def cancel_job(job_id: str, user: AuthUser = Depends(current_user)):
    """
    Cancel a queued or running job. Idempotent — calling on a job that
    already finished is a no-op (returns 200 with `alreadyFinal: true`).
    """
    doc = jobs.get_job(job_id, user_id=user.id)
    if not doc:
        raise HTTPException(status_code=404, detail="Job not found.")
    res = jobs.request_cancel(job_id, user_id=user.id)
    return res


@app.delete("/me/jobs/{job_id}")
def delete_job(job_id: str, user: AuthUser = Depends(current_user)):
    """
    Permanently remove a finished job (done/failed/cancelled) from the
    user's history. Running jobs are cancelled first, then deleted.
    Also wipes the rendered output file + any auxiliary files on disk.
    """
    doc = jobs.get_job(job_id, user_id=user.id)
    if not doc:
        raise HTTPException(status_code=404, detail="Job not found.")

    # If the job is still active, cancel it first so the worker stops
    # writing to the file we're about to delete.
    if doc.get("status") in ("queued", "running"):
        jobs.request_cancel(job_id, user_id=user.id)

    files_removed = 0
    # Delete the main output and any sidecar paths we know about.
    for key in ("outputPath", "srtPath"):
        p = doc.get(key)
        if p:
            try:
                fp = Path(p)
                if fp.exists() and fp.is_file():
                    fp.unlink()
                    files_removed += 1
            except OSError:
                pass
    # Also remove the source uploads if no other job references them.
    params = doc.get("params") or {}
    candidate_paths: list[str] = []
    for key in ("audioPath", "videoPath", "mediaPath", "voicePath"):
        if params.get(key):
            candidate_paths.append(params[key])
    if isinstance(params.get("mediaPaths"), list):
        candidate_paths.extend(str(p) for p in params["mediaPaths"])
    for p in candidate_paths:
        try:
            fp = Path(p)
            if fp.exists() and fp.is_file():
                fp.unlink()
                files_removed += 1
        except OSError:
            pass

    from bson import ObjectId as _OID
    db().tool_jobs.delete_one({"_id": _OID(job_id), "userId": user.id})
    return {"ok": True, "filesRemoved": files_removed}


# ---- Projects ---------------------------------------------------------
# Projects are just a (projectId, projectName) pair stamped on each
# job at submit time. Listing/renaming/deleting projects is implemented
# as a grouped read / multi-update / multi-delete over tool_jobs — no
# separate `projects` collection. Keeps the data model simple and lets
# old jobs (without projectId) coexist with new ones.

@app.get("/me/projects")
def list_my_projects(
    limit: int = 50,
    user: AuthUser = Depends(current_user),
):
    """List the user's projects, newest-first. Each entry summarises
    the project's jobs: counts by status, dominant tool, total bytes.
    Jobs without a projectId are bucketed under "(Unfiled)" so the UI
    can still surface legacy renders."""
    pipeline = [
        {"$match": {"userId": user.id}},
        {"$sort": {"createdAt": -1}},
        {
            "$group": {
                "_id": {"$ifNull": ["$projectId", None]},
                "projectName": {"$first": "$projectName"},
                "createdAt": {"$max": "$createdAt"},
                "updatedAt": {"$max": "$updatedAt"},
                "jobCount": {"$sum": 1},
                "doneCount": {
                    "$sum": {"$cond": [{"$eq": ["$status", "done"]}, 1, 0]},
                },
                "runningCount": {
                    "$sum": {
                        "$cond": [
                            {"$in": ["$status", ["queued", "running"]]}, 1, 0,
                        ],
                    },
                },
                "failedCount": {
                    "$sum": {
                        "$cond": [
                            {"$in": ["$status", ["failed", "cancelled"]]}, 1, 0,
                        ],
                    },
                },
                "tools": {"$addToSet": "$tool"},
            },
        },
        {"$sort": {"updatedAt": -1}},
        {"$limit": max(1, min(200, int(limit)))},
    ]
    items: list[dict] = []
    for row in db().tool_jobs.aggregate(pipeline):
        pid = row["_id"]
        items.append({
            "projectId": pid,
            "projectName": row.get("projectName") or (
                "(Unfiled)" if not pid else "Untitled project"
            ),
            "jobCount": row.get("jobCount", 0),
            "doneCount": row.get("doneCount", 0),
            "runningCount": row.get("runningCount", 0),
            "failedCount": row.get("failedCount", 0),
            "tools": row.get("tools") or [],
            "createdAt": row.get("createdAt").isoformat() if row.get("createdAt") else None,
            "updatedAt": row.get("updatedAt").isoformat() if row.get("updatedAt") else None,
        })
    return {"items": items}


@app.get("/me/projects/{project_id}/jobs")
def list_project_jobs(
    project_id: str,
    user: AuthUser = Depends(current_user),
):
    """Newest-first list of jobs in a single project."""
    cur = db().tool_jobs.find({
        "userId": user.id,
        "projectId": project_id,
    }).sort("createdAt", -1)
    return {"items": [jobs.serialize_job(d) for d in cur]}


@app.post("/me/projects/{project_id}/rename")
def rename_project(
    project_id: str,
    body: dict,
    user: AuthUser = Depends(current_user),
):
    """Rename a project. Updates every job that carries this projectId."""
    new_name = str(body.get("name") or "").strip()[:80]
    if not new_name:
        raise HTTPException(status_code=400, detail="name is required")
    res = db().tool_jobs.update_many(
        {"userId": user.id, "projectId": project_id},
        {"$set": {"projectName": new_name, "updatedAt": datetime.now(timezone.utc)}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Project not found.")
    return {"ok": True, "renamed": res.modified_count, "name": new_name}


@app.delete("/me/projects/{project_id}")
def delete_project(
    project_id: str,
    user: AuthUser = Depends(current_user),
):
    """Cascade-delete a project: cancel any in-flight jobs, then remove
    every job document + its rendered + source files on disk."""
    docs = list(db().tool_jobs.find({
        "userId": user.id,
        "projectId": project_id,
    }))
    if not docs:
        raise HTTPException(status_code=404, detail="Project not found.")

    files_removed = 0
    jobs_removed = 0
    for doc in docs:
        # Cancel running first so the worker stops writing.
        if doc.get("status") in ("queued", "running"):
            try:
                jobs.request_cancel(str(doc["_id"]), user_id=user.id)
            except Exception:
                pass
        for key in ("outputPath", "srtPath"):
            p = doc.get(key)
            if p:
                try:
                    fp = Path(p)
                    if fp.exists() and fp.is_file():
                        fp.unlink()
                        files_removed += 1
                except OSError:
                    pass
        params = doc.get("params") or {}
        candidates: list[str] = []
        for key in ("audioPath", "videoPath", "mediaPath", "voicePath"):
            if params.get(key):
                candidates.append(params[key])
        if isinstance(params.get("mediaPaths"), list):
            candidates.extend(str(p) for p in params["mediaPaths"])
        for p in candidates:
            try:
                fp = Path(p)
                if fp.exists() and fp.is_file():
                    fp.unlink()
                    files_removed += 1
            except OSError:
                pass
        jobs_removed += 1

    db().tool_jobs.delete_many({"userId": user.id, "projectId": project_id})
    return {"ok": True, "jobsRemoved": jobs_removed, "filesRemoved": files_removed}


@app.get("/me/projects/{project_id}/zip")
def download_project_zip(
    project_id: str,
    user: AuthUser = Depends(current_user),
):
    """Bundle every DONE job's output mp4 in this project as a single
    ZIP. Streams the zip so we don't hold the whole archive in RAM."""
    import io
    import zipfile
    from fastapi.responses import StreamingResponse

    docs = list(db().tool_jobs.find({
        "userId": user.id,
        "projectId": project_id,
        "status": "done",
    }))
    if not docs:
        raise HTTPException(
            status_code=404,
            detail="No completed renders in this project yet.",
        )

    project_name = docs[0].get("projectName") or "project"
    safe_name = re.sub(r"[^\w\-]+", "_", project_name).strip("_") or "project"

    # In-memory zip. For large projects (~100 mp4s) we'd want a temp
    # file, but for typical 5-20 file submits this is fine and lets us
    # stream the response without writing intermediate disk state.
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:
        for doc in docs:
            out_path = doc.get("outputPath")
            if not out_path:
                continue
            fp = Path(out_path)
            if not fp.exists():
                continue
            # Pick a friendly arcname: prefer the source filename if known.
            params = doc.get("params") or {}
            base = (
                params.get("audioFilename")
                or params.get("videoFilename")
                or params.get("mediaFilename")
                or fp.name
            )
            arcname = f"{Path(base).stem}{fp.suffix}"
            # Avoid duplicate names by suffixing with the job id tail.
            arcname = f"{Path(base).stem}_{str(doc['_id'])[-6:]}{fp.suffix}"
            zf.write(str(fp), arcname=arcname)
    buf.seek(0)

    headers = {
        "Content-Disposition": f'attachment; filename="{safe_name}.zip"',
    }
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="application/zip",
        headers=headers,
    )


@app.post("/me/jobs/{job_id}/retry")
def retry_job(job_id: str, user: AuthUser = Depends(current_user)):
    """
    Re-queue a failed or cancelled job. Used by the "Retry" button after
    a worker died (server restart) or after a transient API failure.
    Keeps the original upload + params; just resets status to `queued`
    and pushes the job id back onto the worker queue.
    """
    doc = jobs.get_job(job_id, user_id=user.id)
    if not doc:
        raise HTTPException(status_code=404, detail="Job not found.")
    status = doc.get("status")
    if status not in {"failed", "cancelled", "blocked"}:
        raise HTTPException(
            status_code=400,
            detail=f"Can't retry a job that's {status}. Only failed/cancelled/blocked jobs.",
        )
    # Confirm the original uploaded media is still on disk — if cleanup
    # already nuked it (e.g. very old job), the retry would loop on the
    # same "file not found" failure forever. Fail loud instead.
    params = doc.get("params") or {}
    src = params.get("audioPath") or params.get("videoPath")
    if src and not Path(src).exists():
        raise HTTPException(
            status_code=410,
            detail="Original upload file is no longer on disk. Re-upload to render.",
        )

    jobs.update_job(
        job_id,
        status="queued",
        progress=0,
        message="Re-queued for retry",
        errorDetail=None,
        cancelRequested=False,
        creditConsumed=False,
        billedSeconds=None,
    )
    jobs.enqueue(job_id, user.id)
    return {"ok": True, "wasStatus": status}


@app.get("/me/jobs/{job_id}/srt")
def get_job_srt(job_id: str, user: AuthUser = Depends(current_user)):
    doc = jobs.get_job(job_id, user_id=user.id)
    if not doc:
        raise HTTPException(status_code=404, detail="Job not found.")
    if doc.get("status") != "done":
        raise HTTPException(status_code=409, detail="Job is not complete yet.")
    srt_path = doc.get("srtPath")
    if not srt_path or not Path(srt_path).exists():
        raise HTTPException(status_code=404, detail="No SRT for this job.")
    return FileResponse(
        srt_path,
        media_type="application/x-subrip",
        filename=Path(srt_path).name,
    )


@app.get("/me/jobs/{job_id}/output")
def get_job_output(
    job_id: str,
    variant: str = "active",
    user: AuthUser = Depends(current_user),
):
    """
    Stream the rendered mp4. By default ("active") returns the captioned
    variant if one is currently set on the job; falls back to the original.
    Pass ?variant=original to always get the unmodified video.
    """
    doc = jobs.get_job(job_id, user_id=user.id)
    if not doc:
        raise HTTPException(status_code=404, detail="Job not found.")
    if doc.get("status") != "done":
        raise HTTPException(status_code=409, detail="Job is not complete yet.")

    # Thumbnail short-circuit — separate from the main video flow. Free
    # to fetch (no billing), 404 if not extracted (e.g. older jobs).
    if variant == "thumb":
        thumb = doc.get("thumbnailPath")
        if not thumb or not Path(thumb).exists():
            raise HTTPException(status_code=404, detail="No thumbnail.")
        return FileResponse(
            thumb,
            media_type="image/jpeg",
            filename=Path(thumb).name,
            headers={"Cache-Control": "public, max-age=86400"},
        )

    # Resolve which file to serve.
    output_path = doc.get("outputPath")
    if variant == "active":
        cap_id = doc.get("activeCaptionsJobId")
        if cap_id:
            cap_doc = jobs.get_job(str(cap_id), user_id=user.id)
            if cap_doc and cap_doc.get("status") == "done":
                cap_out = cap_doc.get("outputPath")
                if cap_out and Path(cap_out).exists():
                    output_path = cap_out
    if not output_path or not Path(output_path).exists():
        raise HTTPException(status_code=410, detail="Output file is missing.")

    # Burn minutes off the user's subscription on first successful download.
    # Each tool has its own cost multiplier (see billing.TOOL_COST_MULTIPLIERS):
    #   audio-to-video      → 1.0×  (full duration)
    #   captions            → 0.0×  (follow-up; parent paid)
    #   bulk-captions       → 0.5×  (standalone transcribe)
    #   bulk-captions-render→ 0.25× (caption burn-in only)
    # Owner / unlimited plans skip entirely. BYO plans still meter compute
    # minutes — only Gemini cost is on the user.
    tool = doc.get("tool")
    if not doc.get("creditConsumed") and not _is_unlimited(user):
        # Resolve raw media duration: prefer the value stamped at submit
        # time on this job, then fall back to the parent's stored duration
        # for child jobs (captions follow-up, captions-render).
        params = doc.get("params") or {}
        raw_dur = float(
            params.get("audioDurationSec")
            or params.get("videoDurationSec")
            or 0
        )
        if raw_dur <= 0:
            parent_id = params.get("parentJobId")
            if parent_id:
                parent = jobs.get_job(str(parent_id), user_id=user.id)
                if parent:
                    raw_dur = float(
                        parent.get("videoDuration")
                        or (parent.get("params") or {}).get("audioDurationSec")
                        or 0
                    )
        mult = billing.cost_multiplier(tool or "")
        cost_sec = int(round(raw_dur * mult)) if raw_dur > 0 else 0
        if cost_sec > 0:
            sub_tool = billing.sub_tool_for_job(tool or "")
            billing.consume_seconds(user.id, cost_sec, tool=sub_tool)
        jobs.update_job(job_id, creditConsumed=True, billedSeconds=cost_sec)

    return FileResponse(
        output_path,
        media_type=doc.get("outputContentType") or "application/octet-stream",
        filename=Path(output_path).name,
    )


# ---------- Billing / Razorpay -------------------------------------------
#
# Razorpay creds resolve from `tool_runtime_config` first (set via admin
# UI), then env. This lets the owner rotate keys without redeploying.

import runtime_config  # noqa: E402


def _razorpay_creds() -> tuple[str, str, str]:
    c = runtime_config.get_razorpay_creds()
    return c["keyId"], c["keySecret"], c["webhookSecret"]


def _razorpay_configured() -> bool:
    kid, ksec, _ = _razorpay_creds()
    return bool(kid and ksec)


@app.post("/me/billing/checkout")
def create_checkout(payload: dict, user: AuthUser = Depends(current_user)):
    """
    Create a Razorpay order for a plan subscription or top-up.

    Body: { "kind": "subscription"|"topup", "id": "<planId or topupId>" }

    Returns a `clientPayload` the frontend hands to Razorpay Checkout JS.
    When real keys aren't set yet we return a stub payload so the UI can
    still progress through dev/test.
    """
    kind = (payload or {}).get("kind")
    item_id = (payload or {}).get("id")
    if kind not in {"subscription", "topup"}:
        raise HTTPException(status_code=400, detail="Bad kind. Use 'subscription' or 'topup'.")

    if kind == "subscription":
        plan = plans_mod.PLANS.get(item_id)
        if not plan or plan["priceInr"] <= 0:
            raise HTTPException(status_code=400, detail="Unknown or free plan.")
        amount_paise = plan["priceInr"] * 100
        description = f"{plan['name']} subscription"
    else:
        top = plans_mod.TOPUPS.get(item_id)
        if not top:
            raise HTTPException(status_code=400, detail="Unknown top-up.")
        amount_paise = top["priceInr"] * 100
        description = top["label"]

    if not _razorpay_configured():
        # Dev stub — UI can still drive a "fake success" path.
        return {
            "stub": True,
            "amountPaise": amount_paise,
            "description": description,
            "kind": kind,
            "itemId": item_id,
            "message": "Razorpay not configured. Set RAZORPAY_KEY_ID/SECRET to enable real checkout.",
        }

    # Real Razorpay order creation (only runs when keys are present).
    import razorpay  # type: ignore

    kid, ksec, _ = _razorpay_creds()
    rzp = razorpay.Client(auth=(kid, ksec))
    order = rzp.order.create({
        "amount": amount_paise,
        "currency": "INR",
        "receipt": f"u:{user.id}:{kind}:{item_id}",
        "notes": {"userId": user.id, "kind": kind, "itemId": item_id},
    })
    return {
        "stub": False,
        "orderId": order["id"],
        "amountPaise": amount_paise,
        "description": description,
        "kind": kind,
        "itemId": item_id,
        "keyId": kid,
    }


@app.post("/_admin/billing/grant")
def admin_grant(
    payload: dict,
    user: AuthUser = Depends(current_user),
):
    """
    Admin-only manual plan/top-up grant. Used while Razorpay is being
    set up and for support tickets ("free month for X"). Only the
    `owner` plan can call it.
    """
    if user.plan != "owner":
        raise HTTPException(status_code=403, detail="Owner only.")
    target_id = (payload or {}).get("userId")
    kind = (payload or {}).get("kind")
    item_id = (payload or {}).get("id")
    if not target_id or kind not in {"subscription", "topup"}:
        raise HTTPException(status_code=400, detail="Bad input.")

    if kind == "subscription":
        if item_id not in plans_mod.PLANS:
            raise HTTPException(status_code=400, detail="Unknown plan.")
        sub = billing.set_plan(target_id, item_id)
    else:
        top = plans_mod.TOPUPS.get(item_id)
        if not top:
            raise HTTPException(status_code=400, detail="Unknown top-up.")
        sub = billing.add_topup_minutes(target_id, top["minutes"])

    return billing.serialize_subscription(sub)


@app.post("/billing/webhook")
async def razorpay_webhook(request: Request):
    """
    Razorpay webhook handler. Verifies signature when configured, then
    fans out to billing.set_plan / add_topup_minutes based on the order
    notes we attached at checkout time.
    """
    body = await request.body()
    signature = request.headers.get("x-razorpay-signature", "")

    _, _, webhook_secret = _razorpay_creds()
    if webhook_secret:
        import hmac
        import hashlib
        expected = hmac.new(
            webhook_secret.encode(),
            body,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise HTTPException(status_code=400, detail="Bad signature.")
    else:
        print("[webhook] WARNING: webhook secret unset, skipping signature check.")

    import json as _json
    try:
        payload = _json.loads(body)
    except Exception:
        raise HTTPException(status_code=400, detail="Bad JSON.")

    event = payload.get("event", "")
    entity = (payload.get("payload") or {}).get("payment", {}).get("entity") or {}
    notes = entity.get("notes") or {}
    user_id = notes.get("userId")
    kind = notes.get("kind")
    item_id = notes.get("itemId")

    if event in {"payment.captured", "order.paid"} and user_id and kind and item_id:
        if kind == "subscription" and item_id in plans_mod.PLANS:
            billing.set_plan(user_id, item_id, razorpay_sub_id=entity.get("id"))
        elif kind == "topup" and item_id in plans_mod.TOPUPS:
            billing.add_topup_minutes(user_id, plans_mod.TOPUPS[item_id]["minutes"])

    return {"ok": True}


# ---------- Admin: runtime config ---------------------------------------


def _require_owner(user: AuthUser) -> None:
    if user.plan != "owner":
        raise HTTPException(status_code=403, detail="Owner only.")


@app.get("/_admin/config")
def admin_get_config(user: AuthUser = Depends(current_user)):
    """Masked view of runtime config (Gemini keys, Razorpay creds, flags)."""
    _require_owner(user)
    return runtime_config.masked_view()


@app.post("/_admin/config")
def admin_set_config(
    payload: dict,
    user: AuthUser = Depends(current_user),
):
    """
    Update one or more runtime config fields. Empty string clears a field
    (falls back to env). Secret fields are encrypted at rest.

    Body: { field1: value1, field2: value2, ... }
    """
    _require_owner(user)
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Body must be an object.")
    return runtime_config.set_config_values(payload)


@app.get("/_admin/users")
def admin_list_users(
    q: Optional[str] = None,
    limit: int = 100,
    user: AuthUser = Depends(current_user),
):
    """
    List users with subscription info. Optional `q` filters by email
    or name (case-insensitive contains).
    """
    _require_owner(user)
    query: dict[str, Any] = {}
    if q:
        # Escape regex metacharacters so a user with "." in their email
        # still matches literally.
        import re as _re
        pattern = _re.escape(q)
        query["$or"] = [
            {"email": {"$regex": pattern, "$options": "i"}},
            {"name": {"$regex": pattern, "$options": "i"}},
        ]
    rows = list(
        db().user.find(query, {"email": 1, "name": 1, "role": 1, "plan": 1})
        .sort("createdAt", -1)
        .limit(max(1, min(500, limit)))
    )
    out = []
    for r in rows:
        uid = str(r["_id"])
        a2v_sub = billing.get_or_create_subscription(uid, r.get("plan", "free"), tool="audio-to-video")
        cap_sub = billing.get_or_create_subscription(uid, "caption_free", tool="captions")
        sv = billing.serialize_subscription(a2v_sub)
        cv = billing.serialize_subscription(cap_sub)
        out.append({
            "id": uid,
            "email": r.get("email"),
            "name": r.get("name"),
            "role": r.get("role", "user"),
            "plan": sv["plan"],
            "planName": sv["planName"],
            "minutesUsed": sv["minutesUsed"],
            "minutesLimit": sv["minutesLimit"],
            "topUpMinutesRemaining": sv["topUpMinutesRemaining"],
            "cycleEndAt": sv["cycleEndAt"],
            "status": sv["status"],
            "captionPlan": cv["plan"],
            "captionPlanName": cv["planName"],
            "captionMinutesUsed": cv["minutesUsed"],
            "captionMinutesLimit": cv["minutesLimit"],
        })
    return {"items": out}


# ---------- Admin: invite whitelist --------------------------------------
#
# While early-access is on, every signed-in user gets gated through
# tool_invites.is_whitelisted in auth.py. These endpoints let the owner
# add / list / revoke entries from the admin UI. Owner himself bypasses
# the gate via the BYPASS_PLANS set in invites.py.

import invites as invites_mod  # noqa: E402


@app.get("/_admin/invites")
def admin_list_invites(user: AuthUser = Depends(current_user)):
    _require_owner(user)
    return {"items": invites_mod.list_invites()}


@app.post("/_admin/invites")
def admin_add_invite(
    payload: dict,
    user: AuthUser = Depends(current_user),
):
    """Body: { email, note? }"""
    _require_owner(user)
    email = (payload or {}).get("email") or ""
    note = (payload or {}).get("note") or ""
    try:
        row = invites_mod.add_invite(email, added_by=user.email, note=note)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return row


@app.delete("/_admin/invites/{email}")
def admin_remove_invite(
    email: str,
    user: AuthUser = Depends(current_user),
):
    _require_owner(user)
    ok = invites_mod.remove_invite(email)
    return {"ok": ok}


# ---------- Cron / housekeeping ------------------------------------------


@app.post("/_admin/billing/reset-cycles")
def admin_reset_cycles(user: AuthUser = Depends(current_user)):
    """
    Manually fire the monthly cycle rollover. Subscriptions also lazily
    roll on read, so this is mainly a forced-housekeeping endpoint for
    tests or to clear a stuck cycle.
    """
    if user.plan != "owner":
        raise HTTPException(status_code=403, detail="Owner only.")
    n = billing.force_reset_all_cycles()
    return {"reset": n}


# ---------- Dev helper ------------------------------------------------------


@app.get("/_dev/users")
def list_dev_users():
    """
    DEV ONLY. Lists all user accounts so the frontend can pick one when
    running without real SSO. Disabled unless ALLOW_DEV_AUTH=1.
    """
    if os.environ.get("ALLOW_DEV_AUTH") != "1":
        raise HTTPException(status_code=404, detail="Not found.")
    rows = list(db().user.find({}, {"email": 1, "name": 1, "role": 1, "plan": 1}))
    return [
        {
            "id": str(r["_id"]),
            "email": r.get("email"),
            "name": r.get("name"),
            "role": r.get("role", "user"),
            "plan": r.get("plan", "free"),
        }
        for r in rows
    ]


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8001"))
    # Reload off by default — Windows + WatchFiles + console-launched python
    # leaves orphaned processes that hold the port. Run with RELOAD=1 to opt in.
    reload = os.environ.get("RELOAD") == "1"
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=reload)
