#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build one WordPress WXR (XML) import file for all 20 articles.
- Each article: post + scheduled future date + author + category + SEO meta.
- Each article: an <item> of type attachment (the featured image) with a LIVE
  attachment_url, and the post links to it via _thumbnail_id postmeta.
Image live path: https://buyfrombest.com/wp-content/uploads/bfb-articles/<file>
(User extracts media-upload.zip into /wp-content/uploads/bfb-articles/ on live.)
"""
import json, os, html, datetime

BASE = r"c:\Users\Admin\Desktop\saurabh-tools"
ART = os.path.join(BASE, "articles")
manifest = json.load(open(os.path.join(BASE,"bulk-manifest.json"),encoding="utf-8"))["articles"]
data = json.load(open(os.path.join(BASE,"store-data.json"),encoding="utf-8"))

SITE = "https://buyfrombest.com"
IMG_BASE = SITE + "/wp-content/uploads/bfb-articles"

# Authors: login + display + email. Match live site authors.
AUTHORS = {
  "Jordan": {"login":"jordan","email":"jordan@buyfrombest.com","display":"Jordan Miles"},
  "Mia":    {"login":"mia","email":"mia@buyfrombest.com","display":"Mia Carter"},
}

# category -> nicename (slug). Must match live category slugs.
CAT_SLUG = {
 "Dirt Bikes & Motocross":"dirt-bikes-motocross",
 "E-Bikes & E-Mobility":"e-bikes-e-mobility",
 "Powersports & Off-Road":"powersports-off-road",
 "Generators & Power":"generators-power",
 "Lawn & Outdoor Power":"lawn-outdoor-power",
 "Industrial Cleanup":"industrial-cleanup",
 "Hauling & Towing":"hauling-towing",
 "Camping & Overlanding":"camping-overlanding",
}

def cdata(s):
    return "<![CDATA[" + s.replace("]]>", "]]]]><![CDATA[>") + "]]>"

import re as _re
def slugify(s):
    s = s.lower().strip()
    s = _re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")

def build_tags(focus_kw, stores, what):
    # smart tags: the buying-intent phrase variants + the product noun + top store names
    tags = []
    fk = focus_kw.lower()
    tags.append(fk)                                  # full focus keyword
    tags.append(what.lower())                        # product noun e.g. "beginner dirt bikes"
    tags.append("where to buy " + what.lower())
    tags.append(what.lower() + " online")
    tags.append("buy " + what.lower())
    # top 3 store names as brand tags
    for s in stores[:3]:
        tags.append(s["name"].lower())
    # dedupe preserve order, cap 8
    seen=set(); out=[]
    for t in tags:
        t=t.strip()
        if t and t not in seen:
            seen.add(t); out.append(t)
        if len(out)>=8: break
    return out

def tag_xml(name):
    return '\t\t<category domain="post_tag" nicename="{}"><![CDATA[{}]]></category>'.format(slugify(name), name)

def meta(key, val):
    return ("\t\t<wp:postmeta>\n"
            "\t\t\t<wp:meta_key>{}</wp:meta_key>\n"
            "\t\t\t<wp:meta_value>{}</wp:meta_value>\n"
            "\t\t</wp:postmeta>\n").format(html.escape(key), cdata(val))

def to_gmt(dt_str):
    # treat given local time as GMT-ish for import; WP recalculates. Keep same.
    return dt_str

items = []
pid = 5000   # starting post id (high to avoid clashes)
aid = 6000   # attachment ids

for a in manifest:
    slug = a["slug"]
    d = data[slug]
    fname = os.path.join(ART, "{}-{}.html".format(a["n"], slug.replace("best-websites-","")))
    content = open(fname, encoding="utf-8").read()
    title = a["title"]
    author = AUTHORS[a["author"]]
    cat = a["category"]; catslug = CAT_SLUG[cat]
    date = a["date"]                    # "2026-06-28 09:10:00"
    img = a["img"]
    img_url = "{}/{}".format(IMG_BASE, img)
    focus = d_get_focus = a["focus_kw"]
    metadesc = d.get("meta_desc") or d["quickanswer"][:155]
    excerpt = "Compare the {} ranked on price, trust, shipping, and selection. See our top picks and where to buy.".format(slug.replace("best-websites-","best websites for ").replace("-"," "))
    this_post = pid; pid += 1
    this_att = aid; aid += 1

    # ---- attachment item (the image) ----
    att = []
    att.append("\t<item>")
    att.append("\t\t<title>{}</title>".format(html.escape(title + " featured image")))
    att.append("\t\t<link>{}/{}/</link>".format(SITE, slug))
    att.append("\t\t<pubDate>{}</pubDate>".format(date))
    att.append("\t\t<dc:creator>{}</dc:creator>".format(cdata(author["login"])))
    att.append("\t\t<guid isPermaLink=\"false\">{}</guid>".format(img_url))
    att.append("\t\t<description></description>")
    att.append("\t\t<content:encoded>{}</content:encoded>".format(cdata("")))
    att.append("\t\t<excerpt:encoded>{}</excerpt:encoded>".format(cdata("")))
    att.append("\t\t<wp:post_id>{}</wp:post_id>".format(this_att))
    att.append("\t\t<wp:post_date>{}</wp:post_date>".format(date))
    att.append("\t\t<wp:post_date_gmt>{}</wp:post_date_gmt>".format(to_gmt(date)))
    att.append("\t\t<wp:comment_status>closed</wp:comment_status>")
    att.append("\t\t<wp:ping_status>closed</wp:ping_status>")
    att.append("\t\t<wp:post_name>{}</wp:post_name>".format(slug + "-image"))
    att.append("\t\t<wp:status>inherit</wp:status>")
    att.append("\t\t<wp:post_parent>{}</wp:post_parent>".format(this_post))
    att.append("\t\t<wp:menu_order>0</wp:menu_order>")
    att.append("\t\t<wp:post_type>attachment</wp:post_type>")
    att.append("\t\t<wp:post_password></wp:post_password>")
    att.append("\t\t<wp:is_sticky>0</wp:is_sticky>")
    att.append("\t\t<wp:attachment_url>{}</wp:attachment_url>".format(img_url))
    att.append(meta("_wp_attachment_image_alt", title).rstrip("\n"))
    att.append("\t</item>")

    # ---- post item ----
    it = []
    it.append("\t<item>")
    it.append("\t\t<title>{}</title>".format(html.escape(title)))
    it.append("\t\t<link>{}/{}/</link>".format(SITE, slug))
    it.append("\t\t<pubDate>{}</pubDate>".format(date))
    it.append("\t\t<dc:creator>{}</dc:creator>".format(cdata(author["login"])))
    it.append("\t\t<guid isPermaLink=\"false\">{}/?p={}</guid>".format(SITE, this_post))
    it.append("\t\t<description></description>")
    it.append("\t\t<content:encoded>{}</content:encoded>".format(cdata(content)))
    it.append("\t\t<excerpt:encoded>{}</excerpt:encoded>".format(cdata(excerpt)))
    it.append("\t\t<wp:post_id>{}</wp:post_id>".format(this_post))
    it.append("\t\t<wp:post_date>{}</wp:post_date>".format(date))
    it.append("\t\t<wp:post_date_gmt>{}</wp:post_date_gmt>".format(to_gmt(date)))
    it.append("\t\t<wp:comment_status>open</wp:comment_status>")
    it.append("\t\t<wp:ping_status>open</wp:ping_status>")
    it.append("\t\t<wp:post_name>{}</wp:post_name>".format(slug))
    it.append("\t\t<wp:status>future</wp:status>")
    it.append("\t\t<wp:post_parent>0</wp:post_parent>")
    it.append("\t\t<wp:menu_order>0</wp:menu_order>")
    it.append("\t\t<wp:post_type>post</wp:post_type>")
    it.append("\t\t<wp:post_password></wp:post_password>")
    it.append("\t\t<wp:is_sticky>0</wp:is_sticky>")
    it.append("\t\t<category domain=\"category\" nicename=\"{}\"><![CDATA[{}]]></category>".format(catslug, cat))
    # tags
    for tg in build_tags(focus, d["stores"], d["intro_what"]):
        it.append(tag_xml(tg))
    # link featured image
    it.append(meta("_thumbnail_id", str(this_att)).rstrip("\n"))
    it.append(meta("_rh_focus_keyword", focus).rstrip("\n"))
    it.append(meta("_rh_secondary_keywords", focus + ", where to buy, online stores, 2026").rstrip("\n"))
    it.append(meta("_rh_meta_description", metadesc).rstrip("\n"))
    it.append(meta("_rh_seo_title", title).rstrip("\n"))
    it.append("\t</item>")

    items.append("\n".join(att))
    items.append("\n".join(it))

# authors block
author_xml = ""
for k,au in AUTHORS.items():
    author_xml += ("\t<wp:author>\n"
        "\t\t<wp:author_login>{}</wp:author_login>\n"
        "\t\t<wp:author_email>{}</wp:author_email>\n"
        "\t\t<wp:author_display_name>{}</wp:author_display_name>\n"
        "\t\t<wp:author_first_name></wp:author_first_name>\n"
        "\t\t<wp:author_last_name></wp:author_last_name>\n"
        "\t</wp:author>\n").format(cdata(au["login"]), cdata(au["email"]), cdata(au["display"]))

header = """<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0"
\txmlns:excerpt="http://wordpress.org/export/1.2/excerpt/"
\txmlns:content="http://purl.org/rss/1.0/modules/content/"
\txmlns:wfw="http://wellformedweb.org/CommentAPI/"
\txmlns:dc="http://purl.org/dc/elements/1.1/"
\txmlns:wp="http://wordpress.org/export/1.2/">
<channel>
\t<title>Buy From Best</title>
\t<link>{site}</link>
\t<description>Bulk article import</description>
\t<pubDate>Sat, 27 Jun 2026 00:00:00 +0000</pubDate>
\t<language>en-US</language>
\t<wp:wxr_version>1.2</wp:wxr_version>
\t<wp:base_site_url>{site}</wp:base_site_url>
\t<wp:base_blog_url>{site}</wp:base_blog_url>
{authors}\t<generator>https://wordpress.org/?v=6.5</generator>
""".format(site=SITE, authors=author_xml)

footer = "</channel>\n</rss>\n"

out = header + "\n".join(items) + "\n" + footer
path = os.path.join(BASE, "bulk-articles-import.xml")
open(path, "w", encoding="utf-8").write(out)
print("WROTE", path)
print("posts={} attachments={} size={} KB".format(len(manifest), len(manifest), os.path.getsize(path)//1024))
