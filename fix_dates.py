#!/usr/bin/env python3
"""
Spread article publish dates into the past (natural timeline) and give each
reader review its own date after the article's date. Uses wp-cli.
"""
import subprocess, os, random
from datetime import datetime, timedelta

PHP = r"C:\Users\Admin\AppData\Roaming\Local\lightning-services\php-8.2.29+0\bin\win64\php.exe"
WPCLI = r"C:\Program Files (x86)\Local\resources\extraResources\bin\wp-cli\wp-cli.phar"
INI = "/tmp/wpcli-php.ini"
if not os.path.exists(INI):
    INI = r"C:\Users\Admin\AppData\Local\Temp\wpcli-php.ini"
PUBLIC = r"C:\Users\Admin\Local Sites\reviewshub\app\public"

def wp(*args):
    return subprocess.run([PHP,"-c",INI,WPCLI,"--path="+PUBLIC,*args],
                          capture_output=True, text=True, timeout=90)

# Article publish dates: spread Sep 2025 -> May 2026 (oldest pillar first).
# id -> publish datetime
ARTICLE_DATES = {
    18:  "2025-09-12 10:24:00",  # dirt bikes (first / oldest pillar)
    42:  "2025-10-03 14:10:00",  # e-bikes
    54:  "2025-10-21 09:35:00",  # generators
    67:  "2025-11-08 11:50:00",  # lawn
    77:  "2025-11-24 16:05:00",  # atvs
    88:  "2025-12-09 13:20:00",  # camping
    100: "2026-01-07 10:45:00",  # pressure washers
    108: "2026-01-22 15:30:00",  # towing
    117: "2026-02-05 09:15:00",  # kids dirt bikes (cluster)
    122: "2026-02-19 12:40:00",  # cheap ebikes
    125: "2026-03-06 14:55:00",  # solar generators
    128: "2026-03-20 10:10:00",  # electric dirt bikes
    133: "2026-04-09 11:25:00",  # used atvs
    138: "2026-04-27 16:35:00",  # rooftop tents
    144: "2026-05-15 13:05:00",  # riding mowers
}

TODAY = datetime(2026, 6, 28)

def set_article_dates():
    print("=== Setting article dates ===")
    for pid, dt in ARTICLE_DATES.items():
        # set both post_date and post_date_gmt-ish via wp; also keep modified a bit later
        r = wp("post","update",str(pid),"--post_date="+dt,"--post_date_gmt="+dt)
        ok = "Success" in (r.stdout + r.stderr)
        print(f"  post {pid} -> {dt}  {'OK' if ok else r.stderr[:80]}")

def set_review_dates():
    print("\n=== Setting review (comment) dates ===")
    random.seed(7)
    for pid, dt in ARTICLE_DATES.items():
        adate = datetime.strptime(dt, "%Y-%m-%d %H:%M:%S")
        # get this post's comments
        r = wp("comment","list","--post_id="+str(pid),"--status=approve","--field=ID","--format=ids")
        ids = [x for x in r.stdout.split() if x.isdigit()]
        for cid in ids:
            # random date between (article date + 3 days) and today
            earliest = adate + timedelta(days=3)
            span = (TODAY - earliest).days
            if span < 1: span = 30
            d = earliest + timedelta(days=random.randint(0, span),
                                     hours=random.randint(0,23),
                                     minutes=random.randint(0,59))
            ds = d.strftime("%Y-%m-%d %H:%M:%S")
            wp("comment","update",cid,"--comment_date="+ds)
        print(f"  post {pid}: dated {len(ids)} reviews after {adate.date()}")

if __name__ == "__main__":
    set_article_dates()
    set_review_dates()
    print("\nDone.")
