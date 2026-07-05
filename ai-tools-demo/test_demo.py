"""End-to-end smoke test of the full pipeline (no login needed).

Simulates exactly what Claude does for a demo video:
  record -> open browser -> 'use' a couple of pages -> stop -> voiceover ->
  assemble final mp4 with audio.

Run: python test_demo.py
"""
import os
import recorder
import browser
import voiceover
import assembler

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")


def main():
    print("1) start recording")
    print("  ", recorder.start_recording("demo_test"))

    print("2) open browser + visit a couple of pages (simulating tool use)")
    print("  ", browser.browser_open("https://example.com"))
    browser.browser_wait(2)
    browser.browser_screenshot("demo_shot1")

    print("  ", browser.browser_goto("https://duckduckgo.com"))
    browser.browser_wait(1.5)
    # type a query into the search box and submit, like a prompt into an AI tool
    try:
        browser.browser_type("best ai tools 2026", selector="input[name=q]", submit=True)
        browser.browser_wait(3)
    except Exception as e:
        print("   (typing skipped:", e, ")")
    browser.browser_screenshot("demo_shot2")

    print("3) close browser")
    print("  ", browser.browser_close())

    print("4) stop recording")
    rec = recorder.stop_recording()
    print("  ", rec)

    print("5) make voiceover")
    script = (
        "Ye ek demo hai. Pehle humne example dot com khola, phir DuckDuckGo par "
        "best AI tools search kiya. Aise hi asli demo mein har AI tool ko use "
        "karke dikhaya jaayega, voiceover ke saath."
    )
    vo = voiceover.make_voiceover(script, "demo_voice")
    print("  ", vo)

    print("6) assemble final video")
    final = assembler.assemble_video(rec["path"], vo["path"], "demo_final")
    print("  ", final)

    print("\nDONE -> ", final["path"])


if __name__ == "__main__":
    main()
