"""Screen recording via ffmpeg gdigrab (Windows).

Records the full desktop to an mp4 file. Only ONE recording can be active at a
time (the process handle is held at module level). stop_recording() ends it
gracefully by sending 'q' to ffmpeg's stdin so the mp4 is finalized properly.
"""
import os
import subprocess
import time

# Where finished recordings land. Resolved relative to this file so it works
# regardless of the server's working directory.
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")

_proc = None          # the running ffmpeg subprocess, or None
_current_path = None  # path of the file currently being recorded


def is_recording() -> bool:
    return _proc is not None and _proc.poll() is None


def start_recording(name: str, framerate: int = 24) -> dict:
    """Begin recording the full screen to output/<name>.mp4.

    Returns {"path": ...} on success. Raises if a recording is already running.
    """
    global _proc, _current_path
    if is_recording():
        raise RuntimeError(
            f"A recording is already running ({_current_path}). "
            "Call stop_recording first."
        )

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    # sanitize name -> safe filename
    safe = "".join(c for c in name if c.isalnum() or c in ("-", "_", " ")).strip()
    safe = safe.replace(" ", "_") or "recording"
    path = os.path.join(OUTPUT_DIR, f"{safe}.mp4")

    cmd = [
        "ffmpeg", "-y",
        "-f", "gdigrab",
        "-framerate", str(framerate),
        "-i", "desktop",
        # yuv420p + even dims keeps the mp4 playable everywhere
        "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
        "-pix_fmt", "yuv420p",
        "-c:v", "libx264",
        "-preset", "veryfast",
        path,
    ]
    # stdin=PIPE so we can send 'q' to stop cleanly; capture output for errors.
    _proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    _current_path = path

    # Give ffmpeg a moment; if it died immediately the args were bad.
    time.sleep(1.0)
    if _proc.poll() is not None:
        _proc = None
        _current_path = None
        raise RuntimeError("ffmpeg failed to start recording (check ffmpeg/gdigrab).")

    return {"path": path, "status": "recording"}


def stop_recording() -> dict:
    """Stop the active recording and finalize the mp4. Returns {"path": ...}."""
    global _proc, _current_path
    if not is_recording():
        raise RuntimeError("No recording is currently running.")

    path = _current_path
    try:
        # 'q' tells ffmpeg to quit and flush the moov atom -> valid mp4.
        _proc.stdin.write(b"q")
        _proc.stdin.flush()
    except Exception:
        pass
    try:
        _proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        _proc.terminate()
        _proc.wait(timeout=5)

    _proc = None
    _current_path = None

    size = os.path.getsize(path) if os.path.exists(path) else 0
    return {"path": path, "status": "saved", "size_bytes": size}
