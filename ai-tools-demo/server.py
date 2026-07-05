"""ai-tools-demo MCP server.

Lets Claude produce a narrated, screen-recorded demo of AI tools end to end:
  1. start_recording        -> begin capturing the screen
  2. browser_open / *_act   -> drive a visible browser to actually USE each tool
  3. wait_for_login         -> pause so the user logs in / solves captcha once
  4. stop_recording         -> finalize the screen capture mp4
  5. make_voiceover         -> narrate (Gemini TTS, Edge-TTS fallback)
  6. assemble_video         -> mux narration onto the recording -> final mp4

Scoped access by design: the server can record the screen, drive one browser,
synthesize speech, and write files into ./output — nothing else.

Typical Claude flow for "5 best AI tools" video:
  start_recording("ai-tools") ; for each tool: browser_open(url),
  (wait_for_login if needed), browser_type(prompt, submit=True), browser_wait,
  browser_screenshot ; stop_recording() ; make_voiceover(script) ;
  assemble_video(recording, voiceover).
"""
import os
from dotenv import load_dotenv
from fastmcp import FastMCP

import recorder
import browser
import voiceover
import assembler

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

mcp = FastMCP("ai-tools-demo")


# ---------- recording ----------
@mcp.tool()
def start_recording(name: str = "demo", framerate: int = 24) -> dict:
    """Start screen-recording the full desktop to output/<name>.mp4.
    Call this BEFORE opening the browser so the whole demo is captured."""
    return recorder.start_recording(name, framerate)


@mcp.tool()
def stop_recording() -> dict:
    """Stop the active screen recording and finalize the mp4."""
    return recorder.stop_recording()


# ---------- browser (actually using the AI tools) ----------
@mcp.tool()
def browser_open(url: str = "about:blank") -> dict:
    """Open the visible browser (persistent login session) and go to url."""
    return browser.browser_open(url)


@mcp.tool()
def browser_goto(url: str) -> dict:
    """Navigate the open browser to a new url."""
    return browser.browser_goto(url)


@mcp.tool()
def browser_type(text: str, selector: str = None, submit: bool = False) -> dict:
    """Type text into the page. selector optional (else types into focused box);
    submit=True presses Enter (good for chat prompts)."""
    return browser.browser_type(text, selector, submit)


@mcp.tool()
def browser_click(selector: str) -> dict:
    """Click an element by CSS selector."""
    return browser.browser_click(selector)


@mcp.tool()
def browser_wait(seconds: float = 2.0) -> dict:
    """Pause so the AI tool's response/animation is captured on the recording."""
    return browser.browser_wait(seconds)


@mcp.tool()
def browser_screenshot(name: str = "shot") -> dict:
    """Save a screenshot of the current page to output/<name>.png."""
    return browser.browser_screenshot(name)


@mcp.tool()
def browser_read_text(max_chars: int = 4000) -> dict:
    """Read visible page text so Claude can see the tool's output and narrate it."""
    return browser.browser_read_text(max_chars)


@mcp.tool()
def wait_for_login(seconds: float = 90.0) -> dict:
    """Pause while the user manually logs in / solves a captcha in the browser.
    The login session is saved automatically for next time."""
    return browser.wait_for_login(seconds)


@mcp.tool()
def browser_close() -> dict:
    """Close the browser."""
    return browser.browser_close()


# ---------- voiceover + assembly ----------
@mcp.tool()
def make_voiceover(text: str, name: str = "voiceover") -> dict:
    """Generate a narration audio file from text (Gemini TTS, Edge-TTS fallback).
    Returns the audio path and which engine was used."""
    return voiceover.make_voiceover(text, name)


@mcp.tool()
def assemble_video(video_path: str, voiceovers, name: str = "final") -> dict:
    """Mux narration onto the screen recording into a final mp4.
    voiceovers: a single audio path or a list of paths in narration order."""
    return assembler.assemble_video(video_path, voiceovers, name)


if __name__ == "__main__":
    mcp.run()
