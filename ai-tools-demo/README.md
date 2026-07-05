# ai-tools-demo — MCP server

Claude se bolo *"5 best AI tools batao aur demo video banao"* → ye server Claude ko
ye sab karne deta hai, **end to end**:

1. **Screen recording** shuru kare (ffmpeg, Windows)
2. Ek **visible browser** chalaye aur har AI tool ko **actually use** kare
3. Tum **ek baar manually login** kar lo (session save ho jata hai — captcha bhi tum handle karte ho)
4. Recording band kare
5. **Voiceover** banaye (Gemini TTS, fail ho to free Edge-TTS)
6. Recording + voiceover ko ek **final mp4** mein merge kare

Sab output `./output/` mein jata hai. Server ki access **scoped** hai — sirf
screen record, ek browser, TTS, aur `output/` folder. Kuch aur nahi.

---

## Setup (ek baar)

```bash
cd ai-tools-demo
pip install -r requirements.txt
python -m playwright install chromium
cp .env.example .env      # phir .env mein GEMINI_API_KEY daalo (optional)
```

- **ffmpeg** PATH mein hona chahiye (tumhare paas already hai: ffmpeg 8.1).
- **GEMINI_API_KEY** optional hai. Na ho to free Edge-TTS use hota hai. Free key:
  https://aistudio.google.com/apikey

### Voice badalna
`.env` mein:
- `GEMINI_VOICE` — Kore / Puck / Charon / Aoede (default Kore)
- `EDGE_VOICE` — `en-IN-NeerjaNeural` (Indian English F), `hi-IN-SwaraNeural` (Hindi F),
  `hi-IN-MadhurNeural` (Hindi M)

---

## Claude Desktop / Claude Code mein add karo

`C:\Users\Admin\.claude.json` (Claude Code) ya
`C:\Users\Admin\AppData\Roaming\Claude\claude_desktop_config.json` (Desktop) ke
`mcpServers` block mein ye daalo:

```json
{
  "mcpServers": {
    "ai-tools-demo": {
      "command": "python",
      "args": ["c:/Users/Admin/Desktop/saurabh-tools/ai-tools-demo/server.py"]
    }
  }
}
```

Claude restart karo. Tools `ai-tools-demo` ke neeche dikhenge.

---

## Tools (jo Claude call karta hai)

| Tool | Kaam |
|------|------|
| `start_recording(name)` | Screen recording shuru |
| `stop_recording()` | Recording band + mp4 finalize |
| `browser_open(url)` | Visible browser khole (login session persist) |
| `browser_goto(url)` | Naye URL pe jaye |
| `browser_type(text, selector?, submit?)` | Type kare; `submit=True` Enter dabaye |
| `browser_click(selector)` | Element click |
| `browser_wait(seconds)` | Ruke (response/animation capture ke liye) |
| `browser_screenshot(name)` | Screenshot save |
| `browser_read_text()` | Page ka text padhe (Claude tool ka output "dekhe") |
| `wait_for_login(seconds)` | Tum manually login karo — server ruk jaata hai |
| `browser_close()` | Browser band |
| `make_voiceover(text, name)` | Narration audio banaye (Gemini → Edge fallback) |
| `assemble_video(video_path, voiceovers, name)` | Recording + voiceover → final mp4 |

---

## Example prompt jo Claude ko do

> "5 best AI tools ke baare mein ek demo video banao. Screen record karo, har tool ko
> browser mein khol ke ek sample prompt do, response capture karo, phir Hindi-English
> mein voiceover ke saath explain karte hue final mp4 banao. Jab login chahiye ho to
> mujhe bolna, main kar dunga."

### Pehli baar login flow
Jab Claude `wait_for_login` call kare, browser mein tum khud login + captcha kar lo.
Session `sessions/` mein save ho jata hai — agli baar login nahi maangega.

---

## Notes / limits
- **Ek time pe ek** recording aur ek browser (server single-demo ke liye design hua).
- Login wale tools (ChatGPT, Claude, Midjourney) ka pehla run manual login maangega.
  Captcha/2FA tum handle karte ho — koi password store nahi hota.
- Recording **poori screen** capture karti hai (sirf browser window nahi) — demo ke
  time apni private cheezein band rakho.
- Agar audio video se lamba ho to extra video tail rehta hai (demo ke liye theek hai).
