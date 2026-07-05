# wptaskify Plugin — Feature-Parity Build Plan

Goal: bring the plugin to Yoast/Rank Math parity for the basics, while keeping our
AI + AEO/GEO edge. Built in ordered batches; each batch = code + deploy + test.

Legend: ✅ already exists · 🟡 partial (engine there, needs UI/fields) · ❌ missing

---

## What already exists (DO NOT rebuild)
- ✅ Schema engine emits: Article, Product, HowTo, FAQPage, BreadcrumbList,
  Organization, Person, WebSite (class-schema.php)
- ✅ Per-post meta: title, description, focus_kw, keywords, og_title, og_desc,
  og_image, canonical, noindex, schema_type, faq (wppseo_meta_keys)
- ✅ Meta description + OG/Twitter tags (class-frontend.php)
- ✅ Focus keyword + SEO score (class-score.php), AI SEO score AEO/GEO/E-E-A-T
  (class-aiseo.php)
- ✅ XML sitemap (class-sitemap.php), llms.txt (class-llms.php)
- ✅ FAQPage schema per post (faq field)

---

## BATCH 1 — Site-wide identity & homepage (P1: Knowledge Graph + homepage)
The biggest "looks incomplete" gaps. All settings-page work.
- 🟡 **Organization/Person setup**: admin fields — site is Organization or Person,
  name, logo, sameAs[] (social profiles), knowsAbout[]. Wire into the existing
  Organization/Person schema so it's emitted site-wide. (engine exists, no UI)
- ❌ **Homepage / blog-page SEO**: dedicated title, description, schema controls
  for the front page and posts page.
- ❌ **Site-wide default OG image**: fallback chain = per-post og_image →
  featured image → site default. (per-post + featured exist; add the default)

## BATCH 2 — Taxonomy & archive SEO (P1: the Yoast basic we lack)
- ❌ Editable meta **title/description** for: categories, tags, custom taxonomies,
  author archives. New meta storage keyed by term/author + a UI on term-edit
  screens. Frontend must output these on archive pages.

## BATCH 3 — Per-post schema UX + AEO fields (P2 #5,6 + AEO list #1-5)
- 🟡 **Schema-type dropdown** in the post metabox: Article / Product / Recipe /
  HowTo / FAQ / LocalBusiness, showing the right sub-fields per type. (schema_type
  meta exists; add the UI + Recipe + LocalBusiness to the engine)
- ❌ **AEO/E-E-A-T fields** (our USP, WP has none): quick_answer, key_takeaways,
  reviewed_by, last_reviewed (distinct from modified date), speakable, inLanguage.
  Add as meta keys + metabox fields + schema/OG output.
- ❌ **article:* OG tags**, **sameAs** on entities (partly Batch 1).

## BATCH 4 — Breadcrumb block + polish (P2 #7,8)
- ✅ BreadcrumbList schema already emitted.
- ❌ Visual breadcrumb **shortcode/block** `[wptaskify_breadcrumbs]` for themes
  that don't render one.

## BATCH 5 — Redirect manager / 404 awareness (P1 #4)
- ❌ Redirect manager (source→target, 301/302) + 404 log. (We already integrate
  the Redirection plugin via MCP tools; decide: build native, or lean on that +
  surface it in admin.)

## BATCH 6 — AI-management differentiators (AEO list #13,14,16,17)
- ❌ **Undo/rollback + AI action log** for meta/settings changes (not just posts).
- 🟡 Site-audit endpoint with IDs — MCP audit tools exist; add a plugin-side
  audit surface if needed.
- ❌ Content decay / freshness tracking.
- ✅ Bulk ops with dry-run (MCP side) — keep.

---

## Working rules
- Every batch: bump plugin version, repackage zip (forward-slash paths), deploy,
  verify update.json version, smoke test.
- Keep the full plugin and the WP.org lite `_lite_src/` in sync for shared SEO code.
- Never add Studio/updater to the lite version.
- Self-protection (own plugin read-only) must stay intact through all edits.
