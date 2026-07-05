# WordPress.org Submission Guide — wptaskify SEO (free/lite)

The free plugin is packaged at: `plugin/wptaskify-seo.zip`
(Plugin: **wptaskify SEO**, slug: `wptaskify-seo`, version 1.0.0.)

This is the SEO-only edition — safe for WordPress.org. The full version (with the Studio
file/theme/plugin editing + self-hosted updater) stays on wptaskify.com and is NOT
submitted, because those features are disallowed on WordPress.org.

---

## Why a separate lite version?

WordPress.org's guidelines forbid:
- Arbitrary file/code writing or a plugin/theme editor (our "Studio" module).
- Self-hosted auto-updaters (WP.org uses its own update system).

So the lite version removes `class-studio-fs.php`, `class-studio-rest.php`, and
`class-updater.php`, and ships only: SEO meta, focus keyword + score, schema, Open Graph,
Twitter cards, canonical/noindex, XML sitemap, AI SEO Score, and an **optional** AI
connector (fully disclosed in the readme's "External services" section).

---

## Step 1 — Create a WordPress.org account
- Sign up at https://login.wordpress.org/register (free). This account owns the plugin.

## Step 2 — Submit the plugin for review
1. Go to https://wordpress.org/plugins/developers/add/
2. Upload `wptaskify-seo.zip`.
3. Submit. You'll get an automated email, then a **human review** (a volunteer reads the
   code). This can take **a few days to a few weeks** (free, queue-based).
4. If they ask for changes, fix and reply with an updated zip. Common asks:
   - Escape all output, sanitize all input (we already do).
   - Confirm the external-service disclosure (already in readme "External services").
   - Prefix everything (we use `wppseo_` / `WPPSEO_`).

## Step 3 — After approval: SVN (not Git)
- WordPress.org gives you an **SVN repo**: `https://plugins.svn.wordpress.org/wptaskify-seo/`
- Layout:
  - `/trunk/` — current development copy (put the plugin files here)
  - `/tags/1.0.0/` — a snapshot of each released version
  - `/assets/` — banner, icon, screenshots (NOT shipped in the zip)
- Basic flow:
  ```bash
  svn co https://plugins.svn.wordpress.org/wptaskify-seo/ wptaskify-seo-svn
  # copy the unzipped plugin files into trunk/
  cp -r wptaskify-seo/* wptaskify-seo-svn/trunk/
  cd wptaskify-seo-svn
  svn add trunk/* --force
  # tag the release
  svn cp trunk tags/1.0.0
  svn ci -m "Release 1.0.0" --username YOURUSER
  ```
- The **Stable tag** in readme.txt (1.0.0) must match a `/tags/1.0.0/` folder.

## Step 4 — Assets (uploaded to /assets/ in SVN, not the zip)
Create and add these to the SVN `assets/` directory:
- **Icon:** `icon-128x128.png` and `icon-256x256.png` (square logo)
- **Banner:** `banner-772x250.png` and `banner-1544x500.png`
- **Screenshots:** `screenshot-1.png`, `screenshot-2.png`, `screenshot-3.png`
  (matching the "== Screenshots ==" list in readme.txt — order matters)

## Step 5 — Verify the listing
- After `svn ci`, the plugin appears at `https://wordpress.org/plugins/wptaskify-seo/`
  within ~15 minutes.
- Check: readme renders, screenshots show, "Tested up to" and version are right.

---

## Pre-submission checklist (already handled in the zip)
- [x] Text Domain `wptaskify-seo` matches the slug, used in all `__()`/`esc_html__()` calls.
- [x] `ABSPATH` guard at top of every PHP file.
- [x] All prefixes `wppseo_` / `WPPSEO_` (no unprefixed globals).
- [x] Activation/deactivation hooks; `uninstall.php` cleans up with `esc_like` + `prepare`.
- [x] readme.txt in WP.org format with FAQ, Screenshots, Changelog, Upgrade Notice, and a
      full **External services** disclosure for the optional wptaskify connection.
- [x] No banned features (no file editor, no arbitrary code, no self-hosted updater).
- [x] Stable tag (1.0.0) matches the plugin Version.

## You still need to create (I can't):
- The WordPress.org account + the actual submission (your identity).
- The icon / banner / screenshot images.
- (Optional but recommended) a short demo GIF for the description.

## Keeping full vs lite in sync (later)
When you change shared SEO code, update it in BOTH the full plugin
(`plugin/wp-pilot-seo.zip` source) and the lite source (`plugin/_lite_src/`), then
re-zip. The lite version should never gain Studio/updater code, or WP.org will pull it.
