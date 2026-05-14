"""
Bulk Caption Generator — STAGE 2: render captions onto a transcribed video.

Triggered by the user from the editor screen once they've dialed in
style/position/X/Y/words-per-line on top of their actual video. The
parent transcribe job already has:
  - the source mp4 sitting on disk at outputPath
  - the word-level transcript in transcriptWords
  - the video dimensions in videoWidth / videoHeight

This handler reads those, writes ASS, runs ffmpeg, and stamps the parent
job's `activeCaptionsJobId` so /output?variant=active streams the
captioned mp4.
"""

from __future__ import annotations

from pathlib import Path

from jobs import (
    progress,
    raise_if_cancelled,
    update_job,
    get_job,
)

from . import captions as cap


def handle(job_id: str, user_id: str, params: dict) -> None:
    """
    params: {
      "parentJobId": <transcribe job id>,
      "options": {
        "style":        one of cap.STYLE_PRESETS,
        "position":     "top"|"middle"|"bottom",
        "wordsPerLine": int,
        "uppercase":    bool (optional),
        "offsetX":      int px (optional),
        "offsetY":      int px (optional),
      }
    }
    """
    parent_id = params.get("parentJobId")
    if not parent_id:
        raise RuntimeError("parentJobId is required.")

    parent = get_job(parent_id, user_id=user_id)
    if not parent:
        raise RuntimeError("Parent transcribe job not found.")
    if parent.get("status") != "done":
        raise RuntimeError("Parent transcribe job isn't ready yet.")

    source = parent.get("outputPath")
    if not source or not Path(source).exists():
        raise RuntimeError("Source video is missing on disk.")
    source = Path(source)

    words = parent.get("transcriptWords")
    if not isinstance(words, list) or not words:
        raise RuntimeError("Parent job has no transcript.")

    opts = params.get("options") or {}
    style = opts.get("style") or "bold"
    if style not in cap.STYLE_PRESETS:
        style = "bold"
    position = opts.get("position") or "bottom"
    if position not in cap.POSITIONS:
        position = "bottom"
    words_per_line = max(1, min(8, int(opts.get("wordsPerLine") or 2)))
    uppercase = bool(opts.get("uppercase", False))
    pos_x_frac = opts.get("posXFrac")
    pos_y_frac = opts.get("posYFrac")
    pos_x_frac = float(pos_x_frac) if pos_x_frac is not None else None
    pos_y_frac = float(pos_y_frac) if pos_y_frac is not None else None
    # Customize-tab overrides — each optional, falls back to preset.
    primary_color = opts.get("primaryColor") or None
    outline_color = opts.get("outlineColor") or None
    bg_color = opts.get("bgColor") or None
    font_family = opts.get("fontFamily") or None

    def _safe_int(v, lo, hi):
        if v is None:
            return None
        try:
            return max(lo, min(hi, int(v)))
        except (TypeError, ValueError):
            return None

    outline_width_override = _safe_int(opts.get("outlineWidth"), 0, 20)
    bg_alpha = _safe_int(opts.get("bgAlpha"), 0, 255)
    font_size_override = _safe_int(opts.get("fontSize"), 12, 200)
    shadow_override = _safe_int(opts.get("shadow"), 0, 20)

    width = int(parent.get("videoWidth") or 0)
    height = int(parent.get("videoHeight") or 0)
    if not width or not height:
        width, height = cap._video_dims(source)

    progress(job_id, pct=10, message="Building captions…")
    lines = cap._group_words_into_lines(words, words_per_line)
    if not lines:
        raise RuntimeError("Couldn't group transcript into caption lines.")

    workdir = source.parent / "work"
    workdir.mkdir(exist_ok=True)
    # Use the job id in the filename so multiple renders of the same
    # parent video don't collide.
    ass_path = workdir / f"{source.stem}.{job_id}.ass"
    srt_path = workdir / f"{source.stem}.{job_id}.srt"
    cap._write_ass(
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
    cap._write_srt(lines, srt_path)
    raise_if_cancelled(job_id)

    progress(job_id, pct=35, message="Burning captions into video…")
    out_path = source.parent / f"{source.stem}.{job_id}.captioned.mp4"

    fonts_dir = cap.FONT_PATH.parent.resolve().as_posix()
    ass_filter_path = ass_path.resolve().as_posix().replace(":", "\\:")
    fonts_dir_escaped = fonts_dir.replace(":", "\\:")
    vf = f"ass='{ass_filter_path}':fontsdir='{fonts_dir_escaped}'"

    # Probe source duration so the streamed ffmpeg progress means
    # something. Falls back to 0 (no progress updates during encode)
    # only if ffprobe fails — the encode still works.
    burn_total_sec = 0.0
    try:
        from media_probe import audio_duration_seconds
        burn_total_sec = audio_duration_seconds(source)
    except Exception:
        pass

    cap._run_ffmpeg_with_progress(
        job_id,
        [
            cap._ffmpeg(), "-y",
            "-i", str(source),
            "-vf", vf,
            "-c:v", "libx264", "-preset", "faster", "-crf", "22",
            "-c:a", "copy",
            "-movflags", "+faststart",
            str(out_path),
        ],
        total_duration_sec=burn_total_sec,
        progress_lo=35,
        progress_hi=95,
        message_template="Burning captions ({pct}%)",
    )
    raise_if_cancelled(job_id)

    update_job(
        job_id,
        status="done",
        progress=100,
        message=f"Burned {len(lines)} caption lines · {style}",
        outputPath=str(out_path),
        outputContentType="video/mp4",
        srtPath=str(srt_path),
    )

    # Mark this render as the active variant on the parent transcribe job
    # so /output?variant=active on the parent serves the captioned mp4.
    update_job(
        str(parent_id),
        activeCaptionsJobId=job_id,
        activeCaptionsStyle=style,
    )

    try:
        ass_path.unlink()
    except Exception:
        pass
