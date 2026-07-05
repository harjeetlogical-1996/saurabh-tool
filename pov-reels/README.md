# POV Reels — MCP server

Make **"POV: I am a ___"** faceless viral reels where an AI-animated character
(a tomato, a matchstick, a sock…) speaks in first person. Give it a topic; it
writes a funny script, animates each scene with **Google Veo 3**, adds a
voiceover + captions, joins it all, and (optionally) uploads to YouTube Shorts.

It **reuses** the sibling `reels-factory` project for voice, captions, ffmpeg
assembly and YouTube auth — so keep this folder next to `reels-factory`.

## What it does (per reel)

```
topic  ─Gemini text→  script (scenes = visual + spoken line)
       ─Veo 3 Fast →   one animated 8s clip per scene (character acts + talks)
       ─Edge-TTS  →   free voiceover of each line
       ─ffmpeg    →   burn captions, join scenes, music → 9:16 mp4
       ─YouTube   →   optional upload as a Short
```

## Tools

| Tool | What it does | Costs money? |
|------|--------------|--------------|
| `pov_status` | Health check (keys, helpers, folders) | no |
| `estimate_reel_cost` | Cost for N scenes before you spend | no |
| `write_pov_script` | Write a script to review/tweak first | ~free (text) |
| `make_pov_reel` | Full reel. **Dry-run unless `confirm_cost=True`** | Veo clips only |
| `upload_pov_short` | Upload finished mp4 to YouTube Shorts | no |

## Cost

Only the **Veo clips** cost money. Everything else (voice, captions, assembly,
upload) is free/local.

| Quality | Rate (approx) | One 8s clip | 4-scene reel |
|---------|---------------|-------------|--------------|
| `fast`  | ~$0.15 / sec  | ~$1.20      | **~$4.80** |
| `hq`    | ~$0.40 / sec  | ~$3.20      | ~$12.80 |

Rates change — Google's pricing page is the source of truth. `make_pov_reel`
**never spends without `confirm_cost=True`**; without it you get the script +
estimate only.

## Setup

1. `pip install -r requirements.txt` (and install **ffmpeg** on PATH)
2. `copy .env.example .env` and add your `GEMINI_API_KEY` (or it reads
   `../nano-banana/api-key.txt`). **Enable billing** on that key for Veo.
3. YouTube upload reuses reels-factory — run `yt_authorize` there once.

## Connect to Claude Code

```bash
claude mcp add pov-reels -- python "C:\\Users\\Admin\\Desktop\\saurabh-tools\\pov-reels\\server.py"
```

or add to your MCP config:

```json
{
  "mcpServers": {
    "pov-reels": {
      "command": "python",
      "args": ["C:\\Users\\Admin\\Desktop\\saurabh-tools\\pov-reels\\server.py"]
    }
  }
}
```

## Typical flow

1. `write_pov_script(topic="a tomato's life")` → read/tweak the scenes.
2. `estimate_reel_cost(scenes=4)` → see the bill (~$4.80).
3. `make_pov_reel(topic="a tomato's life", confirm_cost=True)` → the mp4.
4. `upload_pov_short(video_path=..., title=...)` → live on Shorts.
