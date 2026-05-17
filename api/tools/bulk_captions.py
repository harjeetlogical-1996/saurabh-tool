"""
Bulk Caption Generator — STAGE 1: transcribe only.

Each upload is one finished video. This handler:
  1. Demuxes the audio into a temp mp3.
  2. Probes width/height/duration so the frontend editor can lay out an
     overlay correctly.
  3. Sends the audio to Gemini Flash with a word-level-timestamp schema.
  4. Saves the transcript on the job and stamps the SOURCE video path as
     `outputPath` so /me/jobs/{id}/output?variant=original streams it
     back to the editor.

It does NOT burn captions. That happens in `bulk_captions_render.py`,
triggered explicitly by the user once they've dialed in their style in
the editor screen.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from jobs import (
    progress,
    raise_if_cancelled,
    update_job,
    get_job,
)
from user_keys import get_gemini_key, NoApiKeyError

from . import captions as cap


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


def _has_audio_track(video_path: Path) -> bool:
    try:
        out = subprocess.run(
            [
                _ffprobe(), "-v", "error",
                "-select_streams", "a",
                "-show_entries", "stream=codec_type",
                "-of", "default=noprint_wrappers=1",
                str(video_path),
            ],
            capture_output=True, text=True, check=True,
        )
        return "codec_type=audio" in out.stdout
    except subprocess.CalledProcessError:
        return True


def _video_duration(video_path: Path) -> float:
    try:
        out = subprocess.run(
            [
                _ffprobe(), "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(video_path),
            ],
            capture_output=True, text=True, check=True,
        )
        return float(out.stdout.strip() or "0")
    except (subprocess.CalledProcessError, ValueError):
        return 0.0


def _extract_audio(job_id: str, video_path: Path, out_audio: Path) -> None:
    cap._run_subprocess(job_id, [
        cap._ffmpeg(), "-y",
        "-threads", "1",
        "-i", str(video_path),
        "-vn",
        "-acodec", "libmp3lame", "-ab", "128k",
        "-ar", "44100", "-ac", "1",
        str(out_audio),
    ])


def handle(job_id: str, user_id: str, params: dict) -> None:
    """
    params: {
      "videoPath":     absolute path to uploaded mp4/mov/webm,
      "videoFilename": original filename
    }
    """
    video_path = Path(params["videoPath"])
    if not video_path.exists():
        raise RuntimeError(f"Uploaded video not found at {video_path}")

    raise_if_cancelled(job_id)

    # Probe dims/duration up front. The frontend editor needs these to
    # build the overlay scale and seek bar.
    width, height = cap._video_dims(video_path)
    duration = _video_duration(video_path)

    workdir = video_path.parent / "work"
    workdir.mkdir(exist_ok=True)
    audio_path = workdir / "audio.mp3"

    progress(job_id, pct=4, message="Reading video…")
    if not _has_audio_track(video_path):
        raise RuntimeError(
            "This video has no audio track. Captions need spoken audio.",
        )
    _extract_audio(job_id, video_path, audio_path)
    raise_if_cancelled(job_id)

    # Skip Gemini if a previous run on the same job already cached the
    # transcript. Bulk submits give each video a fresh job so cache miss
    # on first run; only retries hit this path.
    job_doc = get_job(job_id, user_id=user_id) or {}
    cached_words = job_doc.get("transcriptWords")
    if cached_words and isinstance(cached_words, list) and cached_words:
        words = cap._sanitize_words(cached_words)
        progress(
            job_id, pct=80,
            message=f"Using cached transcript ({len(words)} words)…",
        )
        if words and words != cached_words:
            update_job(job_id, transcriptWords=words)
    else:
        try:
            api_key = get_gemini_key(user_id, user_plan=params.get("userPlan") or "")
        except NoApiKeyError as e:
            raise RuntimeError(str(e))
        from google import genai
        client = genai.Client(api_key=api_key)
        # Chunked + parallel for long audio — caps wall-time to roughly
        # max-chunk-time regardless of total video length.
        words = cap.transcribe_words(
            client, audio_path,
            job_id=job_id, progress_lo=15, progress_hi=85,
            language=params.get("language"),
        )
        if not words:
            raise RuntimeError(
                "Transcription returned no words. Is there speech in the audio?",
            )

    raise_if_cancelled(job_id)

    # Best-effort cleanup of the demuxed audio — we have the transcript now.
    try:
        audio_path.unlink()
    except Exception:
        pass

    # Stamp the source video as outputPath so /output streams it back to
    # the editor. videoWidth/Height/Duration are used by the overlay.
    update_job(
        job_id,
        status="done",
        progress=100,
        message=f"Transcribed {len(words)} words. Open the editor to style captions.",
        transcriptWords=words,
        videoWidth=width,
        videoHeight=height,
        videoDuration=duration,
        outputPath=str(video_path),
        outputContentType="video/mp4",
    )
