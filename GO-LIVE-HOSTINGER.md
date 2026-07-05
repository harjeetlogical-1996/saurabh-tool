# Buy From Best — Go Live on Hostinger (step-by-step)

Site is small (~16MB), so the free All-in-One WP Migration plugin is enough.

## STEP 1 — Buy domain + hosting on Hostinger
1. Go to hostinger.com -> choose a WordPress/Premium hosting plan (Premium is fine to start).
2. During checkout, register the domain: **buyfrombest.com** (often free with annual plan).
3. Complete payment. Note your hPanel login.

## STEP 2 — Install a fresh WordPress on Hostinger
1. In hPanel -> "Websites" -> Add/Manage -> "Install WordPress" (Auto Installer).
2. Set it on buyfrombest.com, pick an admin user/password (SAVE these).
3. Wait for install + SSL (https) to activate (Hostinger does SSL free automatically).

## STEP 3 — Export the local site (All-in-One WP Migration)
On the LOCAL site (reviewshub.local/wp-admin):
1. Plugins -> Add New -> search "All-in-One WP Migration" -> Install + Activate.
2. Left menu: All-in-One WP Migration -> Export -> Export To -> FILE.
3. It builds a single .wpress file -> download it to your PC (~20-30MB).

## STEP 4 — Import on Hostinger
On the LIVE site (buyfrombest.com/wp-admin):
1. Install + Activate "All-in-One WP Migration" there too.
2. (If the .wpress is over the upload limit, also install the free
   "All-in-One WP Migration File Extension" / or use Hostinger's higher limit.)
3. All-in-One WP Migration -> Import -> Import From -> FILE -> pick the .wpress.
4. It replaces the fresh WP with your full site (theme, 25 articles, 101 stores,
   128 reviews, images, schema, settings). Confirm/Proceed.
5. After import: log in again with the LOCAL site's admin user/password
   (import overwrites the login with your local one).

## STEP 5 — Fix URLs + permalinks
1. Settings -> Permalinks -> just click "Save" (re-flushes pretty URLs).
2. The plugin auto-replaces reviewshub.local -> buyfrombest.com. If any old links
   remain, install "Better Search Replace" and run reviewshub.local:10010 -> buyfrombest.com.
3. Check the homepage, an article, /stores/, /guides/ all load on https://buyfrombest.com.

## STEP 6 — Post-launch essentials
1. Settings -> Reading -> ensure "Discourage search engines" is UNCHECKED.
2. Install a caching plugin (LiteSpeed Cache on Hostinger, or WP Rocket) for speed.
3. Google Search Console: add buyfrombest.com, verify, submit /wp-sitemap.xml.
4. Bing Webmaster Tools: same.
5. Google Analytics 4: add tracking.
6. Update the placeholder contact email (hello@reviewshub.com) to a real one
   (e.g. hello@buyfrombest.com via Hostinger email).

## STEP 7 — When AdSense-ready
1. Apply for Google AdSense (15-25 articles + privacy/contact pages = done).
2. After approval, paste your AdSense <ins> code into rh_adsense_code() in
   the theme's functions.php to activate the silent [rh_ad] slots site-wide.

## Notes
- Migration carries EVERYTHING: posts, stores, reviews, dates, schema, theme, settings.
- The Classic Editor + custom theme + all inc/ files move with the import.
- Keep the .wpress backup file safe.
