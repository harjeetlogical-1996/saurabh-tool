"""Visible browser automation via Playwright, with persistent login sessions.

Design choices that matter for this use case:
- We launch a PERSISTENT context (launch_persistent_context) so cookies/logins
  survive across runs. The user logs in once manually; the session is reused.
- headless=False so the user (and the screen recorder) can SEE the browser.
- A single browser/context/page is held at module level — this server drives
  one demo at a time, which keeps the MCP tool surface simple.

Playwright's sync API is used so it composes cleanly with FastMCP's plain
(non-async) tool functions.
"""
import os
from playwright.sync_api import sync_playwright

# Persistent profile dir -> logins/cookies live here between runs.
USER_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sessions")

_pw = None        # the Playwright driver
_context = None   # persistent browser context
_page = None      # the active page


def _ensure_page():
    if _page is None:
        raise RuntimeError("Browser is not open. Call browser_open first.")
    return _page


def browser_open(url: str = "about:blank") -> dict:
    """Open (or reuse) the visible browser and navigate to url."""
    global _pw, _context, _page
    if _context is None:
        os.makedirs(USER_DATA_DIR, exist_ok=True)
        _pw = sync_playwright().start()
        # channel="chrome" uses the real installed Chrome if present; falls back
        # to bundled Chromium otherwise. Real Chrome trips fewer bot checks.
        try:
            _context = _pw.chromium.launch_persistent_context(
                USER_DATA_DIR, headless=False, channel="chrome",
                args=["--start-maximized"], no_viewport=True,
            )
        except Exception:
            _context = _pw.chromium.launch_persistent_context(
                USER_DATA_DIR, headless=False,
                args=["--start-maximized"], no_viewport=True,
            )
        _page = _context.pages[0] if _context.pages else _context.new_page()

    _page.goto(url, wait_until="domcontentloaded", timeout=60000)
    return {"url": _page.url, "title": _page.title()}


def browser_goto(url: str) -> dict:
    page = _ensure_page()
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    return {"url": page.url, "title": page.title()}


def browser_type(text: str, selector: str = None, submit: bool = False) -> dict:
    """Type text. If selector given, fill that element; else type into focused
    element. submit=True presses Enter afterward (handy for chat boxes)."""
    page = _ensure_page()
    if selector:
        page.fill(selector, text)
    else:
        page.keyboard.type(text, delay=20)
    if submit:
        page.keyboard.press("Enter")
    return {"typed": text[:80], "submitted": submit}


def browser_click(selector: str) -> dict:
    page = _ensure_page()
    page.click(selector, timeout=15000)
    return {"clicked": selector}


def browser_wait(seconds: float = 2.0) -> dict:
    """Pause so on-screen action (typing, AI response, animation) is captured."""
    page = _ensure_page()
    page.wait_for_timeout(int(seconds * 1000))
    return {"waited": seconds}


def browser_screenshot(name: str = "shot") -> dict:
    page = _ensure_page()
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
    os.makedirs(out_dir, exist_ok=True)
    safe = "".join(c for c in name if c.isalnum() or c in ("-", "_")) or "shot"
    path = os.path.join(out_dir, f"{safe}.png")
    page.screenshot(path=path, full_page=False)
    return {"path": path}


def browser_read_text(max_chars: int = 4000) -> dict:
    """Return visible text of the page so Claude can 'see' the tool's output."""
    page = _ensure_page()
    text = page.inner_text("body")
    return {"text": text[:max_chars], "truncated": len(text) > max_chars}


def wait_for_login(seconds: float = 90.0) -> dict:
    """Pause while the user manually logs in / solves a captcha in the visible
    browser. The persistent context saves the session automatically."""
    page = _ensure_page()
    page.wait_for_timeout(int(seconds * 1000))
    return {"status": "resumed", "url": page.url}


def browser_close() -> dict:
    global _pw, _context, _page
    if _context is not None:
        try:
            _context.close()
        except Exception:
            pass
    if _pw is not None:
        try:
            _pw.stop()
        except Exception:
            pass
    _pw = _context = _page = None
    return {"status": "closed"}
