# -*- coding: utf-8 -*-
"""
Daily stock reels — runs once a day (e.g. 10 PM via Task Scheduler).
Builds a US (English) + India (Hindi) top-movers reel from LIVE data and
uploads both to the Market Watch Pro YouTube channel. Then cleans up.

Run:  python daily_stock.py
"""
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import server          # reuses make_stock_reel
import youtube_manager as yt
import helpers

CHANNEL = "marketwatchpro"   # YouTube channel nickname
FB_NICK = "marketwatch"      # Facebook page nickname (same brand)
DATE = time.strftime("%d %b %Y")

# load FB page creds from pages.json
import json
_pages = json.load(open(Path(__file__).parent / "pages.json", encoding="utf-8"))
_fb = _pages.get(FB_NICK, {})
FB_PAGE_ID = _fb.get("page_id", "")
FB_TOKEN = _fb.get("token", "")

JOBS = [
    {
        "market": "US",
        "title": f"US Stocks Top Gainers & Losers | {DATE} #Shorts",
        "desc": (f"Today's top US stock movers ({DATE}). Top 5 gainers and "
                 "losers with live prices.\n\n"
                 "#stocks #stockmarket #investing #trading #shorts #usstocks "
                 "#nasdaq #wallstreet #finance #marketwatch"),
        "tags": ["stocks", "stock market", "top gainers", "top losers",
                 "US stocks", "investing", "trading", "nasdaq", "shorts"],
    },
    {
        "market": "INDIA",
        "title": f"Aaj ke Top Gainers aur Losers | NSE | {DATE} #Shorts",
        "desc": (f"Aaj ke top Indian stock movers ({DATE}). Top 5 gainers aur "
                 "losers live price ke saath.\n\n"
                 "#sharemarket #stockmarket #nifty #nse #investing #trading "
                 "#shorts #indianstocks #stocks #finance"),
        "tags": ["share market", "stock market", "nifty", "nse",
                 "top gainers", "top losers", "indian stocks", "shorts"],
    },
]


def run(only_market: str = ""):
    log = []
    jobs = JOBS
    if only_market:
        jobs = [j for j in JOBS if j["market"].upper() == only_market.upper()]
    for job in jobs:
        mk = job["market"]
        try:
            print(f"[{mk}] building reel...")
            res = server.make_stock_reel(market=mk, n=5)
            # extract file path from the tool's text response
            line = [l for l in res.splitlines() if "File:" in l][0]
            path = line.split("File:", 1)[1].strip()
            print(f"[{mk}] reel -> {path}")

            print(f"[{mk}] uploading to YouTube ({CHANNEL})...")
            up = yt.upload_short(path, job["title"], description=job["desc"],
                                 tags=job["tags"], privacy="public",
                                 channel=CHANNEL)
            log.append(f"{mk}: YT -> {up['url']}")
            print(f"[{mk}] {up['url']}")

            # ALSO post to Facebook Market Watch Pro page (same reel)
            try:
                fb_cap = job["title"].replace(" #Shorts", "") + "\n\n" + job["desc"]
                fr = helpers.post_reel_to_facebook(
                    Path(path),
                    fb_cap,
                    FB_PAGE_ID, FB_TOKEN)
                log.append(f"{mk}: FB posted")
                print(f"[{mk}] FB posted")
            except Exception as fe:
                log.append(f"{mk}: FB fail {fe}")
                print(f"[{mk}] FB fail:", str(fe)[:150])

            # clean the file to save disk
            try:
                Path(path).unlink()
                jpg = Path(path).with_suffix(".jpg")
                if jpg.exists():
                    jpg.unlink()
            except Exception:
                pass
        except Exception as e:
            log.append(f"{mk}: FAIL {e}")
            print(f"[{mk}] FAILED:", traceback.format_exc()[:400])

    # tidy temp
    try:
        for f in helpers.TEMP.glob("*"):
            f.unlink()
    except Exception:
        pass

    print("\n=== DAILY STOCK DONE ===")
    for l in log:
        print(" ", l)


if __name__ == "__main__":
    # optional arg: US or INDIA (default both)
    mk = sys.argv[1] if len(sys.argv) > 1 else ""
    run(mk)
