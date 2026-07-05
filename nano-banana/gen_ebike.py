import os, base64, requests
HERE=os.path.dirname(os.path.abspath(__file__))
KEY=open(os.path.join(HERE,"api-key.txt"),encoding="utf-8").read().strip()
IMGDIR=r"C:\Users\Admin\Local Sites\reviewshub\app\public\wp-content\uploads\featured"
EP="https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-image:generateContent"
prompt=("A high-quality realistic wide photograph of a modern electric commuter bike (e-bike) parked on a city "
"street bike path on a bright day, clean editorial product photography, sharp detail, vivid realistic colors, "
"slightly blurred urban background. 16:9 landscape. No text, no watermark, no logos.")
r=requests.post(EP,headers={"x-goog-api-key":KEY,"Content-Type":"application/json"},
  json={"contents":[{"parts":[{"text":prompt}]}],"generationConfig":{"responseModalities":["IMAGE"]}},timeout=120)
if r.status_code==200:
    for p in r.json()["candidates"][0]["content"]["parts"]:
        d=p.get("inlineData") or p.get("inline_data")
        if d:
            open(os.path.join(IMGDIR,"ebikes-featured.jpg"),"wb").write(base64.b64decode(d["data"]))
            print("saved ebikes-featured.jpg")
else: print("ERR",r.status_code,r.text[:200])
