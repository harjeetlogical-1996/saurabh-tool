"""
Finance visuals for Reels Factory.

Generates ORIGINAL animated data visuals (1080x1920) using matplotlib +
FFmpeg — number counters, bar charts, line graphs, stat cards. No stock,
no face: fully your own data-visual, perfect for the finance niche.

Each function returns a path to a silent .mp4 you can use as the reel's
background (pass it where a stock clip would go).
"""
import subprocess
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches
import numpy as np

BASE = Path(__file__).parent
TEMP = BASE / "temp"
TEMP.mkdir(exist_ok=True)

# Finance palette: dark bg, green growth, gold accents
BG = "#0b1220"
GREEN = "#16c784"
RED = "#ea3943"
GOLD = "#f5d400"
WHITE = "#f5f7fa"
GREY = "#8b97a7"

W, H, FPS = 1080, 1920, 30


def _fig():
    fig = plt.figure(figsize=(W / 100, H / 100), dpi=100)
    fig.patch.set_facecolor(BG)
    return fig


def _frames_to_video(frame_dir: Path, out_path: Path, fps: int = FPS) -> Path:
    subprocess.run([
        "ffmpeg", "-y", "-framerate", str(fps),
        "-i", str(frame_dir / "f%04d.png"),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(fps),
        str(out_path),
    ], check=True, capture_output=True, text=True)
    return out_path


def _clean_dir(name: str) -> Path:
    d = TEMP / name
    if d.exists():
        for f in d.glob("*.png"):
            f.unlink()
    d.mkdir(exist_ok=True)
    return d


def _ease(t):
    """ease-out cubic for smooth animation"""
    return 1 - (1 - t) ** 3


# ---------------------------------------------------------------------------
# 1. NUMBER COUNTER  ($1,000 -> $1,250)
# ---------------------------------------------------------------------------
def number_counter(start: float, end: float, out_path: Path,
                   duration: float = 4.0, prefix: str = "$", suffix: str = "",
                   label: str = "") -> Path:
    frames = int(duration * FPS)
    fdir = _clean_dir("num")
    for i in range(frames):
        t = _ease(i / max(1, frames - 1))
        val = start + (end - start) * t
        fig = _fig()
        ax = fig.add_axes([0, 0, 1, 1]); ax.axis("off")
        if label:
            ax.text(0.5, 0.62, label, color=GREY, fontsize=42, ha="center",
                    va="center", weight="bold")
        txt = f"{prefix}{val:,.0f}{suffix}"
        color = GREEN if end >= start else RED
        ax.text(0.5, 0.5, txt, color=color, fontsize=130, ha="center",
                va="center", weight="bold")
        # little up/down arrow + delta
        delta = end - start
        sign = "▲" if delta >= 0 else "▼"
        ax.text(0.5, 0.38, f"{sign} {prefix}{abs(delta):,.0f}",
                color=(GREEN if delta >= 0 else RED), fontsize=46,
                ha="center", va="center", weight="bold")
        fig.savefig(fdir / f"f{i:04d}.png", facecolor=BG)
        plt.close(fig)
    return _frames_to_video(fdir, out_path)


# ---------------------------------------------------------------------------
# 2. ANIMATED BAR CHART
# ---------------------------------------------------------------------------
def bar_chart(labels: list, values: list, out_path: Path,
              duration: float = 4.0, title: str = "", prefix: str = "$") -> Path:
    frames = int(duration * FPS)
    fdir = _clean_dir("bar")
    vmax = max(values) * 1.2
    colors = [GREEN if v >= 0 else RED for v in values]
    for i in range(frames):
        t = _ease(i / max(1, frames - 1))
        fig = _fig()
        ax = fig.add_axes([0.12, 0.18, 0.76, 0.6])
        ax.set_facecolor(BG)
        cur = [v * t for v in values]
        bars = ax.bar(labels, cur, color=colors, width=0.6)
        ax.set_ylim(0, vmax)
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.tick_params(colors=WHITE, labelsize=30)
        ax.set_yticks([])
        for b, v in zip(bars, cur):
            ax.text(b.get_x() + b.get_width() / 2, b.get_height() + vmax * 0.02,
                    f"{prefix}{v:,.0f}", ha="center", color=WHITE,
                    fontsize=30, weight="bold")
        if title:
            fig.text(0.5, 0.86, title, color=WHITE, fontsize=52,
                     ha="center", weight="bold")
        fig.savefig(fdir / f"f{i:04d}.png", facecolor=BG)
        plt.close(fig)
    return _frames_to_video(fdir, out_path)


# ---------------------------------------------------------------------------
# 3. ANIMATED LINE GRAPH  (growth line drawing itself)
# ---------------------------------------------------------------------------
def line_graph(values: list, out_path: Path, duration: float = 4.0,
               title: str = "", prefix: str = "$") -> Path:
    frames = int(duration * FPS)
    fdir = _clean_dir("line")
    xs = np.arange(len(values))
    ys = np.array(values, dtype=float)
    for i in range(frames):
        t = _ease(i / max(1, frames - 1))
        n = max(2, int(len(values) * t))
        fig = _fig()
        ax = fig.add_axes([0.1, 0.2, 0.8, 0.55])
        ax.set_facecolor(BG)
        ax.plot(xs[:n], ys[:n], color=GREEN, linewidth=6)
        ax.fill_between(xs[:n], ys[:n], ys.min(), color=GREEN, alpha=0.15)
        ax.scatter([xs[n - 1]], [ys[n - 1]], color=GOLD, s=180, zorder=5)
        ax.text(xs[n - 1], ys[n - 1] + (ys.max() - ys.min()) * 0.08,
                f"{prefix}{ys[n-1]:,.0f}", color=GOLD, fontsize=40,
                ha="center", weight="bold")
        ax.set_xlim(0, len(values) - 1)
        ax.set_ylim(ys.min() * 0.9, ys.max() * 1.15)
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.set_xticks([]); ax.set_yticks([])
        if title:
            fig.text(0.5, 0.84, title, color=WHITE, fontsize=52,
                     ha="center", weight="bold")
        fig.savefig(fdir / f"f{i:04d}.png", facecolor=BG)
        plt.close(fig)
    return _frames_to_video(fdir, out_path)


# ---------------------------------------------------------------------------
# 4. STAT CARDS  (animated key numbers popping in)
# ---------------------------------------------------------------------------
def stat_cards(stats: list, out_path: Path, duration: float = 4.0,
               title: str = "") -> Path:
    """
    stats: list of (big_value, small_label), e.g. [("+25%","Returns"),
           ("$12k","Saved"), ("3 yrs","Time")]
    """
    frames = int(duration * FPS)
    fdir = _clean_dir("stat")
    n = len(stats)
    for i in range(frames):
        fig = _fig()
        if title:
            fig.text(0.5, 0.82, title, color=WHITE, fontsize=52,
                     ha="center", weight="bold")
        for k, (big, small) in enumerate(stats):
            # each card pops in sequence
            appear = (i / frames) * n - k
            scale = max(0.0, min(1.0, appear))
            scale = _ease(scale)
            if scale <= 0:
                continue
            y = 0.62 - k * (0.5 / max(1, n))
            alpha = scale
            fig.text(0.5, y, str(big), color=GREEN, fontsize=int(96 * (0.5 + 0.5 * scale)),
                     ha="center", weight="bold", alpha=alpha)
            fig.text(0.5, y - 0.06, str(small), color=GREY, fontsize=38,
                     ha="center", alpha=alpha)
        fig.savefig(fdir / f"f{i:04d}.png", facecolor=BG)
        plt.close(fig)
    return _frames_to_video(fdir, out_path)


# ---------------------------------------------------------------------------
# 5. COMPOUND CURVE  (#2 + #14 "what $X becomes" — growth curve w/ year labels)
# ---------------------------------------------------------------------------
def compound_curve(principal: float, monthly: float, rate: float, years: int,
                   out_path: Path, duration: float = 5.0, prefix: str = "$") -> Path:
    """
    Animate a compound-growth curve. Computes the future value month by month,
    draws the curve, and labels milestone years. Great for "what $X becomes".
    """
    months = years * 12
    r = rate / 12.0
    bal, series = principal, [principal]
    for _ in range(months):
        bal = bal * (1 + r) + monthly
        series.append(bal)
    ys = np.array(series)
    xs = np.arange(len(ys)) / 12.0  # in years
    frames = int(duration * FPS)
    fdir = _clean_dir("comp")
    for i in range(frames):
        t = _ease(i / max(1, frames - 1))
        n = max(2, int(len(ys) * t))
        fig = _fig()
        # chart sits in the middle band; leave room top (title) and bottom (captions)
        ax = fig.add_axes([0.12, 0.30, 0.76, 0.42]); ax.set_facecolor(BG)
        ax.plot(xs[:n], ys[:n], color=GREEN, linewidth=7)
        ax.fill_between(xs[:n], ys[:n], ys.min(), color=GREEN, alpha=0.15)
        ax.scatter([xs[n - 1]], [ys[n - 1]], color=GOLD, s=200, zorder=5)
        # value label: flip alignment near the right edge so it never clips
        near_right = xs[n - 1] > years * 0.7
        ax.annotate(f"{prefix}{ys[n-1]:,.0f}",
                    xy=(xs[n - 1], ys[n - 1]),
                    xytext=(-12 if near_right else 12, 18),
                    textcoords="offset points",
                    color=GOLD, fontsize=42, weight="bold",
                    ha="right" if near_right else "left", va="bottom",
                    clip_on=False)
        # year milestone ticks
        for yr in [1, 5, 10, 15, 20, 25, 30]:
            if yr <= xs[n - 1] and yr <= years:
                ax.axvline(yr, color=GREY, alpha=0.25, linewidth=1)
                ax.text(yr, ys.min(), f"Yr {yr}", color=GREY, fontsize=24,
                        ha="center", va="top")
        ax.set_xlim(-0.5, years + 0.5); ax.set_ylim(ys.min() * 0.9, ys.max() * 1.25)
        for s in ax.spines.values():
            s.set_visible(False)
        ax.set_xticks([]); ax.set_yticks([])
        fig.text(0.5, 0.80, f"{prefix}{monthly:,.0f}/mo at {rate*100:.0f}%  •  {years} yrs",
                 color=WHITE, fontsize=46, ha="center", weight="bold")
        fig.savefig(fdir / f"f{i:04d}.png", facecolor=BG)
        plt.close(fig)
    return _frames_to_video(fdir, out_path)


# ---------------------------------------------------------------------------
# 6. BEFORE / AFTER split screen (#3)
# ---------------------------------------------------------------------------
def before_after(left_label: str, left_value: str, right_label: str,
                 right_value: str, out_path: Path, duration: float = 4.0,
                 title: str = "") -> Path:
    frames = int(duration * FPS)
    fdir = _clean_dir("ba")
    for i in range(frames):
        t = _ease(i / max(1, frames - 1))
        fig = _fig()
        if title:
            fig.text(0.5, 0.88, title, color=WHITE, fontsize=50,
                     ha="center", weight="bold")
        # left (red / without) slides from left, right (green / with) from right
        lx = 0.27 - (1 - t) * 0.3
        rx = 0.73 + (1 - t) * 0.3
        fig.patches.append(plt.Rectangle((0.5 - 0.004, 0.15), 0.008, 0.6,
                           transform=fig.transFigure, color=GREY, alpha=0.4))
        fig.text(lx, 0.6, left_label, color=GREY, fontsize=34, ha="center")
        fig.text(lx, 0.5, left_value, color=RED, fontsize=80, ha="center",
                 weight="bold", alpha=t)
        fig.text(rx, 0.6, right_label, color=GREY, fontsize=34, ha="center")
        fig.text(rx, 0.5, right_value, color=GREEN, fontsize=80, ha="center",
                 weight="bold", alpha=t)
        fig.savefig(fdir / f"f{i:04d}.png", facecolor=BG)
        plt.close(fig)
    return _frames_to_video(fdir, out_path)


# ---------------------------------------------------------------------------
# 7. COMPARISON RACE bars (#5)  Savings 0.5% vs Index 8%
# ---------------------------------------------------------------------------
def comparison_race(items: list, out_path: Path, duration: float = 4.5,
                    title: str = "", prefix: str = "$") -> Path:
    """items: list of (label, value). Bars grow to show dramatic difference."""
    labels = [x[0] for x in items]
    values = [float(x[1]) for x in items]
    vmax = max(values) * 1.15
    frames = int(duration * FPS)
    fdir = _clean_dir("race")
    colors = [RED, GREEN, GOLD, "#3b82f6"]
    for i in range(frames):
        t = _ease(i / max(1, frames - 1))
        fig = _fig()
        ax = fig.add_axes([0.28, 0.2, 0.6, 0.55]); ax.set_facecolor(BG)
        cur = [v * t for v in values]
        y = np.arange(len(labels))
        ax.barh(y, cur, color=[colors[k % len(colors)] for k in range(len(labels))],
                height=0.6)
        ax.set_yticks(y); ax.set_yticklabels(labels, color=WHITE, fontsize=30)
        ax.invert_yaxis(); ax.set_xlim(0, vmax)
        for k, v in enumerate(cur):
            ax.text(v + vmax * 0.01, k, f"{prefix}{v:,.0f}", va="center",
                    color=WHITE, fontsize=28, weight="bold")
        for s in ax.spines.values():
            s.set_visible(False)
        ax.set_xticks([])
        if title:
            fig.text(0.5, 0.84, title, color=WHITE, fontsize=48,
                     ha="center", weight="bold")
        fig.savefig(fdir / f"f{i:04d}.png", facecolor=BG)
        plt.close(fig)
    return _frames_to_video(fdir, out_path)


# ---------------------------------------------------------------------------
# 8. PROGRESS BAR fill (#4)  "Emergency fund: 40% complete"
# ---------------------------------------------------------------------------
def progress_bar(label: str, percent: float, out_path: Path,
                 duration: float = 3.5, sub: str = "") -> Path:
    frames = int(duration * FPS)
    fdir = _clean_dir("prog")
    pct = max(0, min(100, percent))
    for i in range(frames):
        t = _ease(i / max(1, frames - 1))
        cur = pct * t
        fig = _fig()
        fig.text(0.5, 0.62, label, color=WHITE, fontsize=50, ha="center",
                 weight="bold")
        # bar track + fill
        fig.patches.append(plt.Rectangle((0.15, 0.48), 0.7, 0.06,
                           transform=fig.transFigure, color="#1e2a3a"))
        fig.patches.append(plt.Rectangle((0.15, 0.48), 0.7 * cur / 100, 0.06,
                           transform=fig.transFigure, color=GREEN))
        fig.text(0.5, 0.4, f"{cur:.0f}%", color=GREEN, fontsize=90,
                 ha="center", weight="bold")
        if sub:
            fig.text(0.5, 0.32, sub, color=GREY, fontsize=34, ha="center")
        fig.savefig(fdir / f"f{i:04d}.png", facecolor=BG)
        plt.close(fig)
    return _frames_to_video(fdir, out_path)


# ---------------------------------------------------------------------------
# 9. PIE CHART build (#6)  50/30/20 budget
# ---------------------------------------------------------------------------
def pie_build(slices: list, out_path: Path, duration: float = 4.0,
              title: str = "") -> Path:
    """slices: list of (label, value). Pie animates from 0 to full."""
    labels = [s[0] for s in slices]
    vals = np.array([float(s[1]) for s in slices])
    total = vals.sum()
    frames = int(duration * FPS)
    fdir = _clean_dir("pie")
    cols = [GREEN, GOLD, "#3b82f6", RED, "#a855f7"]
    for i in range(frames):
        t = _ease(i / max(1, frames - 1))
        fig = _fig()
        ax = fig.add_axes([0.15, 0.25, 0.7, 0.45]); ax.set_facecolor(BG)
        start = 90
        for k, v in enumerate(vals):
            extent = 360 * (v / total) * t
            ax.add_patch(matplotlib.patches.Wedge(
                (0.5, 0.5), 0.45, start, start + extent,
                facecolor=cols[k % len(cols)], edgecolor=BG, linewidth=3,
                transform=ax.transAxes))
            start += extent
        ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
        if title:
            fig.text(0.5, 0.82, title, color=WHITE, fontsize=50,
                     ha="center", weight="bold")
        # legend
        for k, (lb, v) in enumerate(zip(labels, vals)):
            yk = 0.2 - k * 0.045
            fig.patches.append(plt.Rectangle((0.3, yk), 0.03, 0.03,
                               transform=fig.transFigure, color=cols[k % len(cols)]))
            fig.text(0.35, yk + 0.005, f"{lb} — {v/total*100:.0f}%",
                     color=WHITE, fontsize=30, va="bottom")
        fig.savefig(fdir / f"f{i:04d}.png", facecolor=BG)
        plt.close(fig)
    return _frames_to_video(fdir, out_path)


# ---------------------------------------------------------------------------
# 10. MYTH vs FACT flip cards (#11)
# ---------------------------------------------------------------------------
def myth_vs_fact(myth: str, fact: str, out_path: Path, duration: float = 5.0) -> Path:
    frames = int(duration * FPS)
    fdir = _clean_dir("myth")
    flip = int(frames * 0.5)
    for i in range(frames):
        fig = _fig()
        if i < flip:  # MYTH (red)
            a = _ease(min(1, i / (flip * 0.3)))
            fig.text(0.5, 0.6, "MYTH", color=RED, fontsize=70, ha="center",
                     weight="bold", alpha=a)
            fig.text(0.5, 0.46, myth, color=WHITE, fontsize=40, ha="center",
                     va="center", wrap=True, alpha=a)
        else:  # FACT (green)
            a = _ease(min(1, (i - flip) / (flip * 0.3)))
            fig.text(0.5, 0.6, "FACT", color=GREEN, fontsize=70, ha="center",
                     weight="bold", alpha=a)
            fig.text(0.5, 0.46, fact, color=WHITE, fontsize=40, ha="center",
                     va="center", wrap=True, alpha=a)
        fig.savefig(fdir / f"f{i:04d}.png", facecolor=BG)
        plt.close(fig)
    return _frames_to_video(fdir, out_path)


# ---------------------------------------------------------------------------
# 11. MISTAKE COST reveal (#15)  "This mistake = -$2,400/year"
# ---------------------------------------------------------------------------
def mistake_cost(mistake: str, cost: float, out_path: Path,
                 duration: float = 4.0, prefix: str = "$",
                 period: str = "/year") -> Path:
    frames = int(duration * FPS)
    fdir = _clean_dir("mist")
    reveal = int(frames * 0.45)
    for i in range(frames):
        fig = _fig()
        fig.text(0.5, 0.62, mistake, color=WHITE, fontsize=46, ha="center",
                 va="center", weight="bold", wrap=True)
        if i >= reveal:
            t = _ease(min(1, (i - reveal) / (frames - reveal)))
            cur = cost * t
            fig.text(0.5, 0.42, f"-{prefix}{cur:,.0f}{period}", color=RED,
                     fontsize=int(110 * (0.6 + 0.4 * t)), ha="center",
                     weight="bold", alpha=t)
        fig.savefig(fdir / f"f{i:04d}.png", facecolor=BG)
        plt.close(fig)
    return _frames_to_video(fdir, out_path)


def app_mockup(app_name: str, balance: str, sub_lines: list, out_path: Path,
               duration: float = 4.0, accent: str = GREEN) -> Path:
    """
    A generic (made-up) banking/investing APP screen mockup — phone frame,
    app name bar, big balance, a couple of rows. Looks real but is 100%
    original (no real bank UI copied).
    sub_lines: list of (label, value) rows, e.g. [("This month","+$420"),...]
    """
    frames = int(duration * FPS)
    fdir = _clean_dir("app")
    for i in range(frames):
        t = _ease(min(1, i / (frames * 0.25)))
        fig = _fig()
        # phone frame (rounded rect) centered
        px, py, pw, ph = 0.18, 0.16, 0.64, 0.66
        fig.patches.append(plt.Rectangle((px, py), pw, ph,
                           transform=fig.transFigure, facecolor="#101826",
                           edgecolor="#2a3a52", linewidth=3))
        # top app bar
        fig.patches.append(plt.Rectangle((px, py + ph - 0.07), pw, 0.07,
                           transform=fig.transFigure, facecolor=accent))
        fig.text(0.5, py + ph - 0.035, app_name, color="#0b1220", fontsize=30,
                 ha="center", va="center", weight="bold")
        # balance label + big number (counts/appears)
        fig.text(0.5, py + ph - 0.16, "Total Balance", color=GREY,
                 fontsize=26, ha="center")
        fig.text(0.5, py + ph - 0.26, balance, color=WHITE,
                 fontsize=int(78 * (0.5 + 0.5 * t)), ha="center",
                 weight="bold", alpha=t)
        # rows
        for k, (lab, val) in enumerate(sub_lines[:3]):
            ry = py + ph - 0.4 - k * 0.09
            appear = _ease(max(0, min(1, (i / frames) * 3 - k)))
            fig.text(px + 0.06, ry, lab, color=GREY, fontsize=26,
                     ha="left", va="center", alpha=appear)
            col = accent if str(val).strip().startswith("+") else WHITE
            fig.text(px + pw - 0.06, ry, str(val), color=col, fontsize=28,
                     ha="right", va="center", weight="bold", alpha=appear)
        fig.savefig(fdir / f"f{i:04d}.png", facecolor=BG)
        plt.close(fig)
    return _frames_to_video(fdir, out_path)


def highlight_number(big: str, sub: str, out_path: Path, duration: float = 3.5,
                     wait_text: str = "") -> Path:
    """
    A dramatic single-number reveal with a pulsing highlight circle around it
    and an optional 'wait for it...' build-up. Great right before a payoff.
    """
    frames = int(duration * FPS)
    fdir = _clean_dir("hl")
    reveal = int(frames * (0.4 if wait_text else 0.1))
    for i in range(frames):
        fig = _fig()
        if wait_text and i < reveal:
            a = _ease(min(1, i / (reveal * 0.5)))
            dots = "." * (1 + (i // 8) % 3)
            fig.text(0.5, 0.5, wait_text + dots, color=GOLD, fontsize=58,
                     ha="center", va="center", weight="bold", alpha=a)
        else:
            t = _ease(min(1, (i - reveal) / max(1, frames - reveal)))
            # pulsing highlight ring
            import math
            pulse = 0.34 + 0.02 * math.sin(i * 0.4)
            ax = fig.add_axes([0, 0, 1, 1]); ax.axis("off")
            ax.add_patch(matplotlib.patches.Ellipse(
                (0.5, 0.52), pulse, pulse * 1.6 * 0.42,
                transform=ax.transAxes, fill=False, edgecolor=RED,
                linewidth=6, alpha=0.7 * t))
            fig.text(0.5, 0.52, big, color=GREEN,
                     fontsize=int(120 * (0.5 + 0.5 * t)), ha="center",
                     va="center", weight="bold", alpha=t)
            if sub:
                fig.text(0.5, 0.4, sub, color=GREY, fontsize=34,
                         ha="center", alpha=t)
        fig.savefig(fdir / f"f{i:04d}.png", facecolor=BG)
        plt.close(fig)
    return _frames_to_video(fdir, out_path)


def indices_board(items: list, out_path: Path, duration: float = 6.0,
                  heading: str = "MARKET INDICES", market: str = "INDIA",
                  date_str: str = "") -> Path:
    """
    Full-screen index board: name + level + day change (green/red).
    For the long-form market wrap intro. 1080x1920.
    """
    frames = int(duration * FPS)
    fdir = _clean_dir("idx")
    n = len(items)
    cur_sym = "₹" if (items and items[0].get("inr")) else ""
    for i in range(frames):
        prog = i / max(1, frames - 1)
        fig = _fig()
        fig.text(0.5, 0.86, market, color=GOLD, fontsize=34, ha="center",
                 weight="bold")
        if date_str:
            fig.text(0.5, 0.825, date_str, color=GREY, fontsize=26, ha="center")
        fig.text(0.5, 0.75, heading, color=WHITE, fontsize=54, ha="center",
                 weight="bold")
        top = 0.62
        gap = 0.14
        for k, it in enumerate(items):
            appear = _ease(max(0, min(1, prog * n - k)))
            if appear <= 0:
                continue
            y = top - k * gap
            up = it["change"] >= 0
            accent = GREEN if up else RED
            fig.text(0.10, y, it["name"], color=WHITE, fontsize=42,
                     ha="left", weight="bold", alpha=appear)
            fig.text(0.10, y - 0.05, f"{cur_sym}{it['price']:,.0f}", color=GREY,
                     fontsize=30, ha="left", alpha=appear)
            sign = "+" if up else ""
            fig.text(0.92, y, f"{sign}{it['change']:.2f}%", color=accent,
                     fontsize=48, ha="right", weight="bold", alpha=appear)
        fig.savefig(fdir / f"f{i:04d}.png", facecolor=BG)
        plt.close(fig)
    return _frames_to_video(fdir, out_path)


def news_board(headlines: list, out_path: Path, duration: float = 8.0,
               heading: str = "TOP MARKET NEWS", market: str = "INDIA",
               date_str: str = "") -> Path:
    """
    News headlines board — each headline wraps to 2 lines, reveals in turn.
    For the market-wrap news section. 1080x1920.
    """
    import textwrap
    frames = int(duration * FPS)
    fdir = _clean_dir("news")
    n = len(headlines)
    wrapped = [textwrap.fill(h, width=32) for h in headlines]
    for i in range(frames):
        prog = i / max(1, frames - 1)
        fig = _fig()
        fig.text(0.5, 0.86, market, color=GOLD, fontsize=32, ha="center",
                 weight="bold")
        if date_str:
            fig.text(0.5, 0.825, date_str, color=GREY, fontsize=25, ha="center")
        fig.text(0.5, 0.75, heading, color=WHITE, fontsize=48, ha="center",
                 weight="bold")
        top = 0.65
        gap = 0.13
        for k, h in enumerate(wrapped):
            appear = _ease(max(0, min(1, prog * n - k)))
            if appear <= 0:
                continue
            y = top - k * gap
            fig.text(0.08, y, "▸", color=GOLD, fontsize=30, ha="left",
                     va="top", alpha=appear)
            fig.text(0.14, y, h, color="#E8E8E8", fontsize=30, ha="left",
                     va="top", alpha=appear, linespacing=1.2)
        fig.savefig(fdir / f"f{i:04d}.png", facecolor=BG)
        plt.close(fig)
    return _frames_to_video(fdir, out_path)


def title_card(main: str, sub: str, out_path: Path, duration: float = 3.0,
               date_str: str = "") -> Path:
    """Simple intro/outro card — big centered title + subtitle. 1080x1920."""
    frames = int(duration * FPS)
    fdir = _clean_dir("ttl")
    for i in range(frames):
        prog = i / max(1, frames - 1)
        a = _ease(min(1, prog * 2))
        fig = _fig()
        fig.text(0.5, 0.56, main, color=WHITE, fontsize=72, ha="center",
                 va="center", weight="bold", alpha=a)
        if sub:
            fig.text(0.5, 0.46, sub, color=GOLD, fontsize=38, ha="center",
                     va="center", alpha=a)
        if date_str:
            fig.text(0.5, 0.40, date_str, color=GREY, fontsize=30, ha="center",
                     va="center", alpha=a)
        fig.savefig(fdir / f"f{i:04d}.png", facecolor=BG)
        plt.close(fig)
    return _frames_to_video(fdir, out_path)


def stock_section(items: list, out_path: Path, duration: float = 5.0,
                  heading: str = "TOP GAINERS", market: str = "US STOCKS",
                  date_str: str = "", positive: bool = True) -> Path:
    """
    ONE full-screen section (just gainers OR just losers). Big rows, plenty of
    room, safe top/bottom margins. Rows reveal one by one. 1080x1920.
    """
    frames = int(duration * FPS)
    fdir = _clean_dir("sec")
    accent = GREEN if positive else RED
    n = len(items)
    cur_sym = "₹" if (items and items[0].get("inr")) else "$"
    for i in range(frames):
        prog = i / max(1, frames - 1)
        fig = _fig()
        # header block (safe zone, lowered from top edge)
        fig.text(0.5, 0.86, market, color=GOLD, fontsize=34, ha="center",
                 weight="bold")
        if date_str:
            fig.text(0.5, 0.825, date_str, color=GREY, fontsize=26, ha="center")
        fig.text(0.5, 0.76, heading, color=accent, fontsize=58, ha="center",
                 weight="bold")
        # rows — big, spaced, reveal in sequence
        top = 0.66
        gap = 0.115
        for k, it in enumerate(items):
            appear = _ease(max(0, min(1, prog * n - k)))
            if appear <= 0:
                continue
            y = top - k * gap
            chg = it["change"] * appear
            fig.text(0.10, y, it["symbol"][:14], color=WHITE, fontsize=46,
                     ha="left", weight="bold", alpha=appear)
            if it.get("prev") and it.get("price"):
                ptxt = f"{cur_sym}{it['prev']:,.0f} > {cur_sym}{it['price']:,.0f}"
                fig.text(0.10, y - 0.045, ptxt, color=GREY, fontsize=28,
                         ha="left", alpha=appear)
            sign = "+" if positive else ""
            fig.text(0.92, y, f"{sign}{chg:.1f}%", color=accent, fontsize=52,
                     ha="right", weight="bold", alpha=appear)
        fig.savefig(fdir / f"f{i:04d}.png", facecolor=BG)
        plt.close(fig)
    return _frames_to_video(fdir, out_path)


def stock_movers(gainers: list, losers: list, out_path: Path,
                 duration: float = 8.0, title: str = "TOP MOVERS TODAY",
                 market: str = "US", date_str: str = "") -> Path:
    """
    Animated top gainers (green) + losers (red) board for stock reels.
    gainers/losers: list of dicts {symbol, change, price, prev}.
    Shows date + 'prev -> current' price. Rows slide/count in. 1080x1920.
    """
    frames = int(duration * FPS)
    fdir = _clean_dir("stk")
    n_g, n_l = len(gainers), len(losers)
    total_rows = n_g + n_l

    # SAFE ZONE: keep content between ~0.86 (below top UI) and ~0.10 (above
    # bottom UI). Title pushed down from the very top edge.
    for i in range(frames):
        prog = i / max(1, frames - 1)
        fig = _fig()
        # title + market + DATE (lowered into the safe zone)
        fig.text(0.5, 0.865, title, color=WHITE, fontsize=46, ha="center",
                 weight="bold")
        fig.text(0.30, 0.825, market, color=GOLD, fontsize=27, ha="center")
        if date_str:
            fig.text(0.70, 0.825, date_str, color=GREY, fontsize=25, ha="center")

        # GAINERS section
        fig.text(0.12, 0.77, "TOP GAINERS", color=GREEN, fontsize=32,
                 ha="left", weight="bold")
        cur_sym = "₹" if (gainers and gainers[0].get("inr")) else "$"
        for k, g in enumerate(gainers):
            appear = _ease(max(0, min(1, prog * total_rows - k)))
            if appear <= 0:
                continue
            y = 0.72 - k * 0.065
            cur = g["change"] * appear
            fig.text(0.08, y, g["symbol"][:13], color=WHITE, fontsize=29,
                     ha="left", weight="bold", alpha=appear)
            # prev -> current price
            if g.get("prev") and g.get("price"):
                ptxt = f"{cur_sym}{g['prev']:,.0f}>{cur_sym}{g['price']:,.0f}"
            else:
                ptxt = f"{cur_sym}{g.get('price',0):,.0f}"
            fig.text(0.50, y, ptxt, color=GREY, fontsize=22, ha="left", alpha=appear)
            fig.text(0.95, y, f"+{cur:.1f}%", color=GREEN, fontsize=32,
                     ha="right", weight="bold", alpha=appear)

        # LOSERS section
        ly = 0.72 - n_g * 0.065 - 0.035
        fig.text(0.12, ly, "TOP LOSERS", color=RED, fontsize=32,
                 ha="left", weight="bold")
        lcur_sym = "₹" if (losers and losers[0].get("inr")) else "$"
        for k, l in enumerate(losers):
            appear = _ease(max(0, min(1, prog * total_rows - (n_g + k))))
            if appear <= 0:
                continue
            y = ly - 0.05 - k * 0.065
            cur = l["change"] * appear
            fig.text(0.08, y, l["symbol"][:13], color=WHITE, fontsize=29,
                     ha="left", weight="bold", alpha=appear)
            if l.get("prev") and l.get("price"):
                ptxt = f"{lcur_sym}{l['prev']:,.0f}>{lcur_sym}{l['price']:,.0f}"
            else:
                ptxt = f"{lcur_sym}{l.get('price',0):,.0f}"
            fig.text(0.50, y, ptxt, color=GREY, fontsize=22, ha="left", alpha=appear)
            fig.text(0.95, y, f"{cur:.1f}%", color=RED, fontsize=32,
                     ha="right", weight="bold", alpha=appear)

        fig.savefig(fdir / f"f{i:04d}.png", facecolor=BG)
        plt.close(fig)
    return _frames_to_video(fdir, out_path)


def text_card(text: str, out_path: Path, duration: float = 3.0,
              color: str = WHITE) -> Path:
    """A simple centered text scene on the finance background (intro/hook)."""
    frames = int(duration * FPS)
    fdir = _clean_dir("txt")
    for i in range(frames):
        t = _ease(min(1, i / (frames * 0.3)))
        fig = _fig()
        fig.text(0.5, 0.5, text, color=color, fontsize=64, ha="center",
                 va="center", weight="bold", wrap=True, alpha=t)
        fig.savefig(fdir / f"f{i:04d}.png", facecolor=BG)
        plt.close(fig)
    return _frames_to_video(fdir, out_path)


# ---------------------------------------------------------------------------
# DISPATCH: render any chart visual by name (used by scenes)
# ---------------------------------------------------------------------------
def render_visual(visual: str, data: dict, out_path: Path,
                  duration: float) -> Path:
    """Render one chart visual by name+data to a clip of given duration."""
    d = data or {}
    if visual == "counter":
        return number_counter(d["start"], d["end"], out_path, duration,
                              prefix=d.get("prefix", "$"),
                              suffix=d.get("suffix", ""), label=d.get("label", ""))
    if visual == "compound":
        return compound_curve(d.get("principal", 0), d["monthly"], d["rate"],
                              d["years"], out_path, duration,
                              prefix=d.get("prefix", "$"))
    if visual == "line":
        return line_graph(d["values"], out_path, duration,
                         title=d.get("title", ""), prefix=d.get("prefix", "$"))
    if visual == "bar":
        return bar_chart(d["labels"], d["values"], out_path, duration,
                        title=d.get("title", ""), prefix=d.get("prefix", "$"))
    if visual == "race":
        return comparison_race([tuple(x) for x in d["items"]], out_path,
                              duration, title=d.get("title", ""),
                              prefix=d.get("prefix", "$"))
    if visual == "before_after":
        return before_after(d["left_label"], d["left_value"], d["right_label"],
                           d["right_value"], out_path, duration,
                           title=d.get("title", ""))
    if visual == "progress":
        return progress_bar(d["label"], d["percent"], out_path, duration,
                           sub=d.get("sub", ""))
    if visual == "pie":
        return pie_build([tuple(s) for s in d["slices"]], out_path, duration,
                        title=d.get("title", ""))
    if visual == "stat":
        return stat_cards([tuple(s) for s in d["stats"]], out_path, duration,
                         title=d.get("title", ""))
    if visual == "myth":
        return myth_vs_fact(d["myth"], d["fact"], out_path, duration)
    if visual == "mistake":
        return mistake_cost(d["mistake"], d["cost"], out_path, duration,
                           prefix=d.get("prefix", "$"),
                           period=d.get("period", "/year"))
    if visual == "app":
        return app_mockup(d.get("app_name", "MyMoney"), d.get("balance", "$0"),
                          [tuple(x) for x in d.get("rows", [])], out_path,
                          duration)
    if visual == "highlight":
        return highlight_number(d.get("big", ""), d.get("sub", ""), out_path,
                               duration, wait_text=d.get("wait_text", ""))
    if visual == "text":
        return text_card(d.get("text", ""), out_path, duration)
    raise ValueError(f"Unknown visual: {visual}")
