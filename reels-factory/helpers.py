"""
Helper functions for Reels Factory.
These do the real work; server.py exposes them as MCP tools.
"""
import os
import json
import subprocess
import textwrap
import urllib.request
import urllib.parse
from pathlib import Path

BASE = Path(__file__).parent
OUTPUT = BASE / "output"
TEMP = BASE / "temp"
ASSETS = BASE / "assets"
MUSIC = BASE / "music"
for d in (OUTPUT, TEMP, ASSETS, MUSIC):
    d.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# .env loader (no external dependency)
# ---------------------------------------------------------------------------
def load_env():
    env = {}
    envfile = BASE / ".env"
    if envfile.exists():
        for line in envfile.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    # OS env wins over file
    for k in ("PEXELS_API_KEY", "FB_PAGE_ID", "FB_PAGE_ACCESS_TOKEN", "VOICE",
              "GEMINI_API_KEY"):
        if os.environ.get(k):
            env[k] = os.environ[k]
    return env


def load_pages():
    """
    Load multi-page config (nickname -> {page_id, token, ...}).
    Priority:
      1) FB_PAGES_JSON env var (used on cloud, where pages.json isn't in git)
      2) pages.json file (local)
    Returns {} if neither is present.
    """
    raw = os.environ.get("FB_PAGES_JSON", "")
    if not raw:
        f = BASE / "pages.json"
        if f.exists():
            raw = f.read_text(encoding="utf-8")
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except Exception:
        return {}
    return {k: v for k, v in data.items()
            if not k.startswith("_") and isinstance(v, dict)}


def save_pages(pages: dict):
    """Write the pages dict back to pages.json (pretty)."""
    f = BASE / "pages.json"
    f.write_text(json.dumps(pages, indent=2, ensure_ascii=False), encoding="utf-8")
    return f


# ---------------------------------------------------------------------------
# 1. VOICE  (Edge-TTS free, or Kokoro local for real-human quality)
# ---------------------------------------------------------------------------
_KOKORO_PIPE = None  # cached pipeline so the model loads only once

# Kokoro voice presets (af_* female, am_* male, b* British). Pick natural ones.
KOKORO_VOICES = {
    "kokoro:female": "af_heart",
    "kokoro:male":   "am_michael",
    "kokoro:british":"bf_emma",
    "kokoro:bm":     "bm_george",
}


def _kokoro_say(text: str, out_path: Path, voice_id: str = "af_heart") -> Path:
    """Generate speech with the local Kokoro model. Loads once, then cached."""
    global _KOKORO_PIPE
    import soundfile as sf
    if _KOKORO_PIPE is None:
        from kokoro import KPipeline
        _KOKORO_PIPE = KPipeline(lang_code="a")  # 'a' = American English
    wav_path = Path(out_path).with_suffix(".wav")
    audio_chunks = []
    for _, _, audio in _KOKORO_PIPE(text, voice=voice_id):
        audio_chunks.append(audio)
    import numpy as np
    full = np.concatenate(audio_chunks) if len(audio_chunks) > 1 else audio_chunks[0]
    sf.write(str(wav_path), full, 24000)
    # convert wav -> mp3 for consistency with the rest of the pipeline
    subprocess.run(["ffmpeg", "-y", "-i", str(wav_path), str(out_path)],
                   check=True, capture_output=True, text=True)
    return Path(out_path)


# Gemini TTS — ALL 30 prebuilt voices. Use friendly aliases ("gemini:female")
# or the raw name ("gemini:Kore"). The trait next to each helps Claude pick.
GEMINI_VOICES = {
    # --- handy aliases ---
    "gemini:female":  "Kore",        # firm, clear female (default)
    "gemini:male":    "Puck",        # upbeat male
    "gemini:deep":    "Charon",      # deep male, documentary
    "gemini:warm":    "Aoede",       # breezy, warm female
    "gemini:bright":  "Zephyr",      # bright female
    "gemini:calm":    "Enceladus",   # calm, breathy
    "gemini:news":    "Iapetus",     # clear, news-anchor
    "gemini:soft":    "Vindemiatrix",# gentle, soft
    # --- all 30 raw voices (use as gemini:Name) ---
    "gemini:Zephyr": "Zephyr", "gemini:Puck": "Puck", "gemini:Charon": "Charon",
    "gemini:Kore": "Kore", "gemini:Fenrir": "Fenrir", "gemini:Leda": "Leda",
    "gemini:Orus": "Orus", "gemini:Aoede": "Aoede", "gemini:Callirrhoe": "Callirrhoe",
    "gemini:Autonoe": "Autonoe", "gemini:Enceladus": "Enceladus", "gemini:Iapetus": "Iapetus",
    "gemini:Umbriel": "Umbriel", "gemini:Algieba": "Algieba", "gemini:Despina": "Despina",
    "gemini:Erinome": "Erinome", "gemini:Algenib": "Algenib", "gemini:Rasalgethi": "Rasalgethi",
    "gemini:Laomedeia": "Laomedeia", "gemini:Achernar": "Achernar", "gemini:Alnilam": "Alnilam",
    "gemini:Schedar": "Schedar", "gemini:Gacrux": "Gacrux", "gemini:Pulcherrima": "Pulcherrima",
    "gemini:Achird": "Achird", "gemini:Zubenelgenubi": "Zubenelgenubi", "gemini:Vindemiatrix": "Vindemiatrix",
    "gemini:Sadachbia": "Sadachbia", "gemini:Sadaltager": "Sadaltager", "gemini:Sulafat": "Sulafat",
}


def _gemini_say(text: str, out_path: Path, voice_name: str,
                api_key: str, model: str = "gemini-2.5-flash-preview-tts") -> Path:
    """Generate speech with Gemini TTS (paid, ~$10/1M chars). Real-human quality."""
    from google import genai
    from google.genai import types
    import base64, struct, wave

    if not api_key:
        raise RuntimeError("GEMINI_API_KEY missing in .env")
    client = genai.Client(api_key=api_key)
    resp = client.models.generate_content(
        model=model,
        contents=text,
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=voice_name))),
        ),
    )
    data = resp.candidates[0].content.parts[0].inline_data.data
    # Gemini returns raw PCM (16-bit, 24kHz, mono). Wrap as WAV then -> mp3.
    wav_path = Path(out_path).with_suffix(".wav")
    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(24000)
        wf.writeframes(data)
    subprocess.run(["ffmpeg", "-y", "-i", str(wav_path), str(out_path)],
                   check=True, capture_output=True, text=True)
    return Path(out_path)


def make_voice(text: str, out_path: Path, voice: str = "en-US-AriaNeural",
               gemini_key: str = "") -> Path:
    """
    Generate an English voiceover mp3.
      - "gemini:*" (or a raw Gemini voice like "Kore") -> Gemini TTS
        (paid ~Rs0.71/min, real-human quality, 30 voices)
      - "kokoro:*" / af_/am_/bf_/bm_ -> local Kokoro (free, offline)
      - anything else -> Edge-TTS (fast, online, free)
    """
    out_path = Path(out_path)

    # Gemini path
    if voice.startswith("gemini:") or voice in GEMINI_VOICES.values():
        vname = GEMINI_VOICES.get(voice, voice.replace("gemini:", "") or "Kore")
        return _gemini_say(text, out_path, vname, gemini_key)

    # Kokoro path
    if voice.startswith("kokoro:") or voice[:3] in ("af_", "am_", "bf_", "bm_"):
        vid = KOKORO_VOICES.get(voice, voice.replace("kokoro:", "") or "af_heart")
        return _kokoro_say(text, out_path, vid)

    # Edge-TTS path
    cmd = ["python", "-m", "edge_tts", "--voice", voice,
           "--text", text, "--write-media", str(out_path)]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    if not out_path.exists() or out_path.stat().st_size == 0:
        raise RuntimeError("Edge-TTS produced no audio")
    return out_path


def pad_audio_tail(audio_path: Path, seconds: float = 0.8) -> Path:
    """
    Append a short silence to the end of a voice clip so the LAST WORD is
    never clipped by -shortest, and captions/end-card don't overlap it.
    Overwrites the file in place.
    """
    audio_path = Path(audio_path)
    padded = audio_path.with_name(audio_path.stem + "_pad" + audio_path.suffix)
    subprocess.run([
        "ffmpeg", "-y", "-i", str(audio_path),
        "-af", f"apad=pad_dur={seconds}",
        str(padded),
    ], check=True, capture_output=True, text=True)
    padded.replace(audio_path)
    return audio_path


def make_thumbnail(video_path: Path, out_path: Path = None,
                   at_seconds: float = 1.0) -> Path:
    """
    Grab a single frame from a reel as a .jpg thumbnail (for preview).
    """
    video_path = Path(video_path)
    if out_path is None:
        out_path = video_path.with_suffix(".jpg")
    subprocess.run([
        "ffmpeg", "-y", "-ss", f"{at_seconds:.2f}", "-i", str(video_path),
        "-frames:v", "1", "-q:v", "3", str(out_path),
    ], check=True, capture_output=True, text=True)
    return Path(out_path)


# ---------------------------------------------------------------------------
# 2. VISUALS  (Pexels free stock video)
# ---------------------------------------------------------------------------
def fetch_stock_video(query: str, api_key: str, out_path: Path) -> Path:
    """Download one portrait (9:16-ish) stock video clip from Pexels."""
    if not api_key:
        raise RuntimeError("PEXELS_API_KEY missing in .env")
    url = "https://api.pexels.com/videos/search?" + urllib.parse.urlencode({
        "query": query,
        "orientation": "portrait",
        "per_page": 5,
        "size": "medium",
    })
    req = urllib.request.Request(url, headers={
        "Authorization": api_key,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ReelsFactory/1.0",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read().decode())
    videos = data.get("videos", [])
    if not videos:
        raise RuntimeError(f"No Pexels videos found for '{query}'")
    # pick the best portrait file from the first video
    files = videos[0]["video_files"]
    portrait = [f for f in files if f.get("height", 0) >= f.get("width", 0)]
    chosen = (portrait or files)[0]
    video_url = chosen["link"]
    dl = urllib.request.Request(video_url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ReelsFactory/1.0",
    })
    with urllib.request.urlopen(dl, timeout=120) as resp, open(out_path, "wb") as f:
        while True:
            block = resp.read(1 << 16)
            if not block:
                break
            f.write(block)
    return Path(out_path)


def fetch_multiple_videos(query: str, api_key: str, count: int,
                          dest_dir: Path, stamp: str) -> list:
    """
    Feature 2 helper: download up to `count` DIFFERENT portrait clips for a
    query (so a reel can switch backgrounds). Falls back gracefully if Pexels
    returns fewer videos. Returns a list of downloaded paths.
    """
    if not api_key:
        raise RuntimeError("PEXELS_API_KEY missing in .env")
    url = "https://api.pexels.com/videos/search?" + urllib.parse.urlencode({
        "query": query,
        "orientation": "portrait",
        "per_page": max(count * 2, 5),
        "size": "medium",
    })
    req = urllib.request.Request(url, headers={
        "Authorization": api_key,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ReelsFactory/1.0",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read().decode())
    videos = data.get("videos", [])
    if not videos:
        raise RuntimeError(f"No Pexels videos found for '{query}'")

    paths = []
    for n, vid in enumerate(videos[:count]):
        files = vid["video_files"]
        portrait = [f for f in files if f.get("height", 0) >= f.get("width", 0)]
        chosen = (portrait or files)[0]
        out_path = dest_dir / f"bg_{stamp}_{n}.mp4"
        dl = urllib.request.Request(chosen["link"], headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ReelsFactory/1.0",
        })
        with urllib.request.urlopen(dl, timeout=120) as resp, open(out_path, "wb") as f:
            while True:
                block = resp.read(1 << 16)
                if not block:
                    break
                f.write(block)
        paths.append(out_path)
    return paths


def get_audio_duration(audio_path: Path) -> float:
    """Return duration of an audio/video file in seconds via ffprobe."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


# ---------------------------------------------------------------------------
# 3c. CAPTION + HASHTAGS  (Feature 3: build a Facebook caption from script)
# ---------------------------------------------------------------------------
NICHE_HASHTAGS = {
    "facts":    ["#facts", "#didyouknow", "#funfacts", "#mindblown",
                 "#interestingfacts", "#knowledge", "#amazingfacts"],
    "quotes":   ["#quotes", "#motivation", "#inspiration", "#mindset",
                 "#success", "#wisdom", "#lifequotes"],
    "space":    ["#space", "#universe", "#nasa", "#astronomy", "#cosmos"],
    "science":  ["#science", "#scifacts", "#nature", "#biology"],
    "history":  ["#history", "#historyfacts", "#didyouknow"],
}


def build_caption(script: str, niche: str = "facts", topic: str = "") -> str:
    """
    Feature 3: build a ready Facebook caption: first line as a hook from the
    script + relevant + trending-style hashtags. Returns the caption string.
    """
    first = script.strip().split(".")[0].strip()
    if len(first) > 90:
        first = first[:90].rsplit(" ", 1)[0] + "..."
    tags = list(NICHE_HASHTAGS.get(niche, NICHE_HASHTAGS["facts"]))
    if topic:
        t = topic.lower().strip().replace(" ", "")
        extra = NICHE_HASHTAGS.get(topic.lower().split()[0], [])
        tags = [f"#{t}"] + extra + tags
    # de-dup, keep order, cap at 12
    seen, final = set(), []
    for tag in tags:
        if tag.lower() not in seen:
            seen.add(tag.lower())
            final.append(tag)
        if len(final) >= 12:
            break
    cta = "Follow for more! 🔥"
    return f"{first} 🤯\n\n{cta}\n\n{' '.join(final)}"


# ---------------------------------------------------------------------------
# 3. CAPTIONS  (build an .ass subtitle file with big centered text)
# ---------------------------------------------------------------------------
# ASS colours are &HAABBGGRR (alpha,blue,green,red). 00 alpha = opaque.
STYLE_PRESETS = {
    # style:        (font, size, primary, outline, align, outline_w, shadow, words/chunk, marginV)
    "facts":     ("Arial",          90, "&H00FFFFFF", "&H00000000", 2, 6, 2, 6, 250),
    "quotes":    ("Georgia",        84, "&H00F5F5F5", "&H00202020", 5, 3, 3, 4, 0),
    "karaoke":   ("Arial",          92, "&H00FFFFFF", "&H00000000", 2, 5, 1, 5, 320),
    "boldbox":   ("Arial Black",    104,"&H00FFFFFF", "&H000000FF", 2, 8, 0, 3, 320),  # red outline
    "typewriter":("Consolas",       72, "&H0000FF00", "&H00000000", 2, 3, 1, 8, 300),  # green
    "cinematic": ("Georgia",        70, "&H0000D4F5", "&H00101010", 5, 2, 4, 4, 0),    # gold-ish
}


def _ts(sec):
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def build_captions(text: str, duration: float, out_path: Path,
                   style: str = "facts") -> Path:
    """
    Create a .ass subtitle file in one of several styles.

    styles:
      facts      -> bottom white captions, thick outline (~6 words)
      quotes     -> big centered light text (~4 words)
      karaoke    -> word-by-word YELLOW highlight as the voice speaks (viral)
      boldbox    -> huge Arial Black, red outline, MrBeast energy (~3 words)
      typewriter -> green monospace, letters appear one by one (suspense)
      cinematic  -> small elegant GOLD text, fade in/out, centered
    """
    preset = STYLE_PRESETS.get(style, STYLE_PRESETS["facts"])
    font, size, primary, outline, align, ow, shadow, wpc, marginV = preset

    style_line = (f"Style: Big,{font},{size},{primary},{outline},&H00000000,"
                  f"1,{ow},{shadow},{align},80,80,{marginV},1")

    header = textwrap.dedent(f"""\
    [Script Info]
    ScriptType: v4.00+
    PlayResX: 1080
    PlayResY: 1920

    [V4+ Styles]
    Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
    {style_line}

    [Events]
    Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
    """)
    lines = [header]
    words = text.replace("\n", " ").split()
    if not words:
        words = [text]

    if style == "karaoke":
        # group into chunks; within each chunk, highlight the current word yellow
        chunks = [words[i:i + wpc] for i in range(0, len(words), wpc)]
        per_chunk = duration / len(chunks)
        t = 0.0
        for chunk in chunks:
            wdur = per_chunk / len(chunk)
            for wi in range(len(chunk)):
                start, end = t + wi * wdur, t + (wi + 1) * wdur
                parts = []
                for j, w in enumerate(chunk):
                    if j == wi:
                        parts.append(r"{\c&H00FFFF&\fscx115\fscy115}" + w + r"{\r}")
                    else:
                        parts.append(w)
                lines.append(f"Dialogue: 0,{_ts(start)},{_ts(end)},Big,,0,0,0,,{' '.join(parts)}")
            t += per_chunk

    elif style == "typewriter":
        # reveal letters progressively, line by line (~8 words per line)
        chunks = [words[i:i + wpc] for i in range(0, len(words), wpc)]
        per_chunk = duration / len(chunks)
        t = 0.0
        for chunk in chunks:
            full = " ".join(chunk)
            steps = max(1, len(full))
            sdur = per_chunk / steps
            for k in range(1, steps + 1):
                start, end = t + (k - 1) * sdur, t + k * sdur
                shown = full[:k].replace("\n", " ").strip()
                if shown:
                    lines.append(f"Dialogue: 0,{_ts(start)},{_ts(end)},Big,,0,0,0,,{shown}")
            t += per_chunk

    else:
        # facts / quotes / boldbox / cinematic -> chunk reveal
        chunks = [" ".join(words[i:i + wpc]) for i in range(0, len(words), wpc)]
        per = duration / len(chunks)
        t = 0.0
        for ch in chunks:
            start, end = t, t + per
            safe = ch.strip()
            if style == "cinematic":
                safe = r"{\fad(300,300)}" + safe   # gentle fade in/out
            elif style == "boldbox":
                safe = r"{\fscx105\fscy105}" + safe  # slight pop
            lines.append(f"Dialogue: 0,{_ts(start)},{_ts(end)},Big,,0,0,0,,{safe}")
            t = end

    Path(out_path).write_text("\n".join(lines), encoding="utf-8")
    return Path(out_path)


# ---------------------------------------------------------------------------
# 3b. BACKGROUND MUSIC  (pick a random royalty-free track, mood-aware)
# ---------------------------------------------------------------------------
def pick_music(mood: str = "") -> Path | None:
    """
    Return a random music file from the music/ folder, or None if empty.
    If `mood` is given, prefer files whose name contains that word
    (e.g. mood="emotional" -> emotional_piano.mp3).
    """
    import random
    tracks = [p for p in MUSIC.iterdir()
              if p.suffix.lower() in (".mp3", ".m4a", ".wav", ".aac")]
    if not tracks:
        return None
    if mood:
        preferred = [p for p in tracks if mood.lower() in p.name.lower()]
        if preferred:
            tracks = preferred
    return random.choice(tracks)


def _ass_escape(text: str) -> str:
    """Escape text for use inside an ASS drawtext/dialogue."""
    return text.replace("\\", "\\\\").replace("{", "(").replace("}", ")")


# Voice pools so reels don't all sound identical. Picked by index/hash for variety.
# Gemini voices are the default now (real-human quality). Edge pools kept as fallback.
VOICE_POOL = {
    "facts":    ["gemini:deep", "gemini:male", "gemini:female", "gemini:bright"],
    "quotes":   ["gemini:warm", "gemini:calm", "gemini:female"],
    "story":    ["gemini:female", "gemini:warm", "gemini:deep"],
    "energetic":["gemini:male", "gemini:bright", "gemini:female"],
    "default":  ["gemini:female", "gemini:male", "gemini:deep", "gemini:warm",
                 "gemini:bright"],
}

# Edge fallback pools (used automatically if Gemini key is missing/over quota)
VOICE_POOL_EDGE = {
    "facts":    ["en-US-GuyNeural", "en-US-EricNeural", "en-GB-RyanNeural"],
    "quotes":   ["en-GB-RyanNeural", "en-US-AriaNeural"],
    "default":  ["en-US-AriaNeural", "en-US-GuyNeural", "en-GB-RyanNeural"],
}


def auto_voice(seed: str, mood: str = "default", use_gemini: bool = True) -> str:
    """
    Pick a voice automatically, varied by the text so reels differ.
    `mood` selects a pool; the seed text rotates within it.
    use_gemini=False -> use Edge fallback pools (no Gemini key / cost-free).
    """
    pools = VOICE_POOL if use_gemini else VOICE_POOL_EDGE
    pool = pools.get(mood, pools["default"])
    idx = sum(ord(c) for c in seed[:40]) % len(pool)
    return pool[idx]


def pick_voice_for_content(script: str, style: str = "", niche: str = "",
                           use_gemini: bool = True) -> str:
    """
    Smart category-aware voice picker. Claude can rely on this to choose a
    fitting voice based on the script's vibe + niche, varied per reel.
    """
    low = (script + " " + niche).lower()
    # decide a mood bucket from content
    if any(w in low for w in ("quote", "believe", "success", "life lesson",
                              "motivat", "dream", "wisdom", "inspire")):
        mood = "quotes"
    elif any(w in low for w in ("scary", "horror", "mystery", "creepy",
                                "story", "legend")):
        mood = "story"
    elif any(w in low for w in ("amazing", "shocking", "insane", "crazy",
                                "top 5", "countdown")) or style == "boldbox":
        mood = "energetic"
    else:
        mood = "facts"
    return auto_voice(script, mood, use_gemini=use_gemini)


def auto_music_choice(seed: str, want_ratio: float = 0.7):
    """
    Decide whether to use music at all (variety) and which mood.
    Returns (use_music: bool, mood: str). ~want_ratio of reels get music.
    """
    h = sum(ord(c) for c in seed[:50])
    use = (h % 10) < int(want_ratio * 10)
    moods = ["", "calm", "emotional", "cinematic", "upbeat"]
    mood = moods[h % len(moods)]
    return use, mood


def build_overlay(duration: float, out_path: Path, hook: str = "",
                  brand: str = "", outro: str = "Follow for more!") -> Path:
    """
    Feature 1 + Feature 4 combined: an overlay .ass that can show
      - a BIG attention HOOK in the top third for the first ~3s, and/or
      - an OUTRO branding line ("Follow for more!" + page name) in the
        last ~3s.
    Any empty arg is skipped.
    """
    hook_style = ("Style: Hook,Arial Black,96,&H0000FFFF,&H00000000,&H00000000,"
                  "1,7,2,8,60,60,180,1")     # yellow, top-center
    # outro UPPER area (align 8 = top-center, pushed down a bit) — sits well
    # above the bottom captions, so the two never overlap.
    outro_style = ("Style: Outro,Arial Black,86,&H00FFFFFF,&H000000FF,&H64000000,"
                   "1,7,3,8,60,60,520,1")    # white w/ red outline, upper-third
    brand_style = ("Style: Brand,Arial,52,&H0000D4F5,&H00000000,&H64000000,"
                   "1,3,1,7,40,40,60,1")     # small gold, TOP-LEFT corner

    header = textwrap.dedent(f"""\
    [Script Info]
    ScriptType: v4.00+
    PlayResX: 1080
    PlayResY: 1920

    [V4+ Styles]
    Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
    {hook_style}
    {outro_style}
    {brand_style}

    [Events]
    Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
    """)
    events = []
    if hook:
        show = min(3.0, max(1.5, duration * 0.25))
        txt = r"{\fad(150,250)}" + _ass_escape(hook.upper())
        events.append(f"Dialogue: 0,{_ts(0)},{_ts(show)},Hook,,0,0,0,,{txt}")
    if brand:
        # small persistent page-name watermark whole reel
        events.append(f"Dialogue: 0,{_ts(0)},{_ts(duration)},Brand,,0,0,0,,"
                      f"{_ass_escape(brand)}")
    if outro:
        start = max(0.0, duration - 3.0)
        txt = r"{\fad(250,150)}" + _ass_escape(outro.upper())
        events.append(f"Dialogue: 0,{_ts(start)},{_ts(duration)},Outro,,0,0,0,,{txt}")
    Path(out_path).write_text(header + "\n".join(events), encoding="utf-8")
    return Path(out_path)


# backwards-compatible alias
def build_hook_overlay(hook: str, duration: float, out_path: Path) -> Path:
    return build_overlay(duration, out_path, hook=hook, outro="")


def make_endcard(out_path: Path, text: str = "Follow for more!",
                 brand: str = "", seconds: float = 2.0,
                 music: Path | None = None) -> Path:
    """
    Build a standalone black end-card clip (1080x1920) showing a big
    'Follow for more!' (+ optional brand) for `seconds`. Optional music bed.
    Returns the clip path. This is concatenated AFTER the main reel so the
    CTA never overlaps the captions.
    """
    out_path = Path(out_path)
    # Render the CTA text via an ASS subtitle file (reliable on Windows,
    # no font-path headaches that drawtext has).
    cta_ass = out_path.with_suffix(".ass")
    main = _ass_escape(text.upper())
    # NOTE: ASS section headers MUST start at column 0 (no indentation) or
    # libass fails to initialise the filter.
    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "PlayResX: 1080\n"
        "PlayResY: 1920\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, "
        "BackColour, Bold, Outline, Shadow, Alignment, MarginL, MarginR, "
        "MarginV, Encoding\n"
        "Style: CTA,Arial Black,90,&H00FFFFFF,&H00000000,&H00000000,1,4,2,5,80,80,80,1\n"
        "Style: BR,Arial,56,&H0000D4F5,&H00000000,&H00000000,1,2,1,2,80,80,200,1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, "
        "Effect, Text\n"
    )
    ev = [f"Dialogue: 0,{_ts(0)},{_ts(seconds)},CTA,,0,0,0,,{{\\fad(300,0)}}{main}"]
    if brand:
        ev.append(f"Dialogue: 0,{_ts(0)},{_ts(seconds)},BR,,0,0,0,,"
                  f"{{\\fad(300,0)}}{_ass_escape(brand)}")
    cta_ass.write_text(header + "\n".join(ev), encoding="utf-8")
    ass_esc = str(cta_ass).replace("\\", "/").replace(":", "\\:")

    inputs = ["-f", "lavfi", "-i",
              f"color=c=black:s=1080x1920:d={seconds:.2f}:r=30"]
    if music and Path(music).exists():
        inputs += ["-stream_loop", "-1", "-i", str(music)]
    else:
        inputs += ["-f", "lavfi", "-i",
                   "anullsrc=channel_layout=stereo:sample_rate=44100"]
    cmd = (["ffmpeg", "-y"] + inputs +
           ["-t", f"{seconds:.2f}",
            "-vf", f"subtitles='{ass_esc}'",
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k",
            "-pix_fmt", "yuv420p", "-r", "30", "-shortest", str(out_path)])
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return out_path


def mix_music_over(video_path: Path, music: Path, out_path: Path,
                   volume: float = 0.18) -> Path:
    """Lay a quiet looped music bed under an existing video's audio."""
    dur = get_audio_duration(video_path)
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-stream_loop", "-1", "-i", str(music),
        "-filter_complex",
        f"[1:a]volume={volume}[bg];"
        f"[0:a][bg]amix=inputs=2:duration=first:dropout_transition=0[a]",
        "-map", "0:v:0", "-map", "[a]",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
        "-t", f"{dur:.2f}", "-shortest",
        str(out_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return Path(out_path)


def concat_clips(clips: list, out_path: Path, transition: str = "") -> Path:
    """
    Join mp4 clips (same size/fps) into one.
    transition="" -> hard cut (fast).
    transition="fade"/"slideleft"/"fadeblack"/... -> smooth xfade between
    scenes (looks far more professional). Audio is crossfaded to match.
    """
    inputs = []
    for c in clips:
        inputs += ["-i", str(c)]
    n = len(clips)

    if not transition or n < 2:
        streams = "".join(f"[{i}:v:0][{i}:a:0]" for i in range(n))
        fc = f"{streams}concat=n={n}:v=1:a=1[v][a]"
    else:
        # build a chained xfade across all clips
        td = 0.4  # transition duration (seconds)
        durs = [get_audio_duration(Path(c)) for c in clips]
        vparts, aparts = [], []
        # video chain
        prev_v = "0:v:0"
        offset = durs[0] - td
        for i in range(1, n):
            out_lbl = f"v{i}"
            vparts.append(
                f"[{prev_v}][{i}:v:0]xfade=transition={transition}:"
                f"duration={td}:offset={offset:.2f}[{out_lbl}]")
            prev_v = out_lbl
            offset += durs[i] - td
        # audio chain (acrossfade)
        prev_a = "0:a:0"
        for i in range(1, n):
            out_lbl = f"a{i}"
            aparts.append(
                f"[{prev_a}][{i}:a:0]acrossfade=d={td}[{out_lbl}]")
            prev_a = out_lbl
        fc = ";".join(vparts + aparts)
        fc += f";[{prev_v}]null[v];[{prev_a}]anull[a]"

    cmd = (["ffmpeg", "-y"] + inputs +
           ["-filter_complex", fc, "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k", "-pix_fmt", "yuv420p", "-r", "30",
            str(out_path)])
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return Path(out_path)


# ---------------------------------------------------------------------------
# 4. VIDEO BUILDER  (FFmpeg: bg video(s) + voice + music + captions -> reel)
# ---------------------------------------------------------------------------
def build_reel(bg_video, voice_mp3: Path, captions_ass: Path,
               out_path: Path, music: Path | None = None,
               music_volume: float = 0.35, hook_ass: Path | None = None) -> Path:
    """
    Compose the final vertical reel.

    bg_video:     a single background path OR a list of paths. If a list is
                  given, they are concatenated (Feature 2: multiple backgrounds
                  switching through the reel).
    music:        optional background music file (mixed under the voice)
    music_volume: 0.0-1.0, music loudness vs voice (default 0.35)
    hook_ass:     optional hook overlay .ass (Feature 1), burned on top
    """
    duration = get_audio_duration(voice_mp3)

    # ---- normalise backgrounds into a single looping/concatenated clip ----
    bgs = bg_video if isinstance(bg_video, (list, tuple)) else [bg_video]
    bgs = [Path(b) for b in bgs if b and Path(b).exists()]
    if not bgs:
        raise RuntimeError("No background video provided")

    if len(bgs) == 1:
        bg_inputs = ["-stream_loop", "-1", "-i", str(bgs[0])]
        bg_label = "0:v:0"
        next_idx = 1
    else:
        # each background gets ~equal share of the duration, scaled+cropped,
        # then concatenated. Loop the result if voice is longer.
        per = duration / len(bgs)
        bg_inputs = []
        for b in bgs:
            bg_inputs += ["-i", str(b)]
        next_idx = len(bgs)

    # captions (and optional hook) burned via subtitles filter
    ass_path = str(captions_ass).replace("\\", "/").replace(":", "\\:")
    sub_chain = f"subtitles='{ass_path}'"
    if hook_ass and Path(hook_ass).exists():
        hook_path = str(hook_ass).replace("\\", "/").replace(":", "\\:")
        sub_chain += f",subtitles='{hook_path}'"

    cmd = ["ffmpeg", "-y"]
    cmd += bg_inputs
    cmd += ["-i", str(voice_mp3)]                 # voice at index next_idx
    voice_idx = next_idx
    music_idx = None
    if music and Path(music).exists():
        cmd += ["-stream_loop", "-1", "-i", str(music)]
        music_idx = voice_idx + 1

    # build filter_complex
    fc = []
    if len(bgs) == 1:
        fc.append(
            f"[0:v:0]scale=1080:1920:force_original_aspect_ratio=increase,"
            f"crop=1080:1920,{sub_chain}[vout]"
        )
    else:
        for i, b in enumerate(bgs):
            fc.append(
                f"[{i}:v:0]scale=1080:1920:force_original_aspect_ratio=increase,"
                f"crop=1080:1920,trim=0:{per:.2f},setpts=PTS-STARTPTS[v{i}]"
            )
        concat_in = "".join(f"[v{i}]" for i in range(len(bgs)))
        fc.append(f"{concat_in}concat=n={len(bgs)}:v=1:a=0[vcat]")
        fc.append(f"[vcat]{sub_chain}[vout]")

    if music_idx is not None:
        fc.append(f"[{music_idx}:a]volume={music_volume}[bg]")
        fc.append(f"[{voice_idx}:a]volume=1.6[vo]")
        fc.append("[vo][bg]amix=inputs=2:duration=first:dropout_transition=0[aout]")
        audio_map = "[aout]"
    else:
        audio_map = f"{voice_idx}:a:0"

    cmd += [
        "-filter_complex", ";".join(fc),
        "-map", "[vout]", "-map", audio_map,
        "-t", f"{duration:.2f}",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        "-pix_fmt", "yuv420p", "-r", "30",
        "-shortest",
        str(out_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return Path(out_path)


# ---------------------------------------------------------------------------
# 5. FACEBOOK AUTO-POST  (Graph API resumable reel upload)
# ---------------------------------------------------------------------------
def post_reel_to_facebook(video_path: Path, caption: str,
                          page_id: str, token: str,
                          scheduled_time: int = 0) -> dict:
    """
    Upload a reel to a Facebook Page using the resumable upload protocol.
    If scheduled_time (future UNIX timestamp) is given, the reel is SCHEDULED
    on Facebook's servers (posts even if your PC is off; 10 min - 75 days).
    Returns the API response dict.
    """
    import requests  # local import so server starts even if not posting

    if not page_id or not token:
        raise RuntimeError("FB_PAGE_ID / FB_PAGE_ACCESS_TOKEN missing in .env")

    base = f"https://graph.facebook.com/v21.0/{page_id}/video_reels"
    size = os.path.getsize(video_path)

    # Step 1: start
    r = requests.post(base, data={
        "upload_phase": "start",
        "access_token": token,
    }, timeout=30)
    r.raise_for_status()
    start = r.json()
    video_id = start["video_id"]
    upload_url = start["upload_url"]

    # Step 2: upload binary
    with open(video_path, "rb") as f:
        up = requests.post(
            upload_url,
            data=f.read(),
            headers={
                "Authorization": f"OAuth {token}",
                "offset": "0",
                "file_size": str(size),
            },
            timeout=300,
        )
    up.raise_for_status()

    # Step 3: finish + publish (or schedule)
    fin_data = {
        "upload_phase": "finish",
        "video_id": video_id,
        "description": caption,
        "access_token": token,
    }
    if scheduled_time:
        fin_data["video_state"] = "SCHEDULED"
        fin_data["scheduled_publish_time"] = str(int(scheduled_time))
    else:
        fin_data["video_state"] = "PUBLISHED"

    fin = requests.post(base, data=fin_data, timeout=60)
    fin.raise_for_status()
    return {"video_id": video_id, "scheduled": bool(scheduled_time),
            "publish": fin.json()}
