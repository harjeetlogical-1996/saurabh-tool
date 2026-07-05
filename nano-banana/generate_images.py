#!/usr/bin/env python3
"""
Nano Banana (Gemini) image generator for Reviews Hub homepage.
Reads API key from api-key.txt, generates images, saves them into the
WordPress theme's /assets/img/ folder.
"""
import os, sys, base64, json, mimetypes
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
KEY_FILE = os.path.join(HERE, "api-key.txt")

# Where the theme lives (images go here)
THEME_IMG = r"C:\Users\Admin\Local Sites\reviewshub\app\public\wp-content\themes\reviewshub\assets\img"

MODEL = "gemini-2.5-flash-image"   # Nano Banana
ENDPOINT = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"

# (filename, prompt)
IMAGES = [
    ("hero.jpg",
     "A clean, premium wide banner photograph for a product-review website hero section. "
     "A tasteful flat-lay / collage of outdoor power gear arranged neatly: an electric dirt bike, "
     "an e-bike, a portable power station/generator, and camping gear, on a soft light-grey studio background "
     "with lots of empty space on the left for text. Bright, editorial, modern, high-end catalog look. "
     "No text, no watermark, no logos. 16:9, soft natural lighting, shallow depth of field."),

    ("feature-rides.jpg",
     "A dynamic but clean lifestyle photo of an electric dirt bike and a modern e-bike side by side "
     "on a neutral concrete studio floor, soft daylight, editorial product-review style, lots of negative space, "
     "muted premium colors, no text, no watermark. Square-ish framing, sharp focus."),

    ("feature-power.jpg",
     "A clean studio product photo of a portable power station / generator next to camping and overlanding gear "
     "(a cooler, a folding solar panel), on a soft warm off-white background, bright even lighting, "
     "modern catalog look, lots of empty space, no text, no watermark. Square-ish framing."),
]

def load_key():
    if not os.path.exists(KEY_FILE):
        sys.exit("api-key.txt not found.")
    key = open(KEY_FILE, encoding="utf-8").read().strip()
    if not key or "PASTE_YOUR" in key:
        sys.exit("Please paste your Gemini API key into api-key.txt (still a placeholder).")
    return key

def generate(key, prompt):
    headers = {"x-goog-api-key": key, "Content-Type": "application/json"}
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseModalities": ["IMAGE"]},
    }
    r = requests.post(ENDPOINT, headers=headers, json=body, timeout=120)
    if r.status_code != 200:
        print("  ERROR", r.status_code, r.text[:400])
        return None
    data = r.json()
    try:
        parts = data["candidates"][0]["content"]["parts"]
        for p in parts:
            if "inlineData" in p:
                return base64.b64decode(p["inlineData"]["data"])
            if "inline_data" in p:
                return base64.b64decode(p["inline_data"]["data"])
    except Exception as e:
        print("  parse error:", e, json.dumps(data)[:300])
    return None

def main():
    key = load_key()
    os.makedirs(THEME_IMG, exist_ok=True)
    ok = 0
    for fname, prompt in IMAGES:
        print(f"Generating {fname} ...")
        img = generate(key, prompt)
        if img:
            path = os.path.join(THEME_IMG, fname)
            with open(path, "wb") as f:
                f.write(img)
            print(f"  saved -> {path} ({len(img)//1024} KB)")
            ok += 1
        else:
            print(f"  FAILED: {fname}")
    print(f"\nDone. {ok}/{len(IMAGES)} images generated into:\n  {THEME_IMG}")

if __name__ == "__main__":
    main()
