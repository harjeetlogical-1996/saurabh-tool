"""Build one real 'Best AI Tools' demo video end-to-end.

Records the screen while the browser tours several popular AI tools, then
narrates each with a voiceover and stitches everything into one final mp4.

No logins required — we visit public landing/demo pages so the run is reliable.
"""
import os
import time
import recorder
import browser
import voiceover
import assembler

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")

# (label, url, narration spoken while this tool is on screen)
TOOLS = [
    ("ChatGPT", "https://chat.openai.com/",
     "Number one, ChatGPT by OpenAI. Ye sabse popular AI chatbot hai. Aap isse "
     "writing, coding, research aur ideas ke liye baat kar sakte ho, bilkul ek "
     "insaan ki tarah."),
    ("Claude", "https://claude.ai/",
     "Number two, Claude by Anthropic. Ye lambe documents samajhne aur deep "
     "reasoning ke liye sabse accha mana jaata hai. Coding aur analysis mein "
     "kamaal karta hai."),
    ("Perplexity", "https://www.perplexity.ai/",
     "Number three, Perplexity. Ye ek AI search engine hai jo aapke sawaal ka "
     "seedha jawaab deta hai, saath mein sources bhi dikhata hai."),
    ("Midjourney", "https://www.midjourney.com/",
     "Number four, Midjourney. Sirf text likho aur ye stunning AI images bana "
     "deta hai. Designers aur artists ke beech bahut popular hai."),
    ("Gemini", "https://gemini.google.com/",
     "Aur number five, Google Gemini. Google ka apna AI, jo text, image aur "
     "voice sab samajhta hai, aur Google ke products ke saath juda hua hai."),
]

INTRO = ("Namaste! Aaj main aapko 2026 ke 5 best AI tools dikhane wala hoon, "
         "jo aapke kaam ko bahut aasaan bana denge. Chaliye shuru karte hain.")
OUTRO = ("To ye the 2026 ke 5 best AI tools. In sabko try karo aur dekho kaunsa "
         "aapke liye best kaam karta hai. Video pasand aaye to zaroor batana!")


def main():
    print(">> recording start")
    recorder.start_recording("best_ai_tools")

    print(">> open browser")
    browser.browser_open("about:blank")

    # Tour each tool, pausing so the page is clearly on the recording.
    for i, (label, url, _script) in enumerate(TOOLS, 1):
        print(f">> [{i}/{len(TOOLS)}] {label} -> {url}")
        try:
            browser.browser_goto(url)
        except Exception as e:
            print(f"   (goto failed for {label}: {e})")
        browser.browser_wait(4)
        browser.browser_screenshot(f"tool_{i}_{label.lower()}")

    browser.browser_close()

    print(">> stop recording")
    rec = recorder.stop_recording()
    print("   ", rec)

    # Build narration: intro + each tool + outro, concatenated in order.
    print(">> generating voiceovers")
    # Small gap between calls so we stay under Gemini's per-minute rate limit.
    clips = []
    vo = voiceover.make_voiceover(INTRO, "vo_intro")
    print("   intro:", vo["engine"])
    clips.append(vo["path"])
    for i, (label, _url, script) in enumerate(TOOLS, 1):
        time.sleep(7)
        v = voiceover.make_voiceover(script, f"vo_{i}_{label.lower()}")
        print(f"   {label}:", v["engine"])
        clips.append(v["path"])
    time.sleep(7)
    vo_out = voiceover.make_voiceover(OUTRO, "vo_outro")
    print("   outro:", vo_out["engine"])
    clips.append(vo_out["path"])

    print(">> assembling final video")
    final = assembler.assemble_video(rec["path"], clips, "best_ai_tools_final")
    print("\nDONE ->", final["path"], f"({final['size_bytes']} bytes)")


if __name__ == "__main__":
    main()
