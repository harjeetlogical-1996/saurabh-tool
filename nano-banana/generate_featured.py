#!/usr/bin/env python3
"""Generate a featured image for the dirt bikes article."""
import os, base64, requests
HERE = os.path.dirname(os.path.abspath(__file__))
KEY = open(os.path.join(HERE,"api-key.txt"),encoding="utf-8").read().strip()
IMGDIR = r"C:\Users\Admin\Local Sites\reviewshub\app\public\wp-content\uploads\featured"
MODEL = "gemini-2.5-flash-image"
EP = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"

IMAGES = [
    ("dirt-bikes-featured.jpg",
     "A high-quality, realistic wide photograph of a modern dirt bike (motocross bike) parked on a dirt track "
     "outdoors on a bright day, dramatic but natural lighting, slightly blurred background of a motocross trail, "
     "professional product / editorial photography style, sharp detail, vivid but realistic colors. "
     "16:9 landscape. No text, no watermark, no logos."),
]

def gen(prompt):
    r = requests.post(EP, headers={"x-goog-api-key":KEY,"Content-Type":"application/json"},
        json={"contents":[{"parts":[{"text":prompt}]}],"generationConfig":{"responseModalities":["IMAGE"]}}, timeout=120)
    if r.status_code!=200:
        print("ERR",r.status_code,r.text[:200]); return None
    for p in r.json()["candidates"][0]["content"]["parts"]:
        d = p.get("inlineData") or p.get("inline_data")
        if d: return base64.b64decode(d["data"])
    return None

os.makedirs(IMGDIR, exist_ok=True)
for fname,prompt in IMAGES:
    print("Generating",fname)
    img = gen(prompt)
    if img:
        open(os.path.join(IMGDIR,fname),"wb").write(img)
        print("  saved",len(img)//1024,"KB")
    else: print("  FAILED")
print("Done into", IMGDIR)
