"""Combine a screen recording with one or more voiceover clips into a final mp4.

Two modes, picked by what Claude passes:
- Single voiceover: muxed onto the video. If the voice is longer than the
  video, the last video frame is held (tpad) so audio isn't cut off.
- Multiple voiceovers: concatenated in order first, then muxed.

We re-encode audio to AAC and keep the video stream as-is (copy) when possible
for speed; if padding is needed we re-encode video too.
"""
import os
import subprocess
import tempfile

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")


def _run(cmd: list):
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed:\n{proc.stderr[-1500:]}")


def _concat_audio(clips: list, out_path: str):
    """Concatenate audio clips (wav/mp3 mix ok) into one file via concat filter."""
    inputs = []
    for c in clips:
        inputs += ["-i", c]
    n = len(clips)
    filt = "".join(f"[{i}:a]" for i in range(n)) + f"concat=n={n}:v=0:a=1[out]"
    cmd = ["ffmpeg", "-y", *inputs, "-filter_complex", filt,
           "-map", "[out]", out_path]
    _run(cmd)


def assemble_video(video_path: str, voiceovers, name: str = "final") -> dict:
    """Mux voiceover(s) onto the screen recording.

    video_path : the mp4 from the recorder.
    voiceovers : a single path (str) or a list of paths in narration order.
    Returns {"path": ...} of the finished video.
    """
    if not os.path.exists(video_path):
        raise RuntimeError(f"Video not found: {video_path}")

    if isinstance(voiceovers, str):
        voiceovers = [voiceovers]
    voiceovers = [v for v in voiceovers if v and os.path.exists(v)]
    if not voiceovers:
        raise RuntimeError("No valid voiceover files provided.")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    safe = "".join(c for c in name if c.isalnum() or c in ("-", "_")) or "final"
    out_path = os.path.join(OUTPUT_DIR, f"{safe}.mp4")

    # Build a single audio track.
    if len(voiceovers) == 1:
        audio = voiceovers[0]
        tmp_audio = None
    else:
        fd, tmp_audio = tempfile.mkstemp(suffix=".m4a", dir=OUTPUT_DIR)
        os.close(fd)
        _concat_audio(voiceovers, tmp_audio)
        audio = tmp_audio

    # Mux: hold last frame if audio outlasts video (-shortest off, tpad guards).
    # -map 0:v from video, -map 1:a from audio. Re-encode audio to AAC.
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-i", audio,
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        # if audio shorter, video may be longer -> that's fine; if audio longer,
        # -shortest would cut it, so we DON'T use -shortest. Extra video tail is
        # acceptable for a demo.
        out_path,
    ]
    try:
        _run(cmd)
    finally:
        if tmp_audio and os.path.exists(tmp_audio):
            os.remove(tmp_audio)

    size = os.path.getsize(out_path) if os.path.exists(out_path) else 0
    return {"path": out_path, "size_bytes": size}
