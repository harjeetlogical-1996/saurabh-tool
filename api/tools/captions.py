"""
Captions tool. Takes a finished audio-to-video job and burns subtitles
into a *new* mp4 alongside the original.

Pipeline:
  1. Pull the parent job. Validate it's done and that we can find both
     the rendered mp4 and the original audio.
  2. Decrypt the user's Gemini key (so we use their quota, not ours).
  3. Ask Gemini Flash to transcribe the audio with word-level timestamps.
     We send the audio file directly via files.upload + a JSON response
     schema asking for [{word, start, end}].
  4. Group words into lines of `words_per_line` and write an ASS subtitle
     file. The style preset controls colours / outline / highlight.
  5. Run ffmpeg with the `ass=` filter to burn subtitles into a new mp4.
  6. Stamp the job doc with output path + a sidecar .srt path so the
     frontend can offer both the captioned mp4 and a plain SRT download.
"""

from __future__ import annotations

import concurrent.futures as cf
import json
import os
import re
import subprocess
import tempfile
import threading
import shutil
import time
from pathlib import Path
from typing import Any, Optional

from jobs import (
    CancelledError,
    progress,
    raise_if_cancelled,
    register_proc,
    unregister_proc,
    update_job,
    get_job,
)
from user_keys import get_gemini_key, NoApiKeyError


TRANSCRIBE_MODEL = "gemini-flash-latest"

# Audio longer than this gets split into parallel chunks for transcription.
# Single Gemini call on a 10-min file routinely takes 60-90s; 4 parallel
# 60s chunks finish in ~25s and the upload calls overlap network latency
# with each other.
TRANSCRIBE_CHUNK_THRESHOLD_SEC = 75.0
TRANSCRIBE_CHUNK_SIZE_SEC = 60.0
TRANSCRIBE_PARALLEL_WORKERS = 4

ASSETS = Path(__file__).parent.parent / "assets"
FONT_PATH = ASSETS / "fonts" / "Inter-Bold.ttf"


# ---- ffmpeg helpers (mirrors audio_to_video.py) -------------------------

def _ffmpeg() -> str:
    import shutil as _sh
    candidates = [
        "ffmpeg",
        r"C:\Users\Admin\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1-full_build\bin\ffmpeg.exe",
    ]
    for c in candidates:
        if c == "ffmpeg" and _sh.which("ffmpeg"):
            return "ffmpeg"
        if os.path.isfile(c):
            return c
    raise RuntimeError("ffmpeg not found.")


def _run_subprocess(job_id: Optional[str], cmd: list[str]) -> None:
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if job_id:
        register_proc(job_id, proc)
    try:
        stdout, stderr = proc.communicate()
    finally:
        if job_id:
            unregister_proc(job_id, proc)
    if proc.returncode != 0:
        if job_id:
            try:
                raise_if_cancelled(job_id)
            except CancelledError:
                raise
        raise subprocess.CalledProcessError(
            proc.returncode, cmd, output=stdout, stderr=stderr
        )


_FFMPEG_TIME_RE = re.compile(r"time=(\d+):(\d+):([\d.]+)")


def _run_ffmpeg_with_progress(
    job_id: Optional[str],
    cmd: list[str],
    total_duration_sec: float,
    progress_lo: int,
    progress_hi: int,
    message_template: str = "Burning captions ({pct}%)",
) -> None:
    """
    Like _run_subprocess but streams ffmpeg stderr so the user sees
    real-time progress instead of an apparent freeze at progress_lo.
    Maps ffmpeg's `time=HH:MM:SS.xx` line into the [progress_lo..progress_hi]
    window so the parent caller's progress bookkeeping still makes sense.
    """
    # We pipe stdout to DEVNULL and stderr to a pipe we drain in real time.
    # bufsize=1 (line-buffered) + universal_newlines for str output.
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        bufsize=1,
        universal_newlines=True,
    )
    if job_id:
        register_proc(job_id, proc)
    try:
        last_reported = progress_lo
        # Throttle Mongo writes — ffmpeg emits many time= lines per second.
        last_update_ts = 0.0
        for line in proc.stderr or []:
            m = _FFMPEG_TIME_RE.search(line)
            if not m:
                continue
            try:
                h, mm, ss = m.groups()
                t_sec = int(h) * 3600 + int(mm) * 60 + float(ss)
            except ValueError:
                continue
            if total_duration_sec <= 0:
                continue
            frac = min(1.0, t_sec / total_duration_sec)
            pct = progress_lo + int(
                (progress_hi - progress_lo) * frac
            )
            if pct <= last_reported:
                continue
            now = time.time()
            if now - last_update_ts < 0.5:
                continue
            last_update_ts = now
            last_reported = pct
            if job_id:
                progress(
                    job_id,
                    pct=pct,
                    message=message_template.format(pct=pct),
                )
        proc.wait()
    finally:
        if job_id:
            unregister_proc(job_id, proc)
    if proc.returncode != 0:
        if job_id:
            try:
                raise_if_cancelled(job_id)
            except CancelledError:
                raise
        raise subprocess.CalledProcessError(
            proc.returncode, cmd, output=None, stderr=None
        )


# ---- Gemini transcription with word-level timestamps -------------------

def _transcribe_words(client, audio_path: Path, retries: int = 3) -> list[dict]:
    """
    Returns a list of {word, start, end} with timestamps in seconds.
    Falls back to a coarser sentence-level grouping if the structured
    output fails repeatedly.
    """
    from google.genai import types as gtypes

    instruction = """
Listen to this audio carefully. Transcribe every spoken word and return
it with word-level timing.

Return STRICT JSON (no markdown fences):
{
  "words": [
    {"word": "Hello", "start": 0.12, "end": 0.46},
    {"word": "world", "start": 0.55, "end": 0.91},
    ...
  ]
}

Rules:
- One word per item (split on whitespace; keep punctuation attached to
  the previous word).
- Times in SECONDS (not ms), with up to 2 decimal places.
- Times must be monotonically non-decreasing.
- If the audio has no speech, return {"words": []}.
"""

    last_err: Optional[str] = None
    for attempt in range(retries):
        try:
            uploaded = client.files.upload(file=str(audio_path))
            resp = client.models.generate_content(
                model=TRANSCRIBE_MODEL,
                contents=[uploaded, instruction],
                config=gtypes.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.0,
                ),
            )
            text = (resp.text or "").strip()
            text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
            parsed = json.loads(text)

            words: list[dict] = []
            raw = parsed.get("words") if isinstance(parsed, dict) else parsed
            if not isinstance(raw, list):
                raise ValueError("unexpected JSON shape")
            for item in raw:
                if not isinstance(item, dict):
                    continue
                w = str(item.get("word") or "").strip()
                if not w:
                    continue
                try:
                    s = float(item.get("start"))
                    e = float(item.get("end"))
                except (TypeError, ValueError):
                    continue
                if e < s:
                    e = s + 0.1
                words.append({"word": w, "start": s, "end": e})
            return words
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"
            time.sleep(2.0 * (attempt + 1))
    print(f"[captions._transcribe_words] giving up: {last_err}")
    return []


def _audio_duration_sec(audio_path: Path) -> float:
    """Lightweight ffprobe wrapper used by the chunked transcribe path."""
    try:
        from media_probe import audio_duration_seconds
        return audio_duration_seconds(audio_path)
    except Exception:
        return 0.0


def _slice_audio(src: Path, start: float, dur: float, out: Path) -> None:
    """Cut a [start..start+dur] slice as mp3. Re-encode to be safe across formats."""
    try:
        subprocess.run(
            [_ffmpeg(), "-y",
             "-ss", f"{start:.3f}", "-t", f"{dur:.3f}",
             "-i", str(src),
             "-vn",
             "-acodec", "libmp3lame", "-ab", "96k",
             "-ar", "22050", "-ac", "1",
             str(out)],
            check=True, capture_output=True,
        )
    except subprocess.CalledProcessError:
        # Stream-copy fallback for already-mp3 inputs that re-encode failed on.
        subprocess.run(
            [_ffmpeg(), "-y",
             "-ss", f"{start:.3f}", "-t", f"{dur:.3f}",
             "-i", str(src),
             "-c", "copy", str(out)],
            check=True, capture_output=True,
        )


def transcribe_words(
    client,
    audio_path: Path,
    *,
    job_id: Optional[str] = None,
    progress_lo: int = 10,
    progress_hi: int = 80,
) -> list[dict]:
    """
    Public entrypoint. Transcribes an audio file into word-level
    timestamps, chunking + parallelising for long inputs.

    For audio <= TRANSCRIBE_CHUNK_THRESHOLD_SEC we just call
    `_transcribe_words` directly. Longer audio is split into 60s slices,
    transcribed in parallel, and the chunk-local timestamps are offset
    back to global time before merging.
    """
    duration = _audio_duration_sec(audio_path)

    # Short clip — single call is fine.
    if duration <= 0 or duration <= TRANSCRIBE_CHUNK_THRESHOLD_SEC:
        if job_id:
            progress(job_id, pct=progress_lo, message="Transcribing audio…")
        return _transcribe_words(client, audio_path)

    # Long audio — chunked + parallel.
    starts: list[float] = []
    t = 0.0
    while t < duration:
        starts.append(t)
        t += TRANSCRIBE_CHUNK_SIZE_SEC
    num_chunks = len(starts)

    if job_id:
        progress(
            job_id,
            pct=progress_lo,
            message=(
                f"Long audio ({duration:.0f}s) → {num_chunks} parallel chunks…"
            ),
        )

    tmpdir = Path(tempfile.mkdtemp(prefix="cap_chunks_"))
    chunk_infos: list[dict] = []
    try:
        for i, st in enumerate(starts):
            en = min(st + TRANSCRIBE_CHUNK_SIZE_SEC, duration)
            cpath = tmpdir / f"chunk_{i:03d}.mp3"
            _slice_audio(audio_path, st, en - st, cpath)
            chunk_infos.append({"idx": i, "start": st, "path": cpath})

        results: list[Optional[list[dict]]] = [None] * num_chunks
        done_count = [0]
        lock = threading.Lock()

        def _do(ci: dict) -> None:
            if job_id:
                raise_if_cancelled(job_id)
            local_words = _transcribe_words(client, ci["path"])
            # Offset chunk-local timestamps back to the global timeline.
            offset = ci["start"]
            globalised = [
                {
                    "word": w["word"],
                    "start": w["start"] + offset,
                    "end": w["end"] + offset,
                }
                for w in local_words
            ]
            results[ci["idx"]] = globalised
            with lock:
                done_count[0] += 1
                if job_id:
                    span = max(1, progress_hi - progress_lo - 5)
                    pct = progress_lo + int(span * done_count[0] / num_chunks)
                    progress(
                        job_id,
                        pct=pct,
                        message=f"Transcribed chunk {done_count[0]}/{num_chunks}",
                    )

        with cf.ThreadPoolExecutor(max_workers=TRANSCRIBE_PARALLEL_WORKERS) as ex:
            list(ex.map(_do, chunk_infos))
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    merged: list[dict] = []
    for r in results:
        if r:
            merged.extend(r)
    # Defensive sort + monotonic clamp — chunk boundaries can introduce
    # tiny out-of-order pairs if Gemini overshoots a chunk-end timestamp.
    merged.sort(key=lambda w: (w["start"], w["end"]))
    last_end = 0.0
    for w in merged:
        if w["start"] < last_end:
            w["start"] = last_end
        if w["end"] < w["start"]:
            w["end"] = w["start"] + 0.1
        last_end = w["end"]
    return merged


# ---- ASS subtitle building ----------------------------------------------

def _ass_color(hex_or_name: str) -> str:
    """
    Convert #RRGGBB to ASS &HBBGGRR& format. ASS uses BGR not RGB and the
    alpha is the leading byte (00 = opaque). Accepts named shortcuts.
    """
    presets = {
        "white":   "FFFFFF",
        "black":   "000000",
        "yellow":  "FFE04A",
        "cyan":    "00F0FF",
        "navy":    "0B2A4A",
        "magenta": "FF3D9C",
        # New palette for the 10 added styles
        "red":     "FF3D3D",
        "darkred": "B30000",
        "orange":  "FF8A2B",
        "amber":   "FFC107",
        "green":   "32D74B",
        "lime":    "B6FF3C",
        "blue":    "3B82F6",
        "purple":  "A855F7",
        "pink":    "FF6FCB",
        "hotpink": "FF1493",
        "gold":    "F5C518",
        "silver":  "C0C0C0",
        "cream":   "FFF1D0",
        "paper":   "F4ECD8",
        "gray":    "8E8E93",
        "darkgray":"333333",
    }
    h = presets.get(hex_or_name.lower(), hex_or_name.lstrip("#"))
    if len(h) != 6:
        h = "FFFFFF"
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H00{b}{g}{r}".upper()


def _format_ass_time(t: float) -> str:
    """ASS uses H:MM:SS.cc (centiseconds)."""
    if t < 0:
        t = 0.0
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _group_words_into_lines(words: list[dict], words_per_line: int) -> list[dict]:
    """Group consecutive word objects into N-word lines with merged timing."""
    out: list[dict] = []
    n = max(1, int(words_per_line))
    for i in range(0, len(words), n):
        chunk = words[i : i + n]
        if not chunk:
            continue
        text = " ".join(w["word"] for w in chunk).strip()
        out.append({
            "text": text,
            "start": float(chunk[0]["start"]),
            "end": float(chunk[-1]["end"]),
            # Per-word timing is kept for karaoke effect.
            "words": chunk,
        })
    return out


STYLE_PRESETS = {
    # ----- Original 4 -----
    # Plain — white text, semi-transparent black pill behind, bottom
    "plain": {
        "label": "Plain",
        "primary": "white",
        "outline": "black",
        "outline_width": 2,
        "back_alpha": 80,   # 0=opaque, 255=transparent
        "back_color": "black",
        "font_size_ratio": 0.045,  # of video height
        "bold": True,
        "use_back": True,
    },
    # Bold — white shouty caps, thick black outline, no background
    "bold": {
        "label": "Bold",
        "primary": "white",
        "outline": "black",
        "outline_width": 5,
        "back_alpha": 255,
        "back_color": "black",
        "font_size_ratio": 0.052,
        "bold": True,
        "uppercase": True,
        "use_back": False,
    },
    # Highlight — white text, cyan box behind active line (your brand colour)
    "highlight": {
        "label": "Highlight",
        "primary": "white",
        "outline": "black",
        "outline_width": 1,
        "back_alpha": 0,   # opaque
        "back_color": "cyan",
        "font_size_ratio": 0.045,
        "bold": True,
        "use_back": True,
    },
    # Karaoke — yellow active word, white inactive
    "karaoke": {
        "label": "Karaoke",
        "primary": "yellow",
        "outline": "black",
        "outline_width": 3,
        "back_alpha": 255,
        "back_color": "black",
        "font_size_ratio": 0.05,
        "bold": True,
        "use_back": False,
    },

    # ----- New 4 -----
    # Outline — hollow letters: cyan primary, thick black stroke, no fill bg
    "outline": {
        "label": "Outline",
        "primary": "cyan",
        "outline": "black",
        "outline_width": 6,
        "back_alpha": 255,
        "back_color": "black",
        "font_size_ratio": 0.05,
        "bold": True,
        "use_back": False,
    },
    # Neon — cyan letters with strong cyan halo (heavy outline of same hue +
    # max shadow). Reads as glowing tubes against the video frame.
    "neon": {
        "label": "Neon",
        "primary": "white",
        "outline": "cyan",
        "outline_width": 4,
        "shadow": 4,        # px shadow used as soft glow halo
        "back_alpha": 255,
        "back_color": "black",
        "font_size_ratio": 0.05,
        "bold": True,
        "use_back": False,
    },
    # Gradient (cheat) — solid cyan primary on a thick navy outline so it
    # reads as a vivid two-tone. ASS doesn't do real linear gradients
    # without per-glyph overrides; this gets us 90% of the look.
    "gradient": {
        "label": "Gradient",
        "primary": "cyan",
        "outline": "navy",
        "outline_width": 5,
        "back_alpha": 255,
        "back_color": "black",
        "font_size_ratio": 0.052,
        "bold": True,
        "use_back": False,
    },
    # Typewriter — monospace, white on solid-black pill, no outline.
    # Reads like a terminal/mono caption.
    "typewriter": {
        "label": "Typewriter",
        "primary": "white",
        "outline": "black",
        "outline_width": 1,
        "back_alpha": 0,   # opaque pill
        "back_color": "black",
        "font_size_ratio": 0.04,
        "bold": False,
        "use_back": True,
        "fontname": "Courier New",
    },

    # ===== 10 new styles =====

    # CLASSIC / NEWS
    # News-ticker — white serif-feel text on a thin red bar.
    "news": {
        "label": "News",
        "primary": "white",
        "outline": "darkred",
        "outline_width": 2,
        "back_alpha": 0,   # opaque
        "back_color": "darkred",
        "font_size_ratio": 0.044,
        "bold": True,
        "use_back": True,
        "category": "classic",
    },
    # Cinema subtitle — soft white drop, no fill, no caps; lower-third look.
    "cinema": {
        "label": "Cinema",
        "primary": "white",
        "outline": "black",
        "outline_width": 3,
        "back_alpha": 255,
        "back_color": "black",
        "font_size_ratio": 0.038,
        "bold": False,
        "use_back": False,
        "category": "classic",
    },

    # SOCIAL-MEDIA TRENDY
    # MrBeast bold — fat yellow letters, jet-black thick outline + drop shadow.
    "mrbeast": {
        "label": "MrBeast",
        "primary": "yellow",
        "outline": "black",
        "outline_width": 7,
        "shadow": 3,
        "back_alpha": 255,
        "back_color": "black",
        "font_size_ratio": 0.058,
        "bold": True,
        "uppercase": True,
        "use_back": False,
        "category": "trendy",
    },
    # Reels green — neon-lime caps, classic Instagram-Reels aesthetic.
    "reels": {
        "label": "Reels",
        "primary": "lime",
        "outline": "black",
        "outline_width": 5,
        "back_alpha": 255,
        "back_color": "black",
        "font_size_ratio": 0.055,
        "bold": True,
        "uppercase": True,
        "use_back": False,
        "category": "trendy",
    },
    # TikTok pop — hot-pink bold with white outline + pink halo shadow.
    "tiktok": {
        "label": "TikTok",
        "primary": "white",
        "outline": "hotpink",
        "outline_width": 5,
        "shadow": 2,
        "back_alpha": 255,
        "back_color": "black",
        "font_size_ratio": 0.053,
        "bold": True,
        "use_back": False,
        "category": "trendy",
    },

    # MINIMAL
    # Whisper — soft grey lowercase text, almost no outline; understated.
    "whisper": {
        "label": "Whisper",
        "primary": "silver",
        "outline": "black",
        "outline_width": 1,
        "back_alpha": 255,
        "back_color": "black",
        "font_size_ratio": 0.036,
        "bold": False,
        "use_back": False,
        "category": "minimal",
    },
    # Underline — white text with no outline, sitting on a thin cyan
    # background band that mimics a single-line underline.
    "underline": {
        "label": "Underline",
        "primary": "white",
        "outline": "cyan",
        "outline_width": 1,
        "back_alpha": 80,
        "back_color": "navy",
        "font_size_ratio": 0.042,
        "bold": True,
        "use_back": True,
        "category": "minimal",
    },

    # DECORATIVE
    # Sticker — cream paper-ish text on a black pill with thick white border;
    # reads like a vinyl sticker.
    "sticker": {
        "label": "Sticker",
        "primary": "cream",
        "outline": "white",
        "outline_width": 4,
        "back_alpha": 0,
        "back_color": "black",
        "font_size_ratio": 0.046,
        "bold": True,
        "use_back": True,
        "category": "decorative",
    },
    # Comic — bold yellow caps, thick black outline, comic-pop vibe.
    "comic": {
        "label": "Comic",
        "primary": "yellow",
        "outline": "black",
        "outline_width": 6,
        "shadow": 2,
        "back_alpha": 255,
        "back_color": "black",
        "font_size_ratio": 0.054,
        "bold": True,
        "uppercase": True,
        "use_back": False,
        "category": "decorative",
    },
    # Retro — amber-on-black, evokes 80s VHS / arcade marquees.
    "retro": {
        "label": "Retro",
        "primary": "amber",
        "outline": "darkred",
        "outline_width": 4,
        "shadow": 3,
        "back_alpha": 255,
        "back_color": "black",
        "font_size_ratio": 0.05,
        "bold": True,
        "uppercase": True,
        "use_back": False,
        "category": "decorative",
    },
}

POSITIONS = {"top": 8, "middle": 5, "bottom": 2}  # ASS Alignment numpad codes


def _ass_alignment(position: str) -> int:
    return POSITIONS.get(position, 2)


def _write_ass(
    lines: list[dict],
    out_path: Path,
    *,
    width: int,
    height: int,
    style: str,
    position: str,
    uppercase_override: bool = False,
    pos_x_frac: Optional[float] = None,
    pos_y_frac: Optional[float] = None,
    # ---- Per-caption customisation overrides ----
    # Each is optional: when None we use the picked style's preset value.
    # When supplied they replace the preset for this single render.
    primary_color: Optional[str] = None,    # "white" / "#FF3D9C" / etc.
    outline_color: Optional[str] = None,
    outline_width_override: Optional[int] = None,
    bg_color: Optional[str] = None,
    bg_alpha: Optional[int] = None,         # 0=opaque, 255=transparent
    font_size_override: Optional[int] = None,  # absolute px (after our scaling)
    font_family: Optional[str] = None,      # any font name installed in fontsdir
    shadow_override: Optional[int] = None,
) -> None:
    """
    Write an ASS subtitle file.

    Position model:
      - When `pos_x_frac` / `pos_y_frac` are supplied (each 0..1), the
        caption is anchored at that fraction of the source frame
        (0,0=top-left, 1,1=bottom-right) using a per-event \\pos override.
        This is what the editor's drag handle produces.
      - Otherwise we fall back to the discrete `position` ("top" /
        "middle" / "bottom") via ASS Alignment + MarginV. Used when the
        user hasn't dragged yet.

    Customisation:
      Every visual property (primary color, outline, background, font
      size/family) has an override. Picker workflow:
        1. User clicks a style tile → frontend sends `style="mrbeast"`.
        2. User tweaks colors / size in Customize tab → frontend sends
           the override fields above with the explicit user values.
      The preset only fills in fields the user didn't touch.
    """
    preset = STYLE_PRESETS.get(style) or STYLE_PRESETS["plain"]
    use_upper = preset.get("uppercase", False) or uppercase_override
    # Global scale so the captions fit within frame width without libass
    # auto-wrapping (which split each word onto its own line). Tuned by
    # eye on 1080-wide reels content with 4-5 words per line.
    FONT_SCALE = 0.72
    if font_size_override is not None and font_size_override > 0:
        font_size = max(12, int(font_size_override))
    else:
        font_size = max(18, int(height * float(preset["font_size_ratio"]) * FONT_SCALE))
    primary = _ass_color(str(primary_color or preset["primary"]))
    outline = _ass_color(str(outline_color or preset["outline"]))
    back = _ass_color(str(bg_color or preset["back_color"]))
    if bg_alpha is not None:
        back_alpha = max(0, min(255, int(bg_alpha)))
    else:
        back_alpha = int(preset["back_alpha"])
    back_with_alpha = back.replace("&H00", f"&H{back_alpha:02X}", 1)
    border_style = 4 if preset["use_back"] else 1   # 4 = box bg, 1 = outline only
    if outline_width_override is not None:
        outline_w = max(0, int(outline_width_override))
    else:
        outline_w = int(preset["outline_width"])
    if shadow_override is not None:
        shadow_w = max(0, int(shadow_override))
    else:
        shadow_w = int(preset.get("shadow", 0))   # Used by neon for the halo
    bold = -1 if preset.get("bold") else 0
    alignment = _ass_alignment(position)
    fontname = str(font_family or preset.get("fontname") or "Inter")

    margin_v = max(40, int(height * 0.07))
    # Horizontal safety margin. 5% each side gives long captions room
    # without libass auto-wrapping them into 1-word lines on narrow
    # vertical formats.
    margin_h = max(40, int(width * 0.05))

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{fontname},{font_size},{primary},&H000000FF&,{outline},{back_with_alpha},{bold},0,0,0,100,100,0,0,{border_style},{outline_w},{shadow_w},{alignment},{margin_h},{margin_h},{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    # \pos overrides Alignment + MarginV. Use whenever the editor sent a
    # fractional drag position. Also use it for the middle preset (since
    # MarginV is ignored by libass at center-anchor).
    pos_prefix = ""
    if pos_x_frac is not None and pos_y_frac is not None:
        x_frac = max(0.0, min(1.0, float(pos_x_frac)))
        y_frac = max(0.0, min(1.0, float(pos_y_frac)))
        cx = int(round(width * x_frac))
        cy = int(round(height * y_frac))
        pos_prefix = f"{{\\an5\\pos({cx},{cy})}}"
    elif alignment == 5:
        cx = width // 2
        cy = height // 2
        pos_prefix = f"{{\\pos({cx},{cy})}}"

    events: list[str] = []
    for line in lines:
        text = line["text"]
        if use_upper:
            text = text.upper()

        if style == "karaoke":
            # Per-word \k duration in centiseconds. The line starts at the
            # first word's start; each word's \k advances the highlight.
            line_start = float(line["start"])
            parts: list[str] = []
            for w in line["words"]:
                cs = max(1, int(round((float(w["end"]) - float(w["start"])) * 100)))
                wt = w["word"].upper() if use_upper else w["word"]
                parts.append(f"{{\\kf{cs}}}{wt}")
            text = pos_prefix + " ".join(parts)
            start = _format_ass_time(line_start)
            end = _format_ass_time(float(line["end"]))
            events.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}")
        else:
            start = _format_ass_time(float(line["start"]))
            end = _format_ass_time(float(line["end"]))
            # Escape commas/braces that would break ASS field parsing.
            safe = text.replace("{", "(").replace("}", ")").replace(",", "\\،")
            events.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{pos_prefix}{safe}")

    out_path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")


def _write_srt(lines: list[dict], out_path: Path) -> None:
    """Standard SRT for users who want to upload separately."""
    def fmt(t: float) -> str:
        ms = int(round((t - int(t)) * 1000))
        s = int(t) % 60
        m = (int(t) // 60) % 60
        h = int(t) // 3600
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    chunks: list[str] = []
    for i, ln in enumerate(lines, start=1):
        chunks.append(f"{i}\n{fmt(float(ln['start']))} --> {fmt(float(ln['end']))}\n{ln['text']}\n")
    out_path.write_text("\n".join(chunks), encoding="utf-8")


# ---- Probe video dimensions for ASS PlayRes -----------------------------

def _video_dims(video_path: Path) -> tuple[int, int]:
    import shutil as _sh
    ffprobe = "ffprobe" if _sh.which("ffprobe") else r"C:\Users\Admin\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1-full_build\bin\ffprobe.exe"
    out = subprocess.run(
        [ffprobe, "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height",
         "-of", "csv=p=0:s=x", str(video_path)],
        capture_output=True, text=True, check=True,
    )
    w_s, _, h_s = out.stdout.strip().partition("x")
    return int(w_s or "1080"), int(h_s or "1920")


# ---- Job handler --------------------------------------------------------

def handle(job_id: str, user_id: str, params: dict) -> None:
    """
    params: {
      "parentJobId": <ObjectId of audio-to-video job>,
      "options": {
        "style": "plain"|"bold"|"highlight"|"karaoke",
        "position": "top"|"middle"|"bottom",
        "wordsPerLine": int,
        "uppercase": bool (optional override)
      }
    }
    """
    parent_id = params.get("parentJobId")
    if not parent_id:
        raise RuntimeError("parentJobId is required.")

    parent = get_job(parent_id, user_id=user_id)
    if not parent:
        raise RuntimeError("Parent video job not found.")
    if parent.get("status") != "done":
        raise RuntimeError("Parent video isn't done yet.")

    parent_video = parent.get("outputPath")
    parent_params = parent.get("params") or {}
    parent_audio = parent_params.get("audioPath")
    if not parent_video or not Path(parent_video).exists():
        raise RuntimeError("Parent video file is missing on disk.")
    if not parent_audio or not Path(parent_audio).exists():
        raise RuntimeError("Parent audio file is missing on disk; can't transcribe.")

    parent_video = Path(parent_video)
    parent_audio = Path(parent_audio)

    # Options + defaults
    opts = params.get("options") or {}
    style = opts.get("style") or "bold"
    if style not in STYLE_PRESETS:
        style = "bold"
    position = opts.get("position") or "bottom"
    if position not in POSITIONS:
        position = "bottom"
    words_per_line = int(opts.get("wordsPerLine") or 2)
    words_per_line = max(1, min(8, words_per_line))
    uppercase = bool(opts.get("uppercase", False))
    pos_x_frac = opts.get("posXFrac")
    pos_y_frac = opts.get("posYFrac")
    pos_x_frac = float(pos_x_frac) if pos_x_frac is not None else None
    pos_y_frac = float(pos_y_frac) if pos_y_frac is not None else None
    # Per-render style overrides from the Customize tab. Each key is
    # optional — _write_ass falls back to the chosen preset otherwise.
    primary_color = opts.get("primaryColor") or None
    outline_color = opts.get("outlineColor") or None
    outline_width_override = opts.get("outlineWidth")
    if outline_width_override is not None:
        try:
            outline_width_override = max(0, min(20, int(outline_width_override)))
        except (TypeError, ValueError):
            outline_width_override = None
    bg_color = opts.get("bgColor") or None
    bg_alpha = opts.get("bgAlpha")
    if bg_alpha is not None:
        try:
            bg_alpha = max(0, min(255, int(bg_alpha)))
        except (TypeError, ValueError):
            bg_alpha = None
    font_size_override = opts.get("fontSize")
    if font_size_override is not None:
        try:
            font_size_override = max(12, min(200, int(font_size_override)))
        except (TypeError, ValueError):
            font_size_override = None
    font_family = opts.get("fontFamily") or None
    shadow_override = opts.get("shadow")
    if shadow_override is not None:
        try:
            shadow_override = max(0, min(20, int(shadow_override)))
        except (TypeError, ValueError):
            shadow_override = None

    # 1. Decrypt user key (only needed if we don't have a cached transcript).
    raise_if_cancelled(job_id)

    # 2. Transcribe with word-level timing — but first check the parent
    #    job for a cached transcript. The audio for a given audio-to-video
    #    job never changes after the original render, so once we've
    #    transcribed it we can reuse the words for every subsequent style
    #    or position change. This is the single biggest cost saver: a
    #    user who clicks through 4 styles only pays Gemini once instead
    #    of four times.
    cached_words = parent.get("transcriptWords")
    if cached_words and isinstance(cached_words, list) and len(cached_words) > 0:
        progress(
            job_id,
            pct=55,
            message=f"Using cached transcript ({len(cached_words)} words)…",
        )
        words = cached_words
    else:
        try:
            api_key = get_gemini_key(user_id, user_plan=params.get("userPlan") or "")
        except NoApiKeyError as e:
            raise RuntimeError(str(e))
        from google import genai
        client = genai.Client(api_key=api_key)
        # Chunked + parallel for long audio. Single call for short clips.
        words = transcribe_words(
            client, parent_audio,
            job_id=job_id, progress_lo=10, progress_hi=55,
        )
        if not words:
            raise RuntimeError("Transcription returned no words. Is there speech in the audio?")
        # Stash on the parent so future captions jobs reuse this transcript.
        update_job(str(parent_id), transcriptWords=words)
    raise_if_cancelled(job_id)

    progress(job_id, pct=55, message=f"Got {len(words)} words. Building captions…")

    # 3. Group + write ASS + SRT
    lines = _group_words_into_lines(words, words_per_line)
    if not lines:
        raise RuntimeError("Couldn't group transcription into caption lines.")

    width, height = _video_dims(parent_video)
    workdir = parent_video.parent
    ass_path = workdir / f"{parent_video.stem}.captions.ass"
    srt_path = workdir / f"{parent_video.stem}.captions.srt"
    _write_ass(
        lines, ass_path,
        width=width, height=height,
        style=style, position=position,
        uppercase_override=uppercase,
        pos_x_frac=pos_x_frac, pos_y_frac=pos_y_frac,
        primary_color=primary_color,
        outline_color=outline_color,
        outline_width_override=outline_width_override,
        bg_color=bg_color,
        bg_alpha=bg_alpha,
        font_size_override=font_size_override,
        font_family=font_family,
        shadow_override=shadow_override,
    )
    _write_srt(lines, srt_path)

    raise_if_cancelled(job_id)

    # 4. Burn into a NEW mp4 next to the original (never overwrite).
    # Progress 70 → 95 is driven off ffmpeg's own time= reporting; old
    # code froze at 70 for the entire encode because we waited on
    # communicate() with no streaming.
    progress(job_id, pct=70, message="Burning captions into video…")
    out_path = workdir / f"{parent_video.stem}.captioned.mp4"

    # libass needs the font file resolvable. Easiest portable trick:
    # tell ass= to use a fontsdir pointing at our bundled fonts folder.
    fonts_dir = FONT_PATH.parent.resolve().as_posix()
    ass_filter_path = ass_path.resolve().as_posix().replace(":", "\\:")
    fonts_dir_escaped = fonts_dir.replace(":", "\\:")
    vf = f"ass='{ass_filter_path}':fontsdir='{fonts_dir_escaped}'"

    # Probe parent video duration so the streamed progress is meaningful.
    burn_total_sec = 0.0
    try:
        from media_probe import audio_duration_seconds
        burn_total_sec = audio_duration_seconds(parent_video)
    except Exception:
        pass

    _run_ffmpeg_with_progress(
        job_id,
        [
            _ffmpeg(), "-y",
            "-i", str(parent_video),
            "-vf", vf,
            # `preset faster` ~2x quicker than `medium` for very minor
            # quality loss; ASS overlay is what the user notices, not
            # the underlying bitrate. crf 22 keeps file size sane.
            "-c:v", "libx264", "-preset", "faster", "-crf", "22",
            "-c:a", "copy",
            "-movflags", "+faststart",
            str(out_path),
        ],
        total_duration_sec=burn_total_sec,
        progress_lo=70,
        progress_hi=95,
        message_template="Burning captions ({pct}%)",
    )

    raise_if_cancelled(job_id)

    # 5. Stamp success
    update_job(
        job_id,
        status="done",
        progress=100,
        message=f"Burned {len(lines)} caption lines · {style} style",
        outputPath=str(out_path),
        outputContentType="video/mp4",
        # Extras the frontend will read to surface SRT + parent linkage.
        srtPath=str(srt_path),
        parentJobId=str(parent_id),
    )

    # Stamp the PARENT video job so the card immediately shows the
    # captioned variant in place of the original. Frontend reads
    # `activeCaptionsJobId` and `activeCaptionsStyle` to pick which mp4
    # URL to render. Removing captions = unset these on the parent
    # (handler in app.py at /me/jobs/{id}/captions/clear).
    update_job(
        str(parent_id),
        activeCaptionsJobId=job_id,
        activeCaptionsStyle=style,
    )

    # Best-effort cleanup of the .ass scratch file (we keep .srt for download).
    try:
        ass_path.unlink()
    except Exception:
        pass
