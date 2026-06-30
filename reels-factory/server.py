"""
Reels Factory — MCP server.

Lets Claude generate faceless "Did You Know" fact reels and auto-post them
to a Facebook Page. All content is ORIGINAL (Claude script + AI voice +
royalty-free stock footage), so it is safe to monetize.

Tools:
  write_script        -> Claude writes the fact script (no AI call here; Claude
                         itself fills the text when it calls the next tools)
  generate_voiceover  -> English TTS mp3 from script
  fetch_visual        -> download royalty-free stock video for a keyword
  assemble_reel       -> combine voice + visual + captions into a 9:16 mp4
  make_reel           -> ONE-SHOT: script text -> finished reel file
  post_to_facebook    -> upload a finished reel to your Facebook Page
  create_and_post     -> full pipeline: script -> reel -> Facebook
"""
from pathlib import Path
import time

from fastmcp import FastMCP
import helpers
import fb_manager as fb
import finance
import research

mcp = FastMCP("reels-factory")
ENV = helpers.load_env()
PAGES = helpers.load_pages()


def _fb_creds(page: str = ""):
    """
    Resolve (page_id, token) for a page.
    - If `page` matches a nickname in pages.json -> use that page.
    - If `page` is empty and pages.json has entries -> use the FIRST page.
    - Otherwise fall back to single-page .env (FB_PAGE_ID / FB_PAGE_ACCESS_TOKEN).
    """
    if PAGES:
        if page and page in PAGES:
            p = PAGES[page]
            return p.get("page_id", ""), p.get("token", "")
        if not page:
            first = next(iter(PAGES.values()))
            return first.get("page_id", ""), first.get("token", "")
        # named page not found -> error out clearly
        raise RuntimeError(f"Page '{page}' not in pages.json. "
                           f"Available: {', '.join(PAGES.keys())}")
    # single-page mode
    return ENV.get("FB_PAGE_ID", ""), ENV.get("FB_PAGE_ACCESS_TOKEN", "")


def _page_meta(page: str = ""):
    """Return the pages.json dict for a page (for defaults like voice/style)."""
    if PAGES:
        if page and page in PAGES:
            return PAGES[page]
        if not page:
            return next(iter(PAGES.values()))
    return {}


def _stamp() -> str:
    """Unique-ish filename stamp (avoids Date.now restrictions in scripts)."""
    return str(int(time.time() * 1000))


@mcp.tool()
def generate_voiceover(script: str, voice: str = "") -> str:
    """
    Generate an English voiceover mp3 from the given script text.
    Returns the path to the mp3 file.

    script: the spoken text (what the narrator says)
    voice:  optional Edge-TTS voice id; defaults to .env VOICE
    """
    voice = voice or ENV.get("VOICE", "en-US-AriaNeural")
    out = helpers.TEMP / f"voice_{_stamp()}.mp3"
    helpers.make_voice(script, out, voice, gemini_key=ENV.get("GEMINI_API_KEY", ""))
    dur = helpers.get_audio_duration(out)
    return f"OK voiceover saved: {out} ({dur:.1f}s)"


@mcp.tool()
def fetch_visual(keyword: str) -> str:
    """
    Download one royalty-free portrait stock video for a keyword (Pexels).
    Returns the path to the downloaded mp4.

    keyword: search term for the background footage, e.g. "space galaxy"
    """
    out = helpers.TEMP / f"bg_{_stamp()}.mp4"
    helpers.fetch_stock_video(keyword, ENV.get("PEXELS_API_KEY", ""), out)
    return f"OK stock video saved: {out}"


@mcp.tool()
def assemble_reel(script: str, voice_mp3: str, bg_video: str,
                  title: str = "reel") -> str:
    """
    Combine an existing voiceover + background video + auto-captions into a
    finished 9:16 reel mp4. Returns the output path.

    script:    the same text used for the voiceover (used for captions)
    voice_mp3: path from generate_voiceover
    bg_video:  path from fetch_visual
    title:     used in the output filename
    """
    safe = "".join(c for c in title if c.isalnum() or c in "-_")[:40] or "reel"
    voice_path = Path(voice_mp3)
    dur = helpers.get_audio_duration(voice_path)
    ass = helpers.TEMP / f"cap_{_stamp()}.ass"
    helpers.build_captions(script, dur, ass)
    out = helpers.OUTPUT / f"{safe}_{_stamp()}.mp4"
    helpers.build_reel(Path(bg_video), voice_path, ass, out)
    return f"OK reel ready: {out}"


@mcp.tool()
def make_reel(script: str, visual_keyword: str, title: str = "reel",
              voice: str = "auto", style: str = "auto",
              music="auto", music_mood: str = "auto",
              hook: str = "", num_backgrounds: int = 1,
              brand: str = "", outro: str = "Follow for more!",
              music_volume: float = 0.35) -> str:
    """
    ONE-SHOT: turn a script + a visual keyword into a finished reel mp4 with
    voice + stock video(s) + captions + music + hook + branding.
    Returns the final mp4 path.

    script:          narrator text (punchy "Did you know..." fact)
    visual_keyword:  background footage search term, e.g. "ocean deep"
    title:           output filename label
    voice:           Edge-TTS voice id, OR "auto" to let the tool pick a
                     fitting voice that VARIES per reel (so they don't all
                     sound the same). Good ones: en-US-GuyNeural,
                     en-GB-RyanNeural, en-US-AriaNeural
    style:           caption style -> facts | quotes | karaoke | boldbox
                     | typewriter | cinematic | auto
    music:           True/False to force, or "auto" to let the tool decide
                     per reel (some reels get music, some don't = variety).
    music_mood:      "auto" (varied), or a word like calm/emotional/cinematic
    music_volume:    0.0-1.0 loudness of music vs voice (default 0.35)
    hook:            Feature 1 - big attention text for first ~3s
                     (e.g. "99% DON'T KNOW THIS"). Empty = no hook.
    num_backgrounds: Feature 2 - how many different clips to switch through
                     (1 = single bg). 2-4 looks more dynamic.
    brand:           Feature 4 - small page-name watermark whole reel
                     (e.g. "@SpaceFactsHub"). Empty = none.
    outro:           Feature 4 - end-screen CTA in last 3s
                     (default "Follow for more!"). Empty = none.

    TIP: pass voice="auto", style="auto", music="auto" and the tool will
    choose sensible, VARIED settings so a batch of reels feels diverse.
    """
    seed = script  # used to vary auto choices per reel
    has_gemini = bool(ENV.get("GEMINI_API_KEY", ""))

    # --- AUTO style (decide first; voice picker uses it) ---
    if style == "auto":
        low = script.lower()
        if any(w in low for w in ("believe", "success", "life", "never give",
                                  "dream", "yourself")):
            style = "cinematic"
        elif len(script.split()) < 25:
            style = "boldbox"
        else:
            style = "karaoke"

    # --- AUTO voice (category-aware; Claude/tool picks best, varied per reel) ---
    if voice == "auto" or not voice:
        if voice == "auto":
            # smart pick based on the content + style; Gemini if available
            voice = helpers.pick_voice_for_content(
                script, style=style, use_gemini=has_gemini)
        else:
            voice = ENV.get("VOICE", "gemini:female" if has_gemini
                            else "en-US-AriaNeural")

    # --- AUTO music ---
    if isinstance(music, str) and music.lower() == "auto":
        use_music, auto_mood = helpers.auto_music_choice(seed)
        music = use_music
        if music_mood in ("", "auto"):
            music_mood = auto_mood
    elif music_mood == "auto":
        music_mood = helpers.auto_music_choice(seed)[1]

    stamp = _stamp()
    voice_path = helpers.TEMP / f"voice_{stamp}.mp3"
    try:
        helpers.make_voice(script, voice_path, voice,
                           gemini_key=ENV.get("GEMINI_API_KEY", ""))
    except Exception as e:
        # Gemini failed (quota/network)? fall back to a free Edge voice so the
        # reel still gets made instead of erroring out.
        if voice.startswith("gemini:"):
            fb_voice = helpers.auto_voice(seed, "facts", use_gemini=False)
            helpers.make_voice(script, voice_path, fb_voice)
            voice = f"{fb_voice} (gemini fell back)"
        else:
            raise
    # add a short silent tail so the LAST WORD is never clipped and the
    # captions/end-card don't overlap the final word.
    helpers.pad_audio_tail(voice_path, seconds=0.8)
    dur = helpers.get_audio_duration(voice_path)

    # backgrounds (1 or many)
    if num_backgrounds and num_backgrounds > 1:
        bgs = helpers.fetch_multiple_videos(
            visual_keyword, ENV.get("PEXELS_API_KEY", ""),
            num_backgrounds, helpers.TEMP, stamp)
    else:
        bg = helpers.TEMP / f"bg_{stamp}.mp4"
        helpers.fetch_stock_video(visual_keyword, ENV.get("PEXELS_API_KEY", ""), bg)
        bgs = [bg]

    ass = helpers.TEMP / f"cap_{stamp}.ass"
    helpers.build_captions(script, dur, ass, style=style)

    # overlay now only carries the HOOK + brand watermark.
    # The OUTRO is rendered as a separate black end-card (no caption overlap).
    overlay = None
    if hook or brand:
        overlay = helpers.TEMP / f"ovl_{stamp}.ass"
        helpers.build_overlay(dur, overlay, hook=hook, brand=brand, outro="")

    track = helpers.pick_music(music_mood) if music else None

    safe = "".join(c for c in title if c.isalnum() or c in "-_")[:40] or "reel"
    main_clip = helpers.TEMP / f"main_{stamp}.mp4"
    helpers.build_reel(bgs, voice_path, ass, main_clip, music=track,
                       music_volume=music_volume, hook_ass=overlay)

    out = helpers.OUTPUT / f"{safe}_{stamp}.mp4"
    if outro:
        # black end-card with the CTA, appended after the reel (2s)
        endcard = helpers.TEMP / f"end_{stamp}.mp4"
        helpers.make_endcard(endcard, text=outro, brand=brand,
                             seconds=2.0, music=track)
        helpers.concat_clips([main_clip, endcard], out)
    else:
        main_clip.replace(out)

    # generate a thumbnail for preview
    try:
        thumb = helpers.make_thumbnail(out, at_seconds=min(1.0, dur / 2))
        thumb_note = f"\nThumbnail: {thumb}"
    except Exception:
        thumb_note = ""

    note = f"voice={voice} | style={style} | bgs={len(bgs)}"
    note += f" | music={track.name}" if track else " | no-music"
    note += " | +hook" if hook else ""
    note += " | +endcard" if outro else ""
    return (f"REEL READY (NOT posted yet — review it first):\n"
            f"  File: {out}\n"
            f"  Length: {dur + (2 if outro else 0):.1f}s | {note}{thumb_note}\n"
            f"  -> To publish: post_existing_reel(\"{out.name}\", page=\"<nick>\")\n"
            f"  -> Open the File path above to watch it before posting.")


@mcp.tool()
def make_quote_reel(quote: str, author: str = "", visual_keyword: str = "nature cinematic",
                    title: str = "quote", voice: str = "", music_mood: str = "emotional") -> str:
    """
    Make a cinematic QUOTE reel: big centered text + emotional music.
    Returns the final mp4 path.

    quote:          the quote text (the narrator reads this)
    author:         optional author name, appended as "- Name"
    visual_keyword: background footage, e.g. "mountain sunrise", "rain window"
    title:          output filename label
    voice:          optional voice id
    music_mood:     preferred music mood (default "emotional")
    """
    spoken = quote.strip()
    if author:
        spoken = f"{spoken} ... {author}"
    return make_reel(spoken, visual_keyword, title, voice,
                     style="quotes", music=True, music_mood=music_mood)


@mcp.tool()
def make_finance_reel(script: str, visual: str, data: dict,
                      title: str = "finance", voice: str = "",
                      music: bool = True, outro: str = "Follow for more!") -> str:
    """
    Make a FINANCE reel with an ORIGINAL animated data-visual as the
    background (no stock, no face — 100% your own, monetization-safe).
    Returns the reel path (NOT posted; review then post_existing_reel).

    AUTO-GRAPHICS: You (Claude) read the user's topic, WRITE the script, then
    CHOOSE the visual that best fits what the script says and fill `data` with
    sensible (realistic but made-up) numbers — the visual matches the script.

    script:  narrator text explaining the numbers (Gemini voice reads it).
    visual:  pick the one that matches the script's point:
      "counter"      single number growing  (savings/debt/interest)
      "compound"     compound-growth curve with year labels (BEST for
                     "what $X becomes over time" — most shareable)
      "line"         a custom growth line from your own values
      "bar"          compare a few values as vertical bars
      "race"         dramatic horizontal bar race (e.g. Savings 0.5% vs Index 8%)
      "before_after" split screen Without vs With (two numbers)
      "progress"     a % progress bar (e.g. "Emergency fund 40%")
      "pie"          budget pie that builds (e.g. 50/30/20)
      "stat"         a few key stat numbers popping in
      "myth"         MYTH -> FACT flip card (text, no chart)
      "mistake"      a costly mistake reveal ("-$2,400/year")
    data:    numbers for the chosen visual:
      counter:      {"start":1000,"end":1250,"prefix":"$","label":"SAVINGS"}
      compound:     {"principal":0,"monthly":100,"rate":0.08,"years":30}
      line:         {"values":[100,150,200,280,400],"title":"Growth"}
      bar:          {"labels":["Jan","Feb","Mar"],"values":[500,800,1200],"title":"Savings"}
      race:         {"items":[["Savings 0.5%",1025],["Index 8%",2159]],"title":"$1000 in 10y"}
      before_after: {"left_label":"No budget","left_value":"$0",
                     "right_label":"Budgeting","right_value":"$8,200","title":"5 Years"}
      progress:     {"label":"Emergency Fund","percent":40,"sub":"$2,000 / $5,000"}
      pie:          {"slices":[["Needs",50],["Wants",30],["Savings",20]],"title":"50/30/20"}
      stat:         {"stats":[["+25%","Returns"],["$12k","Saved"]],"title":"Results"}
      myth:         {"myth":"Closing cards helps your score","fact":"It hurts it"}
      mistake:      {"mistake":"Only paying card minimums","cost":2400,"period":"/year"}
    title:   filename label
    voice:   voice id (empty = Gemini deep, fits finance)
    music:   add background music
    outro:   end-card CTA
    """
    stamp = _stamp()
    # 1) voice first so the visual can match its length
    voice = voice or "gemini:deep"
    vpath = helpers.TEMP / f"voice_{stamp}.mp3"
    try:
        helpers.make_voice(script, vpath, voice,
                           gemini_key=ENV.get("GEMINI_API_KEY", ""))
    except Exception:
        helpers.make_voice(script, vpath, "en-US-GuyNeural")
        voice = "en-US-GuyNeural (fallback)"
    helpers.pad_audio_tail(vpath, seconds=0.8)
    dur = helpers.get_audio_duration(vpath)

    # 2) build the animated visual to match the voice duration
    vis = helpers.TEMP / f"fin_{stamp}.mp4"
    if visual == "counter":
        finance.number_counter(data["start"], data["end"], vis, duration=dur,
                               prefix=data.get("prefix", "$"),
                               suffix=data.get("suffix", ""),
                               label=data.get("label", ""))
    elif visual == "bar":
        finance.bar_chart(data["labels"], data["values"], vis, duration=dur,
                          title=data.get("title", ""),
                          prefix=data.get("prefix", "$"))
    elif visual == "line":
        finance.line_graph(data["values"], vis, duration=dur,
                           title=data.get("title", ""),
                           prefix=data.get("prefix", "$"))
    elif visual == "stat":
        finance.stat_cards([tuple(s) for s in data["stats"]], vis, duration=dur,
                           title=data.get("title", ""))
    elif visual == "compound":
        finance.compound_curve(data["principal"], data["monthly"], data["rate"],
                               data["years"], vis, duration=dur,
                               prefix=data.get("prefix", "$"))
    elif visual == "before_after":
        finance.before_after(data["left_label"], data["left_value"],
                              data["right_label"], data["right_value"], vis,
                              duration=dur, title=data.get("title", ""))
    elif visual == "race":
        finance.comparison_race([tuple(x) for x in data["items"]], vis,
                                duration=dur, title=data.get("title", ""),
                                prefix=data.get("prefix", "$"))
    elif visual == "progress":
        finance.progress_bar(data["label"], data["percent"], vis, duration=dur,
                             sub=data.get("sub", ""))
    elif visual == "pie":
        finance.pie_build([tuple(s) for s in data["slices"]], vis, duration=dur,
                          title=data.get("title", ""))
    elif visual == "myth":
        finance.myth_vs_fact(data["myth"], data["fact"], vis, duration=dur)
    elif visual == "mistake":
        finance.mistake_cost(data["mistake"], data["cost"], vis, duration=dur,
                             prefix=data.get("prefix", "$"),
                             period=data.get("period", "/year"))
    else:
        return ("Unknown visual. Use: counter | bar | line | stat | compound | "
                "before_after | race | progress | pie | myth | mistake")

    # 3) captions + end-card, assemble (visual is the background)
    ass = helpers.TEMP / f"cap_{stamp}.ass"
    helpers.build_captions(script, dur, ass, style="facts")
    track = helpers.pick_music("calm") if music else None
    safe = "".join(c for c in title if c.isalnum() or c in "-_")[:40] or "finance"
    main_clip = helpers.TEMP / f"main_{stamp}.mp4"
    helpers.build_reel([vis], vpath, ass, main_clip, music=track,
                       music_volume=0.25)
    out = helpers.OUTPUT / f"{safe}_{stamp}.mp4"
    if outro:
        endcard = helpers.TEMP / f"end_{stamp}.mp4"
        helpers.make_endcard(endcard, text=outro, brand="", seconds=2.0, music=track)
        helpers.concat_clips([main_clip, endcard], out)
    else:
        main_clip.replace(out)
    try:
        helpers.make_thumbnail(out, at_seconds=min(1.0, dur / 2))
    except Exception:
        pass
    return (f"FINANCE REEL READY (NOT posted — review first):\n"
            f"  File: {out}\n  visual={visual} | voice={voice} | {dur+2:.1f}s\n"
            f"  -> To publish: post_existing_reel(\"{out.name}\", page=\"<nick>\")")


@mcp.tool()
def make_finance_scenes(scenes: list, title: str = "finance", voice: str = "",
                        music: bool = True, brand: str = "",
                        outro: str = "Follow for more!") -> str:
    """
    SCENE-BASED finance reel: the background CHANGES with the script. Each
    scene has its own narration + its own visual (a chart OR a stock clip),
    and they play in sequence — so a $150/mo -> 8% -> curve -> $27k story
    shows a DIFFERENT visual for each point, in sync with the voice.

    scenes: an ordered list of dicts. Each scene:
      {
        "say":   "<what the narrator says in THIS scene>",   (required)
        "kind":  "chart" | "stock",                          (required)
        # if kind == "chart":
        "visual": "counter|compound|line|bar|race|before_after|progress|pie|stat|myth|mistake|text",
        "data":   { ...numbers for that visual (see make_finance_reel)... },
        # if kind == "stock":
        "keyword": "<stock footage search, e.g. 'money counting'>"
      }
    title:  filename label
    voice:  voice id (empty = Gemini deep). Used for ALL scenes (consistent).
    music:  background music under the whole reel
    brand:  small page-name watermark on every scene
    outro:  end-card CTA

    Example scenes:
      [{"say":"Invest just 150 dollars a month.","kind":"chart",
        "visual":"counter","data":{"start":0,"end":150,"label":"PER MONTH"}},
       {"say":"At an 8 percent return, watch it grow.","kind":"stock",
        "keyword":"stock market chart"},
       {"say":"After 30 years you have over 200 thousand dollars.","kind":"chart",
        "visual":"compound","data":{"principal":0,"monthly":150,"rate":0.08,"years":30}}]
    """
    voice = voice or "gemini:deep"
    gkey = ENV.get("GEMINI_API_KEY", "")
    stamp = _stamp()
    clips = []
    for idx, sc in enumerate(scenes):
        say = sc.get("say", "").strip()
        if not say:
            continue
        # 1) voice for this scene
        vp = helpers.TEMP / f"sc_{stamp}_{idx}.mp3"
        try:
            helpers.make_voice(say, vp, voice, gemini_key=gkey)
        except Exception:
            helpers.make_voice(say, vp, "en-US-GuyNeural")
        helpers.pad_audio_tail(vp, seconds=0.6)
        sdur = helpers.get_audio_duration(vp)

        # 2) visual for this scene (chart or stock)
        bg = helpers.TEMP / f"scbg_{stamp}_{idx}.mp4"
        if sc.get("kind") == "stock":
            helpers.fetch_stock_video(sc.get("keyword", "money"),
                                      ENV.get("PEXELS_API_KEY", ""), bg)
        else:
            finance.render_visual(sc.get("visual", "text"),
                                  sc.get("data", {"text": say}), bg, sdur)

        # 3) captions + overlay (brand) for this scene, assemble
        ass = helpers.TEMP / f"sccap_{stamp}_{idx}.ass"
        helpers.build_captions(say, sdur, ass, style="facts")
        ovl = None
        if brand:
            ovl = helpers.TEMP / f"scovl_{stamp}_{idx}.ass"
            helpers.build_overlay(sdur, ovl, hook="", brand=brand, outro="")
        clip = helpers.TEMP / f"scene_{stamp}_{idx}.mp4"
        helpers.build_reel([bg], vp, ass, clip, music=None, hook_ass=ovl)
        clips.append(clip)

    if not clips:
        return "No valid scenes given."

    # add end-card
    if outro:
        endcard = helpers.TEMP / f"scend_{stamp}.mp4"
        helpers.make_endcard(endcard, text=outro, brand=brand, seconds=2.0)
        clips.append(endcard)

    # join all scenes with a smooth crossfade between them
    safe = "".join(c for c in title if c.isalnum() or c in "-_")[:40] or "finance"
    joined = helpers.TEMP / f"joined_{stamp}.mp4"
    try:
        helpers.concat_clips(clips, joined, transition="fade")
    except Exception:
        # fall back to hard cut if xfade fails for any clip combo
        helpers.concat_clips(clips, joined)

    # optional music bed over the whole thing
    out = helpers.OUTPUT / f"{safe}_{stamp}.mp4"
    track = helpers.pick_music("calm") if music else None
    if track:
        helpers.mix_music_over(joined, track, out, volume=0.18)
    else:
        joined.replace(out)
    try:
        helpers.make_thumbnail(out, at_seconds=1.0)
    except Exception:
        pass
    total = helpers.get_audio_duration(out)
    return (f"SCENE FINANCE REEL READY (NOT posted — review first):\n"
            f"  File: {out}\n  scenes={len(scenes)} | voice={voice} | {total:.1f}s\n"
            f"  -> To publish: post_existing_reel(\"{out.name}\", page=\"<nick>\")")


@mcp.tool()
def generate_caption(script: str, niche: str = "facts", topic: str = "") -> str:
    """
    Feature 3: build a ready-to-paste Facebook caption (hook line + CTA +
    trending hashtags) from the script. Returns the caption text.

    script: the reel narration
    niche:  facts | quotes | space | science | history (picks hashtag set)
    topic:  optional extra topic, added as a #hashtag (e.g. "ocean")
    """
    return helpers.build_caption(script, niche=niche, topic=topic)


# ===========================================================================
# RESEARCH TOOLS — find what's trending / viral so Claude can write better
# hooks and pick winning topics. (FB/Insta can't be reliably scraped; these
# sources reveal the same demand signals legally.)
# ===========================================================================
@mcp.tool()
def research_topics(seed: str) -> str:
    """
    Mine real content angles people search for (Google autocomplete).
    Great for finding reel topics + the exact wording of hooks.
    seed: a niche phrase, e.g. "how to save money", "investing for beginners".
    """
    angles = research.expand_topic(seed)
    if not angles:
        return f"No suggestions found for '{seed}'."
    return f"Real search angles for '{seed}' ({len(angles)}):\n" + \
        "\n".join(f"  - {a}" for a in angles[:30])


@mcp.tool()
def research_reddit(subreddit: str = "personalfinance", period: str = "week",
                    limit: int = 15) -> str:
    """
    What's trending/most-upvoted in a finance subreddit — real questions and
    pain points you can turn into reels.
    subreddit: personalfinance | investing | financialindependence |
               FIRE | stocks | povertyfinance | frugal
    period: day | week | month | year
    """
    posts = research.reddit_top(subreddit, period, limit)
    if posts and "error" in posts[0]:
        return f"Reddit error: {posts[0]['error']} (try again in a moment)"
    return f"Top r/{subreddit} ({period}):\n" + \
        "\n".join(f"  - {p['title']}" for p in posts)


@mcp.tool()
def research_youtube(query: str, order: str = "viewCount", limit: int = 15) -> str:
    """
    Top YouTube videos for a query (official API) — see what's getting views,
    their titles (hooks) and channels. Needs YOUTUBE_API_KEY in .env.
    order: viewCount | relevance | date
    """
    key = ENV.get("YOUTUBE_API_KEY", "")
    vids = research.youtube_api_search(query, key, limit=limit, order=order)
    if vids and "error" in vids[0]:
        return (f"YouTube error: {vids[0]['error']}\n"
                "Get a free key at console.cloud.google.com -> YouTube Data API v3, "
                "then add YOUTUBE_API_KEY to .env.")
    return f"Top YouTube for '{query}' ({order}):\n" + \
        "\n".join(f"  - {v['title']}  [{v['channel']}]" for v in vids)


@mcp.tool()
def research_read_url(url: str) -> str:
    """
    Fetch readable text from any URL (an article, a competitor's blog, a
    transcript page). Claude can then analyse the hooks/structure.
    """
    try:
        return research.page_text(url, max_chars=6000)
    except Exception as e:
        return f"Could not fetch {url}: {e}"


@mcp.tool()
def make_batch(items: list, default_style: str = "facts",
               voice: str = "", num_backgrounds: int = 1,
               brand: str = "", outro: str = "Follow for more!") -> str:
    """
    Feature 5: make MANY reels in one call. Returns a summary of paths.

    items: a list of dicts, each describing one reel. Per-item keys:
           script   (required) - narration text
           keyword  (required) - background search term
           title    (optional) - filename label
           style    (optional) - overrides default_style
           hook     (optional) - big hook text for first 3s
           music_mood (optional)
    default_style:   style used when an item doesn't set its own
    voice:           voice id for all reels
    num_backgrounds: clips per reel (applies to all)
    brand / outro:   branding applied to all reels

    Example items:
      [{"script":"Did you know octopuses have three hearts.",
        "keyword":"ocean","hook":"99% DON'T KNOW THIS","title":"octopus"},
       {"script":"The sun is 400 times bigger than the moon.",
        "keyword":"space sun","title":"sun"}]
    """
    results = []
    for i, it in enumerate(items):
        try:
            script = it["script"]
            keyword = it.get("keyword", "nature")
            title = it.get("title", f"reel{i+1}")
            style = it.get("style", default_style)
            hook = it.get("hook", "")
            mood = it.get("music_mood", "")
            r = make_reel(script, keyword, title=title, voice=voice,
                          style=style, music=True, music_mood=mood,
                          hook=hook, num_backgrounds=num_backgrounds,
                          brand=brand, outro=outro)
            results.append(f"[{i+1}] {r}")
        except Exception as e:
            results.append(f"[{i+1}] FAILED: {e}")
    ok = sum(1 for r in results if "OK reel ready" in r)
    return f"BATCH DONE: {ok}/{len(items)} reels\n" + "\n".join(results)


@mcp.tool()
def schedule_reels(items: list, page: str = "", start_unix: int = 0,
                   per_day: int = 1, hour: int = 9, gap_minutes: int = 180,
                   num_backgrounds: int = 1, brand: str = "",
                   outro: str = "Follow for more!") -> str:
    """
    Make MANY reels and SCHEDULE them on Facebook across several days.
    Reels post on FB's servers — your PC does NOT need to be on at post time.

    items:       list of dicts (same as make_batch): script, keyword, title,
                 style, hook, music_mood, caption (optional).
    page:        page nickname from pages.json (e.g. "cats").
    start_unix:  UNIX timestamp for the FIRST post (e.g. tomorrow 9 AM).
                 If 0, Claude must compute it (no Date.now in this tool).
    per_day:     how many reels to post each day (e.g. 2).
    hour:        hour-of-day base (informational; spacing uses gap_minutes).
    gap_minutes: minutes between reels on the same day (default 180 = 3h).
    num_backgrounds / brand / outro: applied to all reels.

    Scheduling math: reel index i -> day = i // per_day, slot = i % per_day.
    post_time = start_unix + day*86400 + slot*gap_minutes*60.

    Example (10 reels, 2/day for 5 days starting tomorrow 9 AM):
      schedule_reels(items=[...10 dicts...], page="cats",
                     start_unix=<tomorrow 9am>, per_day=2, gap_minutes=240)
    """
    if not start_unix:
        return ("start_unix is required (future UNIX timestamp for first post). "
                "Claude: compute it from the user's desired date/time and pass it.")
    results = []
    for i, it in enumerate(items):
        try:
            day = i // max(1, per_day)
            slot = i % max(1, per_day)
            post_time = int(start_unix) + day * 86400 + slot * gap_minutes * 60

            script = it["script"]
            keyword = it.get("keyword", "nature")
            title = it.get("title", f"sched{i+1}")
            style = it.get("style", "auto")
            hook = it.get("hook", "")
            mood = it.get("music_mood", "auto")
            caption = it.get("caption") or helpers.build_caption(
                script, niche=it.get("niche", "facts"), topic=it.get("topic", ""))

            made = make_reel(script, keyword, title=title, style=style,
                             music="auto", music_mood=mood, hook=hook,
                             num_backgrounds=num_backgrounds, brand=brand,
                             outro=outro)
            path = made.split("OK reel ready:", 1)[1].split("(")[0].strip()

            pid, tok = _fb_creds(page)
            res = helpers.post_reel_to_facebook(Path(path), caption, pid, tok,
                                                scheduled_time=post_time)
            results.append(f"[{i+1}] day{day+1} slot{slot+1} @ {post_time} "
                           f"-> scheduled id={res['video_id']}")
        except Exception as e:
            results.append(f"[{i+1}] FAILED: {e}")
    ok = sum(1 for r in results if "scheduled id=" in r)
    return (f"SCHEDULE DONE: {ok}/{len(items)} reels scheduled on '{page or 'default'}'\n"
            + "\n".join(results))


@mcp.tool()
def post_to_facebook(video_path: str, caption: str, page: str = "",
                     scheduled_time: int = 0) -> str:
    """
    Upload a finished reel mp4 to a Facebook Page — publish now OR schedule.

    video_path:     path to the .mp4 (e.g. from make_reel)
    caption:        post caption text incl. hashtags
    page:           page nickname from pages.json (e.g. "cats", "facts").
    scheduled_time: future UNIX timestamp to SCHEDULE on FB servers
                    (posts even if PC is off). 0 = post now.
                    Range: 10 min to 75 days ahead.
    """
    pid, tok = _fb_creds(page)
    res = helpers.post_reel_to_facebook(Path(video_path), caption, pid, tok,
                                        scheduled_time=scheduled_time)
    when = "scheduled" if scheduled_time else "posted"
    return f"OK {when} to '{page or 'default'}'. video_id={res['video_id']}"


@mcp.tool()
def list_pending_reels(limit: int = 15) -> str:
    """
    Show reels that have been MADE but not yet posted (the output/ folder).
    Use this for the 2-step flow: make -> review -> post.
    Returns each reel's filename, size, and thumbnail path.
    """
    files = sorted(helpers.OUTPUT.glob("*.mp4"),
                   key=lambda p: p.stat().st_mtime, reverse=True)[:limit]
    if not files:
        return "No reels in output/ yet. Make one with make_reel first."
    lines = ["Reels ready to review (newest first):"]
    for f in files:
        thumb = f.with_suffix(".jpg")
        size = f.stat().st_size // 1024
        lines.append(f"  {f.name}  ({size} KB)"
                     + (f"  thumb: {thumb.name}" if thumb.exists() else ""))
    lines.append("\nTo publish one: post_existing_reel(\"<filename>\", page=\"<nick>\", caption=\"...\")")
    return "\n".join(lines)


@mcp.tool()
def post_existing_reel(filename: str, page: str = "", caption: str = "",
                       scheduled_time: int = 0) -> str:
    """
    Publish (or schedule) a reel that was ALREADY made (2-step flow:
    make_reel first to preview, then this to post once you're happy).

    filename:       the reel's file name from output/ (e.g. "cats_123.mp4")
                    or a full path. Use list_pending_reels to see options.
    page:           page nickname from pages.json (e.g. "cats").
    caption:        FB caption; if empty, a simple default is used.
    scheduled_time: future UNIX timestamp to schedule (0 = post now).
    """
    path = Path(filename)
    if not path.is_absolute():
        path = helpers.OUTPUT / filename
    if not path.exists():
        return f"Not found: {path}. Run list_pending_reels to see available reels."
    if not caption:
        caption = "Follow for more! 🔥"
    pid, tok = _fb_creds(page)
    res = helpers.post_reel_to_facebook(path, caption, pid, tok,
                                        scheduled_time=scheduled_time)
    when = "scheduled" if scheduled_time else "posted"
    return f"OK {when} '{path.name}' to '{page or 'default'}'. video_id={res['video_id']}"


@mcp.tool()
def fb_list_pages() -> str:
    """List the pages configured in pages.json (nicknames you can post to)."""
    if not PAGES:
        return ("No pages.json found — running in single-page mode (.env). "
                "Copy pages.example.json to pages.json to manage multiple pages.")
    lines = ["Configured pages:"]
    for nick, p in PAGES.items():
        lines.append(f"  {nick}: id={p.get('page_id','?')} "
                     f"niche={p.get('niche','-')} style={p.get('default_style','-')}")
    return "\n".join(lines)


# ===========================================================================
# FACEBOOK PAGE MANAGEMENT TOOLS
# ===========================================================================
@mcp.tool()
def fb_add_page(nickname: str, page_id: str, token: str, niche: str = "",
                default_voice: str = "en-US-AriaNeural",
                default_style: str = "facts") -> str:
    """
    Add (or update) a page in pages.json from chat — no manual JSON editing.

    nickname:      short name you'll use in chat (e.g. "cats", "facts")
    page_id:       the Facebook Page ID
    token:         the Page access token (long-lived recommended)
    niche:         topic of the page (used for hashtags)
    default_voice: default Edge-TTS voice for this page
    default_style: default caption style for this page
    """
    PAGES[nickname] = {
        "page_id": page_id, "token": token,
        "niche": niche or nickname,
        "default_voice": default_voice, "default_style": default_style,
    }
    helpers.save_pages(PAGES)
    return (f"OK added page '{nickname}' (id {page_id}). "
            f"Total pages: {len(PAGES)} -> {', '.join(PAGES.keys())}")


@mcp.tool()
def fb_import_pages_from_token(token: str, niche_map: dict = None) -> str:
    """
    ONE-SHOT setup: take ONE token (user or page token) and auto-add EVERY
    page it manages into pages.json, each with its own page token.
    The nickname is derived from the page name (lowercased, spaces removed).

    token:     a Facebook token that can list your pages
    niche_map: optional {page_name: niche} to tag niches; otherwise niche = nickname
    """
    info = fb.verify_token(token)
    pages = info.get("pages", [])
    if not pages:
        return "No pages found for this token. Make sure it has pages_show_list."
    niche_map = niche_map or {}
    added = []
    for p in pages:
        name = p.get("name", "page")
        nick = "".join(ch for ch in name.lower() if ch.isalnum()) or f"page{len(PAGES)}"
        PAGES[nick] = {
            "page_id": p.get("id", ""),
            "token": p.get("access_token", ""),
            "niche": niche_map.get(name, nick),
            "default_voice": "en-US-AriaNeural",
            "default_style": "facts",
        }
        added.append(f"{nick} ({name})")
    helpers.save_pages(PAGES)
    return (f"OK imported {len(added)} page(s): {', '.join(added)}\n"
            f"Use these nicknames in chat to post to each page.")


@mcp.tool()
def fb_verify_token(user_or_page_token: str = "") -> str:
    """
    Check a Facebook token and list the Pages it can manage (with their IDs
    and page tokens). Run this FIRST during setup to find your Page ID + token.
    If no token is passed, uses FB_PAGE_ACCESS_TOKEN from .env.
    """
    token = user_or_page_token or ENV.get("FB_PAGE_ACCESS_TOKEN", "")
    if not token:
        return "No token provided and FB_PAGE_ACCESS_TOKEN is empty in .env"
    info = fb.verify_token(token)
    lines = [f"User: {info['user'].get('name')} (id {info['user'].get('id')})",
             f"Managed pages: {len(info['pages'])}"]
    for p in info["pages"]:
        lines.append(f"  - {p.get('name')} | PAGE_ID={p.get('id')} | "
                     f"page_token={p.get('access_token','')[:25]}...")
    return "\n".join(lines)


@mcp.tool()
def fb_insights(period: str = "day", page: str = "") -> str:
    """
    Page analytics: impressions, reach, engagement, fans, views.
    period: day | week | days_28
    page:   page nickname from pages.json (empty = default)
    """
    pid, tok = _fb_creds(page)
    data = fb.page_insights(pid, tok, period=period)
    return "Page insights (" + period + "):\n" + "\n".join(
        f"  {k}: {v}" for k, v in data.items())


@mcp.tool()
def fb_top_posts(limit: int = 10, page: str = "") -> str:
    """Recent posts with reactions/comments/shares — spot what's working."""
    pid, tok = _fb_creds(page)
    rows = fb.top_posts(pid, tok, limit=limit)
    out = []
    for r in rows:
        out.append(f"❤{r['reactions']} 💬{r['comments']} 🔁{r['shares']} | "
                   f"{r['message']!r} | {r['url']}")
    return "\n".join(out) or "No posts yet"


@mcp.tool()
def fb_schedule_post(message: str, when_unix: int, link: str = "",
                     page: str = "") -> str:
    """
    Schedule a TEXT post for a future time.
    when_unix: future UNIX timestamp (10 min to 75 days ahead).
    page:      page nickname from pages.json (empty = default)
    For scheduling a REEL, post it manually at the time or use a cron job.
    """
    pid, tok = _fb_creds(page)
    res = fb.publish_text(message, pid, tok, link=link, scheduled_time=when_unix)
    return f"OK scheduled. post_id={res.get('id')}"


@mcp.tool()
def fb_post_text(message: str, link: str = "", page: str = "") -> str:
    """Publish a plain text (optionally with a link) post right now."""
    pid, tok = _fb_creds(page)
    res = fb.publish_text(message, pid, tok, link=link)
    return f"OK posted. post_id={res.get('id')}"


@mcp.tool()
def fb_get_page_info(page: str = "") -> str:
    """Read current page info (name, about, description, followers, etc.)."""
    pid, tok = _fb_creds(page)
    info = fb.get_page_info(pid, tok)
    return "\n".join(f"{k}: {v}" for k, v in info.items())


@mcp.tool()
def fb_edit_page(about: str = "", description: str = "", website: str = "",
                 phone: str = "", general_info: str = "", page: str = "") -> str:
    """
    Edit page info. Pass only the fields you want to change.
    (about, description, website, phone, general_info)
    page: page nickname from pages.json (empty = default)
    """
    pid, tok = _fb_creds(page)
    res = fb.update_page_info(pid, tok, about=about, description=description,
                              website=website, phone=phone,
                              general_info=general_info)
    return f"OK page updated: {res}"


@mcp.tool()
def fb_list_posts(limit: int = 25, page: str = "") -> str:
    """List recent posts with their IDs (use ID to delete or read comments)."""
    pid, tok = _fb_creds(page)
    posts = fb.list_posts(pid, tok, limit=limit)
    return "\n".join(
        f"{p.get('id')} | {(p.get('message') or '')[:60]!r} | {p.get('created_time')}"
        for p in posts) or "No posts"


@mcp.tool()
def fb_delete_post(post_id: str, page: str = "") -> str:
    """Delete a post by its ID."""
    _, tok = _fb_creds(page)
    fb.delete_post(post_id, tok)
    return f"OK deleted {post_id}"


@mcp.tool()
def fb_get_comments(post_id: str, limit: int = 50, page: str = "") -> str:
    """Read comments on a post (with commenter name + comment ID)."""
    _, tok = _fb_creds(page)
    comments = fb.get_comments(post_id, tok, limit=limit)
    return "\n".join(
        f"{c.get('id')} | {c.get('from',{}).get('name','?')}: {c.get('message')}"
        for c in comments) or "No comments"


@mcp.tool()
def fb_reply_comment(comment_id: str, message: str, page: str = "") -> str:
    """Reply to a single comment."""
    _, tok = _fb_creds(page)
    res = fb.reply_to_comment(comment_id, message, tok)
    return f"OK replied. id={res.get('id')}"


@mcp.tool()
def fb_auto_reply(post_id: str, reply_text: str, limit: int = 50,
                  page: str = "") -> str:
    """
    Auto-reply to EVERY comment on a post with the same message
    (engagement booster, e.g. "Thanks for watching! 🔥 Follow for more").
    """
    _, tok = _fb_creds(page)
    res = fb.auto_reply_post(post_id, tok, reply_text, limit=limit)
    return f"OK auto-reply: {res['replies_sent']}/{res['comments_seen']} comments"


@mcp.tool()
def create_and_post(script: str, visual_keyword: str, caption: str,
                    title: str = "reel", voice: str = "", page: str = "",
                    style: str = "", hook: str = "",
                    num_backgrounds: int = 1) -> str:
    """
    FULL PIPELINE: script -> reel -> publish on a Facebook Page in one call.

    script:         narrator text
    visual_keyword: stock footage search term
    caption:        Facebook caption + hashtags (use generate_caption to build)
    title:          filename label
    voice:          voice id (empty = page default from pages.json, else .env)
    page:           page nickname from pages.json (e.g. "cats"). Empty = default.
    style:          caption style (empty = page default, else "facts")
    hook:           big hook text for first 3s (optional)
    num_backgrounds: how many clips to switch through
    """
    meta = _page_meta(page)
    voice = voice or meta.get("default_voice", "")
    style = style or meta.get("default_style", "facts")
    made = make_reel(script, visual_keyword, title=title, voice=voice,
                     style=style, hook=hook, num_backgrounds=num_backgrounds)
    path = made.split("OK reel ready:", 1)[1].split("(")[0].strip()
    pid, tok = _fb_creds(page)
    res = helpers.post_reel_to_facebook(Path(path), caption, pid, tok)
    return (f"OK created + posted to '{page or 'default'}'. "
            f"file={path} video_id={res['video_id']}")


def _make_oauth(public_url: str):
    """
    Build a self-contained OAuth 2.1 provider with Dynamic Client Registration
    (DCR) + PKCE. This is what claude.ai's custom connector expects — it will
    register itself and walk the user through an approve screen, no Client ID/
    Secret needed by hand.

    public_url: the public base URL claude.ai reaches us on (the ngrok URL).
    """
    from fastmcp.server.auth.providers.in_memory import (
        InMemoryOAuthProvider, ClientRegistrationOptions)
    return InMemoryOAuthProvider(
        base_url=public_url,
        client_registration_options=ClientRegistrationOptions(enabled=True),
        required_scopes=[],
    )


if __name__ == "__main__":
    import sys, os
    # Usage:
    #   python server.py                       -> stdio (Claude Code desktop)
    #   python server.py http                  -> HTTP :8000, OAuth off
    #   python server.py http 8000 <publicURL> -> HTTP + OAuth for claude.ai
    #   python server.py cloud                 -> cloud deploy (reads PORT +
    #                                             PUBLIC_URL from env)
    mode = sys.argv[1] if len(sys.argv) > 1 else ""

    if mode == "cloud":
        # Cloud platforms (Render/Railway/Fly) inject $PORT and let you set
        # $PUBLIC_URL to the permanent app URL. OAuth uses that.
        port = int(os.environ.get("PORT", "8000"))
        public_url = os.environ.get("PUBLIC_URL", "")
        if public_url:
            mcp.auth = _make_oauth(public_url)
            print(f"[cloud] OAuth enabled. Public URL: {public_url}")
        else:
            print("[cloud] WARNING: PUBLIC_URL not set -> server is OPEN. "
                  "Set PUBLIC_URL env to your app's https URL.")
        mcp.run(transport="http", host="0.0.0.0", port=port)

    elif mode == "http":
        port = int(sys.argv[2]) if len(sys.argv) > 2 else 8000
        public_url = sys.argv[3] if len(sys.argv) > 3 else ENV.get("PUBLIC_URL", "")
        if public_url:
            mcp.auth = _make_oauth(public_url)
            print(f"OAuth enabled. Public URL: {public_url}")
        else:
            print("No PUBLIC_URL given -> running OPEN (use only for local test).")
        mcp.run(transport="http", host="0.0.0.0", port=port)
    else:
        mcp.run()
