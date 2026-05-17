"""
Voice Pair tool. Pairs one media file (image or video) with one voice file
and renders a single mp4 whose length matches the voice's duration.

Behavior:
  - Image + voice  → static or Ken Burns slideshow for the voice duration
  - Video + voice  → video loops until voice ends; final mp4 carries the
                     voice as its audio track (source video audio dropped)

Output dimensions auto-detect from the source media:
  - Image: use the image's native dimensions, rounded to even pixels
  - Video: use the video's existing width/height

Free, no per-call cost. Pipeline is pure ffmpeg.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from jobs import (
    CancelledError,
    progress,
    raise_if_cancelled,
    register_proc,
    unregister_proc,
    update_job,
    get_job,
)
from media_probe import audio_duration_seconds


# ---- ffmpeg helpers (shared pattern with captions.py) -----------------

def _ffmpeg() -> str:
    """Resolve the ffmpeg binary; mirrors the lookup used elsewhere."""
    candidates = [
        os.environ.get("FFMPEG_BIN"),
        shutil.which("ffmpeg"),
        r"C:\Users\Admin\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1-full_build\bin\ffmpeg.exe",
    ]
    for c in candidates:
        if c and Path(c).exists():
            return c
    return "ffmpeg"


def _ffprobe() -> str:
    ff = _ffmpeg()
    pp = Path(ff).with_name("ffprobe.exe") if os.name == "nt" else Path(ff).with_name("ffprobe")
    if pp.exists():
        return str(pp)
    return "ffprobe"


def _video_dims(path: Path) -> tuple[int, int]:
    """Return (width, height) of the first video stream. Falls back to
    (1080, 1920) if probing fails so render still produces something."""
    try:
        out = subprocess.run(
            [_ffprobe(), "-v", "error",
             "-select_streams", "v:0",
             "-show_entries", "stream=width,height",
             "-of", "csv=p=0:s=x",
             str(path)],
            capture_output=True, text=True, check=True,
        )
        w_s, _, h_s = out.stdout.strip().partition("x")
        return int(w_s), int(h_s)
    except Exception:
        return 1080, 1920


def _image_dims(path: Path) -> tuple[int, int]:
    """Return (width, height) of an image. Even-aligned for x264."""
    try:
        from PIL import Image
        with Image.open(path) as img:
            w, h = img.size
            # x264 needs even pixel dims.
            return (w - (w % 2), h - (h % 2))
    except Exception:
        return 1080, 1920


def _is_video(path: Path) -> bool:
    """Cheap probe: file extension suffices for a UI-controlled upload."""
    return path.suffix.lower() in {".mp4", ".mov", ".webm", ".m4v", ".mkv", ".avi"}


# Maximum output dimension. 4K source video produces a 4K mp4 by default,
# which is slow to decode in the browser preview (multi-second hang before
# first frame). 1080 on the long edge keeps file size and decode load
# sane while still looking sharp on phones / desktops.
MAX_OUTPUT_LONG_EDGE = 1920


def _cap_dims(w: int, h: int, max_long_edge: int = MAX_OUTPUT_LONG_EDGE) -> tuple[int, int]:
    """Scale (w, h) down so the LONG edge is at most max_long_edge,
    preserving aspect. Returns even-pixel dimensions (x264 requires
    even numbers on both axes)."""
    long_edge = max(w, h)
    if long_edge <= max_long_edge:
        return (w - (w % 2), h - (h % 2))
    scale = max_long_edge / long_edge
    nw = int(round(w * scale))
    nh = int(round(h * scale))
    return (nw - (nw % 2), nh - (nh % 2))


_ENCODER_CACHE: Optional[list[str]] = None


def _probe_encoder(name: str) -> bool:
    """Actually try to open the encoder against a 1-frame test source.
    ffmpeg lists encoders that may still fail at runtime (e.g. NVENC on
    a machine without nvcuda.dll, or QSV without Media SDK). The only
    reliable check is to run a tiny encode and see if it returns 0.
    """
    try:
        r = subprocess.run(
            [_ffmpeg(), "-hide_banner", "-loglevel", "error",
             "-f", "lavfi", "-i", "color=c=black:s=320x240:d=0.1:r=1",
             "-c:v", name, "-frames:v", "1",
             "-f", "null", "-"],
            capture_output=True, text=True, timeout=10,
        )
        return r.returncode == 0
    except Exception:
        return False


def _fast_video_encoder_args() -> list[str]:
    """Pick the fastest h264 encoder that ACTUALLY works on this machine.

    Probes each hardware encoder by running a tiny test encode — listing
    in `-encoders` is not enough (NVENC will list even without an NVIDIA
    GPU on the host). Falls back to libx264 ultrafast on software-only.
    """
    global _ENCODER_CACHE
    if _ENCODER_CACHE is not None:
        return _ENCODER_CACHE

    if _probe_encoder("h264_nvenc"):
        # NVENC: -preset p1 is the fastest preset (quality p7 is best).
        _ENCODER_CACHE = ["-c:v", "h264_nvenc", "-preset", "p1", "-cq", "23"]
    elif _probe_encoder("h264_qsv"):
        # Intel QSV
        _ENCODER_CACHE = ["-c:v", "h264_qsv", "-preset", "veryfast", "-global_quality", "23"]
    elif _probe_encoder("h264_amf"):
        # AMD AMF: -quality speed (vs balanced/quality)
        _ENCODER_CACHE = ["-c:v", "h264_amf", "-quality", "speed", "-qp_i", "23", "-qp_p", "25"]
    else:
        # Software fallback — ultrafast is ~3x faster than `faster` for
        # ~20% bigger output, totally fine for short utility videos.
        _ENCODER_CACHE = ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "23"]
    print(f"[voice_pair] using video encoder: {_ENCODER_CACHE[1]}")
    return _ENCODER_CACHE


def _ken_burns_filter(width: int, height: int, frames: int, index: int) -> str:
    """Mixed-direction medium-speed pan-and-zoom. Uses `on/{frames}` so
    the motion spans the entire clip regardless of duration. With
    `-loop 1` + `-framerate 1`, `dn` is unreliable as a progress
    counter, so we divide by the constant `frames` passed from Python.

    Z=1.6 → 60% zoom across the clip. Pre-scale headroom is 2.5x so
    the inner crop never sees source pixels at <1.0 sampling.

    8 variations cycle by index — single-image clips look interesting
    even alone, and a slideshow gets every direction without repeats.
    """
    # End zoom level. 1.18 was nearly static; 1.35 was OK; 1.6 reads
    # clearly as a moving camera. Visible on phones AND desktops.
    Z = 1.6
    # Strong horizontal/vertical drift coefficient (fraction of the
    # available crop window we sweep across).
    D = 0.6
    m = index % 8

    if m == 0:
        # Zoom-in, centered
        z_expr = f"1.0+{Z - 1.0:.4f}*on/{frames}"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"
    elif m == 1:
        # Zoom-in with rightward drift (camera dolly right)
        z_expr = f"1.0+{Z - 1.0:.4f}*on/{frames}"
        x_expr = f"(iw-iw/zoom)*(0.5-{D / 2}+{D}*on/{frames})"
        y_expr = "ih/2-(ih/zoom/2)"
    elif m == 2:
        # Zoom-out, centered (start tight, ease to wide)
        z_expr = f"{Z:.4f}-{Z - 1.0:.4f}*on/{frames}"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"
    elif m == 3:
        # Zoom-in with leftward drift
        z_expr = f"1.0+{Z - 1.0:.4f}*on/{frames}"
        x_expr = f"(iw-iw/zoom)*(0.5+{D / 2}-{D}*on/{frames})"
        y_expr = "ih/2-(ih/zoom/2)"
    elif m == 4:
        # Diagonal pan top-left → bottom-right + zoom in
        z_expr = f"1.0+{Z - 1.0:.4f}*on/{frames}"
        x_expr = f"(iw-iw/zoom)*({D / 2}*on/{frames})"
        y_expr = f"(ih-ih/zoom)*({D / 2}*on/{frames})"
    elif m == 5:
        # Zoom-in with downward drift (tilt down)
        z_expr = f"1.0+{Z - 1.0:.4f}*on/{frames}"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = f"(ih-ih/zoom)*(0.5-{D / 2}+{D}*on/{frames})"
    elif m == 6:
        # Diagonal pan bottom-right → top-left + zoom in
        z_expr = f"1.0+{Z - 1.0:.4f}*on/{frames}"
        x_expr = f"(iw-iw/zoom)*(1.0-{D / 2}*on/{frames})"
        y_expr = f"(ih-ih/zoom)*(1.0-{D / 2}*on/{frames})"
    else:
        # Zoom-in with upward drift (tilt up)
        z_expr = f"1.0+{Z - 1.0:.4f}*on/{frames}"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = f"(ih-ih/zoom)*(0.5+{D / 2}-{D}*on/{frames})"

    # Pre-scale at 2.5x so the inner crop window has the resolution
    # headroom for Z=1.6 zoom without sampling artifacts.
    return (
        f"scale=iw*2.5:ih*2.5,"
        f"zoompan=z='{z_expr}':x='{x_expr}':y='{y_expr}':"
        f"d={frames}:s={width}x{height}:fps=30,"
        f"format=yuv420p"
    )


def _run_ffmpeg_streamed(job_id: str, cmd: list[str], total_sec: float, lo: int, hi: int) -> None:
    """Run ffmpeg, parse `time=HH:MM:SS.xx` from stderr and update progress."""
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        bufsize=1,
        universal_newlines=True,
    )
    register_proc(job_id, proc)
    try:
        last_pct = lo
        for line in proc.stderr or []:
            raise_if_cancelled(job_id)
            # ffmpeg writes lines like `frame= 234 fps=... time=00:00:08.45 ...`
            if "time=" in line and total_sec > 0:
                try:
                    t = line.split("time=", 1)[1].split(" ", 1)[0]
                    h, m, s = t.split(":")
                    secs = int(h) * 3600 + int(m) * 60 + float(s)
                    pct = lo + int((hi - lo) * min(1.0, secs / total_sec))
                    if pct > last_pct:
                        progress(job_id, pct=pct)
                        last_pct = pct
                except Exception:
                    pass
        rc = proc.wait()
        if rc != 0:
            raise subprocess.CalledProcessError(rc, cmd)
    finally:
        unregister_proc(job_id, proc)


# ---- Core render functions --------------------------------------------

def _render_image_pair(
    job_id: str,
    image_path: Path,
    voice_path: Path,
    out_path: Path,
    voice_duration: float,
    animation: str,
    index: int,
) -> None:
    """Image + voice → mp4. `animation` is 'static' or 'ken_burns'."""
    w, h = _cap_dims(*_image_dims(image_path))
    fps = 30
    frames = max(1, int(round(voice_duration * fps)))

    if animation == "ken_burns":
        # Mirrors audio_to_video.py: -loop 1 -framerate 1 keeps the
        # input "single-frame-per-second" so zoompan's `on` counter
        # advances cleanly through the whole clip. -frames:v {frames}
        # caps the video stream at the exact output frame count.
        # The audio input then provides the soundtrack; we map both.
        vf = _ken_burns_filter(w, h, frames, index)
        cmd = [
            _ffmpeg(), "-y",
            "-loop", "1", "-framerate", "1", "-i", str(image_path),
            "-i", str(voice_path),
            "-map", "0:v:0", "-map", "1:a:0",
            "-vf", vf,
            "-frames:v", str(frames),
            "-r", str(fps),
            *_fast_video_encoder_args(), "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k",
            "-shortest",
            "-movflags", "+faststart",
            str(out_path),
        ]
    else:
        # Static: scale + pad to even pixel dims at the target fps.
        vf = (
            f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black,"
            f"fps={fps},format=yuv420p"
        )
        cmd = [
            _ffmpeg(), "-y",
            "-loop", "1", "-framerate", str(fps), "-i", str(image_path),
            "-i", str(voice_path),
            "-t", f"{voice_duration:.3f}",
            "-vf", vf,
            *_fast_video_encoder_args(), "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k",
            "-shortest",
            "-movflags", "+faststart",
            str(out_path),
        ]
    _run_ffmpeg_streamed(job_id, cmd, voice_duration, lo=10, hi=95)


def _render_video_pair(
    job_id: str,
    video_path: Path,
    voice_path: Path,
    out_path: Path,
    voice_duration: float,
) -> None:
    """Video + voice → mp4 where the video loops to match voice length.
    Source video's own audio track is dropped — only the supplied voice
    is kept on the output."""
    w, h = _cap_dims(*_video_dims(video_path))

    # stream_loop=-1 + -t voice_duration loops the video forever and then
    # ffmpeg cuts at the explicit -t. -map ensures the OUTPUT audio is
    # the voice, not the source video's audio.
    cmd = [
        _ffmpeg(), "-y",
        "-stream_loop", "-1", "-i", str(video_path),
        "-i", str(voice_path),
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-t", f"{voice_duration:.3f}",
        # Re-encode video so the loop boundary is clean; copy audio.
        *_fast_video_encoder_args(), "-pix_fmt", "yuv420p",
        "-vf", f"scale={w}:{h}",
        "-c:a", "aac", "-b:a", "128k",
        "-shortest",
        "-movflags", "+faststart",
        str(out_path),
    ]
    _run_ffmpeg_streamed(job_id, cmd, voice_duration, lo=10, hi=95)


def _render_slideshow_pair(
    job_id: str,
    media_paths: list[Path],
    voice_path: Path,
    out_path: Path,
    voice_duration: float,
) -> None:
    """Slideshow mode: N images (or videos) + 1 voice → 1 mp4. Each item
    occupies an EQUAL share of the voice duration (voice_dur / N). Items
    play back-to-back with hard cuts (no crossfade) so the render is one
    concat pass and stays fast.

    Mixed media (image+video in the same folder) is supported — each item
    is normalised to the same size + fps in a per-item filter chain
    before being fed to the concat demuxer.
    """
    n = len(media_paths)
    if n == 0:
        raise RuntimeError("Slideshow has no media files.")

    # Pick output dimensions from the FIRST item so the slideshow has a
    # consistent canvas. All subsequent items get scaled+padded to fit.
    # Cap to 1080p long edge — 4K source decodes painfully in browser.
    first = media_paths[0]
    if _is_video(first):
        out_w, out_h = _cap_dims(*_video_dims(first))
    else:
        out_w, out_h = _cap_dims(*_image_dims(first))
    fps = 30
    per_clip = max(0.2, voice_duration / n)  # don't go below 200ms

    # Per-clip frame count for image Ken Burns (the `on` denominator).
    per_clip_frames = max(2, int(round(per_clip * fps)))

    # Build one filter chain per input: image → Ken Burns; video →
    # scale+pad+trim. Then concat them all in a single filtergraph.
    inputs: list[str] = []  # ffmpeg input args
    fc_parts: list[str] = []  # filter_complex segments
    concat_inputs: list[str] = []  # streams to feed into concat
    for i, p in enumerate(media_paths):
        if _is_video(p):
            # Loop the video in case it's shorter than per_clip — clean trim.
            inputs += ["-stream_loop", "-1", "-i", str(p)]
            fc_parts.append(
                f"[{i}:v]scale={out_w}:{out_h}:force_original_aspect_ratio=decrease,"
                f"pad={out_w}:{out_h}:(ow-iw)/2:(oh-ih)/2:black,"
                f"setsar=1,fps={fps},trim=duration={per_clip:.3f},setpts=PTS-STARTPTS[v{i}]"
            )
        else:
            # Still image with Ken Burns. -loop 1 + -framerate 1 keeps
            # ffmpeg from drowning zoompan in duplicate input frames;
            # zoompan generates exactly per_clip_frames output frames.
            # The Ken Burns expression varies per index so consecutive
            # slides don't pan the same way.
            inputs += ["-loop", "1", "-framerate", "1", "-i", str(p)]
            kb_vf = _ken_burns_filter(out_w, out_h, per_clip_frames, i)
            fc_parts.append(
                f"[{i}:v]{kb_vf},"
                f"trim=duration={per_clip:.3f},setpts=PTS-STARTPTS[v{i}]"
            )
        concat_inputs.append(f"[v{i}]")

    # Concat all per-item video streams; audio comes from the voice input.
    fc_parts.append(
        "".join(concat_inputs) + f"concat=n={n}:v=1:a=0[vout]"
    )
    filter_complex = ";".join(fc_parts)

    # The voice is the LAST input — easy to reference as [{n}:a:0].
    cmd = [
        _ffmpeg(), "-y",
        *inputs,
        "-i", str(voice_path),
        "-filter_complex", filter_complex,
        "-map", "[vout]",
        "-map", f"{n}:a:0",
        "-t", f"{voice_duration:.3f}",
        *_fast_video_encoder_args(), "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        "-shortest",
        "-movflags", "+faststart",
        str(out_path),
    ]
    _run_ffmpeg_streamed(job_id, cmd, voice_duration, lo=10, hi=95)


# ---- Public handler ---------------------------------------------------

def handle(job_id: str, user_id: str, params: dict) -> None:
    """Job-queue entrypoint. Routes to per-file or slideshow renderer
    based on `mode`:
      - "single" (default): one media file + one voice
      - "slideshow":         many media files + one voice, equal split
    """
    mode = str(params.get("mode") or "single").lower()
    voice_path = Path(params.get("voicePath") or "")
    if not voice_path.exists():
        raise RuntimeError(f"Voice file missing: {voice_path}")

    progress(job_id, pct=5, message="Reading voice duration…")
    voice_dur = audio_duration_seconds(voice_path)
    if voice_dur <= 0.05:
        raise RuntimeError("Voice file has no audible duration.")
    raise_if_cancelled(job_id)

    if mode == "slideshow":
        # Slideshow: multiple media files, one voice. Output sits next
        # to the FIRST media file with a deterministic suffix.
        media_paths = [Path(p) for p in (params.get("mediaPaths") or [])]
        for mp in media_paths:
            if not mp.exists():
                raise RuntimeError(f"Media file missing: {mp}")
        if not media_paths:
            raise RuntimeError("Slideshow has no media files.")
        out_path = media_paths[0].parent / f"slideshow.voicepair.mp4"
        progress(
            job_id, pct=10,
            message=f"Rendering slideshow ({len(media_paths)} items, {voice_dur:.1f}s)…",
        )
        try:
            _render_slideshow_pair(job_id, media_paths, voice_path, out_path, voice_dur)
        except CancelledError:
            try:
                out_path.unlink()
            except OSError:
                pass
            raise
    else:
        media_path = Path(params.get("mediaPath") or "")
        animation = str(params.get("animation") or "static")
        pair_index = int(params.get("pairIndex") or 0)
        if not media_path.exists():
            raise RuntimeError(f"Media file missing: {media_path}")

        out_path = media_path.parent / f"{media_path.stem}.voicepair.mp4"
        is_video_src = _is_video(media_path)
        progress(
            job_id, pct=10,
            message=f"Rendering {'video' if is_video_src else 'image'} + voice ({voice_dur:.1f}s)…",
        )
        try:
            if is_video_src:
                _render_video_pair(job_id, media_path, voice_path, out_path, voice_dur)
            else:
                _render_image_pair(
                    job_id, media_path, voice_path, out_path,
                    voice_dur, animation, pair_index,
                )
        except CancelledError:
            try:
                out_path.unlink()
            except OSError:
                pass
            raise

    update_job(
        job_id,
        status="done",
        progress=100,
        message=f"Rendered {voice_dur:.1f}s clip.",
        outputPath=str(out_path),
        outputContentType="video/mp4",
        videoDuration=voice_dur,
    )
