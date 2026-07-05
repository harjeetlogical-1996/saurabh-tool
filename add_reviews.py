#!/usr/bin/env python3
"""
Add realistic, keyword-rich reader reviews (WordPress comments + star rating)
to each Reviews Hub article. Generates a wp-cli batch and prints it.
"""
import subprocess, os, random

PHP = r"C:\Users\Admin\AppData\Roaming\Local\lightning-services\php-8.2.29+0\bin\win64\php.exe"
WPCLI = r"C:\Program Files (x86)\Local\resources\extraResources\bin\wp-cli\wp-cli.phar"
INI = r"C:\Users\Admin\AppData\Local\Temp\wpcli-php.ini"  # fallback
INI_GIT = "/tmp/wpcli-php.ini"
PUBLIC = r"C:\Users\Admin\Local Sites\reviewshub\app\public"

# article id -> (focus keyword, short noun, a couple of brand/detail mentions)
ARTICLES = {
    18:  ("best websites to buy dirt bikes", "dirt bike", ["MotoBuys", "Apollo", "MX Locker", "125cc"]),
    42:  ("best websites to buy e-bikes", "e-bike", ["Lectric", "Aventon", "Upway", "commuter"]),
    54:  ("best websites to buy generators", "generator", ["EcoFlow", "Jackery", "Anker", "power station"]),
    67:  ("best websites to buy lawn mowers", "lawn mower", ["Home Depot", "EGO", "Toro", "zero-turn"]),
    77:  ("best websites to buy ATVs", "ATV", ["ATV Trader", "RideNow", "Polaris", "side-by-side"]),
    88:  ("best websites to buy camping gear", "camping gear", ["REI", "CampSaver", "OVS", "rooftop tent"]),
    100: ("best websites to buy pressure washers", "pressure washer", ["Sun Joe", "Home Depot", "Simpson", "electric"]),
    108: ("best websites to buy trailer hitches", "trailer hitch", ["etrailer", "U-Haul", "CURT", "tow strap"]),
    117: ("best websites to buy kids dirt bikes", "kids dirt bike", ["Q9 PowerSports", "Tao Motor", "50cc", "youth"]),
    122: ("best websites for cheap electric bikes", "cheap e-bike", ["Lectric", "Heybike", "ENGWE", "under $1000"]),
    125: ("best websites for solar generators", "solar generator", ["EcoFlow", "Jackery", "Anker SOLIX", "power station"]),
    128: ("best websites to buy electric dirt bikes", "electric dirt bike", ["REV Rides", "E Ride Pro", "Talaria", "Sur-Ron"]),
    133: ("best websites to buy used ATVs", "used ATV", ["ATV Trader", "eBay", "Autotrader", "certified"]),
    138: ("best websites for rooftop tents", "rooftop tent", ["OVS", "Rhino", "hardshell", "overlanding"]),
    144: ("best websites to buy riding mowers", "riding mower", ["Home Depot", "Cub Cadet", "Husqvarna", "zero-turn"]),
}

FIRST = ["Mike","Sarah","Dave","Jen","Carlos","Amanda","Tyler","Rachel","Greg","Nicole",
         "Brandon","Kayla","Steve","Megan","Jason","Lauren","Kevin","Ashley","Derek","Holly",
         "Marcus","Diana","Travis","Brittany","Shawn","Erica","Cody","Vanessa","Hunter","Paula"]
LAST = ["R.","M.","T.","K.","P.","B.","H.","S.","W.","C.","D.","L.","G.","N.","J."]

# templates use {kw}=keyword, {n}=noun, {b}=brand/detail
TEMPLATES = [
    "This is hands down the best guide on {kw} I have found. I followed your top pick and my {n} arrived fast and exactly as described. Thank you!",
    "Really helpful comparison. I was confused about where to buy a {n} until I read this. Ended up going with {b} and could not be happier.",
    "Bookmarking this. The breakdown of {kw} saved me hours of research. The price and shipping notes were spot on.",
    "Great roundup. I almost bought from a random site but your warning section made me check reviews first. Bought my {n} from {b} instead, much better experience.",
    "Exactly what I needed. As a first-time {n} buyer this made the whole thing easy. The buying checklist alone is worth it.",
    "Solid list of the {kw}. {b} was my pick too and the deal I got matched what you said. Highly recommend this guide.",
    "I have bought two {n}s now using this guide. Both times the store you recommended had the best price and no shipping headaches.",
    "Wish I had found this sooner. I overpaid on my first {n} from another site. Your comparison of {kw} is the most honest I have seen.",
    "Very thorough and easy to read. The {b} recommendation was perfect for my budget. Appreciate that it does not feel like a sales pitch.",
    "Best resource for {kw} online. Clear, detailed, and the FAQ answered every question I had about buying a {n}.",
    "Used your guide to pick a {n} for my son and it worked out great. The safety and value tips were really useful.",
    "The comparison table made it so easy to decide. Went with {b} based on your ranking and the {n} is fantastic.",
]

def esc(s):
    return s.replace('"', "'").replace("—", ", ").replace("–", "-")

def main():
    ini = INI_GIT if os.path.exists(INI_GIT) else INI
    random.seed(42)
    total = 0
    for pid,(kw,noun,brands) in ARTICLES.items():
        n_reviews = random.randint(4,6)
        used = set()
        tpls = random.sample(TEMPLATES, n_reviews)
        for i in range(n_reviews):
            name = random.choice(FIRST)+" "+random.choice(LAST)
            while name in used: name = random.choice(FIRST)+" "+random.choice(LAST)
            used.add(name)
            b = random.choice(brands)
            text = tpls[i].format(kw=kw, n=noun, b=b)
            text = esc(text)
            rating = 5 if random.random()<0.7 else 4
            # build wp comment create command
            cmd = [PHP, "-c", ini, WPCLI, "--path="+PUBLIC, "comment", "create",
                   "--comment_post_ID="+str(pid),
                   "--comment_author="+name,
                   "--comment_content="+text,
                   "--comment_approved=1",
                   "--porcelain"]
            try:
                out = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                cid = out.stdout.strip().splitlines()[-1] if out.stdout.strip() else ""
                if cid.isdigit():
                    # add rating meta
                    subprocess.run([PHP,"-c",ini,WPCLI,"--path="+PUBLIC,"comment","meta","update",cid,"rh_rating",str(rating)],
                                   capture_output=True, text=True, timeout=60)
                    total += 1
                    print(f"  post {pid}: {name} ({rating}star) -> comment {cid}")
                else:
                    print(f"  post {pid}: FAILED -> {out.stderr[:120]}")
            except Exception as e:
                print(f"  post {pid}: ERROR {e}")
    print(f"\nTotal reviews added: {total}")

if __name__ == "__main__":
    main()
