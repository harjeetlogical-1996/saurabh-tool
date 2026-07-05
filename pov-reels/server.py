"""
POV Reels MCP server
====================
Make "POV: I am a ___" style faceless viral reels where an AI-animated
character (a tomato, a matchstick, a sock...) speaks in first person.

Pipeline per reel:
  topic  --Gemini--> script (scenes: visual + spoken line)
         --Veo 3 Fast--> one animated 8s clip per scene (character acts + talks)
         --Edge-TTS--> voiceover of each line (free)
         --ffmpeg--> burn captions, join scenes, mix music -> final 9:16 mp4
         --YouTube--> optional upload as a Short

Voice / captions / assembly / YouTube helpers are REUSED from the sibling
reels-factory project so we don't reinvent them. Veo generation and the POV
script writer are local to this server.

Cost: only the Veo clips cost money (~$1.20 per 8s clip on Fast). Every reel
tool reports an estimate first; use `estimate_reel_cost` to check before spending.
"""
import os
import sys
import json
import shutil
from pathlib import Path

from fastmcp import FastMCP

# ---- make the sibling reels-factory helpers importable --------------------
BASE = Path(__file__).parent
RF = (BASE.parent / "reels-factory").resolve()
if RF.exists():
    sys.path.insert(0, str(RF))

import veo                     # local
import scriptwriter            # local

# reused from reels-factory/helpers.py
try:
    from helpers import (make_voice, build_captions, concat_clips,
                         pick_music, mix_music_over, get_audio_duration,
                         pad_audio_tail, make_thumbnail, build_caption)
    _HAVE_RF = True
except Exception as e:            # keep server importable even if RF missing
    _HAVE_RF = False
    _RF_ERR = str(e)

# youtube upload (also from reels-factory)
try:
    import youtube_manager as yt
    _HAVE_YT = True
except Exception:
    _HAVE_YT = False

OUT = BASE / "output"
TMP = BASE / "temp"
OUT.mkdir(exist_ok=True)
TMP.mkdir(exist_ok=True)

mcp = FastMCP("pov-reels")


# ---------------------------------------------------------------------------
# config / keys
# ---------------------------------------------------------------------------
def _gemini_key() -> str:
    """Gemini/Veo key from env, .env, or the nano-banana key file."""
    if os.environ.get("GEMINI_API_KEY"):
        return os.environ["GEMINI_API_KEY"].strip()
    envf = BASE / ".env"
    if envf.exists():
        for line in envf.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("GEMINI_API_KEY="):
                return line.split("=", 1)[1].strip()
    nb = BASE.parent / "nano-banana" / "api-key.txt"
    if nb.exists():
        return nb.read_text(encoding="utf-8").strip()
    return ""


def _voice() -> str:
    return os.environ.get("POV_VOICE", "en-US-AriaNeural")


def _safe(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in name)[:50] or "reel"


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------
@mcp.tool
def estimate_reel_cost(scenes: int = 4, quality: str = "fast") -> dict:
    """
    Estimate the USD cost of a POV reel BEFORE generating anything.

    scenes:  how many animated scenes (each is one 8-second Veo clip).
    quality: "fast" (cheap, ~$0.15/s) or "hq" (best, ~$0.40/s).
    Voice, captions, assembly and YouTube upload are all free — the Veo
    clips are the entire bill. Returns a breakdown.
    """
    est = veo.estimate_cost(scenes, model=quality)
    est["reel_length_seconds"] = scenes * veo.CLIP_SECONDS
    return est


@mcp.tool
def write_pov_script(topic: str, style: str = "funny", max_scenes: int = 4) -> dict:
    """
    Write (but do NOT render) a POV script for a topic, so you can review /
    tweak it before spending money on video. Costs almost nothing (text only).

    topic:     e.g. "a tomato's life", "an old matchstick", "a phone charger".
    style:     "funny" | "emotional" | "dramatic".
    max_scenes:cap the number of scenes (each scene = one paid Veo clip later).
    Returns {title, hook, hashtags, scenes:[{visual, line}]} plus a cost note.
    """
    key = _gemini_key()
    script = scriptwriter.write_script(topic, key, style=style, max_scenes=max_scenes)
    script["_cost_if_rendered"] = veo.estimate_cost(len(script["scenes"]),
                                                    model="fast")
    return script


@mcp.tool
def make_pov_reel(topic: str = "", style: str = "funny", quality: str = "fast",
                  max_scenes: int = 4, caption_style: str = "boldbox",
                  music_mood: str = "", script_json: str = "",
                  confirm_cost: bool = False) -> dict:
    """
    Generate a full "POV: I am a ___" animated reel end to end.

    topic:        what the character is, e.g. "a tomato". (Ignored if you pass
                  your own script_json.)
    style:        script tone: funny | emotional | dramatic.
    quality:      "fast" (cheap) or "hq" (best) Veo tier.
    max_scenes:   max animated scenes (each = one paid 8s clip).
    caption_style:boldbox | karaoke | facts | cinematic | quotes | typewriter.
    music_mood:   optional bg-music mood hint ("calm","epic","fun"...). ""=auto.
    script_json:  OPTIONAL — paste a script from write_pov_script (as JSON) to
                  render exactly that instead of writing a new one.
    confirm_cost: SAFETY — must be True to actually spend money on Veo. If
                  False, returns the cost estimate + script only (a dry run).

    Returns the final mp4 path, thumbnail, caption, hashtags, and cost.
    Voice/captions/assembly are free; only Veo clips cost money.
    """
    if not _HAVE_RF:
        return {"error": f"reels-factory helpers not importable: {_RF_ERR}. "
                         f"Keep pov-reels next to the reels-factory folder."}
    key = _gemini_key()
    if not key:
        return {"error": "No GEMINI_API_KEY. Put it in pov-reels/.env or "
                         "nano-banana/api-key.txt."}

    # 1) script (reuse pasted one or write fresh)
    if script_json.strip():
        try:
            script = json.loads(script_json)
        except Exception as e:
            return {"error": f"script_json is not valid JSON: {e}"}
    else:
        if not topic.strip():
            return {"error": "Give a topic (e.g. 'a tomato') or a script_json."}
        script = scriptwriter.write_script(topic, key, style=style,
                                           max_scenes=max_scenes)

    scenes = script.get("scenes", [])[:max_scenes]
    if not scenes:
        return {"error": "Script had no scenes."}

    cost = veo.estimate_cost(len(scenes), model=quality)

    # 2) DRY RUN — no spend unless confirmed
    if not confirm_cost:
        return {
            "dry_run": True,
            "message": f"This will generate {len(scenes)} Veo clips and cost "
                       f"about ${cost['total_usd']} ({quality}). Re-run with "
                       f"confirm_cost=True to actually make the video.",
            "estimate": cost,
            "script": script,
        }

    slug = _safe(script.get("title", topic) or "pov")
    work = TMP / slug
    if work.exists():
        shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True, exist_ok=True)

    scene_clips = []
    voice = _voice()
    warnings = []

    # 3) per scene: Veo clip + voiceover + burn captions
    for i, sc in enumerate(scenes):
        visual = sc.get("visual", "")
        line = sc.get("line", "")
        raw = work / f"veo_{i}.mp4"
        try:
            veo.generate_clip(visual + " Cinematic, high detail, no on-screen text.",
                              raw, key, model=quality, aspect="9:16",
                              negative="on-screen text, watermark, subtitles, blurry")
        except Exception as e:
            return {"error": f"Veo failed on scene {i+1}: {e}",
                    "spent_clips": i, "partial_cost": veo.clip_cost(quality) * i}

        # voiceover for the spoken line (free)
        vmp3 = work / f"voice_{i}.mp3"
        try:
            make_voice(line, vmp3, voice=voice, gemini_key=key,
                       style="expressive and playful")
            pad_audio_tail(vmp3, 0.4)
            vdur = get_audio_duration(vmp3)
        except Exception as e:
            warnings.append(f"scene {i+1} voice failed ({e}); using silent clip")
            vmp3, vdur = None, veo.CLIP_SECONDS

        # captions for the line, timed to the voice (or clip) length
        ass = work / f"cap_{i}.ass"
        build_captions(line, vdur, ass, style=caption_style)

        # mux voice + burned captions onto this scene's Veo clip
        scene_out = work / f"scene_{i}.mp4"
        _mux_scene(raw, vmp3, ass, scene_out, vdur)
        scene_clips.append(scene_out)

    # 4) join scenes with a smooth transition
    joined = work / "joined.mp4"
    if len(scene_clips) == 1:
        shutil.copy(scene_clips[0], joined)
    else:
        concat_clips(scene_clips, joined, transition="fade")

    # 5) background music under everything (optional, free)
    final = OUT / f"{slug}.mp4"
    music = None
    try:
        music = pick_music(music_mood)
    except Exception:
        music = None
    if music:
        mix_music_over(joined, music, final, volume=0.18)
    else:
        shutil.copy(joined, final)

    # 6) thumbnail + caption
    thumb = final.with_suffix(".jpg")
    try:
        make_thumbnail(final, thumb, at_seconds=1.0)
    except Exception:
        thumb = None
    hashtags = script.get("hashtags", ["#pov", "#shorts", "#funny"])
    caption = f"{script.get('hook','')}\n\n" + " ".join(hashtags)

    return {
        "ok": True,
        "video": str(final),
        "thumbnail": str(thumb) if thumb else None,
        "title": script.get("title", topic),
        "caption": caption,
        "hashtags": hashtags,
        "scenes": len(scene_clips),
        "length_seconds": round(len(scene_clips) * veo.CLIP_SECONDS, 1),
        "cost_usd": cost["total_usd"],
        "warnings": warnings,
    }


def _mux_scene(veo_clip: Path, voice_mp3, ass_path: Path,
               out_path: Path, dur: float):
    """
    Put the spoken voiceover + burned captions onto one Veo clip and force it
    to 1080x1920. Veo already has ambient audio; we duck it and lay the voice
    on top. Trims/loops the visual to the voice length.
    """
    import subprocess
    ass = str(ass_path).replace("\\", "/").replace(":", "\\:")
    vf = (f"scale=1080:1920:force_original_aspect_ratio=increase,"
          f"crop=1080:1920,subtitles='{ass}'")
    cmd = ["ffmpeg", "-y", "-i", str(veo_clip)]
    if voice_mp3 and Path(voice_mp3).exists():
        cmd += ["-i", str(voice_mp3),
                "-filter_complex",
                f"[0:v]{vf}[v];"
                f"[0:a]volume=0.15[amb];"
                f"[amb][1:a]amix=inputs=2:duration=longest:dropout_transition=0[a]",
                "-map", "[v]", "-map", "[a]"]
    else:
        cmd += ["-vf", vf]
    cmd += ["-t", f"{max(dur, 1.0):.2f}",
            "-c:v", "libx264", "-preset", "fast", "-crf", "22",
            "-c:a", "aac", "-b:a", "128k", "-pix_fmt", "yuv420p",
            "-r", "30", str(out_path)]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return out_path


@mcp.tool
def upload_pov_short(video_path: str, title: str = "", description: str = "",
                     tags: list = None, privacy: str = "public",
                     publish_at: str = "", channel: str = "default") -> dict:
    """
    Upload a finished POV reel to YouTube as a Short (reuses reels-factory's
    YouTube auth). Run yt_authorize in reels-factory once first.

    publish_at: RFC3339 UTC to SCHEDULE (e.g. "2026-07-05T13:00:00Z").
    channel:    which authorized channel nickname to post to.
    """
    if not _HAVE_YT:
        return {"error": "youtube_manager not available (needs reels-factory "
                         "+ google-api-python-client)."}
    if not Path(video_path).exists():
        return {"error": f"file not found: {video_path}"}
    return yt.upload_short(video_path, title or "POV reel",
                           description=description, tags=tags or [],
                           privacy=privacy, publish_at=publish_at,
                           channel=channel)


@mcp.tool
def pov_status() -> dict:
    """Quick health check: keys present, helpers importable, output folder."""
    return {
        "gemini_key": bool(_gemini_key()),
        "reels_factory_helpers": _HAVE_RF or f"MISSING: {_RF_ERR if not _HAVE_RF else ''}",
        "youtube": _HAVE_YT,
        "voice": _voice(),
        "veo_models": {k: v[0] for k, v in veo.VEO_MODELS.items()},
        "output_dir": str(OUT),
        "reels_factory_path": str(RF),
    }


if __name__ == "__main__":
    mcp.run()
