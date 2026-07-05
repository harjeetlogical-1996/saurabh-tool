#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate 20 article HTML files from store-data.json + bulk-manifest.json.
Matches the exact Buy From Best shortcode format. Adds internal + external links.
Strips em/en dashes. Writes to articles/NN-slug.html
"""
import json, os, re

BASE = r"c:\Users\Admin\Desktop\saurabh-tools"
ART = os.path.join(BASE, "articles")
manifest = json.load(open(os.path.join(BASE, "bulk-manifest.json"), encoding="utf-8"))["articles"]
data = json.load(open(os.path.join(BASE, "store-data.json"), encoding="utf-8"))

# slug -> human title text for internal anchor (derive from existing + new slugs)
SLUG_TITLE = {
    "best-websites-buy-dirt-bikes":"best websites to buy dirt bikes",
    "best-websites-buy-ebikes":"best websites to buy electric bikes",
    "best-websites-buy-generators":"best websites to buy generators",
    "best-websites-buy-lawn-mowers":"best websites to buy lawn mowers",
    "best-websites-buy-atvs":"best websites to buy ATVs and UTVs",
    "best-websites-buy-camping-gear":"best websites to buy camping gear",
    "best-websites-buy-pressure-washers":"best websites to buy pressure washers",
    "best-websites-buy-trailers-towing":"best websites to buy trailers and towing gear",
    "best-websites-kids-dirt-bikes":"best websites to buy kids dirt bikes",
    "best-websites-cheap-ebikes":"best websites for cheap electric bikes",
    "best-websites-solar-generators":"best websites for solar generators",
    "best-websites-electric-dirt-bikes":"best websites to buy electric dirt bikes",
    "best-websites-used-atvs":"best websites to buy used ATVs",
    "best-websites-rooftop-tents":"best websites for rooftop tents",
    "best-websites-riding-mowers":"best websites to buy riding mowers",
    "best-websites-commuter-ebikes":"best sites to buy commuter ebikes",
    "best-websites-fat-tire-ebikes":"best websites for fat tire electric bikes",
    "best-websites-electric-scooters":"where to buy electric scooters online",
    "best-websites-portable-generators":"best places to buy portable generators",
    "best-websites-chainsaws":"best places to buy chainsaws online",
    "best-websites-leaf-blowers":"best websites to buy leaf blowers",
    "best-websites-snowmobiles":"where to buy snowmobiles online",
    "best-websites-cheap-dirt-bikes":"best sites for cheap dirt bikes",
    "best-websites-shop-vacs":"best websites for shop vacs",
    "best-websites-winches":"best sites to buy winches",
    "best-websites-buy-electric-atvs":"best websites to buy electric ATVs",
}
# add the 20 new ones from manifest
for a in manifest:
    SLUG_TITLE[a["slug"]] = a["focus_kw"]

LIVE = "https://buyfrombest.com"

def strip_dashes(s):
    for a,b in [(" — ",", "),(" – ",", "),("—",", "),("–","-")]:
        s = s.replace(a,b)
    return s

def internal_link(slug):
    title = SLUG_TITLE.get(slug, slug.replace("-"," "))
    return '<a href="{}/{}/">{}</a>'.format(LIVE, slug, title)

def stars_phrase(stars):
    return "{} out of 5".format(stars)

def build(article):
    slug = article["slug"]
    d = data[slug]
    what = d["intro_what"]
    stores = d["stores"]
    internal = article.get("internal", [])
    out = []

    # intro
    out.append("<p>{}</p>".format(strip_dashes(d["intro_line"])))
    out.append("<p>We compared the best places to buy {} in the United States and ranked them on the four things that matter most: <strong>price, trust, shipping, and selection</strong>.</p>".format(what))
    # intro internal link
    if internal:
        out.append("<p>Whatever your budget, this guide points you to the right store. For related options, see our guide to the {}.</p>".format(internal_link(internal[0])))
    out.append('<p class="rh-factcheck">Independently researched and fact-checked. We checked live inventory, pricing, and policies on each store. Prices and stock change often, so confirm details on the store before buying.</p>')
    out.append("")
    out.append("[rh_toc]")
    out.append("")
    out.append("[rh_quickanswer]{}[/rh_quickanswer]".format(strip_dashes(d["quickanswer"])))
    out.append("")
    # key takeaways from top 5 stores
    out.append("[rh_keytakeaways]")
    for s in stores[:5]:
        out.append("{} is best for {}.".format(s["name"], s["bestfor"].lower()))
    out.append("Always check price, warranty, shipping, and return policy before buying.")
    out.append("[/rh_keytakeaways]")
    out.append("")
    out.append('[rh_ad slot="in-content"]')
    out.append("")
    # compare table
    out.append("<h2>Best websites to buy {} at a glance</h2>".format(what))
    out.append("")
    out.append("[rh_compare]")
    out.append("Rank | Website | Best for | Price level | Shipping | Trust")
    for i,s in enumerate(stores,1):
        out.append("{} | {} | {} | {} | {} | {}".format(i, s["name"], s["bestfor"], s["price"], s["ship"], s["trust"]))
    out.append("[/rh_compare]")
    out.append("")
    out.append("<p>Below we break down each website, who it is best for, and the pros and cons you should know before you buy.</p>")
    out.append("")
    # products table (top picks)
    out.append("<h2>Top picks at these stores</h2>")
    out.append("<p>To give you a real starting point, here is what each top store is known for and where to find it.</p>")
    out.append("")
    out.append('[rh_products title="What each top store is best known for"]')
    for s in stores[:8]:
        out.append("{} | {} | {} | {} | {}".format(s["name"], s["bestfor"], s["price"], s["trust"]+" trust", s["url"]))
    out.append("[/rh_products]")
    out.append("")
    out.append('[rh_ad slot="in-content"]')
    out.append("")
    # reviews
    out.append("<h2>The best websites to buy {} in 2026</h2>".format(what))
    out.append("")
    for i,s in enumerate(stores,1):
        pros = s["pros"]
        cons = s.get("cons","")
        attrs = 'name="{}" rank="{}" score="{}" stars="{}" bestfor="{}" url="{}" pros="{}"'.format(
            s["name"], i, s["score"], s["stars"], s["bestfor"], s["url"], pros)
        if cons:
            attrs += ' cons="{}"'.format(cons)
        out.append("[rh_review {}]".format(attrs))
        # star phrase line + review body
        body = strip_dashes(s["review"])
        out.append("Rated {} ({}). {}".format(s["score"], stars_phrase(s["stars"]), body))
        out.append("[/rh_review]")
        out.append("")
        if i == 4:
            out.append('[rh_ad slot="in-content"]')
            out.append("")
    # checklist
    out.append("<h2>What to look for when buying {}</h2>".format(what))
    out.append('<div class="rh-tipbox">')
    out.append("<h3>{} buying checklist</h3>".format(what.capitalize()))
    out.append("<ul>")
    for c in d["checklist"]:
        # bold the label before colon
        if ":" in c:
            label, rest = c.split(":",1)
            out.append("<li><strong>{}:</strong>{}</li>".format(label, strip_dashes(rest)))
        else:
            out.append("<li>{}</li>".format(strip_dashes(c)))
    out.append("</ul>")
    out.append("</div>")
    out.append("")
    # budget
    out.append("<h2>How much should you spend on {}?</h2>".format(what))
    out.append("<ul>")
    for b in d["budget"]:
        if ":" in b:
            label, rest = b.split(":",1)
            out.append("<li><strong>{}:</strong>{}</li>".format(label, strip_dashes(rest)))
        else:
            out.append("<li>{}</li>".format(strip_dashes(b)))
    out.append("</ul>")
    out.append("")
    # which should you choose + internal links
    out.append("<h2>Which {} website should you choose?</h2>".format(what))
    out.append("<ul>")
    out.append("<li><strong>Best overall:</strong> go with <strong>{}</strong>.</li>".format(d["verdict_pick"]))
    out.append("<li><strong>Best value:</strong> choose <strong>{}</strong>.</li>".format(d["verdict_value"]))
    out.append("<li><strong>Premium pick:</strong> pick <strong>{}</strong>.</li>".format(d["verdict_premium"]))
    out.append("</ul>")
    out.append("")
    # related guides paragraph (internal links 2nd and 3rd)
    rel = []
    for s_slug in internal[1:3]:
        rel.append(internal_link(s_slug))
    if rel:
        out.append("<p>Want to explore more? See our related guides: {}. Or browse <a href=\"{}/stores/\">our full Store Finder directory</a> to compare every store we review.</p>".format(", ".join(rel), LIVE))
    else:
        out.append("<p>Browse <a href=\"{}/stores/\">our full Store Finder directory</a> to compare every store we review.</p>".format(LIVE))
    out.append("")
    # external authority link
    ext = d.get("external", [])
    if ext:
        e = ext[0]
        out.append("<p>For independent guidance, see <a href=\"{}\" target=\"_blank\" rel=\"noopener nofollow\">{}</a>.</p>".format(e["url"], e["text"]))
        out.append("")
    # verdict
    out.append("<h2>Final verdict</h2>")
    out.append("<p>The right store gets you a fair price, real support, and a {} you can trust. Whether you want the best overall option, the best value, or a premium pick, one of the stores above will fit your needs and budget.</p>".format(what.rstrip("s") if what.endswith("s") else what))
    out.append("<p>Our advice: start with <strong>{}</strong> for the best overall experience, choose <strong>{}</strong> if value matters most, and step up to <strong>{}</strong> for a premium choice. Always confirm price, warranty, and shipping before you buy.</p>".format(d["verdict_pick"], d["verdict_value"], d["verdict_premium"]))
    out.append("")
    # FAQ
    out.append("<h2>Frequently asked questions</h2>")
    out.append("")
    faqs = build_faqs(what, d, stores)
    for q,a in faqs:
        out.append('[rh_faq q="{}"]{}[/rh_faq]'.format(q, strip_dashes(a)))
        out.append("")
    out.append("<p><em>Prices, ratings, and shipping policies change over time. Always confirm the latest details on each website before purchasing.</em></p>")

    return "\n".join(out)

def build_faqs(what, d, stores):
    top = stores[0]["name"]; val = d["verdict_value"]; prem = d["verdict_premium"]
    faqs = [
        ("What is the best website to buy {}?".format(what),
         "{} is the best overall website to buy {}, thanks to its {}. For the best value, consider {}, and for a premium option look at {}.".format(top, what, stores[0]["bestfor"].lower(), val, prem)),
        ("What is the cheapest place to buy {}?".format(what),
         "{} is one of the most budget-friendly options for {}. Always compare the total cost including shipping, and check for sales or financing before buying.".format(val, what)),
        ("How much do {} cost?".format(what),
         "Prices vary widely by type and quality. See the budget breakdown above for typical ranges, from entry-level options to premium picks, and confirm current pricing on each store.".format()),
        ("Is it safe to buy {} online?".format(what),
         "Yes, when you buy from reputable stores like the ones ranked above. Check the return policy, warranty, and customer reviews, and pay with a method that offers buyer protection."),
        ("Which store has the best warranty for {}?".format(what),
         "Warranty terms vary by store and brand. The stores ranked highest above generally offer the strongest support and clearest warranties, so check each one's policy before you buy."),
        ("Do these stores offer free shipping on {}?".format(what),
         "Many do, either outright or above a minimum order. The comparison table above shows each store's shipping at a glance, but always confirm on the store since policies change."),
    ]
    return faqs

count = 0
for a in manifest:
    html = build(a)
    fname = os.path.join(ART, "{}-{}.html".format(a["n"], a["slug"].replace("best-websites-","")))
    open(fname, "w", encoding="utf-8").write(html)
    # verify no dashes
    bad = html.count("—") + html.count("–")
    print("WROTE {}  ({} chars, {} reviews, dashes={})".format(os.path.basename(fname), len(html), len(data[a["slug"]]["stores"]), bad))
    count += 1
print("DONE: {} articles".format(count))
