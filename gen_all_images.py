#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate all 20 featured images via Gemini, optimize to 1200x675,
save into a 'media-upload' folder (flat) for bulk Media Library import on live.
Each image named <slug>.jpg matching manifest img field.
"""
import os, base64, requests, json, time, sys
from PIL import Image

BASE = r"c:\Users\Admin\Desktop\saurabh-tools"
KEY = open(os.path.join(BASE,"nano-banana","api-key.txt"),encoding="utf-8").read().strip()
OUT = os.path.join(BASE, "media-upload")
os.makedirs(OUT, exist_ok=True)
EP = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-image:generateContent"
manifest = json.load(open(os.path.join(BASE,"bulk-manifest.json"),encoding="utf-8"))["articles"]

# photographic prompt per slug. Realistic, editorial, no text/logos/watermarks.
PROMPTS = {
 "best-websites-beginner-dirt-bikes":"A clean modern beginner dirt bike on a dirt trail at golden hour, side view, shallow depth of field, professional product photography, no text, no logos, no people faces",
 "best-websites-refurbished-electric-bikes":"A sleek refurbished electric commuter bike leaning against a brick urban wall, soft daylight, editorial product photography, no text, no logos",
 "best-websites-buy-utvs-side-by-sides":"A rugged side-by-side UTV parked on an off-road trail with mountains behind, dramatic lighting, professional automotive photography, no text, no logos, no faces",
 "best-websites-standby-generators":"A home standby generator unit installed beside a modern suburban house, clean daylight, professional product photography, no text, no logos",
 "best-websites-dirt-bike-gear-helmets":"A motocross helmet and riding gloves on a wooden bench in a garage, soft studio light, editorial gear photography, no text, no logos",
 "best-websites-string-trimmers":"A modern battery string trimmer leaning on freshly cut green grass in a backyard, warm daylight, product photography, no text, no logos",
 "best-websites-buy-jet-skis":"A jet ski personal watercraft skimming across blue lake water with spray, action shot, bright sunny day, professional photography, no text, no logos, no faces",
 "best-websites-portable-power-stations":"A portable power station with cables on a campsite table at dusk with string lights, cozy editorial photography, no text, no logos",
 "best-websites-trailer-hitches":"A chrome trailer hitch receiver on the back of a pickup truck, close up, soft outdoor light, detailed product photography, no text, no logos",
 "best-websites-camping-coolers":"A rugged hard cooler on a rocky lakeshore at a campsite with pine trees, golden hour, lifestyle photography, no text, no logos, no faces",
 "best-websites-used-dirt-bikes":"A used dirt bike for sale in a sunlit yard, side profile, slightly worn but clean, realistic photography, no text, no logos, no faces",
 "best-websites-ebike-batteries":"A close up of a removable electric bike battery pack on a workbench with tools, clean studio light, product photography, no text, no logos",
 "best-websites-buy-trailers":"An enclosed cargo trailer parked in a lot under blue sky, three quarter view, professional product photography, no text, no logos",
 "best-websites-robotic-lawn-mowers":"A robotic lawn mower cutting a lush green lawn in a modern backyard, soft morning light, lifestyle product photography, no text, no logos",
 "best-websites-off-road-recovery-gear":"Off road recovery gear with kinetic rope and shackles laid out on a tailgate in a muddy trail setting, rugged editorial photography, no text, no logos",
 "best-websites-commercial-pressure-washers":"A commercial hot water pressure washer on a wash bay floor, industrial setting, clean lighting, professional product photography, no text, no logos",
 "best-websites-atv-utv-parts":"ATV and UTV aftermarket parts and accessories arranged on a garage workbench, soft light, detailed product photography, no text, no logos",
 "best-websites-emergency-backup-power":"A home battery backup unit mounted in a garage powering a house during an outage, warm interior light, editorial photography, no text, no logos",
 "best-websites-tie-down-straps":"Heavy duty ratchet tie down straps securing cargo on a flatbed trailer, close up, outdoor daylight, product photography, no text, no logos",
 "best-websites-floor-scrubbers":"An industrial walk behind floor scrubber cleaning a large warehouse floor, wide shot, clean lighting, professional photography, no text, no logos, no faces",
}

def gen(slug, fname):
    prompt = PROMPTS[slug] + ". Wide 16:9 composition, high detail, no watermark."
    for attempt in range(3):
        try:
            r = requests.post(EP, headers={"x-goog-api-key":KEY,"Content-Type":"application/json"},
                json={"contents":[{"parts":[{"text":prompt}]}],"generationConfig":{"responseModalities":["IMAGE"]}}, timeout=150)
            if r.status_code != 200:
                print("  ERR", r.status_code, r.text[:120]); time.sleep(5); continue
            for p in r.json()["candidates"][0]["content"]["parts"]:
                dd = p.get("inlineData") or p.get("inline_data")
                if dd:
                    path = os.path.join(OUT, fname)
                    open(path,"wb").write(base64.b64decode(dd["data"]))
                    im = Image.open(path).convert("RGB"); w,h = im.size; tr = 16/9
                    if w/h > tr:
                        nw = int(h*tr); l=(w-nw)//2; im = im.crop((l,0,l+nw,h))
                    else:
                        nh = int(w/tr); t=(h-nh)//2; im = im.crop((0,t,w,t+nh))
                    im = im.resize((1200,675), Image.LANCZOS)
                    im.save(path,"JPEG",quality=82,optimize=True,progressive=True)
                    kb = os.path.getsize(path)//1024
                    print("  OK {} ({} KB)".format(fname, kb)); return True
            print("  no image part"); time.sleep(5)
        except Exception as e:
            print("  EXC", str(e)[:120]); time.sleep(5)
    return False

only = sys.argv[1] if len(sys.argv)>1 else None
done=0; fail=[]
for a in manifest:
    slug = a["slug"]; fname = a["img"]
    if only and only not in slug: continue
    if os.path.exists(os.path.join(OUT,fname)):
        print("SKIP exists", fname); done+=1; continue
    print("GEN", slug)
    if gen(slug, fname): done+=1
    else: fail.append(fname)
    time.sleep(2)
print("DONE images={} fail={}".format(done, fail))
