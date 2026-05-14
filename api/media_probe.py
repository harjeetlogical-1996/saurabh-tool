"""
Small ffprobe helper shared by handlers and the submit endpoint.

We need to know audio duration *at submit time* to gate against the
user's remaining minutes — we can't rely on the handler computing it
because by then the upload has already been accepted.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


def _ffprobe_path() -> str:
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


def audio_duration_seconds(path: Path) -> float:
    """Return audio duration in seconds. 0.0 if unparseable."""
    try:
        out = subprocess.run(
            [
                _ffprobe_path(), "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True, text=True, check=True, timeout=30,
        )
        return float(out.stdout.strip())
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError):
        return 0.0
