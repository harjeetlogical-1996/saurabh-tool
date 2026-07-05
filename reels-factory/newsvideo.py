"""
LANDSCAPE (16:9, 1920x1080) news-style video builder.

Each segment = a voiceover line + a background (stock b-roll video OR image OR
a generated graphic) + a lower-third headline caption + optional big stat.
Segments are concatenated into one anchor-style news video.

Kept separate from the portrait reel pipeline so nothing there changes.
"""
import json
import subprocess
import textwrap
import urllib.parse
import urllib.request
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

import helpers

W, H, FPS = 1920, 1080, 30
BG = "#0B0F14"
WHITE = "#FFFFFF"
GOLD = "#F5C518"
GREEN = "#16C784"
RED = "#EA3943"
GREY = "#9AA0A6"
BLUE = "#1877F2"

TMP = helpers.TEMP
OUT = helpers.OUTPUT


# --------------------------------------------------------------------------
# Pexels — landscape b-roll video + images
# --------------------------------------------------------------------------
def _pexels_video(query: str, api_key: str, out_path: Path) -> Path:
    url = "https://api.pexels.com/videos/search?" + urllib.parse.urlencode({
        "query": query, "orientation": "landscape", "per_page": 8,
        "size": "medium"})
    req = urllib.request.Request(url, headers={"Authorization": api_key,
        "User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    data = json.loads(urllib.request.urlopen(req, timeout=30).read())
    vids = data.get("videos", [])
    if not vids:
        raise RuntimeError(f"no pexels video for {query}")
    # first video, best landscape file near 1080p
    files = sorted(vids[0]["video_files"],
                   key=lambda f: abs(f.get("height", 0) - 1080))
    link = files[0]["link"]
    dl = urllib.request.Request(link, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(dl, timeout=120) as r, open(out_path, "wb") as f:
        while True:
            b = r.read(1 << 16)
            if not b:
                break
            f.write(b)
    return out_path


def _pexels_image(query: str, api_key: str, out_path: Path) -> Path:
    url = "https://api.pexels.com/v1/search?" + urllib.parse.urlencode({
        "query": query, "orientation": "landscape", "per_page": 5})
    req = urllib.request.Request(url, headers={"Authorization": api_key,
        "User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    data = json.loads(urllib.request.urlopen(req, timeout=30).read())
    photos = data.get("photos", [])
    if not photos:
        raise RuntimeError(f"no pexels image for {query}")
    link = photos[0]["src"].get("landscape") or photos[0]["src"]["large"]
    dl = urllib.request.Request(link, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(dl, timeout=60) as r, open(out_path, "wb") as f:
        f.write(r.read())
    return out_path


# --------------------------------------------------------------------------
# Graphics (matplotlib) — landscape cards
# --------------------------------------------------------------------------
def _fig():
    fig = plt.figure(figsize=(W / 100, H / 100), dpi=100)
    fig.patch.set_facecolor(BG)
    return fig


def graphic_headline(main: str, sub: str, out_path: Path,
                     accent: str = GOLD) -> Path:
    """A full-screen title/headline graphic (used for cold-open & VS cards)."""
    fig = _fig()
    fig.text(0.5, 0.6, textwrap.fill(main, 26), color=WHITE, fontsize=64,
             ha="center", va="center", weight="bold", linespacing=1.1)
    if sub:
        fig.text(0.5, 0.36, textwrap.fill(sub, 40), color=accent, fontsize=34,
                 ha="center", va="center")
    fig.savefig(out_path, facecolor=BG)
    plt.close(fig)
    return out_path


def graphic_stat(big: str, label: str, out_path: Path,
                 accent: str = GREEN) -> Path:
    """A giant number/stat card, e.g. '+10%'  'META'."""
    fig = _fig()
    fig.text(0.5, 0.55, big, color=accent, fontsize=180, ha="center",
             va="center", weight="bold")
    fig.text(0.5, 0.30, label, color=WHITE, fontsize=48, ha="center",
             va="center", weight="bold")
    fig.savefig(out_path, facecolor=BG)
    plt.close(fig)
    return out_path


def graphic_versus(left: str, right_list: list, out_path: Path) -> Path:
    """META  vs  AWS / Azure / Google Cloud style comparison card."""
    fig = _fig()
    fig.text(0.25, 0.6, left, color=BLUE, fontsize=90, ha="center",
             va="center", weight="bold")
    fig.text(0.5, 0.6, "VS", color=GOLD, fontsize=60, ha="center", va="center",
             weight="bold")
    ry = 0.78
    for r in right_list:
        fig.text(0.75, ry, r, color=WHITE, fontsize=40, ha="center",
                 va="center", weight="bold")
        ry -= 0.16
    fig.savefig(out_path, facecolor=BG)
    plt.close(fig)
    return out_path


# --------------------------------------------------------------------------
# Segment assembly
# --------------------------------------------------------------------------
def _lower_third(text: str) -> str:
    """ASS caption chain — lower-third news banner, centered, wrapped."""
    esc = text.replace("\n", " ")
    wrapped = "\\N".join(textwrap.wrap(esc, 46)) or esc
    return wrapped


_MOTION_I = 0  # rotate motion direction per segment so it doesn't feel templated


def build_segment(voice_path: Path, bg_path: Path, is_video: bool,
                  caption: str, out_path: Path, dim: bool = True,
                  motion: bool = True) -> Path:
    """
    Combine one background (video or image) + a voice clip + a lower-third
    caption into a 1920x1080 segment matching the voice length.
    Adds a subtle Ken-Burns zoom/pan (varied per segment) + a quick fade-in
    so clips don't feel static/templated.
    """
    global _MOTION_I
    dur = helpers.get_audio_duration(voice_path)
    ass = out_path.with_suffix(".ass")
    _write_lower_third_ass(caption, dur, ass)
    ass_esc = str(ass).replace("\\", "/").replace(":", "\\:")

    darken = "eq=brightness=-0.10:saturation=1.08," if dim else ""
    total_frames = max(2, int(dur * FPS))

    # rotate through 4 motion styles: zoom-in, zoom-out, pan-L, pan-R
    style = _MOTION_I % 4
    _MOTION_I += 1
    OW, OH = W + 240, H + 240  # oversize so pan has room

    fade = "fade=t=in:st=0:d=0.4,fade=t=out:st=" + f"{max(0.1,dur-0.4):.2f}" + ":d=0.4,"
    if motion and is_video:
        # video already has its own motion -> keep it, just crop a touch tighter
        # for a subtle "framed" push, plus fade in/out transitions. Reliable.
        vf = (f"scale={int(W*1.06)}:{int(H*1.06)}:force_original_aspect_ratio=increase,"
              f"crop={W}:{H},{darken}{fade}subtitles='{ass_esc}'")
    elif motion:  # image -> full Ken Burns zoompan
        base = (f"scale={OW}:{OH}:force_original_aspect_ratio=increase,"
                f"crop={OW}:{OH},")
        if style == 0:
            zp = (f"zoompan=z='min(zoom+0.0006,1.12)':d={total_frames}"
                  f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={FPS}")
        elif style == 1:
            zp = (f"zoompan=z='if(eq(on,0),1.12,max(zoom-0.0006,1.0))':d={total_frames}"
                  f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={FPS}")
        elif style == 2:
            zp = (f"zoompan=z='1.10':d={total_frames}"
                  f":x='(iw-iw/zoom)*(on/{total_frames})':y='ih/2-(ih/zoom/2)'"
                  f":s={W}x{H}:fps={FPS}")
        else:
            zp = (f"zoompan=z='1.10':d={total_frames}"
                  f":x='(iw-iw/zoom)*(1-on/{total_frames})':y='ih/2-(ih/zoom/2)'"
                  f":s={W}x{H}:fps={FPS}")
        vf = f"{base}{zp},{darken}{fade}subtitles='{ass_esc}'"
    else:
        vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,"
              f"crop={W}:{H},{darken}subtitles='{ass_esc}'")

    if is_video:
        cmd = ["ffmpeg", "-y", "-stream_loop", "-1", "-i", str(bg_path),
               "-i", str(voice_path),
               "-t", f"{dur:.2f}", "-vf", vf, "-r", str(FPS),
               "-map", "0:v:0", "-map", "1:a:0",
               "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
               "-c:a", "aac", "-shortest", str(out_path)]
    else:
        cmd = ["ffmpeg", "-y", "-loop", "1", "-i", str(bg_path),
               "-i", str(voice_path),
               "-t", f"{dur:.2f}", "-vf", vf, "-r", str(FPS),
               "-map", "0:v:0", "-map", "1:a:0",
               "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
               "-c:a", "aac", "-shortest", str(out_path)]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return out_path


def _write_lower_third_ass(text: str, dur: float, ass_path: Path):
    body = _lower_third(text)
    header = (
        "[Script Info]\nScriptType: v4.00+\n"
        f"PlayResX: {W}\nPlayResY: {H}\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, "
        "BackColour, Bold, BorderStyle, Outline, Shadow, Alignment, "
        "MarginL, MarginR, MarginV, Encoding\n"
        # BorderStyle 4 = opaque box behind text (news lower-third look)
        "Style: LT,Arial,44,&H00FFFFFF,&H00000000,&HB0000000,-1,4,6,0,2,"
        "120,120,90,1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, "
        "MarginV, Effect, Text\n")
    end = _fmt(dur)
    line = f"Dialogue: 0,0:00:00.00,{end},LT,,0,0,0,,{body}\n"
    ass_path.write_text(header + line, encoding="utf-8")


def _fmt(sec: float) -> str:
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def concat(clips: list, out_path: Path) -> Path:
    lst = out_path.with_suffix(".txt")
    lst.write_text("".join(f"file '{Path(c).as_posix()}'\n" for c in clips))
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0",
                    "-i", str(lst), "-c", "copy", str(out_path)],
                   check=True, capture_output=True, text=True)
    return out_path
