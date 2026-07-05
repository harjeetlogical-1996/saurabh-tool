"""
Audio -> Video render handler (real pipeline).

Pipeline:
  1. Decrypt the user's Gemini API key
  2. Read audio duration with ffprobe
  3. Plan scenes: ask Gemini Flash to listen and return one image prompt
     per ~2.5s segment (chunked + parallel for long audio)
  4. Generate one image per scene with Gemini Nano Banana (gemini-2.5-flash-image)
  5. Ken Burns animate each image to a clip
  6. Concat clips and mux with the original audio
  7. Stamp the job doc with the output path

Heavy lifting (chunked planning, retries, ffmpeg expressions) is adapted
from the original make_video.py at C:\\Users\\Admin\\Desktop\\audio-video-tool\\.
"""

from __future__ import annotations

import base64
import concurrent.futures as cf
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote

import requests
from PIL import Image, ImageDraw, ImageFont

from jobs import (
    CancelledError,
    progress,
    raise_if_cancelled,
    register_proc,
    unregister_proc,
    update_job,
)
from user_keys import get_gemini_key, NoApiKeyError


def _run_subprocess(job_id: Optional[str], cmd: list[str]) -> None:
    """
    Run an ffmpeg/ffprobe subprocess. If a job_id is given, the Popen is
    registered with the cancellation system so a /cancel call can kill it
    mid-encode. Raises CancelledError if the user cancels while it's running.
    """
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if job_id:
        register_proc(job_id, proc)
    try:
        stdout, stderr = proc.communicate()
    finally:
        if job_id:
            unregister_proc(job_id, proc)
    if proc.returncode != 0:
        # If the user cancelled, the process was killed and the return
        # code will be non-zero — surface the cancel cleanly.
        if job_id:
            try:
                raise_if_cancelled(job_id)
            except CancelledError:
                raise
        raise subprocess.CalledProcessError(
            proc.returncode, cmd, output=stdout, stderr=stderr
        )

# ---- Constants ------------------------------------------------------------

TRANSCRIBE_MODEL = "gemini-flash-latest"
IMAGE_MODEL = "gemini-2.5-flash-image"

# Audio longer than this -> chunk before planning (better per-scene quality).
CHUNK_PLAN_THRESHOLD_SEC = 75.0
PLAN_CHUNK_SIZE_SEC = 60.0
PLAN_PARALLEL_WORKERS = 3

# Auto-pacing: when the user picks "Auto (match audio)" we let Gemini
# decide each scene's duration so a punchy beat gets a 1.5s cut while a
# slow narration sentence lingers 5-6s. These clamps keep the result
# sane regardless of what Gemini returns.
AUTO_PACE_MIN_SEC = 1.5
AUTO_PACE_MAX_SEC = 6.0
# Target average scene length used to compute roughly how many segments
# to ask Gemini for upfront. The model can deviate (that's the point) —
# we just need a starting bucket count.
AUTO_PACE_TARGET_AVG_SEC = 3.0

# Concurrency knobs for the two heaviest stages of the pipeline.
# Image gen is network-bound (Gemini API) so we can run more in flight
# than the CPU has cores. ffmpeg clip rendering is CPU-bound; 4 was the
# sweet spot in our testing on a 4-vCPU machine — too many and libx264
# starves itself.
IMAGE_PARALLEL_WORKERS = 4
CLIP_PARALLEL_WORKERS  = 4

# Default render config for v1 — keep options small to start.
DEFAULTS: dict[str, Any] = {
    "size": "9:16",            # 9:16 | 16:9 | 1:1 | 4:5
    # "auto" = Gemini picks per-scene duration based on audio pacing.
    # A numeric value forces fixed-length scenes (legacy/advanced mode).
    "segment_seconds": "auto",
    "fps": 30,
    "style_preset": "photoreal",
    "animation_style": "ken_burns",
    # Audio language hint for scene-planning. "auto" lets Gemini detect
    # it; otherwise we tell Gemini exactly what language to listen for so
    # it doesn't get confused by Hinglish / regional code-switching. Image
    # prompts are still emitted in ENGLISH regardless (image models
    # understand English best).
    "audio_language": "auto",
}

# Human-readable hint we paste into the planning prompt. Keep names as
# Gemini-readable strings, not codes.
AUDIO_LANGUAGE_HINTS: dict[str, str] = {
    "auto":     "the audio's natural language (detect it)",
    "english":  "English",
    "hindi":    "Hindi",
    "hinglish": "Hinglish (Hindi-English code-switching)",
    "marathi":  "Marathi",
    "tamil":    "Tamil",
    "bengali":  "Bengali",
    "gujarati": "Gujarati",
    "punjabi":  "Punjabi",
    "telugu":   "Telugu",
    "kannada":  "Kannada",
    "malayalam":"Malayalam",
    "spanish":  "Spanish",
    "french":   "French",
    "german":   "German",
    "portuguese":"Portuguese",
    "japanese": "Japanese",
    "korean":   "Korean",
    "arabic":   "Arabic",
    "other":    "the audio's natural language",
}

SIZE_PRESETS: dict[str, tuple[int, int]] = {
    "9:16": (1080, 1920),
    "16:9": (1920, 1080),
    "1:1":  (1080, 1080),
    "4:5":  (1080, 1350),
}

STYLE_PROMPTS: dict[str, str] = {
    "photoreal": (
        "ultra photorealistic, 8k, DSLR photograph, natural lighting, "
        "sharp focus, shallow depth of field, film grain, true to life colors"
    ),
    "cinematic": (
        "cinematic film still, moody lighting, teal and orange color grade, "
        "anamorphic lens, shallow DOF, 35mm, dramatic composition"
    ),
    "3d_pixar": (
        "3D animated style, Pixar-like CGI render, cinematic lighting, "
        "soft shadows, vibrant colors, high detail, octane render"
    ),
    "anime": (
        "Japanese anime style, vibrant cel shading, clean line art, "
        "Studio Ghibli inspired, expressive, pastel colors, detailed backgrounds"
    ),
    "watercolor": (
        "watercolor painting, soft washes, paper texture, hand-painted, "
        "gentle brush strokes, pastel palette"
    ),
    "comic": (
        "American comic book art, bold ink outlines, halftone dots, "
        "dynamic composition, saturated colors"
    ),
}


# ---- ffmpeg wrappers ------------------------------------------------------

def _ffmpeg() -> str:
    candidates = [
        "ffmpeg",
    ]
    for c in candidates:
        if c == "ffmpeg" and shutil.which("ffmpeg"):
            return "ffmpeg"
        if os.path.isfile(c):
            return c
    raise RuntimeError("ffmpeg not found.")


def _ffprobe() -> str:
    candidates = [
        "ffprobe",
        r"C:\Users\Admin\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1-full_build\bin\ffprobe.exe",
    ]
    for c in candidates:
        if c == "ffprobe" and shutil.which("ffprobe"):
            return "ffprobe"
        if os.path.isfile(c):
            return c
    raise RuntimeError("ffprobe not found.")


def _audio_duration(path: Path) -> float:
    out = subprocess.run(
        [
            _ffprobe(), "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True, text=True, check=True,
    )
    try:
        return float(out.stdout.strip())
    except ValueError:
        return 0.0


def _extract_chunk(src: Path, start: float, dur: float, out: Path) -> None:
    try:
        subprocess.run(
            [_ffmpeg(), "-y", "-ss", f"{start:.3f}", "-t", f"{dur:.3f}",
             "-i", str(src), "-c", "copy", str(out)],
            check=True, capture_output=True,
        )
    except subprocess.CalledProcessError:
        # Re-encode if stream copy fails (some MP3s)
        subprocess.run(
            [_ffmpeg(), "-y", "-ss", f"{start:.3f}", "-t", f"{dur:.3f}",
             "-i", str(src), "-vn", "-acodec", "libmp3lame", "-b:a", "128k", str(out)],
            check=True, capture_output=True,
        )


# ---- Gemini scene planning ------------------------------------------------

def _plan_chunk(client, chunk_path: Path, chunk_dur: float,
                num_segments: int, segment_seconds: float,
                language_hint: str = "the audio's natural language (detect it)",
                retries: int = 3) -> list[dict]:
    """Plan a single audio chunk. Returns list of {image_prompt}."""
    from google.genai import types as gtypes

    instruction = f"""
You are given a short audio CLIP of ~{chunk_dur:.2f} seconds (this is ONE CHUNK
from a longer piece of audio — treat it self-contained).

The audio is spoken in {language_hint}. Listen, comprehend the meaning,
then translate the visual concepts into ENGLISH image prompts (image
generation models understand English best regardless of the source
language).

Listen carefully. Split it into exactly {num_segments} consecutive visual
segments of ~{segment_seconds:.1f}s each, tiling the clip.

Return STRICT JSON (no markdown fences):
{{
  "segments": [
    {{"image_prompt": "vivid concrete ENGLISH prompt that VISUALLY matches what is being
      said in segment 1 — describe people, actions, objects, setting, mood. NO generic
      abstract shapes unless the audio is truly abstract. NO text in image."}},
    ...exactly {num_segments} items...
  ]
}}

Be SPECIFIC and CONCRETE. If a narrator talks about coffee, show coffee.
If they describe a city street, show that street. Avoid 'swirling lights'
or 'abstract mood' unless the content is literally abstract.
"""
    last_err: Optional[str] = None
    for attempt in range(retries):
        try:
            uploaded = client.files.upload(file=str(chunk_path))
            resp = client.models.generate_content(
                model=TRANSCRIBE_MODEL,
                contents=[uploaded, instruction],
                config=gtypes.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.3,
                ),
            )
            text = (resp.text or "").strip()
            text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
            parsed = json.loads(text)
            if isinstance(parsed, list):
                segs_raw = parsed
            elif isinstance(parsed, dict):
                segs_raw = parsed.get("segments", []) or []
            else:
                raise ValueError("unexpected JSON type")
            out: list[dict] = []
            for item in segs_raw:
                if isinstance(item, dict):
                    out.append({"image_prompt": (item.get("image_prompt") or "").strip()})
                elif isinstance(item, str):
                    out.append({"image_prompt": item.strip()})
            return out
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"
            time.sleep(2.0 * (attempt + 1))
    print(f"[plan_chunk] giving up after {retries}: {last_err}")
    return [{"image_prompt": f"cinematic scene, part {i+1}"} for i in range(num_segments)]


def _plan_chunk_auto(client, chunk_path: Path, chunk_dur: float,
                     chunk_offset: float,
                     language_hint: str = "the audio's natural language (detect it)",
                     retries: int = 3) -> list[dict]:
    """
    Auto-paced planner. Asks Gemini to listen and decide for itself how
    many scenes are right for this chunk and how long each one should be.

    Returns a list of {start, end, image_prompt} in CHUNK-LOCAL time
    (offset added by the caller). Each scene is clamped to
    [AUTO_PACE_MIN_SEC, AUTO_PACE_MAX_SEC]; the chunk's last scene is
    stretched to cover any rounding residue so total duration == chunk_dur.
    """
    from google.genai import types as gtypes

    instruction = f"""
You are given a short audio CLIP of ~{chunk_dur:.2f} seconds (this is ONE CHUNK
from a longer piece of audio — treat it self-contained).

The audio is spoken in {language_hint}. Listen, comprehend the meaning,
then translate the visual concepts into ENGLISH image prompts (image
generation models understand English best regardless of the source
language).

YOUR JOB: decide where each visual scene SHOULD start and end, matching
the rhythm of the speech.
- Faster pace (rapid sentences, beat changes, exclamations) → shorter
  scenes ({AUTO_PACE_MIN_SEC:.1f}s minimum).
- Slower pace (long pauses, deliberate narration, single sustained
  topic) → longer scenes (up to {AUTO_PACE_MAX_SEC:.1f}s).
- Group consecutive ideas under one image; cut to a new image when the
  topic, mood, or subject shifts.
- Times in SECONDS from the START of THIS CHUNK (0.0 = chunk start).
- Times must be monotonically non-decreasing.
- Cover the entire chunk: segment[0].start == 0, segment[last].end == {chunk_dur:.2f}.

Return STRICT JSON (no markdown fences):
{{
  "segments": [
    {{
      "start": 0.0,
      "end": 2.3,
      "image_prompt": "vivid concrete ENGLISH prompt that visually matches segment 1 —
                       describe people, actions, objects, setting, mood. NO text, NO logos."
    }},
    {{"start": 2.3, "end": 5.8, "image_prompt": "..."}},
    ...
  ]
}}

Be SPECIFIC and CONCRETE. If a narrator talks about coffee, show coffee.
If they describe a city street, show that street. Use {AUTO_PACE_MIN_SEC:.1f}-{AUTO_PACE_MAX_SEC:.1f}
second scenes — never shorter than {AUTO_PACE_MIN_SEC:.1f}s, never longer than
{AUTO_PACE_MAX_SEC:.1f}s.
"""
    last_err: Optional[str] = None
    for attempt in range(retries):
        try:
            uploaded = client.files.upload(file=str(chunk_path))
            resp = client.models.generate_content(
                model=TRANSCRIBE_MODEL,
                contents=[uploaded, instruction],
                config=gtypes.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.3,
                ),
            )
            text = (resp.text or "").strip()
            text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
            parsed = json.loads(text)
            raw = parsed.get("segments") if isinstance(parsed, dict) else parsed
            if not isinstance(raw, list) or not raw:
                raise ValueError("no segments")
            out: list[dict] = []
            cursor = 0.0
            for item in raw:
                if not isinstance(item, dict):
                    continue
                prompt_txt = (item.get("image_prompt") or "").strip()
                if not prompt_txt:
                    continue
                try:
                    s = float(item.get("start", cursor))
                    e = float(item.get("end", cursor + AUTO_PACE_TARGET_AVG_SEC))
                except (TypeError, ValueError):
                    continue
                # Clamp: monotonic, within chunk, min/max scene length.
                s = max(cursor, s)
                e = max(s + AUTO_PACE_MIN_SEC, e)
                e = min(e, s + AUTO_PACE_MAX_SEC)
                e = min(e, chunk_dur)
                if e <= s:
                    continue
                out.append({"start": s, "end": e, "image_prompt": prompt_txt})
                cursor = e
                if cursor >= chunk_dur:
                    break
            if not out:
                raise ValueError("clamped to zero scenes")
            # Stretch last scene to chunk end so no audio is unbacked.
            if out[-1]["end"] < chunk_dur:
                out[-1]["end"] = chunk_dur
            return out
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"
            time.sleep(2.0 * (attempt + 1))
    print(f"[plan_chunk_auto] giving up after {retries}: {last_err}")
    # Fallback: even-split using target average — better than failing the job.
    n = max(1, int(round(chunk_dur / AUTO_PACE_TARGET_AVG_SEC)))
    step = chunk_dur / n
    return [
        {
            "start": i * step,
            "end": min((i + 1) * step, chunk_dur),
            "image_prompt": f"cinematic scene, part {i+1}",
        }
        for i in range(n)
    ]


def _plan_scenes_auto(client, audio_path: Path, duration: float, job_id: str,
                      language_hint: str = "the audio's natural language (detect it)") -> list[dict]:
    """
    Variable-duration planner. Returns {index, start, end, image_prompt}
    where every scene's length is decided by Gemini based on the audio's
    pacing. Used when the user picks "Auto (match audio)" in the UI.
    """
    if duration <= CHUNK_PLAN_THRESHOLD_SEC:
        progress(job_id, pct=10, message="Auto-pacing scenes from audio…")
        local = _plan_chunk_auto(client, audio_path, duration, 0.0, language_hint)
        global_segs = [
            {"start": s["start"], "end": s["end"], "image_prompt": s["image_prompt"]}
            for s in local
        ]
    else:
        chunk_size = PLAN_CHUNK_SIZE_SEC
        starts: list[float] = []
        t = 0.0
        while t < duration:
            starts.append(t)
            t += chunk_size
        num_chunks = len(starts)
        progress(
            job_id, pct=8,
            message=f"Long audio ({duration:.0f}s) → auto-pacing {num_chunks} chunks…",
        )

        tmpdir = Path(tempfile.mkdtemp(prefix="a2v_chunks_"))
        chunk_infos = []
        for i, st in enumerate(starts):
            en = min(st + chunk_size, duration)
            cdur = en - st
            cpath = tmpdir / f"chunk_{i:03d}.mp3"
            _extract_chunk(audio_path, st, cdur, cpath)
            chunk_infos.append({"idx": i, "start": st, "dur": cdur, "path": cpath})

        results: list[Optional[list[dict]]] = [None] * num_chunks
        done_count = [0]
        lock = threading.Lock()

        def _do(ci):
            local = _plan_chunk_auto(
                client, ci["path"], ci["dur"], ci["start"], language_hint,
            )
            # Offset chunk-local times to global timeline.
            offset = ci["start"]
            results[ci["idx"]] = [
                {
                    "start": s["start"] + offset,
                    "end":   s["end"]   + offset,
                    "image_prompt": s["image_prompt"],
                }
                for s in local
            ]
            with lock:
                done_count[0] += 1
                pct = 8 + int(10 * done_count[0] / num_chunks)
                progress(
                    job_id, pct=pct,
                    message=f"Auto-pacing chunk {done_count[0]}/{num_chunks}",
                )

        with cf.ThreadPoolExecutor(max_workers=PLAN_PARALLEL_WORKERS) as ex:
            list(ex.map(_do, chunk_infos))
        shutil.rmtree(tmpdir, ignore_errors=True)

        global_segs: list[dict] = []
        for r in results:
            if r:
                global_segs.extend(r)

    # Final safety: ensure monotonic, span the whole audio.
    if not global_segs:
        global_segs = [{"start": 0.0, "end": duration, "image_prompt": "cinematic scene"}]
    global_segs.sort(key=lambda s: s["start"])
    last_end = 0.0
    for s in global_segs:
        if s["start"] < last_end:
            s["start"] = last_end
        if s["end"] <= s["start"]:
            s["end"] = min(duration, s["start"] + AUTO_PACE_TARGET_AVG_SEC)
        last_end = s["end"]
    global_segs[-1]["end"] = duration  # cover any residue

    for i, s in enumerate(global_segs):
        s["index"] = i
        if not s.get("image_prompt"):
            s["image_prompt"] = "cinematic abstract scene"
    return global_segs


def _plan_scenes(client, audio_path: Path, duration: float,
                 num_segments: int, segment_seconds: float,
                 job_id: str,
                 language_hint: str = "the audio's natural language (detect it)") -> list[dict]:
    """Returns list of {index, start, end, image_prompt}, exactly num_segments long."""
    if duration <= CHUNK_PLAN_THRESHOLD_SEC:
        progress(job_id, pct=10, message="Planning scenes from audio…")
        segs = _plan_chunk(client, audio_path, duration, num_segments,
                           segment_seconds, language_hint)
    else:
        # Chunked + parallel planning for long audio
        chunk_size = PLAN_CHUNK_SIZE_SEC
        starts: list[float] = []
        t = 0.0
        while t < duration:
            starts.append(t)
            t += chunk_size
        num_chunks = len(starts)
        progress(job_id, pct=8,
                 message=f"Long audio ({duration:.0f}s) — splitting into {num_chunks} chunks…")

        tmpdir = Path(tempfile.mkdtemp(prefix="a2v_chunks_"))
        chunk_infos = []
        for i, st in enumerate(starts):
            en = min(st + chunk_size, duration)
            cdur = en - st
            c_segs = max(1, int(round(cdur / segment_seconds)))
            cpath = tmpdir / f"chunk_{i:03d}.mp3"
            _extract_chunk(audio_path, st, cdur, cpath)
            chunk_infos.append({"idx": i, "dur": cdur, "segs": c_segs, "path": cpath})

        results: list[Optional[list[dict]]] = [None] * num_chunks
        done_count = [0]
        lock = threading.Lock()

        def _do(ci):
            segs = _plan_chunk(client, ci["path"], ci["dur"], ci["segs"],
                               segment_seconds, language_hint)
            while len(segs) < ci["segs"]:
                segs.append({"image_prompt": "cinematic scene"})
            results[ci["idx"]] = segs[:ci["segs"]]
            with lock:
                done_count[0] += 1
                pct = 8 + int(10 * done_count[0] / num_chunks)
                progress(job_id, pct=pct,
                         message=f"Chunk {done_count[0]}/{num_chunks} planned")

        with cf.ThreadPoolExecutor(max_workers=PLAN_PARALLEL_WORKERS) as ex:
            list(ex.map(_do, chunk_infos))
        shutil.rmtree(tmpdir, ignore_errors=True)

        segs = []
        for r in results:
            if r:
                segs.extend(r)

    # Normalize to exact count
    while len(segs) < num_segments:
        segs.append({"image_prompt": "cinematic abstract scene"})
    segs = segs[:num_segments]

    for i, s in enumerate(segs):
        s["index"] = i
        s["start"] = i * segment_seconds
        s["end"] = min((i + 1) * segment_seconds, duration)
        if not s.get("image_prompt"):
            s["image_prompt"] = "cinematic abstract scene"

    return segs


# ---- Gemini image generation ----------------------------------------------

def _orientation_hint(size_ratio: str) -> str:
    return {
        "9:16": "Vertical 9:16 portrait composition, tall frame, subject centered.",
        "16:9": "Horizontal 16:9 widescreen composition.",
        "1:1":  "Square 1:1 composition, centered subject.",
        "4:5":  "Vertical 4:5 portrait composition.",
    }.get(size_ratio, "")


def _dims_for_ratio(size_ratio: str):
    return {
        "9:16": (720, 1280),
        "16:9": (1280, 720),
        "1:1":  (1024, 1024),
        "4:5":  (864, 1080),
    }.get(size_ratio, (720, 1280))


def _generate_image_gemini(client, prompt: str, style_prompt: str,
                           size_ratio: str, out_path: Path, retries: int = 7) -> bool:
    """
    Try Gemini Nano Banana with up to N retries. Bumped from 4 to 7 because
    long videos with many segments hit transient 429s often, and a single
    placeholder frame in a 90-segment render is very visible.
    """
    full = (
        f"{prompt}. Style: {style_prompt}. {_orientation_hint(size_ratio)} "
        f"High quality, no text, no watermark, no logos."
    )
    last_err: Optional[str] = None
    for attempt in range(retries):
        try:
            resp = client.models.generate_content(
                model=IMAGE_MODEL,
                contents=[full],
            )
            cands = getattr(resp, "candidates", None) or []
            if cands:
                parts = getattr(cands[0].content, "parts", None) or []
                for part in parts:
                    inline = getattr(part, "inline_data", None)
                    if inline and inline.data:
                        data = inline.data
                        if isinstance(data, str):
                            data = base64.b64decode(data)
                        with open(out_path, "wb") as f:
                            f.write(data)
                        return True
                fr = getattr(cands[0], "finish_reason", None)
                last_err = f"no image part (finish_reason={fr})"
            else:
                last_err = "empty candidates"
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"

        is_rate = last_err and any(
            s in last_err.lower() for s in ("429", "quota", "rate", "resource_exhausted")
        )
        # Cap exponential backoff at 90s; rate-limit waits are longer.
        wait = min(90.0, (6.0 if is_rate else 1.5) * (2 ** attempt))
        time.sleep(wait)

    print(f"[image_gen.gemini] gave up after {retries}: {last_err}")
    return False


def _generate_image_pollinations(prompt: str, style_prompt: str,
                                 size_ratio: str, out_path: Path,
                                 seed: Optional[int] = None,
                                 retries: int = 3) -> bool:
    """
    Free FLUX-based fallback. Different model = different content filter,
    so often succeeds where Gemini's safety stack refuses. Style won't
    perfectly match Gemini frames but better than a placeholder.
    """
    w, h = _dims_for_ratio(size_ratio)
    full = (
        f"{prompt}. Style: {style_prompt}. {_orientation_hint(size_ratio)} "
        f"High quality, no text, no watermark, no logos."
    )
    url = f"https://image.pollinations.ai/prompt/{quote(full)}"
    params: dict[str, Any] = {"width": w, "height": h, "model": "flux", "nologo": "true"}
    if seed is not None:
        params["seed"] = int(seed)

    last_err: Optional[str] = None
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, timeout=180)
            r.raise_for_status()
            if len(r.content) < 2048:
                last_err = f"response too small ({len(r.content)} bytes)"
                raise ValueError(last_err)
            with open(out_path, "wb") as f:
                f.write(r.content)
            return True
        except Exception as e:
            last_err = str(e)
            time.sleep(2.0 * (attempt + 1))
    print(f"[image_gen.pollinations] gave up: {last_err}")
    return False


def _generate_image(client, prompt: str, style_prompt: str, size_ratio: str,
                    out_path: Path, seed: Optional[int] = None) -> tuple[bool, str]:
    """
    Cost-ascending image-gen chain. Returns (success, source) where source
    is the actual provider name that produced the image.

    Order:
      1. Cheap FLUX providers (Together → Replicate → Fireworks)
         — ~₹0.23-0.30/image, indistinguishable quality from Gemini.
      2. Gemini Nano Banana (₹3.30/image) — only if none of the cheap
         providers are configured OR all of them failed.
      3. Pollinations.ai (free, FLUX) — last-resort fallback.
    """
    # Layer 1: cheap FLUX providers
    try:
        import image_providers
        ok, src = image_providers.try_chain(
            prompt, style_prompt, size_ratio, out_path, seed=seed,
        )
        if ok:
            return True, src
    except Exception as e:
        print(f"[image] cheap-chain crashed: {e}")

    # Layer 2: Gemini (kept for tenants without cheap-provider keys yet)
    if _generate_image_gemini(client, prompt, style_prompt, size_ratio, out_path):
        return True, "gemini"

    # Layer 3: free fallback
    if _generate_image_pollinations(prompt, style_prompt, size_ratio, out_path, seed=seed):
        return True, "pollinations"
    return False, "placeholder"


def _make_placeholder(out_path: Path, w: int, h: int, label: str) -> None:
    img = Image.new("RGB", (w, h), color=(13, 13, 16))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 36)
    except Exception:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), label, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    draw.text(((w - tw) / 2, (h - th) / 2), label, font=font, fill=(0, 240, 255))
    img.save(out_path, "JPEG", quality=85)


# ---- Ken Burns clip rendering ---------------------------------------------

def _ken_burns_exprs(index: int, frames: int):
    """
    Frame-fraction Ken Burns. We use `on` (output frame counter inside
    the current input frame) divided by total output frames so motion
    smoothly spans the WHOLE clip — 1.5s or 6s, same arc.

    Important: with `-loop 1` + zoompan, `dn` (displayed input frame
    count) keeps growing past 1, so `on/dn` is NOT [0..1]. We must
    divide by the constant `frames` (computed in Python from duration
    × fps) instead. That's why this function takes `frames` now.
    """
    # End zoom level — bounded so the upscale headroom (1.5x in
    # _animate_clip) doesn't run out and produce a pixelated frame.
    Z = 1.18
    m = index % 4
    if m == 0:
        # Slow zoom-in
        return (
            f"1.0+({Z - 1.0:.4f})*on/{frames}",
            "iw/2-(iw/zoom/2)",
            "ih/2-(ih/zoom/2)",
        )
    if m == 1:
        # Zoom-in with horizontal drift right
        return (
            f"1.0+0.20*on/{frames}",
            f"(iw-iw/zoom)*0.5+(iw-iw/zoom)*0.15*on/{frames}",
            "ih/2-(ih/zoom/2)",
        )
    if m == 2:
        # Zoom-out (start zoomed, ease to neutral)
        return (
            f"{Z:.4f}-({Z - 1.0:.4f})*on/{frames}",
            "iw/2-(iw/zoom/2)",
            "ih/2-(ih/zoom/2)",
        )
    # Zoom-in with vertical drift up
    return (
        f"1.0+0.20*on/{frames}",
        "iw/2-(iw/zoom/2)",
        f"(ih-ih/zoom)*0.5-(ih-ih/zoom)*0.15*on/{frames}",
    )


def _style_exprs(style: str, index: int, frames: int):
    """Map an animation style name to (z, x, y) ffmpeg zoompan expressions.

    `frames` is the total output frame count (duration × fps). All
    expressions normalize against this constant rather than `dn`, since
    `-loop 1` makes `dn` unreliable for the [0..1] progress signal.
    """
    if style == "ken_burns":
        return _ken_burns_exprs(index, frames)
    if style == "zoom_in":
        return (
            f"1.0+0.30*on/{frames}",
            "iw/2-(iw/zoom/2)",
            "ih/2-(ih/zoom/2)",
        )
    if style == "zoom_out":
        return (
            f"1.28-0.28*on/{frames}",
            "iw/2-(iw/zoom/2)",
            "ih/2-(ih/zoom/2)",
        )
    if style == "pan_lr":
        return (
            "1.15",
            f"(iw-iw/zoom)*on/{frames}",
            "ih/2-(ih/zoom/2)",
        )
    if style == "pan_rl":
        return (
            "1.15",
            f"(iw-iw/zoom)*(1-on/{frames})",
            "ih/2-(ih/zoom/2)",
        )
    if style == "pulse":
        # 2 full breath-cycles across the clip
        return (
            f"1.10+0.06*sin(4*PI*on/{frames})",
            "iw/2-(iw/zoom/2)",
            "ih/2-(ih/zoom/2)",
        )
    return _ken_burns_exprs(index, frames)


def _animate_clip(image_path: Path, duration: float, index: int,
                  out_w: int, out_h: int, fps: int, out_path: Path,
                  style: str = "ken_burns",
                  job_id: Optional[str] = None) -> None:
    """
    ffmpeg zoompan recipe. We pre-upscale 1.5x so the zoom has crisp
    headroom, but no more — going to 2x with N concurrent workers
    pushes libx264 over its malloc limit on Windows. We also pin
    libx264 to a single thread per call so the 3-worker pool can't
    stampede the RAM.
    """
    frames = max(2, int(round(duration * fps)))
    z, x, y = _style_exprs(style, index, frames)
    up_w = int(out_w * 1.5)
    up_h = int(out_h * 1.5)
    # IMPORTANT: limit input to exactly 1 still frame so zoompan's
    # `on` counter spans 0..frames-1 across the WHOLE clip. Without
    # this `-loop 1` pumps repeated input frames and zoompan resets
    # `on` per input, producing visible animation hitches / freezes.
    vf = (
        f"scale={up_w}:{up_h}:force_original_aspect_ratio=increase,"
        f"crop={up_w}:{up_h},"
        f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={out_w}x{out_h}:fps={fps},"
        f"setsar=1"
    )
    _run_subprocess(job_id, [
        _ffmpeg(), "-y",
        "-threads", "1",
        "-loop", "1", "-framerate", "1", "-i", str(image_path),
        "-frames:v", str(frames), "-vf", vf,
        "-c:v", "libx264", "-x264-params", "threads=1",
        "-pix_fmt", "yuv420p", "-preset", "faster", "-crf", "21",
        "-r", str(fps), str(out_path),
    ])


def _static_clip(image_path: Path, duration: float, out_w: int, out_h: int,
                 fps: int, out_path: Path,
                 job_id: Optional[str] = None) -> None:
    _run_subprocess(job_id, [
        _ffmpeg(), "-y",
        "-threads", "1",
        "-loop", "1", "-i", str(image_path),
        "-t", f"{duration:.3f}",
        "-vf", f"scale={out_w}:{out_h}:force_original_aspect_ratio=decrease,"
               f"pad={out_w}:{out_h}:(ow-iw)/2:(oh-ih)/2:color=black,"
               f"setsar=1,fps={fps}",
        "-c:v", "libx264", "-x264-params", "threads=1",
        "-pix_fmt", "yuv420p", "-preset", "faster", "-crf", "21",
        str(out_path),
    ])


def _build_video(clips: list[Path], audio_path: Path, out_path: Path, workdir: Path,
                 job_id: Optional[str] = None) -> None:
    concat_file = workdir / "concat.txt"
    concat_file.write_text(
        "\n".join(f"file '{c.resolve().as_posix()}'" for c in clips) + "\n",
        encoding="utf-8",
    )
    silent = workdir / "silent.mp4"
    _run_subprocess(job_id, [
        _ffmpeg(), "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file),
        "-c", "copy", str(silent),
    ])
    _run_subprocess(job_id, [
        _ffmpeg(), "-y", "-i", str(silent), "-i", str(audio_path),
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-shortest", "-movflags", "+faststart", str(out_path),
    ])


# ---- Job handler entry point ----------------------------------------------

def handle(job_id: str, user_id: str, params: dict) -> None:
    audio_path = Path(params["audioPath"])
    if not audio_path.exists():
        raise RuntimeError(f"Uploaded audio not found at {audio_path}")

    opts = {**DEFAULTS, **{k: v for k, v in (params.get("options") or {}).items() if v is not None}}
    size_key = opts["size"] if opts["size"] in SIZE_PRESETS else "9:16"
    out_w, out_h = SIZE_PRESETS[size_key]
    fps = int(opts["fps"])
    # segment_seconds can be a number (fixed-pacing) OR the literal string
    # "auto" (let Gemini decide per scene). Anything unparseable falls back
    # to the auto path since the new default is auto.
    raw_seg = opts.get("segment_seconds", "auto")
    if isinstance(raw_seg, str) and raw_seg.lower() == "auto":
        auto_pace = True
        seg_sec = AUTO_PACE_TARGET_AVG_SEC  # used only for legacy fallback math
    else:
        try:
            seg_sec = float(raw_seg)
            auto_pace = False
        except (TypeError, ValueError):
            auto_pace = True
            seg_sec = AUTO_PACE_TARGET_AVG_SEC
    style_key = opts.get("style_preset") or "photoreal"
    if style_key not in STYLE_PROMPTS:
        style_key = "photoreal"
    style_prompt = STYLE_PROMPTS[style_key]

    # Audio-language hint passed through to scene planning so Gemini
    # comprehends non-English speech correctly. Default = auto-detect.
    lang_key = (opts.get("audio_language") or "auto").lower()
    language_hint = AUDIO_LANGUAGE_HINTS.get(
        lang_key, AUDIO_LANGUAGE_HINTS["auto"]
    )

    # 1. Resolve Gemini key (platform-owned by default; BYO for code-sale users)
    try:
        api_key = get_gemini_key(user_id, user_plan=params.get("userPlan") or "")
    except NoApiKeyError as e:
        raise RuntimeError(str(e))

    # Lazy import — these can be slow to load
    from google import genai
    client = genai.Client(api_key=api_key)

    # 2. Audio duration
    progress(job_id, pct=4, message="Reading audio…")
    duration = _audio_duration(audio_path)
    if duration <= 0:
        raise RuntimeError("Could not read audio duration. Is the file valid?")
    if auto_pace:
        progress(job_id, pct=6,
                 message=f"{duration:.1f}s of audio → auto-paced scenes @ {size_key}")
    else:
        approx = max(1, int(round(duration / seg_sec)))
        progress(job_id, pct=6,
                 message=f"{duration:.1f}s of audio → {approx} scenes @ {size_key}")
    raise_if_cancelled(job_id)

    # 3. Plan scenes (Gemini Flash, listens to the audio)
    if auto_pace:
        segments = _plan_scenes_auto(
            client, audio_path, duration, job_id, language_hint,
        )
    else:
        num_segments = max(1, int(round(duration / seg_sec)))
        segments = _plan_scenes(
            client, audio_path, duration, num_segments,
            seg_sec, job_id, language_hint,
        )
    # Auto-pace yields a variable count; rebind num_segments for the
    # downstream loops that allocate per-scene buffers.
    num_segments = len(segments)
    raise_if_cancelled(job_id)

    # 4. Generate images — parallelized. Image gen is network-bound
    #    (Gemini / Pollinations) so we can run several in flight at once.
    #    A bounded ThreadPoolExecutor keeps us from hammering the API
    #    too hard while still being ~4x faster than sequential.
    workdir = audio_path.parent / "work"
    workdir.mkdir(exist_ok=True)
    image_paths: list[Path] = [Path() for _ in range(num_segments)]
    failed: list[int] = []
    fallback_used: list[int] = []
    base_seed = int(time.time()) & 0xFFFFFF
    img_done_count = [0]
    img_lock = threading.Lock()

    def _gen_one(idx_seg: tuple[int, dict]) -> None:
        i, seg = idx_seg
        raise_if_cancelled(job_id)
        img_path = workdir / f"img_{i:03d}.png"
        ok, source = _generate_image(
            client, seg["image_prompt"], style_prompt, size_key, img_path,
            seed=base_seed + i,
        )
        with img_lock:
            if not ok or not img_path.exists():
                _make_placeholder(img_path, out_w, out_h, f"scene {i+1}")
                failed.append(i)
            elif source == "pollinations":
                fallback_used.append(i)
            image_paths[i] = img_path
            img_done_count[0] += 1
            done = img_done_count[0]
        # Progress 18 → 78 across image gen. Reported from worker threads;
        # progress() is thread-safe via update_job's $set semantics.
        pct = 18 + int(60 * done / num_segments)
        progress(job_id, pct=pct, message=f"Image {done}/{num_segments}")

    with cf.ThreadPoolExecutor(max_workers=IMAGE_PARALLEL_WORKERS) as ex:
        list(ex.map(_gen_one, enumerate(segments)))

    raise_if_cancelled(job_id)

    if failed:
        print(f"[a2v] {len(failed)}/{num_segments} images fell back to placeholder: {sorted(failed)}")
    if fallback_used:
        print(f"[a2v] {len(fallback_used)}/{num_segments} images used Pollinations fallback")

    # 5. Ken Burns each image — parallelized. ffmpeg is CPU-bound; we
    #    cap concurrency at CLIP_PARALLEL_WORKERS so libx264 doesn't
    #    starve itself thrashing for cores.
    progress(job_id, pct=80, message="Animating scenes…")
    clips_dir = workdir / "clips"
    clips_dir.mkdir(exist_ok=True)
    clip_paths: list[Path] = [Path() for _ in range(num_segments)]
    animation = opts.get("animation_style") or "ken_burns"

    # When the user picks "mixed", every scene gets a different animation,
    # cycling through the 6 motion styles in a fixed order so re-renders
    # of the same audio stay reproducible.
    MIXED_CYCLE = ("ken_burns", "zoom_in", "pan_lr", "pulse", "zoom_out", "pan_rl")

    clip_done_count = [0]
    clip_lock = threading.Lock()

    def _render_one_clip(idx_pair: tuple[int, tuple[Path, dict]]) -> None:
        i, (img, seg) = idx_pair
        raise_if_cancelled(job_id)
        clip_dur = seg["end"] - seg["start"]
        if i == len(segments) - 1:
            clip_dur = max(clip_dur, duration - seg["start"])
        clip_path = clips_dir / f"clip_{i:03d}.mp4"

        if animation == "mixed":
            scene_anim = MIXED_CYCLE[i % len(MIXED_CYCLE)]
        else:
            scene_anim = animation

        try:
            if scene_anim == "none":
                _static_clip(img, clip_dur, out_w, out_h, fps, clip_path,
                             job_id=job_id)
            else:
                _animate_clip(img, clip_dur, i, out_w, out_h, fps, clip_path,
                              style=scene_anim, job_id=job_id)
        except subprocess.CalledProcessError:
            # Cancellation surfaces as CancelledError, not CalledProcessError.
            # Reaching here means a real ffmpeg failure on this clip — fall
            # back to a static clip so the rest of the render still works.
            _static_clip(img, clip_dur, out_w, out_h, fps, clip_path,
                         job_id=job_id)
        with clip_lock:
            clip_paths[i] = clip_path
            clip_done_count[0] += 1
            done = clip_done_count[0]
        # Progress 80 → 90 across clip render
        pct = 80 + int(10 * done / num_segments)
        progress(job_id, pct=pct, message=f"Clip {done}/{num_segments}")

    with cf.ThreadPoolExecutor(max_workers=CLIP_PARALLEL_WORKERS) as ex:
        list(ex.map(_render_one_clip, enumerate(zip(image_paths, segments))))

    # 6. Concat + mux audio
    raise_if_cancelled(job_id)
    progress(job_id, pct=92, message="Assembling final video…")
    out_path = audio_path.parent / f"{audio_path.stem}.mp4"
    _build_video(clip_paths, audio_path, out_path, workdir, job_id=job_id)

    # Final cancel guard — if the user cancelled while we were in a
    # non-cancellable section (e.g. the last ffmpeg mux), don't clobber
    # the cancelled status with "done".
    raise_if_cancelled(job_id)

    # 7. Stamp success. Also persist the per-frame fallback breakdown so
    #    the frontend can surface a "1 of 24 frames used fallback" badge —
    #    silent placeholder swaps used to be invisible to users.
    frame_quality = {
        "totalFrames":      num_segments,
        "geminiFrames":     num_segments - len(fallback_used) - len(failed),
        "pollinationsFrames": len(fallback_used),
        "placeholderFrames": len(failed),
        "pollinationsIndices": fallback_used,
        "placeholderIndices":  failed,
    }
    update_job(
        job_id,
        status="done",
        progress=100,
        message=(
            f"Rendered {duration:.1f}s · {num_segments} scenes · {size_key}"
            + (f" · {len(failed)} placeholder" if failed else "")
            + (f" · {len(fallback_used)} fallback" if fallback_used else "")
        ),
        outputPath=str(out_path),
        outputContentType="video/mp4",
        frameQuality=frame_quality,
    )

    # Best-effort cleanup of the working scratch dir (keep the final mp4)
    try:
        shutil.rmtree(workdir, ignore_errors=True)
    except Exception:
        pass
