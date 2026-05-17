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


# Anything that isn't a letter, digit, apostrophe (for "don't"), or hyphen
# (for "well-known"). Keeps the spoken word, drops the punctuation Gemini
# was attaching like "saurabh.", "hello,", "okay:" → "saurabh", "hello", "okay".
_PUNCT_STRIP_RE = re.compile(r"[^\w'\-ऀ-ॿ]+", re.UNICODE)


def _clean_word(w: str) -> str:
    """Strip leading/trailing punctuation. Returns "" for tokens that are
    nothing but punctuation (so the caller can skip them)."""
    if not w:
        return ""
    cleaned = _PUNCT_STRIP_RE.sub("", w).strip()
    return cleaned


def _sanitize_words(words: list[dict]) -> list[dict]:
    """Strip punctuation from every word entry; drop now-empty entries.
    Safe to call on either fresh-transcribed words or cached words from
    the parent job doc — so old jobs re-rendered after this fix still
    come out clean."""
    out: list[dict] = []
    for w in words or []:
        if not isinstance(w, dict):
            continue
        cleaned = _clean_word(str(w.get("word") or ""))
        if not cleaned:
            continue
        try:
            s = float(w.get("start"))
            e = float(w.get("end"))
        except (TypeError, ValueError):
            continue
        out.append({"word": cleaned, "start": s, "end": e})
    return out

# Audio longer than this gets split into parallel chunks for transcription.
# Single Gemini call on a 10-min file routinely takes 60-90s; 4 parallel
# 60s chunks finish in ~25s and the upload calls overlap network latency
# with each other.
TRANSCRIBE_CHUNK_THRESHOLD_SEC = 75.0
TRANSCRIBE_CHUNK_SIZE_SEC = 60.0
TRANSCRIBE_PARALLEL_WORKERS = 4

# Process-wide cap on concurrent Gemini transcribe calls. Multiple bulk
# jobs running in parallel would otherwise multiply (4 per job × N jobs)
# and rate-limit each other. This semaphore serialises overflow so each
# call gets full bandwidth instead of all of them stalling.
_TRANSCRIBE_GLOBAL_SEMAPHORE = threading.Semaphore(
    int(os.environ.get("TRANSCRIBE_GLOBAL_CONCURRENCY", "4"))
)

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

Rules:
- One spoken word per item. DO NOT include punctuation — return only the
  bare word (e.g. "hello" not "hello,", "saurabh" not "saurabh.").
- Times in SECONDS (not ms), with up to 2 decimal places.
- Times must be monotonically non-decreasing.
- If the audio has no speech, return an empty list.
"""

    # Strongly-typed response schema — eliminates the "Gemini returned
    # malformed JSON" failure mode that caused silent retries+slowdowns.
    response_schema = {
        "type": "object",
        "properties": {
            "words": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "word": {"type": "string"},
                        "start": {"type": "number"},
                        "end": {"type": "number"},
                    },
                    "required": ["word", "start", "end"],
                },
            },
        },
        "required": ["words"],
    }

    # Hard upper bound per Gemini call. Without this, a single stuck
    # request can wedge a worker thread for many minutes — exactly the
    # "job sits at 'Transcribing audio…' for 6 min" symptom users saw.
    GEMINI_CALL_TIMEOUT_SEC = 90.0

    def _do_one_call() -> str:
        uploaded = client.files.upload(file=str(audio_path))
        resp = client.models.generate_content(
            model=TRANSCRIBE_MODEL,
            contents=[uploaded, instruction],
            config=gtypes.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=response_schema,
                temperature=0.0,
            ),
        )
        return (resp.text or "").strip()

    last_err: Optional[str] = None
    for attempt in range(retries):
        try:
            # cf.ThreadPoolExecutor for a timeout that actually fires on
            # network-stuck calls. The underlying request will keep
            # running in its thread until the SDK returns, but we move on.
            with _TRANSCRIBE_GLOBAL_SEMAPHORE:
                with cf.ThreadPoolExecutor(max_workers=1) as ex:
                    fut = ex.submit(_do_one_call)
                    text = fut.result(timeout=GEMINI_CALL_TIMEOUT_SEC)
            text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
            parsed = json.loads(text)

            words: list[dict] = []
            raw = parsed.get("words") if isinstance(parsed, dict) else parsed
            if not isinstance(raw, list):
                raise ValueError("unexpected JSON shape")
            for item in raw:
                if not isinstance(item, dict):
                    continue
                raw_w = str(item.get("word") or "").strip()
                w = _clean_word(raw_w)
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
            # Print on every retry so a hung transcribe shows WHICH call
            # is failing and why, instead of silently sleeping in the loop.
            print(f"[captions._transcribe_words] attempt {attempt+1}/{retries} failed: {last_err}")
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
    language: Optional[str] = None,
) -> list[dict]:
    """
    Public entrypoint. Transcribes an audio file into word-level
    timestamps.

    Provider routing via TRANSCRIBE_PROVIDER env var:
      - "whisper" (default): local faster-whisper. Free, native word
        alignment, no chunking needed. Best caption-audio sync.
      - "gemini": Gemini Flash via the chunked+parallel path below.
        Kept as fallback for environments where the whisper model can't
        load (low memory, missing deps). `client` must be a genai.Client.

    On whisper failure we fall back to Gemini automatically — keeps
    captions working even if the whisper model can't load.
    """
    provider = os.environ.get("TRANSCRIBE_PROVIDER", "whisper").lower()

    if provider == "whisper":
        try:
            from .whisper_local import transcribe_words_local
        except ImportError:
            try:
                from whisper_local import transcribe_words_local  # type: ignore
            except ImportError:
                from tools.whisper_local import transcribe_words_local  # type: ignore
        if job_id:
            # Generic message — never expose the underlying engine to users.
            # If another job is already transcribing we surface that fact
            # so the user understands the 15% bar isn't frozen — they're
            # just queued behind another video on the same CPU pipeline.
            try:
                from .whisper_local import TRANSCRIBE_BUSY  # type: ignore
            except ImportError:
                try:
                    from whisper_local import TRANSCRIBE_BUSY  # type: ignore
                except ImportError:
                    from tools.whisper_local import TRANSCRIBE_BUSY  # type: ignore
            if TRANSCRIBE_BUSY.is_set():
                progress(
                    job_id,
                    pct=progress_lo,
                    message="Waiting in transcribe queue…",
                )
            else:
                progress(job_id, pct=progress_lo, message="Transcribing audio…")

        # Whisper decode is slow on CPU (~3 min per 1 min audio at the
        # medium model), so without a streamed progress signal the UI
        # bar freezes at progress_lo for minutes. We surface per-segment
        # progress as it decodes.
        def _on_seg(frac: float, seg_end: float, duration: float) -> None:
            if not job_id:
                return
            span = max(1, progress_hi - 5 - progress_lo)
            pct = progress_lo + int(span * frac)
            progress(
                job_id,
                pct=pct,
                message=f"Transcribing audio… {int(seg_end)}s / {int(duration)}s",
            )

        try:
            words = transcribe_words_local(
                audio_path,
                language=language,
                on_progress=_on_seg,
            )
            if job_id:
                progress(job_id, pct=progress_hi - 5, message=f"Transcribed {len(words)} words.")
            # Apply the same punctuation/whitespace cleanup the Gemini
            # path already runs through _clean_word.
            cleaned: list[dict] = []
            for w in words:
                txt = _clean_word(str(w.get("word") or ""))
                if not txt:
                    continue
                cleaned.append({"word": txt, "start": float(w["start"]), "end": float(w["end"])})
            return cleaned
        except Exception as e:
            print(f"[captions.transcribe_words] whisper failed, falling back to gemini: {type(e).__name__}: {e}")
            # fall through to gemini path below

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
    # Plain — white text, semi-transparent black pill behind, bottom.
    # outline_width / shadow are now % of font_size (was abs pixels).
    "plain": {
        "label": "Plain",
        "primary": "white",
        "outline": "black",
        "outline_width": 9,   # % of font size
        "back_alpha": 80,   # 0=opaque, 255=transparent
        "back_color": "black",
        "font_size_ratio": 0.045,  # of video height
        "bold": True,
        "use_back": True,
    },
    # Highlight — white text, cyan box behind active line (your brand colour)
    "highlight": {
        "label": "Highlight",
        "primary": "white",
        "outline": "black",
        "outline_width": 5,  # % of font size
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
        "outline_width": 7,   # % of font size
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
        "outline_width": 13,  # % of font size
        "back_alpha": 255,
        "back_color": "black",
        "font_size_ratio": 0.05,
        "bold": True,
        "use_back": False,
    },
    # Neon — cyan letters with strong cyan halo. libass shadow is just a
    # solid offset, not a blur, so to read as "glow" we lean hard on the
    # cyan outline. % of font_size keeps ratios stable across resolutions.
    "neon": {
        "label": "Neon",
        "primary": "white",
        "outline": "cyan",
        "outline_width": 16,  # % of font size
        "shadow": 7,          # % of font size
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
        "outline_width": 11,  # % of font size
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
        "outline_width": 5,  # % of font size
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
        "outline_width": 10,  # % of font size
        "back_alpha": 0,   # opaque
        "back_color": "darkred",
        "font_size_ratio": 0.044,
        "bold": True,
        "use_back": True,
        "category": "classic",
    },
    # Cinema subtitle — soft white drop, no fill, no caps; lower-third look.
    # Italic so it reads like proper film subtitle typography.
    "cinema": {
        "label": "Cinema",
        "primary": "white",
        "outline": "black",
        "outline_width": 9,   # % of font size
        "back_alpha": 255,
        "back_color": "black",
        "font_size_ratio": 0.038,
        "bold": False,
        "italic": True,
        "use_back": False,
        "category": "classic",
    },

    # SOCIAL-MEDIA TRENDY
    # MrBeast bold — fat yellow letters, jet-black thick outline + drop shadow.
    # Anton's condensed-bold weight gives the chunky display look.
    "mrbeast": {
        "label": "MrBeast",
        "primary": "yellow",
        "outline": "black",
        "outline_width": 12,  # % of font size — heavy but doesn't fill in
        "shadow": 4,          # % of font size (drop)
        "back_alpha": 255,
        "back_color": "black",
        "font_size_ratio": 0.058,
        # Anton has no native bold; libass would synthesise a fat stroke
        # that distorts the condensed glyphs into rounded blobs. The
        # font is already display-bold at its native weight.
        "bold": False,
        "uppercase": True,
        "use_back": False,
        "category": "trendy",
        "fontname": "Anton",
    },
    # Reels green — neon-lime caps, classic Instagram-Reels aesthetic.
    "reels": {
        "label": "Reels",
        "primary": "lime",
        "outline": "black",
        "outline_width": 10,  # % of font size
        "back_alpha": 255,
        "back_color": "black",
        "font_size_ratio": 0.055,
        # See mrbeast — Anton is display-bold natively, no synthesis.
        "bold": False,
        "uppercase": True,
        "use_back": False,
        "category": "trendy",
        "fontname": "Anton",
    },
    # TikTok pop — hot-pink bold with white outline + pink halo shadow.
    "tiktok": {
        "label": "TikTok",
        "primary": "white",
        "outline": "hotpink",
        "outline_width": 10,  # % of font size
        "shadow": 3,           # % of font size
        "back_alpha": 255,
        "back_color": "black",
        "font_size_ratio": 0.053,
        # See mrbeast — Anton is display-bold natively, no synthesis.
        "bold": False,
        "use_back": False,
        "category": "trendy",
        "fontname": "Anton",
    },

    # MINIMAL
    # Whisper — soft grey lowercase text, almost no outline; understated.
    # `lowercase` is enforced at burn time so the tile preview and the
    # final mp4 stay in lockstep.
    "whisper": {
        "label": "Whisper",
        "primary": "silver",
        "outline": "black",
        "outline_width": 6,  # % of font size
        "back_alpha": 255,
        "back_color": "black",
        "font_size_ratio": 0.036,
        "bold": False,
        "lowercase": True,
        "use_back": False,
        "category": "minimal",
    },
    # Underline — white text with a thick cyan "underline" effect.
    # libass can't do partial-height backgrounds, so we approximate with
    # a thick cyan outline (acts like a heavy underline + edge glow).
    "underline": {
        "label": "Underline",
        "primary": "white",
        "outline": "cyan",
        "outline_width": 12,  # % of font size
        "shadow": 0,
        "back_alpha": 255,
        "back_color": "black",
        "font_size_ratio": 0.046,
        "bold": True,
        "use_back": False,
        "category": "minimal",
    },

    # DECORATIVE
    # Sticker — cream paper-ish text on a black pill with thick white border;
    # reads like a vinyl sticker.
    "sticker": {
        "label": "Sticker",
        "primary": "cream",
        "outline": "white",
        "outline_width": 9,   # % of font size
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
        "outline_width": 11,  # % of font size
        "shadow": 3,           # % of font size
        "back_alpha": 255,
        "back_color": "black",
        "font_size_ratio": 0.054,
        # Bangers is single-weight; synthesised bold ruins the comic style.
        "bold": False,
        "uppercase": True,
        "use_back": False,
        "category": "decorative",
        "fontname": "Bangers",
    },
    # Retro — amber-on-black, evokes 80s VHS / arcade marquees.
    "retro": {
        "label": "Retro",
        "primary": "amber",
        "outline": "darkred",
        "outline_width": 9,   # % of font size
        "shadow": 5,           # % of font size
        "back_alpha": 255,
        "back_color": "black",
        "font_size_ratio": 0.05,
        # See mrbeast — Anton is display-bold natively, no synthesis.
        "bold": False,
        "uppercase": True,
        "use_back": False,
        "category": "decorative",
        "fontname": "Anton",
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
    use_lower = preset.get("lowercase", False)
    # Global scale so the captions fit within frame width without libass
    # auto-wrapping (which split each word onto its own line). Tuned by
    # eye on 1080-wide reels content with 3-4 words per line. Bumped
    # from 0.72 → 0.95 — users felt the captions were too small in the
    # final render compared to the preview tile.
    FONT_SCALE = 0.95
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
    # outline_width / shadow values in STYLE_PRESETS are PERCENTAGES of
    # the actual font_size so the visual proportion stays constant
    # across video resolutions AND matches the cqh-based demo tile.
    # Example: outline_width=10 + font_size=96px → 9.6px stroke.
    if outline_width_override is not None:
        outline_w = max(0, int(outline_width_override))
    else:
        outline_pct = float(preset["outline_width"])
        outline_w = max(0, int(round(font_size * outline_pct / 100)))
    if shadow_override is not None:
        shadow_w = max(0, int(shadow_override))
    else:
        shadow_pct = float(preset.get("shadow", 0))
        shadow_w = max(0, int(round(font_size * shadow_pct / 100)))
    bold = -1 if preset.get("bold") else 0
    italic = -1 if preset.get("italic") else 0
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
Style: Default,{fontname},{font_size},{primary},&H000000FF&,{outline},{back_with_alpha},{bold},{italic},0,0,100,100,0,0,{border_style},{outline_w},{shadow_w},{alignment},{margin_h},{margin_h},{margin_v},1

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
        elif use_lower:
            text = text.lower()

        if style == "karaoke":
            # Per-word \k duration in centiseconds. The line starts at the
            # first word's start; each word's \k advances the highlight.
            line_start = float(line["start"])
            parts: list[str] = []
            for w in line["words"]:
                cs = max(1, int(round((float(w["end"]) - float(w["start"])) * 100)))
                wt = (
                    w["word"].upper() if use_upper
                    else w["word"].lower() if use_lower
                    else w["word"]
                )
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
        # Sanitize on read — strips punctuation from pre-fix cached
        # transcripts so re-renders of older a2v jobs come out clean too.
        words = _sanitize_words(cached_words)
        progress(
            job_id,
            pct=55,
            message=f"Using cached transcript ({len(words)} words)…",
        )
        # If sanitizing changed anything, overwrite the cache so we don't
        # keep redoing this work on every future re-render.
        if words and words != cached_words:
            update_job(str(parent_id), transcriptWords=words)
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
