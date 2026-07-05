# Buy From Best — Workflow after going live

Two separate things, two separate rules. NEVER mix.

## RULE 1 — CONTENT lives on LIVE only
Articles, stores, reviews, page edits, menus, settings = ALWAYS done on the
live site (buyfrombest.com/wp-admin) after launch.
- Write new articles directly on live.
- Approve user reviews on live.
- NEVER create content on local after launch (it would conflict).
- Local's database becomes a stale snapshot; that's fine, it's only for code testing.

## RULE 2 — CODE/DESIGN built on LOCAL, then uploaded
Theme files (PHP, CSS, JS) = build + test on local first, then upload ONLY the
changed theme files to live. This never touches the live database, so live
content/reviews stay safe.

Files that change for code/design work (all inside the theme folder):
  wp-content/themes/reviewshub/
    - style.css, functions.php, header.php, footer.php, sidebar.php
    - single.php, page-*.php, category.php, author.php, comments.php
    - inc/*.php  (seo, geo-schema, store-cpt, store-sync, store-rest, reviews)
    - assets/js/*.js  (stores.js, loader.js)

### How to push a code change to live
1. I make + test the change on local.
2. You upload the changed file(s) to live via:
   - Hostinger hPanel -> File Manager, OR
   - FTP (FileZilla) into /public_html/wp-content/themes/reviewshub/
   Overwrite the same file path. Done. No database, no migration.
3. Bump the version in functions.php (style/js ?ver=) so caches refresh,
   or clear the cache plugin on live.

## What NOT to do
- Do NOT re-run All-in-One migration after launch (it overwrites the live
  database and would delete live content + real user reviews).
- Do NOT edit content on local after launch.
- Do NOT edit theme files directly on live (test on local first).

## Quick mental model
- New article / store / review  -> LIVE wp-admin
- New feature / design / bugfix -> LOCAL (I build) -> upload theme file(s) -> LIVE

## Optional later (advanced, if you grow)
- Use a staging site (Hostinger has 1-click staging) to test big changes,
  then "push to live" which can merge code without wiping content.
