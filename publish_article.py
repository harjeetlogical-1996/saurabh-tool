#!/usr/bin/env python3
"""
Publish one Reviews Hub article end-to-end.
Usage: python publish_article.py <config.json>
config keys: html_file, title, slug, excerpt, author_id, category_name,
  focus_kw, secondary_kw, meta_desc, tags(list), img_prompt, img_name,
  cat_placeholders {PLACEHOLDER: category_name_or_HOME}, post_date
"""
import subprocess, os, sys, json, base64, random
from datetime import datetime
import requests
from PIL import Image

PHP=r"C:\Users\Admin\AppData\Roaming\Local\lightning-services\php-8.2.29+0\bin\win64\php.exe"
WPCLI=r"C:\Program Files (x86)\Local\resources\extraResources\bin\wp-cli\wp-cli.phar"
INI=r"C:\Users\Admin\AppData\Local\Temp\wpcli-php.ini"
PUBLIC=r"C:\Users\Admin\Local Sites\reviewshub\app\public"
FEATDIR=r"C:\Users\Admin\Local Sites\reviewshub\app\public\wp-content\uploads\featured"
KEY=open(r"c:\Users\Admin\Desktop\saurabh-tools\nano-banana\api-key.txt",encoding="utf-8").read().strip()

def wp(*a):
    return subprocess.run([PHP,"-c",INI,WPCLI,"--path="+PUBLIC,*a],capture_output=True,text=True,timeout=120)

def caturl(name):
    r=wp("term","list","category","--name="+name,"--field=url","--format=csv")
    lines=[l for l in r.stdout.strip().splitlines() if l.startswith("http")]
    return lines[-1] if lines else "http://reviewshub.local:10010/"

def catid(name):
    r=wp("term","list","category","--name="+name,"--field=term_id","--format=ids")
    return r.stdout.split()[0] if r.stdout.split() else ""

def gen_image(prompt, fname):
    ep="https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-image:generateContent"
    r=requests.post(ep,headers={"x-goog-api-key":KEY,"Content-Type":"application/json"},
        json={"contents":[{"parts":[{"text":prompt}]}],"generationConfig":{"responseModalities":["IMAGE"]}},timeout=120)
    if r.status_code!=200: print("img ERR",r.status_code,r.text[:120]); return None
    for p in r.json()["candidates"][0]["content"]["parts"]:
        d=p.get("inlineData") or p.get("inline_data")
        if d:
            path=os.path.join(FEATDIR,fname); open(path,"wb").write(base64.b64decode(d["data"]))
            im=Image.open(path).convert("RGB"); w,h=im.size; tr=16/9
            if w/h>tr: nw=int(h*tr); l=(w-nw)//2; im=im.crop((l,0,l+nw,h))
            else: nh=int(w/tr); t=(h-nh)//2; im=im.crop((0,t,w,t+nh))
            im=im.resize((1200,675),Image.LANCZOS); im.save(path,"JPEG",quality=82,optimize=True,progressive=True)
            return path
    return None

def main():
    cfg=json.load(open(sys.argv[1],encoding="utf-8"))
    html=open(cfg["html_file"],encoding="utf-8").read()
    # strip dashes
    for a,b in [(" — ",", "),(" – ",", "),("—",", "),("–","-")]:
        html=html.replace(a,b)
    # replace category placeholders
    for ph,target in cfg.get("cat_placeholders",{}).items():
        url = "http://reviewshub.local:10010/" if target=="HOME" else caturl(target)
        html=html.replace(ph,url)
    tmp=r"C:\Users\Admin\AppData\Local\Temp\rh_article.html"
    open(tmp,"w",encoding="utf-8").write(html)

    cid=catid(cfg["category_name"])
    r=wp("post","create",tmp,"--post_type=post","--post_status=publish",
         "--post_title="+cfg["title"],"--post_excerpt="+cfg["excerpt"],
         "--post_author="+str(cfg["author_id"]),"--post_category="+cid,
         "--post_date="+cfg["post_date"],"--post_date_gmt="+cfg["post_date"],"--porcelain")
    pid=r.stdout.strip().splitlines()[-1]
    if not pid.isdigit(): print("CREATE FAIL:",r.stderr[:200]); return
    wp("post","update",pid,"--post_name="+cfg["slug"])
    wp("post","meta","update",pid,"_rh_focus_keyword",cfg["focus_kw"])
    wp("post","meta","update",pid,"_rh_secondary_keywords",cfg["secondary_kw"])
    wp("post","meta","update",pid,"_rh_meta_description",cfg["meta_desc"])
    wp("post","meta","update",pid,"_rh_seo_title",cfg["title"])
    wp("post","term","set",pid,"post_tag",*cfg["tags"])
    # featured image
    if gen_image(cfg["img_prompt"], cfg["img_name"]):
        rr=wp("media","import",os.path.join(FEATDIR,cfg["img_name"]),"--post_id="+pid,
              "--title="+cfg["title"],"--alt="+cfg.get("img_alt",cfg["title"]),"--porcelain")
        aid=rr.stdout.strip().splitlines()[-1]
        if aid.isdigit(): wp("post","meta","update",pid,"_thumbnail_id",aid)
    print("PUBLISHED pid="+pid+" slug="+cfg["slug"])

if __name__=="__main__":
    main()
