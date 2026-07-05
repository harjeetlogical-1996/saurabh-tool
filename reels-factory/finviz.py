"""
Animated LANDSCAPE (1920x1080) finance graphics for explainer videos.
Every graphic is a moving video clip (count-ups, growing bars, racing lines),
so the screen always has motion. Pairs with newsvideo.build_segment.
"""
import subprocess
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import helpers

W, H, FPS = 1920, 1080, 30
BG = "#0B0F14"
WHITE = "#FFFFFF"
GOLD = "#F5C518"
GREEN = "#16C784"
RED = "#EA3943"
GREY = "#9AA0A6"
BLUE = "#3B82F6"


def _ease(t):
    return 1 - (1 - t) ** 3


def _fig():
    fig = plt.figure(figsize=(W / 100, H / 100), dpi=100)
    fig.patch.set_facecolor(BG)
    return fig


def _clean(prefix):
    d = helpers.TEMP / prefix
    if d.exists():
        for f in d.glob("*.png"):
            f.unlink()
    d.mkdir(exist_ok=True)
    return d


def _render(fdir, out_path):
    subprocess.run([
        "ffmpeg", "-y", "-framerate", str(FPS),
        "-i", str(fdir / "f%04d.png"),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast",
        str(out_path)],
        check=True, capture_output=True, text=True)
    return out_path


def _inr(v):
    """Format rupees as lakh/crore string."""
    if v >= 1e7:
        return f"Rs {v/1e7:.2f} Cr"
    if v >= 1e5:
        return f"Rs {v/1e5:.1f} L"
    return f"Rs {v:,.0f}"


# --------------------------------------------------------------------------
# 1. Count-up hero number (e.g. Rs 10,000 -> Rs 1 Crore)
# --------------------------------------------------------------------------
def countup(target, label, out_path, duration=5.0, sub="", accent=GREEN,
            prefix_rs=True):
    frames = int(duration * FPS)
    fdir = _clean("cu")
    for i in range(frames):
        t = _ease(i / max(1, frames - 1))
        cur = target * t
        fig = _fig()
        txt = _inr(cur) if prefix_rs else f"{cur:,.0f}"
        fig.text(0.5, 0.56, txt, color=accent, fontsize=150, ha="center",
                 va="center", weight="bold")
        fig.text(0.5, 0.34, label, color=WHITE, fontsize=46, ha="center",
                 va="center", weight="bold")
        if sub:
            fig.text(0.5, 0.25, sub, color=GREY, fontsize=32, ha="center",
                     va="center")
        fig.savefig(fdir / f"f{i:04d}.png", facecolor=BG)
        plt.close(fig)
    return _render(fdir, out_path)


# --------------------------------------------------------------------------
# 2. Growing SIP table (years -> invested vs final), rows + bars animate
# --------------------------------------------------------------------------
def sip_table(rows, out_path, duration=7.0, title="Rs 10,000/month @ 12%"):
    """rows: list of (years, invested, final)."""
    frames = int(duration * FPS)
    fdir = _clean("sip")
    n = len(rows)
    maxv = max(r[2] for r in rows)
    for i in range(frames):
        prog = i / max(1, frames - 1)
        fig = _fig()
        fig.text(0.5, 0.90, title, color=GOLD, fontsize=44, ha="center",
                 weight="bold")
        # column headers
        fig.text(0.10, 0.80, "YEARS", color=GREY, fontsize=30, ha="left", weight="bold")
        fig.text(0.30, 0.80, "INVESTED", color=GREY, fontsize=30, ha="left", weight="bold")
        fig.text(0.55, 0.80, "FINAL VALUE", color=GREY, fontsize=30, ha="left", weight="bold")
        top = 0.70
        gap = 0.135
        for k, (yr, inv, fin) in enumerate(rows):
            appear = _ease(max(0, min(1, prog * n - k)))
            if appear <= 0:
                continue
            y = top - k * gap
            fig.text(0.10, y, f"{yr} yr", color=WHITE, fontsize=40, ha="left",
                     weight="bold", alpha=appear)
            fig.text(0.30, y, _inr(inv), color=GREY, fontsize=34, ha="left", alpha=appear)
            fig.text(0.55, y, _inr(fin * appear), color=GREEN, fontsize=40,
                     ha="left", weight="bold", alpha=appear)
            # bar
            bw = 0.32 * (fin / maxv) * appear
            fig.patches.append(plt.Rectangle((0.55, y - 0.045), bw, 0.02,
                transform=fig.transFigure, color=GREEN, alpha=appear * 0.5))
        fig.savefig(fdir / f"f{i:04d}.png", facecolor=BG)
        plt.close(fig)
    return _render(fdir, out_path)


# --------------------------------------------------------------------------
# 3. Inflation shrink (Rs 1 Cr -> Rs 31 L)
# --------------------------------------------------------------------------
def shrink(from_v, to_v, out_path, duration=5.0, label="After 20 yrs @ 6% inflation"):
    frames = int(duration * FPS)
    fdir = _clean("shr")
    for i in range(frames):
        t = _ease(i / max(1, frames - 1))
        cur = from_v + (to_v - from_v) * t
        size = 150 - 60 * t
        col = GREEN if t < 0.5 else RED
        fig = _fig()
        fig.text(0.5, 0.86, "THE INFLATION TRAP", color=RED, fontsize=44,
                 ha="center", weight="bold")
        fig.text(0.5, 0.54, _inr(cur), color=col, fontsize=size, ha="center",
                 va="center", weight="bold")
        fig.text(0.5, 0.30, label, color=GREY, fontsize=34, ha="center", va="center")
        if t > 0.6:
            fig.text(0.5, 0.20, "Feels like Rs 31 Lakh today", color=GOLD,
                     fontsize=32, ha="center", va="center",
                     weight="bold", alpha=_ease((t - 0.6) / 0.4))
        fig.savefig(fdir / f"f{i:04d}.png", facecolor=BG)
        plt.close(fig)
    return _render(fdir, out_path)


# --------------------------------------------------------------------------
# 4. Race chart — flat SIP vs step-up SIP, two lines drawing across
# --------------------------------------------------------------------------
def race(out_path, duration=7.0, years=20):
    import numpy as np
    frames = int(duration * FPS)
    fdir = _clean("race")
    xs = np.arange(0, years + 1)
    # flat 10k @12%; step-up 10% annually
    def grow(step):
        vals, corpus, sip = [], 0.0, 10000.0
        for y in range(years + 1):
            vals.append(corpus)
            for _ in range(12):
                corpus = corpus * (1 + 0.12 / 12) + sip
            if step:
                sip *= 1.10
        return np.array(vals) / 1e7  # crore
    flat = grow(False)
    step = grow(True)
    ymax = max(step.max(), flat.max()) * 1.1
    for i in range(frames):
        prog = i / max(1, frames - 1)
        show = _ease(prog) * years
        fig = _fig()
        ax = fig.add_axes([0.10, 0.14, 0.82, 0.66])
        ax.set_facecolor(BG)
        m = int(show) + 1
        ax.plot(xs[:m], flat[:m], color=GREY, lw=5, label="Flat Rs 10k SIP")
        ax.plot(xs[:m], step[:m], color=GREEN, lw=5, label="10% Step-up SIP")
        if m > 0:
            ax.scatter([xs[m-1]], [flat[m-1]], color=GREY, s=120, zorder=5)
            ax.scatter([xs[m-1]], [step[m-1]], color=GREEN, s=120, zorder=5)
            ax.text(xs[m-1], step[m-1]+ymax*0.03, f"Rs {step[m-1]:.2f} Cr",
                    color=GREEN, fontsize=26, ha="right", weight="bold")
            ax.text(xs[m-1], flat[m-1]-ymax*0.06, f"Rs {flat[m-1]:.2f} Cr",
                    color=GREY, fontsize=24, ha="right", weight="bold")
        ax.set_xlim(0, years); ax.set_ylim(0, ymax)
        ax.set_xlabel("Years", color=WHITE, fontsize=26)
        ax.set_ylabel("Corpus (Rs Crore)", color=WHITE, fontsize=26)
        ax.tick_params(colors=GREY, labelsize=20)
        for s in ax.spines.values():
            s.set_color(GREY)
        ax.legend(loc="upper left", fontsize=24, facecolor=BG,
                  edgecolor=GREY, labelcolor=WHITE)
        fig.text(0.5, 0.90, "STEP-UP SIP vs FLAT SIP", color=GOLD,
                 fontsize=42, ha="center", weight="bold")
        fig.savefig(fdir / f"f{i:04d}.png", facecolor=BG)
        plt.close(fig)
    return _render(fdir, out_path)


# --------------------------------------------------------------------------
# 5. Rules card — numbered rules reveal one by one (with motion)
# --------------------------------------------------------------------------
def rules(title, items, out_path, duration=6.0):
    frames = int(duration * FPS)
    fdir = _clean("rul")
    n = len(items)
    for i in range(frames):
        prog = i / max(1, frames - 1)
        fig = _fig()
        fig.text(0.5, 0.88, title, color=GOLD, fontsize=46, ha="center", weight="bold")
        top = 0.68
        gap = 0.20
        for k, it in enumerate(items):
            appear = _ease(max(0, min(1, prog * n - k)))
            if appear <= 0:
                continue
            y = top - k * gap
            # slide in from left
            x = 0.12 - (1 - appear) * 0.1
            fig.text(x, y, f"{k+1}", color=BG, fontsize=44, ha="center",
                     va="center", weight="bold",
                     bbox=dict(boxstyle="circle", fc=GREEN, ec="none"), alpha=appear)
            fig.text(x + 0.06, y, it, color=WHITE, fontsize=36, ha="left",
                     va="center", alpha=appear)
        fig.savefig(fdir / f"f{i:04d}.png", facecolor=BG)
        plt.close(fig)
    return _render(fdir, out_path)
