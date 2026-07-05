#!/usr/bin/env python3
"""Generate author profile photos for Reviews Hub."""
import os, base64, requests

HERE = os.path.dirname(os.path.abspath(__file__))
KEY = open(os.path.join(HERE,"api-key.txt"),encoding="utf-8").read().strip()
IMGDIR = r"C:\Users\Admin\Local Sites\reviewshub\app\public\wp-content\uploads\authors"
MODEL = "gemini-2.5-flash-image"
EP = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"

AUTHORS = [
    ("author-jordan.jpg",
     "Professional headshot photograph of a friendly 30-something American man with short brown hair "
     "and light stubble, wearing a casual gray shirt, neutral soft-blurred studio background, natural lighting, "
     "looking at camera with a warm confident smile. Realistic, high quality, editorial portrait. No text."),
    ("author-mia.jpg",
     "Professional headshot photograph of a friendly 30-something American woman with shoulder-length dark hair, "
     "wearing a casual olive-green top, neutral soft-blurred studio background, natural lighting, warm confident smile, "
     "looking at camera. Realistic, high quality, editorial portrait. No text."),
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
for fname,prompt in AUTHORS:
    print("Generating",fname)
    img = gen(prompt)
    if img:
        open(os.path.join(IMGDIR,fname),"wb").write(img)
        print("  saved",len(img)//1024,"KB")
    else:
        print("  FAILED")
print("Done into", IMGDIR)
