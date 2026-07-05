=== wptaskify SEO ===
Contributors: wptaskify
Tags: seo, meta description, schema, sitemap, open graph
Requires at least: 5.6
Tested up to: 6.8
Requires PHP: 7.4
Stable tag: 1.0.0
License: GPLv2 or later
License URI: https://www.gnu.org/licenses/gpl-2.0.html

Free, full-featured SEO for WordPress: meta titles & descriptions, focus keywords with a live score, schema, Open Graph, XML sitemap, and an AI-era SEO scorecard.

== Description ==

wptaskify SEO gives you everything you need to rank, for free:

* **SEO title & meta description** with a live Google-style snippet preview
* **Focus keyword** and secondary keywords with a real-time SEO score
* **Open Graph (Facebook)** and **Twitter Card** tags
* **Canonical URLs** and **noindex** control
* **JSON-LD structured data**: Organization, WebSite, Breadcrumb, Article, Product, FAQPage, HowTo
* **Automatic XML sitemap**
* **AI SEO Score** - a site-wide scorecard across On-Page, Technical, AEO (answer-engine) and GEO (AI-citation), measured from your own published content

= AI-era SEO (AEO & GEO) =

Search is changing. Answer engines like ChatGPT, Perplexity, Claude and Google AI
Overviews increasingly answer questions directly and cite sources. wptaskify SEO helps
you structure content so it can be understood and cited by these engines, with FAQ and
Article schema, clean metadata, and an AI SEO Score that highlights what to improve.

= Optional: connect to AI (Claude & ChatGPT) =

You can optionally connect your site to **wptaskify** so an AI assistant (Claude or
ChatGPT) can read and update your SEO for you through a secure connector. This is
entirely optional - the SEO features above work on their own without connecting.

== External services ==

This plugin can OPTIONALLY connect your site to the third-party service **wptaskify**
(https://wptaskify.com). You only connect if you click "Connect to AI" in the plugin;
nothing is sent otherwise.

* **What is sent, and when:** When you click "Connect to AI", the plugin creates a
  WordPress Application Password and sends your **site URL, your WordPress username, your
  account email, and that Application Password** to wptaskify so it can act on your
  behalf. When you click "Disconnect", your site URL is sent to wptaskify to remove the
  connection.
* **Why:** So an AI assistant you authorize can manage your SEO (read and write SEO
  fields, schema and sitemap) on your instruction.
* **Service provider:** wptaskify - Terms: https://wptaskify.com/terms - Privacy:
  https://wptaskify.com/privacy

If you do not use the "Connect to AI" feature, this plugin makes no external requests.

== Installation ==

1. Upload the plugin to `/wp-content/plugins/`, or install it from Plugins > Add New.
2. Activate it.
3. Edit any post or page - the SEO box appears below the editor with a live snippet
   preview and score.
4. (Optional) Open **wptaskify SEO > Connect to AI** to let Claude or ChatGPT manage
   your SEO.

== Frequently Asked Questions ==

= Is this plugin free? =

Yes. All SEO features (meta, schema, Open Graph, sitemap, SEO score) are free and work
without any account.

= Do I have to connect to wptaskify? =

No. Connecting is optional. The SEO features work on their own. Connect only if you want
an AI assistant to manage your SEO for you.

= Does it work with the block editor and classic editor? =

Yes, both. The SEO box and live snippet preview appear in each.

= Will it conflict with another SEO plugin? =

Run one SEO plugin at a time to avoid duplicate meta tags. Deactivate other SEO plugins
before using this one.

= What data leaves my site? =

Nothing, unless you click "Connect to AI". See the "External services" section above for
exactly what is sent when you connect.

== Screenshots ==

1. The SEO box below the editor with a live Google snippet preview and score.
2. The site-wide AI SEO Score with On-Page, Technical, AEO and GEO breakdown.
3. The optional "Connect to AI" page.

== Changelog ==

= 1.0.0 =
* Initial release: SEO meta, focus keyword + score, schema (Article, FAQ, HowTo,
  Product, Organization, WebSite, Breadcrumb), Open Graph, Twitter Cards, canonical,
  noindex, XML sitemap, AI SEO Score, and an optional AI connector.

== Upgrade Notice ==

= 1.0.0 =
Initial release.
