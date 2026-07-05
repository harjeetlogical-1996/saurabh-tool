#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Add clean, complete meta_desc (150-158 chars) to each entry in store-data.json."""
import json, os
BASE = r"c:\Users\Admin\Desktop\saurabh-tools"
p = os.path.join(BASE, "store-data.json")
d = json.load(open(p, encoding="utf-8"))

# Hand-written meta descriptions: keyword-led, names the top pick + value pick, ends clean.
META = {
 "best-websites-beginner-dirt-bikes":"Looking for the best websites to buy beginner dirt bikes? We rank Tribal Motorsports, MotoBuys, GoKarts USA and more on price, trust, shipping and choice.",
 "best-websites-refurbished-electric-bikes":"The best websites to buy refurbished electric bikes, ranked. Upway, Trek Red Barn Refresh and The Pro's Closet compared on warranty, price and selection.",
 "best-websites-buy-utvs-side-by-sides":"The best websites to buy UTVs and side-by-sides, ranked. Compare ATV Trader, RideNow, Polaris and Can-Am on price, trust, shipping and selection.",
 "best-websites-standby-generators":"The best websites to buy standby generators, ranked. Electric Generators Direct, Home Depot, Lowe's and Generac compared on price, trust and support.",
 "best-websites-dirt-bike-gear-helmets":"The best websites to buy dirt bike gear and helmets, ranked. BTO Sports, Rocky Mountain ATV/MC and RevZilla compared on price, brands and service.",
 "best-websites-string-trimmers":"The best websites to buy string trimmers, ranked. Home Depot, Lowe's, Amazon and Husqvarna compared on price, power type, trust and shipping.",
 "best-websites-buy-jet-skis":"The best websites to buy jet skis and personal watercraft, ranked. PWC Trader, RideNow, Sea-Doo and Yamaha compared on price, trust and selection.",
 "best-websites-portable-power-stations":"The best websites to buy power stations, ranked. EcoFlow, Anker SOLIX, Bluetti and Jackery compared on capacity, price, warranty and value.",
 "best-websites-trailer-hitches":"The best websites to buy trailer hitches, ranked. etrailer, U-Haul, CURT and Draw-Tite compared on fitment, price, install and trust.",
 "best-websites-camping-coolers":"The best websites to buy camping coolers, ranked. YETI, RTIC, Amazon and REI compared on ice retention, price, durability and shipping.",
 "best-websites-used-dirt-bikes":"The best websites to buy used dirt bikes, ranked. Cycle Trader, MX Locker, eBay and Facebook Marketplace compared on price, trust and selection.",
 "best-websites-ebike-batteries":"The best websites to buy ebike batteries, ranked. EM3ev, eBikeling, DJ Bikes and brand sites compared on cell quality, warranty and price.",
 "best-websites-buy-trailers":"The best websites to buy trailers online, ranked. TrailersPlus, Renown Cargo Trailers and Trailer Trader compared on price, quality and delivery.",
 "best-websites-robotic-lawn-mowers":"The best websites to buy robotic lawn mowers, ranked. Segway Navimow, Husqvarna, Worx and Amazon compared on navigation, price and lawn size.",
 "best-websites-off-road-recovery-gear":"The best websites to buy off-road recovery gear, ranked. Overland Vehicle Systems, TrailRecon and ExtremeTerrain compared on quality and price.",
 "best-websites-commercial-pressure-washers":"The best websites to buy commercial pressure washers, ranked. PowerWash.com, Water Cannon, Hotsy and Landa compared on power, price and support.",
 "best-websites-atv-utv-parts":"The best websites to buy ATV and UTV parts, ranked. SuperATV, Rocky Mountain ATV/MC and UTVSource compared on fitment, selection and price.",
 "best-websites-emergency-backup-power":"The best websites to buy emergency backup power, ranked. EcoFlow, Anker SOLIX, Bluetti and Best Buy compared on capacity, price and support.",
 "best-websites-tie-down-straps":"The best websites to buy tie-down straps and towing accessories, ranked. Rhino USA, US Cargo Control and Vulcan Brands compared on ratings and price.",
 "best-websites-floor-scrubbers":"The best websites to buy industrial floor scrubbers, ranked. SweepScrub, Floor Scrubber USA, Karcher and Tennant compared on size, price and support.",
}

bad=0
for slug, md in META.items():
    if slug not in d:
        print("MISSING in data:", slug); continue
    d[slug]["meta_desc"] = md
    n = len(md)
    flag = "" if 140 <= n <= 160 else "  <-- LEN " + str(n)
    if flag: bad+=1
    print("{:3d}  {}{}".format(n, slug, flag))

json.dump(d, open(p,"w",encoding="utf-8"), indent=2, ensure_ascii=False)
print("\nSaved. {} out-of-range.".format(bad))
