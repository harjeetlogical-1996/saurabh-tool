"""
Render a 3-second test segment of one parent video with every caption
style. Drops a side-by-side reference frame per style under
C:/Users/Admin/Desktop/caption_compare/<style>.png so we can eyeball
demo-tile vs final-render parity in one folder.

Usage:
    python scripts/test_all_caption_styles.py <parent_job_id>
"""

from __future__ import annotations

import os
import sys
import subprocess
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from pymongo import MongoClient
from bson import ObjectId
from tools.captions import (
    STYLE_PRESETS, _group_words_into_lines, _write_ass, _video_dims, _ffmpeg,
)


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: test_all_caption_styles.py <parent_job_id>")
        return 1
    parent_id = sys.argv[1]
    out_dir = Path("C:/Users/Admin/Desktop/caption_compare")
    out_dir.mkdir(parents=True, exist_ok=True)

    db = MongoClient(os.environ["MONGODB_URI"])[os.environ.get("MONGODB_DB", "saurabh")]
    parent = db.tool_jobs.find_one({"_id": ObjectId(parent_id)})
    if not parent:
        print(f"parent job {parent_id} not found")
        return 1
    video_path = Path(parent["params"]["videoPath"])
    if not video_path.exists():
        print(f"video missing: {video_path}")
        return 1

    words = parent.get("transcriptWords") or []
    if not words:
        print("parent has no cached transcript")
        return 1
    # Trim transcript to first 3 seconds so renders are fast.
    words = [w for w in words if float(w["end"]) <= 3.0]
    if len(words) < 2:
        # Fallback: just take first 6 words and remap timestamps to 0-3s
        all_words = parent.get("transcriptWords") or []
        words = []
        for i, w in enumerate(all_words[:6]):
            words.append({"word": w["word"], "start": i * 0.5, "end": (i + 1) * 0.5})
    print(f"using {len(words)} words for test transcript")

    width, height = _video_dims(video_path)
    print(f"video: {width}x{height}")

    # Cut a 3-second clip to keep iteration fast.
    clip_path = out_dir / "clip.mp4"
    subprocess.run(
        [_ffmpeg(), "-y", "-i", str(video_path), "-t", "3", "-c", "copy", str(clip_path)],
        check=True, capture_output=True,
    )

    workdir = Path(tempfile.mkdtemp(prefix="capstyle_"))

    for style in STYLE_PRESETS.keys():
        print(f"--- {style} ---")
        lines = _group_words_into_lines(words, 4)
        ass_path = workdir / f"{style}.ass"
        _write_ass(
            lines,
            ass_path,
            width=width, height=height,
            style=style, position="bottom",
            uppercase_override=False,
        )

        out_mp4 = out_dir / f"{style}.mp4"
        out_png = out_dir / f"{style}.png"

        # Burn captions on the 3-sec clip.
        fonts_dir = (Path(__file__).resolve().parent.parent / "assets" / "fonts").as_posix()
        ass_filter_path = ass_path.resolve().as_posix().replace(":", r"\:")
        fonts_dir_escaped = fonts_dir.replace(":", r"\:")
        vf = f"ass='{ass_filter_path}':fontsdir='{fonts_dir_escaped}'"
        try:
            subprocess.run(
                [_ffmpeg(), "-y", "-i", str(clip_path), "-vf", vf,
                 "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
                 "-pix_fmt", "yuv420p", "-an", str(out_mp4)],
                check=True, capture_output=True, text=True,
            )
            # Extract one frame at 1.5 seconds (mid-clip)
            subprocess.run(
                [_ffmpeg(), "-y", "-ss", "1.5", "-i", str(out_mp4),
                 "-vframes", "1", "-q:v", "2", str(out_png)],
                check=True, capture_output=True,
            )
            print(f"  done {out_png}")
        except subprocess.CalledProcessError as e:
            print(f"  FAILED: {e.stderr[:300] if e.stderr else e}")

    print(f"\nAll done. Open {out_dir} to compare.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
