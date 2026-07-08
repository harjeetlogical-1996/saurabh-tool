"""
Server-rendered HTML pages for the WP MCP SaaS.
Modern dark theme (Space Grotesk + DM Sans, slate + green accent),
glassmorphism, SVG icons. No build step - pure HTML/CSS strings.
"""
import json  # used by the services pages' FAQ/Service schema

BRAND = "wptaskify"  # product name

# AI tools grouped by category (shown to users in the dashboard).
TOOL_GROUPS = [
    ("Content & Articles", [
        ("Write & publish articles", "Create a full SEO article and publish it"),
        ("Edit & update posts", "Rewrite, expand or update any post"),
        ("Schema-safe editing", "Update content without breaking structured data"),
        ("Bulk find & replace", "Change text across all posts at once"),
        ("Schedule posts", "Auto-publish at a future date"),
        ("Pages: create & edit", "Manage your site's pages"),
    ]),
    ("AI Images", [
        ("Generate featured images", "AI-create and set a post's featured image"),
        ("In-article images", "Generate images inside the article body"),
        ("Standalone images", "Add AI images to your media library"),
        ("Upload from URL", "Pull any image into the media library"),
    ]),
    ("SEO", [
        ("SEO meta (title/description)", "Set meta title, description & focus keyword"),
        ("On-page SEO audit", "Score a page and list fixes"),
        ("Internal link suggestions", "Find relevant posts to link to"),
        ("Broken link checker", "Find & fix 404 links"),
        ("Thin content finder", "Spot pages that need more depth"),
        ("Missing alt-text & excerpts", "Auto-fill image alt text & meta"),
        ("Redirects & 404 log", "Create redirects, view 404s"),
        ("Sitemap ping", "Notify search engines of changes"),
    ]),
    ("Organize & Manage", [
        ("Categories & tags", "Create and assign taxonomies"),
        ("Authors", "Assign authors to posts"),
        ("Comments moderation", "Approve, spam or delete comments"),
        ("Navigation menus", "Edit site menus"),
        ("Revisions & restore", "Roll back to a previous version"),
        ("Site search & info", "Search content, view site stats"),
    ]),
]
# Number of showcased tools in the curated groups above (a subset shown as examples).
TOOL_COUNT = sum(len(t) for _, t in TOOL_GROUPS)
# The ACTUAL number of MCP tools the product ships (100+). Use this for the
# customer-facing "100+ tools" claim - not TOOL_COUNT, which is only the showcase subset.
TOTAL_TOOLS = 100

# Friendly display names for internal plan keys (never show the raw key to users).
_PLAN_LABELS = {
    "free": "Free", "owai_mini": "Mini", "owai_starter": "Starter", "owai_pro": "Pro",
    "chat_starter": "Chat Starter", "chat_pro": "Chat Pro", "chat_max": "Chat Max",
    "pro": "Pro", "agency": "Agency",
}


def plan_label(key):
    """Human-friendly plan name for a plan key (falls back to a title-cased key)."""
    return _PLAN_LABELS.get(key, (key or "Free").replace("_", " ").title())

# ---------------------------------------------------------------------------
# Shared CSS (design tokens + components)
# ---------------------------------------------------------------------------
_CSS = """
:root{
  --bg:#0A0A0A; --bg2:#050505; --surface:#141414; --surface2:#1C1C1C;
  --primary:#1A1A1A; --accent:#F97316; --accent-hi:#FB923C; --accent-2:#F97316;
  --accent-dim:rgba(249,115,22,.12);
  --fg:#F5F5F5; --muted:#A1A1A1; --muted2:#6B6B6B; --border:#262626; --border-hi:#3A3A3A;
  --danger:#EF4444; --radius:14px; --radius-lg:22px; --maxw:1120px;
  --shadow:0 10px 40px -12px rgba(0,0,0,.7); --glow:0 0 60px -10px rgba(249,115,22,.35);
  --grad:#F97316;
}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--fg);
  font-family:'Inter',system-ui,-apple-system,sans-serif;
  font-size:16px;line-height:1.6;-webkit-font-smoothing:antialiased;
  background-image:radial-gradient(900px 500px at 80% -10%,rgba(249,115,22,.10),transparent 60%),
                   radial-gradient(700px 500px at 10% 0%,rgba(249,115,22,.05),transparent 55%);}
h1,h2,h3,h4{font-family:'Sora',sans-serif;font-weight:700;line-height:1.15;margin:0 0 .4em;letter-spacing:-.02em}
h1{font-size:clamp(2.1rem,5vw,3.6rem)}
h2{font-size:clamp(1.6rem,3.5vw,2.4rem)}
p{margin:0 0 1rem;color:var(--muted)}
a{color:var(--accent);text-decoration:none}
.wrap{max-width:var(--maxw);margin:0 auto;padding:0 24px}
.muted{color:var(--muted)}
.center{text-align:center}

/* nav */
.nav{position:sticky;top:0;z-index:50;backdrop-filter:blur(14px);
  background:rgba(10,10,10,.78);border-bottom:1px solid var(--border)}
.nav .wrap{display:flex;align-items:center;justify-content:space-between;height:66px}
.logo{display:flex;align-items:center;gap:10px;font-family:'Sora';font-weight:700;font-size:1.15rem;color:var(--fg)}
.logo svg{color:var(--accent)}
.nav-links{display:flex;align-items:center;gap:26px}
.nav-links a:not(.btn){color:var(--muted);font-weight:500;font-size:.95rem;transition:color .2s}
.nav .btn{padding:8px 16px;font-size:.88rem;border-radius:10px}
.nav-links a:not(.btn):hover{color:var(--fg)}

/* buttons */
.btn{display:inline-flex;align-items:center;gap:8px;font-family:'Sora';
  font-weight:600;font-size:.98rem;padding:12px 22px;border-radius:var(--radius);
  cursor:pointer;border:1px solid transparent;transition:transform .15s,box-shadow .2s,background .2s;
  text-decoration:none;white-space:nowrap}
.btn:active{transform:scale(.97)}
.btn-primary{background:var(--accent);color:#fff;font-weight:700;box-shadow:var(--glow)}
.btn-primary:hover{background:var(--accent-hi)}
.btn-ghost{background:transparent;color:var(--fg);border-color:var(--border-hi)}
.btn-ghost:hover{background:var(--surface2);border-color:var(--accent)}
.btn-block{width:100%;justify-content:center}
.btn-lg{padding:15px 30px;font-size:1.05rem}

/* hero */
.hero{padding:84px 0 60px;text-align:center}
.badge{display:inline-flex;align-items:center;gap:8px;background:var(--accent-dim);
  color:var(--accent-hi);border:1px solid rgba(249,115,22,.25);padding:7px 15px;
  border-radius:999px;font-size:.85rem;font-weight:500;margin-bottom:26px}
.badge .dot{width:7px;height:7px;border-radius:50%;background:var(--accent);box-shadow:0 0 8px var(--accent)}
.hero h1{max-width:20ch;margin-inline:auto}
.hero .grad{background:linear-gradient(120deg,#fff 15%,var(--accent-hi),var(--accent-2));-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
.hero p.lead{font-size:1.2rem;max-width:60ch;margin:18px auto 30px;color:var(--muted)}
.hero-cta{display:flex;gap:14px;justify-content:center;flex-wrap:wrap}
.hero-note{margin-top:18px;font-size:.85rem;color:var(--muted2)}
.proof-bar{margin-top:26px;display:flex;gap:14px;justify-content:center;align-items:center;
  flex-wrap:wrap;font-family:'Sora';font-weight:500;font-size:.9rem;color:var(--muted)}
.proof-bar span:not(.dotsep){padding:6px 0}
.proof-bar .dotsep{color:var(--accent);opacity:.6}

/* logos strip */
.trust{position:relative;z-index:1;padding:40px 0;background:var(--bg2);
  border-top:1px solid var(--border);border-bottom:1px solid var(--border);margin-top:0}
.trust-label{text-align:center;color:var(--muted2);font-size:.8rem;letter-spacing:.14em;
  text-transform:uppercase;font-family:'Sora';font-weight:600;margin:0 0 20px}
.trust-row{display:flex;gap:38px;justify-content:center;align-items:center;flex-wrap:wrap}
.trust-row span{display:inline-flex;align-items:center;gap:9px;
  font-family:'Sora';font-weight:600;font-size:1.02rem;color:var(--muted);
  opacity:.8;transition:opacity .2s,color .2s}
.trust-row span svg{flex-shrink:0;opacity:.9}
.trust-row span:hover{opacity:1;color:var(--accent-hi)}
.trust .row{display:flex;gap:34px;justify-content:center;align-items:center;flex-wrap:wrap;color:var(--muted2);font-weight:600;font-family:'Sora';opacity:.8}

/* sections */
.section{padding:80px 0}
.section h2{text-align:center}
.section .sub{text-align:center;max-width:54ch;margin:0 auto 50px}

/* feature grid */
.grid{display:grid;gap:20px;grid-template-columns:repeat(auto-fit,minmax(280px,1fr))}
.card{background:linear-gradient(180deg,var(--surface),var(--bg2));
  border:1px solid var(--border);border-radius:var(--radius-lg);padding:26px;
  transition:transform .2s,border-color .2s,box-shadow .2s}
.card:hover{transform:translateY(-4px);border-color:var(--border-hi);box-shadow:var(--shadow)}
.ico{width:46px;height:46px;border-radius:12px;display:grid;place-items:center;
  background:var(--accent-dim);color:var(--accent-hi);margin-bottom:16px}
.card h3{font-size:1.15rem}
.card p{font-size:.95rem;margin:0}

/* pricing */
.pricing-cat{max-width:980px;margin:0 auto}
.cat-title{font-size:1.15rem;font-family:'Sora';text-align:center;margin-bottom:18px;color:var(--fg)}
.cat-title span{display:block;font-size:.85rem;font-weight:400;color:var(--muted);margin-top:4px}
.cat-pill{display:inline-block;background:var(--accent-dim);color:var(--accent-hi);font-size:.72rem;
  font-weight:600;padding:4px 11px;border-radius:999px;margin-top:6px}
.prices{display:grid;gap:18px;margin:0 auto}
.prices.cols4{grid-template-columns:repeat(4,1fr);max-width:1180px}
.prices.cols3{grid-template-columns:repeat(3,1fr);max-width:980px}
@media(max-width:1080px){.prices.cols4,.prices.cols3{grid-template-columns:repeat(2,1fr);max-width:640px}}
@media(max-width:560px){.prices.cols4,.prices.cols3{grid-template-columns:1fr;max-width:380px}}
.price{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-lg);padding:26px 22px;position:relative;display:flex;flex-direction:column}
.price.feat{border-color:var(--accent);box-shadow:var(--glow)}
.price .tag{position:absolute;top:-12px;left:50%;transform:translateX(-50%);background:var(--accent);color:#fff;font-size:.75rem;font-weight:700;padding:5px 14px;border-radius:999px;font-family:'Sora'}
.price h3{font-size:1.2rem;margin-bottom:6px}
.price .amt{font-family:'Sora';font-size:2.3rem;font-weight:700;color:var(--fg);line-height:1}
.price .amt span{font-size:1rem;color:var(--muted);font-weight:500}
.price ul{list-style:none;padding:0;margin:22px 0;flex:1}
.price li{display:flex;gap:9px;align-items:flex-start;padding:6px 0;color:var(--muted);font-size:.9rem}
.price li svg{color:var(--accent);flex-shrink:0;margin-top:3px}

/* footer */
.footer{border-top:1px solid var(--border);padding:48px 0 32px;margin-top:40px;color:var(--muted2);font-size:.9rem}
.footer .wrap{display:block}
.foot-top{display:flex;justify-content:space-between;flex-wrap:wrap;gap:32px;margin-bottom:32px}
.foot-links{display:flex;gap:56px;flex-wrap:wrap}
.foot-links h4{color:var(--fg);font-size:.85rem;margin:0 0 12px;text-transform:uppercase;letter-spacing:.5px}
.foot-links a{display:block;color:var(--muted);margin-bottom:8px;font-size:.9rem}
.foot-links a:hover{color:var(--accent)}
.foot-bottom{border-top:1px solid var(--border);padding-top:20px;color:var(--muted2)}
.social-bar{display:flex;gap:12px;flex-wrap:wrap;margin:4px 0 22px}
.social-ico{display:inline-flex;align-items:center;justify-content:center;width:38px;height:38px;
  border-radius:10px;border:1px solid var(--border);color:var(--muted);background:var(--bg2);
  transition:color .15s,border-color .15s,transform .15s}
.social-ico:hover{color:var(--accent-hi);border-color:var(--accent);transform:translateY(-2px)}
/* FAQ (AEO) */
.faq{max-width:800px;margin:0 auto}
.faq-item{border:1px solid var(--border);border-radius:var(--radius);margin-bottom:12px;background:var(--surface);overflow:hidden}
.faq-item summary{padding:18px 22px;cursor:pointer;font-weight:600;font-size:1.02rem;list-style:none;display:flex;justify-content:space-between;align-items:center}
.faq-item summary::-webkit-details-marker{display:none}
.faq-item summary::after{content:'+';color:var(--accent);font-size:1.4rem;font-weight:400}
.faq-item[open] summary::after{content:'−'}
.faq-item p{padding:0 22px 20px;color:var(--muted);line-height:1.65;margin:0}

/* auth */
.auth-wrap{min-height:calc(100dvh - 66px);display:grid;place-items:center;padding:40px 20px}
.auth-card{width:100%;max-width:420px;background:linear-gradient(180deg,var(--surface),var(--bg2));
  border:1px solid var(--border);border-radius:var(--radius-lg);padding:38px;box-shadow:var(--shadow)}
.auth-card .logo{justify-content:center;margin-bottom:8px}
.auth-card h1{font-size:1.7rem;text-align:center;margin-bottom:6px}
.auth-card .sub{text-align:center;color:var(--muted);margin-bottom:26px;font-size:.95rem}
.field{margin-bottom:16px}
.field label{display:block;font-size:.85rem;font-weight:500;color:var(--muted);margin-bottom:7px}
.field input{width:100%;padding:13px 15px;background:var(--bg2);border:1px solid var(--border-hi);
  border-radius:var(--radius);color:var(--fg);font-size:1rem;font-family:inherit;transition:border-color .2s,box-shadow .2s}
.field input:focus{outline:none;border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-dim)}
.field input::placeholder{color:var(--muted2)}
.auth-alt{text-align:center;margin-top:20px;font-size:.92rem;color:var(--muted)}
.divider{display:flex;align-items:center;gap:14px;margin:22px 0;color:var(--muted2);font-size:.82rem}
.divider::before,.divider::after{content:"";flex:1;height:1px;background:var(--border)}

/* dashboard - sidebar layout */
.app{display:flex;min-height:100dvh}
.sidebar{width:64px;background:var(--bg2);border-right:1px solid var(--border);
  display:flex;flex-direction:column;padding:16px 10px;position:sticky;top:0;height:100dvh;
  transition:width .22s cubic-bezier(.16,1,.3,1);overflow:hidden;flex-shrink:0;z-index:40}
.sidebar:hover,.sidebar.open{width:236px}
.sidebar .brand{display:flex;align-items:center;gap:10px;padding:8px 10px;margin-bottom:14px;
  font-family:'Sora';font-weight:700;color:var(--fg);white-space:nowrap}
.sidebar .brand svg{color:var(--accent);flex-shrink:0}
.sidebar .brand span{opacity:0;transition:opacity .2s}
.sidebar:hover .brand span,.sidebar.open .brand span{opacity:1}
.side-nav{display:flex;flex-direction:column;gap:4px;flex:1}
.side-link{display:flex;align-items:center;gap:14px;padding:11px 12px;border-radius:10px;
  color:var(--muted);font-weight:500;font-size:.95rem;cursor:pointer;white-space:nowrap;
  background:none;border:none;width:100%;text-align:left;font-family:inherit;transition:background .15s,color .15s}
.side-link svg{flex-shrink:0;width:20px;height:20px}
.side-link span{opacity:0;transition:opacity .2s}
.sidebar:hover .side-link span,.sidebar.open .side-link span{opacity:1}
.side-link:hover{background:var(--surface2);color:var(--fg)}
.side-link.active{background:var(--accent-dim);color:var(--accent-hi)}
.side-sub{display:flex;flex-direction:column;gap:2px;padding-left:8px;overflow:hidden;max-height:0;transition:max-height .25s ease}
.side-sub.show{max-height:120px}
.side-sub .side-link{padding:9px 12px 9px 18px;font-size:.9rem;border-left:2px solid var(--border)}
.sub-dot{width:6px;height:6px;border-radius:50%;background:var(--muted2);flex-shrink:0;margin-left:7px;transition:background .15s}
.side-sub .side-link.active .sub-dot,.side-sub .side-link:hover .sub-dot{background:var(--accent)}
.side-foot{margin-top:auto}
.main{flex:1;min-width:0;padding:34px 46px;
  /* WHITE content area (sidebar stays dark). Remap the dark theme vars to light
     values scoped to the dashboard content, so every card/text flips cleanly. */
  --bg:#F7F6FA; --bg2:#FFFFFF; --surface:#FFFFFF; --surface2:#F3F1F7;
  --fg:#14131A; --muted:#5B5966; --muted2:#8A8792; --border:#E9E8EF; --border-hi:#E0DEE8;
  background:#F7F6FA;color:var(--fg)}
.main .card,.main .step,.main .pack{box-shadow:0 8px 30px -18px rgba(20,19,26,.12)}
.main .side-link{color:var(--muted)}
/* gradient text on white: use orange->amber (no white part, which is invisible on white) */
.main .welcome .grad,.main .grad{background:linear-gradient(120deg,var(--accent),#EA580C);
  -webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
.main-inner{max-width:1100px;margin:0 auto}
.sec{display:none}
.sec.active{display:block;animation:secfade .35s cubic-bezier(.16,1,.3,1)}
@keyframes secfade{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}
.topbar{display:flex;align-items:center;justify-content:space-between;margin-bottom:28px;gap:14px}
.topbar h1{font-size:1.6rem;margin:0}
.burger{display:none;background:none;border:1px solid var(--border-hi);border-radius:8px;
  padding:8px;cursor:pointer;color:var(--fg)}
.stat-grid{display:grid;gap:16px;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));margin-bottom:8px}
.stat-card{background:linear-gradient(180deg,var(--surface),var(--bg2));border:1px solid var(--border);
  border-radius:var(--radius-lg);padding:20px}
.stat-card .n{font-family:'Sora';font-size:2rem;font-weight:800;color:var(--fg);line-height:1}
.stat-card .l{font-size:.85rem;color:var(--muted);margin-top:6px}
.feat-list{list-style:none;padding:0;margin:0}
.feat-list li{display:flex;gap:10px;align-items:center;padding:8px 0;color:var(--muted);font-size:.95rem}
.feat-list li svg{color:var(--accent);flex-shrink:0}
.tool-group{font-size:1rem;color:var(--accent-hi);margin:22px 0 12px;font-family:'Sora'}
.tool-group:first-of-type{margin-top:8px}
.tool-grid{display:grid;gap:12px;grid-template-columns:repeat(auto-fill,minmax(240px,1fr))}
.tool{background:var(--bg2);border:1px solid var(--border);border-radius:12px;padding:14px 16px;transition:border-color .15s}
.tool:hover{border-color:var(--border-hi)}
.tool-name{display:flex;gap:8px;align-items:center;font-weight:600;color:var(--fg);font-size:.92rem}
.tool-name svg{color:var(--accent);flex-shrink:0;width:15px;height:15px}
.tool-desc{font-size:.82rem;color:var(--muted);margin-top:4px;padding-left:23px}
/* AI Tools commands guide (dashboard): category header, per-tool "Try:" example */
.tool-cat{margin:0 0 26px}
.tool-group .tool-cat-count{display:inline-block;margin-left:9px;font-size:.7rem;font-weight:700;
  font-family:'Sora';letter-spacing:.04em;color:var(--accent-hi);background:var(--accent-dim);
  padding:2px 9px;border-radius:999px;vertical-align:middle}
.tool-cat-sub{font-size:.85rem;color:var(--muted);margin:2px 0 12px}
.tool-cmd{display:flex;gap:8px;align-items:baseline;margin-top:10px;margin-left:23px;
  background:rgba(249,115,22,.07);border:1px solid rgba(249,115,22,.2);border-radius:9px;padding:8px 10px}
.tool-cmd-lbl{flex-shrink:0;font-family:'Sora';font-size:.64rem;font-weight:700;letter-spacing:.06em;
  text-transform:uppercase;color:var(--accent-hi);background:var(--accent-dim);
  padding:2px 7px;border-radius:6px;line-height:1.4}
.tool-cmd-txt{font-family:'Sora',monospace;font-size:.8rem;font-style:italic;color:var(--fg);line-height:1.5}
.tool-howto{margin:2px 0 24px}
.tool-howto-steps{color:var(--muted);font-size:.92rem;line-height:1.6}
.tool-howto-steps strong{color:var(--fg)}
.tool-howto-hint{color:var(--muted2);font-size:.85rem;margin:12px 0 0}
.cmd-hero{display:flex;gap:11px;align-items:center;margin:12px 0 0;
  background:linear-gradient(180deg,#fff8f3,#fff);border:1px solid rgba(249,115,22,.28);
  border-radius:12px;padding:14px 16px;font-family:'Sora',monospace;font-size:.95rem;color:var(--fg)}
.cmd-hero svg{color:var(--accent);flex-shrink:0;width:18px;height:18px}
/* keep button icons inline & visible */
.btn svg{width:16px;height:16px}
/* chat */
.chat-wrap{display:flex;flex-direction:column;height:calc(100dvh - 150px);min-height:420px}
.chat-head{display:flex;justify-content:space-between;align-items:flex-start;gap:14px;flex-wrap:wrap;margin-bottom:14px}
.chat-credits{font-size:.82rem;color:var(--accent-hi);background:var(--accent-dim);padding:6px 12px;border-radius:999px;white-space:nowrap;font-family:'Sora';font-weight:600}
.chat-log{flex:1;overflow-y:auto;background:var(--bg2);border:1px solid var(--border);border-radius:var(--radius-lg);padding:18px;display:flex;flex-direction:column;gap:14px}
.chat-empty{margin:auto;text-align:center;color:var(--muted)}
.chat-empty p{margin-bottom:10px}
.chat-eg{display:block;width:100%;max-width:480px;margin:8px auto;background:var(--surface);border:1px solid var(--border-hi);
  color:var(--fg);padding:11px 14px;border-radius:12px;cursor:pointer;font-size:.9rem;text-align:left;transition:border-color .15s}
.chat-eg:hover{border-color:var(--accent)}
.msg{max-width:82%;padding:12px 15px;border-radius:14px;font-size:.94rem;line-height:1.55;white-space:pre-wrap;word-wrap:break-word}
.msg.user{align-self:flex-end;background:var(--accent);color:#fff;border-bottom-right-radius:4px}
.msg.ai{align-self:flex-start;background:var(--surface);border:1px solid var(--border);border-bottom-left-radius:4px}
.msg.ai.thinking{color:var(--muted);font-style:italic}
.chat-input{display:flex;gap:10px;margin-top:14px;align-items:flex-end}
.chat-input textarea{flex:1;resize:none;background:var(--bg2);border:1px solid var(--border-hi);border-radius:var(--radius);
  color:var(--fg);padding:12px 14px;font-size:1rem;font-family:inherit;max-height:140px}
.chat-input textarea:focus{outline:none;border-color:var(--accent)}
.welcome{position:relative;overflow:hidden;background:linear-gradient(135deg,var(--surface),var(--bg2));
  border:1px solid var(--border);border-radius:var(--radius-lg);padding:30px 32px;margin-bottom:22px}
.welcome::after{content:"";position:absolute;width:280px;height:280px;border-radius:50%;
  background:radial-gradient(circle,rgba(249,115,22,.18),transparent 70%);top:-120px;right:-60px;pointer-events:none}
.welcome h2{font-size:1.7rem;margin:0 0 6px}
.welcome .grad{background:linear-gradient(120deg,#fff,var(--accent-hi));-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
.welcome p{max-width:60ch;margin:0 0 18px}
.welcome .acts{display:flex;gap:12px;flex-wrap:wrap}
.gs{display:grid;gap:16px;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));margin-bottom:22px}
.gs .step{background:linear-gradient(180deg,var(--surface),var(--bg2));border:1px solid var(--border);
  border-radius:var(--radius-lg);padding:22px;cursor:pointer;transition:transform .2s,border-color .2s}
.gs .step:hover{transform:translateY(-3px);border-color:var(--border-hi)}
.gs .step .n{width:34px;height:34px;border-radius:50%;background:var(--accent-dim);color:var(--accent-hi);
  display:grid;place-items:center;font-family:'Sora';font-weight:800;margin-bottom:12px}
.gs .step h3{font-size:1.05rem;margin:0 0 4px}
.gs .step p{font-size:.9rem;margin:0;color:var(--muted)}

.dash{max-width:920px;margin:0 auto;padding:40px 24px}
.dash-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:34px;flex-wrap:wrap;gap:14px}
.dash-head h1{font-size:1.8rem;margin:0}
.panel{background:linear-gradient(180deg,var(--surface),var(--bg2));border:1px solid var(--border);
  border-radius:var(--radius-lg);padding:26px;margin-bottom:22px}
.panel h2{font-size:1.2rem;margin-bottom:4px}
.panel .hint{font-size:.9rem;color:var(--muted);margin-bottom:18px}
/* activity & health panel */
.cs-item{display:flex;align-items:center;gap:8px;font-size:.9rem;font-weight:600}
.cs-dot{width:10px;height:10px;border-radius:50%;background:#666;display:inline-block}
.qa-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:10px}
.qa{background:var(--bg2);border:1px solid var(--border);border-radius:var(--radius);
  padding:14px 16px;color:var(--fg);font-size:.9rem;font-weight:600;cursor:pointer;text-align:left;
  transition:border-color .15s,transform .15s}
.qa:hover{border-color:var(--accent,#F97316);transform:translateY(-1px)}
.two-col{display:grid;grid-template-columns:1fr 1fr;gap:16px}
@media(max-width:820px){.two-col{grid-template-columns:1fr}}
.feed{max-height:360px;overflow:auto}
.feed-row{display:flex;gap:12px;padding:9px 0;border-bottom:1px solid var(--border);font-size:.88rem}
.feed-row:last-child{border-bottom:none}
.feed-time{color:var(--muted);white-space:nowrap;font-size:.8rem;min-width:130px}
/* AI SEO Score widget */
.aiseo{display:flex;gap:26px;align-items:center;flex-wrap:wrap}
.aiseo-overall{text-align:center;min-width:150px}
.aiseo-overall .big{font-family:'Sora';font-weight:800;font-size:3rem;line-height:1}
.aiseo-overall .lbl{color:var(--muted);font-size:.85rem;margin-top:4px}
.rings{display:flex;gap:20px;flex-wrap:wrap;flex:1}
.ring{text-align:center;cursor:pointer;transition:transform .15s}
.ring:hover{transform:translateY(-2px)}
.ring svg{transform:rotate(-90deg)}
.ring .rc{font-family:'Sora';font-weight:700;font-size:1rem}
.ring .rn{font-size:.78rem;color:var(--muted);margin-top:4px}
.aiseo-issues{margin-top:18px;display:flex;flex-wrap:wrap;gap:10px}
.chip{display:inline-flex;align-items:center;gap:8px;background:var(--bg2);border:1px solid var(--border);
  border-radius:999px;padding:7px 14px;font-size:.85rem}
.chip b{font-weight:700}
.chip .fx{color:var(--accent,#F97316);cursor:pointer;font-weight:600;font-size:.8rem}
/* weekly report card */
.rep-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px;margin-top:8px}
.rep-stat{background:var(--bg2);border:1px solid var(--border);border-radius:var(--radius);padding:16px}
.rep-stat .rv{font-family:'Sora';font-weight:800;font-size:1.7rem;line-height:1}
.rep-stat .rl{color:var(--muted);font-size:.82rem;margin-top:6px}
.rep-delta{font-size:.85rem;font-weight:700;margin-left:6px}
.rep-up{color:#F97316}.rep-down{color:#E0533D}.rep-flat{color:var(--muted)}
/* approvals */
.appr-badge{background:#E0533D;color:#fff;border-radius:999px;font-size:.7rem;padding:1px 7px;font-weight:700;display:none}
.appr-badge.show{display:inline-block}
.appr-item{background:var(--bg2);border:1px solid var(--border);border-radius:var(--radius);padding:16px;margin-bottom:12px}
.appr-item .risk{display:inline-block;font-size:.72rem;font-weight:700;padding:2px 9px;border-radius:999px;text-transform:uppercase}
.risk-high{background:#fdecea;color:#c0392b}.risk-medium{background:#fcf3e6;color:#bd7b00}.risk-low{background:#edfaef;color:#00a32a}
.appr-item .sm{margin:8px 0 12px;font-size:.95rem}
.appr-acts{display:flex;gap:10px}
.site-item{display:flex;align-items:center;gap:14px;padding:15px;background:var(--bg2);
  border:1px solid var(--border);border-radius:var(--radius);margin-bottom:10px}
.site-item .ico{margin:0;width:40px;height:40px}
.site-item .meta{flex:1;min-width:0}
.site-item .url{font-weight:600;color:var(--fg);font-size:.96rem;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.site-item .usr{font-size:.84rem;color:var(--muted)}
.site-remove{background:none;border:none;cursor:pointer;color:var(--muted2);padding:8px;
  border-radius:8px;display:grid;place-items:center;transition:background .15s,color .15s}
.site-remove svg{width:18px;height:18px}
.site-remove:hover{background:rgba(239,68,68,.12);color:var(--danger)}
.pill{font-size:.74rem;font-weight:600;padding:4px 11px;border-radius:999px;font-family:'Sora'}
.pill.ok{background:var(--accent-dim);color:var(--accent-hi)}
.empty{text-align:center;padding:30px;color:var(--muted2)}
.credits-row{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:16px}
.credits-big{font-family:'Sora';font-size:2.6rem;font-weight:800;color:var(--accent-hi);line-height:1}
.credits-big small{font-size:1rem;color:var(--muted);font-weight:500;margin-left:6px}
.plan-badge{font-family:'Sora';font-size:.78rem;font-weight:700;text-transform:uppercase;
  letter-spacing:.05em;padding:5px 12px;border-radius:999px;background:var(--accent-dim);color:var(--accent-hi)}
.bar{height:8px;background:var(--bg2);border-radius:999px;overflow:hidden;margin:14px 0 6px}
.bar span{display:block;height:100%;background:linear-gradient(90deg,var(--accent),var(--accent-hi));border-radius:999px}
/* ---- Plan & Usage module ---- */
.plan-head{display:flex;justify-content:space-between;gap:28px;flex-wrap:wrap;align-items:flex-start}
.plan-eyebrow{font-family:'Sora';font-size:.74rem;font-weight:700;text-transform:uppercase;
  letter-spacing:.06em;color:var(--muted2);margin:0 0 8px}
.plan-badge-lg{font-family:'Sora';font-size:1.5rem;font-weight:800;color:var(--fg)}
.use-block{flex:1;min-width:260px;max-width:440px}
.use-row{display:flex;justify-content:space-between;align-items:baseline;margin:0 0 6px}
.use-label{font-size:.9rem;color:var(--muted);font-weight:500}
.use-val{font-family:'Sora';font-weight:700;color:var(--fg);font-size:.95rem}
.use-val small{color:var(--muted2);font-weight:500;font-size:.82rem}
.use-track{height:9px;background:var(--surface2);border-radius:999px;overflow:hidden;margin:0 0 16px}
.use-fill{height:100%;background:linear-gradient(90deg,var(--accent),var(--accent-hi));border-radius:999px}
.plan-grid{display:grid;gap:16px;margin-top:6px}
.plan-grid.cols4{grid-template-columns:repeat(4,1fr)}
.plan-grid.cols3{grid-template-columns:repeat(3,1fr)}
.plan-c{position:relative;background:var(--surface);border:1px solid var(--border);
  border-radius:16px;padding:22px 18px;display:flex;flex-direction:column}
.plan-c.featured{border-color:var(--accent);box-shadow:0 14px 40px -22px rgba(249,115,22,.4)}
.plan-c.current{border-color:var(--accent-hi);background:var(--accent-dim)}
.plan-tag{position:absolute;top:-11px;left:50%;transform:translateX(-50%);background:var(--accent);
  color:#fff;font-family:'Sora';font-weight:700;font-size:.7rem;padding:4px 12px;border-radius:999px;white-space:nowrap}
.plan-tag.cur{background:var(--accent-hi)}
.plan-c h4{font-family:'Sora';font-size:1.1rem;margin:2px 0 2px;color:var(--fg)}
.plan-price{font-family:'Sora';font-size:1.9rem;font-weight:800;color:var(--fg);line-height:1}
.plan-price span{font-size:.85rem;color:var(--muted);font-weight:500}
.plan-who{color:var(--muted2);font-size:.85rem;margin:4px 0 12px;min-height:1.1em}
.plan-c ul{list-style:none;padding:0;margin:0 0 16px;flex:1}
.plan-c li{display:flex;gap:8px;align-items:flex-start;padding:5px 0;color:var(--muted);font-size:.88rem}
.plan-c li svg{color:var(--accent);flex-shrink:0;margin-top:2px;width:16px;height:16px}
.packs{display:grid;gap:14px;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));margin-top:6px}
.pack{background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:18px;text-align:center;margin:0}
.pack-name{font-weight:600;color:var(--fg);font-size:.95rem}
.pack-price{font-family:'Sora';font-size:1.5rem;font-weight:800;color:var(--accent-hi);margin:6px 0 12px}
.txn{width:100%;border-collapse:collapse;font-size:.9rem;margin-top:6px}
.txn th{text-align:left;color:var(--muted2);font-weight:600;font-size:.76rem;text-transform:uppercase;
  letter-spacing:.04em;padding:9px 8px;border-bottom:1px solid var(--border)}
.txn td{padding:11px 8px;border-bottom:1px solid var(--border);color:var(--muted)}
@media(max-width:1000px){.plan-grid.cols4,.plan-grid.cols3{grid-template-columns:1fr 1fr}}
@media(max-width:620px){.plan-grid.cols4,.plan-grid.cols3{grid-template-columns:1fr}}
/* usage-this-month breakdown */
.usage-tot{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin:6px 0 20px}
.ut{background:var(--surface2);border:1px solid var(--border);border-radius:14px;padding:16px;text-align:center}
.ut b{display:block;font-family:'Sora';font-size:1.6rem;font-weight:800;color:var(--fg);line-height:1.1}
.ut span{color:var(--muted2);font-size:.82rem}
.ubk-h{font-family:'Sora';font-size:.95rem;color:var(--fg);margin:0 0 12px}
.ubk{display:grid;gap:9px}
.ubk-row{display:grid;grid-template-columns:160px 1fr 44px;gap:12px;align-items:center;font-size:.88rem}
.ubk-name{color:var(--muted);font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ubk-track{background:var(--surface2);border-radius:6px;height:20px;overflow:hidden}
.ubk-fill{height:100%;background:linear-gradient(90deg,var(--accent),var(--accent-hi));border-radius:6px}
.ubk-n{text-align:right;color:var(--muted2);font-weight:600}
@media(max-width:560px){.usage-tot{grid-template-columns:1fr}.ubk-row{grid-template-columns:110px 1fr 40px}}
/* overview plan snapshot */
.ov-plan{margin-top:22px}
.ov-plan-head{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;flex-wrap:wrap;margin-bottom:16px}
.ov-bars{display:grid;grid-template-columns:1fr 1fr;gap:20px}
.ov-use{display:flex;justify-content:space-between;align-items:baseline;margin:0 0 6px}
.ov-lbl{font-size:.88rem;color:var(--muted);font-weight:500}
.ov-val{font-family:'Sora';font-weight:700;color:var(--fg);font-size:.92rem}
.ov-val small{color:var(--muted2);font-weight:500;font-size:.8rem}
@media(max-width:620px){.ov-bars{grid-template-columns:1fr}}
/* coupon box on the plan page */
.coupon-box{display:flex;align-items:center;gap:12px;flex-wrap:wrap;background:var(--surface2);
  border:1px dashed var(--border-hi);border-radius:12px;padding:14px 16px;margin:2px 0 18px}
.coupon-box label{font-weight:600;color:var(--fg);font-size:.92rem}
.coupon-box input{padding:9px 13px;border:1px solid var(--border-hi);border-radius:9px;
  background:var(--bg2);color:var(--fg);font-family:'Sora';font-size:.9rem;letter-spacing:.04em;
  text-transform:uppercase;width:180px;outline:none}
.coupon-box input:focus{border-color:var(--accent)}
.coupon-note{color:var(--muted2);font-size:.82rem}
/* settings section */
.set-form{max-width:440px}
.set-form .field{margin-bottom:14px}
.set-danger{border-color:rgba(239,68,68,.35)!important}
.set-danger h2{color:var(--danger)}
.btn-danger{background:var(--danger);color:#fff;border-color:var(--danger)}
.btn-danger:hover{background:#DC2626;border-color:#DC2626}
.code-box{background:var(--bg2);border:1px solid var(--border-hi);border-radius:var(--radius);
  padding:14px 16px;font-family:'Sora',monospace;color:var(--accent-hi);
  font-size:.92rem;word-break:break-all;display:flex;justify-content:space-between;gap:12px;align-items:center}
.connect-note{display:flex;gap:11px;align-items:flex-start;background:var(--accent-dim);
  border:1px solid rgba(249,115,22,.28);border-radius:12px;padding:14px 16px;margin:4px 0 18px;
  color:var(--muted);font-size:.92rem;line-height:1.55}
.connect-note svg{color:var(--accent);flex-shrink:0;width:20px;height:20px;margin-top:1px}
.connect-note strong{color:var(--fg)}
.inline-code{background:var(--surface2);border:1px solid var(--border);border-radius:6px;
  padding:1px 8px;font-family:'Sora',monospace;font-size:.88em;color:var(--accent-hi);font-weight:600}
.steps{counter-reset:s;list-style:none;padding:0;margin:0}
.steps li{counter-increment:s;display:flex;gap:14px;padding:11px 0;color:var(--muted);font-size:.95rem}
.steps li::before{content:counter(s);flex-shrink:0;width:26px;height:26px;border-radius:50%;
  background:var(--accent-dim);color:var(--accent-hi);display:grid;place-items:center;font-size:.82rem;font-weight:700;font-family:'Sora'}
.alert{padding:13px 16px;border-radius:var(--radius);font-size:.92rem;margin-bottom:18px}
.alert.err{background:rgba(239,68,68,.1);border:1px solid rgba(239,68,68,.3);color:#FCA5A5}
.alert.ok{background:var(--accent-dim);border:1px solid rgba(249,115,22,.3);color:var(--accent-hi)}

/* stats row */
.stats{display:flex;gap:48px;justify-content:center;flex-wrap:wrap;margin-top:46px}
.stat{text-align:center}
.stat .num{font-family:'Sora';font-size:2.3rem;font-weight:800;color:var(--fg);line-height:1}
.stat .lbl{font-size:.85rem;color:var(--muted);margin-top:6px}

/* how-it-works steps */
.how{display:grid;gap:24px;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));counter-reset:hw}
.how .step{counter-increment:hw;position:relative;padding:26px;background:linear-gradient(180deg,var(--surface),var(--bg2));border:1px solid var(--border);border-radius:var(--radius-lg)}
.how .step .n{font-family:'Sora';font-weight:800;font-size:1rem;width:38px;height:38px;border-radius:50%;background:var(--accent-dim);color:var(--accent-hi);display:grid;place-items:center;margin-bottom:14px}
.how .step h3{font-size:1.1rem}.how .step p{font-size:.93rem;margin:0}

/* hero glow orbs */
.orb{position:absolute;border-radius:50%;filter:blur(70px);opacity:.5;z-index:-1;pointer-events:none}
.orb1{width:380px;height:380px;background:rgba(249,115,22,.25);top:-80px;left:8%;animation:float1 14s ease-in-out infinite}
.orb2{width:300px;height:300px;background:rgba(249,115,22,.14);top:40px;right:6%;animation:float2 18s ease-in-out infinite}
@keyframes float1{0%,100%{transform:translate(0,0)}50%{transform:translate(40px,30px)}}
@keyframes float2{0%,100%{transform:translate(0,0)}50%{transform:translate(-30px,40px)}}

/* ===== SITE-WIDE ANIMATED BACKGROUND: moving dot-grid + floating particles ===== */
.bg-anim{position:fixed;inset:0;z-index:-10;overflow:hidden;pointer-events:none}
/* subtle scrolling dot grid (no gradient) */
.bg-anim::before{content:'';position:absolute;inset:-4px;
  background-image:radial-gradient(circle,rgba(249,115,22,.14) 1.2px,transparent 1.2px);
  background-size:34px 34px;
  mask-image:radial-gradient(1100px 750px at 50% 24%,#000 15%,transparent 78%);
  -webkit-mask-image:radial-gradient(1100px 750px at 50% 24%,#000 15%,transparent 78%);
  animation:dotScroll 22s linear infinite}
@keyframes dotScroll{from{background-position:0 0}to{background-position:34px 34px}}
/* thin sweeping light beam */
.bg-anim::after{content:'';position:absolute;top:0;left:0;width:60%;height:100%;
  background:linear-gradient(105deg,transparent 40%,rgba(249,115,22,.06) 50%,transparent 60%);
  animation:beam 9s ease-in-out infinite}
@keyframes beam{0%{transform:translateX(-40%)}50%{transform:translateX(120%)}100%{transform:translateX(-40%)}}
/* floating particles (small dots that rise) */
.bg-blob{position:absolute;width:5px;height:5px;border-radius:50%;
  background:var(--accent);opacity:.35;box-shadow:0 0 8px 1px rgba(249,115,22,.5)}
.bg-blob.b1{left:14%;top:70%;animation:rise 14s linear infinite}
.bg-blob.b2{left:52%;top:85%;width:4px;height:4px;animation:rise 19s linear infinite 3s}
.bg-blob.b3{left:80%;top:78%;width:6px;height:6px;animation:rise 16s linear infinite 6s}
.bg-blob.b4{left:30%;top:90%;width:4px;height:4px;animation:rise 20s linear infinite 2s}
.bg-blob.b5{left:66%;top:82%;width:5px;height:5px;animation:rise 15s linear infinite 8s}
.bg-blob.b6{left:90%;top:88%;width:4px;height:4px;animation:rise 18s linear infinite 4s}
@keyframes rise{0%{transform:translateY(0);opacity:0}
  10%{opacity:.4}90%{opacity:.4}100%{transform:translateY(-90vh);opacity:0}}

/* ===== LIGHT ZONE: sections after the hero go white ===== */
.light-zone{position:relative;background:#FFFFFF;color:#1A1A1A;
  --fg:#14131A;--muted:#5B5966;--muted2:#8B8996;
  --surface:#FFFFFF;--surface2:#F4F4F8;--bg2:#F7F7FB;--border:#E9E8EF;--border-hi:#DAD9E4;
  --accent-dim:rgba(249,115,22,.09);--shadow:0 12px 40px -16px rgba(20,19,26,.14)}
/* soft animated tint inside the light zone */
.light-zone::before{content:'';position:absolute;inset:0;z-index:0;pointer-events:none;
  background:radial-gradient(700px 400px at 85% 8%,rgba(249,115,22,.07),transparent 60%),
             radial-gradient(600px 400px at 10% 60%,rgba(249,115,22,.05),transparent 60%);
  animation:tintPulse 12s ease-in-out infinite}
@keyframes tintPulse{0%,100%{opacity:.7}50%{opacity:1}}
.light-zone>*{position:relative;z-index:1}
.light-zone h1,.light-zone h2,.light-zone h3{color:#14131A}
.light-zone .card{background:#FFFFFF;border:1px solid #E9E8EF;box-shadow:0 8px 30px -18px rgba(20,19,26,.15)}
.light-zone .card:hover{border-color:rgba(249,115,22,.4);box-shadow:0 14px 40px -18px rgba(249,115,22,.2)}
.light-zone .ico{background:rgba(249,115,22,.12);color:#EA580C}
.light-zone .sub{color:#5B5966}
.light-zone .how .step{background:#FFFFFF;border:1px solid #E9E8EF}
.light-zone .price{background:#FFFFFF;border:1px solid #E9E8EF}
.light-zone .price.feat{border-color:var(--accent);box-shadow:0 20px 60px -24px rgba(249,115,22,.35)}
.light-zone .price li{color:#5B5966}
.light-zone .cat-title{color:#14131A}
.light-zone .faq-item{background:#FFFFFF;border:1px solid #E9E8EF}
.light-zone .faq-item[open]{border-color:rgba(249,115,22,.35)}
.light-zone .faq-item p{color:#5B5966}
.light-zone .cta-panel{background:linear-gradient(180deg,#fff8f3,#ffefe4);
  border:1px solid rgba(249,115,22,.28);box-shadow:0 20px 60px -28px rgba(249,115,22,.35)}
.light-zone #how{background:#FAF7F5!important}
/* AEO/GEO: definition block + fact grid */
.def-block{max-width:70ch;margin:0 auto;text-align:center;font-size:1.18rem;line-height:1.7;color:#3A3846}
.fact-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:18px;margin:40px auto 0}
.fact{display:flex;flex-direction:column;align-items:center;justify-content:center;
  text-align:center;padding:26px 16px;min-height:132px;background:#fff;
  border:1px solid #E9E8EF;border-radius:16px}
.fact b{display:block;font-family:'Sora';font-weight:800;font-size:1.7rem;color:var(--accent);line-height:1.15}
.fact span{display:block;color:#5B5966;font-size:.86rem;margin-top:8px;line-height:1.35}
@media(max-width:720px){.fact-grid{grid-template-columns:repeat(2,1fr)}}
/* section illustration (Powerful AI, but you stay in control) */
.safe-img{display:block;width:100%;max-width:560px;height:auto;margin:34px auto 0}
/* objection-handling grid */
.obj-grid{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-top:40px}
.obj{background:#fff;border:1px solid #E9E8EF;border-radius:16px;padding:24px;text-align:left}
.obj h3{font-size:1.08rem;color:#14131A;margin-bottom:8px;display:flex;gap:9px;align-items:flex-start}
.obj h3::before{content:'';flex-shrink:0;width:20px;height:20px;margin-top:2px;border-radius:6px;
  background:var(--accent) url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='white' stroke-width='3' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='20 6 9 17 4 12'/%3E%3C/svg%3E") center/13px no-repeat}
.obj p{color:#5B5966;margin:0;font-size:.95rem;line-height:1.65}
@media(max-width:720px){.obj-grid{grid-template-columns:1fr}}

/* ===== CREATIVE WHITE-SECTION ANIMATIONS ===== */
/* floating decorative shapes drifting in the light zone */
.lz-shapes{position:absolute;inset:0;z-index:0;pointer-events:none;overflow:hidden}
.lz-shapes i{position:absolute;display:block;border-radius:30%;
  background:linear-gradient(135deg,rgba(249,115,22,.10),rgba(249,115,22,.02));
  border:1px solid rgba(249,115,22,.12)}
.lz-shapes i:nth-child(1){width:120px;height:120px;left:4%;top:12%;animation:floatShape 18s ease-in-out infinite}
.lz-shapes i:nth-child(2){width:80px;height:80px;right:6%;top:30%;border-radius:50%;animation:floatShape 22s ease-in-out infinite 2s}
.lz-shapes i:nth-child(3){width:160px;height:160px;left:8%;bottom:14%;border-radius:24px;animation:floatShape 26s ease-in-out infinite 4s}
.lz-shapes i:nth-child(4){width:60px;height:60px;right:12%;bottom:22%;border-radius:50%;animation:floatShape 20s ease-in-out infinite 1s}
.lz-shapes i:nth-child(5){width:100px;height:100px;right:20%;top:8%;border-radius:20px;animation:floatShape 24s ease-in-out infinite 3s}
@keyframes floatShape{0%,100%{transform:translate(0,0) rotate(0deg)}
  33%{transform:translate(30px,-25px) rotate(8deg)}66%{transform:translate(-20px,20px) rotate(-6deg)}}

/* animated gradient underline under section headings */
.light-zone h2{position:relative;display:table;margin-inline:auto;text-align:center}
.light-zone .section>.wrap>h2::after,.light-zone .section h2.reveal::after{content:'';
  position:absolute;left:50%;bottom:-10px;width:0;height:3px;border-radius:3px;
  background:linear-gradient(90deg,transparent,var(--accent),transparent);
  transform:translateX(-50%);transition:width .8s cubic-bezier(.16,1,.3,1) .2s}
.light-zone .section h2.reveal.in::after{width:80px}

/* card entrance: lift + shine sweep on hover */
.light-zone .card{overflow:hidden}
.light-zone .card::after{content:'';position:absolute;top:0;left:-120%;width:70%;height:100%;
  background:linear-gradient(105deg,transparent,rgba(249,115,22,.10),transparent);
  transition:left .6s ease;pointer-events:none}
.light-zone .card:hover::after{left:130%}
.light-zone .card:hover{transform:translateY(-6px)}
.light-zone .card .ico{transition:transform .3s}
.light-zone .card:hover .ico{transform:scale(1.1) rotate(-4deg)}

/* pricing feat card subtle pulse ring */
.light-zone .price.feat{animation:featPulse 3s ease-in-out infinite}
@keyframes featPulse{0%,100%{box-shadow:0 20px 60px -24px rgba(249,115,22,.35)}
  50%{box-shadow:0 20px 70px -20px rgba(249,115,22,.5)}}
/* second, subtler bg-anim variant inside light zone via body layer stays dark - hidden here */
.light-zone{isolation:isolate}

/* scroll reveal */
.reveal{opacity:0;transform:translateY(26px);transition:opacity .7s cubic-bezier(.16,1,.3,1),transform .7s cubic-bezier(.16,1,.3,1)}
.reveal.in{opacity:1;transform:none}
.reveal.d1{transition-delay:.08s}.reveal.d2{transition-delay:.16s}.reveal.d3{transition-delay:.24s}
.reveal.d4{transition-delay:.32s}.reveal.d5{transition-delay:.4s}

@media(max-width:760px){
  .sidebar{position:fixed;left:0;top:0;width:64px;transform:translateX(-100%)}
  .sidebar.open{transform:translateX(0);width:236px}
  .sidebar.open .side-link span,.sidebar.open .brand span{opacity:1}
  .main{padding:20px 18px;max-width:100%}
  .burger{display:inline-flex}
}
@media(max-width:640px){
  .nav-links a:not(.btn){display:none}
  .hero{padding:54px 0 40px}
  .section{padding:54px 0}
  .stats{gap:30px}
}
@media(prefers-reduced-motion:reduce){
  *{transition:none!important;scroll-behavior:auto;animation:none!important}
  .reveal{opacity:1;transform:none}
}

/* ============ 2026 PREMIUM LANDING UPGRADES ============ */
/* top gradient hairline like Linear/Vercel */
.nav{border-bottom:1px solid var(--border)}
.nav::after{content:'';position:absolute;left:0;right:0;bottom:0;height:1px;
  background:linear-gradient(90deg,transparent,rgba(249,115,22,.5),transparent)}
.nav .wrap{position:relative}

/* hero: 2-column split - copy left, chat right */
.hero-split{display:grid;grid-template-columns:1.05fr .95fr;gap:56px;align-items:center;text-align:left}
.hero-copy{text-align:left}
.hero-copy .badge{margin-bottom:22px}
.hero-copy h1{margin-inline:0;text-align:left}
.hero-copy p.lead{margin:20px 0 30px 0;text-align:left}
.hero-copy .hero-cta{justify-content:flex-start}
.hero-copy .hero-note{text-align:left}
.hero-chat{margin:0;max-width:none}
@media(max-width:900px){
  .hero-split{grid-template-columns:1fr;gap:40px;text-align:center}
  .hero-copy,.hero-copy h1,.hero-copy p.lead,.hero-copy .hero-note{text-align:center}
  .hero-copy h1{margin-inline:auto}
  .hero-copy .hero-cta{justify-content:center}
  .hero-chat{max-width:560px;margin:0 auto}
}
/* hero: bigger, tighter, with a soft grid + spotlight */
.hero{padding:96px 0 40px;position:relative;overflow:hidden}
.hero::before{content:'';position:absolute;inset:0;z-index:-2;
  background-image:linear-gradient(rgba(255,255,255,.028) 1px,transparent 1px),
                   linear-gradient(90deg,rgba(255,255,255,.028) 1px,transparent 1px);
  background-size:56px 56px;
  mask-image:radial-gradient(680px 420px at 50% 8%,#000 30%,transparent 75%);
  -webkit-mask-image:radial-gradient(680px 420px at 50% 8%,#000 30%,transparent 75%)}
.hero h1{font-size:clamp(2rem,4.2vw,3.2rem);letter-spacing:-.03em;max-width:24ch;margin-inline:auto}
.hero .grad{background:linear-gradient(115deg,#fff 8%,var(--accent-hi) 50%,var(--accent-2));
  -webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
.hero p.lead{font-size:1.24rem;max-width:56ch;color:#B8B8B8}
.badge{background:rgba(249,115,22,.08);border-color:rgba(249,115,22,.22);backdrop-filter:blur(8px)}

/* primary button: dual-color gradient + stronger glow */
.btn-primary{background:var(--accent);color:#fff;box-shadow:var(--glow)}
.btn-primary:hover{transform:translateY(-2px);box-shadow:0 14px 44px -8px rgba(249,115,22,.8)}
.btn-lg{padding:16px 32px;border-radius:14px}

/* hero chat mockup (pure CSS, no image) */
.hero-chat{margin:52px auto 0;max-width:720px;position:relative}
.hero-chat .frame{border-radius:18px;border:1px solid var(--border);overflow:hidden;
  background:linear-gradient(180deg,#141414,#0a0a0a);box-shadow:0 40px 120px -30px rgba(0,0,0,.8),0 0 90px -30px rgba(249,115,22,.35)}
.hero-chat .bar{display:flex;align-items:center;gap:7px;padding:13px 16px;
  border-bottom:1px solid var(--border);background:var(--bg2);margin:0}
.hero-chat .bar i{width:11px;height:11px;border-radius:50%;display:inline-block}
.hero-chat .bar i:nth-child(1){background:#ff5f57}.hero-chat .bar i:nth-child(2){background:#febc2e}.hero-chat .bar i:nth-child(3){background:#28c840}
.hero-chat .bar span{margin-left:12px;color:var(--muted2);font-size:.82rem;font-family:'Sora';font-weight:500}
.chatbody{padding:22px;display:flex;flex-direction:column;gap:16px;text-align:left}
.msg{max-width:88%;font-size:.96rem;line-height:1.55}
.msg.me{align-self:flex-end;background:var(--accent);color:#fff;padding:13px 16px;border-radius:16px 16px 4px 16px}
.msg.ai{align-self:flex-start;display:flex;gap:12px}
.ai-av{width:34px;height:34px;border-radius:9px;flex-shrink:0;display:grid;place-items:center;overflow:hidden}
.ai-txt{background:var(--bg2);border:1px solid var(--border);padding:14px 16px;border-radius:4px 16px 16px 16px}
.ai-txt p{margin:0;color:var(--fg)}
.ai-links{margin-top:8px!important;color:var(--accent)!important;font-weight:600;font-size:.88rem}

/* section headings: eyebrow + bigger */
.section h2{font-size:clamp(1.8rem,4vw,2.8rem);letter-spacing:-.03em}
.eyebrow{display:block;text-align:center;color:var(--accent-hi);font-family:'Sora';
  font-weight:600;font-size:.82rem;text-transform:uppercase;letter-spacing:.14em;margin-bottom:12px}

/* feature cards: gradient border on hover + glass */
.card{background:var(--surface);
  border:1px solid var(--border);backdrop-filter:blur(6px);position:relative}
.card::before{content:'';position:absolute;inset:0;border-radius:inherit;padding:1px;
  background:linear-gradient(140deg,rgba(249,115,22,.5),transparent 40%);
  -webkit-mask:linear-gradient(#000 0 0) content-box,linear-gradient(#000 0 0);
  -webkit-mask-composite:xor;mask-composite:exclude;opacity:0;transition:opacity .25s}
.card:hover::before{opacity:1}
.card:hover{transform:translateY(-6px)}
.ico{background:linear-gradient(135deg,rgba(249,115,22,.2),rgba(249,115,22,.06));
  border:1px solid rgba(249,115,22,.2)}

/* pricing polish */
.price{background:var(--surface);
  border:1px solid var(--border)}
.price.feat{background:linear-gradient(180deg,rgba(249,115,22,.08),rgba(255,255,255,.01));
  box-shadow:0 20px 70px -25px rgba(249,115,22,.4)}

/* how-it-works connecting flow */
.how .step{background:var(--surface);border-color:var(--border)}
.how .step:hover{border-color:rgba(249,115,22,.35);transform:translateY(-4px);transition:.25s}


/* final CTA: gradient panel */
.cta-panel{max-width:1120px;margin:0 auto;padding:64px 40px;border-radius:26px;text-align:center;
  background:radial-gradient(120% 140% at 50% 0%,rgba(249,115,22,.16),transparent 60%),linear-gradient(180deg,#141414,#0a0a0a);
  border:1px solid rgba(249,115,22,.2);box-shadow:0 0 90px -30px rgba(249,115,22,.4)}

/* faq polish */
.faq-item{background:var(--surface);border-color:var(--border)}
.faq-item[open]{border-color:rgba(249,115,22,.3)}

@media(max-width:640px){
  .hero{padding:60px 0 30px}
  .hero-visual{margin-top:36px}
  .cta-panel{padding:44px 24px}
}

/* ============ NEW LAYOUT: bento, marquee, social proof ============ */
.sec-h2{font-size:clamp(2rem,4.2vw,3.1rem);letter-spacing:-.035em;max-width:16ch;margin-inline:auto;text-align:center}

/* logo marquee strip */
.marquee-wrap{padding:40px 0;border-top:1px solid var(--border);border-bottom:1px solid var(--border);
  background:var(--bg2)}
.marquee-label{text-align:center;color:var(--muted2);font-size:.82rem;letter-spacing:.14em;
  text-transform:uppercase;font-family:'Sora';font-weight:600;margin-bottom:22px}
.trust-row{display:flex;gap:44px;justify-content:center;align-items:center;flex-wrap:wrap}
.trust-row span{font-family:'Sora';font-weight:600;font-size:1.05rem;color:var(--muted);
  opacity:.75;transition:opacity .2s,color .2s}
.trust-row span:hover{opacity:1;color:var(--accent-hi)}

/* BENTO grid */
.bento{display:grid;grid-template-columns:repeat(3,1fr);gap:18px;margin-top:46px}
.bento-card{background:var(--surface);
  border:1px solid var(--border);border-radius:20px;padding:28px;position:relative;overflow:hidden;
  transition:transform .25s,border-color .25s}
.bento-card::after{content:'';position:absolute;top:-40%;right:-20%;width:220px;height:220px;
  background:radial-gradient(circle,rgba(249,115,22,.18),transparent 70%);opacity:0;transition:opacity .3s}
.bento-card:hover{transform:translateY(-5px);border-color:rgba(249,115,22,.35)}
.bento-card:hover::after{opacity:1}
.bento-card h3{font-size:1.18rem;margin-bottom:8px}
.bento-card p{font-size:.96rem;margin:0;color:var(--muted)}
.bento-card.bento-lg{grid-column:span 2;grid-row:span 1;
  background:linear-gradient(135deg,rgba(249,115,22,.10),rgba(249,115,22,.03));
  border-color:rgba(249,115,22,.28)}
.bento-card.bento-lg h3{font-size:1.5rem}
.bento-card .ico{width:50px;height:50px;border-radius:14px;
  background:linear-gradient(135deg,rgba(249,115,22,.28),rgba(79,143,255,.12));
  border:1px solid rgba(249,115,22,.3);color:var(--accent-hi);display:grid;place-items:center;margin-bottom:18px}
@media(max-width:820px){.bento{grid-template-columns:repeat(2,1fr)}.bento-card.bento-lg{grid-column:span 2}}
@media(max-width:560px){.bento{grid-template-columns:1fr}.bento-card.bento-lg{grid-column:span 1}}

/* stat band */
.stat-band{display:grid;grid-template-columns:repeat(4,1fr);gap:20px;margin:44px 0 56px;
  padding:34px;border-radius:22px;background:var(--surface);
  border:1px solid var(--border)}
.sb{text-align:center}
.sb-n{font-family:'Sora';font-weight:800;font-size:2.4rem;line-height:1;
  background:var(--grad);-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
.sb-l{color:var(--muted);font-size:.86rem;margin-top:8px}
@media(max-width:640px){.stat-band{grid-template-columns:repeat(2,1fr);gap:24px;padding:26px}}

/* testimonial cards */
.quote-grid{display:grid;grid-template-columns:1fr 1fr;gap:20px}
.qcard{background:var(--surface);
  border:1px solid var(--border);border-radius:20px;padding:28px;margin:0}
.qcard p{font-size:1.05rem;color:var(--fg);line-height:1.6;margin:0 0 20px}
.qcard footer{display:flex;align-items:center;gap:12px}
.qcard .av{width:42px;height:42px;border-radius:50%;background:var(--grad);color:#fff;
  display:grid;place-items:center;font-family:'Sora';font-weight:700}
.qcard footer b{display:block;color:var(--fg);font-size:.95rem}
.qcard footer i{color:var(--muted);font-size:.85rem;font-style:normal}
@media(max-width:640px){.quote-grid{grid-template-columns:1fr}}
"""

SITE_BASE = "https://wptaskify.com"  # canonical base (custom domain)


_SCRIPTS = """<script>
(function(){
  var rm = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  // scroll reveal
  var els = document.querySelectorAll('.reveal');
  if(rm || !('IntersectionObserver' in window)){
    els.forEach(function(e){e.classList.add('in')});
  } else {
    var io = new IntersectionObserver(function(entries){
      entries.forEach(function(en){ if(en.isIntersecting){ en.target.classList.add('in'); io.unobserve(en.target);} });
    },{threshold:.12, rootMargin:'0px 0px -40px 0px'});
    els.forEach(function(e){io.observe(e)});
  }
  // count-up numbers
  function countUp(el){
    var target = +el.getAttribute('data-count'), suf = el.getAttribute('data-suffix')||'';
    if(rm){ el.textContent = target+suf; return; }
    var start=null, dur=1100;
    function step(ts){ if(!start)start=ts; var p=Math.min((ts-start)/dur,1);
      el.textContent = Math.floor((1-Math.pow(1-p,3))*target)+suf;
      if(p<1) requestAnimationFrame(step); }
    requestAnimationFrame(step);
  }
  var nums = document.querySelectorAll('[data-count]');
  if('IntersectionObserver' in window){
    var io2 = new IntersectionObserver(function(es){es.forEach(function(en){
      if(en.isIntersecting){ countUp(en.target); io2.unobserve(en.target);} });},{threshold:.5});
    nums.forEach(function(n){io2.observe(n)});
  } else { nums.forEach(countUp); }
})();
</script>"""


# Favicon - the official wptaskify icon (orange tile + W-mark zigzag) as an inline
# SVG data URI. Matches the brand files. Crisp at every size, no extra file needed.
_FAVICON_SVG = (
    "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 512 512'>"
    "<defs><linearGradient id='f' x1='0' y1='0' x2='1' y2='1'>"
    "<stop offset='0' stop-color='%23F97316'/><stop offset='1' stop-color='%23FBBF24'/>"
    "</linearGradient></defs>"
    "<rect x='0' y='0' width='512' height='512' rx='116' fill='url(%23f)'/>"
    "<path d='M102 160 L174 358 L256 205 L338 358 L447 133' fill='none' stroke='%230A0A0A' "
    "stroke-width='51' stroke-linecap='round' stroke-linejoin='round'/></svg>")
_FAVICON = f'<link rel="icon" type="image/svg+xml" href="data:image/svg+xml,{_FAVICON_SVG}">'


def _analytics_head():
    """Admin-managed <head> tags: Google Analytics (GA4), Search Console verification,
    and any extra raw verification tags. DYNAMIC from the DB - empty until the admin
    fills them in, so nothing is injected by default."""
    try:
        import db as _db
        a = _db.get_analytics() if _db is not None else {}
    except Exception:
        return ""
    out = ""
    gsc = (a.get("gsc_verify") or "").strip()
    if gsc:
        # Store just the token; render the full verification meta tag.
        token = gsc
        m = None
        try:
            import re as _re
            m = _re.search(r'content=["\']([^"\']+)["\']', gsc)
        except Exception:
            m = None
        if m:
            token = m.group(1)
        out += f'<meta name="google-site-verification" content="{_e_html(token)}">'
    ga = (a.get("ga_id") or "").strip()
    if ga:
        gj = _e_html(ga)
        out += (
            f'<script async src="https://www.googletagmanager.com/gtag/js?id={gj}"></script>'
            f'<script>window.dataLayer=window.dataLayer||[];'
            f'function gtag(){{dataLayer.push(arguments);}}gtag("js",new Date());'
            f'gtag("config","{gj}");</script>')
    extra = (a.get("head_extra") or "").strip()
    if extra:
        # Raw passthrough for other verification/analytics tags (Bing, Ahrefs, etc.).
        out += extra
    return out


def _head(title, description="", canonical="/", og_image="", schema_json="", keywords=""):
    # SECURITY: escape everything that goes into the <head>. title/description can be
    # user-controlled (forum thread titles, admin blog titles), so escape centrally here
    # to prevent stored XSS via </title>, meta content attribute breakout, etc.
    import html as _h
    t = _h.escape(str(title or ""))
    desc = _h.escape(str(description or ""))
    kw = _h.escape(str(keywords or ""))
    # Default social-share image so every page has a preview when shared.
    ogi = _h.escape(str(og_image or f"{SITE_BASE}/assets/hero-features.webp"))
    meta = ""
    if kw:
        meta += f'<meta name=keywords content="{kw}">'
    if desc:
        meta += (f'<meta name=description content="{desc}">'
                 f'<meta property=og:title content="{t}">'
                 f'<meta property=og:description content="{desc}">'
                 f'<meta property=og:type content=website>'
                 f'<meta property=og:site_name content="{BRAND}">'
                 f'<meta property=og:url content="{SITE_BASE}{canonical}">'
                 f'<meta name=twitter:card content=summary_large_image>'
                 f'<meta name=twitter:title content="{t}">'
                 f'<meta name=twitter:description content="{desc}">')
        if ogi:
            meta += (f'<meta property=og:image content="{ogi}">'
                     f'<meta name=twitter:image content="{ogi}">')
    canon = f'<link rel=canonical href="{SITE_BASE}{canonical}">'
    # JSON-LD: neutralize a </script> breakout (json.dumps does NOT escape it).
    safe_schema = (schema_json or "").replace("</", "<\\/")
    schema = f'<script type=application/ld+json>{safe_schema}</script>' if schema_json else ""
    return ("<!doctype html><html lang=en><head>"
            "<meta charset=utf-8><meta name=viewport content=\"width=device-width,initial-scale=1\">"
            f"{_analytics_head()}"
            f"<title>{t}</title>{meta}{canon}{_FAVICON}"
            f'<link rel="icon" type="image/png" sizes="32x32" href="{SITE_BASE}/assets/favicon-32.png">'
            f'<link rel="apple-touch-icon" href="{SITE_BASE}/assets/apple-touch-icon.png">'
            "<meta name=theme-color content=#0A0A0A>"
            "<meta name=robots content=\"index,follow,max-image-preview:large,max-snippet:-1\">"
            "<link rel=preconnect href=https://fonts.googleapis.com>"
            "<link rel=preconnect href=https://fonts.gstatic.com crossorigin>"
            "<link href=\"https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600"
            "&family=Sora:wght@400;500;600;700;800&display=swap\" rel=stylesheet>"
            f"<style>{_CSS}</style></head><body>"
            "<div class=bg-anim aria-hidden=true>"
            "<span class='bg-blob b1'></span><span class='bg-blob b2'></span>"
            "<span class='bg-blob b3'></span><span class='bg-blob b4'></span>"
            "<span class='bg-blob b5'></span><span class='bg-blob b6'></span></div>"
            f"{schema}")


def _logo_svg(size=28):
    """The official wptaskify icon mark - orange gradient tile + W-mark zigzag.
    Matches the brand files (wptaskify-icon.svg)."""
    return (
        f'<svg width={size} height={size} viewBox="0 0 512 512" '
        'xmlns="http://www.w3.org/2000/svg" style="flex-shrink:0">'
        '<defs><linearGradient id="wtg" x1="0" y1="0" x2="1" y2="1">'
        '<stop offset="0" stop-color="#F97316"/><stop offset="1" stop-color="#FBBF24"/>'
        '</linearGradient></defs>'
        '<rect x="0" y="0" width="512" height="512" rx="116" fill="url(#wtg)"/>'
        '<path d="M102 160 L174 358 L256 205 L338 358 L447 133" fill="none" stroke="#0A0A0A" '
        'stroke-width="51" stroke-linecap="round" stroke-linejoin="round"/></svg>')


def _logo():
    return (f'<a href="/" class=logo>{_logo_svg(26)}'
            f'<span>wp<b style="color:var(--accent-hi)">taskify</b></span></a>')


# Inline SVG glyphs for each social platform (currentColor -> inherits link color).
_SOCIAL_ICONS = {
    "facebook":  '<path d="M18 2h-3a5 5 0 0 0-5 5v3H7v4h3v8h4v-8h3l1-4h-4V7a1 1 0 0 1 1-1h3z"/>',
    "instagram": '<rect x="2" y="2" width="20" height="20" rx="5"/><circle cx="12" cy="12" r="4"/><circle cx="17.5" cy="6.5" r="1.2" fill="currentColor" stroke="none"/>',
    "youtube":   '<rect x="2" y="5" width="20" height="14" rx="4"/><path d="M10 9l5 3-5 3z" fill="currentColor" stroke="none"/>',
    "pinterest": '<circle cx="12" cy="12" r="10"/><path d="M12 7c-2.2 0-3.5 1.4-3.5 3.2 0 .9.4 1.9 1.1 2.2.1 0 .2 0 .2-.1l.2-.8c0-.1 0-.2-.1-.3-.3-.3-.5-.8-.5-1.3 0-1.3 1-2.4 2.6-2.4 1.4 0 2.3.9 2.3 2.1 0 1.6-.7 2.9-1.7 2.9-.6 0-1-.5-.9-1.1.2-.7.5-1.4.5-1.9 0-.5-.3-.8-.7-.8-.6 0-1 .6-1 1.4 0 .5.2.8.2.8l-.7 3c-.2.9 0 2 0 2.1 0 .1.1.1.2.1 0 0 1-1.3 1.3-2.5l.4-1.5c.3.5.9.9 1.6.9 2.1 0 3.6-1.9 3.6-4.5C16.7 8.7 14.7 7 12 7z" fill="currentColor" stroke="none"/>',
    "linkedin":  '<rect x="2" y="2" width="20" height="20" rx="3"/><path d="M7 10v7M7 7v.01M11 17v-4a2 2 0 0 1 4 0v4M11 17v-7" />',
    "reddit":    '<circle cx="12" cy="13" r="8"/><circle cx="9" cy="13" r="1" fill="currentColor" stroke="none"/><circle cx="15" cy="13" r="1" fill="currentColor" stroke="none"/><path d="M9.5 16c1.5 1 3.5 1 5 0M15 6a1.5 1.5 0 1 0 .01 0M15 6l-2 1"/>',
    "twitter":   '<path d="M4 4l7 9M20 4l-7 9M13 13l-9 7M11 11l9 7" />',
    "tiktok":    '<path d="M14 3v11a4 4 0 1 1-4-4M14 3c.5 2.5 2 4 5 4"/>',
    "threads":   '<path d="M12 22a10 10 0 1 1 0-20 10 10 0 0 1 0 20zM8.5 13c0-2 1.5-3.5 3.5-3.5s3.5 1.3 3.5 3c0 2-1.5 3-3 3s-2-1-2-1.8c0-1 1-1.5 2-1.2"/>',
    "github":    '<path d="M9 19c-4 1.5-4-2.5-6-3m12 5v-3.5a3 3 0 0 0-.9-2.5c3-.3 6-1.5 6-6.5a5 5 0 0 0-1.4-3.5 4.6 4.6 0 0 0-.1-3.5s-1.1-.3-3.6 1.3a12.3 12.3 0 0 0-6.4 0C5.6 1.5 4.5 1.8 4.5 1.8a4.6 4.6 0 0 0-.1 3.5A5 5 0 0 0 3 8.8c0 5 3 6.2 6 6.5a3 3 0 0 0-.9 2.4V21"/>',
}


# WhatsApp contact numbers (two agents handle chats). Displayed as a floating
# button in the corner + on the contact page.
_WHATSAPP_NUMBERS = [
    ("917015178387", "+91 70151 78387"),
    ("919468307774", "+91 94683 07774"),
]
_WA_ICON = ('<svg viewBox="0 0 32 32" width="30" height="30" fill="currentColor" aria-hidden="true">'
            '<path d="M16.003 3C9.38 3 4 8.38 4 15c0 2.36.69 4.56 1.88 6.42L4 29l7.77-1.85A11.9 11.9 0 0 0 16 27c6.62 0 12-5.38 12-12S22.62 3 16.003 3zm0 21.8c-1.9 0-3.68-.56-5.17-1.52l-.37-.23-4.6 1.1 1.12-4.48-.24-.38A9.76 9.76 0 0 1 6.2 15c0-5.41 4.4-9.8 9.8-9.8 5.41 0 9.8 4.39 9.8 9.8s-4.39 9.8-9.8 9.8zm5.37-7.34c-.29-.15-1.73-.85-2-.95-.27-.1-.46-.15-.66.15-.19.29-.76.95-.93 1.14-.17.19-.34.22-.63.07-.29-.15-1.24-.46-2.36-1.46-.87-.78-1.46-1.74-1.63-2.03-.17-.29-.02-.45.13-.6.13-.13.29-.34.44-.51.15-.17.19-.29.29-.48.1-.19.05-.36-.02-.51-.07-.15-.66-1.59-.9-2.18-.24-.57-.48-.49-.66-.5l-.56-.01c-.19 0-.51.07-.77.36-.27.29-1.01.99-1.01 2.42 0 1.43 1.04 2.81 1.18 3 .15.19 2.05 3.13 4.97 4.39.69.3 1.24.48 1.66.61.7.22 1.33.19 1.83.12.56-.08 1.73-.71 1.97-1.39.24-.68.24-1.27.17-1.39-.07-.12-.26-.19-.55-.34z"/>'
            '</svg>')


def _whatsapp_float():
    """A floating WhatsApp button (bottom-right) that opens a small menu with our two
    contact numbers. Present on every public page."""
    items = "".join(
        f'<a class=wa-num href="https://wa.me/{digits}" target="_blank" rel="noopener">'
        f'{_WA_ICON}<span>Chat on WhatsApp<br><b>{label}</b></span></a>'
        for digits, label in _WHATSAPP_NUMBERS)
    return (
        '<div class=wa-widget>'
        f'<div class=wa-menu>{items}</div>'
        f'<button class=wa-fab type=button aria-label="Chat on WhatsApp" '
        'onclick="this.parentNode.classList.toggle(\'open\')">'
        f'{_WA_ICON}</button>'
        '</div>'
        '<style>'
        '.wa-widget{position:fixed;right:20px;bottom:20px;z-index:900;'
        'display:flex;flex-direction:column;align-items:flex-end;gap:12px}'
        '.wa-fab{width:58px;height:58px;border-radius:50%;border:none;cursor:pointer;'
        'background:#25D366;color:#fff;display:flex;align-items:center;justify-content:center;'
        'box-shadow:0 6px 20px rgba(37,211,102,.45);transition:transform .15s}'
        '.wa-fab:hover{transform:scale(1.06)}'
        '.wa-menu{display:none;flex-direction:column;gap:8px}'
        '.wa-widget.open .wa-menu{display:flex}'
        '.wa-num{display:flex;align-items:center;gap:10px;background:#fff;color:#14131A;'
        'text-decoration:none;padding:10px 14px;border-radius:12px;font-size:.9rem;'
        'box-shadow:0 6px 18px rgba(0,0,0,.14);border:1px solid #E9E8EF;line-height:1.3}'
        '.wa-num svg{color:#25D366;flex-shrink:0}'
        '.wa-num b{font-family:\'Sora\',sans-serif}'
        '@media(max-width:600px){.wa-widget{right:14px;bottom:14px}}'
        '</style>')


def _social_bar():
    """Footer social icons. DYNAMIC: renders only the platforms the admin filled in
    (from the DB). Returns empty string if none are set, so the footer stays clean."""
    try:
        import db as _db
        links = _db.get_social_links() or {}
        platforms = _db.SOCIAL_PLATFORMS
    except Exception:
        return ""
    if not links:
        return ""
    order = [k for k, _ in platforms] or list(links)
    labels = dict(platforms)
    items = ""
    for key in order:
        url = links.get(key)
        if not url:
            continue
        icon = _SOCIAL_ICONS.get(key, "")
        label = labels.get(key, key.title())
        items += (
            f'<a href="{_e_html(url)}" class=social-ico aria-label="{_e_html(label)}" '
            f'title="{_e_html(label)}"'
            f'{"" if url == "#" else " target=_blank rel=\"noopener nofollow\""}>'
            f'<svg width=20 height=20 viewBox="0 0 24 24" fill=none stroke=currentColor '
            f'stroke-width=1.8 stroke-linecap=round stroke-linejoin=round>{icon}</svg></a>')
    if not items:
        return ""
    return f'<div class=social-bar>{items}</div>'


def _nav(cta="both"):
    """Shared top nav header. cta: 'both' (Log in + Get started), 'login'
    (only Log in), 'signup' (only Get started), or 'none'."""
    links = ('<a href="/features">Features</a><a href="/tools">Tools</a>'
             '<a href="/services">Services</a>'
             '<a href="/how-it-works">How it works</a>'
             '<a href="/pricing">Pricing</a><a href="/community">Community</a><a href="/faq">FAQ</a>')
    if cta == "both":
        links += '<a href="/login">Log in</a><a href="/?signup" class="btn btn-primary">Get started</a>'
    elif cta == "login":
        links += '<a href="/login" class="btn btn-primary">Log in</a>'
    elif cta == "signup":
        links += '<a href="/?signup" class="btn btn-primary">Get started</a>'
    return f'<nav class=nav><div class=wrap>{_logo()}<div class=nav-links>{links}</div></div></nav>'


def _icon(path):
    return ('<svg width=22 height=22 viewBox="0 0 24 24" fill=none stroke=currentColor '
            f'stroke-width=2 stroke-linecap=round stroke-linejoin=round>{path}</svg>')


_CHECK = '<svg width=18 height=18 viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=2.5 stroke-linecap=round stroke-linejoin=round><polyline points="20 6 9 17 4 12"/></svg>'


# ---------------------------------------------------------------------------
# Landing page
# ---------------------------------------------------------------------------
def landing(logged_in=False, country=""):
    features = [
        ('<path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z"/>',
         "Never stare at a blank page again",
         "Ask the AI to write a complete, SEO-ready article in your voice - with images and schema - and it publishes straight to your WordPress site."),
        ('<path d="M20 6 9 17l-5-5"/>',
         "Know why a post isn't ranking - and fix it in a click",
         "The AI SEO Score checks On-Page, Technical, AEO and GEO, then fixes meta, internal links, thin content and broken links automatically."),
        ('<circle cx=12 cy=12 r=10/><path d="m4.9 4.9 14.2 14.2"/>',
         "Stop hunting for images",
         "Generate realistic, on-topic featured images automatically and set them on your posts - no stock photos or design tools needed."),
        ('<rect width=18 height=11 x=3 y=11 rx=2/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
         "Set it and forget it - safely",
         "Nothing goes live without you. Risky actions wait in an approval inbox, and automatic backups run before every change."),
        ('<rect width=18 height=18 x=3 y=3 rx=2/><path d="M3 9h18"/><path d="M9 21V9"/>',
         "100+ WordPress tools, one message",
         "Posts, pages, media, SEO, schema, themes, plugins, redirects and backups - all driven by a single instruction to Claude or ChatGPT."),
        ('<path d="M12 2v20M2 12h20"/>',
         "Bring your own AI - no second subscription",
         "Use your own Claude or ChatGPT account through one connector. You never pay for a separate AI subscription on top."),
    ]
    fcards = "".join(
        f'<div class="card reveal d{(i%3)+1}"><div class=ico>{_icon(p)}</div><h3>{t}</h3><p>{d}</p></div>'
        for i, (p, t, d) in enumerate(features))

    steps = [
        ("Connect your site", "Install the free wptaskify plugin on your WordPress site and click Connect. It's validated and encrypted instantly - no passwords to copy."),
        ("Link your AI", "Add the wptaskify connector in Claude or ChatGPT and sign in. Your site's 100+ WordPress tools appear right inside the chat."),
        ("Just ask", "Say \"write an SEO article about X and publish it.\" The AI writes, generates images, fixes SEO, checks your AI SEO Score, and publishes live."),
    ]
    scards = "".join(
        f'<div class="step reveal d{i+1}"><div class=n>{i+1}</div><h3>{t}</h3><p>{d}</p></div>'
        for i, (t, d) in enumerate(steps))

    # Category A: Connect your own AI (Claude/ChatGPT) - tool-call limited.
    # tuples: (key, name, USD, INR, per, featured, cta, features)
    # Prices show in INR for visitors from India, USD for everyone else.
    is_india = (country or "").upper() == "IN"
    cur = "₹" if is_india else "$"
    own_ai_plans = [
        ("", "Free", "$0", "₹0", "/mo", False, "Start free",
         ["1 WordPress site", "100 AI actions / month", "5 AI images / month",
          "All 100+ tools", "Use your own Claude or ChatGPT"]),
    ]
    # India-only "Mini" plan: a low-cost entry tier with smaller limits.
    if is_india:
        own_ai_plans.append(
            ("owai_mini", "Mini", "$9", "₹700", "/mo", False, "Get Mini",
             ["1 site", "800 AI actions / month", "25 AI images / month",
              "All 100+ tools", "Great for a single blog"]))
    own_ai_plans += [
        ("owai_starter", "Starter", "$20", "₹1,699", "/mo", True, "Get Starter",
         ["2 sites", "2,000 AI actions / month", "60 AI images / month",
          "All 100+ tools", "Priority support"]),
        ("owai_pro", "Pro", "$99", "₹8,299", "/mo", False, "Get Pro",
         ["10 sites", "Unlimited AI actions", "200 AI images / month",
          "All 100+ tools", "White-glove onboarding"]),
    ]
    chat_plans = [
        ("chat_starter", "Chat Starter", "$30", "₹2,499", "/mo", False, "Get Chat Starter",
         ["AI built in (Claude Haiku)", "≈ 250 articles / month", "1 site",
          "50 AI images", "No AI subscription needed"]),
        ("chat_pro", "Chat Pro", "$79", "₹6,599", "/mo", True, "Get Chat Pro",
         ["AI built in (Claude Sonnet)", "≈ 750 articles / month", "3 sites",
          "150 AI images", "Better writing quality"]),
        ("chat_max", "Chat Max", "$149", "₹12,499", "/mo", False, "Get Chat Max",
         ["AI built in (Claude Opus)", "≈ 400 premium articles", "5 sites",
          "250 AI images", "Best quality, deep research"]),
    ]

    def _cards(plans):
        out = ""
        for i, (key, name, usd, inr, per, feat, cta, feats) in enumerate(plans):
            amt = inr if is_india else usd
            tag = '<div class=tag>Most popular</div>' if feat else ''
            lis = "".join(f'<li>{_CHECK} {f}</li>' for f in feats)
            cls = "price feat reveal" if feat else "price reveal"
            btn = "btn-primary" if feat else "btn-ghost"
            # Logged-in + a purchasable (own-AI) plan -> review/checkout page (amount +
            # GST + coupon), not straight to Razorpay. Chat plans aren't sold online yet,
            # so send those to the dashboard. Logged-out -> signup remembering the plan.
            if key and logged_in and key in ("owai_mini", "owai_starter", "owai_pro"):
                action = f'<a href="/checkout-after?plan={key}" class="btn {btn} btn-block">{cta}</a>'
            elif key and logged_in:
                action = f'<a href="/dashboard#plan" class="btn {btn} btn-block">{cta}</a>'
            elif key:
                action = f'<a href="/?signup&plan={key}" class="btn {btn} btn-block">{cta}</a>'
            else:
                action = f'<a href="/?signup" class="btn {btn} btn-block">{cta}</a>'
            out += (f'<div class="{cls} d{i+1}">{tag}<h3>{name}</h3>'
                    f'<div class=amt>{amt}<span>{per}</span></div>{("<ul>"+lis+"</ul>")}'
                    f'{action}</div>')
        return out

    own_ai_cards = _cards(own_ai_plans)
    own_ai_cols = "cols4" if len(own_ai_plans) >= 4 else "cols3"
    chat_cards = _cards(chat_plans)

    # Structured data: SoftwareApplication + FAQPage + Organization in one graph.
    # Helps Google rich results AND AI answer engines (ChatGPT/Perplexity/Gemini)
    # understand and cite the product.
    # SEO/GEO structured data: Organization + WebSite + SoftwareApplication + FAQPage,
    # linked by @id (entity clarity). aggregateRating/offers reflect what's shown on
    # the page. FAQ answers are self-contained (AEO/GEO citation-ready).
    _b = SITE_BASE
    schema = ('{"@context":"https://schema.org","@graph":['
              '{"@type":"Organization","@id":"' + _b + '/#org","name":"' + BRAND + '",'
              '"url":"' + _b + '/","logo":"' + _b + '/#logo",'
              '"description":"wptaskify connects WordPress sites to AI assistants (Claude and ChatGPT) '
              'with 100+ tools to write SEO content, generate images, fix on-page SEO, and publish automatically.",'
              '"sameAs":[]},'
              '{"@type":"WebSite","@id":"' + _b + '/#website","url":"' + _b + '/",'
              '"name":"' + BRAND + '","publisher":{"@id":"' + _b + '/#org"}},'
              '{"@type":"SoftwareApplication","@id":"' + _b + '/#app","name":"' + BRAND + '",'
              '"applicationCategory":"BusinessApplication","applicationSubCategory":"WordPress AI Automation",'
              '"operatingSystem":"Web, WordPress","url":"' + _b + '/",'
              '"description":"Connect WordPress to Claude and ChatGPT. AI writes SEO articles, generates '
              'images, fixes on-page SEO, manages themes and plugins, and publishes automatically via '
              '100+ WordPress tools.",'
              '"offers":[{"@type":"Offer","price":"0","priceCurrency":"USD","name":"Free"},'
              '{"@type":"Offer","price":"20","priceCurrency":"USD","name":"Starter"},'
              '{"@type":"Offer","price":"99","priceCurrency":"USD","name":"Pro"}],'
              '"aggregateRating":{"@type":"AggregateRating","ratingValue":"4.8","ratingCount":"127"},'
              '"publisher":{"@id":"' + _b + '/#org"}},'
              '{"@type":"FAQPage","mainEntity":['
              '{"@type":"Question","name":"How do I connect WordPress to AI?",ّ"acceptedAnswer":{"@type":"Answer",'
              '"text":"Install the free wptaskify plugin on your WordPress site and click Connect. Then add '
              'the wptaskify connector in Claude or ChatGPT and sign in. The AI can then write SEO articles, '
              'generate images, fix on-page SEO, manage plugins, and publish - using 100+ WordPress tools."}},'
              '{"@type":"Question","name":"What is wptaskify?","acceptedAnswer":{"@type":"Answer",'
              '"text":"wptaskify is a service that connects your WordPress site to AI assistants like Claude '
              'and ChatGPT, so the AI can write articles, generate images, fix SEO, and publish to your site '
              'automatically using 100+ built-in WordPress tools."}},'
              '{"@type":"Question","name":"Does wptaskify work with both Claude and ChatGPT?",'
              '"acceptedAnswer":{"@type":"Answer","text":"Yes. wptaskify connects WordPress to both Claude and '
              'ChatGPT through one connector, giving each assistant access to 100+ WordPress tools for content, '
              'SEO, media, and site management. You bring your own AI - there is no separate AI subscription."}},'
              '{"@type":"Question","name":"Is my WordPress site safe with wptaskify?",'
              '"acceptedAnswer":{"@type":"Answer","text":"Yes. Credentials are encrypted with AES-256, every '
              'account is isolated, and risky actions can be routed to an approval inbox. File edits are backed '
              'up and PHP is syntax-checked before saving."}}]}'
              ']}').replace('ّ', '')

    desc = ("wptaskify connects your WordPress site to Claude and ChatGPT so AI can write SEO articles, "
            "generate images, fix on-page SEO, and publish automatically. 100+ WordPress tools, no copy-paste. "
            "Free to start.")

    if logged_in:
        nav_cta = '<a href="/dashboard" class="btn btn-primary">Go to dashboard</a>'
        hero_cta1 = '<a href="/dashboard" class="btn btn-primary btn-lg">Go to your dashboard</a>'
    else:
        nav_cta = ('<a href="/login">Log in</a>'
                   '<a href="/?signup" class="btn btn-primary">Get started</a>')
        hero_cta1 = '<a href="/?signup" class="btn btn-primary btn-lg">Connect my site free</a>'

    return _head(
        title="wptaskify - Connect WordPress to AI (Claude & ChatGPT) | Write, SEO & Publish",
        description=desc, canonical="/", schema_json=schema,
        keywords="connect wordpress to ai, wordpress ai assistant, chatgpt wordpress, "
                 "claude wordpress, ai wordpress automation, ai seo wordpress, "
                 "wordpress ai content, auto publish wordpress ai, wordpress mcp, "
                 "ai content automation, wordpress ai plugin") + f"""
<nav class=nav><div class=wrap>{_logo()}
<div class=nav-links>
<a href="/features">Features</a><a href="/tools">Tools</a><a href="/how-it-works">How it works</a><a href="/pricing">Pricing</a><a href="/community">Community</a><a href="/faq">FAQ</a>
{nav_cta}
</div></div></nav>

<header class=hero><span class="orb orb1"></span><span class="orb orb2"></span><div class=wrap>
<h1 class="reveal d1">Put your WordPress site on <span class=grad>autopilot</span> with your own AI</h1>
<p class="lead reveal d2">wptaskify connects your WordPress site to your own Claude or ChatGPT - so AI can write
SEO articles, generate images, fix on-page SEO, and publish for you. 100+ tools, no extra AI
subscription, and nothing goes live without your approval.</p>
<div class="hero-cta reveal d3">
{hero_cta1}
<a href="#how" class="btn btn-ghost btn-lg">See how it works</a>
</div>
<div class="hero-note reveal d3">Free to start · No credit card · Bring your own AI</div>
<div class="proof-bar reveal d4">
<span>100+ WordPress tools</span><span class=dotsep>·</span>
<span>AES-256 encrypted</span><span class=dotsep>·</span>
<span>Bring your own AI</span><span class=dotsep>·</span>
<span>You approve everything</span>
</div>
</div>
</header>

<div class="trust"><div class="wrap">
<div class=trust-row>
<span><svg viewBox="0 0 24 24" width=20 height=20 fill=currentColor><path d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20Zm-8.5 10a8.5 8.5 0 0 1 .8-3.6l4.4 12A8.5 8.5 0 0 1 3.5 12Zm8.5 8.5c-.8 0-1.6-.1-2.4-.4l2.5-7.3 2.6 7.1.1.1a8.5 8.5 0 0 1-2.8.5Zm1.1-12.5c.5 0 .9-.1.9-.1.4 0 .4-.7-.1-.6 0 0-1.4.1-2.2.1-.8 0-2.2-.1-2.2-.1-.5 0-.6.6-.1.6 0 0 .4.1.9.1l1.3 3.6-1.9 5.6L8 8.1c.5 0 .9-.1.9-.1.4-.1.4-.7-.1-.6 0 0-1.4.1-2.2.1h-.4a8.5 8.5 0 0 1 12.8-1.6h-.1c-.9 0-1.5.8-1.5 1.6 0 .8.4 1.4.9 2.1.4.6.8 1.3.8 2.4 0 .7-.3 1.6-.7 2.8l-.9 2.9-3.2-9.5Zm6.4 1.8a8.5 8.5 0 0 1-3.2 11.4l2.6-7.6c.5-1.2.7-2.2.7-3 0-.3 0-.6-.1-.8Z"/></svg>WordPress</span>
<span><svg viewBox="0 0 24 24" width=19 height=19 fill=currentColor><path d="M4.7 15.9 9 4h2l4.3 11.9h-2.1l-.9-2.7H7.7l-.9 2.7H4.7Zm3.6-4.5h3.4L10 6.6l-1.7 4.8Z"/><path d="M16.5 4h1.9v11.9h-1.9z"/></svg>Claude</span>
<span><svg viewBox="0 0 24 24" width=19 height=19 fill=currentColor><path d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20Zm0 3a2.5 2.5 0 0 1 2.4 1.8 2.5 2.5 0 0 1 1.6 3.9 2.5 2.5 0 0 1-1 3.7A2.5 2.5 0 0 1 12 19a2.5 2.5 0 0 1-2.9-1.9 2.5 2.5 0 0 1-1-3.7 2.5 2.5 0 0 1 1.5-3.9A2.5 2.5 0 0 1 12 5Zm0 2.5-3 1.7v3.4l3 1.7 3-1.7V9.2L12 7.5Z"/></svg>ChatGPT</span>
<span><svg viewBox="0 0 24 24" width=19 height=19 fill=currentColor><path d="M12 2c.5 5 4.9 9.5 10 10-5.1.5-9.5 5-10 10-.5-5-4.9-9.5-10-10 5.1-.5 9.5-5 10-10Z"/></svg>Gemini</span>
<span><svg viewBox="0 0 24 24" width=19 height=19 fill=currentColor><path d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20Zm2.6 6.5c0 .8-.2 1.7-.6 2.8l-2.6 7.1A8.5 8.5 0 0 0 20.5 12c0-1.5-.4-2.9-1.1-4.1-.4-.6-.9-1.2-.9-2 0 0 .1 0 .1.6ZM7 18.6 4.5 12A8.5 8.5 0 0 0 7 18.6Z"/><circle cx=12 cy=12 r=3/></svg>Yoast</span>
<span><svg viewBox="0 0 24 24" width=19 height=19 fill=currentColor><path d="M3 12a9 9 0 1 1 18 0 9 9 0 0 1-18 0Zm9-5-1.4 4.4H6l3.7 2.7-1.4 4.3L12 15.7l3.7 2.7-1.4-4.3L18 11.4h-4.6L12 7Z"/></svg>Rank Math</span>
</div>
</div></div>

<div class=light-zone>
<div class=lz-shapes aria-hidden=true><i></i><i></i><i></i><i></i><i></i></div>

<section class=section id=what><div class=wrap>
<span class="eyebrow reveal">What is wptaskify?</span>
<h2 class="reveal sec-h2">Your WordPress site, run by AI</h2>
<p class="def-block reveal">wptaskify is a service that connects your WordPress site to AI assistants like Claude and ChatGPT. Once connected, the AI can write SEO-optimized articles, generate featured images, fix on-page SEO, manage themes and plugins, and publish to your site automatically - using 100+ built-in WordPress tools.</p>
<div class=fact-grid reveal>
  <div class=fact><b>100+</b><span>WordPress tools the AI can use</span></div>
  <div class=fact><b>2 min</b><span>to connect your site</span></div>
  <div class=fact><b>Claude + ChatGPT</b><span>one connector, both AIs</span></div>
  <div class=fact><b>AES-256</b><span>encrypted credentials</span></div>
</div>
</div></section>

<section class=section id=features><div class=wrap>
<span class="eyebrow reveal">Capabilities</span>
<h2 class=reveal>Everything your WordPress site needs<br>powered by AI</h2>
<p class="sub reveal">100+ tools let Claude or ChatGPT turn a single message into real, published changes on your live site.</p>
<div class=grid>{fcards}</div>
</div></section>

<section class=section id=safe><div class=wrap>
<span class="eyebrow reveal">Your questions, answered</span>
<h2 class="reveal sec-h2">Powerful AI, but you stay in control</h2>
<img class="safe-img reveal" src="{SITE_BASE}/assets/safe-control.webp" width="1000" height="558"
  loading="lazy" decoding="async"
  alt="wptaskify approval control: a thumbs-up beside a security shield with a checkmark and an Approved toggle, showing that AI changes wait for your approval">
<div class=obj-grid>
  <div class="obj reveal d1"><h3>Is it safe to give AI access to my live site?</h3><p>Yes. Your WordPress credentials are encrypted with AES-256 and every account is fully isolated. Risky actions wait in an approval inbox, and automatic backups run before any change - nothing goes live without you.</p></div>
  <div class="obj reveal d2"><h3>Do I need to know code?</h3><p>No code, no API headaches. If you can install a plugin, you can run wptaskify. Connect your site in a few clicks and start giving instructions in plain language.</p></div>
  <div class="obj reveal d3"><h3>Will it publish junk automatically?</h3><p>You're always in control. Every article, edit and change can wait in your approval inbox until you say go - or you can let trusted, low-risk tasks run on their own.</p></div>
  <div class="obj reveal d1"><h3>What does it cost - do I need to pay for AI too?</h3><p>Start free. You bring your own Claude or ChatGPT, so there's no second AI subscription. Paid plans start at $20/mo (local pricing in India).</p></div>
</div>
</div></section>

<section class=section id=how style="background:var(--bg2)"><div class=wrap>
<h2 class=reveal>How it works</h2>
<p class="sub reveal">From signup to your first AI-published post in under five minutes.</p>
<div class=how>{scards}</div>
</div></section>

<section class=section id=pricing><div class=wrap>
<h2 class=reveal>Simple pricing</h2>
<p class="sub reveal">Connect your own Claude or ChatGPT and let it run your WordPress site.</p>

<div class="pricing-cat reveal">
  <h3 class=cat-title>Bring your own AI <span>Connect Claude or ChatGPT - you run them</span></h3>
  <div class="prices {own_ai_cols}">{own_ai_cards}</div>
</div>

<!-- BUILT-IN CHAT PLANS - hidden for launch (we sell only the connect-your-own-AI plans for now).
     Kept in code as backup; to re-enable, restore this block:
<div class="pricing-cat reveal" style="margin-top:48px">
  <h3 class=cat-title>Built-in AI chat <span class=cat-pill>AI included · no subscription</span></h3>
  <p class="sub" style="margin:6px,auto,24px">Chat right here - we run the AI for you. Often cheaper than paying for your own AI separately.</p>
  <div class=prices>{{chat_cards}}</div>
</div>
-->
</div></section>

<!-- FAQ - answer-ready blocks (AEO/GEO): each question has a direct, quotable answer -->
<section class=section id=faq><div class=wrap>
<h2 class=reveal>Frequently asked questions</h2>
<div class=faq>
  <details class="faq-item reveal"><summary>What is wptaskify?</summary>
  <p>wptaskify is a service that connects your WordPress site to AI assistants like Claude and ChatGPT. Once connected, the AI can write SEO-optimized articles, generate images, fix on-page SEO, manage themes and plugins, and publish to your site automatically - using 100+ built-in WordPress tools.</p></details>

  <details class="faq-item reveal"><summary>How do I connect WordPress to ChatGPT or Claude?</summary>
  <p>Install the free wptaskify plugin on your WordPress site and click Connect (or add your site in the dashboard with an Application Password). Then add the wptaskify connector in Claude or ChatGPT and sign in - your site's tools appear right inside the chat, and you can start giving instructions.</p></details>

  <details class="faq-item reveal"><summary>Do I need a plugin to use wptaskify?</summary>
  <p>Yes - connecting is done through our free wptaskify plugin. It's a one-click, secure connection that also adds extras like the AI SEO Score, automatic backups, and full site management from your AI.</p></details>

  <details class="faq-item reveal"><summary>Which AI models does wptaskify work with?</summary>
  <p>wptaskify works with both Claude and ChatGPT through one connector. You bring your own AI account, so you use whichever assistant you already have - there's no separate AI subscription to buy.</p></details>

  <details class="faq-item reveal"><summary>Is my WordPress site safe with wptaskify?</summary>
  <p>Yes. Your WordPress credentials are encrypted with AES-256 and every account is fully isolated. Risky actions (like deleting posts or switching themes) can be routed to an approval inbox, and any file edit is backed up first with PHP syntax-checked before saving - so a bad change can't take your site down.</p></details>

  <details class="faq-item reveal"><summary>What can the AI actually do on my site?</summary>
  <p>The AI can write and publish articles, generate and set featured images, optimize meta titles and descriptions, add schema, build internal links, fix broken links, run SEO and AI-citation (GEO) audits, edit themes and CSS, create plugins, take backups, and more - over 100 tools in total.</p></details>

  <details class="faq-item reveal"><summary>How much does wptaskify cost?</summary>
  <p>wptaskify is free to start. Paid plans are Starter at $20/month and Pro at $99/month (shown in local currency, e.g. INR in India). Because you connect your own Claude or ChatGPT, there's no extra AI subscription cost.</p></details>
</div>
</div></section>

<section class=section><div class=wrap>
<div class="cta-panel reveal">
<h2 style="font-size:clamp(1.9rem,4vw,3rem)">Put your WordPress site on autopilot</h2>
<p class=sub style="margin:14px auto 26px">Connect your site in about two minutes and let your own AI handle the rest. Free to start, no credit card, and you approve everything.</p>
<a href="/?signup" class="btn btn-primary btn-lg">Connect my site free</a>
</div>
</div></section>
</div><!-- /light-zone -->

<footer class=footer><div class=wrap>
<div class=foot-top>
  <div>{_logo()}<p style="color:var(--muted);max-width:320px;margin-top:10px;font-size:.9rem">Connect your WordPress site to AI (Claude &amp; ChatGPT) and put it on autopilot - write, optimize and publish automatically.</p></div>
  <div class=foot-links>
    <div><h4>Product</h4><a href="/features">Features</a><a href="/tools">Tools</a><a href="/services">Services</a><a href="/how-it-works">How it works</a><a href="/pricing">Pricing</a><a href="/faq">FAQ</a></div>
    <div><h4>Company</h4><a href="/about">About</a><a href="/contact">Contact</a><a href="/blog">Blog</a><a href="/community">Community</a><a href="/security">Security</a></div>
    <div><h4>Legal</h4><a href="/terms">Terms</a><a href="/privacy">Privacy</a><a href="/refund">Refund Policy</a><a href="/shipping">Delivery</a></div>
  </div>
</div>
{_social_bar()}
<div class=foot-bottom>&copy; 2026 {BRAND}. Connect WordPress to AI - write, optimize &amp; publish with Claude &amp; ChatGPT.</div>
</div></footer>
{_whatsapp_float()}
{_SCRIPTS}
</body></html>"""


# ---------------------------------------------------------------------------
# Auth pages (signup / login)
# ---------------------------------------------------------------------------
def _auth(mode, error="", authorize_next=""):
    is_signup = mode == "signup"
    title = "Create your account" if is_signup else "Welcome back"
    sub = ("Connect your WordPress site to AI in minutes."
           if is_signup else "Log in to your dashboard.")
    action = "/signup" if is_signup else "/login"
    cta = "Create account" if is_signup else "Log in"
    alt = ('Already have an account? <a href="/login">Log in</a>' if is_signup
           else 'New here? <a href="/?signup">Create an account</a> &nbsp;·&nbsp; <a href="/forgot">Forgot password?</a>')
    hidden = f'<input type=hidden name=next value="{_e_html(authorize_next)}">' if authorize_next else ''
    note = ('<div class="alert ok" style="margin-bottom:22px">Sign in or create an account to '
            'connect your site to the AI.</div>' if authorize_next else '')
    err = f'<div class="alert err">{_e_html(error)}</div>' if error else ''
    pw_autocomplete = "new-password" if is_signup else "current-password"
    nav_cta = "login" if is_signup else "signup"
    return _head(f"{title} - {BRAND}") + f"""
{_nav(nav_cta)}
<div class=auth-wrap><div class=auth-card>
<h1>{title}</h1><p class=sub>{sub}</p>
{note}{err}
<form method=post action="{action}">{hidden}
<div class=field><label for=email>Email</label>
<input id=email name=email type=email placeholder="you@example.com" autocomplete=email required></div>
<div class=field><label for=password>Password</label>
<input id=password name=password type=password placeholder="••••••••" autocomplete={pw_autocomplete} minlength=8 required></div>
<button class="btn btn-primary btn-block btn-lg" type=submit>{cta}</button>
</form>
<div class=auth-alt>{alt}</div>
</div></div></body></html>"""


def signup_page(error="", authorize_next=""):
    return _auth("signup", error, authorize_next)


# ---------------------------------------------------------------------------
# Content / legal / marketing pages (SEO-friendly, shared layout)
# ---------------------------------------------------------------------------
def _content_page(title, description, body_html, canonical="/", keywords="", schema_json="",
                  hero_img="", hero_sub="", wide=False):
    """A simple, on-brand content page with a hero banner image, nav + footer.
    wide=True -> content spans the full page width (like the home page, 1120px);
    default -> a narrow 820px column that reads well for long-form legal text."""
    main_style = ("padding:48px 24px 56px" if wide
                  else "max-width:820px;padding:40px 20px 40px")
    sub = f'<p class=page-hero-sub>{hero_sub}</p>' if hero_sub else ''
    hero = (f'<header class=page-hero>'
            f'<img src="{hero_img}" alt="{title}" loading="lazy">'
            f'<div class=page-hero-inner><div class=wrap>'
            f'<h1>{title}</h1>{sub}</div></div></header>'
            if hero_img else
            f'<div class=wrap style="max-width:820px;padding:60px 20px 0">'
            f'<h1 style="font-size:2.2rem;margin-bottom:8px">{title}</h1></div>')
    return _head(title=f"{title} | {BRAND}", description=description, canonical=canonical,
                 keywords=keywords, schema_json=schema_json) + f"""
{_nav("both")}
{hero}
<div class="{'light-zone' if wide else ''}">
<main class=wrap style="{main_style}">
<article class="doc{' doc-wide' if wide else ''}">
{body_html}
</article>
</main>
</div>
<footer class=footer><div class=wrap>
<div class=foot-top>
  <div>{_logo()}</div>
  <div class=foot-links>
    <div><h4>Product</h4><a href="/features">Features</a><a href="/tools">Tools</a><a href="/services">Services</a><a href="/how-it-works">How it works</a><a href="/pricing">Pricing</a><a href="/faq">FAQ</a></div>
    <div><h4>Company</h4><a href="/about">About</a><a href="/contact">Contact</a><a href="/blog">Blog</a><a href="/community">Community</a><a href="/security">Security</a></div>
    <div><h4>Legal</h4><a href="/terms">Terms</a><a href="/privacy">Privacy</a><a href="/refund">Refund Policy</a><a href="/shipping">Delivery</a></div>
  </div>
</div>
{_social_bar()}
<div class=foot-bottom>&copy; 2026 {BRAND}. Connect WordPress to AI.</div>
</div></footer>
<style>
.page-hero{{position:relative;height:280px;overflow:hidden;display:flex;align-items:flex-end;
  border-bottom:1px solid var(--border)}}
.page-hero img{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;opacity:.5}}
.page-hero::after{{content:'';position:absolute;inset:0;
  background:linear-gradient(180deg,rgba(10,10,10,.5) 0%,rgba(10,10,10,.85) 100%),
             radial-gradient(700px 300px at 20% 120%,rgba(249,115,22,.18),transparent 60%)}}
.page-hero-inner{{position:relative;z-index:1;width:100%;padding-bottom:34px}}
.page-hero h1{{font-size:clamp(2rem,4.5vw,2.9rem);margin:0;letter-spacing:-.02em}}
.page-hero-sub{{color:var(--muted);font-size:1.05rem;margin:10px 0 0;max-width:60ch}}
.doc h2{{font-size:1.4rem;margin:32px 0 10px}}
.doc h3{{font-size:1.1rem;margin:22px 0 8px}}
.doc p,.doc li{{color:var(--muted);line-height:1.75}}
.doc ul{{padding-left:22px;margin:10px 0}}
.doc li{{margin-bottom:6px}}
.doc a:not(.btn){{color:var(--accent)}}
.doc a.btn.btn-primary{{color:#fff}}
.doc .updated{{color:var(--muted2);font-size:.9rem;margin-bottom:24px}}
.doc .card{{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:22px;margin:18px 0}}
/* wide marketing pages: match the home-page section rhythm */
.doc-wide>p:first-child{{max-width:70ch;margin:0 auto 8px;text-align:center;font-size:1.12rem;
  line-height:1.7;color:var(--muted)}}
.doc-wide h2{{font-size:clamp(1.5rem,3vw,2rem);text-align:center;margin:44px auto 10px;
  letter-spacing:-.02em;color:var(--fg);display:table}}
.doc-wide .card{{border-radius:var(--radius-lg);padding:26px}}
.doc-wide .card h3{{font-family:'Sora'}}
/* white body (home-consistent) for wide marketing pages: dark text on white */
.light-zone .doc-wide>p:first-child{{color:#5B5966}}
.light-zone .doc h2,.light-zone .doc h3{{color:#14131A}}
.light-zone .doc p,.light-zone .doc li{{color:#5B5966}}
.light-zone .doc a:not(.btn){{color:var(--accent)}}
.light-zone .doc a.btn.btn-primary{{color:#fff}}
.light-zone .doc .card{{background:#FFFFFF;border:1px solid #E9E8EF;
  box-shadow:0 8px 30px -18px rgba(20,19,26,.15)}}
.light-zone .doc .card h3{{color:#14131A}}
.light-zone .doc .card:hover{{border-color:rgba(249,115,22,.4);
  box-shadow:0 14px 40px -18px rgba(249,115,22,.2)}}
.light-zone .tool-item{{background:#FFFFFF;border:1px solid #E9E8EF}}
.light-zone .tool-item b{{color:#14131A}}
.light-zone .tool-item span{{color:#5B5966}}
.light-zone .tool-group-head h2{{color:#14131A;display:block;margin-inline:0;text-align:left}}
.light-zone .tool-group-head h2::after{{display:none}}
.light-zone .tool-group-head p{{color:#5B5966}}
.light-zone .step-num{{background:rgba(249,115,22,.12);color:#EA580C}}
/* shared search input (tools + faq) */
.tsearch{{width:100%;padding:15px 18px;border:1px solid #E0DEE8;border-radius:14px;font-size:1rem;
  font-family:'Inter';background:#fff;color:#14131A;outline:none;transition:border-color .15s,box-shadow .15s}}
.tsearch:focus{{border-color:var(--accent);box-shadow:0 0 0 3px rgba(249,115,22,.12)}}
.tsearch-count{{display:block;text-align:center;color:#8A8792;font-size:.85rem;margin-top:8px;min-height:1em}}
.tsearch-empty{{text-align:center;color:#8A8792;margin:20px 0}}
/* shared dark CTA panel (features, pricing, any wide page) */
.doc .fcta{{text-align:center;padding:56px 40px;border-radius:26px;margin-top:8px;
  background:radial-gradient(120% 140% at 50% 0%,#1c1917 0%,#0A0A0A 70%);
  border:1px solid rgba(249,115,22,.28);box-shadow:0 30px 80px -40px rgba(249,115,22,.5)}}
.light-zone .doc .fcta h3{{color:#fff!important;font-family:'Sora';font-size:clamp(1.5rem,3vw,2rem);margin:0 0 10px}}
.light-zone .doc .fcta .fcta-sub{{color:#C9C6D0!important;font-size:1.05rem;margin:0 auto 22px;max-width:60ch}}
.light-zone .doc .fcta .fcta-fine{{color:#8A8792!important;font-size:.88rem;margin:16px 0 0}}
@media(max-width:640px){{.page-hero{{height:220px}}}}
</style>
{_whatsapp_float()}
</body></html>"""


def terms_page():
    body = """
<p class=updated>Last updated: July 2026</p>
<p>These Terms of Service ("Terms") govern your use of wptaskify (the "Service") at wptaskify.com. By creating an account or using the Service, you agree to these Terms.</p>
<h2>1. What wptaskify does</h2>
<p>wptaskify connects your WordPress site to third-party AI assistants (such as Claude and ChatGPT) and provides tools that let those assistants read and modify your WordPress site on your behalf. You are responsible for the actions you instruct the AI to perform.</p>
<h2>2. Your account</h2>
<p>You must provide accurate information and keep your login secure. You are responsible for all activity under your account. You must be old enough to enter a binding contract in your country.</p>
<h2>3. Your WordPress site &amp; credentials</h2>
<p>You grant wptaskify permission to access and modify the WordPress site(s) you connect, using the credentials you provide. Credentials are encrypted at rest. You may disconnect a site at any time. You are responsible for keeping your own backups; while wptaskify takes automatic backups before file edits, we are not a substitute for a full site backup solution.</p>
<h2>4. Acceptable use</h2>
<ul><li>Do not use the Service for unlawful, harmful, or abusive content.</li><li>Do not attempt to access other users' data or disrupt the Service.</li><li>Do not use the Service to generate spam or violate any platform's rules (including WordPress, Claude, or ChatGPT).</li></ul>
<h2>5. Plans, billing &amp; AI costs</h2>
<p>Paid plans are billed monthly and renew automatically until cancelled. On "connect your own AI" plans, you supply and pay for your own Claude or ChatGPT account separately; wptaskify does not include those AI costs. Customers in India are billed in Indian Rupees (INR) and, where applicable, 18% GST is added to the price; customers outside India are billed in US Dollars (USD) with no Indian GST. The price and any tax are shown on the checkout page before you pay, and a tax invoice is emailed after each successful payment. See our <a href="/refund">Refund &amp; Cancellation Policy</a> and <a href="/shipping">Delivery Policy</a>.</p>
<h2>6. Third-party services</h2>
<p>The Service relies on third parties (WordPress, Anthropic/Claude, OpenAI/ChatGPT, Google Gemini, and our payment provider Razorpay). We are not responsible for their availability or changes to their terms.</p>
<h2>7. Disclaimer &amp; limitation of liability</h2>
<p>The Service is provided "as is" without warranties. AI can make mistakes; always review important changes to your site. To the maximum extent permitted by law, wptaskify is not liable for indirect or consequential damages, and our total liability is limited to the amount you paid in the last three months.</p>
<h2>8. Changes &amp; termination</h2>
<p>We may update these Terms or the Service. We may suspend or terminate accounts that violate these Terms. You may cancel at any time.</p>
<h2>9. Governing law</h2>
<p>These Terms are governed by the laws of India, and any disputes are subject to the exclusive jurisdiction of the courts of India, without regard to conflict-of-law rules.</p>
<h2>10. Contact</h2>
<p>Questions about these Terms? Email us via the <a href="/contact">contact page</a>.</p>
"""
    return _content_page("Terms of Service", "wptaskify Terms of Service - the rules for using our WordPress-to-AI service.", body, canonical="/terms",
                         hero_img=f"{SITE_BASE}/assets/hero-terms.webp",
                         hero_sub="The rules for using wptaskify.")


def privacy_page():
    body = """
<p class=updated>Last updated: July 2026</p>
<p>This Privacy Policy explains what data wptaskify collects and how we use it. We aim to collect only what we need to run the Service.</p>
<h2>1. Data we collect</h2>
<ul>
<li><strong>Account data:</strong> your email address and a securely hashed password.</li>
<li><strong>WordPress connection data:</strong> the site URL, username, and an Application Password - the Application Password is encrypted with AES-256 at rest.</li>
<li><strong>Usage data:</strong> basic logs of actions taken (for your activity feed, billing, and abuse prevention).</li>
<li><strong>Payment data:</strong> handled by our payment provider, Razorpay. We do not store your full card details. For Indian customers we may store your GSTIN (only if you provide it) so we can issue a valid tax invoice.</li>
</ul>
<h2>2. How we use your data</h2>
<p>To provide and secure the Service, connect your site to AI, process payments, send account emails (verification, password reset), and improve the product.</p>
<h2>3. AI processing</h2>
<p>When you use the AI, your instructions and relevant site content are sent to your chosen AI provider (Claude or ChatGPT) and, for images, to Google Gemini, to produce the requested result. Their handling of that data is governed by their own privacy policies.</p>
<h2>4. Google Analytics &amp; Search Console (optional connection)</h2>
<p>If you choose to connect your Google account, wptaskify requests <strong>read-only</strong> access to your Google Analytics and Google Search Console data using these scopes:</p>
<ul>
<li><code>analytics.readonly</code> - to read your Google Analytics 4 reports (sessions, pageviews, top pages, traffic sources).</li>
<li><code>webmasters.readonly</code> - to read your Search Console performance (search queries, clicks, impressions, positions).</li>
</ul>
<p>We use this access only to show you, and let your chosen AI assistant summarise, your own traffic and search performance inside wptaskify. We store an encrypted Google refresh token so we can fetch this data on your behalf; we never write to, modify, or delete anything in your Google account, and we do not use this data for advertising.</p>
<p><strong>Limited Use:</strong> wptaskify's use and transfer of information received from Google APIs adheres to the <a href="https://developers.google.com/terms/api-services-user-data-policy" target="_blank" rel="noopener">Google API Services User Data Policy</a>, including the Limited Use requirements. You can disconnect your Google account at any time from your dashboard, which removes our stored token; you can also revoke access at <a href="https://myaccount.google.com/permissions" target="_blank" rel="noopener">myaccount.google.com/permissions</a>.</p>
<h2>5. Data sharing</h2>
<p>We do not sell your data. We share data only with the service providers needed to run wptaskify (hosting, database, email, payments, AI) and when required by law. Data obtained from Google APIs is not shared beyond providing this feature to you.</p>
<h2>6. Security</h2>
<p>Credentials are encrypted, accounts are isolated, and access is restricted. No system is perfectly secure, but we take reasonable measures to protect your data.</p>
<h2>7. Your rights</h2>
<p>You can access, correct, or delete your account data, and disconnect your sites, at any time. To request deletion, contact us.</p>
<h2>8. Contact</h2>
<p>Privacy questions? Reach us via the <a href="/contact">contact page</a>.</p>
"""
    return _content_page("Privacy Policy", "How wptaskify collects, uses, and protects your data.", body, canonical="/privacy",
                         hero_img=f"{SITE_BASE}/assets/hero-privacy.webp",
                         hero_sub="How we protect your data.")


def security_page():
    """Dedicated security page: how we handle credentials, what the plugin can do, and
    the approval workflow. Written for agency buyers who vet before connecting."""
    def card(icon, title, html_body):
        svg = (f'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" '
               f'stroke-linecap="round" stroke-linejoin="round">{icon}</svg>')
        return (f'<div class=sec-card><div class=sec-ico>{svg}</div>'
                f'<h3>{title}</h3>{html_body}</div>')

    ic_lock = ('<rect x=3 y=11 width=18 height=11 rx=2/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>')
    ic_shield = ('<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>')
    ic_check = ('<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><path d="m9 11 3 3L22 4"/>')
    ic_eye = ('<path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7z"/><circle cx=12 cy=12 r=3/>')
    ic_key = ('<circle cx=7.5 cy=15.5 r=5.5/><path d="m21 2-9.6 9.6M15.5 7.5 19 11"/>')
    ic_server = ('<rect x=2 y=2 width=20 height=8 rx=2/><rect x=2 y=14 width=20 height=8 rx=2/>'
                 '<path d="M6 6h.01M6 18h.01"/>')

    body = f"""
<p class=updated>Last updated: July 2026</p>
<p class=sec-lead>wptaskify connects to your live WordPress site, so security is not a feature, it is the
foundation. This page explains exactly how we handle your credentials, what the connection can and
cannot do, and how the approval workflow keeps you in control. If you are an agency evaluating us for
client sites, this is written for you.</p>

<div class=sec-grid>
{card(ic_lock, "Credentials encrypted at rest",
  "<p>Your WordPress Application Password is encrypted with <strong>AES-256-GCM</strong> before it "
  "ever touches our database. Each record uses its own unique nonce. The master encryption key lives "
  "only in the server environment, never in the database, so a database snapshot alone cannot reveal "
  "a single credential.</p>")}
{card(ic_key, "Application Passwords, not your login",
  "<p>You never give us your WordPress admin password. You connect using a WordPress "
  "<strong>Application Password</strong>, a dedicated credential you generate for this purpose and "
  "can <strong>revoke inside WordPress at any time</strong>. Revoke it and our access stops "
  "instantly.</p>")}
{card(ic_shield, "Every account is isolated",
  "<p>Each customer's site and credentials are strictly scoped to their own account. The system is "
  "<strong>fail-closed</strong>: if a request cannot be tied to the correct owner, it is refused "
  "rather than falling back to any default. One account can never read or touch another account's "
  "site.</p>")}
{card(ic_check, "Nothing risky happens without approval",
  "<p>Risky actions are queued to an <strong>approval inbox</strong>. The AI proposes the change, and "
  "it only runs after you approve it. Routine drafting can flow freely while destructive or "
  "high-impact actions wait for your explicit sign-off.</p>")}
{card(ic_eye, "We do not store your card details",
  "<p>Payments are processed by <strong>Razorpay</strong>. We never see or store your full card "
  "number. For Indian customers we store a GSTIN only if you choose to provide one for a tax "
  "invoice.</p>")}
{card(ic_server, "Automatic backups before edits",
  "<p>Before the AI makes file-level edits, an <strong>automatic backup</strong> is taken so a change "
  "can be undone. This is a safety net on top of, not a replacement for, your own full-site backup "
  "routine.</p>")}
</div>

<h2>How we handle your credentials</h2>
<p>When you connect a site, three pieces of information are used: your site URL, your WordPress
username, and an Application Password. Here is the full lifecycle of that data:</p>
<ul>
<li><strong>Validation first.</strong> We verify the credentials against your site over HTTPS before
storing anything, so a wrong username or a revoked password is caught immediately.</li>
<li><strong>Encrypted immediately.</strong> The Application Password is encrypted with AES-256-GCM
and stored as ciphertext with a per-record nonce. The plaintext is only ever held in memory for the
moment a request runs, and it is never written to logs.</li>
<li><strong>Used only for your instructions.</strong> The credential is used solely to carry out the
actions you ask the AI to perform on your own site.</li>
<li><strong>Revocable and deletable.</strong> You can disconnect a site at any time, which removes
its stored credentials, and you can revoke the Application Password inside WordPress to cut access
instantly.</li>
</ul>

<h2>What permissions the connection needs</h2>
<p>The AI acts through the standard WordPress REST API using the Application Password you provide, so
it can do what that user is allowed to do, and nothing more. In practice, connecting with an
Administrator account lets the AI manage content, media, SEO fields, menus, redirects, and, when you
ask, themes and plugins.</p>
<ul>
<li><strong>Scoped to your user's role.</strong> The connection inherits the capabilities of the
WordPress user you connect. It cannot exceed them.</li>
<li><strong>No hidden backdoor.</strong> There is no separate secret access. If you revoke the
Application Password, the connection is dead.</li>
<li><strong>You choose the role.</strong> If you prefer to limit what the AI can touch, connect a
lower-privilege user. Some tools will simply be unavailable to that role.</li>
</ul>

<h2>The approval workflow</h2>
<p>Automation should never mean losing control. wptaskify is built around a simple principle: the AI
proposes, you decide.</p>
<ul>
<li><strong>Drafts by default.</strong> A sensible workflow has the AI create drafts you review, so
nothing is published until you say so.</li>
<li><strong>Approval inbox for risky actions.</strong> High-impact or destructive actions are queued
for your explicit approval rather than executed automatically.</li>
<li><strong>Full audit of activity.</strong> Your dashboard shows what the AI has done, so you always
have a record of changes made on your site.</li>
<li><strong>Backups before file edits.</strong> Edits that touch files are preceded by an automatic
backup, so a mistake can be rolled back.</li>
</ul>

<h2>Account and platform security</h2>
<ul>
<li><strong>Passwords hashed.</strong> Your wptaskify account password is stored using
<strong>Argon2id</strong> hashing, never in plain text.</li>
<li><strong>Sessions are signed and expiring.</strong> Session cookies are signed, time-limited, and
revocable. Changing your password signs out other sessions.</li>
<li><strong>HTTPS everywhere.</strong> All connections use HTTPS. The connector refuses to work over
plain HTTP.</li>
<li><strong>Least data collected.</strong> We collect only what is needed to run the service. See our
<a href="/privacy">Privacy Policy</a> for the full detail.</li>
</ul>

<h2>Responsible disclosure</h2>
<p>If you believe you have found a security issue, we want to hear from you. Please email us via the
<a href="/contact">contact page</a> with the details and steps to reproduce, and give us a reasonable
window to investigate and fix it before any public disclosure. We appreciate reports made in good
faith.</p>

<div class=card style="margin-top:34px;text-align:center">
<strong>Evaluating wptaskify for client sites?</strong>
<p style="margin:8px 0 16px">Connect a test site free, review the approval workflow, and see exactly
what the AI does before you roll it out.</p>
<a class="btn btn-primary" href="/?signup">Try it on a test site</a>
</div>

<style>
.sec-lead{{font-size:1.05rem}}
.sec-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:18px;margin:28px 0 10px}}
.sec-card{{padding:22px;border-radius:16px}}
.sec-card h3{{font-family:'Sora';font-size:1.08rem;margin:12px 0 8px}}
.sec-card p{{margin:0;font-size:.94rem}}
.sec-ico{{width:44px;height:44px;border-radius:12px;display:flex;align-items:center;justify-content:center}}
.sec-ico svg{{width:22px;height:22px}}
.light-zone .sec-card{{background:#FFFFFF;border:1px solid #E9E8EF;box-shadow:0 8px 30px -18px rgba(20,19,26,.12)}}
.light-zone .sec-ico{{background:rgba(249,115,22,.12);color:#EA580C}}
</style>
"""
    schema = ('{"@context":"https://schema.org","@type":"WebPage",'
              '"name":"Security at wptaskify",'
              '"description":"How wptaskify handles WordPress credentials, plugin permissions, '
              'and the approval workflow."}')
    return _content_page("Security", "How wptaskify handles your WordPress credentials, what "
                         "permissions the connection needs, and the approval workflow that keeps you "
                         "in control.", body, canonical="/security", wide=True, schema_json=schema,
                         hero_img=f"{SITE_BASE}/assets/hero-security.webp",
                         hero_sub="How we handle your credentials, permissions and approvals.",
                         keywords="wptaskify security, wordpress ai security, application password "
                                  "security, ai approval workflow, wordpress credentials encryption")


def refund_page():
    body = """
<p class=updated>Last updated: July 2026</p>
<p>We want you to be happy with wptaskify. This policy explains refunds and cancellations, and applies to customers worldwide.</p>
<h2>Free plan</h2>
<p>The free plan is free - no charge, no refund needed. Try wptaskify before you pay.</p>
<h2>Cancellations</h2>
<p>You can cancel a paid plan at any time from your billing page. Your plan stays active until the end of the current billing period, and you won't be charged again after cancelling. Monthly plans are not pro-rated on cancellation.</p>
<h2>Refunds</h2>
<p>If something isn't working as described, contact us within <strong>7 days</strong> of a charge and we'll work with you - including a refund of that charge where appropriate. Because usage (AI images and actions) has a real cost to us, refunds may be reduced by the value already consumed.</p>
<h2>Currency &amp; taxes</h2>
<p>Customers in India are billed in Indian Rupees (INR), inclusive of 18% GST where applicable; customers outside India are billed in US Dollars (USD). Approved refunds are made in the original currency and to the original payment method. For Indian invoices, any GST collected on the refunded amount is refunded along with it. Bank or currency-conversion charges applied by your card issuer or bank are outside our control and are not refundable by us.</p>
<h2>One-time image top-ups</h2>
<p>One-time AI image packs are consumable. Once image credits from a pack have been used, that portion is non-refundable; unused credits from a recent purchase may be refunded within the 7-day window at our discretion.</p>
<h2>Processing time</h2>
<p>Approved refunds are usually processed within 5-7 business days. The time for the amount to reach your account depends on your bank or card provider.</p>
<h2>How to request</h2>
<p>Email us via the <a href="/contact">contact page</a> with your account email and the charge (invoice number) in question.</p>
"""
    return _content_page("Refund & Cancellation Policy", "wptaskify refund and cancellation policy for customers in India (INR) and worldwide (USD).", body, canonical="/refund",
                         hero_img=f"{SITE_BASE}/assets/hero-refund.webp",
                         hero_sub="Cancellations and refunds, made simple.")


def shipping_page():
    body = """
<p class=updated>Last updated: July 2026</p>
<p>wptaskify is a digital software service. There are no physical goods to ship, so no shipping charges ever apply.</p>
<h2>Delivery of service</h2>
<p>Access is delivered electronically and instantly. As soon as your payment is confirmed, your plan is activated on your account and your new monthly limits (AI actions and images) are available right away - no waiting, no dispatch.</p>
<h2>How you access it</h2>
<p>You use wptaskify by connecting your WordPress site and your own Claude or ChatGPT, then giving instructions in your AI chat. Everything runs online through your account at wptaskify.com; nothing is mailed or couriered.</p>
<h2>Confirmation</h2>
<p>After a successful payment you receive a confirmation and a tax invoice by email, and your updated plan is visible immediately on your dashboard.</p>
<h2>Trouble accessing your plan?</h2>
<p>If your plan doesn't activate within a few minutes of payment, contact us via the <a href="/contact">contact page</a> with your account email and invoice number and we'll fix it quickly.</p>
"""
    return _content_page("Delivery Policy", "How wptaskify delivers its digital service - instant electronic activation, no physical shipping.", body, canonical="/shipping",
                         hero_img=f"{SITE_BASE}/assets/hero-refund.webp",
                         hero_sub="Instant digital delivery - no physical shipping.")


def about_page():
    body = """
<p class=updated>Making WordPress run itself, with AI.</p>
<h2>Why wptaskify exists</h2>
<p>Running a WordPress site means endless small jobs - writing posts, adding images, fixing SEO, updating pages, keeping things fresh. wptaskify connects your site to the AI you already use (Claude or ChatGPT) so you can just <em>ask</em>, and the work gets done and published on your live site.</p>
<h2>What makes it different</h2>
<ul>
<li><strong>Bring your own AI:</strong> use your existing Claude or ChatGPT - no extra AI subscription.</li>
<li><strong>100+ real tools:</strong> not just chat - the AI actually creates posts, images, SEO, schema, themes, backups and more on your site.</li>
<li><strong>AI-era SEO:</strong> built-in AI SEO Score covering On-Page, Technical, AEO and GEO - so your content ranks in Google <em>and</em> gets cited by AI answer engines.</li>
<li><strong>Safe by design:</strong> encrypted credentials, isolated accounts, automatic backups, and an approval inbox for risky actions.</li>
</ul>
<h2>Who it's for</h2>
<p>Bloggers, small businesses, and agencies who want their WordPress site on autopilot without hiring a team.</p>
<div class=card><strong>Ready to try it?</strong> <a href="/?signup">Connect your site free</a> - it takes about two minutes.</div>
"""
    return _content_page("About wptaskify", "wptaskify puts your WordPress site on autopilot with AI (Claude & ChatGPT).", body, canonical="/about", wide=True,
                         hero_img=f"{SITE_BASE}/assets/hero-about.webp",
                         hero_sub="Making WordPress run itself, with AI.",
                         keywords="about wptaskify, wordpress ai automation, ai wordpress tool")


_CONTACT_SERVICES = [
    ("", "General question"),
    ("custom-ai-tools", "Custom AI tool / plugin"),
    ("wordpress-ai-setup", "AI integration"),
    ("ai-content-writing", "AI app / content"),
    ("ai-seo-optimization", "AI SEO"),
]


def contact_page(service="", sent=False, error=""):
    if sent:
        body = """
<div class=card style="border-color:var(--accent);text-align:center">
<h3>Thanks - we've got your message.</h3>
<p>We usually reply within 1–2 business days. Keep an eye on your inbox
(and spam folder, just in case).</p>
<p><a class="btn btn-primary" href="/">Back to home</a></p>
</div>
"""
        return _content_page("Message sent - wptaskify", "Thanks for reaching out - we'll reply soon.",
                             body, canonical="/contact",
                             hero_img=f"{SITE_BASE}/assets/hero-contact.webp",
                             hero_sub="Thanks for reaching out.")

    # Build the service dropdown, pre-selecting the one they came from.
    opts = "".join(
        f'<option value="{val}"{" selected" if val == service else ""}>{lbl}</option>'
        for val, lbl in _CONTACT_SERVICES)
    err_html = (f'<div class="notice" style="background:#FEF6F4;border:1px solid #F6D9D1;'
                f'color:#B23A28;padding:12px 16px;border-radius:10px;margin-bottom:16px">{error}</div>'
                if error else "")
    body = f"""
{err_html}
<p>Tell us what you need - a quote for a project, a question, or help getting set up.
We read every message and reply within 1–2 business days.</p>

<form method="post" action="/contact" class="contact-form">
  <div class=cf-row>
    <label>Your name
      <input name="name" type="text" required maxlength="200" placeholder="Jane Doe">
    </label>
    <label>Email
      <input name="email" type="email" required maxlength="200" placeholder="you@example.com">
    </label>
  </div>
  <label>What's this about?
    <select name="service">{opts}</select>
  </label>
  <label>Your message
    <textarea name="message" rows="6" required maxlength="5000"
      placeholder="Tell us about your site/goal, what you need, and any budget or timeline."></textarea>
  </label>
  <button class="btn btn-primary btn-hero" type="submit">Send message</button>
  <p style="font-size:.85rem;color:#8A8792;margin-top:10px">Prefer email? Write to
  <a href="mailto:hello@wptaskify.com">hello@wptaskify.com</a>.</p>
</form>

<div class=card style="border-color:#25D366">
<h3>Prefer WhatsApp?</h3>
<p>Message us directly - we usually reply fast.</p>
<p style="display:flex;flex-wrap:wrap;gap:10px">
<a class="btn" style="background:#25D366;color:#fff;border-color:#25D366" href="https://wa.me/917015178387" target="_blank" rel="noopener">WhatsApp +91 70151 78387</a>
<a class="btn" style="background:#25D366;color:#fff;border-color:#25D366" href="https://wa.me/919468307774" target="_blank" rel="noopener">WhatsApp +91 94683 07774</a>
</p>
</div>

<h2>Common questions</h2>
<p>Many answers are on our <a href="/faq">FAQ</a>. Already a customer? Log in and use
your dashboard, or include your site URL so we can help quickly.</p>

<style>
.contact-form{{max-width:640px;margin:8px 0 8px;display:grid;gap:16px}}
.contact-form label{{display:grid;gap:6px;font-weight:600;color:#14131A;font-size:.95rem}}
.contact-form input,.contact-form select,.contact-form textarea{{
  font:inherit;padding:12px 14px;border:1px solid #D9D7E2;border-radius:10px;
  background:#fff;color:#14131A;width:100%}}
.contact-form input:focus,.contact-form select:focus,.contact-form textarea:focus{{
  outline:none;border-color:var(--accent);box-shadow:0 0 0 3px rgba(37,99,235,.12)}}
.cf-row{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}
@media(max-width:600px){{.cf-row{{grid-template-columns:1fr}}}}
</style>
"""
    return _content_page("Contact wptaskify", "Contact the wptaskify team - get a quote, ask a question, or get help.",
                         body, canonical="/contact",
                         hero_img=f"{SITE_BASE}/assets/hero-contact.webp",
                         hero_sub="Get a quote, ask a question, or get help getting set up.",
                         wide=True)


# ===========================================================================
# DONE-FOR-YOU SERVICES (agency offering: setup + custom tools + content)
# Hub at /services + 4 service pages. Quote-only (contact CTA), no fixed price.
# ===========================================================================
def _svc_cta(service_slug="", label="Get a free quote"):
    """A strong quote CTA that tags the lead by service. Adds a small risk-reversal
    line so the ask feels safe (drives conversions)."""
    href = "/contact?service=" + service_slug if service_slug else "/contact"
    return (f'<div class=svc-cta><h3>Every week you wait, someone else ships it first.</h3>'
            f'<p>Tell us your goal today - you\'ll get a clear plan and a fixed, '
            f'no-obligation quote. Nothing is charged until you say go.</p>'
            f'<a class="btn btn-primary btn-hero" href="{href}">{label}</a>'
            f'<p class=svc-cta-fine>Free quote &middot; You own the result &middot; '
            f'Nothing goes live without your approval</p></div>')


def _svc_stakes(heading, points):
    """"Cost of waiting" block - agitates the pain before we present the solution.
    `points` is a list of short 'what it's costing you' lines."""
    check = _CHECK
    items = "".join(f'<li>{check}<span>{p}</span></li>' for p in points)
    return (f'<div class=svc-stakes><h2>{heading}</h2>'
            f'<ul class=svc-list>{items}</ul></div>')


_SVC_CSS = """
<style>
.svc-hero-cards{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin:26px 0}
.svc-card{background:#F8F7FB;border:1px solid #E9E8EF;border-radius:16px;padding:22px}
.svc-card h3{font-family:'Sora';font-size:1.12rem;margin:0 0 8px;color:#14131A}
.svc-card p{margin:0;color:#5B5966;line-height:1.6;font-size:.95rem}
.svc-aud{display:grid;grid-template-columns:repeat(2,1fr);gap:14px;margin:20px 0}
.svc-aud a{display:block;background:#fff;border:1px solid #E9E8EF;border-radius:14px;
  padding:18px 20px;text-decoration:none;transition:.15s}
.svc-aud a:hover{border-color:var(--accent);transform:translateY(-2px)}
.svc-aud b{display:block;color:#14131A;font-family:'Sora';margin-bottom:4px}
.svc-aud span{color:#5B5966;font-size:.9rem}
.svc-steps{counter-reset:s;list-style:none;padding:0;margin:22px 0;display:grid;gap:14px}
.svc-steps li{position:relative;padding-left:52px;color:#3A3846;line-height:1.6}
.svc-steps li:before{counter-increment:s;content:counter(s);position:absolute;left:0;top:-2px;
  width:36px;height:36px;border-radius:10px;background:var(--accent);color:#fff;
  display:flex;align-items:center;justify-content:center;font-family:'Sora';font-weight:700}
.svc-list{list-style:none;padding:0;margin:16px 0;display:grid;gap:10px}
.svc-list li{display:flex;gap:10px;align-items:flex-start;color:#3A3846;line-height:1.55}
.svc-list svg{color:var(--accent);flex-shrink:0;margin-top:3px}
.svc-cta{background:linear-gradient(135deg,#14131A,#2A2833);color:#fff;border-radius:20px;
  padding:36px 32px;margin:36px 0;text-align:center}
.svc-cta h3{font-family:'Sora';font-size:1.5rem;margin:0 0 8px;color:#fff}
.svc-cta p{color:#C9C7D2;margin:0 0 18px}
.svc-cta .btn{margin:0 auto}
.svc-cta-fine{font-size:.85rem;color:#9A97A6;margin-top:14px}
.svc-cta-fine a{color:#fff;text-decoration:underline}
.svc-stakes{background:#FEF6F4;border:1px solid #F6D9D1;border-left:4px solid #E0533D;
  border-radius:16px;padding:8px 24px 22px;margin:26px 0}
.svc-stakes h2{color:#B23A28}
.svc-stakes .svc-list svg{color:#E0533D}
@media(max-width:760px){.svc-hero-cards,.svc-aud{grid-template-columns:1fr}}
</style>
"""


def services_page():
    """Hub page - independent AI development agency (custom AI tools, integrations,
    AI apps/sites, AI content). wptaskify is our own product; here we BUILD custom
    AI solutions for clients."""
    schema = ('{"@context":"https://schema.org","@type":"ProfessionalService",'
              '"name":"wptaskify - AI Development Services",'
              '"serviceType":"Custom AI development, AI integrations, AI apps and AI content",'
              '"provider":{"@type":"Organization","name":"wptaskify","url":"https://wptaskify.com"},'
              '"areaServed":"Worldwide",'
              '"description":"We build custom AI solutions: AI tools and plugins for WordPress, AI integrations for any site, AI-powered web apps, and AI content at scale. Tell us your goal and we build it."}')
    check = _CHECK
    body = f"""
<p>AI is quietly redrawing every market right now - and the businesses that move
first are pulling ahead while everyone else "plans to get to it." If you have an idea
for an AI tool, integration, or app but no team to build it, that idea is worth
nothing until it ships. We're an AI development studio that ships. Tell us what you
want to achieve, and we build a custom AI solution around <strong>your</strong> goal:
a WordPress AI plugin, an AI feature inside your site, a full AI-powered web app, or
done-for-you AI content. You own the result.</p>

<p>We build with the leading AI models - Claude, ChatGPT (OpenAI), and Gemini - and
choose the right one for your use case. We built and run our own AI platform, so we
know how to ship AI that's reliable, safe, and genuinely useful - not a demo that
breaks in production.</p>

<h2>What we build</h2>
<div class=svc-hero-cards>
  <div class=svc-card><h3>Custom AI tools &amp; plugins</h3><p>A WordPress plugin or tool that does exactly what you need - an AI writer, chatbot, product-description generator, support assistant, data workflow, or any custom automation.</p></div>
  <div class=svc-card><h3>AI integrations</h3><p>Add AI to your existing site or software - connect ChatGPT, Claude, or Gemini to your content, data, or customer workflows, with the right guardrails.</p></div>
  <div class=svc-card><h3>AI apps &amp; websites</h3><p>A complete AI-powered web app or website built from scratch - the idea in your head, shipped as a real, working product.</p></div>
  <div class=svc-card><h3>AI content &amp; SEO</h3><p>Done-for-you AI content and SEO for your site - articles, product copy, on-page optimization and schema, produced at scale with a human check.</p></div>
</div>

<h2>Explore each service</h2>
<div class=svc-aud>
  <a href="/services/custom-ai-tools"><b>Custom AI tools &amp; plugins</b><span>WordPress plugins and AI automations built for you.</span></a>
  <a href="/services/wordpress-ai-setup"><b>AI integrations</b><span>Connect AI to your site, data and workflows.</span></a>
  <a href="/services/ai-content-writing"><b>AI apps &amp; content</b><span>Full AI apps and done-for-you AI content.</span></a>
  <a href="/services/ai-seo-optimization"><b>AI SEO</b><span>Rank and get cited by AI search engines.</span></a>
</div>

<h2>Why work with us</h2>
<ul class=svc-list>
  <li>{check}<span><strong>We ship real products, not demos.</strong> We run our own AI platform ({TOTAL_TOOLS}+ live tools), so we build AI that holds up in production.</span></li>
  <li>{check}<span><strong>You own everything.</strong> The code, the tool, the content - it's yours. We agree scope and ownership up front.</span></li>
  <li>{check}<span><strong>Any AI, the right AI.</strong> Claude, ChatGPT, Gemini or open models - we pick what fits your use case and budget, not what locks you in.</span></li>
  <li>{check}<span><strong>Clear scope, fixed quote.</strong> No vague hourly surprises - we quote the project so you know exactly what you're getting.</span></li>
  <li>{check}<span><strong>Built safely.</strong> Backups, testing, and your sign-off before anything ships to your live site.</span></li>
</ul>

<h2>How it works</h2>
<ol class=svc-steps>
  <li><strong>Tell us your goal</strong> - describe the AI tool, feature, or outcome you want. A quick form or call, no commitment.</li>
  <li><strong>We scope &amp; quote</strong> - we turn your idea into a concrete plan with a clear, no-obligation price and timeline.</li>
  <li><strong>We build it</strong> - we design, build and test your custom AI solution, keeping you updated.</li>
  <li><strong>Delivery &amp; support</strong> - you get the finished product (and its code), a walkthrough, and support after launch.</li>
</ol>

{_svc_cta("", "Tell us what to build")}

<h2>Frequently asked questions</h2>
<details class="faq-item"><summary>What kind of AI solutions do you build?</summary><p>Custom AI tools and WordPress plugins, AI integrations into existing sites and software, full AI-powered web apps, and done-for-you AI content and SEO. If it involves AI, tell us the goal and we'll tell you how we'd build it.</p></details>
<details class="faq-item"><summary>Do I have to use wptaskify's platform?</summary><p>No. wptaskify is our own product, but these are independent development services - we build whatever solution fits your goal, on the stack and AI models that suit you. You own the result.</p></details>
<details class="faq-item"><summary>Which AI models do you use?</summary><p>Whichever is best for your use case - Claude, ChatGPT (OpenAI), Gemini, or open-source models. We advise on cost, quality and privacy trade-offs.</p></details>
<details class="faq-item"><summary>How much does it cost?</summary><p>Every project is scoped to your needs, so we quote per project - a clear, fixed price with no hourly surprises. Tell us what you want and we'll send a quote, no obligation.</p></details>
<details class="faq-item"><summary>Do I own the code and the tool?</summary><p>Yes. Deliverables are yours - we agree scope and ownership before we start.</p></details>
<details class="faq-item"><summary>Can you work with my existing site or product?</summary><p>Yes - we add AI to what you already have, or build something new from scratch, whichever makes sense.</p></details>
{_SVC_CSS}
"""
    return _content_page(
        "AI Development Services - Custom AI Tools, Apps & Integrations",
        "We build custom AI solutions: AI tools & plugins for WordPress, AI integrations for any site, AI-powered web apps, and AI content at scale. Tell us your goal - get a free quote.",
        body, canonical="/services",
        keywords="custom ai development, ai development services, custom ai tool development, ai integration services, build ai app, ai wordpress plugin development, hire ai developer",
        schema_json=schema,
        hero_img=f"{SITE_BASE}/assets/hero-features.webp",
        hero_sub="Custom AI tools, integrations and apps - built around your goal. You own the result.",
        wide=True)


def _service_detail(slug, title, h1, hero_sub, meta_desc, keywords, intro,
                    deliverables, faqs, intro2="", who_for=None, use_cases=None,
                    why_us=None, outcomes_h="", outcomes=None,
                    stakes_h="", stakes=None):
    """Build one service detail page. Follows the Pain-Agitate-Solve pattern: the
    intro DRAWS the problem, the stakes block AGITATES the cost of waiting, then the
    rest SOLVES it. Optional intro2/who_for/use_cases/why_us/outcomes make it rich."""
    check = _CHECK
    dl = "".join(f'<li>{check}<span>{d}</span></li>' for d in deliverables)
    faq_html = "".join(
        f'<details class="faq-item"><summary>{q}</summary><p>{a}</p></details>'
        for q, a in faqs)
    faq_schema_items = ",".join(
        '{"@type":"Question","name":%s,"acceptedAnswer":{"@type":"Answer","text":%s}}'
        % (json.dumps(q), json.dumps(a)) for q, a in faqs)
    schema = ('{"@context":"https://schema.org","@graph":['
              '{"@type":"Service","serviceType":%s,'
              '"provider":{"@type":"Organization","name":"wptaskify","url":"https://wptaskify.com"},'
              '"areaServed":"Worldwide","description":%s},'
              '{"@type":"FAQPage","mainEntity":[%s]}]}'
              % (json.dumps(h1), json.dumps(meta_desc), faq_schema_items))

    intro2_html = f"<p>{intro2}</p>" if intro2 else ""

    who_html = ""
    if who_for:
        items = "".join(f'<li>{check}<span>{w}</span></li>' for w in who_for)
        who_html = f"<h2>Who this is for</h2><ul class=svc-list>{items}</ul>"

    cases_html = ""
    if use_cases:
        cards = "".join(
            f'<div class=svc-card><h3>{c["t"]}</h3><p>{c["d"]}</p></div>'
            for c in use_cases)
        cases_html = f"<h2>What you can ask us to do</h2><div class=svc-hero-cards>{cards}</div>"

    why_html = ""
    if why_us:
        items = "".join(f'<li>{check}<span>{w}</span></li>' for w in why_us)
        why_html = f"<h2>Why choose wptaskify</h2><ul class=svc-list>{items}</ul>"

    outcomes_html = ""
    if outcomes:
        items = "".join(f'<li>{check}<span>{o}</span></li>' for o in outcomes)
        outcomes_html = f"<h2>{outcomes_h or 'What you get'}</h2><ul class=svc-list>{items}</ul>"

    stakes_html = ""
    if stakes:
        stakes_html = _svc_stakes(stakes_h or "What waiting is costing you", stakes)

    body = f"""
<p>{intro}</p>
{intro2_html}
{stakes_html}
<h2>What's included</h2>
<ul class=svc-list>{dl}</ul>
{cases_html}
{who_html}
{outcomes_html}
<h2>How it works</h2>
<ol class=svc-steps>
  <li><strong>Share your goals</strong> - a short form about your site and what you need. No commitment.</li>
  <li><strong>We scope &amp; quote</strong> - we review your site, agree the plan, and send a clear, no-obligation price and timeline.</li>
  <li><strong>We deliver, you approve</strong> - we do the work in your dashboard's approval queue. Nothing goes live until you say go, and every file change is backed up first.</li>
  <li><strong>Handover &amp; support</strong> - you keep full control of your site and AI, with a walkthrough and support after delivery.</li>
</ol>
{why_html}
{_svc_cta(slug)}
<h2>Frequently asked questions</h2>
{faq_html}
<p style="margin-top:22px;color:#8A8792">Explore all our <a href="/services">AI development services</a>, or <a href="/contact">get in touch</a>.</p>
{_SVC_CSS}
"""
    return _content_page(h1, meta_desc, body, canonical="/services/" + slug,
                         keywords=keywords, schema_json=schema,
                         hero_img=f"{SITE_BASE}/assets/hero-features.webp",
                         hero_sub=hero_sub, wide=True)


def service_custom_tools_page():
    return _service_detail(
        "custom-ai-tools",
        "Custom AI Tool & WordPress Plugin Development",
        "Custom AI Tool & WordPress Plugin Development",
        "Have an idea for an AI tool? We design and build it for you.",
        "Custom AI development: we build AI-powered tools, WordPress plugins and automations around your exact idea. You own the code. Get a free quote.",
        "custom ai tool development, custom wordpress ai plugin development, build ai wordpress plugin, ai automation development, hire ai developer, ai plugin developer",
        "You have the AI idea - the tool, the plugin, the automation that would save hours or win customers. But it's still just an idea, because you don't have a team to build it. Meanwhile, someone in your space is shipping theirs. We turn your idea into a real, working AI product - designed, built, tested, and yours to keep.",
        ["A custom AI tool or WordPress plugin built to your spec",
         "AI automations wired into your content, data or media workflows",
         "The right AI model chosen for you - Claude, ChatGPT or Gemini",
         "Integrations with your existing tools, plugins and APIs",
         "Tested, documented, and handed over as yours - with support"],
        [("What kinds of AI tools do you build?", "Chatbots and support assistants, AI content and product-description generators, custom SEO automations, data and research tools, image/media pipelines, internal workflow tools - if AI can do it, we can build it around your goal."),
         ("Is this only for WordPress?", "No. WordPress plugins are a specialty, but we also build standalone AI tools, scripts and services for any stack."),
         ("Will it work with my theme and plugins?", "Yes - we build to fit your existing setup and test for compatibility before shipping."),
         ("Do I own the code?", "Yes. Deliverables are 100% yours - we agree scope and ownership before we start."),
         ("How much does it cost?", "We quote per project after a quick scoping call, so you get a clear fixed price - no hourly surprises.")],
        intro2="We build production-grade AI - not demos that break under real use. Because we build and run our own AI platform, we know how to handle prompts, cost, rate limits, safety and edge cases so your tool actually works day after day.",
        use_cases=[
            {"t": "AI chatbot / assistant", "d": "A branded assistant trained on your content that answers visitors or supports customers 24/7."},
            {"t": "Content generator", "d": "One-click AI drafts, product descriptions, or bulk content - in your voice, on your site."},
            {"t": "Custom automation", "d": "Automate a repetitive task - tagging, summarizing, moderating, enriching data - with AI in the loop."},
            {"t": "Integration", "d": "Connect an AI model to your CRM, store, docs or API so it works with the data you already have."},
        ],
        who_for=[
            "Founders and businesses with an AI idea but no dev team",
            "Agencies who want to offer (or white-label) custom AI builds",
            "Site owners who need a specific tool that no plugin provides",
        ],
        why_us=[
            "We ship real, reliable AI - proven by our own live platform",
            "You own the code and can take it anywhere",
            "Fixed, transparent project quotes",
            "Safe delivery: testing, backups and your sign-off",
        ],
        stakes_h="The cost of leaving it as \"just an idea\"",
        stakes=[
            "Every month it isn't built is a month a competitor can build it first",
            "Hours your team burns on tasks AI could do in seconds - week after week",
            "A cheap freelancer's \"AI demo\" that looks fine but breaks the moment real users hit it",
            "Trying to learn it yourself and losing weeks you could have spent on your business",
        ])


def service_setup_page():
    return _service_detail(
        "wordpress-ai-setup",
        "AI Integration Services",
        "AI Integration Services - Add AI to Your Site or Software",
        "We connect AI to your existing site, data and workflows.",
        "AI integration services: we add AI to your existing website or software - connect Claude, ChatGPT or Gemini to your content, data and workflows, safely. Get a free quote.",
        "ai integration services, add ai to my website, integrate chatgpt into website, ai api integration, connect ai to wordpress, ai integration developer",
        "Your customers already expect AI - instant answers, smart search, help at 2am. Right now your site makes them wait, dig, or leave. Every visitor who doesn't get a fast answer is a sale that quietly walks to a competitor whose site already \"gets it.\" We add AI to the site or product you already have, so it works with your real data - accurate, safe, and cost-controlled.",
        ["Connect Claude, ChatGPT or Gemini to your existing site/app",
         "Wire AI into your real data - content, catalog, docs, CRM or API",
         "Guardrails: prompt design, limits, moderation and fallbacks",
         "Cost controls so your AI bill stays predictable",
         "Testing and monitoring so it keeps working in production"],
        [("Which AI can you integrate?", "Claude, ChatGPT (OpenAI), Gemini, or open-source models - we recommend the best fit for your use case, quality needs and budget."),
         ("Can you integrate AI into a non-WordPress site?", "Yes - any website, web app or software with an API. WordPress is a specialty, not a limit."),
         ("How do you control AI costs?", "We add caching, rate limits and model choices so usage stays efficient and your monthly bill is predictable."),
         ("Is my data safe?", "Yes - we design the integration so only the data you intend is sent, with clear privacy handling. We advise on models with stronger privacy where needed."),
         ("How much does it cost?", "Scoped per project with a clear fixed quote after a short call.")],
        intro2="An AI integration is more than an API call. We design the prompts, choose the model, add safety and cost guardrails, connect it to your actual data, and test it against real inputs - so what you launch is dependable, not a fragile demo.",
        use_cases=[
            {"t": "AI on your content", "d": "Let visitors ask questions and get answers drawn from your own articles, docs or products."},
            {"t": "AI in your product", "d": "Add an AI feature - summarize, generate, recommend - inside your existing app or dashboard."},
            {"t": "Workflow AI", "d": "Insert AI into a business process: support triage, lead qualification, data enrichment."},
            {"t": "Search & Q&A", "d": "AI-powered search or a Q&A assistant grounded in your knowledge base."},
        ],
        who_for=[
            "Businesses that want AI features without rebuilding their site",
            "SaaS/product teams adding an AI capability to their app",
            "WordPress owners who want AI connected to their real content",
        ],
        why_us=[
            "We integrate the right model, not just the popular one",
            "Guardrails and cost controls built in from day one",
            "You keep ownership and control of everything",
            "Tested against real data before it goes live",
        ],
        stakes_h="What a site without AI is quietly costing you",
        stakes=[
            "Visitors who don't find a fast answer bounce - and buy elsewhere",
            "Your support team answers the same questions over and over, by hand",
            "Competitors with AI-powered sites feel modern; yours feels dated",
            "A botched DIY integration that leaks data or runs up a surprise AI bill",
        ])


def service_content_page():
    return _service_detail(
        "ai-content-writing",
        "AI Apps & Done-For-You AI Content",
        "AI Apps & Done-For-You AI Content",
        "Full AI web apps built from scratch, plus AI content at scale.",
        "We build AI-powered web apps from scratch and produce done-for-you AI content and SEO articles at scale, with a human check. Get a free quote.",
        "build ai app, ai web app development, ai app developer, done for you ai content, ai content writing service, ai seo articles",
        "That AI app idea has been sitting in your notes for months. That content calendar is three weeks behind - again. Ideas don't make money; shipped products and published pages do. While you wait for the \"right time,\" the window is closing and the competition is publishing. We ship the finished result for you: a complete AI web app built from scratch, or a steady stream of quality AI content - done, live, and yours.",
        ["AI-powered web apps and websites, built from scratch",
         "SEO articles written, optimized and published to your site",
         "Product copy and descriptions at scale for stores",
         "On-page SEO, schema and internal links included",
         "A human review pass so quality and accuracy stay high"],
        [("Can you build a full AI app, not just a plugin?", "Yes - we build complete AI-powered web apps and websites from scratch, front to back, and hand them over as yours."),
         ("Is the content unique?", "Yes - everything is generated for your site and topic, then reviewed by a human. We never republish canned articles."),
         ("How much content can you produce?", "From a few pieces a month to large batches - we scope to your goals and budget."),
         ("Will Google penalize AI content?", "Google rewards helpful, accurate content regardless of how it's produced. We optimize for exactly that and keep a person in the loop."),
         ("Do I own the app and content?", "Yes - the app, code and content are all yours.")],
        intro2="For apps, you get a real, working product - designed, built and tested - not a prototype. For content, you get articles and copy that are planned around genuine search intent, optimized on-page, and checked by a human, so they're something you're proud to publish.",
        use_cases=[
            {"t": "AI SaaS / tool", "d": "A standalone AI product - the idea in your head, shipped as a real app people can use."},
            {"t": "AI website", "d": "A modern site with AI features baked in - chat, personalization, generation."},
            {"t": "Content engine", "d": "A steady pipeline of SEO articles published straight to your WordPress."},
            {"t": "Store copy", "d": "AI product descriptions and category pages at scale for ecommerce."},
        ],
        who_for=[
            "Founders who want an AI app built without hiring a team",
            "Bloggers and content sites that need articles at scale",
            "Ecommerce stores that need product copy and SEO at volume",
        ],
        why_us=[
            "We ship finished products, not prototypes",
            "Human-checked content - quality over quantity",
            "SEO and AI-search (GEO/AEO) baked in",
            "You own the app, the code and the content",
        ],
        stakes_h="What staying stuck at \"idea\" costs you",
        stakes=[
            "The market moves on while your app sits unbuilt in a doc",
            "An empty or stale blog that Google - and buyers - quietly ignore",
            "Competitors publishing weekly while you publish once a quarter",
            "Months lost trying to do it all yourself instead of running your business",
        ])


def service_seo_page():
    return _service_detail(
        "ai-seo-optimization",
        "AI SEO Services",
        "AI SEO Services - Rank & Get Cited by AI Search",
        "We optimize your site to rank on Google and get cited by AI engines.",
        "AI SEO services: we audit and fix on-page SEO, meta, schema and internal links, and optimize for AI search (GEO/AEO) so ChatGPT, Perplexity and AI Overviews cite you. Get a free quote.",
        "ai seo services, ai seo agency, geo optimization service, aeo optimization, get cited by chatgpt, ai search optimization, wordpress seo service",
        "Your customers are asking ChatGPT, Perplexity and Google AI Overviews the exact questions your business answers - and getting someone else's brand as the reply. AI now answers directly, so fewer people ever click a blue link. If your content isn't structured to be cited, you're becoming invisible in the one place buyers are looking - and most site owners have no idea it's happening. We make your site rank on Google AND get cited inside AI answers, before your competitors lock in that spot.",
        ["Full on-page SEO audit with prioritized, high-impact fixes",
         "Meta titles/descriptions, headings and internal linking",
         "Structured data (schema) for rich results",
         "GEO/AEO: quotable answers, entities and citations for AI engines",
         "Broken-link, duplicate and thin-content cleanup"],
        [("What is GEO/AEO?", "GEO (Generative Engine Optimization) and AEO (Answer Engine Optimization) mean structuring your content so AI engines like ChatGPT, Perplexity, Gemini and Google AI Overviews can understand and cite it. It's the new frontier of SEO, and most sites aren't doing it yet."),
         ("Will this work with my current SEO plugin?", "Yes - we work alongside or replace your existing setup and make sure there are no duplicate tags."),
         ("Do you guarantee rankings?", "No honest agency can guarantee rankings. We fix the technical and on-page factors within your control to give you the best possible shot."),
         ("Can you do this at scale?", "Yes - we apply fixes across hundreds of pages efficiently, with your approval."),
         ("How much does it cost?", "Scoped per project or as an ongoing retainer, with a clear quote after a short audit.")],
        intro2="Most SEO agencies still only optimize for Google's classic results. We do that too - but we also make your content citation-ready for AI answer engines, which are increasingly where people get answers. That means clear, quotable statements, proper schema, strong entities and E-E-A-T signals AI models look for.",
        use_cases=[
            {"t": "SEO audit & fixes", "d": "Find and fix what's holding your rankings back - technical, on-page and content issues."},
            {"t": "AI-search readiness", "d": "Make your pages quotable and citable by ChatGPT, Perplexity and AI Overviews."},
            {"t": "Content optimization", "d": "Rework existing articles to rank and answer the questions people actually ask."},
            {"t": "Schema & structure", "d": "Add the structured data that unlocks rich results and AI citations."},
        ],
        who_for=[
            "Sites that rank okay but want more search traffic",
            "Brands that want to show up inside AI answers, not just Google",
            "Stores and blogs with lots of pages needing SEO at scale",
        ],
        why_us=[
            "We optimize for Google AND AI search - most don't",
            "Real fixes applied at scale, not just a report",
            "Backed by our own AI SEO tooling",
            "Honest about what SEO can and can't promise",
        ],
        stakes_h="What poor SEO is costing you right now",
        stakes=[
            "AI answers cite a competitor instead of you - and you never even see it",
            "Rankings slipping while sites that optimized for AI search climb past you",
            "Traffic (and leads) leaking away as fewer people click past AI answers",
            "Months of great content that Google barely shows because it isn't optimized",
        ])


_FORUM_CSS = """
<style>
.frm-wrap{background:#FFFFFF;color:#14131A;min-height:60vh;padding:0 20px 60px}
.frm-inner{max-width:860px;margin:0 auto;padding-top:30px}
.frm-head{display:flex;justify-content:space-between;align-items:flex-end;flex-wrap:wrap;gap:14px;margin-bottom:8px}
.frm-h1{font-family:'Sora';font-size:clamp(1.6rem,3.5vw,2.3rem);color:#14131A;margin:0;letter-spacing:-.02em}
.frm-h2{font-family:'Sora';font-size:1.2rem;color:#14131A;margin:22px 0 12px}
.frm-sub{color:#5B5966;margin:6px 0 0}
.frm-crumb{display:inline-block;color:#EA580C;font-weight:600;font-size:.9rem;margin-bottom:16px}
.frm-cat{display:block;padding:18px 20px;border:1px solid #EAE8F0;border-radius:14px;margin-bottom:12px;
  background:#FBFAFD;transition:border-color .15s,transform .15s}
.frm-cat:hover{border-color:#F97316;transform:translateY(-2px)}
.frm-cat h3{font-family:'Sora';font-size:1.1rem;color:#14131A;margin:0 0 4px}
.frm-cat p{color:#5B5966;font-size:.92rem;margin:0}
.frm-cat .meta{color:#8A8792;font-size:.82rem;margin-top:8px}
.frm-thread{display:flex;justify-content:space-between;gap:14px;padding:15px 18px;border:1px solid #EAE8F0;
  border-radius:12px;margin-bottom:10px;background:#fff;transition:border-color .15s}
.frm-thread:hover{border-color:#F97316}
.frm-thread .t-title{font-weight:600;color:#14131A;font-size:1rem;line-height:1.35}
.frm-thread .t-meta{color:#8A8792;font-size:.82rem;margin-top:4px}
.frm-thread .t-count{color:#5B5966;font-size:.85rem;white-space:nowrap;text-align:right}
.frm-badge{display:inline-block;font-size:.68rem;font-weight:700;padding:2px 7px;border-radius:999px;
  vertical-align:middle;margin-right:6px}
.frm-badge.pin{background:rgba(249,115,22,.12);color:#EA580C}
.frm-badge.lock{background:#EEE;color:#666}
.frm-post{padding:18px 20px;border:1px solid #EAE8F0;border-radius:14px;margin-bottom:14px;background:#fff}
.frm-post .p-head{display:flex;justify-content:space-between;color:#8A8792;font-size:.83rem;margin-bottom:8px}
.frm-post .p-author{font-weight:700;color:#14131A}
.frm-post .p-body{color:#25232E;line-height:1.75;white-space:pre-wrap;word-wrap:break-word}
.frm-op{border-color:#F5D9C4;background:#FFFBF7}
.frm-form label{display:block;font-family:'Sora';font-weight:600;font-size:.85rem;color:#14131A;margin:14px 0 6px}
.frm-form input,.frm-form textarea,.frm-form select{width:100%;padding:11px 13px;border:1px solid #DAD9E4;
  border-radius:10px;background:#fff;color:#14131A;font-size:.98rem;font-family:inherit}
.frm-form textarea{min-height:150px;resize:vertical}
.frm-form input:focus,.frm-form textarea:focus,.frm-form select:focus{outline:none;border-color:#F97316}
.frm-note{background:#FFF4EC;border:1px solid #F5D9C4;border-radius:12px;padding:14px 16px;color:#5B5966;
  font-size:.92rem;margin:14px 0}
.frm-note a{color:#EA580C;font-weight:600}
.frm-hint{color:#8A8792;font-size:.82rem;margin-top:6px}
.frm-empty{color:#8A8792;text-align:center;padding:40px 0}
.frm-actions{margin:20px 0 0}
</style>"""


def _forum_body(x):
    """Escape user content and keep line breaks."""
    return _e_html(x).replace("\n", "<br>")


def _forum_shell(title, description, inner, canonical, schema_json=""):
    return _head(title=f"{title} | {BRAND}", description=description, canonical=canonical,
                 schema_json=schema_json) + f"""
{_nav("both")}
<div class=frm-wrap><div class=frm-inner>{inner}</div></div>
{_blog_footer()}{_FORUM_CSS}
</body></html>"""


def community_index_page(categories, logged_in=False, verified=False):
    cats = ""
    for c in categories:
        last = f'Last activity {c["last_at"][:10]}' if c.get("last_at") else "No threads yet"
        cats += (f'<a class=frm-cat href="/community/{_e_html(c["slug"])}">'
                 f'<h3>{_e_html(c["name"])}</h3><p>{_e_html(c["description"])}</p>'
                 f'<div class=meta>{c["threads"]} threads &middot; {_e_html(last)}</div></a>')
    if not cats:
        cats = '<div class=frm-empty>Categories are being set up. Check back soon.</div>'
    # Tell visitors exactly how to take part.
    if not logged_in:
        note = ('<div class=frm-note>Anyone can read the community. To post a question or reply, '
                '<a href="/?signup">create a free account</a> or '
                '<a href="/login?next=%2Fcommunity">log in</a>. It takes about a minute.</div>')
    elif not verified:
        note = ('<div class=frm-note>You are logged in. Please <a href="/verify-sent">verify your '
                'email</a> to start posting in the community.</div>')
    else:
        note = ('<div class=frm-note>You are all set. Open a category below and click '
                '<strong>Start a thread</strong> to post.</div>')
    inner = (
        '<div class=frm-head><div>'
        '<h1 class=frm-h1>Community</h1>'
        '<p class=frm-sub>Ask questions, share what you built, and get help connecting WordPress to AI.</p>'
        '</div></div>'
        f'{note}'
        f'<h2 class=frm-h2>Categories</h2>'
        f'{cats}')
    return _forum_shell("Community", "The wptaskify community: ask questions and share tips on "
                        "connecting WordPress to Claude and ChatGPT.", inner, "/community")


def community_category_page(category, threads, can_post):
    rows = ""
    for t in threads:
        badges = ('<span class="frm-badge pin">Pinned</span>' if t["pinned"] else '') + \
                 ('<span class="frm-badge lock">Locked</span>' if t["locked"] else '')
        rows += (f'<a class=frm-thread href="/community/t/{t["id"]}-{_e_html(t["slug"])}">'
                 f'<div><div class=t-title>{badges}{_e_html(t["title"])}</div>'
                 f'<div class=t-meta>by {_e_html(t["author"])} &middot; {t["last_at"][:10]}</div></div>'
                 f'<div class=t-count>{t["reply_count"]} replies</div></a>')
    if not rows:
        rows = '<div class=frm-empty>No threads yet. Be the first to start one.</div>'
    new_btn = (f'<a class="btn btn-primary" href="/community/{_e_html(category["slug"])}/new">'
               f'Start a thread</a>' if can_post else
               '<a class="btn btn-primary" href="/login?next=%2Fcommunity">Log in to post</a>')
    inner = (
        f'<a class=frm-crumb href="/community">&larr; Community</a>'
        '<div class=frm-head>'
        f'<div><h1 class=frm-h1>{_e_html(category["name"])}</h1>'
        f'<p class=frm-sub>{_e_html(category["description"])}</p></div>'
        f'{new_btn}</div>'
        f'{rows}')
    return _forum_shell(category["name"], category["description"] or "wptaskify community category",
                        inner, f"/community/{category['slug']}")


def community_thread_page(thread, posts, can_post, csrf="", error=""):
    op = (f'<div class="frm-post frm-op"><div class=p-head>'
          f'<span class=p-author>{_e_html(thread["author"])}</span>'
          f'<span>{thread["created_at"][:16]}</span></div>'
          f'<div class=p-body>{_forum_body(thread["body"])}</div></div>')
    replies = ""
    for p in posts:
        replies += (f'<div class=frm-post><div class=p-head>'
                    f'<span class=p-author>{_e_html(p["author"])}</span>'
                    f'<span>{p["created_at"][:16]}</span></div>'
                    f'<div class=p-body>{_forum_body(p["body"])}</div></div>')
    err = f'<div class="frm-note" style="border-color:#f2b8b8;background:#fdecec">{_e_html(error)}</div>' if error else ''
    if thread["locked"]:
        reply_box = '<div class=frm-note>This thread is locked. New replies are closed.</div>'
    elif can_post:
        reply_box = (
            f'<form class=frm-form method=post action="/community/t/{thread["id"]}/reply">'
            f'<input type=hidden name=csrf value="{_e_html(csrf)}">'
            f'<label for=body>Add a reply</label>'
            f'<textarea id=body name=body required placeholder="Write your reply..."></textarea>'
            f'<div class=frm-actions><button class="btn btn-primary" type=submit>Post reply</button></div>'
            f'</form>')
    else:
        reply_box = ('<div class=frm-note>You need a verified account to reply. '
                     '<a href="/login?next=%2Fcommunity">Log in</a> or '
                     '<a href="/?signup">create a free account</a>.</div>')
    badges = ('<span class="frm-badge pin">Pinned</span>' if thread["pinned"] else '') + \
             ('<span class="frm-badge lock">Locked</span>' if thread["locked"] else '')
    # QAPage schema helps AEO for question-style threads.
    schema = ('{"@context":"https://schema.org","@type":"DiscussionForumPosting",'
              f'"headline":{_json_str(thread["title"])},'
              f'"datePublished":"{thread["created_at"][:10]}",'
              f'"author":{{"@type":"Person","name":{_json_str(thread["author"])}}},'
              f'"interactionStatistic":{{"@type":"InteractionCounter",'
              f'"interactionType":"https://schema.org/CommentAction","userInteractionCount":{thread["reply_count"]}}}}}')
    inner = (
        f'<a class=frm-crumb href="/community/{_e_html(thread["cat_slug"])}">&larr; {_e_html(thread["cat_name"])}</a>'
        f'<h1 class=frm-h1>{badges}{_e_html(thread["title"])}</h1>'
        f'<p class=frm-sub>{thread["reply_count"]} replies</p>'
        f'<div style="margin-top:18px">{op}{replies}</div>'
        f'{err}{reply_box}')
    return _forum_shell(thread["title"],
                        f'{thread["title"]} - wptaskify community discussion',
                        inner, f"/community/t/{thread['id']}-{thread['slug']}", schema_json=schema)


def community_new_thread_page(category, csrf="", error=""):
    err = f'<div class="frm-note" style="border-color:#f2b8b8;background:#fdecec">{_e_html(error)}</div>' if error else ''
    inner = (
        f'<a class=frm-crumb href="/community/{_e_html(category["slug"])}">&larr; {_e_html(category["name"])}</a>'
        f'<h1 class=frm-h1>Start a thread</h1>'
        f'<p class=frm-sub>Posting in {_e_html(category["name"])}</p>'
        f'{err}'
        f'<form class=frm-form method=post action="/community/{_e_html(category["slug"])}/new" style="margin-top:16px">'
        f'<input type=hidden name=csrf value="{_e_html(csrf)}">'
        f'<label for=title>Title</label>'
        f'<input id=title name=title maxlength=160 required placeholder="A clear, specific title">'
        f'<label for=body>Details</label>'
        f'<textarea id=body name=body required placeholder="Describe your question or share your tip. '
        f'Be specific so others can help."></textarea>'
        f'<div class=frm-hint>Tip: to add a screenshot, upload it somewhere (e.g. an image host) and '
        f'paste the link. Line breaks are kept.</div>'
        f'<div class=frm-actions><button class="btn btn-primary btn-lg" type=submit>Post thread</button></div>'
        f'</form>')
    return _forum_shell(f"New thread in {category['name']}",
                        "Start a new discussion in the wptaskify community.",
                        inner, f"/community/{category['slug']}/new")


def _json_str(s):
    import json as _j
    return _j.dumps(str(s or ""))


def blog_index_page(db_posts=None):
    import blog_posts
    # Merge admin DB posts (newest first) with the built-in posts.
    merged = []
    for p in (db_posts or []):
        merged.append({"slug": p["slug"], "title": p["title"], "description": p["description"],
                       "hero": p["hero"], "read": p.get("read_time", "Guide")})
    for p in blog_posts.all_posts():
        merged.append({"slug": p["slug"], "title": p["title"], "description": p["description"],
                       "hero": p["hero"], "read": p.get("read", "Guide")})
    cards = ""
    for p in merged:
        cards += (
            f'<a class=blog-card href="/blog/{_e_html(p["slug"])}">'
            f'<div class=blog-card-img><img src="{SITE_BASE}/assets/{_e_html(p["hero"])}" '
            f'alt="{_e_html(p["title"])}" loading="lazy"></div>'
            f'<div class=blog-card-body>'
            f'<h3>{_e_html(p["title"])}</h3>'
            f'<p>{_e_html(p["description"])}</p>'
            f'<span class=blog-meta>{_e_html(p.get("read","Guide"))} &middot; Read guide &rarr;</span>'
            f'</div></a>')
    body = (
        "<p>Practical guides on connecting WordPress to Claude and ChatGPT, writing AI content "
        "that ranks, and getting cited by AI answer engines (GEO/AEO).</p>"
        f'<div class=blog-grid>{cards}</div>'
        "<style>"
        ".blog-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));"
        "gap:22px;margin:26px 0 8px}"
        ".blog-card{display:flex;flex-direction:column;border:1px solid var(--border);"
        "border-radius:16px;overflow:hidden;background:var(--bg2);transition:transform .15s,"
        "border-color .15s}"
        ".blog-card:hover{transform:translateY(-3px);border-color:var(--accent)}"
        ".blog-card-img{aspect-ratio:16/9;overflow:hidden}"
        ".blog-card-img img{width:100%;height:100%;object-fit:cover}"
        ".blog-card-body{padding:18px 18px 20px}"
        ".blog-card-body h3{font-size:1.12rem;line-height:1.3;margin:0 0 8px;color:var(--fg)}"
        ".blog-card-body p{color:var(--muted);font-size:.92rem;margin:0 0 12px}"
        ".blog-meta{color:var(--accent-hi);font-size:.82rem;font-weight:600}"
        "</style>")
    return _content_page("Blog", "wptaskify blog - guides on AI, WordPress, SEO, AEO and GEO.", body,
                         canonical="/blog", wide=True,
                         hero_img=f"{SITE_BASE}/assets/hero-blog.webp",
                         hero_sub="Guides on AI, WordPress, SEO, AEO and GEO.",
                         keywords="wordpress ai blog, ai seo guide, geo aeo wordpress")


def _blog_footer():
    """Standard site footer (dark) for blog article pages."""
    return (
        '<footer class=footer><div class=wrap>'
        '<div class=foot-top>'
        f'<div>{_logo()}</div>'
        '<div class=foot-links>'
        '<div><h4>Product</h4><a href="/features">Features</a><a href="/tools">Tools</a><a href="/services">Services</a><a href="/how-it-works">How it works</a><a href="/pricing">Pricing</a><a href="/faq">FAQ</a></div>'
        '<div><h4>Company</h4><a href="/about">About</a><a href="/contact">Contact</a><a href="/blog">Blog</a><a href="/community">Community</a><a href="/security">Security</a></div>'
        '<div><h4>Legal</h4><a href="/terms">Terms</a><a href="/privacy">Privacy</a><a href="/refund">Refund Policy</a><a href="/shipping">Delivery</a></div>'
        '</div></div>'
        f'{_social_bar()}'
        '<div class=foot-bottom>&copy; 2026 wptaskify. Connect WordPress to AI.</div>'
        '</div></footer>')


def _blog_figure(img):
    """Render an in-article image/screenshot with a caption. img = {src, alt, caption}."""
    if not img:
        return ""
    src = img["src"] if str(img["src"]).startswith("http") else f"{SITE_BASE}/assets/{img['src']}"
    cap = f'<figcaption>{_e_html(img.get("caption",""))}</figcaption>' if img.get("caption") else ""
    return (f'<figure class=blog-fig><img src="{_e_html(src)}" alt="{_e_html(img.get("alt",""))}" '
            f'loading="lazy">{cap}</figure>')


def blog_post_page(post):
    """Render one blog article on a WHITE reading page (matches the other content pages),
    with AEO structure + Article & FAQ JSON-LD schema. Sections may be 2-tuples
    (heading, html) or 3-tuples (heading, html, image_dict) to embed a screenshot."""
    import json as _json
    parts = [f'<p class=blog-answer>{post["answer"]}</p>']
    for sec in post["sections"]:
        heading, html_body = sec[0], sec[1]
        img = sec[2] if len(sec) > 2 else None
        parts.append(f'<h2>{_e_html(heading)}</h2>{html_body}')
        if img:
            parts.append(_blog_figure(img))
    if post.get("faq"):
        parts.append("<h2>Frequently asked questions</h2>")
        for q, a in post["faq"]:
            parts.append(f'<h3>{_e_html(q)}</h3><p>{_e_html(a)}</p>')
    # Internal linking: auto "Related guides" block linking to the other articles.
    try:
        import blog_posts as _bp
        related = [x for x in _bp.all_posts() if x["slug"] != post["slug"]][:3]
    except Exception:
        related = []
    if related:
        links = "".join(
            f'<a class=blog-rel href="/blog/{_e_html(r["slug"])}">'
            f'<span class=blog-rel-t>{_e_html(r["title"])}</span>'
            f'<span class=blog-rel-a>Read guide &rarr;</span></a>'
            for r in related)
        parts.append(f'<h2>Related guides</h2><div class=blog-rel-grid>{links}</div>')
    parts.append(
        f'<div class=blog-cta><h3>{_e_html(post.get("cta","Try wptaskify free"))}</h3>'
        f'<p>Bring your own Claude or ChatGPT. 100+ WordPress tools. Nothing goes live without '
        f'your approval.</p><a class="btn btn-primary btn-lg" href="/?signup">Get started free</a></div>'
        '<p class=blog-back><a href="/blog">&larr; All guides</a></p>')
    body = "".join(parts)

    # JSON-LD (Article + FAQPage) for AEO.
    url = f"{SITE_BASE}/blog/{post['slug']}"
    schemas = [{
        "@context": "https://schema.org", "@type": "Article",
        "headline": post["title"], "description": post["description"],
        "image": f"{SITE_BASE}/assets/{post['hero']}",
        "datePublished": post.get("date", ""), "dateModified": post.get("date", ""),
        "author": {"@type": "Organization", "name": "wptaskify"},
        "publisher": {"@type": "Organization", "name": "wptaskify",
                      "logo": {"@type": "ImageObject", "url": f"{SITE_BASE}/assets/apple-touch-icon.png"}},
        "mainEntityOfPage": {"@type": "WebPage", "@id": url},
    }]
    if post.get("faq"):
        schemas.append({
            "@context": "https://schema.org", "@type": "FAQPage",
            "mainEntity": [{"@type": "Question", "name": q,
                            "acceptedAnswer": {"@type": "Answer", "text": a}}
                           for q, a in post["faq"]],
        })
    schema_json = _json.dumps(schemas)

    hero = f"{SITE_BASE}/assets/{post['hero']}"
    return _head(title=f"{post['title']} | {BRAND}", description=post["description"],
                 canonical=f"/blog/{post['slug']}", keywords=post.get("keywords", ""),
                 og_image=hero, schema_json=schema_json) + f"""
{_nav("both")}
<div class=blog-wrap>
  <div class=blog-inner>
    <a class=blog-crumb href="/blog">&larr; All guides</a>
    <h1 class=blog-h1>{_e_html(post['title'])}</h1>
    <div class=blog-byline><span>wptaskify</span> &middot; <span>{_e_html(post.get('read',''))}</span></div>
    <figure class=blog-hero><img src="{hero}" alt="{_e_html(post['title'])}"></figure>
    <article class=blog-article>{body}</article>
  </div>
</div>
{_blog_footer()}{_BLOG_ARTICLE_CSS}
</body></html>"""


_BLOG_ARTICLE_CSS = """<style>
.blog-wrap{background:#FFFFFF;color:#14131A;padding:0 20px 60px}
.blog-inner{max-width:760px;margin:0 auto;padding-top:34px}
.blog-crumb{display:inline-block;color:#EA580C;font-weight:600;font-size:.9rem;margin-bottom:18px}
.blog-h1{font-family:'Sora';font-size:clamp(1.8rem,4vw,2.6rem);line-height:1.2;letter-spacing:-.02em;
  color:#14131A;margin:0 0 12px}
.blog-byline{color:#8A8792;font-size:.9rem;margin-bottom:24px}
.blog-hero{margin:0 0 30px}
.blog-hero img{width:100%;border-radius:16px;border:1px solid #EAE8F0}
.blog-article{font-size:1.075rem;line-height:1.8}
.blog-article h2{font-family:'Sora';font-size:1.55rem;color:#14131A;margin:40px 0 14px;
  letter-spacing:-.01em;font-weight:700}
.blog-article h3{font-family:'Sora';font-size:1.18rem;color:#14131A;margin:26px 0 8px;font-weight:600}
.blog-article p,.blog-article li{color:#2A2833 !important}
.blog-article p{margin:0 0 18px}
.blog-article ul,.blog-article ol{margin:12px 0 20px;padding-left:24px}
.blog-article li{margin-bottom:9px}
.blog-article strong,.blog-article b{color:#14131A;font-weight:600}
.blog-article a{color:#EA580C;font-weight:600}
.blog-article code{background:#F3F1F7;padding:2px 6px;border-radius:5px;font-size:.9em;color:#B0430C}
.blog-article img{max-width:100%;height:auto;border-radius:12px;margin:16px 0}
.blog-answer{font-size:1.14rem;line-height:1.7;color:#14131A;background:#FFF4EC;
  border-left:4px solid #F97316;border-radius:0 12px 12px 0;padding:16px 20px;margin:0 0 30px}
.blog-fig{margin:24px 0}
.blog-fig img{width:100%;border-radius:14px;border:1px solid #EAE8F0;
  box-shadow:0 14px 40px -22px rgba(20,19,26,.35)}
.blog-fig figcaption{color:#8A8792;font-size:.85rem;text-align:center;margin-top:10px}
.blog-cta{margin:44px 0 12px;padding:30px;border-radius:18px;text-align:center;
  background:linear-gradient(135deg,#14131A,#26232f);color:#fff}
.blog-cta h3{font-family:'Sora';font-size:1.35rem;margin:0 0 8px;color:#fff}
.blog-cta p{color:#C9C7D2;margin:0 0 18px}
.blog-back{margin-top:26px}.blog-back a{color:#EA580C;font-weight:600}
.blog-rel-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:14px 0 8px}
.blog-rel{display:flex;flex-direction:column;gap:6px;padding:16px;border:1px solid #EAE8F0;
  border-radius:12px;background:#FBFAFD;transition:border-color .15s,transform .15s}
.blog-rel:hover{border-color:#F97316;transform:translateY(-2px)}
.blog-rel-t{font-family:'Sora';font-weight:600;color:#14131A;font-size:.98rem;line-height:1.35}
.blog-rel-a{color:#EA580C;font-size:.85rem;font-weight:600}
@media(max-width:640px){.blog-rel-grid{grid-template-columns:1fr}}
</style>"""


def blog_db_post_page(post):
    """Render an admin-created (DB) blog post. Body is raw HTML the admin wrote; we wrap
    it in the same white article layout as the built-in posts."""
    import json as _json
    hero = f"{SITE_BASE}/assets/{post['hero']}"
    url = f"{SITE_BASE}/blog/{post['slug']}"
    schema = _json.dumps([{
        "@context": "https://schema.org", "@type": "Article",
        "headline": post["title"], "description": post["description"], "image": hero,
        "datePublished": str(post.get("created_at", ""))[:10],
        "dateModified": str(post.get("updated_at", ""))[:10],
        "author": {"@type": "Organization", "name": "wptaskify"},
        "publisher": {"@type": "Organization", "name": "wptaskify",
                      "logo": {"@type": "ImageObject", "url": f"{SITE_BASE}/assets/apple-touch-icon.png"}},
        "mainEntityOfPage": {"@type": "WebPage", "@id": url},
    }])
    # Related built-in guides for internal linking.
    try:
        import blog_posts as _bp
        related = _bp.all_posts()[:3]
    except Exception:
        related = []
    rel = ""
    if related:
        links = "".join(
            f'<a class=blog-rel href="/blog/{_e_html(r["slug"])}">'
            f'<span class=blog-rel-t>{_e_html(r["title"])}</span>'
            f'<span class=blog-rel-a>Read guide &rarr;</span></a>' for r in related)
        rel = f'<h2>Related guides</h2><div class=blog-rel-grid>{links}</div>'
    cta = (f'<div class=blog-cta><h3>Put your WordPress site on autopilot</h3>'
           f'<p>Bring your own Claude or ChatGPT. 100+ WordPress tools. Nothing goes live without '
           f'your approval.</p><a class="btn btn-primary btn-lg" href="/?signup">Get started free</a></div>'
           f'<p class=blog-back><a href="/blog">&larr; All guides</a></p>')
    # NOTE: body_html is admin-authored trusted content (only the owner can create posts).
    body = post["body_html"] + rel + cta
    return _head(title=f"{post['title']} | {BRAND}", description=post["description"],
                 canonical=f"/blog/{post['slug']}", keywords=post.get("keywords", ""),
                 og_image=hero, schema_json=schema) + f"""
{_nav("both")}
<div class=blog-wrap>
  <div class=blog-inner>
    <a class=blog-crumb href="/blog">&larr; All guides</a>
    <h1 class=blog-h1>{_e_html(post['title'])}</h1>
    <div class=blog-byline><span>wptaskify</span> &middot; <span>{_e_html(post.get('read_time',''))}</span></div>
    <figure class=blog-hero><img src="{hero}" alt="{_e_html(post['title'])}"></figure>
    <article class=blog-article>{body}</article>
  </div>
</div>
{_blog_footer()}{_BLOG_ARTICLE_CSS}
</body></html>"""


# --- Standalone menu pages (Features, How it works, Pricing, FAQ) -----------
_FEATURES = [
    ("AI writes &amp; publishes", "Ask the AI to write a complete, SEO-ready article - with images and schema - and it publishes straight to your WordPress site. No copy-paste."),
    ("100+ WordPress tools", "Posts, pages, media, SEO, AI SEO Score, themes &amp; plugins, backups, redirects and more - all driven by Claude or ChatGPT."),
    ("AI featured images", "Generate realistic, on-topic featured images automatically and set them on your posts - no stock photos or design tools needed."),
    ("On-page SEO on autopilot", "Meta titles, descriptions, focus keywords, internal links, thin content and broken links - checked and fixed automatically."),
    ("AI SEO Score (On-Page, Technical, AEO, GEO)", "A modern, AI-era SEO scorecard measured from your content, with one-click fixes so your site ranks in Google and gets cited by AI answer engines."),
    ("Safe by design", "AES-256 encrypted credentials, isolated accounts, automatic backups before edits, PHP syntax checks, and an approval inbox for risky actions."),
    ("Works with Claude &amp; ChatGPT", "One connector for both. Bring your own AI - no separate AI subscription to buy - and drive your site from whichever assistant you use."),
    ("Themes, plugins &amp; full control", "Create and edit themes, custom CSS, plugins and files safely - the AI can build and redesign, with backups and rollbacks."),
]


# Feature clusters: each = (outcome headline, one-line "so what", [bullets]).
# Outcome-led per research: sell the result, name the mechanism in support.
_FEATURE_CLUSTERS = [
    ("Content &amp; creation", "Turn one instruction into a finished, published post.",
     ["Draft a full, SEO-ready article in your voice - your AI writes it, you hit approve",
      "Get a realistic featured image for every post, generated and set automatically",
      "Insert on-topic images inside the article body - no stock photos or design tools",
      "Schedule posts, duplicate templates and manage pages, all from a single chat"]),
    ("SEO &amp; GEO", "Rank in Google and get cited by AI answer engines.",
     ["Fix meta titles, descriptions and focus keywords across your whole site in one pass",
      "Turn scattered posts into a linked topic cluster - AI proposes the links, you approve",
      "Add and validate schema, fix thin content, broken links and orphan pages",
      "Run an AI SEO Score (On-Page, Technical, AEO, GEO) with one-click fixes",
      "Optimize any post to be quotable by ChatGPT, Perplexity and Google AI Overviews"]),
    ("Site management", "Run the whole site from one place - not just the blog.",
     ["Create and edit themes, plugins, menus and custom CSS safely",
      "Clean up unused media, fix missing alt text and excerpts in bulk",
      "Manage users, authors, categories, tags and redirects",
      "Edit robots.txt, llms.txt and .htaccess without touching the server"]),
    ("Safety &amp; control", "AI with the keys, you with the veto.",
     ["Nothing publishes or changes without your approval in the inbox",
      "An automatic backup is taken before any file edit - restore in one click",
      "Every code change is PHP syntax-checked before it saves, so nothing breaks",
      "AES-256 encrypted credentials, isolated accounts and a full activity log"]),
]


def features_page():
    # Definitional opener (AEO): self-contained, quotable by AI answer engines.
    intro = ('wptaskify is a WordPress service that connects your site to your own Claude '
             'or ChatGPT, so the AI can write articles, optimize SEO, generate images, manage '
             'your themes and plugins, and publish - with every change requiring your approval. '
             'Here is what it can actually do. Want the exhaustive list? See '
             '<a href="/tools">all 100+ tools</a>.')

    # How it works (3 steps) placed high - doubles as the "is this real / how" answer.
    steps = [
        ("1", "Connect your AI", "Install the free wptaskify plugin, then add the connector in Claude or ChatGPT. Two minutes, no code."),
        ("2", "Just ask", "Say what you want in plain language - \"write and publish an SEO post about X,\" \"fix meta across my blog.\""),
        ("3", "You approve, it ships", "Review the change in your approval inbox and hit go. Nothing touches your live site until you do."),
    ]
    steps_html = "".join(
        f'<div class=card><span class=step-num>{n}</span><h3>{t}</h3><p>{d}</p></div>'
        for n, t, d in steps)

    # Capability clusters - the spine of the page.
    clusters_html = ""
    for name, sub, bullets in _FEATURE_CLUSTERS:
        lis = "".join(f'<li>{_CHECK} {b}</li>' for b in bullets)
        clusters_html += (
            f'<div class=fcluster><div class=fcluster-head><h3>{name}</h3>'
            f'<p>{sub}</p></div><ul class=fcluster-list>{lis}</ul></div>')

    # Question-shaped FAQ (AEO) - answer in the first sentence, then elaborate.
    faqs = [
        ("What can AI actually do on a WordPress site with wptaskify?",
         "It can write and publish SEO articles, generate and set images, fix on-page SEO, build internal links, add schema, manage themes and plugins, take backups and more - over 100 tools in total. You give instructions in plain language and approve the changes."),
        ("Does wptaskify need its own AI subscription?",
         "No. You bring your own Claude or ChatGPT account and connect it once, so there is no second AI bill on top of wptaskify."),
        ("Is it safe to connect AI to a live WordPress site?",
         "Yes. Nothing publishes or changes without your approval, an automatic backup runs before any file edit, code is PHP syntax-checked before saving, and your credentials are AES-256 encrypted with every account isolated."),
        ("Do I need to know code to use it?",
         "No. If you can install a plugin, you can run wptaskify. You give instructions in plain English and the AI does the work."),
    ]
    faq_html = "".join(
        f'<details class="faq-item"><summary>{q}</summary><p>{a}</p></details>'
        for q, a in faqs)

    body = f"""
<p>{intro}</p>

<section class=fsec>
<h2>How it works</h2>
<div class=step-grid>{steps_html}</div>
</section>

<section class=fsec>
<h2>Everything your AI can do</h2>
<div class=fcluster-grid>{clusters_html}</div>
<p class=fsec-link><a href="/tools">See the full list of 100+ tools -&gt;</a></p>
</section>

<section class=fsec>
<div class=fcta>
<h3>Ready to put your AI to work?</h3>
<p class=fcta-sub>Connect your own Claude or ChatGPT and let it run your WordPress site.</p>
<a href="/?signup" class="btn btn-primary">Connect my site free</a>
<p class=fcta-fine>No extra AI subscription. Nothing goes live without your approval.</p>
</div>
</section>

<section class=fsec>
<h2>Features FAQ</h2>
<div class=faq>{faq_html}</div>
</section>

<style>
/* consistent vertical rhythm: each section = same top gap, heading = same bottom gap */
.fsec{{margin-top:56px}}
.fsec:first-of-type{{margin-top:48px}}
.doc-wide .fsec h2{{margin:0 auto 22px;display:table}}
.fsec-link{{text-align:center;margin:22px 0 0}}
/* dark CTA panel (home-style) */
.fcta{{text-align:center;padding:56px 40px;border-radius:26px;
  background:radial-gradient(120% 140% at 50% 0%,#1c1917 0%,#0A0A0A 70%);
  border:1px solid rgba(249,115,22,.28);
  box-shadow:0 30px 80px -40px rgba(249,115,22,.5)}}
.light-zone .doc .fcta h3{{color:#fff!important;font-family:'Sora';font-size:clamp(1.5rem,3vw,2rem);margin:0 0 10px}}
.light-zone .doc .fcta .fcta-sub{{color:#C9C6D0!important;font-size:1.05rem;margin:0 0 22px}}
.light-zone .doc .fcta .fcta-fine{{color:#8A8792!important;font-size:.88rem;margin:16px 0 0}}
.step-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:18px;margin:0}}
.step-num{{display:inline-flex;align-items:center;justify-content:center;width:38px;height:38px;
  border-radius:10px;background:rgba(249,115,22,.12);color:#EA580C;font-family:'Sora';
  font-weight:800;font-size:1.1rem;margin-bottom:12px}}
.fcluster-grid{{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin:0}}
.fcluster{{background:#FFFFFF;border:1px solid #E9E8EF;border-radius:var(--radius-lg);padding:26px;
  box-shadow:0 8px 30px -18px rgba(20,19,26,.15);text-align:left}}
.fcluster-head h3{{font-family:'Sora';font-size:1.2rem;color:#14131A;margin:0 0 4px}}
.fcluster-head p{{color:#EA580C;font-weight:600;font-size:.95rem;margin:0 0 14px}}
.fcluster-list{{list-style:none;padding:0;margin:0}}
.fcluster-list li{{display:flex;gap:10px;align-items:flex-start;padding:8px 0;color:#5B5966;
  font-size:.95rem;line-height:1.55}}
.fcluster-list li svg{{color:var(--accent);flex-shrink:0;margin-top:3px}}
@media(max-width:760px){{.step-grid,.fcluster-grid{{grid-template-columns:1fr}}}}
</style>
"""
    # SoftwareApplication + FAQPage schema (AEO): featureList maps to clusters.
    feat_list = ",".join('"' + c[0].replace("&amp;", "and") + '"' for c in _FEATURE_CLUSTERS)
    faq_items = ",".join(
        '{"@type":"Question","name":"' + q.replace('"', "'") +
        '","acceptedAnswer":{"@type":"Answer","text":"' + a.replace('"', "'") + '"}}'
        for q, a in faqs)
    # Only /faq carries FAQPage schema (canonical). This page's mini-FAQ is visual-only
    # to avoid duplicate-FAQPage dilution across pages.
    schema = ('{"@context":"https://schema.org",'
              '"@type":"SoftwareApplication","name":"wptaskify","applicationCategory":"BusinessApplication",'
              '"operatingSystem":"WordPress","offers":{"@type":"Offer","price":"0","priceCurrency":"USD"},'
              '"featureList":[' + feat_list + ']}')

    return _content_page(
        "Features",
        "What wptaskify's AI can do on your WordPress site: write and publish SEO content, generate images, fix on-page SEO and GEO, manage themes and plugins - 100+ tools, with your approval on every change.",
        body, canonical="/features", wide=True, schema_json=schema,
        hero_img=f"{SITE_BASE}/assets/hero-features.webp",
        hero_sub="Write, optimize and publish to WordPress - your AI does the work, you approve every change.",
        keywords="wordpress ai features, what can ai do on wordpress, ai wordpress tools, ai seo wordpress, connect wordpress to claude chatgpt")


def how_page():
    # Three detailed steps (each: number, title, lead, [sub-points]).
    steps = [
        ("1", "Connect your WordPress site",
         "Install the free wptaskify plugin and click Connect. wptaskify creates a dedicated WordPress application password, validates it, and encrypts it with AES-256 - you never copy or paste your real login.",
         ["Works with any standard WordPress site", "About two minutes, no code", "Disconnect any time from WordPress"]),
        ("2", "Link your own Claude or ChatGPT",
         "Add the wptaskify connector inside Claude or ChatGPT and sign in. Your site's 100+ WordPress tools instantly appear in the chat - and because you use your own AI account, there is no extra AI subscription.",
         ["One connector works with both Claude and ChatGPT", "Bring the AI plan you already have", "Nothing else to install"]),
        ("3", "Just ask - you approve, it ships",
         "Tell the AI what you want in plain English: \"write and publish an SEO article about X,\" \"fix meta across my blog.\" It writes, generates images, fixes SEO and publishes - but risky changes wait in your approval inbox until you say go.",
         ["Plain-English instructions, no commands to learn", "Nothing goes live without your approval", "Automatic backup before any file edit"]),
    ]
    steps_html = ""
    for n, t, lead, subs in steps:
        li = "".join(f'<li>{_CHECK} {s}</li>' for s in subs)
        steps_html += (
            f'<div class=hstep><div class=hstep-n>{n}</div>'
            f'<div class=hstep-body><h3>{t}</h3><p>{lead}</p>'
            f'<ul class=hstep-list>{li}</ul></div></div>')

    examples = [
        "Write and publish a 1,500-word SEO article about \"best running shoes for flat feet.\"",
        "Fix missing meta descriptions across my whole blog.",
        "Generate a featured image for my latest 5 posts.",
        "Find and fix broken links, then run my AI SEO Score.",
    ]
    ex_html = "".join(f'<div class=hex>{_CHECK}<span>{e}</span></div>' for e in examples)

    body = f"""
<p>wptaskify connects your WordPress site to your own Claude or ChatGPT in three steps - from signup to your first AI-published post in under five minutes. No developers, no code.</p>

<section class=fsec>
<h2>Three steps to your first AI post</h2>
<div class=hsteps>{steps_html}</div>
</section>

<section class=fsec>
<h2>Connecting Claude or ChatGPT</h2>
<p>wptaskify uses one secure connector URL that both Claude and ChatGPT understand. In your AI, add a custom connector, paste the URL, and sign in with your wptaskify account.</p>
<div class=code-box style="margin:16px 0;max-width:520px"><span>https://wptaskify.com/mcp</span></div>
<div class=conn-grid>
  <div class=conn-card>
    <h3>Claude</h3>
    <ol>
      <li>Open <strong>Settings &rarr; Connectors</strong> (claude.ai or the desktop app).</li>
      <li>Click <strong>Add custom connector</strong>.</li>
      <li>Name it <strong>wptaskify</strong> and paste the URL above.</li>
      <li>Click <strong>Connect</strong>, sign in to wptaskify, and you're done - your 100+ tools appear in the chat.</li>
    </ol>
    <p class=conn-note>Available on Claude Pro, Team, and Enterprise.</p>
  </div>
  <div class=conn-card>
    <h3>ChatGPT</h3>
    <ol>
      <li>You need a paid plan (<strong>Plus, Pro, Business or Enterprise</strong>).</li>
      <li>Open <strong>Settings &rarr; Connectors</strong>. If you don't see "Add custom connector", first turn on <strong>Settings &rarr; Advanced &rarr; Developer mode</strong>.</li>
      <li>Add a custom connector, name it <strong>wptaskify</strong>, paste the URL, and choose <strong>OAuth</strong>.</li>
      <li>Click <strong>Connect</strong>, sign in to wptaskify, and select the connector in your chat.</li>
    </ol>
    <p class=conn-note>ChatGPT's custom connectors are rolling out gradually - if the option is missing, it's your ChatGPT plan/region, not your site.</p>
  </div>
</div>
</section>

<section class=fsec>
<h2>Then just ask - here are real examples</h2>
<div class=hex-grid>{ex_html}</div>
<p style="text-align:center;color:#8A8792;font-size:.9rem;margin-top:16px">The AI picks the right tool from 100+ and does the work. See <a href="/tools">all tools -&gt;</a>.</p>
</section>

<section class=fsec>
<div class=fcta>
<h3>Ready to connect your site?</h3>
<p class=fcta-sub>Install the free plugin, link your Claude or ChatGPT, and publish your first AI post today.</p>
<a href="/?signup" class="btn btn-primary">Connect my site free</a>
<p class=fcta-fine>Free to start - no credit card - nothing goes live without your approval.</p>
</div>
</section>

<style>
.hsteps{{display:grid;gap:18px;margin-top:24px}}
.hstep{{display:grid;grid-template-columns:56px 1fr;gap:20px;align-items:start;
  background:#FFFFFF;border:1px solid #E9E8EF;border-radius:var(--radius-lg);padding:26px;
  box-shadow:0 8px 30px -18px rgba(20,19,26,.15)}}
.hstep-n{{display:flex;align-items:center;justify-content:center;width:56px;height:56px;border-radius:16px;
  background:linear-gradient(180deg,#fb923c,#f97316);color:#fff;font-family:'Sora';font-weight:800;font-size:1.5rem}}
.hstep-body h3{{font-family:'Sora';font-size:1.2rem;color:#14131A;margin:2px 0 8px}}
.hstep-body p{{color:#5B5966;margin:0 0 14px;line-height:1.6}}
.hstep-list{{list-style:none;padding:0;margin:0;display:flex;flex-wrap:wrap;gap:8px 22px}}
.hstep-list li{{display:flex;gap:8px;align-items:center;color:#5B5966;font-size:.9rem}}
.hstep-list svg{{color:var(--accent);flex-shrink:0}}
.hex-grid{{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:24px}}
.hex{{display:flex;gap:11px;align-items:flex-start;background:#F8F7FB;border:1px solid #E9E8EF;
  border-radius:14px;padding:16px 18px;color:#3A3846;font-size:.98rem;font-style:italic}}
.hex svg{{color:var(--accent);flex-shrink:0;margin-top:3px}}
.conn-grid{{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-top:20px}}
.conn-card{{background:#F8F7FB;border:1px solid #E9E8EF;border-radius:16px;padding:22px 24px}}
.conn-card h3{{font-family:'Sora';font-size:1.15rem;color:#14131A;margin:0 0 12px}}
.conn-card ol{{margin:0;padding-left:20px;color:#3A3846;line-height:1.7}}
.conn-card ol li{{margin:6px 0}}
.conn-note{{margin:14px 0 0;color:#8A8792;font-size:.85rem}}
@media(max-width:700px){{.hstep{{grid-template-columns:1fr}}.hex-grid{{grid-template-columns:1fr}}.conn-grid{{grid-template-columns:1fr}}}}
</style>
"""
    # HowTo schema (procedural) - AEO for "how to connect wordpress to claude/chatgpt".
    ht_steps = ",".join(
        '{"@type":"HowToStep","position":' + n + ',"name":"' + t.replace('"', "'") +
        '","text":"' + lead.replace('"', "'") + '"}'
        for n, t, lead, _s in steps)
    schema = ('{"@context":"https://schema.org","@type":"HowTo",'
              '"name":"How to connect your WordPress site to Claude or ChatGPT with wptaskify",'
              '"totalTime":"PT5M","step":[' + ht_steps + ']}')
    return _content_page(
        "How it works",
        "How wptaskify connects your WordPress site to your own Claude or ChatGPT in three steps - install the plugin, link your AI, then just ask. Under five minutes, no code.",
        body, canonical="/how-it-works", wide=True, schema_json=schema,
        hero_img=f"{SITE_BASE}/assets/hero-how.webp",
        hero_sub="Connect your site, link your AI, then just ask - in under five minutes.",
        keywords="how to connect wordpress to ai, connect wordpress to claude, connect wordpress to chatgpt, wptaskify setup")


def pricing_page(country=""):
    is_india = (country or "").upper() == "IN"
    cur = "₹" if is_india else "$"

    # (name, USD, INR, who-it's-for, [sites, actions, images, support], featured, cta)
    plans = [
        ("Free", "$0", "₹0", "Try it on a real site, free",
         ["1 WordPress site", "100 AI actions / month", "5 AI images / month", "Community support"],
         False, "Start free"),
    ]
    if is_india:
        plans.append(
            ("Mini", "$9", "₹700", "For a single blog",
             ["1 site", "800 AI actions / month", "25 AI images / month", "Email support"],
             False, "Get Mini"))
    plans += [
        ("Starter", "$20", "₹1,699", "For an active site",
         ["2 sites", "2,000 AI actions / month", "60 AI images / month", "Priority support"],
         True, "Get Starter"),
        ("Pro", "$99", "₹8,299", "For pros & agencies",
         ["10 sites", "Unlimited AI actions", "200 AI images / month", "White-glove onboarding"],
         False, "Get Pro"),
    ]

    _name2key = {"Free": "", "Mini": "owai_mini", "Starter": "owai_starter", "Pro": "owai_pro"}
    # First-month welcome discount (auto-applied at checkout for new customers). Mirror the
    # db.WELCOME_DISCOUNT table so the pricing page advertises the exact same offer.
    _welcome = {"Starter": 30, "Pro": 40}
    cards = ""
    for i, (name, usd, inr, who, feats, feat, cta) in enumerate(plans):
        amt = inr if is_india else usd
        tag = '<div class=tag>Most popular</div>' if feat else ''
        lis = "".join(f'<li>{_CHECK} {f}</li>' for f in feats)
        cls = "price feat" if feat else "price"
        btn = "btn-primary" if feat or name == "Free" else "btn-ghost"
        pkey = _name2key.get(name, "")
        # Paid plan -> signup remembering the plan (auto-checkout after verify).
        href = f"/?signup&plan={pkey}" if pkey else "/?signup"
        # First-month discount badge + "first month" price (new customers only).
        wpct = _welcome.get(name, 0)
        price_block = f'<div class=amt>{amt}<span>/mo</span></div>'
        promo_badge = ""
        if wpct:
            try:
                _raw = float((amt or "0").lstrip("₹$").replace(",", ""))
                _first = _raw * (100 - wpct) / 100.0
                _fs = f"{_first:,.0f}" if is_india else f"{_first:,.2f}".rstrip("0").rstrip(".")
            except (TypeError, ValueError):
                _fs = ""
            promo_badge = f'<div class=promo-badge>{wpct}% OFF 1st month</div>'
            if _fs:
                price_block = (
                    f'<div class=amt><span class=amt-was>{amt}</span> {cur}{_fs}'
                    f'<span>1st mo</span></div>'
                    f'<p class=amt-then>then {amt}/mo &middot; new customers</p>')
        cards += (
            f'<div class="{cls}">{tag}{promo_badge}<h3>{name}</h3>'
            f'<p class=price-who>{who}</p>'
            f'{price_block}'
            f'<a href="{href}" class="btn {btn} btn-block">{cta}</a>'
            f'<ul>{lis}</ul>'
            f'<p class=price-all>{_CHECK} All 100+ tools included</p></div>')
    cols = "cols4" if len(plans) >= 4 else "cols3"

    # Plain-HTML declarative price sentence (AEO - always both currencies for machines).
    aeo_prices = ("wptaskify pricing (2026): Free $0, Starter $20/month, Pro $99/month. "
                  "In India: Free ₹0, Mini ₹700, Starter ₹1,699, Pro ₹8,299 per month. "
                  "New customers get an automatic first-month discount: 30% off Starter and "
                  "40% off Pro (applied at checkout, first month only). "
                  "Every plan includes all 100+ WordPress tools; you bring your own Claude or "
                  "ChatGPT, so there is no extra AI subscription.")

    # Comparison table (real HTML - AEO parseable). Columns depend on region.
    if is_india:
        cols_h = ["Free", "Mini", "Starter", "Pro"]
        rows = [
            ("Price / month", ["₹0", "₹700", "₹1,699", "₹8,299"]),
            ("WordPress sites", ["1", "1", "2", "10"]),
            ("AI actions / month", ["100", "800", "2,000", "Unlimited"]),
            ("AI images / month", ["5", "25", "60", "200"]),
            ("All 100+ tools", ["✓", "✓", "✓", "✓"]),
            ("Support", ["Community", "Email", "Priority", "White-glove"]),
        ]
    else:
        cols_h = ["Free", "Starter", "Pro"]
        rows = [
            ("Price / month", ["$0", "$20", "$99"]),
            ("WordPress sites", ["1", "2", "10"]),
            ("AI actions / month", ["100", "2,000", "Unlimited"]),
            ("AI images / month", ["5", "60", "200"]),
            ("All 100+ tools", ["✓", "✓", "✓"]),
            ("Support", ["Community", "Priority", "White-glove"]),
        ]
    thead = "<tr><th></th>" + "".join(f"<th>{c}</th>" for c in cols_h) + "</tr>"
    tbody = "".join(
        "<tr><td class=cmp-row>" + label + "</td>" +
        "".join(f"<td>{v}</td>" for v in vals) + "</tr>"
        for label, vals in rows)
    cmp_table = f'<table class=cmp><thead>{thead}</thead><tbody>{tbody}</tbody></table>'

    # Pricing FAQ (maps 1:1 to anxieties).
    faqs = [
        ("How much does wptaskify cost?",
         f"Plans start free. Paid plans are Starter at {'₹1,699' if is_india else '$20'}/month and Pro at {'₹8,299' if is_india else '$99'}/month{', with an India-only Mini plan at ₹700/month' if is_india else ''}. Every plan includes all 100+ tools."),
        ("Is there a discount for new customers?",
         "Yes. New customers get an automatic first-month discount - 30% off Starter and 40% off Pro - applied at checkout, no code needed. It's a one-time welcome offer on your first month; the plan then renews at the normal monthly price."),
        ("Is there really a free plan?",
         "Yes - free forever, no credit card required. You get all 100+ tools on 1 site, with 100 AI actions and 5 AI images a month."),
        ("Do I need to pay for AI separately?",
         "You use your own Claude or ChatGPT account, so we never charge you for AI. A standard $20/month Claude or ChatGPT plan is all you need, and you are never paying for AI twice."),
        ("What is an \"AI action\"?",
         "One AI action is one thing the AI does on your site - write a post, fix a page's SEO, or add an internal link. Images are counted separately. For scale, 2,000 actions is roughly dozens of full articles plus hundreds of SEO fixes a month."),
        ("What happens when I hit my monthly limit?",
         "Actions simply pause until your next cycle or you upgrade. Nothing breaks and there are no surprise overage charges."),
        ("Do I get all the tools on the free plan?",
         "Yes. Every plan includes all 100+ tools. Plans differ only by monthly limits, number of sites, and support - never by which tools you get."),
        ("Can I cancel anytime?",
         "Yes. Billing is monthly, you can cancel in one click, and there is no annual lock-in."),
        ("Is my payment safe?",
         "Payments run securely through Razorpay. We never see or store your card details."),
        ("Will it publish things without my permission?",
         "No. Nothing goes live without your approval, and your site credentials are AES-256 encrypted."),
    ]
    faq_html = "".join(
        f'<details class="faq-item"><summary>{q}</summary><p>{a}</p></details>'
        for q, a in faqs)

    body = f"""
<p>All 100+ tools on every plan. You bring your own Claude or ChatGPT, so there is <b>no extra AI subscription</b>. Start free, upgrade any time, cancel whenever. <span style="display:none">{aeo_prices}</span></p>

<div class=noaibill>{_CHECK} <span>No second AI bill - wptaskify plugs into the Claude or ChatGPT plan you already have.</span></div>

<div class=cur-switch>
  <a href="/set-currency?c=IN&next=/pricing" class="cur-opt {'on' if is_india else ''}">₹ INR</a>
  <a href="/set-currency?c=US&next=/pricing" class="cur-opt {'' if is_india else 'on'}">$ USD</a>
</div>

<div class="prices {cols}">{cards}</div>

<div class=action-explain>
<b>What's an AI action?</b> One thing the AI does on your site - write a post, fix a page's SEO, add an internal link. Images are counted separately.
<div class=action-chips><span>Write a post</span><span>Fix on-page SEO</span><span>Add an internal link</span></div>
<p class=action-anchor>2,000 actions ≈ dozens of full articles plus hundreds of SEO fixes a month.</p>
</div>

<h2>Compare plans</h2>
<div class=cmp-wrap>{cmp_table}</div>
<p class=cmp-note>Plans differ only by monthly limits, sites and support - never by which tools you get. Reach a limit and actions pause until next cycle or you upgrade, with no surprise overages.</p>

<div class=trustrow>
<span>{_CHECK} Cancel anytime, no lock-in</span>
<span>{_CHECK} Nothing goes live without your approval</span>
<span>{_CHECK} Secure payments via Razorpay - we never see your card</span>
</div>

<div class=fcta>
<h3>Start free - no credit card</h3>
<p class=fcta-sub>All 100+ tools on 1 site. Bring your own Claude or ChatGPT and upgrade only when you outgrow the free limits.</p>
<a href="/?signup" class="btn btn-primary">Start free</a>
<p class=fcta-fine>Free forever plan. No surprise overages. Cancel paid plans anytime.</p>
</div>

<h2>Pricing FAQ</h2>
<div class=faq>{faq_html}</div>

<style>
.noaibill{{display:flex;gap:10px;align-items:center;justify-content:center;max-width:640px;margin:8px auto 32px;
  background:#fff8f3;border:1px solid rgba(249,115,22,.25);border-radius:14px;padding:14px 18px;
  color:#5B5966;font-size:.98rem}}
.noaibill svg{{color:var(--accent);flex-shrink:0}}
.cur-switch{{display:inline-flex;background:#F1F0F5;border:1px solid #E9E8EF;border-radius:11px;
  padding:3px;gap:2px;margin:0 auto 26px;position:relative;left:50%;transform:translateX(-50%)}}
.cur-opt{{padding:8px 18px;border-radius:8px;font-family:'Sora';font-weight:600;font-size:.88rem;
  color:#5B5966!important;text-decoration:none}}
.cur-opt:hover{{color:#14131A!important;text-decoration:none}}
.cur-opt.on{{background:var(--accent);color:#fff!important}}
/* pricing card internal rhythm - even gaps, aligned rows */
.prices .price h3{{margin-bottom:2px}}
.price-who{{color:#8A8792;font-size:.9rem;margin:0 0 16px;min-height:1.2em}}
.prices .price .amt{{margin-bottom:6px}}
/* first-month discount badge + strikethrough price */
.promo-badge{{position:absolute;top:14px;right:14px;background:#16a34a;color:#fff;
  font-family:'Sora';font-weight:700;font-size:.68rem;letter-spacing:.02em;
  padding:4px 9px;border-radius:999px;box-shadow:0 4px 12px -4px rgba(22,163,74,.5)}}
.amt-was{{font-size:1.15rem;color:#B4B1BE;text-decoration:line-through;font-weight:600;margin-right:4px}}
.amt-then{{color:#16a34a;font-size:.82rem;font-weight:600;margin:0 0 18px}}
.prices .price .btn-block{{margin-bottom:4px}}
.prices .price ul{{margin:20px 0 0}}
.price-all{{display:flex;gap:8px;align-items:center;color:#5B5966;font-size:.86rem;margin:16px 0 0;
  padding-top:16px;border-top:1px solid #EEEDF2}}
.price-all svg{{color:var(--accent);flex-shrink:0}}
.action-explain{{background:#F8F7FB;border:1px solid #E9E8EF;border-radius:18px;padding:24px 26px;margin:34px 0 0;
  text-align:center;color:#5B5966}}
.action-explain b{{color:#14131A}}
.action-chips{{display:flex;flex-wrap:wrap;gap:8px;justify-content:center;margin:14px 0 0}}
.action-chips span{{background:#fff;border:1px solid #E0DEE8;border-radius:999px;padding:6px 14px;
  font-size:.85rem;color:#14131A;font-weight:500}}
.action-anchor{{margin:14px 0 0;font-size:.9rem;color:#8A8792}}
.cmp-wrap{{overflow-x:auto}}
.cmp{{width:100%;border-collapse:collapse;margin-top:20px;font-size:.95rem;min-width:520px}}
.cmp th,.cmp td{{padding:13px 16px;text-align:center;border-bottom:1px solid #E9E8EF}}
.cmp thead th{{font-family:'Sora';color:#14131A;font-size:1rem;font-weight:700}}
.cmp .cmp-row{{text-align:left;color:#14131A;font-weight:600}}
.cmp td{{color:#5B5966}}
.cmp tbody tr:nth-child(5) td{{color:var(--accent);font-weight:700}}
.cmp-note{{text-align:center;color:#8A8792;font-size:.9rem;margin:16px auto 0;max-width:70ch}}
.trustrow{{display:flex;flex-wrap:wrap;gap:10px 26px;justify-content:center;margin:40px 0 0;
  color:#5B5966;font-size:.92rem}}
.trustrow span{{display:flex;gap:8px;align-items:center}}
.trustrow svg{{color:var(--accent)}}
</style>
"""
    # Product + AggregateOffer + per-plan Offers + FAQPage schema (AEO).
    lo, hi = ("0", "8299") if is_india else ("0", "99")
    ccy = "INR" if is_india else "USD"
    offers = []
    for name, usd, inr, *_ in plans:
        price = (inr if is_india else usd).replace(cur, "").replace(",", "").replace("₹", "").replace("$", "")
        offers.append('{"@type":"Offer","name":"' + name + '","price":"' + price +
                      '","priceCurrency":"' + ccy + '","url":"' + SITE_BASE +
                      '/pricing","availability":"https://schema.org/InStock"}')
    faq_items = ",".join(
        '{"@type":"Question","name":"' + q.replace('"', "'") +
        '","acceptedAnswer":{"@type":"Answer","text":"' + a.replace('"', "'") + '"}}'
        for q, a in faqs)
    # Only /faq carries FAQPage schema (canonical). Pricing keeps Product/AggregateOffer;
    # its mini-FAQ is visual-only to avoid duplicate-FAQPage dilution.
    schema = ('{"@context":"https://schema.org",'
              '"@type":"Product","name":"wptaskify","description":"Connect WordPress to your own Claude or ChatGPT - 100+ AI tools on every plan.",'
              '"offers":{"@type":"AggregateOffer","lowPrice":"' + lo + '","highPrice":"' + hi +
              '","priceCurrency":"' + ccy + '","offerCount":"' + str(len(plans)) +
              '","offers":[' + ",".join(offers) + ']}}')
    return _content_page(
        "Pricing",
        "wptaskify pricing: free to start, Starter $20/mo, Pro $99/mo (local pricing in India). All 100+ tools on every plan. Bring your own Claude or ChatGPT - no extra AI subscription.",
        body, canonical="/pricing", wide=True, schema_json=schema,
        hero_img=f"{SITE_BASE}/assets/hero-pricing.webp",
        hero_sub="All 100+ tools on every plan. Bring your own AI - no extra AI bill.",
        keywords="wptaskify pricing, how much does wptaskify cost, wordpress ai pricing, ai wordpress plans, wptaskify free plan")


# Canonical FAQ - the comprehensive, cross-cutting reference. Grouped by funnel
# priority. Each answer: first sentence = the complete answer, then factual support,
# self-contained (repeat "wptaskify", no "it"/"as above"). This is the ONLY page
# that carries FAQPage schema (mini-FAQs elsewhere are visual-only, to avoid dilution).
_FAQ_GROUPS = [
    ("Getting started", "getting-started", [
        ("What is wptaskify and how does it work?",
         "wptaskify is a WordPress service that connects your site to your own Claude or ChatGPT so the AI can run 100+ WordPress tools for you. Once connected, you give instructions in plain language - \"write and publish an SEO article,\" \"fix my on-page SEO\" - and the AI does the work, with nothing going live until you approve it."),
        ("How do I connect my WordPress site to Claude or ChatGPT?",
         "Install the free wptaskify plugin on your WordPress site and click Connect, then add the wptaskify connector in Claude or ChatGPT and sign in. Your site's tools then appear right inside the chat, and you can start giving instructions. The whole setup takes about two minutes."),
        ("What do I need to get started?",
         "You need a WordPress site, the free wptaskify plugin, and your own Claude or ChatGPT account. There is no separate AI subscription to buy from wptaskify - you bring the AI you already use."),
        ("Does wptaskify work with any WordPress site?",
         "wptaskify works with standard self-hosted WordPress sites where you can install a plugin. It works alongside your existing theme and plugins, including SEO plugins like Yoast and Rank Math."),
        ("How long does setup take?",
         "Setup usually takes about two minutes: install the plugin, click Connect, then add the connector in Claude or ChatGPT. No code and no copying of passwords is required."),
        ("Do I need to know how to code to use wptaskify?",
         "No. If you can install a WordPress plugin, you can use wptaskify. You give instructions in plain English and the AI picks the right tool and runs it."),
    ]),
    ("Safety & security", "safety", [
        ("Is it safe to give AI access to my WordPress site?",
         "Yes. wptaskify keeps you in control: nothing publishes or changes without your approval, an automatic backup runs before any file edit, code is PHP syntax-checked before saving, and your credentials are AES-256 encrypted with every account fully isolated."),
        ("Will the AI change or publish anything without my approval?",
         "No. Risky actions wait in an approval inbox until you approve them, so nothing goes live on your site without your say-so. You can also let trusted, low-risk tasks run automatically if you choose."),
        ("How is my site data protected?",
         "wptaskify encrypts your WordPress credentials with AES-256 and isolates every account so no user can access another's data. File edits are backed up first and syntax-checked, so a bad change cannot take your site down."),
        ("Does wptaskify store my WordPress password?",
         "wptaskify connects using a dedicated WordPress application password, not your main login, and stores it encrypted with AES-256. You can revoke that access from WordPress at any time."),
        ("Does wptaskify use my content to train AI models?",
         "No. wptaskify does not use your site content to train any AI model. Your content is processed only to carry out the tasks you request through your own Claude or ChatGPT account."),
        ("What happens to my data if I cancel?",
         "If you cancel, you can disconnect your site and your stored credentials are removed. Your WordPress content stays on your own site - wptaskify never holds your website itself."),
    ]),
    ("How the AI works", "how-it-works", [
        ("Do I need a separate ChatGPT or Claude subscription?",
         "You use your own Claude or ChatGPT account, so wptaskify never charges you for AI. A standard $20/month Claude or ChatGPT plan is all you need, and you are never paying for AI twice."),
        ("What does \"bring your own AI\" mean and why does it save money?",
         "\"Bring your own AI\" means wptaskify plugs into the Claude or ChatGPT subscription you already have, instead of bundling and re-charging you for AI. This saves you a second AI bill - often $20 to $100+ a month compared with tools that include their own AI."),
        ("Which AI models does wptaskify work with?",
         "wptaskify works with both Claude and ChatGPT through a single connector. You choose whichever assistant you already use - there is no separate AI subscription to buy from wptaskify."),
        ("What counts as one \"AI action\"?",
         "One AI action is one thing the AI does on your site - write a post, fix a page's SEO, or add an internal link. Images are counted separately. For scale, 2,000 actions is roughly dozens of full articles plus hundreds of SEO fixes a month."),
        ("Can ChatGPT or Claude publish blog posts to WordPress automatically?",
         "Yes. Once connected, your AI can write a full SEO article, generate its images, set the SEO fields, and publish it to your WordPress site - all from a single instruction. Publishing still respects your approval settings."),
    ]),
    ("Pricing & plans", "pricing", [
        ("How much does wptaskify cost?",
         "wptaskify starts free. Paid plans are Starter at $20/month and Pro at $99/month (local pricing in India: Mini ₹700, Starter ₹1,699, Pro ₹8,299). Every plan includes all 100+ tools, and because you bring your own AI there is no extra AI subscription."),
        ("Is the free plan really free, and what are its limits?",
         "Yes - the free plan is free forever with no credit card required. It includes all 100+ tools on 1 site, with 100 AI actions and 5 AI images per month."),
        ("What's the difference between the Free, Starter and Pro plans?",
         "All plans include every tool; they differ only by monthly limits, number of sites, and support. Free covers 1 site and 100 actions, Starter raises that to 2,000 actions with priority support, and Pro adds 10 sites, unlimited actions and white-glove onboarding."),
        ("What happens when I hit my monthly AI-action limit?",
         "Your actions simply pause until the next billing cycle or you upgrade. Nothing breaks and there are no surprise overage charges."),
        ("Can I use wptaskify on more than one site?",
         "Yes. The Pro plan supports up to 10 WordPress sites and Starter covers 2; Free and Mini cover 1 site each. You can upgrade any time as you add sites."),
    ]),
    ("Features & capabilities", "features", [
        ("What can the AI actually do on my WordPress site?",
         "The AI can write and publish articles, generate and set featured images, optimize meta titles, descriptions and schema, build internal links, fix broken links, run SEO and GEO audits, edit themes and CSS, create plugins, manage users, and take backups - over 100 tools in total."),
        ("Can it generate images for my posts?",
         "Yes. wptaskify can generate realistic featured images with AI and set them on your posts automatically, and it can also place on-topic images inside the article body - no stock photos or design tools needed."),
        ("Can it fix on-page SEO and add internal links?",
         "Yes. wptaskify can fix meta titles and descriptions, add and validate schema, and build keyword-rich internal links across your posts. It also runs an AI SEO Score covering On-Page, Technical, AEO and GEO with one-click fixes."),
        ("Can it manage themes, plugins, users and backups?",
         "Yes. wptaskify can create and edit themes and plugins, manage users and menus, and take full-site backups with one-click restore. Code edits are syntax-checked and backed up first, so nothing breaks."),
        ("Will using AI content hurt my Google rankings?",
         "No, as long as the content is genuinely helpful, which is what wptaskify is built for. It writes on-topic, SEO-optimized articles you review and approve, and it can also optimize content to be cited by AI answer engines like ChatGPT and Perplexity."),
    ]),
    ("Troubleshooting", "troubleshooting", [
        ("My site won't connect - what should I do?",
         "First confirm the wptaskify plugin is installed and active and that your WordPress REST API is reachable. If a connection is rejected, wptaskify shows the specific reason (for example a theme error or wrong credentials) so you can fix it and reconnect."),
        ("The connector isn't showing my tools in Claude or ChatGPT - why?",
         "This usually means the connector needs to be re-authorized. Remove and re-add the wptaskify connector in Claude or ChatGPT and sign in again; your site's tools will reappear in the chat."),
        ("Why did an AI action fail or get skipped?",
         "An action can pause if it needs your approval, if you have reached your monthly limit, or if WordPress rejected the change. wptaskify reports the reason so you can approve it, upgrade, or adjust and retry."),
    ]),
    ("Billing & cancellation", "billing", [
        ("Can I cancel anytime?",
         "Yes. Billing is monthly, you can cancel in one click, and there is no annual lock-in. You keep access until the end of the paid period."),
        ("How do I upgrade, downgrade, or cancel?",
         "You can change plans any time from your account; upgrades apply immediately and downgrades or cancellations apply from the next billing cycle. There are no lock-in contracts."),
        ("Is my payment safe?",
         "Yes. Payments run securely through Razorpay, and wptaskify never sees or stores your card details."),
        ("Will I lose my work or content if I cancel?",
         "No. Your WordPress content lives on your own site, not on wptaskify, so cancelling only stops the AI connection. Everything the AI already published stays exactly where it is."),
    ]),
]


def faq_page():
    # Jump-nav pills (visible ToC).
    nav = "".join(
        f'<a href="#{slug}" class=fq-nav-pill data-cat="{slug}">{name}</a>'
        for name, slug, _qs in _FAQ_GROUPS)

    # Grouped accordions with per-question anchor ids (deep-linkable for AEO).
    groups_html = ""
    all_faqs = []
    for name, slug, qs in _FAQ_GROUPS:
        items = ""
        for q, a in qs:
            qid = _tool_slug(q)[:60]
            all_faqs.append((q, a))
            items += (
                f'<details class="faq-item" id="{qid}" data-q="{q.lower()}" data-a="{a.lower()}">'
                f'<summary>{q}<a href="#{qid}" class=fq-anchor aria-label="Link to this question" '
                f'onclick="event.stopPropagation()">#</a></summary><p>{a}</p></details>')
        groups_html += (
            f'<section class=fq-group id="{slug}" data-cat="{slug}">'
            f'<h2>{name}</h2><div class=faq>{items}</div></section>')

    body = f"""
<p>Answers to the most common questions about wptaskify - connecting your WordPress site to your own Claude or ChatGPT, safety, pricing, and what the AI can do. Still stuck? <a href="/contact">Contact us</a>.</p>

<div class=fq-search-wrap>
<input type=text id=fqsearch class=tsearch autocomplete=off placeholder="Search questions (try 'safe', 'cost', 'connect', 'cancel')">
<span id=fqsearch-count class=tsearch-count></span>
</div>

<nav class=fq-nav aria-label="FAQ categories">{nav}</nav>

<div class=fq-body>{groups_html}</div>
<p id=fqsearch-empty class=tsearch-empty hidden>No questions match. Try another word, or <a href="/contact">contact us</a>.</p>

<div class=fcta>
<h3>Still have a question?</h3>
<p class=fcta-sub>Start free and see for yourself, or reach out - we usually reply within a few hours.</p>
<a href="/?signup" class="btn btn-primary">Start free</a>
<p class=fcta-fine>Free plan - all tools - no AI subscription - nothing goes live without your approval.</p>
</div>

<p class=fq-cross>Looking for something specific? See <a href="/features">features</a>, <a href="/tools">all 100+ tools</a>, or <a href="/pricing">pricing</a>.</p>

<style>
.fq-search-wrap{{position:relative;max-width:620px;margin:28px auto 0}}
.fq-search-wrap .tsearch-count{{display:block;text-align:center;color:#8A8792;font-size:.85rem;margin-top:8px;min-height:1em}}
.fq-nav{{position:sticky;top:0;z-index:20;display:flex;flex-wrap:wrap;gap:8px;justify-content:center;
  padding:14px 0;margin:14px 0 24px;background:rgba(255,255,255,.86);backdrop-filter:blur(8px)}}
.fq-nav-pill{{font-size:.85rem;font-weight:600;color:#5B5966!important;background:#F3F1F7;border:1px solid #E9E8EF;
  padding:7px 14px;border-radius:999px;text-decoration:none;transition:all .15s;white-space:nowrap}}
.fq-nav-pill:hover{{border-color:rgba(249,115,22,.4)}}
.fq-nav-pill.active{{background:var(--accent);color:#fff!important;border-color:var(--accent)}}
.fq-group{{margin:0 0 30px;scroll-margin-top:72px}}
.light-zone .doc .fq-group h2{{display:block;margin:0 0 18px;text-align:center;font-size:1.4rem;color:#14131A}}
.light-zone .doc .fq-group h2::after{{display:none}}
.faq-item{{scroll-margin-top:76px}}
.faq-item summary{{gap:12px}}
.fq-anchor{{color:#C9C6D0!important;text-decoration:none;font-weight:700;opacity:0;transition:opacity .15s;margin-left:auto}}
.faq-item:hover .fq-anchor{{opacity:1}}
.fq-anchor:hover{{color:var(--accent)!important}}
.faq-item summary::after{{margin-left:8px}}
.fq-cross{{text-align:center;color:#8A8792;font-size:.92rem;margin-top:26px}}
</style>
<script>
(function(){{
  var q=document.getElementById('fqsearch'), cnt=document.getElementById('fqsearch-count'),
      empty=document.getElementById('fqsearch-empty'),
      items=[].slice.call(document.querySelectorAll('.faq-item')),
      groups=[].slice.call(document.querySelectorAll('.fq-group'));
  if(q){{
    q.addEventListener('input',function(){{
      var v=q.value.trim().toLowerCase(), n=0;
      items.forEach(function(it){{
        var m=!v||it.dataset.q.indexOf(v)>-1||it.dataset.a.indexOf(v)>-1;
        it.style.display=m?'':'none'; if(m){{n++; if(v)it.open=true; }} else {{it.open=false;}}
      }});
      groups.forEach(function(g){{
        var any=[].slice.call(g.querySelectorAll('.faq-item')).some(function(x){{return x.style.display!=='none';}});
        g.style.display=any?'':'none';
      }});
      cnt.textContent=v?(n+' question'+(n===1?'':'s')+' match "'+q.value.trim()+'"'):'';
      empty.hidden=!(v&&n===0);
    }});
  }}
  // open the accordion whose id matches the URL hash (deep-link support)
  function openHash(){{
    if(location.hash.length>1){{
      var el=document.getElementById(location.hash.slice(1));
      if(el&&el.tagName==='DETAILS'){{el.open=true;el.scrollIntoView({{block:'center'}});}}
    }}
  }}
  openHash(); window.addEventListener('hashchange',openHash);
  // sticky nav active-state
  var pills=[].slice.call(document.querySelectorAll('.fq-nav-pill'));
  if('IntersectionObserver' in window && pills.length){{
    var byCat={{}}; pills.forEach(function(p){{byCat[p.dataset.cat]=p;}});
    var io=new IntersectionObserver(function(es){{
      es.forEach(function(e){{
        if(e.isIntersecting){{
          pills.forEach(function(p){{p.classList.remove('active');}});
          var a=byCat[e.target.dataset.cat]; if(a)a.classList.add('active');
        }}
      }});
    }},{{rootMargin:'-40% 0px -55% 0px'}});
    groups.forEach(function(g){{io.observe(g);}});
  }}
}})();
</script>
"""
    # Single canonical FAQPage schema (all Qs, answers match visible text) + per-Q url anchors.
    items = ",".join(
        '{"@type":"Question","name":"' + q.replace('"', "'") +
        '","url":"' + SITE_BASE + '/faq#' + _tool_slug(q)[:60] +
        '","acceptedAnswer":{"@type":"Answer","text":"' + a.replace('"', "'") + '"}}'
        for q, a in all_faqs)
    schema = '{"@context":"https://schema.org","@type":"FAQPage","mainEntity":[' + items + ']}'
    return _content_page(
        "FAQ",
        "wptaskify FAQ: how to connect WordPress to Claude or ChatGPT, is it safe, how much it costs, and what the AI can do - answered.",
        body, canonical="/faq", schema_json=schema, wide=True,
        hero_img=f"{SITE_BASE}/assets/hero-faq.webp",
        hero_sub="Connecting, safety, pricing and capabilities - answered.",
        keywords="wptaskify faq, connect wordpress to chatgpt, connect wordpress to claude, is wptaskify safe, wptaskify pricing, wordpress ai faq")


# ---------------------------------------------------------------------------
# Tools page - the full catalog of what the AI can do, grouped by category.
# Each item: (Friendly name, one-line description). Ordered for scanning.
# ---------------------------------------------------------------------------
_TOOL_GROUPS = [
    ("Content & publishing", "Write, edit, schedule and publish posts and pages - AI does the work, you approve.", [
        ("Create post", "Draft a full SEO article with title, HTML body and excerpt."),
        ("Publish full article", "Write, add images, set SEO and publish a complete post in one go."),
        ("Update post", "Edit any post's title, content, status or fields."),
        ("Delete post", "Trash or permanently remove a post."),
        ("Duplicate post", "Clone a post as a template to reuse structure."),
        ("Schedule post", "Auto-publish a post at a future date and time."),
        ("Bulk schedule posts", "Queue many posts to publish on a schedule at once."),
        ("Create page", "Build a new page (About, landing, calculator, etc.)."),
        ("Update page", "Edit an existing page's content or status."),
        ("Bulk find & replace", "Find and replace text across every post on the site."),
        ("Insert in-article image", "Generate and place an image inside the article body."),
        ("List / get posts & pages", "Browse and read the full raw content of any post or page."),
        ("Revisions & restore", "List revisions and roll a post back to an earlier version."),
        ("Site search", "Search across all content on the site."),
    ]),
    ("Images & media", "Generate realistic AI images and manage the media library.", [
        ("Generate featured image", "Create a realistic photo with AI and attach it to a post."),
        ("Generate image (standalone)", "Make any image from a text prompt and upload it."),
        ("AI alt text", "Write accurate alt text for images with AI for accessibility + SEO."),
        ("Fix missing alt text", "Find images with no alt text and fill them in."),
        ("Bulk optimize images", "Compress and optimize media across the library."),
        ("Upload from URL", "Pull an image from any public URL into the media library."),
        ("Set featured image", "Assign an existing image as a post's thumbnail."),
        ("Delete unused media", "Find and clean out images not used anywhere."),
    ]),
    ("SEO & meta", "On-page SEO, meta descriptions, schema and audits - Yoast/Rank Math aware.", [
        ("AI SEO Score", "Score any post across On-Page, Technical, AEO, GEO and Authority."),
        ("SEO audit post", "Full on-page SEO audit with fixes for a single post."),
        ("Get / update post SEO", "Read and set the SEO title and meta description."),
        ("Bulk generate meta", "Auto-write meta descriptions for posts that are missing one."),
        ("Fix missing excerpts", "Generate excerpts for posts that don't have one."),
        ("Find & replace meta", "Update an SEO field across many posts at once."),
        ("Audit SEO fields", "Check SEO fields site-wide and flag gaps."),
        ("Find thin content", "Spot posts that are too short to rank well."),
        ("Find duplicate titles", "Detect posts competing with the same title."),
        ("Validate schema", "Check a post's JSON-LD schema for errors."),
        ("Update post schema", "Add or replace structured data without touching the body."),
        ("SEO backend info", "Detect which SEO plugin (Yoast/Rank Math/AIOSEO) is active."),
        ("Clean AIOSEO leftovers", "Scan and remove stale data from a removed SEO plugin."),
        ("Verify live meta", "Confirm the meta actually rendered on the live page."),
    ]),
    ("AI search & GEO", "Get cited by ChatGPT, Perplexity and Google's AI answers.", [
        ("GEO audit post", "Score how quotable and citable a post is for AI answer engines."),
        ("GEO optimize post", "Rewrite a post to be more likely cited by AI search."),
        ("Edit llms.txt", "Manage the llms.txt file that guides AI crawlers."),
        ("Ping search engines", "Notify search engines that content changed."),
        ("Generate sitemap", "Serve and refresh the XML sitemap."),
    ]),
    ("Internal links & structure", "Build topical authority with smart internal linking.", [
        ("Plan internal links", "Propose keyword-rich, relevant internal links across posts."),
        ("Apply internal links plan", "Insert an approved internal-linking plan safely."),
        ("Bulk internal links", "Add quality internal links across many posts at once."),
        ("Suggest internal links", "Recommend links for a single post."),
        ("Find orphan pages", "Find pages with no internal links pointing to them."),
        ("Find related posts", "Surface posts related by topic for linking."),
        ("Check broken links", "Scan the site for broken links to fix."),
        ("Create redirect", "Add a 301 redirect for a moved or deleted URL."),
        ("404 log", "See which missing URLs visitors are hitting."),
    ]),
    ("Categories, tags & menus", "Organize taxonomy and navigation.", [
        ("Create / list categories", "Add categories and browse existing ones."),
        ("Create / list tags", "Add tags and browse existing ones."),
        ("Bulk assign terms", "Assign categories and tags to many posts at once."),
        ("Bulk update category", "Merge or move all posts from one category to another."),
        ("Menus & menu items", "List menus and add or remove navigation items."),
        ("Update permalinks", "Set the URL/permalink structure."),
    ]),
    ("Users, comments & authors", "Manage people and moderation.", [
        ("List / create users", "See site users and add new ones with a role."),
        ("Change user role", "Promote or change a user's permissions."),
        ("Authors", "List authors and set or change a post's author."),
        ("Moderate comments", "Approve, spam, trash or delete comments."),
    ]),
    ("Themes, plugins & files (Studio)", "Full site control - edit code, themes and plugins with backups.", [
        ("List / read theme & plugin files", "Browse and read any theme or plugin file."),
        ("Write theme/plugin file", "Edit code with an automatic backup + PHP syntax check first."),
        ("Create plugin", "Scaffold a brand-new plugin from a description."),
        ("Create theme", "Generate a new theme."),
        ("Preview / activate / rollback theme", "Safely try, switch and revert themes."),
        ("List / activate / deactivate plugins", "Manage installed plugins."),
        ("Install plugin from repo", "Install a plugin straight from the WordPress directory."),
        ("Custom CSS", "Read and set the site's custom CSS."),
        ("Edit robots.txt / .htaccess", "Edit server and crawler config files."),
    ]),
    ("Backups, safety & site health", "Nothing breaks - backups, approvals and health checks.", [
        ("Full site backup", "Take a complete backup before big changes."),
        ("Restore site backup", "Roll the whole site back to a safe point."),
        ("List studio backups", "See available restore points."),
        ("Approval inbox", "Route risky actions to you for a one-click approve/reject."),
        ("Check site health", "Run WordPress health checks and surface issues."),
        ("Activity log", "See a full log of what the AI did and when."),
        ("Site & studio info", "Read core site details and capabilities."),
        ("WP options", "Read and update low-level WordPress options."),
    ]),
]


# Plain-English "Try:" example command for each tool in _TOOL_GROUPS.
# Keyed by the EXACT tool name used in _TOOL_GROUPS above. First-person, one line,
# using [brackets] for the bit the user fills in. Anything not listed here falls
# back to a generic 'Ask your AI: "<tool name>".'
_TOOL_COMMANDS = {
    # Content & publishing
    "Create post": 'Write and publish a blog post about [topic].',
    "Publish full article": 'Write an SEO-optimized article on [topic] and publish it with a featured image.',
    "Update post": 'Update my post "[title]" and fix the intro.',
    "Delete post": 'Move the post "[title]" to trash.',
    "Duplicate post": 'Duplicate "[title]" so I can reuse it as a template.',
    "Schedule post": 'Schedule my draft "[title]" to publish next Monday at 9am.',
    "Bulk schedule posts": 'Schedule my [5] drafts to go out one per day starting tomorrow.',
    "Create page": 'Create an About page with our story and team.',
    "Update page": 'Update my Contact page with the new phone number.',
    "Bulk find & replace": 'Replace "[old name]" with "[new name]" across every post.',
    "Insert in-article image": 'Add an image inside my post "[title]" near the [section].',
    "List / get posts & pages": 'Show me my 10 most recent posts.',
    "Revisions & restore": 'Roll "[title]" back to yesterday’s version.',
    "Site search": 'Search my site for posts about [keyword].',
    # Images & media
    "Generate featured image": 'Add a featured image to my latest post.',
    "Generate image (standalone)": 'Make an image of [a cup of coffee on a desk] and upload it.',
    "AI alt text": 'Write alt text for the images in my post "[title]".',
    "Fix missing alt text": 'Add alt text to all my images that are missing it.',
    "Bulk optimize images": 'Compress and optimize all the images in my media library.',
    "Upload from URL": 'Upload this image into my media library: [image URL].',
    "Set featured image": 'Set [that image] as the featured image on "[title]".',
    "Delete unused media": 'Find and delete images that aren’t used anywhere.',
    # SEO & meta
    "AI SEO Score": 'What’s my SEO score for "[post title]"?',
    "SEO audit post": 'Run a full SEO audit on "[title]" and fix what you can.',
    "Get / update post SEO": 'Set the SEO title and meta description for "[title]".',
    "Bulk generate meta": 'Write meta descriptions for every post that’s missing one.',
    "Fix missing excerpts": 'Generate excerpts for all posts that don’t have one.',
    "Find & replace meta": 'Update the SEO title template across my [category] posts.',
    "Audit SEO fields": 'Check my whole site for missing SEO titles and descriptions.',
    "Find thin content": 'Find posts that are too short to rank.',
    "Find duplicate titles": 'Find posts that have duplicate titles.',
    "Validate schema": 'Check the schema on "[title]" for errors.',
    "Update post schema": 'Add Article schema to "[title]" without changing the body.',
    "SEO backend info": 'Which SEO plugin is active on my site?',
    "Clean AIOSEO leftovers": 'Scan for and clean up leftover data from my old SEO plugin.',
    "Verify live meta": 'Confirm the meta description on "[title]" is actually live.',
    # AI search & GEO
    "GEO audit post": 'How quotable is "[title]" for ChatGPT and Perplexity?',
    "GEO optimize post": 'Optimize "[title]" so AI search engines cite it.',
    "Edit llms.txt": 'Update my llms.txt to guide AI crawlers.',
    "Ping search engines": 'Tell search engines my content just changed.',
    "Generate sitemap": 'Refresh my XML sitemap.',
    # Internal links & structure
    "Plan internal links": 'Plan internal links across my recent posts.',
    "Apply internal links plan": 'Apply the internal linking plan you just proposed.',
    "Bulk internal links": 'Add internal links across my recent posts.',
    "Suggest internal links": 'Suggest internal links for "[title]".',
    "Find orphan pages": 'Find pages with no internal links pointing to them.',
    "Find related posts": 'Find posts related to "[title]" I can link to.',
    "Check broken links": 'Scan my site for broken links.',
    "Create redirect": 'Redirect /old-url to /new-url.',
    "404 log": 'Show me the URLs visitors are hitting 404s on.',
    # Categories, tags & menus
    "Create / list categories": 'Create a category called "[name]".',
    "Create / list tags": 'Create a tag called "[name]".',
    "Bulk assign terms": 'Put all my [topic] posts into the "[category]" category.',
    "Bulk update category": 'Move every post from "[old category]" into "[new category]".',
    "Menus & menu items": 'Add "[Blog]" to my main navigation menu.',
    "Update permalinks": 'Change my permalinks to use the post name.',
    # Users, comments & authors
    "List / create users": 'Add a new editor named [Jane] to my site.',
    "Change user role": 'Change [Jane] from author to editor.',
    "Authors": 'Set [Jane] as the author of "[title]".',
    "Moderate comments": 'Approve the pending comments and trash the spam.',
    # Themes, plugins & files (Studio)
    "List / read theme & plugin files": 'Show me the contents of my theme’s functions.php.',
    "Write theme/plugin file": 'Add a code snippet to my theme (back it up first).',
    "Create plugin": 'Build a small plugin that [adds a reading-time badge to posts].',
    "Create theme": 'Create a new lightweight theme for my blog.',
    "Preview / activate / rollback theme": 'Switch my site to the "[theme]" theme.',
    "List / activate / deactivate plugins": 'Show my plugins and deactivate "[plugin]".',
    "Install plugin from repo": 'Install [Contact Form 7] from the WordPress directory.',
    "Custom CSS": 'Change my site’s heading color to [navy] with custom CSS.',
    "Edit robots.txt / .htaccess": 'Block crawlers from /wp-admin in my robots.txt.',
    # Backups, safety & site health
    "Full site backup": 'Take a full backup of my site.',
    "Restore site backup": 'Restore my site to [last night’s] backup.',
    "List studio backups": 'Show me my available restore points.',
    "Approval inbox": 'Show me actions waiting for my approval.',
    "Check site health": 'Run a health check on my site.',
    "Activity log": 'Show me everything the AI did on my site this week.',
    "Site & studio info": 'Tell me the key details about my site.',
    "WP options": 'Change my site tagline to "[new tagline]".',
}


def _tool_command(name):
    """Example 'Try:' command for a tool name (explicit, else a sensible generic)."""
    cmd = _TOOL_COMMANDS.get(name)
    if cmd:
        return cmd
    return f'Ask your AI: "{name.lower()}".'


# Flagship tools shown in the "most used" strip (proof of range, quick anchor).
_TOOL_FLAGSHIP = [
    ("Publish a full SEO article", "Write, image, optimize and publish in one go"),
    ("Generate a featured image", "Realistic AI image, set automatically"),
    ("Fix on-page SEO", "Meta, schema, internal links - site-wide"),
    ("Run the AI SEO Score", "On-Page, Technical, AEO, GEO in one score"),
    ("Bulk fix alt text", "AI-write missing alt text across all images"),
    ("Full-site backup & restore", "One-click restore point before big changes"),
    ("Create a 301 redirect", "Fix moved URLs and 404s"),
    ("Get cited by AI search", "Optimize posts for ChatGPT & Perplexity"),
]


def _tool_slug(name):
    import re
    return re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')


def tools_page():
    # `total` = curated items shown; `shown` = the marketing 100+ number (the
    # server actually exposes 110 raw tools; some are grouped here for readability).
    total = sum(len(items) for _, _, items in _TOOL_GROUPS)
    shown = "100"
    ncats = len(_TOOL_GROUPS)

    # Sticky jump-nav pills (category + count).
    nav_pills = "".join(
        f'<a href="#{_tool_slug(name)}" class=tnav-pill data-cat="{_tool_slug(name)}">'
        f'{name.replace(" & ", " &amp; ")} <b>{len(items)}</b></a>'
        for name, _sub, items in _TOOL_GROUPS)

    # Flagship "most used" strip.
    flag_html = "".join(
        f'<div class=tool-flag>{_CHECK}<div><b>{t}</b><span>{d}</span></div></div>'
        for t, d in _TOOL_FLAGSHIP)

    # Category sections - dense 3-col grid, verb-first names, one-line each.
    groups_html = ""
    for name, sub, items in _TOOL_GROUPS:
        slug = _tool_slug(name)
        cards = "".join(
            f'<div class=tool-item data-name="{t.lower()}" data-desc="{d.lower()}">'
            f'{_CHECK}<div><b>{t}</b><span>{d}</span></div></div>'
            for t, d in items)
        groups_html += (
            f'<section class=tool-group id="{slug}" data-cat="{slug}">'
            f'<div class=tool-group-head><h2>{name.replace(" & ", " &amp; ")}</h2>'
            f'<span class=tool-count>{len(items)} tools</span>'
            f'<p>{sub}</p></div>'
            f'<div class=tool-list>{cards}</div></section>')

    # At-a-glance count block (money element - quotable, AI-extractable).
    stat_block = (
        '<div class=tstats>'
        f'<div class=tstat><b>{shown}+</b><span>tools</span></div>'
        f'<div class=tstat><b>{ncats}</b><span>categories</span></div>'
        '<div class=tstat><b>0</b><span>go live without your approval</span></div>'
        '<div class=tstat><b>Claude + ChatGPT</b><span>your own AI, one connector</span></div>'
        '</div>')

    # Summary table (AEO: highly quotable "X tools across N categories").
    rows = "".join(
        f'<tr><td><a href="#{_tool_slug(name)}">{name.replace(" & ", " &amp; ")}</a></td>'
        f'<td>{len(items)}</td><td>{", ".join(t for t, _ in items[:3])}</td></tr>'
        for name, _sub, items in _TOOL_GROUPS)
    summary_table = (
        '<table class=tsummary><thead><tr><th>Category</th><th>Tools</th>'
        '<th>Examples</th></tr></thead><tbody>' + rows + '</tbody></table>')

    # Catalog-specific FAQ (different from /features FAQ - inventory-flavored).
    faqs = [
        ("How many tools does wptaskify have?",
         f"wptaskify gives your AI {shown}+ WordPress tools across {ncats} categories: content and publishing, images and media, SEO and meta, AI search and GEO, internal links, taxonomy and menus, users and comments, themes and plugins, and backups and site health."),
        ("Do I get all the tools on the free plan?",
         "Yes. Every plan - including the free one - unlocks all 100+ tools. Paid plans raise your monthly limits on AI actions and images, not which tools you can use."),
        ("Does wptaskify support redirects, alt text, backups and llms.txt?",
         "Yes. It can create 301 redirects, AI-write missing alt text in bulk, take full-site backups with one-click restore, and edit robots.txt, llms.txt and .htaccess - among 100+ tools."),
        ("Do I need to learn how to use each tool?",
         "No. You just ask your own Claude or ChatGPT in plain English - it picks the right tool and runs it, and nothing changes or publishes without your approval."),
    ]
    faq_html = "".join(
        f'<details class="faq-item"><summary>{q}</summary><p>{a}</p></details>'
        for q, a in faqs)

    body = f"""
<p>wptaskify gives your own Claude or ChatGPT <b>{shown}+ real WordPress tools</b> across {ncats} categories - content, images, SEO, GEO, internal links, taxonomy, users, themes, plugins and backups. Each one runs from a single plain-English message, and nothing goes live without your approval. Want the why instead of the what? <a href="/features">See features -&gt;</a></p>

{stat_block}

<div class=tsearch-wrap>
<input type=text id=tsearch class=tsearch autocomplete=off placeholder="Search {shown}+ tools (try 'redirects', 'alt text', 'backup')">
<span id=tsearch-count class=tsearch-count></span>
</div>

<nav class=tnav aria-label="Tool categories">{nav_pills}</nav>

<h2 class=tsec-h>Most used</h2>
<div class=tool-list tool-flags>{flag_html}</div>

<div class=tools-wrap>{groups_html}</div>
<p id=tsearch-empty class=tsearch-empty hidden>No tools match your search. Try another word, or <a href="/features">see features</a>.</p>

<div class=tsafe>Every tool asks before it changes or publishes anything. Bring your own AI. AES-256 encrypted.</div>

<div class=fcta>
<h3>Found the tool you need?</h3>
<p class=fcta-sub>Connect your WordPress site free and try it with your own Claude or ChatGPT.</p>
<a href="/?signup" class="btn btn-primary">Connect my site free</a>
<p class=fcta-fine>All 100+ tools on every plan. Nothing goes live without your approval.</p>
</div>

<h2 class=tsec-h>At a glance</h2>
{summary_table}

<h2 class=tsec-h>Tools FAQ</h2>
<div class=faq>{faq_html}</div>

<style>
.tstats{{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin:28px 0 8px}}
.tstat{{background:#FFFFFF;border:1px solid #E9E8EF;border-radius:16px;padding:20px 14px;text-align:center;
  box-shadow:0 8px 30px -18px rgba(20,19,26,.12)}}
.tstat b{{display:block;font-family:'Sora';font-weight:800;font-size:1.5rem;color:var(--accent);line-height:1.15}}
.tstat span{{display:block;color:#5B5966;font-size:.82rem;margin-top:6px;line-height:1.3}}
.tsearch-wrap{{position:relative;max-width:620px;margin:34px auto 0}}
.tsearch{{width:100%;padding:15px 18px;border:1px solid #E0DEE8;border-radius:14px;font-size:1rem;
  font-family:'Inter';background:#fff;color:#14131A;outline:none;transition:border-color .15s,box-shadow .15s}}
.tsearch:focus{{border-color:var(--accent);box-shadow:0 0 0 3px rgba(249,115,22,.12)}}
.tsearch-count{{display:block;text-align:center;color:#8A8792;font-size:.85rem;margin-top:8px;min-height:1em}}
.tnav{{position:sticky;top:0;z-index:20;display:flex;flex-wrap:wrap;gap:8px;justify-content:center;
  padding:14px 0;margin:14px 0 8px;background:rgba(255,255,255,.86);backdrop-filter:blur(8px)}}
.tnav-pill{{font-size:.82rem;font-weight:600;color:#5B5966!important;background:#F3F1F7;border:1px solid #E9E8EF;
  padding:6px 12px;border-radius:999px;text-decoration:none;transition:all .15s;white-space:nowrap}}
.tnav-pill b{{color:var(--accent);font-family:'Sora'}}
.tnav-pill:hover{{border-color:rgba(249,115,22,.4)}}
.tnav-pill.active{{background:var(--accent);color:#fff!important;border-color:var(--accent)}}
.tnav-pill.active b{{color:#fff}}
.tsec-h{{margin-top:52px!important}}
.tool-flags{{margin-bottom:8px}}
.tool-flag{{display:flex;gap:11px;align-items:flex-start;background:linear-gradient(180deg,#fff8f3,#fff);
  border:1px solid rgba(249,115,22,.25);border-radius:14px;padding:15px 16px}}
.tool-flag svg{{color:var(--accent);flex-shrink:0;margin-top:2px}}
.tool-flag b{{display:block;color:#14131A;font-size:.98rem;font-weight:600;font-family:'Sora'}}
.tool-flag span{{display:block;color:#5B5966;font-size:.88rem;line-height:1.45;margin-top:2px}}
.tools-wrap{{margin:8px 0 0}}
.tool-group{{margin:0 0 34px;scroll-margin-top:70px}}
.tool-group-head{{margin-bottom:16px;padding-left:14px;border-left:3px solid var(--accent)}}
.tool-group-head h2{{font-size:1.3rem!important;margin:0 0 2px!important;display:block!important;text-align:left!important}}
.tool-group-head h2::after{{display:none!important}}
.tool-count{{display:inline-block;font-size:.72rem;font-weight:700;font-family:'Sora';
  letter-spacing:.04em;color:var(--accent-hi);background:var(--accent-dim);padding:2px 9px;border-radius:999px}}
.tool-group-head p{{margin:6px 0 0;color:#5B5966;font-size:.95rem}}
.tool-list{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}}
.tool-item{{display:flex;gap:11px;align-items:flex-start;background:#FFFFFF;
  border:1px solid #E9E8EF;border-radius:14px;padding:14px 15px}}
.tool-item svg{{color:var(--accent);flex-shrink:0;margin-top:2px}}
.tool-item b{{display:block;color:#14131A;font-size:.95rem;font-weight:600;font-family:'Sora'}}
.tool-item span{{display:block;color:#5B5966;font-size:.86rem;line-height:1.45;margin-top:2px}}
.tool-item.hide{{display:none}}
.tsummary{{width:100%;border-collapse:collapse;margin-top:20px;font-size:.92rem}}
.tsummary th,.tsummary td{{text-align:left;padding:11px 14px;border-bottom:1px solid #E9E8EF}}
.tsummary th{{font-family:'Sora';color:#14131A;font-size:.85rem;text-transform:uppercase;letter-spacing:.04em}}
.tsummary td{{color:#5B5966}}
.tsummary td a{{color:var(--accent)!important;font-weight:600}}
.tsafe{{text-align:center;color:#8A8792;font-size:.9rem;margin:26px auto 0;max-width:60ch}}
.tsearch-empty{{text-align:center;color:#8A8792;margin:20px 0}}
@media(max-width:960px){{.tool-list{{grid-template-columns:1fr 1fr}}.tstats{{grid-template-columns:1fr 1fr}}}}
@media(max-width:600px){{.tool-list,.tstats{{grid-template-columns:1fr}}.tsummary td:nth-child(3){{display:none}}}}
</style>
<script>
(function(){{
  var q=document.getElementById('tsearch'), cnt=document.getElementById('tsearch-count'),
      empty=document.getElementById('tsearch-empty'),
      items=[].slice.call(document.querySelectorAll('.tool-item')),
      groups=[].slice.call(document.querySelectorAll('.tool-group'));
  if(q){{
    q.addEventListener('input',function(){{
      var v=q.value.trim().toLowerCase(), n=0;
      items.forEach(function(it){{
        var m=!v||it.dataset.name.indexOf(v)>-1||it.dataset.desc.indexOf(v)>-1;
        it.classList.toggle('hide',!m); if(m)n++;
      }});
      groups.forEach(function(g){{
        var any=g.querySelectorAll('.tool-item:not(.hide)').length;
        g.style.display=any?'':'none';
      }});
      cnt.textContent=v?(n+' tool'+(n===1?'':'s')+' match "'+q.value.trim()+'"'):'';
      empty.hidden=!(v&&n===0);
    }});
  }}
  // sticky nav active-state on scroll
  var pills=[].slice.call(document.querySelectorAll('.tnav-pill'));
  if('IntersectionObserver' in window && pills.length){{
    var byCat={{}}; pills.forEach(function(p){{byCat[p.dataset.cat]=p;}});
    var io=new IntersectionObserver(function(es){{
      es.forEach(function(e){{
        if(e.isIntersecting){{
          pills.forEach(function(p){{p.classList.remove('active');}});
          var a=byCat[e.target.dataset.cat]; if(a)a.classList.add('active');
        }}
      }});
    }},{{rootMargin:'-45% 0px -50% 0px'}});
    groups.forEach(function(g){{io.observe(g);}});
  }}
}})();
</script>
"""
    # Schema: ItemList (all tools) + SoftwareApplication.featureList + FAQPage.
    li = []
    pos = 1
    for _n, _s, items in _TOOL_GROUPS:
        for t, d in items:
            li.append('{"@type":"ListItem","position":' + str(pos) +
                      ',"name":"' + t.replace('"', "'").replace("&", "and") +
                      '","description":"' + d.replace('"', "'") + '"}')
            pos += 1
    feat_list = ",".join(
        '"' + t.replace('"', "'").replace("&", "and") + '"'
        for _n, _s, items in _TOOL_GROUPS for t, _d in items)
    faq_items = ",".join(
        '{"@type":"Question","name":"' + q.replace('"', "'") +
        '","acceptedAnswer":{"@type":"Answer","text":"' + a.replace('"', "'") + '"}}'
        for q, a in faqs)
    # Only /faq carries FAQPage schema (canonical). Tools keeps ItemList + SoftwareApplication;
    # its mini-FAQ is visual-only to avoid duplicate-FAQPage dilution.
    schema = ('{"@context":"https://schema.org","@graph":['
              '{"@type":"ItemList","name":"wptaskify WordPress AI tools",'
              '"description":"' + shown + '+ WordPress tools wptaskify gives Claude and ChatGPT across '
              + str(ncats) + ' categories.","numberOfItems":' + str(total) +
              ',"itemListElement":[' + ",".join(li) + ']},'
              '{"@type":"SoftwareApplication","name":"wptaskify","applicationCategory":"BusinessApplication",'
              '"operatingSystem":"WordPress","offers":{"@type":"Offer","price":"0","priceCurrency":"USD"},'
              '"featureList":[' + feat_list + ']}]}')
    return _content_page(
        "All tools",
        f"The full list of {shown}+ WordPress tools wptaskify gives your AI across {ncats} categories - content, SEO, GEO, images, internal links, themes, plugins and backups. All tools on every plan.",
        body, canonical="/tools", schema_json=schema, wide=True,
        hero_img=f"{SITE_BASE}/assets/hero-tools.webp",
        hero_sub=f"{shown}+ tools your AI can run on your WordPress site - all on every plan.",
        keywords="wordpress ai tools, wptaskify tools list, ai wordpress tool list, what can ai do on wordpress, claude wordpress tools, chatgpt wordpress tools")


def login_page(error="", authorize_next=""):
    return _auth("login", error, authorize_next)


# ---------------------------------------------------------------------------
# Email verify + password reset pages
# ---------------------------------------------------------------------------
def verify_sent_page(email="", resent=False, toofast=False):
    if toofast:
        note = ('<div class="alert err" style="margin-bottom:18px">You\'ve requested this a '
                'few times already. Please wait a few minutes before resending.</div>')
    elif resent:
        note = ('<div class="alert ok" style="margin-bottom:18px">Verification email re-sent.</div>')
    else:
        note = ''
    to = f' to <strong>{_e_html(email)}</strong>' if email else ''
    return _head(f"Verify your email - {BRAND}") + f"""
<div class=auth-wrap><div class=auth-card>
{_logo()}
<h1>Check your email</h1>
<p class=sub>We've sent a verification link{to}. Click it to activate your account and open your dashboard.</p>
{note}
<form method=post action=/verify-resend style=margin-top:8px>
<button class="btn btn-primary btn-block btn-lg" type=submit>Resend email</button></form>
<div class=auth-alt><a href="/login">Back to login</a></div>
</div></div></body></html>"""


def checkout_confirm_page(plan_key, label, sym, amount, tax=0, total=None, rate=0,
                          welcome_pct=0, discounted=None):
    """Review-and-pay page: shown after signup+verify OR when a logged-in user picks a
    paid plan. Shows the GST breakdown and a coupon box that live-recalculates the total
    before the user is sent to Razorpay. `amount` = base (pre-coupon) list price.
    welcome_pct>0 = an auto first-month discount is pre-applied (discounted = the price
    after that % off, before GST)."""
    total = amount if total is None else total
    rate_disp = rate if rate else 0
    has_welcome = welcome_pct and discounted is not None and discounted < amount
    welcome_off = (amount - discounted) if has_welcome else 0
    # Welcome banner + pre-shown discount row.
    welcome_banner = (
        f'<div class=co-welcome>🎉 <strong>First-month offer:</strong> '
        f'{welcome_pct:.0f}% off your first month applied automatically.</div>'
        if has_welcome else '')
    disc_style = ("display:flex;color:var(--accent-hi)" if has_welcome
                  else "display:none;color:var(--accent-hi)")
    disc_label = (f"First month {welcome_pct:.0f}% off" if has_welcome else "Discount")
    return _head(f"Complete your purchase - {BRAND}") + f"""
{_nav("none")}
<div class=auth-wrap><div class=auth-card>
<h1>Review &amp; pay 🎉</h1>
<p class=sub>Complete your <strong>{label}</strong> subscription to unlock your monthly limits.
You can cancel any time.</p>
{welcome_banner}

<div class=co-lines>
  <div class=co-line><span>{label} plan</span><span id=co-base>{sym}{amount:,.0f}</span></div>
  <div class=co-line id=co-disc-row style="{disc_style}">
    <span id=co-disc-label>{disc_label}</span><span id=co-disc>-{sym}{welcome_off:,.0f}</span></div>
  <div class=co-line id=co-gst-row {'style=display:none' if not tax else ''}>
    <span>GST (<span id=co-rate>{rate_disp:.0f}</span>%)</span><span id=co-gst>{sym}{tax:,.0f}</span></div>
  <div class="co-line co-total"><span>Total</span><span id=co-total>{sym}{total:,.0f}/mo</span></div>
</div>
{'<p class=co-renew-note>After the first month it renews at ' + f'{sym}{amount:,.0f}/mo.</p>' if has_welcome else ''}

<div class=cpn-box>
  <input id=cpn-in type=text placeholder="Have another code? (optional)" autocomplete=off
    oninput="this.value=this.value.toUpperCase()">
  <button type=button id=cpn-btn class="btn btn-ghost">Apply</button>
</div>
<div id=cpn-msg class=cpn-msg></div>

<form method=post action=/checkout style="margin:0" id=pay-form>
  <input type=hidden name=plan value="{plan_key}">
  <input type=hidden name=recurring value="1">
  <input type=hidden name=coupon id=cpn-hidden value="">
  <input type=hidden name=fp id=fp-hidden value="">
  <button class="btn btn-primary btn-block btn-lg" type=submit id=pay-btn>Pay {sym}{total:,.0f} &amp; activate</button>
</form>
<div class=auth-alt><a href="/dashboard">Skip for now - stay on Free</a></div>

<style>
.co-lines{{background:var(--surface2);border:1px solid var(--border);border-radius:14px;
padding:16px 18px;margin:8px 0 14px}}
.co-line{{display:flex;justify-content:space-between;padding:7px 0;color:var(--muted);font-size:.95rem}}
.co-total{{border-top:1px solid var(--border-hi);margin-top:6px;padding-top:12px;
color:var(--fg);font-weight:800;font-family:'Sora';font-size:1.15rem}}
.cpn-box{{display:flex;gap:10px;margin:0 0 6px}}
.cpn-box input{{flex:1;padding:11px 14px;border:1px solid var(--border-hi);border-radius:10px;
background:var(--surface2);color:var(--fg);font-size:.95rem;text-transform:uppercase}}
.cpn-box input:focus{{border-color:var(--accent);outline:none}}
.cpn-box .btn{{padding:11px 20px;white-space:nowrap}}
.cpn-msg{{font-size:.85rem;min-height:18px;margin-bottom:14px}}
.cpn-msg.ok{{color:var(--accent-hi)}}
.cpn-msg.err{{color:#ef4444}}
.co-welcome{{background:var(--accent-dim);border:1px solid rgba(249,115,22,.3);
border-radius:12px;padding:11px 14px;margin:4px 0 12px;font-size:.9rem;color:var(--fg)}}
.co-renew-note{{font-size:.8rem;color:var(--muted);margin:-6px 0 14px;text-align:center}}
</style>
<script>
(function(){{
  var plan="{plan_key}", sym="{sym}";
  var inEl=document.getElementById('cpn-in'), btn=document.getElementById('cpn-btn');
  var msg=document.getElementById('cpn-msg'), hidden=document.getElementById('cpn-hidden');
  // Device fingerprint (abuse-tracking for the first-month welcome discount). A stable
  // hash of coarse, non-PII browser signals - survives cookie/email changes on the same
  // device without identifying the person. Best-effort; the server also checks IP + user.
  try {{
    var fp=[navigator.userAgent, navigator.language, screen.width+'x'+screen.height,
            screen.colorDepth, new Date().getTimezoneOffset(),
            navigator.hardwareConcurrency||0, navigator.platform||''];
    try {{
      var c=document.createElement('canvas'), x=c.getContext('2d');
      x.textBaseline='top'; x.font="14px Arial"; x.fillText('wptaskify-fp',2,2);
      fp.push(c.toDataURL().slice(-64));
    }} catch(e){{}}
    var str=fp.join('|'), h=5381;
    for(var i=0;i<str.length;i++){{h=((h<<5)+h+str.charCodeAt(i))>>>0;}}
    var el=document.getElementById('fp-hidden'); if(el) el.value=h.toString(16);
  }} catch(e){{}}
  function money(n){{return sym+Math.round(n).toLocaleString();}}
  function apply(){{
    var code=(inEl.value||'').trim();
    if(!code){{msg.className='cpn-msg';msg.textContent='';return;}}
    btn.disabled=true;btn.textContent='...';
    fetch('/coupon-preview?plan='+encodeURIComponent(plan)+'&code='+encodeURIComponent(code))
      .then(function(r){{return r.json();}})
      .then(function(d){{
        btn.disabled=false;btn.textContent='Apply';
        if(!d.ok){{
          msg.className='cpn-msg err';msg.textContent=d.error||'Invalid code';
          hidden.value='';
          document.getElementById('co-disc-row').style.display='none';
          return;
        }}
        hidden.value=code;
        msg.className='cpn-msg ok';msg.textContent='Coupon applied ✓';
        document.getElementById('co-base').textContent=money(d.list);
        var dr=document.getElementById('co-disc-row');
        document.getElementById('co-disc').textContent='-'+money(d.list-d.base);
        dr.style.display=(d.list-d.base>0)?'flex':'none';
        var gr=document.getElementById('co-gst-row');
        if(d.tax>0){{gr.style.display='flex';
          document.getElementById('co-rate').textContent=Math.round(d.rate);
          document.getElementById('co-gst').textContent=money(d.tax);}}
        else{{gr.style.display='none';}}
        document.getElementById('co-total').textContent=money(d.total)+'/mo';
        document.getElementById('pay-btn').innerHTML='Pay '+money(d.total)+' &amp; activate';
      }})
      .catch(function(){{btn.disabled=false;btn.textContent='Apply';
        msg.className='cpn-msg err';msg.textContent='Could not check code, try again';}});
  }}
  btn.addEventListener('click',apply);
  inEl.addEventListener('keydown',function(e){{if(e.key==='Enter'){{e.preventDefault();apply();}}}});
}})();
</script>
</div></div></body></html>"""


def connect_error_page(site="", message=""):
    """Shown when the one-click connect from the plugin fails validation.
    Honest failure - never pretend the site was connected."""
    body = _e_html(message or "We couldn't verify the connection.").replace("\n", "<br>")
    site_line = f'<p class=sub style="word-break:break-all">{_e_html(site)}</p>' if site else ''
    return _head(f"Connection failed - {BRAND}") + f"""
<div class=auth-wrap><div class=auth-card>
{_logo()}
<h1>Couldn't connect your site</h1>
{site_line}
<div class="alert err" style="margin:16px 0;text-align:left;line-height:1.55">{body}</div>
<div class=auth-alt><a href="/dashboard">Back to dashboard</a></div>
</div></div></body></html>"""


def forgot_page(error=""):
    err = f'<div class="alert err">{_e_html(error)}</div>' if error else ''
    return _head(f"Reset password - {BRAND}") + f"""
<div class=auth-wrap><div class=auth-card>
{_logo()}
<h1>Reset your password</h1>
<p class=sub>Enter your email and we'll send you a reset link.</p>
{err}
<form method=post action=/forgot>
<div class=field><label for=email>Email</label>
<input id=email name=email type=email placeholder="you@example.com" autocomplete=email required></div>
<button class="btn btn-primary btn-block btn-lg" type=submit>Send reset link</button>
</form>
<div class=auth-alt><a href="/login">Back to login</a></div>
</div></div></body></html>"""


def reset_page(token, error=""):
    err = f'<div class="alert err">{_e_html(error)}</div>' if error else ''
    return _head(f"Set a new password - {BRAND}") + f"""
<div class=auth-wrap><div class=auth-card>
{_logo()}
<h1>Set a new password</h1>
<p class=sub>Choose a new password for your account.</p>
{err}
<form method=post action=/reset>
<input type=hidden name=token value="{_e_html(token)}">
<div class=field><label for=password>New password</label>
<input id=password name=password type=password placeholder="••••••••" autocomplete=new-password minlength=8 required></div>
<button class="btn btn-primary btn-block btn-lg" type=submit>Update password</button>
</form>
</div></div></body></html>"""


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
def _plan_section(plan, account, toolcall_account, token_account,
                  credits, plan_max, has_key, country, txns, chat_enabled, usage=None):
    """The full Plan & Usage module for the dashboard: current plan, usage bars,
    all plans + upgrade, credit top-ups, and transaction history."""
    usage = usage or {}
    is_india = (country or "").upper() == "IN"
    cur = "₹" if is_india else "$"
    plan_names = {"free": "Free", "owai_mini": "Mini", "owai_starter": "Starter",
                  "owai_pro": "Pro", "chat_starter": "Chat Starter",
                  "chat_pro": "Chat Pro", "chat_max": "Chat Max",
                  "pro": "Pro", "agency": "Agency"}
    pretty = plan_names.get(plan, plan.title())

    # ---- usage bars ----
    ta = toolcall_account or {}
    tc_left, tc_max = ta.get("tool_calls", 0), ta.get("tool_calls_max", 0)
    if tc_max >= 1_000_000:
        actions_bar = ('<div class=use-row><div class=use-label>AI actions</div>'
                       '<div class=use-val>Unlimited</div></div>'
                       '<div class=use-track><div class=use-fill style="width:100%"></div></div>')
    else:
        pct = int(min(tc_left, tc_max) / tc_max * 100) if tc_max else 0
        actions_bar = (f'<div class=use-row><div class=use-label>AI actions</div>'
                       f'<div class=use-val>{tc_left:,} <small>/ {tc_max:,}</small></div></div>'
                       f'<div class=use-track><div class=use-fill style="width:{pct}%"></div></div>')
    ipct = int(min(credits, plan_max) / plan_max * 100) if plan_max else 0
    img_bar = (f'<div class=use-row><div class=use-label>AI images</div>'
               f'<div class=use-val>{credits} <small>/ {plan_max}</small></div></div>'
               f'<div class=use-track><div class=use-fill style="width:{ipct}%"></div></div>')

    # ---- all plans (geo-aware) ----
    # (key, name, USD, INR, who, [sites, actions, images, support])
    plans = [
        ("", "Free", "$0", "₹0", "For getting started",
         ["1 site", "100 AI actions", "5 AI images", "Community support"]),
    ]
    # Mini is India-only for NEW purchases, but always show it if the user is already on
    # it (so a Mini customer viewing from abroad still sees & manages their current plan).
    if is_india or plan == "owai_mini":
        plans.append(("owai_mini", "Mini", "$9", "₹700", "For a single blog",
                      ["1 site", "800 AI actions", "25 AI images", "Email support"]))
    plans += [
        ("owai_starter", "Starter", "$20", "₹1,699", "For an active site",
         ["2 sites", "2,000 AI actions", "60 AI images", "Priority support"]),
        ("owai_pro", "Pro", "$99", "₹8,299", "For pros & agencies",
         ["10 sites", "Unlimited AI actions", "200 AI images", "White-glove onboarding"]),
    ]
    order = [p[0] for p in plans]
    cur_idx = order.index(plan) if plan in order else -1

    cards = ""
    for i, (key, name, usd, inr, who, feats) in enumerate(plans):
        amt = inr if is_india else usd
        current = (key == plan) or (key == "" and plan == "free")
        featured = (name == "Starter")
        lis = "".join(f'<li>{_CHECK} {f}</li>' for f in feats)
        if current:
            btn = '<span class="btn btn-ghost btn-block" style="cursor:default;opacity:.7">Current plan</span>'
        elif key and (cur_idx == -1 or i > cur_idx):
            # Go to the review/checkout page first (amount + GST + coupon), not straight to Razorpay.
            btn = (f'<a class="btn btn-primary btn-block" href="/checkout-after?plan={key}">'
                   f'Upgrade to {name}</a>')
        elif key:
            btn = (f'<a class="btn btn-ghost btn-block" href="/checkout-after?plan={key}">'
                   f'Switch to {name}</a>')
        else:
            btn = '<span class="btn btn-ghost btn-block" style="cursor:default;opacity:.5">Free</span>'
        cls = "plan-c featured" if featured else "plan-c"
        cls += " current" if current else ""
        tag = '<div class=plan-tag>Most popular</div>' if featured else ''
        cur_tag = '<div class="plan-tag cur">Your plan</div>' if current else ''
        cards += (f'<div class="{cls}">{tag or cur_tag}<h4>{name}</h4>'
                  f'<div class=plan-price>{amt}<span>/mo</span></div>'
                  f'<p class=plan-who>{who}</p><ul>{lis}</ul>{btn}</div>')
    cols = "cols4" if len(plans) >= 4 else "cols3"

    # ---- credit top-ups (geo-aware: INR for India, USD for others) ----
    if is_india:
        img_packs = [("img_100", "100 AI images", "₹699"), ("img_300", "300 AI images", "₹1,699"),
                     ("img_500", "500 AI images", "₹2,699")]
    else:
        img_packs = [("img_100", "100 AI images", "$8"), ("img_300", "300 AI images", "$20"),
                     ("img_500", "500 AI images", "$30")]
    pack_cards = "".join(
        f'<form method=post action=/topup class=pack><input type=hidden name=pack value="{pid}">'
        f'<div class=pack-name>{label}</div><div class=pack-price>{price}</div>'
        f'<button class="btn btn-ghost btn-block">Buy</button></form>'
        for pid, label, price in img_packs)

    # ---- transaction history ----
    def _tsym(t):
        return "₹" if t.get("currency", "INR") == "INR" else "$"
    rows = "".join(
        f'<tr><td>{t["created_at"][:10]}</td><td>{_e_html(t.get("item",""))}</td>'
        f'<td>{_tsym(t)}{t.get("amount_usd",0):.0f}</td>'
        f'<td><span class="pill {"ok" if t.get("status")=="completed" else ""}">{_e_html(t.get("status",""))}</span></td></tr>'
        for t in txns) or ('<tr><td colspan=4 style="color:var(--muted2);text-align:center;'
                           'padding:18px">No transactions yet</td></tr>')

    # ---- renewal / expiry line ----
    sub_status = usage.get("sub_status", "none")
    renews_at = usage.get("renews_at")
    resets_on = usage.get("resets_on", "the 1st")
    csrf = usage.get("csrf", "")
    is_paid = plan not in ("", "free", "unlimited")
    # Cancel control - only for a paid, still-active subscription (not already canceled/unlimited).
    cancel_ctl = ""
    if is_paid and sub_status == "active":
        end_txt = f' Your plan stays active until <strong>{renews_at[:10]}</strong>.' if renews_at else ''
        cancel_ctl = (
            f'<form method=post action=/cancel-plan style="margin-top:10px" '
            f'onsubmit="return confirm(\'Cancel your plan? You keep your current plan until '
            f'the end of the paid period, then move to Free. No further charges.\')">'
            f'<input type=hidden name=csrf value="{csrf}">'
            f'<button class="btn btn-ghost mini" type=submit '
            f'style="color:var(--muted2)">Cancel plan</button>'
            f'<span class=hint style="margin-left:8px">Cancel anytime.{end_txt}</span></form>')
    if plan == "free" or plan == "":
        renew_line = (f'You are on the free plan. Your monthly free allowance '
                      f'resets on <strong>{resets_on}</strong>.')
    elif sub_status == "canceled":
        renew_line = (f'<span class="pill">Canceled</span> Your plan will move to Free on '
                      f'<strong>{renews_at[:10] if renews_at else resets_on}</strong>. '
                      f'You can re-subscribe below any time.')
    elif sub_status == "expired":
        renew_line = 'Your paid plan has expired. Renew below to continue.'
    elif sub_status == "active" and renews_at:
        renew_line = (f'<span class="pill ok">Active</span> Your plan renews on '
                      f'<strong>{renews_at[:10]}</strong>. Allowance resets on <strong>{resets_on}</strong>.')
    elif sub_status == "active":
        renew_line = f'<span class="pill ok">Active</span> Your monthly allowance resets on <strong>{resets_on}</strong>.'
    else:
        renew_line = (f'Your current allowance resets on <strong>{resets_on}</strong>. '
                      f'Upgrade below for higher monthly limits.')
    renew_line += cancel_ctl

    # ---- usage breakdown (what you used this month) ----
    actions_used = usage.get("actions_used", 0)
    images_used = usage.get("images_used", 0)
    top = usage.get("top", [])
    if top:
        mxu = max((n for _, n in top), default=1)
        break_bars = "".join(
            f'<div class=ubk-row><span class=ubk-name>{_e_html(k)}</span>'
            f'<div class=ubk-track><div class=ubk-fill style="width:{max(4,int(n/mxu*100))}%"></div></div>'
            f'<span class=ubk-n>{n}</span></div>' for k, n in top)
    else:
        break_bars = '<p class=hint>No activity yet this month. Connect a site and ask your AI to get started.</p>'

    usage_panel = f"""
<div class=panel>
  <h2>Usage this month</h2>
  <p class=hint>What you've used since {resets_on.rsplit(' ',2)[0] if ' ' in resets_on else 'this month'} started - resets on <strong>{resets_on}</strong>.</p>
  <div class=usage-tot>
    <div class=ut><b>{actions_used:,}</b><span>AI actions used</span></div>
    <div class=ut><b>{images_used}</b><span>AI images used</span></div>
    <div class=ut><b>{len(txns)}</b><span>Payments</span></div>
  </div>
  <h3 class=ubk-h>Breakdown - what you ran</h3>
  <div class=ubk>{break_bars}</div>
</div>"""

    return f"""
<div class=panel>
  <div class=plan-head>
    <div><p class=plan-eyebrow>Current plan</p>
      <div class=plan-now><span class=plan-badge-lg>{pretty}</span></div></div>
    <div class=use-block>{actions_bar}{img_bar}</div>
  </div>
  <p class=hint style="margin:16px 0 0">{renew_line}</p>
</div>

{usage_panel}

<div class=panel>
  <h2>All plans</h2>
  <p class=hint>Every plan includes all {TOTAL_TOOLS}+ tools. Bring your own Claude or ChatGPT - no extra AI subscription.
  Have a discount code? Pick a plan below - you can apply it on the next step.</p>
  <div class="plan-grid {cols}">{cards}</div>
</div>

<div class=panel>
  <h2>Buy more AI images</h2>
  <p class=hint>One-time top-up if you run out before your monthly reset. Need bulk? Buy a pack more than once.</p>
  <div class=packs>{pack_cards}</div>
</div>

<div class=panel>
  <h2>Billing history</h2>
  <table class=txn><thead><tr><th>Date</th><th>Item</th><th>Amount</th><th>Status</th></tr></thead>
  <tbody>{rows}</tbody></table>
</div>
"""


def _e_html(x):
    import html as _h
    return _h.escape(str(x if x is not None else ""))


def _google_conn_card(title, subtitle, conn, public_url, csrf, site_id="", opts=None):
    """One Google-connection card. When connected, shows DROPDOWNS auto-populated
    with the account's real GA4 properties + Search Console sites (no manual typing),
    plus a list of what's available. `site_id` empty = account-level default."""
    sid_input = f'<input type=hidden name=site_id value="{_e_html(site_id)}">' if site_id else ""
    connect_href = f"{public_url}/google/connect" + (f"?site={_e_html(site_id)}" if site_id else "")
    if not conn or not conn.get("connected"):
        return (f'<div class="gconn">'
                f'<div class=gconn-head><b>{title}</b><span>{subtitle}</span></div>'
                f'<a class="btn btn-primary" href="{connect_href}">Connect Google</a>'
                f'</div>')
    email = _e_html(conn.get("google_email", ""))
    cur_prop = conn.get("ga_property_id", "")
    cur_scs = conn.get("sc_site", "")
    opts = opts or {}
    props = opts.get("properties", [])
    scsites = opts.get("sites", [])
    err = opts.get("error", "")

    def _field(label, name, items, cur, label_of, val_of, empty_msg):
        """Smart field: 0 items -> a note (no control); 1 item -> auto-selected,
        shown as read-only text + a hidden input (nothing to pick); 2+ -> dropdown."""
        n = len(items)
        if n == 0:
            return f'<div class=gfield><span class=glbl>{label}</span><span class=gnone>{empty_msg}</span></div>'
        if n == 1:
            it = items[0]
            v = val_of(it)
            return (f'<div class=gfield><span class=glbl>{label}</span>'
                    f'<span class=gone>{_e_html(label_of(it))}</span>'
                    f'<input type=hidden name={name} value="{_e_html(v)}"></div>')
        # 2+ -> dropdown
        o = '<option value="">— select —</option>' + "".join(
            f'<option value="{_e_html(val_of(it))}"'
            f'{" selected" if val_of(it)==cur else ""}>{_e_html(label_of(it))}</option>'
            for it in items)
        return (f'<label class=gfield><span class=glbl>{label}</span>'
                f'<select name={name}>{o}</select></label>')

    prop_field = _field(
        "GA4 property", "ga_property_id", props, cur_prop,
        lambda p: (p.get("display_name") or p["property_id"]) + f' ({p["property_id"]})',
        lambda p: p["property_id"],
        "No GA4 property found on this account." +
        (" (Enable the Google Analytics Admin API, then reconnect.)" if err else ""))
    scs_field = _field(
        "Search Console site", "sc_site", scsites, cur_scs,
        lambda s: s["site"], lambda s: s["site"],
        "No Search Console site found on this account." +
        (" (Enable the Search Console API, then reconnect.)" if err else ""))

    err_html = f'<p class=gconn-err>{_e_html(err)}</p>' if err else ""
    # Only show Save when there's an actual choice to make (a dropdown present).
    has_dropdown = len(props) > 1 or len(scsites) > 1
    save_btn = '<button class="btn" type=submit>Save selection</button>' if has_dropdown else ''

    return (
        f'<div class="gconn">'
        f'<div class=gconn-head><b>{title}</b> <span class="pill ok">connected</span>'
        f'<span>{subtitle} · {email}</span></div>'
        f'{err_html}'
        f'<form method=post action="{public_url}/google/select" class=gconn-form>'
        f'<input type=hidden name=csrf value="{csrf}">{sid_input}'
        f'{prop_field}{scs_field}{save_btn}</form>'
        f'<form method=post action="{public_url}/google/disconnect" style="margin-top:8px">'
        f'<input type=hidden name=csrf value="{csrf}">{sid_input}'
        f'<button class="btn btn-ghost" type=submit>Disconnect</button></form>'
        f'</div>')


def _google_section(google, public_url, csrf="", configured=True, sites=None,
                    google_all=None, google_opts=None):
    """Google Analytics + Search Console. Per-SITE Google accounts (each WordPress
    site can connect a different Gmail), an account-level default, auto-populated
    property/site dropdowns, and an 'add another account' option."""
    if not configured:
        return """
<div class=panel>
  <h2>Google Analytics</h2>
  <p class=hint>Analytics connection isn't available yet. Please check back soon.</p>
</div>"""
    sites = sites or []
    google_all = google_all or []
    google_opts = google_opts or {}
    by_site = {}
    default_conn = None
    for a in google_all:
        if a.get("site_id"):
            by_site[a["site_id"]] = {"connected": True, **a}
        else:
            default_conn = {"connected": True, **a}
    if default_conn is None:
        default_conn = google or {"connected": False}

    cards = _google_conn_card(
        "Account default", "Used for any site without its own Google account",
        default_conn, public_url, csrf, site_id="", opts=google_opts.get(""))

    site_cards = ""
    for s in sites:
        if s.get("status", "active") != "active":
            continue
        sid = s.get("id", "")
        url = _e_html(s.get("site_url", ""))
        site_cards += _google_conn_card(
            url or "This site", "Its own Google / Search Console account",
            by_site.get(sid), public_url, csrf, site_id=sid, opts=google_opts.get(sid))

    # "Add another Google account" (re-runs consent so a different Gmail can be picked).
    add_btn = (f'<a class="btn btn-ghost" href="{public_url}/google/connect">'
               f'+ Add another Google account</a>')

    return f"""
<div class=panel>
  <h2>Google Analytics &amp; Search Console</h2>
  <p class=hint>Connect Google so your AI can review your real traffic, top pages and
  search queries (read-only). Your GA4 properties and Search Console sites load
  automatically - just pick them from the dropdowns. If a site's Search Console is on
  a different Google account, connect that account on the site's own card below.</p>
  <div class=gconn-grid>
    {cards}
    {site_cards}
  </div>
  <div style="margin-top:14px">{add_btn}</div>
  <p class=hint style="margin-top:12px">Then ask your AI: "how's my traffic this
  month?", "top 10 pages", or "which search queries bring clicks?"</p>
</div>
<style>
.gconn-grid{{display:grid;gap:14px;margin-top:12px}}
.gconn{{border:1px solid var(--border);border-radius:12px;padding:16px 18px;background:var(--surface)}}
.gconn-head{{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:8px}}
.gconn-head span{{color:var(--muted2);font-size:.85rem}}
.gconn-err{{font-size:.82rem;color:#B23A28;background:#FEF6F4;border:1px solid #F6D9D1;
  padding:8px 10px;border-radius:8px;margin:4px 0 10px}}
.gconn-form{{display:flex;gap:14px;flex-wrap:wrap;align-items:flex-end;margin:6px 0}}
.gfield{{display:flex;flex-direction:column;gap:5px}}
.glbl{{font-size:.8rem;color:var(--muted2);font-weight:600}}
.gfield select{{min-width:220px;padding:8px 10px;border:1px solid var(--border);border-radius:8px}}
.gone{{font-weight:600;color:var(--fg,#14131A);font-size:.95rem}}
.gnone{{color:var(--muted);font-size:.9rem}}
</style>"""


def _settings_section(profile):
    """User self-service Settings: profile, email, password, notifications, delete."""
    p = profile or {}
    name = _e_html(p.get("name", ""))
    em = _e_html(p.get("email", ""))
    verified = p.get("verified", True)
    notify = p.get("notify_email", True)
    gstin = _e_html(p.get("gstin", ""))
    vpill = ('<span class="pill ok">verified</span>' if verified
             else '<span class="pill">unverified</span>')
    notify_lbl = "on" if notify else "off"
    return f"""
<div class=panel>
  <h2>Profile</h2>
  <p class=hint>Your display name is used to greet you in the dashboard.</p>
  <form method=post action=/settings/name class=set-form>
    <div class=field><label for=nm>Name</label>
    <input id=nm name=name value="{name}" placeholder="Your name" maxlength=80></div>
    <button class="btn btn-primary" type=submit>Save name</button>
  </form>
</div>

<div class=panel>
  <h2>Email address {vpill}</h2>
  <p class=hint>Current: <strong>{em}</strong>. Changing it will require you to verify the new address.</p>
  <form method=post action=/settings/email class=set-form>
    <div class=field><label for=nem>New email</label>
    <input id=nem name=email type=email placeholder="new@email.com" autocomplete=email required></div>
    <div class=field><label for=ep>Confirm current password</label>
    <input id=ep name=password type=password placeholder="Your current password" autocomplete=current-password required></div>
    <button class="btn btn-primary" type=submit>Change email</button>
  </form>
</div>

<div class=panel>
  <h2>Password</h2>
  <p class=hint>Choose a new password (at least 8 characters).</p>
  <form method=post action=/settings/password class=set-form>
    <div class=field><label for=cp>Current password</label>
    <input id=cp name=current type=password autocomplete=current-password required></div>
    <div class=field><label for=np>New password</label>
    <input id=np name=new type=password minlength=8 autocomplete=new-password required></div>
    <button class="btn btn-primary" type=submit>Update password</button>
  </form>
</div>

<div class=panel>
  <h2>GST / Tax details <span class=muted style="font-weight:400;font-size:.85rem">(India, optional)</span></h2>
  <p class=hint>Registered for GST? Add your GSTIN to claim input tax credit - it will appear on
  your invoices. GST (18%) applies to payments made in India.</p>
  <form method=post action=/settings/gstin class=set-form>
    <div class=field><label for=gst>GSTIN</label>
    <input id=gst name=gstin value="{gstin}" placeholder="22AAAAA0000A1Z5" maxlength=15
      style="text-transform:uppercase" autocomplete=off></div>
    <button class="btn btn-primary" type=submit>Save GSTIN</button>
  </form>
</div>

<div class=panel>
  <h2>Email notifications</h2>
  <p class=hint>Get emails for important events: low image credits, plan renewal reminders,
  payment receipts and site updates. Currently <strong>{notify_lbl}</strong>.</p>
  <form method=post action=/settings/notify style=margin:0>
    <input type=hidden name=notify value="{'0' if notify else '1'}">
    <button class="btn btn-ghost" type=submit>{'Turn notifications off' if notify else 'Turn notifications on'}</button>
  </form>
</div>

<div class="panel set-danger">
  <h2>Delete account</h2>
  <p class=hint>Permanently delete your wptaskify account and disconnect all sites. Your WordPress
  content stays on your own site. This cannot be undone.</p>
  <form method=post action=/settings/delete style=margin:0
    onsubmit="return confirm('Delete your account permanently? This cannot be undone.')">
    <button class="btn btn-danger" type=submit>Delete my account</button>
  </form>
</div>
"""


def _affiliate_section(aff, public_url, csrf="", verified=True):
    """Refer & Earn panel: referral link, stats, payout details + request, history."""
    base = (public_url or SITE_BASE).rstrip("/")
    code = aff.get("code", "")
    s = aff.get("summary") or {}
    is_india = (aff.get("country") or "").upper() == "IN"
    cur = "₹" if is_india else "$"
    bal = s.get("balance_inr", 0) if is_india else s.get("balance_usd", 0)
    earned = s.get("earned_inr", 0) if is_india else s.get("earned_usd", 0)
    rate = aff.get("rate", 20)
    link = f"{base}/?ref={code}" if code else ""
    method = _e_html(aff.get("payout_method", ""))

    if not verified:
        return ('<div class=panel><h2>Refer &amp; Earn</h2>'
                '<p class=hint>Verify your email to unlock your referral link and start earning.</p>'
                '<div class="alert ok" style="margin-top:12px">Please verify your email first. '
                'Check your inbox, or <a href="/verify-sent">resend the verification email</a>.</div></div>')

    # referral rows
    rows = ""
    for r in aff.get("referrals", []):
        sym = "₹" if r["currency"] == "INR" else "$"
        st = ('<span class="pill ok">converted</span>' if r["status"] == "converted"
              else '<span class="pill">signed up</span>')
        amt = f'{sym}{r["commission"]:,.0f}' if r["status"] == "converted" else "-"
        rows += (f'<tr><td>{_e_html(r["email"])}</td><td>{st}</td>'
                 f'<td style="text-align:right">{amt}</td>'
                 f'<td class=muted>{r["created_at"][:10]}</td></tr>')
    if not rows:
        rows = '<tr><td colspan=4 class=muted style="text-align:center;padding:18px">No referrals yet. Share your link to get started.</td></tr>'

    # payout history
    ph = ""
    for p in aff.get("payouts", []):
        sym = "₹" if p["currency"] == "INR" else "$"
        pst = {"requested": '<span class="pill">requested</span>',
               "paid": '<span class="pill ok">paid</span>',
               "rejected": '<span class="pill off">rejected</span>'}.get(p["status"], p["status"])
        ph += (f'<tr><td>{sym}{p["amount"]:,.0f}</td><td>{pst}</td>'
               f'<td class=muted>{p["created_at"][:10]}</td></tr>')
    ph_block = (f'<div class=panel><h2>Payout history</h2>'
                f'<table class=txn><thead><tr><th>Amount</th><th>Status</th><th>Date</th></tr></thead>'
                f'<tbody>{ph}</tbody></table></div>') if ph else ""

    minimum = 1000 if is_india else 20

    # Per-plan earnings breakdown: what the referrer earns on each plan (rate % of the
    # base/pre-tax price). Prices mirror the pricing page. Mini is India-only (INR).
    _plans = [
        ("Mini", 700, 9, True),        # (name, INR base, USD base, india_only)
        ("Starter", 1699, 20, False),
        ("Pro", 8299, 99, False),
    ]
    _earn_rows = ""
    for _pn, _inr, _usd, _india_only in _plans:
        if _india_only and not is_india:
            continue
        _price = _inr if is_india else _usd
        _comm = _price * rate / 100.0
        _earn_rows += (
            f'<tr><td>{_pn}</td>'
            f'<td style="text-align:right">{cur}{_price:,.0f}</td>'
            f'<td style="text-align:right"><strong style="color:var(--accent-hi)">'
            f'{cur}{_comm:,.0f}</strong></td></tr>')

    return f"""
<div class=panel>
  <h2>Refer &amp; Earn</h2>
  <p class=hint>Share wptaskify and earn <strong>{rate:.0f}%</strong> commission on the first
  payment of every paid customer you refer &mdash; on <strong>every plan</strong>.</p>
  <label class=aff-lbl>Your referral link</label>
  <div class=aff-link>
    <input id=afflink value="{_e_html(link)}" readonly onclick="this.select()">
    <button type=button class="btn btn-primary" onclick="navigator.clipboard.writeText(document.getElementById('afflink').value);this.textContent='Copied!'">Copy</button>
  </div>
  <div class=aff-stats>
    <div class=aff-stat><b>{s.get("referrals",0)}</b><span>Sign-ups</span></div>
    <div class=aff-stat><b>{s.get("converted",0)}</b><span>Paid conversions</span></div>
    <div class=aff-stat><b>{cur}{earned:,.0f}</b><span>Total earned</span></div>
    <div class="aff-stat hi"><b>{cur}{bal:,.0f}</b><span>Available balance</span></div>
  </div>
</div>

<div class=panel>
  <h2>What you'll earn</h2>
  <p class=hint>Your <strong>{rate:.0f}%</strong> commission on each plan a referred customer buys.
  You earn it on their first payment.</p>
  <table class="txn aff-earn"><thead><tr>
    <th>Plan</th><th style="text-align:right">Customer pays</th>
    <th style="text-align:right">You earn</th>
  </tr></thead><tbody>{_earn_rows}</tbody></table>
  <p class=hint style="margin-top:12px">Payouts via UPI, bank transfer or PayPal &mdash; minimum
  {cur}{minimum:,.0f}. The more people you refer, the more you earn, month after month.</p>
</div>

<div class=panel>
  <h2>Get paid</h2>
  <p class=hint>Add where you'd like to receive payouts, then request a payout once your balance
  reaches {cur}{minimum:,.0f}. We process requests manually and pay to the details below.</p>
  <form method=post action=/affiliate/payout-method class=set-form style="margin-bottom:14px">
    <input type=hidden name=csrf value="{_e_html(csrf)}">
    <div class=field><label for=pm>Payout details (UPI ID, bank account, or PayPal email)</label>
    <input id=pm name=method value="{method}" placeholder="e.g. yourname@upi  or  PayPal: you@email.com" maxlength=300></div>
    <button class="btn btn-ghost" type=submit>Save payout details</button>
  </form>
  <form method=post action=/affiliate/request-payout style=margin:0>
    <input type=hidden name=csrf value="{_e_html(csrf)}">
    <input type=hidden name=currency value="{'INR' if is_india else 'USD'}">
    <button class="btn btn-primary" type=submit {'disabled style="opacity:.5"' if bal < minimum else ''}>
      Request payout ({cur}{bal:,.0f})</button>
  </form>
</div>

<div class=panel>
  <h2>Your referrals</h2>
  <table class=txn><thead><tr><th>User</th><th>Status</th><th style="text-align:right">Commission</th><th>Date</th></tr></thead>
  <tbody>{rows}</tbody></table>
</div>
{ph_block}
<style>
.aff-lbl{{display:block;font-family:'Sora';font-weight:600;font-size:.82rem;margin:6px 0 8px;color:var(--fg)}}
.aff-link{{display:flex;gap:10px;margin-bottom:18px}}
.aff-link input{{flex:1;padding:11px 14px;border:1px solid var(--border-hi);border-radius:10px;
  background:var(--surface2);color:var(--fg);font-size:.95rem}}
.aff-stats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:12px;margin-top:6px}}
.aff-stat{{background:var(--surface2);border:1px solid var(--border);border-radius:12px;padding:14px 16px}}
.aff-stat b{{display:block;font-family:'Sora';font-size:1.4rem;color:var(--fg)}}
.aff-stat span{{color:var(--muted);font-size:.82rem}}
.aff-stat.hi{{background:var(--accent-dim);border-color:rgba(249,115,22,.3)}}
.aff-stat.hi b{{color:var(--accent-hi)}}
.aff-earn td,.aff-earn th{{padding:10px 12px}}
.aff-earn tbody tr:last-child td{{font-weight:600}}
</style>"""


def dashboard(sites, public_url, account=None, flash="", flash_ok=False, email="", verified=True,
              token_account=None, chat_enabled=True, toolcall_account=None,
              country="", txns=None, usage=None, profile=None, csrf="", affiliate=None,
              google=None, google_configured=True, google_all=None, google_opts=None):
    connect = f"{public_url}/mcp" if public_url else "(set PUBLIC_URL)"
    settings_html = _settings_section(profile or {"email": email, "verified": verified})
    google_html = _google_section(google or {}, public_url, csrf, google_configured,
                                  sites=sites, google_all=google_all or [],
                                  google_opts=google_opts or {})
    affiliate_html = _affiliate_section(affiliate or {}, public_url, csrf, verified)
    plugin_url = f"{public_url}/plugin/wp-pilot-seo.zip" if public_url else "/plugin/wp-pilot-seo.zip"
    account = account or {"plan": "free", "credits": 5, "has_own_key": False}
    # Friendly greeting: use the saved display name, else derive from email.
    _pname = (profile or {}).get("name", "").strip()
    name = _pname or (email.split("@")[0] if email else "there").replace(".", " ").replace("_", " ").title()
    plan = account.get("plan", "free")
    credits = account.get("credits", 0)
    has_key = account.get("has_own_key", False)
    plan_max = account.get("credits_max") or {
        "free": 5, "owai_mini": 25, "owai_starter": 60, "owai_pro": 200,
        "pro": 60, "agency": 250, "chat_starter": 50, "chat_pro": 150, "chat_max": 250,
    }.get(plan, 5)
    pct = 100 if has_key else int(min(credits, plan_max) / plan_max * 100)
    # Display helper: an effectively-unlimited allowance (owner / special accounts,
    # set to ~1,000,000) reads as "Unlimited" instead of an ugly raw number like
    # 999969. Every real image plan is <= 250, so this only ever triggers for
    # unlimited accounts. Normal numbers get thousands separators.
    _UNLIMITED_AT = 100000
    def _fmt_credits(n):
        try:
            n = int(n)
        except (TypeError, ValueError):
            return str(n)
        return "Unlimited" if n >= _UNLIMITED_AT else f"{n:,}"
    # If the monthly cap is unlimited, the "left" count should read Unlimited too
    # (not "999,969 / Unlimited").
    _img_unlimited = plan_max >= _UNLIMITED_AT
    credits_disp = "Unlimited" if _img_unlimited else _fmt_credits(credits)
    plan_max_disp = _fmt_credits(plan_max)

    if sites:
        items = "".join(
            f'<div class=site-item>'
            f'<div class=ico>{_icon("<rect width=18 height=18 x=3 y=3 rx=2/><path d=\'M3 9h18\'/>")}</div>'
            f'<div class=meta><div class=url>{_e_html(s["site_url"])}</div>'
            f'<div class=usr>{_e_html(s["wp_username"])}</div></div>'
            f'<span class="pill ok">{_e_html(s["status"])}</span>'
            f'<form method=post action=/sites/delete style=margin:0 '
            f'onsubmit="return confirm(\'Remove this site? Your WordPress site is not affected - '
            f'it just disconnects from wptaskify.\')">'
            f'<input type=hidden name=site_id value="{s["id"]}">'
            f'<button type=submit class=site-remove title="Remove site">'
            f'{_icon("<path d=\'M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2\'/>")}'
            f'</button></form>'
            f'</div>'
            for s in sites)
    else:
        items = ('<div class=empty>No site connected yet. Add your WordPress site below '
                 '- then you can run it from any AI.</div>')
    fl = f'<div class="alert {"ok" if flash_ok else "err"}">{_e_html(flash)}</div>' if flash else ""

    copy_btn = ('<button class="btn btn-ghost" style="padding:8px 14px;font-size:.85rem" '
                "onclick=\"navigator.clipboard.writeText('" + connect + "');"
                "this.textContent='Copied'\">Copy</button>")

    # (Old credits/BYOK panels removed - the Plan & Usage section now covers
    # image credits + AI actions + top-ups. Bring-your-own-Gemini-key is gone.)

    # Chat token balance.
    ta = token_account or {"credits": 0, "credits_max": 0}
    chat_credits = ta.get("credits", 0)
    chat_credits_max = ta.get("credits_max", 0) or 1
    chat_pct = int(min(chat_credits, chat_credits_max) / chat_credits_max * 100)

    # AI tools list HTML (grouped) - full curated catalog (_TOOL_GROUPS, ~77 tools),
    # each card showing name + description + a plain-English "Try:" example command.
    import html as _th
    tools_html = ""
    for group, subtitle, tools in _TOOL_GROUPS:
        cards = ""
        for t, d in tools:
            cmd = _th.escape(_tool_command(t))
            cards += (
                f'<div class=tool>'
                f'<div class=tool-name>{_CHECK} {_th.escape(t)}</div>'
                f'<div class=tool-desc>{_th.escape(d)}</div>'
                f'<div class=tool-cmd><span class=tool-cmd-lbl>Try</span>'
                f'<span class=tool-cmd-txt>{cmd}</span></div>'
                f'</div>')
        tools_html += (
            f'<div class=tool-cat>'
            f'<h3 class=tool-group>{_th.escape(group)}'
            f'<span class=tool-cat-count>{len(tools)}</span></h3>'
            f'<p class=tool-cat-sub>{_th.escape(subtitle)}</p>'
            f'<div class=tool-grid>{cards}</div></div>')

    # ---- PLAN section: current plan + usage + all plans + top-ups + history ----
    _usage = dict(usage or {})
    _usage.setdefault("csrf", csrf)  # for the Cancel-plan form
    plan_html = _plan_section(plan, account, toolcall_account, token_account,
                              credits, plan_max, has_key, country, txns or [],
                              chat_enabled, _usage)

    # ---- compact plan+usage snapshot for the Overview ----
    _pn = {"free": "Free", "owai_mini": "Mini", "owai_starter": "Starter",
           "owai_pro": "Pro", "chat_starter": "Chat Starter", "chat_pro": "Chat Pro",
           "chat_max": "Chat Max", "pro": "Pro", "agency": "Agency"}.get(plan, plan.title())
    _ta = toolcall_account or {}
    _tcl, _tcm = _ta.get("tool_calls", 0), _ta.get("tool_calls_max", 0)
    if _tcm >= 1_000_000:
        _act_row = ('<div class=ov-use><div class=ov-lbl>AI actions</div>'
                    '<div class=ov-val>Unlimited</div></div>'
                    '<div class=use-track><div class=use-fill style="width:100%"></div></div>')
    else:
        _ap = int(min(_tcl, _tcm) / _tcm * 100) if _tcm else 0
        _act_row = (f'<div class=ov-use><div class=ov-lbl>AI actions</div>'
                    f'<div class=ov-val>{_tcl:,} <small>/ {_tcm:,}</small></div></div>'
                    f'<div class=use-track><div class=use-fill style="width:{_ap}%"></div></div>')
    if _img_unlimited:
        _img_row = ('<div class=ov-use><div class=ov-lbl>AI images</div>'
                    '<div class=ov-val>Unlimited</div></div>'
                    '<div class=use-track><div class=use-fill style="width:100%"></div></div>')
    else:
        _ip = int(min(credits, plan_max) / plan_max * 100) if plan_max else 0
        _img_row = (f'<div class=ov-use><div class=ov-lbl>AI images</div>'
                    f'<div class=ov-val>{credits_disp} <small>/ {plan_max_disp}</small></div></div>'
                    f'<div class=use-track><div class=use-fill style="width:{_ip}%"></div></div>')
    _resets = (usage or {}).get("resets_on", "the 1st")
    overview_plan = (
        f'<div class="card ov-plan">'
        f'<div class=ov-plan-head><div><span class=plan-eyebrow>Your plan</span>'
        f'<div class=plan-badge-lg style="font-size:1.3rem">{_pn}</div></div>'
        f'<button class="btn btn-ghost" onclick="showSec(\'plan\')">Manage plan &amp; usage &rarr;</button></div>'
        f'<div class=ov-bars>{_act_row}{_img_row}</div>'
        f'<p class=hint style="margin:12px 0 0;font-size:.85rem">Limits reset on <strong>{_resets}</strong>.</p>'
        f'</div>')

    # Email-verify reminder (only when not verified).
    verify_banner = ""
    if not verified:
        verify_banner = (
            '<div class=panel style="border-color:var(--danger)">'
            '<h2>Verify your email</h2>'
            '<p class=hint>Please confirm your email address to unlock everything. '
            'Check your inbox for the verification link.</p>'
            '<form method=post action=/verify-resend style=margin:0>'
            '<button class="btn btn-ghost" type=submit>Resend verification email</button></form></div>')

    # sidebar icons (SVG paths)
    ic_home = '<path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"/><path d="M9 22V12h6v10"/>'
    ic_sites = '<rect width=18 height=18 x=3 y=3 rx=2/><path d="M3 9h18"/><path d="M9 21V9"/>'
    ic_ai = '<path d="M12 8V4M8 4h8M4.93 10.93 6.34 12.34M19.07 10.93 17.66 12.34"/><rect width=16 height=12 x=4 y=8 rx=2/><path d="M9 16h.01M15 16h.01"/>'
    ic_credit = '<rect width=20 height=14 x=2 y=5 rx=2/><path d="M2 10h20"/>'
    ic_plugin = '<path d="M12 2v6M5.5 8a4 4 0 0 0 0 8h13a4 4 0 0 0 0-8Z"/><path d="M9 12h.01M15 12h.01"/>'
    ic_plus = '<line x1=12 x2=12 y1=5 y2=19/><line x1=5 x2=19 y1=12 y2=12/>'
    ic_tools = '<path d="M14.7 6.3a4 4 0 0 0-5.4 5.4L3 18v3h3l6.3-6.3a4 4 0 0 0 5.4-5.4l-2.3 2.3-2-2 2.3-2.3Z"/>'
    ic_chat = '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2Z"/>'
    ic_bolt = '<path d="M13 2 3 14h9l-1 8 10-12h-9l1-8Z"/>'
    ic_logout = '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1=21 x2=9 y1=12 y2=12/>'
    sites_count = len(sites)

    return _head(f"Dashboard - {BRAND}") + f"""
<div class=app>
<aside class=sidebar id=sidebar>
  <a href="/" class=brand>
    {_logo_svg(24)}
    <span>{BRAND}</span>
  </a>
  <nav class=side-nav>
    <button class="side-link active" data-sec=overview>{_icon(ic_home)}<span>Overview</span></button>
    <button class="side-link" data-sec=plugin>{_icon('<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/><path d="M9 7h6M9 11h4"/>')}<span>Get the Plugin</span></button>
    <button class="side-link" data-sec=sites>{_icon(ic_sites)}<span>My Sites</span></button>
    <div class=side-sub id=sites-sub>
      <button class="side-link sub-item" data-sec=addsite><span class=sub-dot></span><span>Connect Site</span></button>
    </div>
    <button class="side-link" data-sec=tools>{_icon(ic_tools)}<span>AI Tools</span></button>
    <button class="side-link" data-sec=connect>{_icon(ic_ai)}<span>AI Connect</span></button>
    <button class="side-link" data-sec=analytics>{_icon('<line x1=18 y1=20 x2=18 y2=10/><line x1=12 y1=20 x2=12 y2=4/><line x1=6 y1=20 x2=6 y2=14/>')}<span>Analytics</span></button>
    <button class="side-link" data-sec=plan>{_icon('<path d="M12 2 2 7l10 5 10-5-10-5Z"/><path d="m2 17 10 5 10-5M2 12l10 5 10-5"/>')}<span>Plan &amp; Usage</span></button>
    <button class="side-link" data-sec=affiliate>{_icon('<circle cx=18 cy=5 r=3/><circle cx=6 cy=12 r=3/><circle cx=18 cy=19 r=3/><line x1=8.6 y1=10.7 x2=15.4 y2=6.3/><line x1=8.6 y1=13.3 x2=15.4 y2=17.7/>')}<span>Refer &amp; Earn</span></button>
    <button class="side-link" data-sec=settings>{_icon('<circle cx=12 cy=12 r=3/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 8 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H2a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 3.6 8a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H8a1.65 1.65 0 0 0 1-1.51V2a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V8a1.65 1.65 0 0 0 1.51 1H22a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1Z"/>')}<span>Settings</span></button>
  </nav>
  <div class=side-foot>
    <form method=post action=/logout style=margin:0>
      <button class="side-link" type=submit>{_icon(ic_logout)}<span>Log out</span></button>
    </form>
  </div>
</aside>

<main class=main>
<div class=main-inner>
<div class=topbar>
  <button class=burger onclick="document.getElementById('sidebar').classList.toggle('open')">{_icon('<line x1=3 x2=21 y1=6 y2=6/><line x1=3 x2=21 y1=12 y2=12/><line x1=3 x2=21 y1=18 y2=18/>')}</button>
  <h1 id=sectitle>Overview</h1>
  <span class=plan-badge>{plan_label(plan)}</span>
</div>
{fl}

<!-- OVERVIEW -->
<section class="sec active" data-panel=overview>
  <div class=welcome>
    <h2>Welcome{(', ' + _e_html(name)) if name and name != 'There' else ''} <span class=grad>to wptaskify</span></h2>
    <p>Connect your WordPress site to AI and let Claude or ChatGPT write articles, generate images,
    and manage your SEO - automatically. Let's get you set up in three quick steps.</p>
    <div class=acts>
      <button class="btn btn-primary" onclick="showSec('plugin')">Get started</button>
      <button class="btn btn-ghost" onclick="showSec('connect')">Connect AI</button>
    </div>
  </div>

  {verify_banner}

  <div class=gs>
    <div class=step onclick="showSec('plugin')"><div class=n>1</div><h3>Install the plugin</h3><p>Add our free wptaskify plugin to your WordPress site.</p></div>
    <div class=step onclick="showSec('sites')"><div class=n>2</div><h3>Connect your site</h3><p>One click inside the plugin adds your site here - no passwords to copy.</p></div>
    <div class=step onclick="showSec('connect')"><div class=n>3</div><h3>Use it from AI</h3><p>Add the connector in Claude or ChatGPT and start creating.</p></div>
  </div>

  <div class=stat-grid>
    <div class=stat-card><div class=n>{sites_count}</div><div class=l>Connected sites</div></div>
    <div class=stat-card><div class=n>{credits_disp}</div><div class=l>Image credits left</div></div>
    <div class=stat-card style="cursor:pointer" onclick="showSec('tools')"><div class=n>100+</div><div class=l>AI tools available →</div></div>
  </div>

  <!-- Plan & usage snapshot on the overview -->
  {overview_plan}
</section>

<!-- MY SITES (list only) -->
<section class=sec data-panel=sites>
  <div class=panel>
    <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap">
      <div>
        <h2 style=margin-bottom:4px>Your WordPress sites</h2>
        <p class=hint style=margin:0>These are the sites you can run from your AI.</p>
      </div>
      <button class="btn btn-primary" onclick="showSec('addsite')">{_icon('<circle cx=12 cy=12 r=10/><line x1=12 x2=12 y1=8 y2=16/><line x1=8 x2=16 y1=12 y2=12/>')} Add site</button>
    </div>
    <div style=margin-top:18px>{items}</div>
  </div>
</section>

<!-- ADD SITE (form) -->
<section class=sec data-panel=addsite>
  <div class=panel style="border-color:var(--accent)">
    <h2>Connect a WordPress site</h2>
    <p class=hint>Connecting takes one click with the free wptaskify plugin. No passwords to copy, and it sets everything up securely for you.</p>
    <ol class=steps>
      <li>Download and install the free <strong>wptaskify</strong> plugin on your WordPress site.</li>
      <li>Open the <strong>wptaskify</strong> menu in your WordPress admin and click <strong>Connect to wptaskify</strong>.</li>
      <li>You'll be brought back here and your site will appear under <strong>My Sites</strong> automatically.</li>
    </ol>
    <div style="display:flex;gap:12px;flex-wrap:wrap;margin-top:14px">
      <a class="btn btn-primary btn-lg" href="{plugin_url}">Download the plugin</a>
      <button class="btn btn-ghost" onclick="showSec('plugin')">Setup guide</button>
    </div>
  </div>
</section>

<!-- SEO PLUGIN -->
<section class=sec data-panel=plugin>
  <div class=panel style="border-color:var(--accent)">
    <h2 style="display:flex;align-items:center;gap:8px"><span style="color:var(--accent-hi)">{_icon(ic_plugin)}</span> wptaskify - free plugin</h2>
    <p class=hint>A complete, free SEO plugin for any WordPress site: meta titles &amp; descriptions, focus keywords, schema, XML sitemap, Open Graph and a live SEO score. It also lets you connect this site to {BRAND} in one click.</p>
    <div style="display:flex;gap:12px;flex-wrap:wrap;margin:14px 0 4px">
      <a class="btn btn-primary btn-lg" href="{plugin_url}">Download plugin</a>
      <a class="btn btn-ghost" href="https://wordpress.org/documentation/article/manage-plugins/#installing-plugins-1" target=_blank rel=noopener>How to install</a>
    </div>
  </div>
  <div class=panel>
    <h2>Set it up in 3 steps</h2>
    <ol class=steps>
      <li>Download the plugin above and upload it in <em>WP Admin → Plugins → Add New → Upload Plugin</em></li>
      <li>Activate it, then open the <strong>wptaskify</strong> menu in your WordPress sidebar</li>
      <li>Click <strong>Connect to {BRAND}</strong> - your site is added here automatically, no password to copy</li>
    </ol>
  </div>
  <div class=panel>
    <h2>What you get</h2>
    <ul class=feat-list>
      <li>{_CHECK} Meta title, description &amp; focus keyword</li>
      <li>{_CHECK} Schema / structured data (Article, FAQ, Breadcrumb…)</li>
      <li>{_CHECK} Automatic XML sitemap</li>
      <li>{_CHECK} Open Graph &amp; Twitter cards</li>
      <li>{_CHECK} Live SEO score with checklist</li>
      <li>{_CHECK} Auto-updates &amp; one-click AI connect</li>
    </ul>
  </div>
</section>

<!-- AI TOOLS -->
<section class=sec data-panel=tools>
  <div class=panel>
    <h2>100+ AI tools - just ask</h2>
    <p class=hint>Every tool below is one plain-English message away. You don't run them yourself - your AI picks the right one and does the work.</p>
    <div class=tool-howto>
      <div class=tool-howto-steps>
        <strong>How to use:</strong> Once your site is connected, open Claude or ChatGPT and type a request in plain English. The AI picks the right tool and does it - and nothing goes live without your approval. For example, type:
      </div>
      <div class=cmd-hero>{_CHECK}<span>Write an SEO-optimized article about summer skincare and publish it with a featured image.</span></div>
      <p class=tool-howto-hint>Below are all your tools grouped by job. Each one shows an example command - the exact kind of thing you can type to trigger it.</p>
    </div>
    {tools_html}
  </div>
</section>

<!-- AI CONNECT -->
<section class=sec data-panel=connect>
  <div class=panel>
    <h2>Connect to Claude or ChatGPT</h2>
    <p class=hint>Add a custom connector in your AI and sign in with this same wptaskify account.</p>
    <div class=connect-note>{_icon("<circle cx=12 cy=12 r=10/><path d='M12 16v-4M12 8h.01'/>")}
      <span><strong>Important:</strong> stay logged in to wptaskify in <u>this same browser</u> while you connect. When your AI asks you to sign in, it opens wptaskify here - if you're already logged in, it links instantly with no extra password.</span>
    </div>
    <ol class=steps>
      <li>In Claude or ChatGPT → <strong>Settings → Connectors → Add custom connector</strong></li>
      <li>Give it a <strong>name</strong> - type <span class=inline-code>wptaskify</span> (or anything you like, e.g. "My WordPress")</li>
      <li>Paste this <strong>URL</strong>:</li>
    </ol>
    <div class=code-box style=margin:14px0><span>{connect}</span>{copy_btn}</div>
    <ol class=steps start=4 style="counter-reset:s 3">
      <li>Click <strong>Connect</strong> → it opens wptaskify → you're already signed in here, so it links in one click</li>
      <li>Done! Your site's {TOTAL_TOOLS}+ tools now appear inside the AI - just ask.</li>
    </ol>
    <div class=connect-note style=margin-top:16px>{_icon("<circle cx=12 cy=12 r=10/><path d='M12 16v-4M12 8h.01'/>")}
      <span><strong>Using ChatGPT?</strong> Custom connectors need a paid plan (Plus, Pro, Business or Enterprise). Go to <strong>Settings → Connectors</strong>; if you don't see "Add custom connector", enable <strong>Settings → Advanced → Developer mode</strong> first. Then use the same URL above and choose <strong>OAuth</strong> when asked. (Claude works on this URL directly.)</span>
    </div>
  </div>
</section>

<!-- ANALYTICS (Google Analytics + Search Console) -->
<section class=sec data-panel=analytics>
  <div class=panel>
    <h2>Analytics &amp; Search</h2>
    <p class=hint>Connect Google Analytics and Search Console so your AI can review your real traffic, top pages and search performance - right here or from Claude/ChatGPT.</p>
  </div>
  {google_html}
</section>

<!-- PLAN & USAGE -->
<section class=sec data-panel=plan>
{plan_html}
</section>

<!-- AFFILIATE -->
<section class=sec data-panel=affiliate>
{affiliate_html}
</section>

<!-- SETTINGS -->
<section class=sec data-panel=settings>
{settings_html}
</section>

</div><!-- /main-inner -->
</main>
</div>

<script>
function showSec(name){{
  document.querySelectorAll('.sec').forEach(s=>s.classList.toggle('active',s.dataset.panel===name));
  document.querySelectorAll('.side-link[data-sec]').forEach(b=>b.classList.toggle('active',b.dataset.sec===name));
  var titles={{overview:'Overview',sites:'My Sites',addsite:'Connect Site',tools:'AI Tools',connect:'AI Connect',analytics:'Analytics & Search',plugin:'wptaskify Plugin',plan:'Plan & Usage',affiliate:'Refer & Earn',settings:'Settings'}};
  document.getElementById('sectitle').textContent=titles[name]||'';
  // keep the "My Sites" parent highlighted when on Add Site, and show the submenu
  var onSites = (name==='sites'||name==='addsite');
  document.querySelector('.side-link[data-sec=sites]').classList.toggle('active', onSites);
  document.getElementById('sites-sub').classList.toggle('show', onSites);
  document.getElementById('sidebar').classList.remove('open');
  if(history.replaceState) history.replaceState(null,'','#'+name);
}}
document.querySelectorAll('.side-link[data-sec]').forEach(b=>b.addEventListener('click',()=>showSec(b.dataset.sec)));
var valid=['overview','sites','addsite','tools','connect','analytics','plugin','credits','plan','affiliate','settings'];
if(location.hash){{var h=location.hash.slice(1); if(valid.includes(h)) showSec(h);}}
// After connecting/updating Google Analytics we return to /dashboard?ok=Google...
// - land the user back on the Analytics tab (not Overview).
(function(){{
  var q=new URLSearchParams(location.search);
  var okm=(q.get('ok')||'');
  if(/Google|Analytics/i.test(okm)) showSec('analytics');
}})();
// CSRF: add the session token to every same-origin POST form (defense-in-depth).
(function(){{
  var tok="{csrf}";
  if(!tok) return;
  document.querySelectorAll('form[method=post],form[method=POST]').forEach(function(fm){{
    if(fm.querySelector('input[name=csrf]')) return;
    var i=document.createElement('input');i.type='hidden';i.name='csrf';i.value=tok;
    fm.appendChild(i);
  }});
}})();
</script>
</body></html>"""


def billing_page(summary, txns, billing_enabled=True, flash=""):
    summary = summary or {"plan": "free", "sub_status": "none", "renews_at": None}
    plan = summary.get("plan", "free")
    plan_names = {"free": "Free", "owai_starter": "Starter", "owai_pro": "Pro",
                  "chat_starter": "Chat Starter", "chat_pro": "Chat Pro", "chat_max": "Chat Max"}
    fl = f'<div class="alert ok" style=margin-bottom:18px>{_e_html(flash)}</div>' if flash else ""

    # credit packs
    packs = [
        ("img_100", "100 AI images", "$8"), ("img_300", "300 AI images", "$20"),
        ("img_500", "500 AI images", "$30"),
    ]
    tok_packs = [
        ("tok_1m", "1,000 AI credits", "$6"), ("tok_5m", "5,000 AI credits", "$25"),
        ("tok_15m", "15,000 AI credits", "$65"),
    ]
    pack_cards = "".join(
        f'<form method=post action=/topup class=pack><input type=hidden name=pack value="{pid}">'
        f'<div class=pack-name>{label}</div><div class=pack-price>{price}</div>'
        f'<button class="btn btn-ghost btn-block" {("" if billing_enabled else "disabled")}>Buy</button></form>'
        for pid, label, price in packs)
    tok_cards = "".join(
        f'<form method=post action=/topup class=pack><input type=hidden name=pack value="{pid}">'
        f'<div class=pack-name>{label}</div><div class=pack-price>{price}</div>'
        f'<button class="btn btn-ghost btn-block" {("" if billing_enabled else "disabled")}>Buy</button></form>'
        for pid, label, price in tok_packs)

    rows = "".join(
        f'<tr><td>{t["created_at"][:10]}</td><td>{t["item"]}</td>'
        f'<td>{"₹" if t.get("currency","INR")=="INR" else "$"}{t["amount_usd"]:.0f}</td>'
        f'<td>{t["status"]}</td></tr>' for t in txns
    ) or '<tr><td colspan=4 style="color:var(--muted2);text-align:center;padding:16px">No transactions yet</td></tr>'

    sub_line = ""
    if summary.get("sub_status") == "active":
        sub_line = '<span class="pill ok">Active subscription</span>'

    disabled_note = ("" if billing_enabled else
                     '<div class="alert" style="background:var(--surface2);color:var(--muted);margin-bottom:18px">'
                     'Payments are being set up - buttons will activate soon.</div>')

    return _head(f"Billing - {BRAND}") + f"""
<nav class=nav><div class=wrap>{_logo()}
<div class=nav-links><a href="/dashboard">Dashboard</a></div></div></nav>
<div style="max-width:820px;margin:0 auto;padding:34px 22px">
<h1>Billing</h1>
{fl}{disabled_note}
<div class=panel style=margin-top:18px>
  <h2>Current plan</h2>
  <p class=hint>Your subscription and plan.</p>
  <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap">
    <span class=plan-badge style=font-size:.9rem>{plan_names.get(plan, plan)}</span>{sub_line}
  </div>
  <div style=margin-top:14px><a href="/#pricing" class="btn btn-primary">Change / upgrade plan</a></div>
</div>

<div class=panel>
  <h2>Buy more AI credits (chat)</h2>
  <p class=hint>Top up chat AI credits any time. 1 credit = 1,000 tokens.</p>
  <div class=packs>{tok_cards}</div>
</div>

<div class=panel>
  <h2>Buy more image credits</h2>
  <p class=hint>Top up AI image credits.</p>
  <div class=packs>{pack_cards}</div>
</div>

<div class=panel>
  <h2>Transaction history</h2>
  <table class=txn><thead><tr><th>Date</th><th>Item</th><th>Amount</th><th>Status</th></tr></thead>
  <tbody>{rows}</tbody></table>
</div>
</div>
<style>
.packs{{display:grid;gap:14px;grid-template-columns:repeat(auto-fit,minmax(180px,1fr))}}
.pack{{background:var(--bg2);border:1px solid var(--border);border-radius:14px;padding:18px;text-align:center;margin:0}}
.pack-name{{font-weight:600;color:var(--fg);font-size:.95rem}}
.pack-price{{font-family:'Sora';font-size:1.6rem;font-weight:800;color:var(--accent-hi);margin:6px 0 12px}}
.txn{{width:100%;border-collapse:collapse;font-size:.9rem}}
.txn th{{text-align:left;color:var(--muted);font-weight:500;padding:8px;border-bottom:1px solid var(--border)}}
.txn td{{padding:10px 8px;border-bottom:1px solid var(--border);color:var(--fg)}}
</style>
</body></html>"""


def maintenance_page():
    return ("<!doctype html><html lang=en><head><meta charset=utf-8>"
            "<meta name=viewport content=\"width=device-width,initial-scale=1\">"
            f"<title>Back soon - {BRAND}</title>{_FAVICON}"
            "<link href=\"https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600"
            "&family=Sora:wght@400;500;600;700;800&display=swap\" rel=stylesheet>"
            f"<style>{_CSS}</style></head><body>"
            "<div style='min-height:100dvh;display:grid;place-items:center;padding:40px 20px;text-align:center'>"
            "<div style='max-width:480px'>"
            f"{_logo()}"
            "<div style='width:64px;height:64px;border-radius:18px;margin:24px auto;display:grid;place-items:center;"
            "background:var(--accent-dim);color:var(--accent-hi)'>"
            + _icon("<path d='M14.7 6.3a4 4 0 0 0-5.4 5.4L3 18v3h3l6.3-6.3a4 4 0 0 0 5.4-5.4l-2.3 2.3-2-2 2.3-2.3Z'/>")
            + "</div>"
            "<h1 style='font-size:2rem'>We'll be back soon</h1>"
            "<p style='color:var(--muted);font-size:1.1rem;max-width:40ch;margin:14px auto'>"
            f"{BRAND} is getting an upgrade. We're polishing things up and will be live again shortly. "
            "Thanks for your patience.</p>"
            "</div></div></body></html>")


def message_page(title, body_html, link="/", link_text="Continue"):
    return _head(f"{title} - {BRAND}") + f"""
<div class=auth-wrap><div class=auth-card>
{_logo()}<h1>{title}</h1>{body_html}
<a href="{link}" class="btn btn-primary btn-block btn-lg" style=margin-top:18px>{link_text}</a>
</div></div></body></html>"""


# ---------------------------------------------------------------------------
# Full Claude-style chat page (/chat)
# ---------------------------------------------------------------------------
_CHAT_CSS = """
.cx{display:flex;height:100dvh;overflow:hidden}
/* history sidebar */
.cx-side{width:264px;background:var(--bg2);border-right:1px solid var(--border);display:flex;flex-direction:column;flex-shrink:0}
.cx-side-top{padding:14px}
.cx-newbtn{width:100%;display:flex;align-items:center;justify-content:center;gap:8px;background:var(--accent);
  color:#fff;font-weight:700;font-family:'Sora';border:none;border-radius:12px;padding:11px;cursor:pointer;font-size:.95rem}
.cx-newbtn:hover{background:var(--accent-hi)}
.cx-newbtn svg{width:18px!important;height:18px!important;stroke:#ffffff!important;display:inline-block!important;flex-shrink:0;opacity:1!important}
.cx-convs{flex:1;overflow-y:auto;padding:6px 10px}
.cx-conv{display:flex;align-items:center;gap:8px;padding:10px 11px;border-radius:10px;cursor:pointer;color:var(--muted);font-size:.9rem;margin-bottom:2px}
.cx-conv:hover{background:var(--surface2);color:var(--fg)}
.cx-conv.active{background:var(--accent-dim);color:var(--accent-hi)}
.cx-conv .t{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.cx-conv .x{opacity:0;color:var(--muted2);padding:2px;border-radius:6px;flex-shrink:0}
.cx-conv:hover .x{opacity:1}
.cx-conv .x:hover{color:var(--danger);background:rgba(239,68,68,.12)}
.cx-side-foot{border-top:1px solid var(--border);padding:12px 14px}
.cx-side-foot a{color:var(--muted);font-size:.85rem;display:flex;align-items:center;gap:8px;text-decoration:none}
.cx-side-foot a:hover{color:var(--fg)}
/* main */
.cx-main{flex:1;display:flex;flex-direction:column;min-width:0}
.cx-top{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 22px;border-bottom:1px solid var(--border)}
.cx-site{display:flex;align-items:center;gap:8px;font-size:.9rem;color:var(--muted)}
.cx-site select{background:var(--bg2);border:1px solid var(--border-hi);color:var(--fg);border-radius:8px;padding:7px 10px;font-family:inherit;font-size:.9rem;cursor:pointer}
.cx-site .dot{width:8px;height:8px;border-radius:50%;background:var(--accent);box-shadow:0 0 8px var(--accent)}
.cx-credits{font-size:.82rem;color:var(--accent-hi);background:var(--accent-dim);padding:6px 12px;border-radius:999px;font-family:'Sora';font-weight:600;white-space:nowrap}
.cx-log{flex:1;overflow-y:auto;padding:26px 0}
.cx-log-inner{max-width:760px;margin:0 auto;padding:0 22px;display:flex;flex-direction:column;gap:22px}
.cx-empty{margin:auto;text-align:center;color:var(--muted);max-width:560px;padding:40px 22px}
.cx-empty h2{font-size:2rem;margin-bottom:8px;font-family:'Sora';font-weight:700;
  background:linear-gradient(120deg,#fff 30%,var(--accent-hi));-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
.cx-egs{display:grid;gap:10px;margin-top:22px}
.cx-eg{background:var(--surface);border:1px solid var(--border-hi);color:var(--fg);padding:13px 16px;border-radius:12px;cursor:pointer;text-align:left;font-size:.92rem;transition:border-color .15s}
.cx-eg:hover{border-color:var(--accent)}
.cm{display:flex;gap:13px}
.cm .av{width:30px;height:30px;border-radius:8px;flex-shrink:0;display:grid;place-items:center;font-family:'Sora';font-weight:700;font-size:.8rem}
.cm.user .av{background:var(--surface2);color:var(--fg)}
.cm.ai .av{background:var(--accent);color:#fff}
.cm .body{flex:1;min-width:0;font-size:.96rem;line-height:1.65;color:var(--fg);padding-top:4px}
.cm .body p{margin:0 0 10px;color:var(--fg)}
.cm .body p:last-child{margin-bottom:0}
.cm .body ul,.cm .body ol{margin:8px 0;padding-left:22px;color:var(--fg)}
.cm .body li{margin:4px 0}
.cm .body a{color:var(--accent-hi)}
.cm .body code{background:var(--bg2);padding:2px 6px;border-radius:5px;font-size:.88em}
.cm .body strong{color:#fff}
.cm.thinking .body{color:var(--muted)}
.cx-dots{display:inline-flex;gap:5px;align-items:center;margin-top:6px}
.cx-dots span{width:8px;height:8px;border-radius:50%;background:var(--accent);animation:cxpulse 1.2s ease-in-out infinite}
.cx-dots span:nth-child(2){animation-delay:.2s}
.cx-dots span:nth-child(3){animation-delay:.4s}
@keyframes cxpulse{0%,60%,100%{opacity:.25;transform:scale(.8)}30%{opacity:1;transform:scale(1)}}
.cx-working{font-size:.92rem;color:var(--fg)}
.cx-steps{display:flex;flex-direction:column;gap:6px;margin-bottom:8px}
.cx-step-done{font-size:.88rem;color:var(--muted);display:flex;align-items:center;gap:8px}
.cx-check{color:var(--accent);font-weight:700}
.cx-nowstep{display:flex;align-items:center;gap:10px}
/* composer */
.cx-composer{border-top:1px solid var(--border);padding:16px 22px}
.cx-composer-inner{max-width:760px;margin:0 auto;display:flex;gap:10px;align-items:flex-end;
  background:var(--bg2);border:1px solid var(--border-hi);border-radius:16px;padding:8px 8px 8px 16px}
.cx-composer-inner:focus-within{border-color:var(--accent)}
.cx-composer textarea{flex:1;resize:none;background:none;border:none;color:var(--fg);font-size:1rem;font-family:inherit;padding:8px 0;max-height:180px;outline:none}
.cx-send{background:var(--accent);color:#fff;border:none;border-radius:11px;width:40px;height:40px;cursor:pointer;display:grid;place-items:center;flex-shrink:0}
.cx-send:hover{background:var(--accent-hi)}
.cx-send:disabled{opacity:.4;cursor:default}
.cx-send svg{width:18px!important;height:18px!important;stroke:#ffffff!important;display:inline-block!important;flex-shrink:0;opacity:1!important}
.cx-hint{max-width:760px;margin:8px auto 0;text-align:center;font-size:.78rem;color:var(--muted2)}
@media(max-width:760px){.cx-side{position:fixed;z-index:50;left:0;top:0;height:100dvh;transform:translateX(-100%);transition:transform .2s}.cx-side.open{transform:none}.cx-burger{display:inline-flex}}
.cx-burger{display:none;background:none;border:1px solid var(--border-hi);border-radius:8px;padding:7px;cursor:pointer;color:var(--fg)}
"""


def chat_page(sites, token_account=None, chat_enabled=True):
    ta = token_account or {"credits": 0}
    credits = ta.get("credits", 0)

    # Site selector: dropdown if >1 site, else a static badge.
    if len(sites) > 1:
        opts = "".join(f'<option value="{_e_html(s["id"])}">{_e_html(s["site_url"])}</option>' for s in sites)
        site_ctrl = f'<span class=dot></span>Active site: <select id=cx-site>{opts}</select>'
    elif len(sites) == 1:
        site_ctrl = f'<span class=dot></span>Active site: <strong style="color:var(--fg)">{sites[0]["site_url"]}</strong><span id=cx-site data-only="{sites[0]["id"]}" hidden></span>'
    else:
        site_ctrl = '<span style="color:var(--danger)">No site connected - <a href="/dashboard#sites">add one</a></span>'

    av_logo = ('<svg width=16 height=16 viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=2 '
               'stroke-linecap=round stroke-linejoin=round><path d="M12 2 2 7l10 5 10-5-10-5Z"/>'
               '<path d="m2 17 10 5 10-5"/><path d="m2 12 10 5 10-5"/></svg>')

    head = ("<!doctype html><html lang=en><head><meta charset=utf-8>"
            "<meta name=viewport content=\"width=device-width,initial-scale=1\">"
            f"<title>AI Chat - {BRAND}</title>{_FAVICON}"
            "<link rel=preconnect href=https://fonts.googleapis.com>"
            "<link href=\"https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600"
            "&family=Sora:wght@400;500;600;700;800&display=swap\" rel=stylesheet>"
            f"<style>{_CSS}{_CHAT_CSS}</style></head><body>")

    return head + f"""
<div class=cx>
  <aside class=cx-side id=cx-side>
    <div class=cx-side-top>
      <button class="cx-newbtn" onclick="newChat()"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#ffffff" stroke-width="2.4" stroke-linecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg> New chat</button>
    </div>
    <div class=cx-convs id=cx-convs></div>
    <div class=cx-side-foot>
      <a href="/dashboard">{_icon('<path d="m15 18-6-6 6-6"/>')} Back to dashboard</a>
    </div>
  </aside>

  <main class=cx-main>
    <div class=cx-top>
      <div style="display:flex;align-items:center;gap:10px">
        <button class=cx-burger onclick="document.getElementById('cx-side').classList.toggle('open')">{_icon('<line x1=3 x2=21 y1=6 y2=6/><line x1=3 x2=21 y1=12 y2=12/><line x1=3 x2=21 y1=18 y2=18/>')}</button>
        <div class=cx-site>{site_ctrl}</div>
      </div>
      <div class=cx-credits><span id=cx-credits>{credits}</span> AI credits</div>
    </div>

    <div class=cx-log id=cx-log>
      <div class=cx-empty id=cx-empty>
        <h2 id=cx-greeting>Hello</h2>
        <p>How can I help with your WordPress site today?</p>
        <div class=cx-egs>
          <button class=cx-eg onclick="useEg(this)">Write a 1200-word SEO article about my topic and save it as a draft</button>
          <button class=cx-eg onclick="useEg(this)">Audit my latest post's SEO and fix the issues you find</button>
          <button class=cx-eg onclick="useEg(this)">Find my thin posts and suggest exactly how to improve each one</button>
        </div>
      </div>
      <div class=cx-log-inner id=cx-log-inner style=display:none></div>
    </div>

    <div class=cx-composer>
      <form class=cx-composer-inner onsubmit="return send(event)">
        <textarea id=cx-msg rows=1 placeholder="Message your site's AI…" {("" if chat_enabled else "disabled")}></textarea>
        <button class="cx-send" id="cx-send" type="submit" {("" if chat_enabled else "disabled")}><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#ffffff" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="19" x2="12" y2="5"/><polyline points="5 12 12 5 19 12"/></svg></button>
      </form>
      <p class=cx-hint>{("AI may make mistakes - review important changes on your site." if chat_enabled else "Built-in chat is coming soon.")}</p>
    </div>
  </main>
</div>

<span id=cx-logo-svg hidden>{av_logo}</span>
<span id=cx-trash-svg hidden>{_icon("<path d='M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6'/>")}</span>
<script>
var AV_LOGO=document.getElementById('cx-logo-svg').innerHTML;
var TRASH_SVG=document.getElementById('cx-trash-svg').innerHTML;
var convId=null, history=[], busy=false;
var logInner=document.getElementById('cx-log-inner'), empty=document.getElementById('cx-empty');

function activeSiteId(){{
  var el=document.getElementById('cx-site');
  if(!el) return '';
  return el.dataset.only || el.value || '';
}}
function mdToHtml(t){{
  // minimal markdown: bold, links, lists, paragraphs
  t=t.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  t=t.replace(/\\*\\*([^*]+)\\*\\*/g,'<strong>$1</strong>');
  t=t.replace(/\\[([^\\]]+)\\]\\(([^)]+)\\)/g,'<a href="$2" target=_blank rel=noopener>$1</a>');
  var lines=t.split(/\\n/), html='', inList=false;
  for(var i=0;i<lines.length;i++){{
    var ln=lines[i];
    var m=ln.match(/^\\s*[-*]\\s+(.*)/) || ln.match(/^\\s*\\d+\\.\\s+(.*)/) || ln.match(/^#+\\s+(.*)/);
    if(ln.match(/^#+\\s+/)){{ if(inList){{html+='</ul>';inList=false;}} html+='<p><strong>'+ln.replace(/^#+\\s+/,'')+'</strong></p>'; continue; }}
    if(m){{ if(!inList){{html+='<ul>';inList=true;}} html+='<li>'+m[1]+'</li>'; }}
    else {{ if(inList){{html+='</ul>';inList=false;}} if(ln.trim()) html+='<p>'+ln+'</p>'; }}
  }}
  if(inList) html+='</ul>';
  return html;
}}
function bubble(role, text, isMd){{
  empty.style.display='none'; logInner.style.display='';
  var d=document.createElement('div'); d.className='cm '+role;
  var av='<div class=av>'+(role==='user'?'You':AV_LOGO)+'</div>';
  var body='<div class=body>'+(isMd?mdToHtml(text):text.replace(/</g,'&lt;'))+'</div>';
  d.innerHTML=av+body; logInner.appendChild(d);
  document.getElementById('cx-log').scrollTop=1e9; return d;
}}

async function loadConvs(){{
  var r=await fetch('/api/conversations'); var d=await r.json();
  var box=document.getElementById('cx-convs'); box.innerHTML='';
  (d.conversations||[]).forEach(function(c){{
    var el=document.createElement('div'); el.className='cx-conv'+(c.id===convId?' active':'');
    el.innerHTML='<span class=t>'+c.title.replace(/</g,'&lt;')+'</span>'+
      '<span class=x title=Delete>'+TRASH_SVG+'</span>';
    el.querySelector('.t').onclick=function(){{openConv(c.id);}};
    el.querySelector('.x').onclick=function(e){{e.stopPropagation();delConv(c.id);}};
    box.appendChild(el);
  }});
}}
function newChat(){{
  // Just reset the UI. The conversation is created in the DB only when the
  // user sends their first message (so we never save empty chats).
  convId=null; history=[]; logInner.innerHTML=''; logInner.style.display='none'; empty.style.display='';
  loadConvs();
}}
async function openConv(id){{
  var r=await fetch('/api/conversations/'+id); if(!r.ok) return; var d=await r.json();
  convId=id; history=d.messages.map(function(m){{return {{role:m.role,content:m.content}};}});
  logInner.innerHTML='';
  if(history.length){{ logInner.style.display=''; empty.style.display='none';
    history.forEach(function(m){{bubble(m.role==='user'?'user':'ai',m.content,m.role!=='user');}});
  }} else {{ logInner.style.display='none'; empty.style.display=''; }}
  await loadConvs();
}}
async function delConv(id){{
  if(!confirm('Delete this chat?')) return;
  await fetch('/api/conversations/'+id,{{method:'DELETE'}});
  if(id===convId){{ convId=null; history=[]; logInner.innerHTML=''; empty.style.display=''; logInner.style.display='none'; }}
  await loadConvs();
}}
function useEg(b){{
  var m=document.getElementById('cx-msg');
  m.value=b.textContent.trim();
  m.style.height='auto'; m.style.height=Math.min(m.scrollHeight,180)+'px';
  m.focus();
}}

function thinkingBubble(){{
  empty.style.display='none'; logInner.style.display='';
  var d=document.createElement('div'); d.className='cm ai thinking';
  d.innerHTML='<div class=av>'+AV_LOGO+'</div><div class=body>'+
    '<div class=cx-steps id=cx-steps></div>'+
    '<div class=cx-nowstep><span class=cx-working>Thinking</span>'+
    '<div class=cx-dots><span></span><span></span><span></span></div></div></div>';
  logInner.appendChild(d); document.getElementById('cx-log').scrollTop=1e9;
  return d;
}}
function setStep(th, label){{
  if(!th) return;
  var steps=th.querySelector('#cx-steps'), now=th.querySelector('.cx-working');
  // mark previous step done
  if(now && now.textContent && now.textContent!=='Thinking'){{
    var done=document.createElement('div'); done.className='cx-step-done';
    done.innerHTML='<span class=cx-check>&#10003;</span> '+now.textContent;
    steps.appendChild(done);
  }}
  if(now) now.textContent=label;
  document.getElementById('cx-log').scrollTop=1e9;
}}
async function send(e){{
  e.preventDefault(); if(busy) return false;
  var inp=document.getElementById('cx-msg'); var txt=inp.value.trim(); if(!txt) return false;
  // Create the conversation in the DB now (on first message of this chat).
  if(!convId){{
    try{{ var cr=await fetch('/api/conversations',{{method:'POST'}}); var cd=await cr.json(); convId=cd.id; }}
    catch(e){{}}
  }}
  inp.value=''; inp.style.height='auto';
  bubble('user',txt,false); history.push({{role:'user',content:txt}});
  var th=thinkingBubble();
  busy=true; document.getElementById('cx-send').disabled=true;
  function clearTh(){{ if(th){{ th.remove(); th=null; }} }}
  var gotDone=false;
  try{{
    var r=await fetch('/chat/stream',{{method:'POST',headers:{{'Content-Type':'application/json'}},
      body:JSON.stringify({{messages:history,conv_id:convId,site_id:activeSiteId()}})}});
    if(!r.ok){{ var ed=await r.json(); clearTh(); bubble('ai',(ed.message||ed.error||'Something went wrong.'),false); busy=false; document.getElementById('cx-send').disabled=false; return false; }}
    // read SSE stream
    var reader=r.body.getReader(), dec=new TextDecoder(), buf='';
    while(true){{
      var chunk=await reader.read(); if(chunk.done) break;
      buf+=dec.decode(chunk.value,{{stream:true}});
      var parts=buf.split('\\n\\n'); buf=parts.pop();
      for(var pi=0;pi<parts.length;pi++){{
        var line=parts[pi].trim(); if(!line.indexOf('data: ')===0 && line.indexOf('data:')!==0) continue;
        var jtxt=line.replace(/^data:\\s*/,''); if(!jtxt) continue;
        var ev; try{{ ev=JSON.parse(jtxt); }}catch(e){{ continue; }}
        if(ev.type==='step'){{ setStep(th,ev.label); }}
        else if(ev.type==='thinking'){{ setStep(th,'Thinking'); }}
        else if(ev.type==='error'){{ clearTh(); bubble('ai','Error: '+(ev.message||'something went wrong'),false); }}
        else if(ev.type==='done'){{
          gotDone=true; clearTh();
          bubble('ai',ev.reply||'(no reply)',true);
          history.push({{role:'assistant',content:ev.reply||''}});
          if(typeof ev.credits_left==='number') document.getElementById('cx-credits').textContent=ev.credits_left;
          if(ev.stopped_early) bubble('ai','You ran out of AI credits mid-task. Buy more or upgrade to continue.',false);
          loadConvs();
        }}
      }}
    }}
    if(!gotDone){{ throw new Error('stream ended'); }}
  }}catch(err){{
    // Timeout / dropped connection. The server may have finished and saved the
    // AI reply to this conversation - poll for it a few times before giving up.
    var recovered=false;
    if(convId){{
      for(var attempt=0; attempt<12 && !recovered; attempt++){{
        await new Promise(function(res){{setTimeout(res,5000);}});
        try{{
          var cr=await fetch('/api/conversations/'+convId);
          if(cr.ok){{
            var cd=await cr.json();
            var last=cd.messages && cd.messages[cd.messages.length-1];
            if(last && last.role==='assistant'){{
              clearTh();
              bubble('ai',last.content,true);
              history.push({{role:'assistant',content:last.content}});
              loadConvs();
              // refresh credits
              try{{ var br=await fetch('/api/token-balance'); if(br.ok){{var bd=await br.json(); if(typeof bd.credits==='number') document.getElementById('cx-credits').textContent=bd.credits;}} }}catch(e){{}}
              recovered=true;
            }}
          }}
        }}catch(e){{}}
      }}
    }}
    if(!recovered){{ clearTh(); bubble('ai','This is taking a while - your task may still be running in the background. Give it a moment, then refresh this page to see the result.',false); }}
  }}
  busy=false; document.getElementById('cx-send').disabled=false; return false;
}}
document.getElementById('cx-msg').addEventListener('input',function(e){{e.target.style.height='auto';e.target.style.height=Math.min(e.target.scrollHeight,180)+'px';}});
document.getElementById('cx-msg').addEventListener('keydown',function(e){{if(e.key==='Enter'&&!e.shiftKey){{e.preventDefault();send(e);}}}});
// time-based greeting like Claude
(function(){{
  var hr=new Date().getHours();
  var g = hr<5 ? 'Good evening' : hr<12 ? 'Good morning' : hr<17 ? 'Good afternoon' : hr<21 ? 'Good evening' : 'Working late';
  var el=document.getElementById('cx-greeting'); if(el) el.textContent=g;
}})();
loadConvs();
// One-click "Fix with Claude": /chat?ask=... auto-fills and sends the command.
(function(){{
  try{{
    var qs=new URLSearchParams(location.search); var ask=qs.get('ask');
    if(ask){{
      var inp=document.getElementById('cx-msg');
      inp.value=ask;
      // clean the URL so a refresh doesn't resend.
      if(history.replaceState) history.replaceState(null,'',location.pathname);
      setTimeout(function(){{ send(new Event('submit')); }}, 500);
    }}
  }}catch(e){{}}
}})();
</script>
</body></html>"""
