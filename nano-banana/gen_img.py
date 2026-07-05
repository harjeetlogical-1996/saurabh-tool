import os, base64, requests, sys
HERE=os.path.dirname(os.path.abspath(__file__))
KEY=open(os.path.join(HERE,"api-key.txt"),encoding="utf-8").read().strip()
IMGDIR=r"C:\Users\Admin\Local Sites\reviewshub\app\public\wp-content\uploads\featured"
EP="https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-image:generateContent"
fname, prompt = sys.argv[1], sys.argv[2]
r=requests.post(EP,headers={"x-goog-api-key":KEY,"Content-Type":"application/json"},
  json={"contents":[{"parts":[{"text":prompt}]}],"generationConfig":{"responseModalities":["IMAGE"]}},timeout=120)
if r.status_code==200:
    for p in r.json()["candidates"][0]["content"]["parts"]:
        d=p.get("inlineData") or p.get("inline_data")
        if d:
            open(os.path.join(IMGDIR,fname),"wb").write(base64.b64decode(d["data"])); print("saved",fname); sys.exit()
print("ERR",r.status_code,r.text[:150])
