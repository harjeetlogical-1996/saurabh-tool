"""
wptaskify owner admin panel (private).

Secret-URL + password gated dashboard for the site owner only. Shows users,
payments/revenue, usage, and lets you manually change a user's plan, add image
credits, or delete a user. NOT linked from anywhere public.

Access: set ADMIN_PATH (secret slug, e.g. "sb-console-9f3") and ADMIN_PASSWORD
in the environment. Visit /<ADMIN_PATH>, enter the password, get a session
cookie signed with ADMIN_PASSWORD. All routes live under /<ADMIN_PATH>/...
"""
import os
import html
import hmac
import hashlib
import base64
import time
import urllib.parse

import db

ADMIN_PATH = os.environ.get("ADMIN_PATH", "").strip("/")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
_COOKIE = "wtadmin"
_SESSION_HOURS = 12


def enabled():
    return bool(ADMIN_PATH and ADMIN_PASSWORD)


def base_path():
    return "/" + ADMIN_PATH


# --- session cookie (HMAC-signed, no DB) --------------------------------------
def _sign(exp: int) -> str:
    msg = str(exp).encode()
    sig = hmac.new(ADMIN_PASSWORD.encode(), msg, hashlib.sha256).hexdigest()[:32]
    return base64.urlsafe_b64encode(msg).decode() + "." + sig


def make_cookie() -> str:
    exp = int(time.time()) + _SESSION_HOURS * 3600
    val = _sign(exp)
    # SameSite=Strict (not Lax): the admin cookie is never sent on ANY cross-site request,
    # including top-level navigations - so a cross-site POST to a destructive admin action
    # (ban/delete/refund) simply isn't authenticated. Strong CSRF defense for the panel.
    return (f"{_COOKIE}={val}; Path={base_path()}; HttpOnly; SameSite=Strict; "
            f"Max-Age={_SESSION_HOURS * 3600}; Secure")


def clear_cookie() -> str:
    return f"{_COOKIE}=; Path={base_path()}; HttpOnly; Max-Age=0"


def _valid_cookie(raw: str) -> bool:
    if not raw:
        return False
    for part in raw.split(";"):
        part = part.strip()
        if part.startswith(_COOKIE + "="):
            token = part[len(_COOKIE) + 1:]
            try:
                b64, sig = token.split(".", 1)
                exp = int(base64.urlsafe_b64decode(b64).decode())
            except Exception:
                return False
            if exp < time.time():
                return False
            good = hmac.new(ADMIN_PASSWORD.encode(), str(exp).encode(),
                            hashlib.sha256).hexdigest()[:32]
            return hmac.compare_digest(good, sig)
    return False


def is_authed(cookie_header: str) -> bool:
    return _valid_cookie(cookie_header or "")


def check_password(pw: str) -> bool:
    return bool(pw) and hmac.compare_digest(pw, ADMIN_PASSWORD)


# --- HTML ---------------------------------------------------------------------
def _e(x):
    return html.escape(str(x if x is not None else ""))


_FONTS = ("<link rel=preconnect href=https://fonts.googleapis.com>"
          "<link rel=preconnect href=https://fonts.gstatic.com crossorigin>"
          "<link href=\"https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600"
          "&family=Sora:wght@400;500;600;700;800&display=swap\" rel=stylesheet>")

_CSS = """
:root{--accent:#F97316;--accent-hi:#FB923C;--ink:#14131A;--muted:#5B5966;--muted2:#8A8792;
  --line:#E9E8EF;--bg:#F7F6FA;--surface:#FFFFFF;--green:#059669;--red:#DC2626}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Inter',-apple-system,BlinkMacSystemFont,sans-serif;
  background:var(--bg);color:var(--ink);line-height:1.5;-webkit-font-smoothing:antialiased}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
h1,h2,h3,.brand,.stat b,.btn,.nav a,th{font-family:'Sora',sans-serif}
/* ---- dark sidebar + WHITE content ---- */
.layout{display:flex;min-height:100vh}
.side{position:fixed;top:0;left:0;bottom:0;width:236px;background:#0F0E13;
  display:flex;flex-direction:column;padding:22px 16px;z-index:20}
.side .brand{font-weight:800;font-size:1.15rem;color:#fff;padding:0 8px 20px;
  border-bottom:1px solid #23222b;margin-bottom:16px}
.brand b{color:var(--accent-hi)}
.brand span{display:block;color:#6b6a75;font-family:'Inter';font-weight:500;font-size:.76rem;margin-top:3px}
.nav{display:flex;flex-direction:column;gap:4px;flex:1}
.nav a{display:flex;align-items:center;gap:11px;padding:11px 12px;border-radius:10px;
  color:#b6b5bf;font-size:.92rem;font-weight:500}
.nav a:hover{background:#1b1a22;text-decoration:none;color:#fff}
.nav a.on{background:var(--accent);color:#fff;font-weight:600}
.nav a svg{width:18px;height:18px;flex-shrink:0;stroke:#8a8792}
.nav a.on svg,.nav a:hover svg{stroke:currentColor}
.side .logout{margin-top:auto;padding:11px 12px;border-radius:10px;color:#8a8792;
  font-family:'Inter';font-size:.9rem;border:1px solid #23222b;text-align:center}
.side .logout:hover{border-color:var(--accent);color:#fff;text-decoration:none}
.content{flex:1;margin-left:236px;min-width:0;background:var(--bg)}
.wrap{max-width:1120px;margin:0 auto;padding:0 34px}
main{padding:34px 0 64px}
@media(max-width:900px){
  .side{position:static;width:100%;flex-direction:row;flex-wrap:wrap;align-items:center;padding:12px 16px}
  .side .brand{border:0;padding:0;margin:0 auto 0 0;font-size:1rem}
  .side .brand span{display:none}
  .nav{flex-direction:row;flex:0;flex-wrap:wrap;gap:4px}
  .nav a span{display:none}
  .side .logout{margin:0 0 0 4px;padding:9px 11px}
  .content{margin-left:0}.wrap{padding:0 18px}
}
h1{font-size:1.7rem;margin-bottom:4px;letter-spacing:-.02em}
.muted{color:var(--muted2)}.sub{color:var(--muted);margin-bottom:26px;font-size:.98rem}
/* stat cards - white */
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:26px}
.stat{background:var(--surface);border:1px solid var(--line);border-radius:16px;padding:20px;
  box-shadow:0 6px 24px -18px rgba(20,19,26,.15)}
.stat b{display:block;font-size:1.8rem;font-weight:800;line-height:1.1;color:var(--ink)}
.stat span{color:var(--muted2);font-size:.83rem}
.stat.rev b{color:var(--green)}
.stat .delta{font-size:.78rem;font-weight:600;margin-left:6px}
.stat .up{color:var(--green)}.stat .down{color:var(--red)}
/* cards - white */
.card{background:var(--surface);border:1px solid var(--line);border-radius:16px;padding:22px;margin-bottom:20px;
  box-shadow:0 6px 24px -18px rgba(20,19,26,.12)}
.card h2{font-size:1.08rem;margin-bottom:16px;color:var(--ink)}
table{width:100%;border-collapse:collapse;font-size:.92rem}
th,td{text-align:left;padding:11px 12px;border-bottom:1px solid var(--line)}
th{color:var(--muted2);font-size:.76rem;text-transform:uppercase;letter-spacing:.05em;font-weight:600}
td{color:var(--muted)}tbody tr:hover td{background:#FBF9FC}
td a{color:var(--ink);font-weight:600}td a:hover{color:var(--accent)}
.pill{display:inline-block;padding:2px 10px;border-radius:999px;font-size:.74rem;font-weight:600;font-family:'Sora'}
.pill.free{background:#F1F0F5;color:#6B6A75}
.pill.paid{background:rgba(5,150,105,.12);color:var(--green)}
.pill.on{background:rgba(5,150,105,.12);color:var(--green)}
.pill.off{background:rgba(220,38,38,.1);color:var(--red)}
.search{width:100%;max-width:380px;padding:11px 15px;border:1px solid #E0DEE8;border-radius:11px;
  background:#fff;color:var(--ink);font-family:'Inter';font-size:.95rem;margin-bottom:18px;outline:none}
.search:focus{border-color:var(--accent);box-shadow:0 0 0 3px rgba(249,115,22,.1)}
.btn{display:inline-block;padding:9px 16px;border-radius:10px;border:1px solid #E0DEE8;
  background:#fff;color:var(--ink);font-size:.88rem;font-weight:600;cursor:pointer;text-decoration:none}
.btn:hover{border-color:var(--accent);text-decoration:none}
.btn.primary{background:var(--accent);color:#fff;border-color:var(--accent)}
.btn.primary:hover{background:#EA580C}
.btn.danger{color:var(--red);border-color:#F3C9C9}
.btn.danger:hover{background:#FEF2F2}
.row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:20px}
.grid3{display:grid;grid-template-columns:2fr 1fr;gap:20px}
form.inline{display:inline}
select,input.inp{padding:9px 13px;border:1px solid #E0DEE8;border-radius:10px;background:#fff;
  color:var(--ink);font-family:'Inter';font-size:.9rem;outline:none}
select:focus,input.inp:focus{border-color:var(--accent)}
.bars{display:grid;gap:10px}
.bar{display:grid;grid-template-columns:190px 1fr 56px;gap:12px;align-items:center;font-size:.9rem}
.bar>span:first-child{color:var(--ink);font-weight:500}
.bar .track{background:#F1F0F5;border-radius:7px;height:24px;overflow:hidden}
.bar .fill{background:linear-gradient(90deg,#fb923c,#fbbf24);height:100%;border-radius:7px}
.bar .n{text-align:right;color:var(--muted2);font-weight:600}
.section-label{font-family:'Sora';font-weight:700;font-size:.8rem;text-transform:uppercase;
  letter-spacing:.06em;color:var(--muted2);margin:6px 0 12px}
.crumb{color:var(--muted2);font-size:.9rem;margin-bottom:8px}
.crumb a{color:var(--muted2)}.crumb a:hover{color:var(--accent)}
/* login */
.login-box{max-width:380px;margin:13vh auto;background:#141319;border:1px solid #23222b;
  border-radius:18px;padding:36px}
.login-box h1{text-align:center;margin-bottom:6px;color:#fff}
.login-box p{text-align:center;color:#8a8792;margin-bottom:24px;font-size:.9rem}
.login-box input{width:100%;padding:13px 15px;border:1px solid #2b2a33;border-radius:11px;
  background:#0f0e13;color:#e7e6ea;font-family:'Inter';font-size:1rem;margin-bottom:14px;outline:none}
.login-box input:focus{border-color:var(--accent)}
.login-box .btn{width:100%;text-align:center;padding:13px;background:var(--accent);color:#fff;border-color:var(--accent)}
.err{background:#FEF2F2;border:1px solid #F3C9C9;color:var(--red);
  padding:11px 15px;border-radius:11px;margin-bottom:16px;font-size:.9rem}
.login-box .err{background:rgba(220,38,38,.12);border-color:rgba(220,38,38,.3);color:#f87171}
.ok{background:rgba(5,150,105,.1);border:1px solid rgba(5,150,105,.25);color:var(--green);
  padding:11px 15px;border-radius:11px;margin-bottom:18px;font-size:.9rem}
@media(max-width:820px){.stats{grid-template-columns:1fr 1fr}.grid2,.grid3{grid-template-columns:1fr}
  .bar{grid-template-columns:120px 1fr 44px}table{font-size:.84rem}th,td{padding:9px 8px}}
/* ---- owner-admin additions ---- */
.tbl-wrap{overflow-x:auto;-webkit-overflow-scrolling:touch}
.btn.secondary{background:#F5F4F8;border-color:#E0DEE8}
.btn.secondary:hover{background:#EEECF3;border-color:var(--accent)}
.btn.ghost{background:transparent;border-color:transparent;color:var(--muted)}
.btn.ghost:hover{background:#F5F4F8;color:var(--ink)}
.btn.mini{padding:5px 11px;font-size:.8rem}
.btn.loginas{background:#0F0E13;color:#fff;border-color:#0F0E13}
.btn.loginas:hover{background:#23222b;color:#fff}
.filters{display:flex;gap:10px;align-items:end;flex-wrap:wrap;margin-bottom:18px}
.filters .fld{display:flex;flex-direction:column;gap:5px}
.filters label{font-size:.74rem;font-weight:600;color:var(--muted2);text-transform:uppercase;letter-spacing:.04em}
.filters .chk{flex-direction:row;align-items:center;gap:7px}
.filters .chk label{text-transform:none;font-size:.9rem;letter-spacing:0;color:var(--ink);font-weight:500}
.filters input.inp,.filters select{min-width:150px}
.controls-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}
@media(max-width:900px){.controls-grid{grid-template-columns:repeat(2,1fr)}}
@media(max-width:620px){.controls-grid{grid-template-columns:1fr}}
.ctl{border:1px solid var(--line);border-radius:12px;padding:14px;background:#FCFBFE}
.ctl label{display:block;font-size:.78rem;font-weight:600;color:var(--muted2);margin-bottom:8px;
  text-transform:uppercase;letter-spacing:.04em;font-family:'Sora'}
.ctl .row{gap:8px}
.ctl input.inp,.ctl select{flex:1;min-width:0}
.ctl .hint{font-size:.76rem;color:var(--muted2);margin-top:7px;line-height:1.4}
.danger-zone{border-color:rgba(220,38,38,.35);background:linear-gradient(0deg,rgba(220,38,38,.03),rgba(220,38,38,.03)),#fff}
.danger-zone h2{color:var(--red)}
.activity-log{max-height:320px;overflow-y:auto;border:1px solid var(--line);border-radius:12px}
.activity-log .ev{display:flex;justify-content:space-between;gap:12px;padding:9px 14px;
  border-bottom:1px solid var(--line);font-size:.88rem}
.activity-log .ev:last-child{border-bottom:0}
.activity-log .ev .k{color:var(--ink);font-weight:500}
.activity-log .ev .t{color:var(--muted2);font-size:.82rem;white-space:nowrap}
.chart svg{display:block;width:100%;height:auto}
.chart .cap{display:flex;justify-content:space-between;font-size:.78rem;color:var(--muted2);margin-top:6px}
.sys-rows{display:flex;flex-direction:column;gap:2px}
.sys-row{display:flex;justify-content:space-between;align-items:center;gap:12px;
  padding:13px 4px;border-bottom:1px solid var(--line);font-size:.94rem}
.sys-row:last-child{border-bottom:0}
.sys-row .lbl{font-weight:500;color:var(--ink)}
.sys-row .lbl small{display:block;color:var(--muted2);font-weight:400;font-size:.8rem;margin-top:2px;font-family:'Inter'}
.note{background:#FFFBEB;border:1px solid #FDE68A;color:#92660A;padding:12px 15px;
  border-radius:11px;font-size:.86rem;line-height:1.5;margin-bottom:18px}
/* ---- user moderation additions ---- */
.pill.active{background:rgba(5,150,105,.1);color:var(--green)}
.ban-banner{background:#FEF2F2;border:1px solid #F3C9C9;color:var(--red);
  border-radius:14px;padding:16px 18px;margin-bottom:20px;display:flex;
  justify-content:space-between;align-items:center;gap:16px;flex-wrap:wrap}
.ban-banner .msg{font-weight:600;font-size:.95rem}
.note-card{background:#FFFBEB;border:1px solid #FDE68A}
.note-card h2{color:#92660A}
.note-card textarea{width:100%;min-height:90px;padding:11px 13px;border:1px solid #FDE68A;
  border-radius:10px;background:#FFFEF8;color:var(--ink);font-family:'Inter';font-size:.9rem;
  line-height:1.5;outline:none;resize:vertical;margin-bottom:12px}
.note-card textarea:focus{border-color:var(--accent)}
.bulk-bar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;background:#F1F0F5;
  border:1px solid var(--line);border-radius:12px;padding:12px 14px;margin-bottom:14px}
.bulk-bar .lbl{font-family:'Sora';font-weight:600;font-size:.82rem;color:var(--muted2);
  text-transform:uppercase;letter-spacing:.04em}
th.chkcol,td.chkcol{width:34px;padding-right:0}
/* usage page: header + date-range toggle */
.usage-head{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;flex-wrap:wrap}
.rngbar{display:inline-flex;background:#F1F0F5;border:1px solid var(--line);border-radius:11px;padding:3px;gap:2px}
.rng{padding:7px 14px;border-radius:8px;font-family:'Sora';font-weight:600;font-size:.85rem;
  color:var(--muted);text-decoration:none}
.rng:hover{color:var(--ink);text-decoration:none}
.rng.on{background:var(--accent);color:#fff}
"""


_ICONS = {
    "dash": '<path d="M3 3h7v7H3zM14 3h7v7h-7zM14 14h7v7h-7zM3 14h7v7H3z"/>',
    "users": '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>',
    "pay": '<rect x="1" y="4" width="22" height="16" rx="2"/><line x1="1" y1="10" x2="23" y2="10"/>',
    "usage": '<line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/>',
    "sys": '<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>',
    "coupon": '<path d="M9 11H5a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-6a2 2 0 0 0-2-2h-4M9 11V4a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v7M9 11h6M12 15v3"/>',
    "plans": '<path d="M12 2 2 7l10 5 10-5-10-5Z"/><path d="m2 17 10 5 10-5M2 12l10 5 10-5"/>',
    "emails": '<rect x="2" y="4" width="20" height="16" rx="2"/><path d="m22 7-10 5L2 7"/>',
    "tax": '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M9 15 15 9M9.5 9h.01M14.5 15h.01"/>',
    "social": '<circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.6" y1="10.7" x2="15.4" y2="6.3"/><line x1="8.6" y1="13.3" x2="15.4" y2="17.7"/>',
    "seo": '<circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/><path d="M8 11h6M11 8v6"/>',
    "forum": '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
    "aff": '<circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.6" y1="10.7" x2="15.4" y2="6.3"/><line x1="8.6" y1="13.3" x2="15.4" y2="17.7"/>',
    "blog": '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>',
}


def _ic(key):
    return (f'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
            f'stroke-linecap="round" stroke-linejoin="round">{_ICONS[key]}</svg>')


def _shell(title, active, inner, flash=""):
    b = base_path()
    nav = "".join(
        f'<a href="{b}{href}" class="{"on" if active == key else ""}">{_ic(key)}<span>{label}</span></a>'
        for key, href, label in [
            ("dash", "", "Dashboard"),
            ("users", "/users", "Users"),
            ("pay", "/payments", "Payments"),
            ("plans", "/plans", "Plans"),
            ("coupon", "/coupons", "Coupons"),
            ("tax", "/tax", "Tax / GST"),
            ("emails", "/emails", "Emails"),
            ("social", "/social", "Social links"),
            ("seo", "/seo", "Analytics / SEO"),
            ("forum", "/forum", "Community"),
            ("aff", "/affiliates", "Affiliates"),
            ("blog", "/blog", "Blog"),
            ("usage", "/usage", "Usage"),
            ("sys", "/system", "System"),
        ])
    flash_html = f'<div class="ok">{_e(flash)}</div>' if flash else ""
    return (f"<!doctype html><html lang=en><head><meta charset=utf-8>"
            f"<meta name=viewport content='width=device-width,initial-scale=1'>"
            f"<meta name=robots content='noindex,nofollow'>"
            f"<title>{_e(title)} · wptaskify admin</title>{_FONTS}<style>{_CSS}</style></head><body>"
            f"<div class=layout>"
            f"<aside class=side>"
            f"<div class=brand>wp<b>taskify</b><span>owner admin</span></div>"
            f"<nav class=nav>{nav}</nav>"
            f"<a href='{b}/logout' class=logout>Log out</a>"
            f"</aside>"
            f"<div class=content><main><div class=wrap>{flash_html}{inner}</div></main></div>"
            f"</div></body></html>")


def login_page(error=""):
    err = f'<div class="err">{_e(error)}</div>' if error else ""
    return (f"<!doctype html><html lang=en><head><meta charset=utf-8>"
            f"<meta name=viewport content='width=device-width,initial-scale=1'>"
            f"<meta name=robots content='noindex,nofollow'>"
            f"<title>Admin · wptaskify</title>{_FONTS}<style>{_CSS}</style></head><body>"
            f"<form class=login-box method=post action='{base_path()}/login'>"
            f"<h1>wp<b style='color:#fb923c'>taskify</b> admin</h1>"
            f"<p>Owner access only.</p>{err}"
            f"<input type=password name=password placeholder='Admin password' autofocus required>"
            f"<button class='btn primary' type=submit>Enter</button>"
            f"</form></body></html>")


def _money(x, currency="INR"):
    """Format an amount with the right symbol. Defaults to INR (this is an
    India-based business - most payments are in rupees via Razorpay)."""
    sym = "₹" if currency == "INR" else "$"
    try:
        return f"{sym}{float(x):,.0f}" if currency == "INR" else f"{sym}{float(x):,.2f}"
    except (TypeError, ValueError):
        return f"{sym}0"


def _svg_bars(data, color="#F97316", height=120):
    """Inline SVG bar chart. data = list of (label, value). No JS, no libs.
    Scales to the max value; labels roughly every 5th bar on the x-axis."""
    data = list(data or [])
    if not data:
        return '<p class=muted>No data yet.</p>'
    n = len(data)
    W = 640
    pad_l, pad_r, pad_t, pad_b = 6, 6, 8, 20
    plot_h = height - pad_t - pad_b
    plot_w = W - pad_l - pad_r
    vals = [float(v or 0) for _, v in data]
    mx = max(vals) or 1.0
    gap = 2 if n <= 60 else 1
    slot = plot_w / n
    bw = max(1.0, slot - gap)
    bars = []
    labels = []
    for i, (lbl, v) in enumerate(data):
        v = float(v or 0)
        bh = (v / mx) * plot_h
        x = pad_l + i * slot
        y = pad_t + (plot_h - bh)
        bars.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{bh:.1f}" '
            f'rx="1.5" fill="{color}"><title>{_e(lbl)}: {_e(v)}</title></rect>')
        if i % 5 == 0 or i == n - 1:
            tx = x + bw / 2
            labels.append(
                f'<text x="{tx:.1f}" y="{height-6}" font-size="9" fill="#8A8792" '
                f'font-family="Inter,sans-serif" text-anchor="middle">{_e(lbl)}</text>')
    return (
        f'<div class=chart><svg viewBox="0 0 {W} {height}" '
        f'preserveAspectRatio="none" role="img">'
        f'<line x1="{pad_l}" y1="{pad_t+plot_h:.1f}" x2="{W-pad_r}" y2="{pad_t+plot_h:.1f}" '
        f'stroke="#E9E8EF" stroke-width="1"/>'
        f'{"".join(bars)}{"".join(labels)}</svg></div>')


def dashboard_page(flash=""):
    s = db.admin_stats()
    b = base_path()
    conv = round(s["paid"] / s["total_users"] * 100, 1) if s["total_users"] else 0
    # Revenue is shown per currency - INR and USD are different money and are never summed.
    def _rev2(inr, usd):
        return f'{_money(inr, "INR")} <small style="opacity:.6">+ {_money(usd, "USD")}</small>'
    stats = "".join([
        f'<div class=stat><b>{s["total_users"]}</b><span>Total users '
        f'<span class="delta up">+{s["new_7d"]} this week</span></span></div>',
        f'<div class=stat><b>{s["paid"]}</b><span>Paid users · {conv}% conversion</span></div>',
        f'<div class=stat><b>{s["sites"]}</b><span>Connected sites</span></div>',
        f'<div class=stat><b>{s["verified"]}</b><span>Verified emails</span></div>',
        f'<div class="stat rev"><b>{_rev2(s["rev_inr"], s["rev_usd"])}</b><span>Total revenue</span></div>',
        f'<div class="stat rev"><b>{_rev2(s["rev30_inr"], s["rev30_usd"])}</b><span>Revenue (30 days)</span></div>',
        f'<div class=stat><b>{s["txns"]}</b><span>Completed payments</span></div>',
    ])

    # plan breakdown as bars
    mx = max((n for _, n in s["plans"]), default=1)
    plan_bars = "".join(
        f'<div class=bar><span><span class="pill {"paid" if p!="free" else "free"}">{_e(p)}</span></span>'
        f'<div class=track><div class=fill style="width:{max(4,int(n/mx*100))}%"></div></div>'
        f'<span class=n>{n}</span></div>' for p, n in s["plans"])

    # recent signups (first 6)
    recent = db.admin_list_users(limit=6)
    sign_rows = "".join(
        f'<tr><td><a href="{b}/user/{u["id"]}">{_e(u["email"])}</a></td>'
        f'<td><span class="pill {"paid" if u["plan"]!="free" else "free"}">{_e(u["plan"])}</span></td>'
        f'<td class=muted>{_e(u["created_at"][:10])}</td></tr>' for u in recent) \
        or '<tr><td colspan=3 class=muted>No users yet</td></tr>'

    # recent payments (first 6)
    pays = db.admin_recent_transactions(limit=6)
    pay_rows = "".join(
        f'<tr><td><a href="{b}/user/{t["user_id"]}">{_e(t["email"])}</a></td>'
        f'<td>{_e(t["item"])}</td><td>{_money(t["amount"], t.get("currency","INR"))}</td>'
        f'<td class=muted>{_e(t["created_at"][:10])}</td></tr>' for t in pays) \
        or '<tr><td colspan=4 class=muted>No payments yet</td></tr>'

    # usage top tools (top 6)
    tools = db.admin_top_tools(limit=6)
    tmx = max((n for _, n in tools), default=1)
    tool_bars = "".join(
        f'<div class=bar><span>{_e(k)}</span>'
        f'<div class=track><div class=fill style="width:{max(4,int(n/tmx*100))}%"></div></div>'
        f'<span class=n>{n}</span></div>' for k, n in tools) \
        or '<p class=muted>No usage in the last 30 days.</p>'

    # 30-day charts (pure inline SVG)
    signups = db.admin_signups_daily(30)
    revenue = db.admin_revenue_daily(30)
    signup_total = sum(v for _, v in signups)
    rev_total_30 = sum(v for _, v in revenue)
    signup_chart = _svg_bars(signups, color="#F97316")
    rev_chart = _svg_bars(revenue, color="#059669")

    return _shell("Dashboard", "dash", (
        f'<h1>Dashboard</h1><p class=sub>Live overview of wptaskify.</p>'
        f'<div class=stats>{stats}</div>'
        f'<div class=grid2>'
        f'<div class=card><h2>Signups (30 days)</h2>{signup_chart}'
        f'<div class="cap" style="display:flex;justify-content:space-between;'
        f'font-size:.78rem;color:var(--muted2);margin-top:6px">'
        f'<span>{signups[0][0] if signups else ""}</span>'
        f'<span>{signup_total} new users</span>'
        f'<span>{signups[-1][0] if signups else ""}</span></div></div>'
        f'<div class=card><h2>Revenue (30 days)</h2>{rev_chart}'
        f'<div class="cap" style="display:flex;justify-content:space-between;'
        f'font-size:.78rem;color:var(--muted2);margin-top:6px">'
        f'<span>{revenue[0][0] if revenue else ""}</span>'
        f'<span>{_money(rev_total_30)}</span>'
        f'<span>{revenue[-1][0] if revenue else ""}</span></div></div>'
        f'</div>'
        f'<div class=grid3>'
        f'<div class=card><h2>Recent signups</h2>'
        f'<table><thead><tr><th>Email</th><th>Plan</th><th>Joined</th></tr></thead>'
        f'<tbody>{sign_rows}</tbody></table>'
        f'<div class=row style="margin-top:14px"><a class=btn href="{b}/users">View all users</a></div></div>'
        f'<div class=card><h2>Users by plan</h2><div class=bars>{plan_bars}</div></div>'
        f'</div>'
        f'<div class=grid2>'
        f'<div class=card><h2>Recent payments</h2>'
        f'<table><thead><tr><th>User</th><th>Item</th><th>Amount</th><th>Date</th></tr></thead>'
        f'<tbody>{pay_rows}</tbody></table>'
        f'<div class=row style="margin-top:14px"><a class=btn href="{b}/payments">All payments</a></div></div>'
        f'<div class=card><h2>Top actions (30 days)</h2><div class=bars>{tool_bars}</div>'
        f'<div class=row style="margin-top:14px"><a class=btn href="{b}/usage">Full usage</a></div></div>'
        f'</div>'
    ), flash)


def users_page(search="", plan="", verified="", paid="", sort="created_at", flash=""):
    import urllib.parse
    b = base_path()
    users = db.admin_users_filtered(search, plan, verified,
                                    paid_only=(paid == "1"), sort=sort)
    plan_opts_list = db.admin_plan_options()

    # filter bar
    def _sel(name, current, options, all_label="All"):
        opts = [f'<option value="" {"selected" if current=="" else ""}>{all_label}</option>']
        for val, lbl in options:
            opts.append(f'<option value="{_e(val)}" '
                        f'{"selected" if current==val else ""}>{_e(lbl)}</option>')
        return f'<select name={name} class=inp>{"".join(opts)}</select>'

    plan_select = _sel("plan", plan, [(p, p) for p in plan_opts_list], "All plans")
    verified_select = _sel("verified", verified, [("yes", "Verified"), ("no", "Unverified")])
    sort_select = _sel("sort", sort, [
        ("created_at", "Newest"), ("email", "Email"),
        ("plan", "Plan"), ("spent", "Spent")], "Newest") if sort else ""
    # sort has no real "all" state -> render explicitly with Newest default
    sort_opts = "".join(
        f'<option value="{v}" {"selected" if sort==v else ""}>{lbl}</option>'
        for v, lbl in [("created_at", "Newest"), ("email", "Email"),
                       ("plan", "Plan"), ("spent", "Spent")])
    sort_select = f'<select name=sort class=inp>{sort_opts}</select>'

    qs = urllib.parse.urlencode({"q": search, "plan": plan, "verified": verified,
                                 "paid": paid, "sort": sort})
    csv_href = f"{b}/users.csv?{qs}"

    rows = ""
    for u in users:
        plan_cls = "paid" if u["plan"] != "free" else "free"
        vr = ('<span class="pill on">yes</span>' if u["verified"]
              else '<span class="pill off">no</span>')
        status = ('<span class="pill off">suspended</span>'
                  if u.get("status") == "banned" else '<span class=muted>—</span>')
        if u["site_url"]:
            disp = (u["site_url"] or "").replace("https://", "").replace("http://", "")
            site = (f'<a href="{_e(u["site_url"])}" target=_blank rel=noopener>'
                    f'{_e(disp)}</a>')
        else:
            site = '<span class=muted>—</span>'
        last = _e(u["last_active"][:10]) if u.get("last_active") else '<span class=muted>—</span>'
        rows += (
            f'<tr><td class=chkcol><input type=checkbox class=ub name=uid value="{_e(u["id"])}"></td>'
            f'<td><a href="{b}/user/{u["id"]}">{_e(u["email"])}</a></td>'
            f'<td><span class="pill {plan_cls}">{_e(u["plan"])}</span></td>'
            f'<td>{vr}</td><td>{status}</td><td>{u["sites"]}</td><td>{site}</td>'
            f'<td>{_money(u["spent"], "INR")}{(" + " + _money(u["spent_usd"], "USD")) if u.get("spent_usd") else ""}</td>'
            f'<td class=muted>{last}</td>'
            f'<td class=muted>{_e(u["created_at"][:10])}</td></tr>')
    if not rows:
        rows = ('<tr><td colspan=10 class=muted style="text-align:center;padding:24px">'
                'No users found</td></tr>')

    paid_checked = "checked" if paid == "1" else ""
    filter_bar = (
        f'<form method=get action="{b}/users" class=filters>'
        f'<div class=fld><label>Search</label>'
        f'<input class=inp name=q value="{_e(search)}" placeholder="email..."></div>'
        f'<div class=fld><label>Plan</label>{plan_select}</div>'
        f'<div class=fld><label>Verified</label>{verified_select}</div>'
        f'<div class=fld><label>Sort</label>{sort_select}</div>'
        f'<div class="fld chk"><input type=checkbox name=paid value=1 id=paidonly {paid_checked}>'
        f'<label for=paidonly>Paid only</label></div>'
        f'<button class="btn primary" type=submit>Filter</button>'
        f'<a class="btn secondary" href="{b}/users">Reset</a>'
        f'</form>')

    # bulk-action plan select (reuse the plan options)
    bulk_plan_opts = "".join(
        f'<option value="{_e(p)}">{_e(p)}</option>' for p in plan_opts_list)
    bulk_bar = (
        f'<div class=bulk-bar><span class=lbl>Bulk</span>'
        f'<select name=action class=inp>'
        f'<option value="">— choose —</option>'
        f'<option value="ban">Ban selected</option>'
        f'<option value="unban">Un-ban selected</option>'
        f'<option value="plan">Change plan</option>'
        f'<option value="delete">Delete selected</option>'
        f'</select>'
        f'<select name=value class=inp>{bulk_plan_opts}</select>'
        f'<button class="btn primary" type=submit>Apply to selected</button></div>')

    return _shell("Users", "users", (
        f'<h1>Users</h1><p class=sub>{len(users)} shown.</p>'
        f'{filter_bar}'
        f'<div class=row style="margin-bottom:14px"><a class="btn secondary" '
        f'href="{_e(csv_href)}">Download CSV</a></div>'
        f'<form method=post action="{b}/bulk" id=bulkform '
        f'onsubmit="return confirm(\'Apply to the selected users?\')">'
        f'{bulk_bar}'
        f'<div class=card><div class=tbl-wrap><table><thead><tr>'
        f'<th class=chkcol><input type=checkbox onclick="for(var c of '
        f'document.querySelectorAll(\'.ub\'))c.checked=this.checked"></th>'
        f'<th>Email</th><th>Plan</th><th>Verified</th><th>Status</th><th>Sites</th>'
        f'<th>Primary site</th><th>Spent</th><th>Last active</th><th>Joined</th></tr></thead>'
        f'<tbody>{rows}</tbody></table></div></div>'
        f'</form>'
    ), flash)


def user_detail_page(user_id, flash=""):
    u = db.admin_get_user(user_id)
    b = base_path()
    if not u:
        return _shell("User", "users", '<h1>User not found</h1>'
                      f'<p><a href="{b}/users">← Back to users</a></p>')

    activity = db.admin_user_activity(user_id)
    all_txns = db.admin_all_user_txns(user_id)
    # Spent per currency (INR / USD kept separate - never one mixed figure).
    spent_inr = sum(t["amount"] for t in all_txns if t["status"] == "completed" and t.get("currency", "INR") == "INR")
    spent_usd = sum(t["amount"] for t in all_txns if t["status"] == "completed" and t.get("currency") == "USD")
    total_spent_txt = _money(spent_inr, "INR")
    if spent_usd:
        total_spent_txt += f' + {_money(spent_usd, "USD")}'

    is_banned = u.get("status") == "banned"
    plan_pill = f'<span class="pill {"paid" if u["plan"]!="free" else "free"}">{_e(u["plan"])}</span>'
    verified_pill = ('<span class="pill on">verified</span>' if u["verified"]
                     else '<span class="pill off">unverified</span>')
    byok = ('<span class="pill on">own key</span>' if u["byok"]
            else '<span class=muted>uses credits</span>')
    # status pill for the header sub-line
    if is_banned:
        since = ""
        if u.get("banned_at"):
            since = f' <span class=muted>since {_e(u["banned_at"][:10])}</span>'
        acct_status_pill = f'<span class="pill off">SUSPENDED</span>{since}'
    else:
        acct_status_pill = '<span class="pill active">active</span>'
    # prominent banner shown at top of content when banned
    if is_banned:
        ban_banner = (
            f'<div class=ban-banner><span class=msg>This account is suspended '
            f'&mdash; the user cannot log in or use the AI.</span>'
            f'<form method=post action="{b}/user/{user_id}/unban">'
            f'<button class="btn primary" type=submit>Un-suspend</button></form></div>')
    else:
        ban_banner = ""

    # --- stat cards ---
    stat_cards = "".join([
        f'<div class=stat><b>{u["credits"]}</b><span>Image credits left</span></div>',
        f'<div class=stat><b>{u["tool_calls"]}</b><span>AI actions left</span></div>',
        f'<div class=stat><b>{u["ai_tokens"]:,}</b><span>Chat tokens left</span></div>',
        f'<div class=stat><b>{u["actions_30d"]}</b><span>Actions (30d)</span></div>',
        f'<div class=stat><b>{u["img_30d"]}</b><span>Images (30d)</span></div>',
        f'<div class="stat rev"><b>{total_spent_txt}</b><span>Total spent</span></div>',
    ])

    # --- account controls ---
    plan_opts = "".join(
        f'<option value="{p}" {"selected" if p == u["plan"] else ""}>{p}</option>'
        for p in ["free", "owai_mini", "owai_starter", "owai_pro",
                  "chat_starter", "chat_pro", "chat_max"])
    verify_target = "0" if u["verified"] else "1"
    verify_label = "Mark unverified" if u["verified"] else "Mark verified"

    controls = (
        f'<div class=card><h2>Account controls</h2><div class=controls-grid>'
        # plan
        f'<div class=ctl><label>Plan</label>'
        f'<form method=post action="{b}/user/{user_id}/plan"><div class=row>'
        f'<select name=plan>{plan_opts}</select>'
        f'<button class="btn primary mini" type=submit>Set</button></div></form></div>'
        # image credits (absolute + adjust)
        f'<div class=ctl><label>Image credits</label>'
        f'<form method=post action="{b}/user/{user_id}/credits"><div class=row>'
        f'<input class=inp type=number name=count value="{u["credits"]}">'
        f'<button class="btn mini" type=submit>Set</button></div></form>'
        f'<div class=row style="margin-top:8px">'
        f'<form class=inline method=post action="{b}/user/{user_id}/addcredits">'
        f'<input type=hidden name=delta value="10">'
        f'<button class="btn secondary mini" type=submit>+10</button></form>'
        f'<form method=post action="{b}/user/{user_id}/addcredits"><div class=row>'
        f'<input class=inp type=number name=delta value="0" style="max-width:90px">'
        f'<button class="btn mini" type=submit>Add</button></div></form></div>'
        f'<div class=hint>Set = absolute. Add takes +/- (e.g. -5).</div></div>'
        # AI actions (absolute + adjust)
        f'<div class=ctl><label>AI actions</label>'
        f'<form method=post action="{b}/user/{user_id}/actions"><div class=row>'
        f'<input class=inp type=number name=count value="{u["tool_calls"]}">'
        f'<button class="btn mini" type=submit>Set</button></div></form>'
        f'<div class=row style="margin-top:8px">'
        f'<form class=inline method=post action="{b}/user/{user_id}/addactions">'
        f'<input type=hidden name=delta value="10">'
        f'<button class="btn secondary mini" type=submit>+10</button></form>'
        f'<form method=post action="{b}/user/{user_id}/addactions"><div class=row>'
        f'<input class=inp type=number name=delta value="0" style="max-width:90px">'
        f'<button class="btn mini" type=submit>Add</button></div></form></div>'
        f'<div class=hint>Set = absolute. Add takes +/- (e.g. -5).</div></div>'
        # chat tokens (absolute)
        f'<div class=ctl><label>Chat tokens</label>'
        f'<form method=post action="{b}/user/{user_id}/tokens"><div class=row>'
        f'<input class=inp type=number name=count value="{u["ai_tokens"]}">'
        f'<button class="btn mini" type=submit>Set</button></div></form>'
        f'<div class=hint>Absolute value.</div></div>'
        # email
        f'<div class=ctl><label>Email</label>'
        f'<form method=post action="{b}/user/{user_id}/email"><div class=row>'
        f'<input class=inp type=email name=email value="{_e(u["email"])}">'
        f'<button class="btn mini" type=submit>Save</button></div></form></div>'
        # verified toggle
        f'<div class=ctl><label>Email verified · {"yes" if u["verified"] else "no"}</label>'
        f'<form method=post action="{b}/user/{user_id}/verify">'
        f'<input type=hidden name=verified value="{verify_target}">'
        f'<button class="btn mini" type=submit>{verify_label}</button></form></div>'
        # password reset
        f'<div class=ctl><label>Password</label>'
        f'<form method=post action="{b}/user/{user_id}/reset">'
        f'<button class="btn mini" type=submit>Send reset link</button></form>'
        f'<div class=hint>Emails them a reset link.</div></div>'
        # login as
        f'<div class=ctl><label>Impersonate</label>'
        f'<form method=post action="{b}/user/{user_id}/loginas">'
        f'<button class="btn loginas mini" type=submit>Log in as user</button></form>'
        f'<div class=hint>Opens their dashboard.</div></div>'
        f'</div></div>')

    # --- admin note (sticky-note style) ---
    note_card = (
        f'<div class="card note-card"><h2>Internal note (only you see this)</h2>'
        f'<form method=post action="{b}/user/{user_id}/note">'
        f'<textarea name=note placeholder="Add a private note about this user...">'
        f'{_e(u.get("admin_note") or "")}</textarea>'
        f'<button class="btn mini" type=submit>Save note</button></form></div>')

    # --- ban / suspend control ---
    if is_banned:
        ban_ctl = (
            f'<form class=inline method=post action="{b}/user/{user_id}/unban">'
            f'<button class="btn primary" type=submit>Un-suspend user</button></form>')
    else:
        ban_ctl = (
            f'<form class=inline method=post action="{b}/user/{user_id}/ban" '
            f'onsubmit="return confirm(\'Suspend this user? They will be blocked '
            f'from logging in and using the AI.\')">'
            f'<button class="btn danger" type=submit>Suspend user</button></form>')

    # --- danger zone ---
    danger = (
        f'<div class="card danger-zone"><h2>Danger zone</h2>'
        f'<div class=row style="margin-bottom:12px">{ban_ctl}</div>'
        f'<div class=row>'
        f'<form method=post action="{b}/user/{user_id}/disconnect" '
        f'onsubmit="return confirm(\'Disconnect ALL of this user\\\'s WordPress sites? '
        f'This revokes their AI access.\')">'
        f'<button class="btn danger" type=submit>Disconnect all sites</button></form>'
        f'<form method=post action="{b}/user/{user_id}/delete" '
        f'onsubmit="return confirm(\'Delete this user and ALL their data? '
        f'This cannot be undone.\')">'
        f'<button class="btn danger" type=submit>Delete user</button></form>'
        f'</div></div>')

    # --- connected sites ---
    sites = "".join(
        f'<tr><td><a href="{_e(s["url"])}" target=_blank rel=noopener>{_e(s["url"])}</a></td>'
        f'<td>{_e(s["user"])}</td>'
        f'<td><span class="pill {"on" if s["status"]=="active" else "off"}">{_e(s["status"])}</span></td>'
        f'<td class=muted>{_e(s["created_at"][:10])}</td></tr>' for s in u["sites"]) \
        or '<tr><td colspan=4 class=muted>No sites connected</td></tr>'

    # --- transactions (with refund) ---
    txn_rows = ""
    for t in all_txns:
        status_pill = (f'<span class="pill {"on" if t["status"]=="completed" else "off"}">'
                       f'{_e(t["status"])}</span>')
        if t["status"] == "completed":
            refund = (
                f'<form method=post action="{b}/txn/{t["id"]}/refund" '
                f'onsubmit="return confirm(\'Mark this transaction refunded?\')">'
                f'<button class="btn danger mini" type=submit>Refund</button></form>')
        else:
            refund = '<span class=muted>—</span>'
        txn_rows += (
            f'<tr><td class=muted>{_e(t["created_at"][:16])}</td><td>{_e(t["item"])}</td>'
            f'<td>{_money(t["amount"], t.get("currency","INR"))}</td><td>{_e(t["provider"])}</td>'
            f'<td>{status_pill}</td><td>{refund}</td></tr>')
    if not txn_rows:
        txn_rows = '<tr><td colspan=6 class=muted>No transactions</td></tr>'

    # --- activity log ---
    if activity:
        evs = "".join(
            f'<div class=ev><span class=k>{_e(a["kind"])}</span>'
            f'<span class=t>{_e(a["created_at"][:16])}</span></div>' for a in activity)
        activity_html = f'<div class=activity-log>{evs}</div>'
    else:
        activity_html = '<p class=muted>No activity logged.</p>'

    sub_line = (f'Subscription: {_e(u["sub_status"])}'
                f'{" via "+_e(u["sub_provider"]) if u["sub_provider"] else ""}'
                f'{" · renews "+_e(u["sub_renews_at"][:10]) if u["sub_renews_at"] else ""}')

    return _shell(u["email"], "users", (
        f'{ban_banner}'
        f'<div class=crumb><a href="{b}/users">Users</a> / {_e(u["email"])}</div>'
        f'<h1>{_e(u["email"])}</h1>'
        f'<p class=sub>{plan_pill} · {verified_pill} · {acct_status_pill} · '
        f'joined {_e(u["created_at"][:10])} · Gemini key: {byok}</p>'
        f'<div class=stats>{stat_cards}</div>'
        f'{controls}'
        f'{note_card}'
        f'{danger}'
        f'<div class=card><h2>Connected sites</h2><div class=tbl-wrap><table><thead><tr>'
        f'<th>URL</th><th>WP user</th><th>Status</th><th>Added</th></tr></thead>'
        f'<tbody>{sites}</tbody></table></div></div>'
        f'<div class=card><h2>Transactions</h2>'
        f'<p class=muted style="margin-bottom:10px;font-size:.85rem">{sub_line}</p>'
        f'<div class=tbl-wrap><table><thead><tr><th>Date</th><th>Item</th><th>Amount</th>'
        f'<th>Provider</th><th>Status</th><th></th></tr></thead>'
        f'<tbody>{txn_rows}</tbody></table></div></div>'
        f'<div class=card><h2>Activity log</h2>{activity_html}</div>'
    ), flash)


def payments_page(flash=""):
    txns = db.admin_recent_transactions()
    b = base_path()
    # Totals per currency - never sum INR and USD into one number.
    total_inr = sum(t["amount"] for t in txns if t["status"] == "completed" and t.get("currency", "INR") == "INR")
    total_usd = sum(t["amount"] for t in txns if t["status"] == "completed" and t.get("currency") == "USD")
    total_txt = _money(total_inr, "INR")
    if total_usd:
        total_txt += f' + {_money(total_usd, "USD")}'
    rows = ""
    for t in txns:
        rows += (
            f'<tr><td class=muted>{_e(t["created_at"][:16])}</td>'
            f'<td><a href="{b}/user/{t["user_id"]}">{_e(t["email"])}</a></td>'
            f'<td>{_e(t["item"])}</td><td>{_money(t["amount"], t.get("currency","INR"))}</td>'
            f'<td>{_e(t["provider"])}</td>'
            f'<td><span class="pill {"on" if t["status"]=="completed" else "off"}">{_e(t["status"])}</span></td></tr>')
    if not rows:
        rows = '<tr><td colspan=6 class=muted style="text-align:center;padding:24px">No transactions yet</td></tr>'
    return _shell("Payments", "pay", (
        f'<h1>Payments</h1><p class=sub>Last {len(txns)} transactions · '
        f'{total_txt} shown.</p>'
        f'<div class=row style="margin-bottom:14px"><a class="btn secondary" '
        f'href="{b}/payments.csv">Download CSV</a></div>'
        f'<div class=card><div class=tbl-wrap><table><thead><tr>'
        f'<th>Date</th><th>User</th><th>Item</th><th>Amount</th><th>Provider</th>'
        f'<th>Status</th></tr></thead><tbody>{rows}</tbody></table></div></div>'
        f'<p class=muted style="font-size:.85rem">To refund a payment, open the '
        f'user and use the Refund button on their transaction.</p>'
    ), flash)


def usage_page(days=30, flash=""):
    b = base_path()
    try:
        days = int(days)
    except (ValueError, TypeError):
        days = 30
    if days not in (7, 30, 90, 365):
        days = 30
    label = {7: "7 days", 30: "30 days", 90: "90 days", 365: "12 months"}[days]

    s = db.admin_usage_stats(days)
    daily = db.admin_actions_daily(days)
    daily_img = db.admin_images_daily(days)
    tools = db.admin_top_tools_window(days, limit=25)
    power = db.admin_top_users_by_usage(days, limit=10)
    inactive = db.admin_inactive_users(days, limit=12)

    # date-range toggle
    def _range(dn, lbl):
        cls = "on" if dn == days else ""
        return f'<a href="{b}/usage?days={dn}" class="rng {cls}">{lbl}</a>'
    toggle = ('<div class=rngbar>' + _range(7, "7d") + _range(30, "30d") +
              _range(90, "90d") + _range(365, "12mo") + '</div>')

    # stat cards
    stats = "".join([
        f'<div class=stat><b>{s["actions"]}</b><span>Total AI actions '
        f'<span class="delta up">{s["today"]} today</span></span></div>',
        f'<div class=stat><b>{s["images"]}</b><span>AI images</span></div>',
        f'<div class=stat><b>{s["active_users"]}</b><span>Active users '
        f'({s["active_users"]}/{s["total_users"]})</span></div>',
        f'<div class=stat><b>{s["avg_per_active"]}</b><span>Avg actions / active user</span></div>',
        f'<div class=stat><b>{s["avg_per_day"]}</b><span>Actions per day</span></div>',
        f'<div class=stat><b>{s["peak_count"]}</b><span>Peak day · {_e(s["peak_day"])}</span></div>',
        f'<div class=stat><b>{s["chats"]}</b><span>Chat messages</span></div>',
        f'<div class=stat><b>{s["sites"]}</b><span>Active sites</span></div>',
    ])

    # tool breakdown bars with % of total
    tot = sum(n for _, n in tools) or 1
    mx = max((n for _, n in tools), default=1)
    tool_bars = "".join(
        f'<div class=bar><span>{_e(k)}</span>'
        f'<div class=track><div class=fill style="width:{max(4,int(n/mx*100))}%"></div></div>'
        f'<span class=n>{n} · {round(n/tot*100)}%</span></div>' for k, n in tools) \
        or '<p class=muted>No usage in this period.</p>'

    # power users table
    pw_rows = "".join(
        f'<tr><td><a href="{b}/user/{u["id"]}">{_e(u["email"])}</a></td>'
        f'<td><span class="pill {"paid" if u["plan"]!="free" else "free"}">{_e(u["plan"])}</span></td>'
        f'<td>{u["count"]}</td></tr>' for u in power) \
        or '<tr><td colspan=3 class=muted>No active users in this period</td></tr>'

    # inactive (churn risk) table
    in_rows = "".join(
        f'<tr><td><a href="{b}/user/{u["id"]}">{_e(u["email"])}</a></td>'
        f'<td><span class="pill {"paid" if u["plan"]!="free" else "free"}">{_e(u["plan"])}</span></td>'
        f'<td class=muted>{_e(u["created_at"][:10])}</td></tr>' for u in inactive) \
        or '<tr><td colspan=3 class=muted>Everyone has been active</td></tr>'

    return _shell("Usage", "usage", (
        f'<div class=usage-head><div><h1>Usage</h1>'
        f'<p class=sub>Activity in the last {label}.</p></div>{toggle}</div>'
        f'<div class=stats>{stats}</div>'
        f'<div class=grid2>'
        f'<div class=card><h2>Actions per day</h2>{_svg_bars(daily, "#F97316")}</div>'
        f'<div class=card><h2>Images per day</h2>{_svg_bars(daily_img, "#059669")}</div>'
        f'</div>'
        f'<div class=grid3>'
        f'<div class=card><h2>Most-used actions</h2><div class=bars>{tool_bars}</div></div>'
        f'<div class=card><h2>Power users</h2>'
        f'<div class=tbl-wrap><table><thead><tr><th>User</th><th>Plan</th><th>Actions</th></tr></thead>'
        f'<tbody>{pw_rows}</tbody></table></div></div>'
        f'</div>'
        f'<div class=card><h2>Inactive users · churn risk '
        f'<span class=muted style="font-weight:400;font-size:.85rem">(signed up, no activity in {label})</span></h2>'
        f'<div class=tbl-wrap><table><thead><tr><th>User</th><th>Plan</th><th>Joined</th></tr></thead>'
        f'<tbody>{in_rows}</tbody></table></div></div>'
    ), flash)


def system_page(status: dict, flash=""):
    """Read-only health/monitoring view. `status` keys: db_ok, email_configured,
    razorpay_configured, gemini_configured, stripe_configured, maintenance_on,
    builtin_chat_on (all bools)."""
    status = status or {}

    def _pill(ok, on_label="OK", off_label="off"):
        return (f'<span class="pill on">{on_label}</span>' if ok
                else f'<span class="pill off">{off_label}</span>')

    rows_spec = [
        ("Database", "Postgres connection pool",
         _pill(status.get("db_ok"), "OK", "error")),
        ("Email (SMTP)", "Verification + reset + notification mail",
         _pill(status.get("email_configured"), "configured", "off")),
        ("Razorpay", "India payments provider",
         _pill(status.get("razorpay_configured"), "configured", "off")),
        ("Stripe", "International payments provider",
         _pill(status.get("stripe_configured"), "configured", "off")),
        ("Gemini", "Image generation API key",
         _pill(status.get("gemini_configured"), "configured", "off")),
        ("Maintenance mode", "Public site locked to visitors",
         _pill(status.get("maintenance_on"), "on", "off")),
        ("Built-in chat", "Hosted Claude chat feature",
         _pill(status.get("builtin_chat_on"), "on", "off")),
    ]
    rows = "".join(
        f'<div class=sys-row><span class=lbl>{_e(label)}<small>{_e(desc)}</small></span>'
        f'{pill}</div>' for label, desc, pill in rows_spec)

    note = (
        '<div class=note>Maintenance mode and built-in chat are controlled by '
        'Railway environment variables and read once at boot. Changing them '
        'requires editing the env var and redeploying &mdash; this page is '
        'status/monitoring only and cannot toggle them.</div>')

    return _shell("System", "sys", (
        f'<h1>System health</h1><p class=sub>Live status of core services and '
        f'configuration.</p>'
        f'{note}'
        f'<div class=card><h2>Services</h2><div class=sys-rows>{rows}</div></div>'
    ), flash)


def coupons_page(flash="", err=""):
    """Admin: create + manage discount coupons."""
    b = base_path()
    coupons = db.list_coupons()

    def _disc(c):
        if c["kind"] == "percent":
            return f'{int(c["value"]) if c["value"]==int(c["value"]) else c["value"]}% off'
        cur = "" if c["currency"] == "ANY" else (c["currency"] + " ")
        return f'{cur}{int(c["value"]) if c["value"]==int(c["value"]) else c["value"]} off'

    rows = ""
    for c in coupons:
        uses = f'{c["used_count"]}' + (f' / {c["max_uses"]}' if c["max_uses"] else ' / ∞')
        exp = c["expires_at"][:10] if c["expires_at"] else "never"
        st = ('<span class="pill on">active</span>' if c["active"]
              else '<span class="pill off">off</span>')
        toggle = "off" if c["active"] else "on"
        toggle_lbl = "Disable" if c["active"] else "Enable"
        rows += (
            f'<tr><td><b style="font-family:\'Sora\';color:#14131A">{_e(c["code"])}</b></td>'
            f'<td>{_e(_disc(c))}</td><td>{_e(c["currency"])}</td>'
            f'<td>{uses}</td><td class=muted>{exp}</td><td>{st}</td>'
            f'<td>{_e(c["note"])}</td>'
            f'<td style="white-space:nowrap">'
            f'<form class=inline method=post action="{b}/coupon/{urllib.parse.quote(c["code"], safe="")}/toggle">'
            f'<input type=hidden name=active value="{"1" if not c["active"] else "0"}">'
            f'<button class="btn mini" type=submit>{toggle_lbl}</button></form> '
            f'<form class=inline method=post action="{b}/coupon/{urllib.parse.quote(c["code"], safe="")}/delete" '
            f'onsubmit="return confirm(\'Delete coupon {_e(c["code"])}?\')">'
            f'<button class="btn mini danger" type=submit>Delete</button></form>'
            f'</td></tr>')
    if not rows:
        rows = '<tr><td colspan=8 class=muted style="text-align:center;padding:22px">No coupons yet - create one below.</td></tr>'

    total_redeemed = sum(c["used_count"] for c in coupons)
    active_n = sum(1 for c in coupons if c["active"])
    err_html = f'<div class="err">{_e(err)}</div>' if err else ""

    create = (
        f'<div class=card><h2>Create a coupon</h2>{err_html}'
        f'<form method=post action="{b}/coupons/create">'
        f'<div class=coupon-grid>'
        f'<div><label class=lbl>Code</label>'
        f'<input class=inp name=code placeholder="LAUNCH50" required style="text-transform:uppercase"></div>'
        f'<div><label class=lbl>Type</label>'
        f'<select name=kind><option value=percent>Percent %</option>'
        f'<option value=flat>Flat amount</option></select></div>'
        f'<div><label class=lbl>Value</label>'
        f'<input class=inp name=value type=number step=0.01 placeholder="50" required></div>'
        f'<div><label class=lbl>Currency (flat only)</label>'
        f'<select name=currency><option value=ANY>Any</option>'
        f'<option value=INR>INR</option><option value=USD>USD</option></select></div>'
        f'<div><label class=lbl>Max uses (0 = unlimited)</label>'
        f'<input class=inp name=max_uses type=number value=0></div>'
        f'<div><label class=lbl>Expires (optional)</label>'
        f'<input class=inp name=expires type=date></div>'
        f'<div style="grid-column:1/-1"><label class=lbl>Note (internal)</label>'
        f'<input class=inp name=note placeholder="e.g. Launch promo" style="width:100%"></div>'
        f'</div>'
        f'<button class="btn primary" type=submit style="margin-top:14px">Create coupon</button>'
        f'</form></div>')

    return _shell("Coupons", "coupon", (
        f'<h1>Coupons</h1><p class=sub>Discount codes for checkout. '
        f'{active_n} active · {total_redeemed} total redemptions.</p>'
        f'{create}'
        f'<div class=card><h2>All coupons</h2>'
        f'<div class=tbl-wrap><table><thead><tr>'
        f'<th>Code</th><th>Discount</th><th>Currency</th><th>Uses</th><th>Expires</th>'
        f'<th>Status</th><th>Note</th><th></th></tr></thead>'
        f'<tbody>{rows}</tbody></table></div></div>'
        f'<style>'
        f'.coupon-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}}'
        f'.coupon-grid .lbl{{display:block;font-size:.78rem;font-weight:600;color:var(--muted2);'
        f'margin-bottom:5px;font-family:\'Sora\'}}'
        f'.coupon-grid .inp,.coupon-grid select{{width:100%}}'
        f'.btn.mini{{padding:5px 10px;font-size:.8rem}}'
        f'.btn.mini.danger{{color:var(--red);border-color:#F3C9C9}}'
        f'@media(max-width:760px){{.coupon-grid{{grid-template-columns:1fr}}}}'
        f'</style>'
    ), flash)


def plans_page(flash="", err=""):
    """Admin: edit plan prices (INR/USD) + monthly limits. Live-applies on save."""
    b = base_path()
    cfg = db.get_plan_config()
    err_html = f'<div class="err">{_e(err)}</div>' if err else ""
    order = ["owai_mini", "owai_starter", "owai_pro"]
    cards = ""
    for key in order:
        p = cfg.get(key, {})
        io = ' <span class="pill free">India only</span>' if p.get("india_only") else ""
        actions_display = "Unlimited" if int(p.get("actions", 0)) >= 1_000_000 else p.get("actions", 0)
        cards += (
            f'<form method=post action="{b}/plans/save" class=plan-edit>'
            f'<input type=hidden name=key value="{_e(key)}">'
            f'<div class=plan-edit-head><h3>{_e(p.get("name", key))}{io}</h3>'
            f'<code class=muted>{_e(key)}</code></div>'
            f'<div class=pe-grid>'
            f'<div><label class=lbl>Price INR (₹/mo)</label>'
            f'<input class=inp name=inr type=number value="{int(p.get("inr",0))}"></div>'
            f'<div><label class=lbl>Price USD ($/mo)</label>'
            f'<input class=inp name=usd type=number value="{int(p.get("usd",0))}"></div>'
            f'<div><label class=lbl>AI images / mo</label>'
            f'<input class=inp name=images type=number value="{int(p.get("images",0))}"></div>'
            f'<div><label class=lbl>AI actions / mo <span class=muted>(1000000 = ∞)</span></label>'
            f'<input class=inp name=actions type=number value="{int(p.get("actions",0))}"></div>'
            f'<div><label class=lbl>Sites</label>'
            f'<input class=inp name=sites type=number value="{int(p.get("sites",1))}"></div>'
            f'<div style="display:flex;align-items:flex-end">'
            f'<button class="btn primary" type=submit>Save {_e(p.get("name",key))}</button></div>'
            f'</div></form>')
    return _shell("Plans", "plans", (
        f'<h1>Plan management</h1>'
        f'<p class=sub>Edit prices and monthly limits. Changes apply immediately - '
        f'new checkouts use the updated prices, and limits apply on the next monthly reset.</p>'
        f'{err_html}'
        f'<div class=note>The Free plan (₹0) is fixed. Actions = 1000000 means unlimited '
        f'(shown as "Unlimited" to users).</div>'
        f'{cards}'
        f'<style>'
        f'.plan-edit{{background:var(--surface);border:1px solid var(--line);border-radius:16px;'
        f'padding:22px;margin-bottom:18px;box-shadow:0 6px 24px -18px rgba(20,19,26,.12)}}'
        f'.plan-edit-head{{display:flex;align-items:center;justify-content:space-between;'
        f'margin-bottom:16px}}.plan-edit-head h3{{color:var(--ink)}}'
        f'.pe-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}}'
        f'.pe-grid .lbl{{display:block;font-size:.76rem;font-weight:600;color:var(--muted2);'
        f'margin-bottom:5px;font-family:Sora,sans-serif}}.pe-grid .inp{{width:100%}}'
        f'@media(max-width:760px){{.pe-grid{{grid-template-columns:1fr 1fr}}}}'
        f'</style>'
    ), flash)


def emails_page(flash="", err=""):
    """Admin: view all notification emails, edit subject, turn on/off, test-send."""
    b = base_path()
    cfg = db.get_email_config()
    err_html = f'<div class="err">{_e(err)}</div>' if err else ""
    rows = ""
    for key, e in cfg.items():
        ph = ", ".join("{" + p + "}" for p in e["placeholders"]) or "-"
        st = ('<span class="pill on">on</span>' if e["enabled"]
              else '<span class="pill off">off</span>')
        rows += (
            f'<form method=post action="{b}/emails/save" class=email-row>'
            f'<input type=hidden name=key value="{_e(key)}">'
            f'<div class=er-top><div><b style="color:var(--ink);font-family:Sora,sans-serif">'
            f'{_e(e["label"])}</b> {st}<div class=muted style="font-size:.8rem;margin-top:2px">'
            f'Placeholders: {_e(ph)}</div></div></div>'
            f'<div class=er-grid>'
            f'<div style="flex:1"><label class=lbl>Subject</label>'
            f'<input class=inp name=subject value="{_e(e["subject"])}" style="width:100%"></div>'
            f'<label class=chk><input type=checkbox name=enabled value=1 '
            f'{"checked" if e["enabled"] else ""}> Enabled</label>'
            f'<button class="btn" type=submit>Save</button>'
            f'</div></form>'
            f'<form method=post action="{b}/emails/test" class=email-test>'
            f'<input type=hidden name=key value="{_e(key)}">'
            f'<input class=inp name=to type=email placeholder="test@email.com to send a preview">'
            f'<button class="btn mini" type=submit>Send test</button></form>')
    return _shell("Emails", "emails", (
        f'<h1>Email management</h1>'
        f'<p class=sub>All notification emails. Edit the subject, turn any on or off, '
        f'and send yourself a test. Bodies use the branded template automatically.</p>'
        f'{err_html}'
        f'<div class=note>Placeholders like {{name}} or {{link}} are filled in automatically '
        f'when the email is sent.</div>'
        f'<div class=card>{rows}</div>'
        f'<style>'
        f'.email-row{{padding:16px 0 6px;border-top:1px solid var(--line)}}'
        f'.email-row:first-child{{border-top:0}}'
        f'.er-top{{margin-bottom:10px}}'
        f'.er-grid{{display:flex;gap:12px;align-items:flex-end;flex-wrap:wrap}}'
        f'.er-grid .lbl{{display:block;font-size:.74rem;font-weight:600;color:var(--muted2);'
        f'margin-bottom:4px;font-family:Sora,sans-serif}}'
        f'.chk{{display:flex;align-items:center;gap:6px;font-size:.85rem;color:var(--muted);'
        f'white-space:nowrap;padding-bottom:9px}}'
        f'.email-test{{display:flex;gap:8px;align-items:center;margin:8px 0 14px}}'
        f'.email-test .inp{{width:280px}}.btn.mini{{padding:6px 12px;font-size:.8rem}}'
        f'</style>'
    ), flash)


def social_page(flash="", err=""):
    """Admin: manage the social media links shown in the site footer. Any link left
    blank is hidden; a '#' shows the icon as a placeholder (not yet live)."""
    b = base_path()
    current = db.get_social_links()
    err_html = f'<div class="err">{_e(err)}</div>' if err else ""
    rows = ""
    for key, label in db.SOCIAL_PLATFORMS:
        val = current.get(key, "")
        rows += (
            f'<div class=srow>'
            f'<label class=slabel>{_e(label)}</label>'
            f'<input class=inp name="{_e(key)}" value="{_e(val)}" '
            f'placeholder="https://... (or # for now, blank to hide)" '
            f'style="flex:1;min-width:220px"></div>')
    return _shell("Social links", "social", (
        f'<h1>Social links</h1>'
        f'<p class=sub>Add your social profile URLs. They appear as icons in the site '
        f'footer automatically - only the ones you fill in are shown. Leave a field blank '
        f'to hide that icon; enter <b>#</b> to show the icon now as a placeholder.</p>'
        f'{err_html}'
        f'<form method=post action="{b}/social/save">'
        f'<div class=card>{rows}'
        f'<div style="margin-top:16px"><button class="btn" type=submit>Save social links</button></div>'
        f'</div></form>'
        f'<div class=note>Supported: Facebook, Instagram, YouTube, Pinterest, LinkedIn, '
        f'Reddit, X (Twitter), TikTok, Threads, GitHub. More can be added in code if needed.</div>'
        f'<style>'
        f'.srow{{display:flex;gap:14px;align-items:center;padding:9px 0;border-top:1px solid var(--line)}}'
        f'.srow:first-child{{border-top:0}}'
        f'.slabel{{width:120px;font-weight:600;color:var(--ink);font-family:Sora,sans-serif;font-size:.9rem}}'
        f'</style>'
    ), flash)


def analytics_page(flash="", err=""):
    """Admin: Google Analytics ID + Search Console verification + extra head tags.
    These are injected into every page's <head> automatically."""
    b = base_path()
    a = db.get_analytics()
    err_html = f'<div class="err">{_e(err)}</div>' if err else ""
    return _shell("Analytics / SEO", "seo", (
        f'<h1>Analytics &amp; Search Console</h1>'
        f'<p class=sub>Add your tracking and verification tags here. They are injected into '
        f'the &lt;head&gt; of every page on the site automatically - no code needed.</p>'
        f'{err_html}'
        f'<form method=post action="{b}/seo/save">'
        f'<div class=card>'

        f'<div class=fld>'
        f'<label class=lbl>Google Analytics ID</label>'
        f'<input class=inp name=ga_id value="{_e(a["ga_id"])}" placeholder="G-XXXXXXXXXX" '
        f'style="width:100%">'
        f'<div class=hint>Your GA4 Measurement ID (looks like <b>G-XXXXXXXXXX</b>). Find it in '
        f'Google Analytics &rarr; Admin &rarr; Data streams. Leave blank to turn analytics off.</div>'
        f'</div>'

        f'<div class=fld style="margin-top:18px">'
        f'<label class=lbl>Google Search Console verification</label>'
        f'<input class=inp name=gsc_verify value="{_e(a["gsc_verify"])}" '
        f'placeholder="paste the verification code (or the whole meta tag)" style="width:100%">'
        f'<div class=hint>In Search Console choose the <b>HTML tag</b> verification method and paste '
        f'the code here (either just the <code>content</code> value, or the full '
        f'<code>&lt;meta name="google-site-verification" ...&gt;</code> tag - we\'ll extract it).</div>'
        f'</div>'

        f'<div class=fld style="margin-top:18px">'
        f'<label class=lbl>Extra head tags <span class=muted>(optional)</span></label>'
        f'<textarea class=inp name=head_extra rows=4 placeholder="Any other verification / analytics '
        f'tags (Bing, Ahrefs, etc.) - pasted verbatim into &lt;head&gt;" '
        f'style="width:100%;font-family:monospace;font-size:.85rem">{_e(a["head_extra"])}</textarea>'
        f'<div class=hint>Advanced: raw HTML injected as-is. Only paste tags from services you trust.</div>'
        f'</div>'

        f'<div style="margin-top:18px"><button class="btn" type=submit>Save &amp; apply</button></div>'
        f'</div></form>'
        f'<div class=note>After saving, open your site and use &ldquo;View source&rdquo; to confirm '
        f'the tags are in the &lt;head&gt;. Then click <b>Verify</b> in Search Console and check '
        f'Realtime in Google Analytics.</div>'
        f'<style>'
        f'.fld .lbl{{display:block;font-size:.8rem;font-weight:600;color:var(--ink);'
        f'font-family:Sora,sans-serif;margin-bottom:6px}}'
        f'.fld .hint{{font-size:.8rem;color:var(--muted);margin-top:6px;line-height:1.5}}'
        f'.inp{{padding:10px 12px;border:1px solid var(--line);border-radius:8px;background:var(--bg);'
        f'color:var(--ink)}}'
        f'</style>'
    ), flash)


def forum_page(flash="", err=""):
    """Admin: community moderation. List recent threads with pin/lock/delete actions."""
    b = base_path()
    s = db.forum_stats()
    threads = db.forum_threads(limit=100)
    err_html = f'<div class="err">{_e(err)}</div>' if err else ""
    rows = ""
    for t in threads:
        pin_lbl = "Unpin" if t["pinned"] else "Pin"
        lock_lbl = "Unlock" if t["locked"] else "Lock"
        badges = ('<span class="pill on">pinned</span> ' if t["pinned"] else '') + \
                 ('<span class="pill off">locked</span> ' if t["locked"] else '')
        rows += (
            f'<tr><td><a href="/community/t/{t["id"]}-{_e(t["slug"])}" target=_blank>{_e(t["title"])}</a> '
            f'{badges}<div class=muted style="font-size:.8rem">{_e(t["cat_name"])} &middot; '
            f'by {_e(t["author"])} &middot; {t["reply_count"]} replies</div></td>'
            f'<td style="white-space:nowrap;text-align:right">'
            f'<form class=inline method=post action="{b}/forum/thread/{t["id"]}/pin">'
            f'<button class="btn mini" type=submit>{pin_lbl}</button></form> '
            f'<form class=inline method=post action="{b}/forum/thread/{t["id"]}/lock">'
            f'<button class="btn mini" type=submit>{lock_lbl}</button></form> '
            f'<form class=inline method=post action="{b}/forum/thread/{t["id"]}/delete" '
            f'onsubmit="return confirm(\'Delete this thread and all replies?\')">'
            f'<button class="btn mini danger" type=submit>Delete</button></form>'
            f'</td></tr>')
    if not rows:
        rows = '<tr><td colspan=2 class=muted style="text-align:center;padding:24px">No threads yet</td></tr>'
    stats = "".join([
        f'<div class=stat><b>{s["categories"]}</b><span>Categories</span></div>',
        f'<div class=stat><b>{s["threads"]}</b><span>Threads</span></div>',
        f'<div class=stat><b>{s["posts"]}</b><span>Replies</span></div>',
    ])
    return _shell("Community", "forum", (
        f'<h1>Community moderation</h1>'
        f'<p class=sub>Pin, lock or delete threads. Threads are public and indexed; only verified '
        f'users can post.</p>'
        f'{err_html}'
        f'<div class=stats>{stats}</div>'
        f'<div class=card><div class=tbl-wrap><table><thead><tr><th>Thread</th>'
        f'<th style="text-align:right">Actions</th></tr></thead><tbody>{rows}</tbody></table></div></div>'
    ), flash)


def affiliates_page(flash="", err=""):
    """Admin: affiliate program. Set commission %, approve payout requests, see top affiliates."""
    b = base_path()
    s = db.admin_affiliate_stats()
    rate = db.get_commission_rate()
    pending = db.admin_payout_requests(status="requested")
    recent = db.admin_payout_requests(limit=30)
    top = db.admin_top_affiliates(15)
    err_html = f'<div class="err">{_e(err)}</div>' if err else ""

    stats = "".join([
        f'<div class=stat><b>{s["affiliates"]}</b><span>Affiliates</span></div>',
        f'<div class=stat><b>{s["referrals"]}</b><span>Referrals</span></div>',
        f'<div class=stat><b>{s["converted"]}</b><span>Paid conversions</span></div>',
        f'<div class="stat rev"><b>{_money(s["owed_inr"])}{(" + " + _money(s["owed_usd"],"USD")) if s["owed_usd"] else ""}</b><span>Total commission earned</span></div>',
        f'<div class=stat><b>{s["pending_payouts"]}</b><span>Pending payouts</span></div>',
    ])

    def payout_rows(rows, actions=True):
        out = ""
        for p in rows:
            sym = "₹" if p["currency"] == "INR" else "$"
            pst = {"requested": '<span class="pill">requested</span>',
                   "paid": '<span class="pill on">paid</span>',
                   "rejected": '<span class="pill off">rejected</span>'}.get(p["status"], p["status"])
            act = ""
            if actions and p["status"] == "requested":
                act = (f'<form class=inline method=post action="{b}/payout/{p["id"]}/paid">'
                       f'<button class="btn mini" type=submit>Mark paid</button></form> '
                       f'<form class=inline method=post action="{b}/payout/{p["id"]}/rejected" '
                       f'onsubmit="return confirm(\'Reject this payout request?\')">'
                       f'<button class="btn mini danger" type=submit>Reject</button></form>')
            out += (f'<tr><td><a href="{b}/user/{p["user_id"]}">{_e(p["email"])}</a></td>'
                    f'<td>{sym}{p["amount"]:,.0f}</td>'
                    f'<td style="max-width:260px;word-break:break-all">{_e(p["method"])}</td>'
                    f'<td>{pst}</td><td class=muted>{p["created_at"][:10]}</td>'
                    f'<td style="text-align:right;white-space:nowrap">{act}</td></tr>')
        return out

    pending_rows = payout_rows(pending) or '<tr><td colspan=6 class=muted style="text-align:center;padding:18px">No pending payout requests</td></tr>'
    recent_rows = payout_rows(recent, actions=False) or '<tr><td colspan=6 class=muted style="text-align:center;padding:18px">No payouts yet</td></tr>'

    top_rows = ""
    for t in top:
        top_rows += (f'<tr><td>{_e(t["email"])}</td><td class=muted>{_e(t["ref_code"] or "-")}</td>'
                     f'<td>{t["conversions"]}</td>'
                     f'<td style="text-align:right">{_money(t["inr"])}{(" + " + _money(t["usd"],"USD")) if t["usd"] else ""}</td></tr>')
    if not top_rows:
        top_rows = '<tr><td colspan=4 class=muted style="text-align:center;padding:18px">No affiliates with referrals yet</td></tr>'

    return _shell("Affiliates", "aff", (
        f'<h1>Affiliate program</h1>'
        f'<p class=sub>Commission is credited on each referred customer\'s first paid payment. '
        f'Payouts are manual: approve requests below.</p>'
        f'{err_html}'
        f'<div class=stats>{stats}</div>'
        f'<div class=card style="margin-bottom:18px"><h3 style="margin:0 0 10px">Commission rate</h3>'
        f'<form method=post action="{b}/affiliates/rate" class=row style="align-items:flex-end;gap:12px">'
        f'<div><label class=lbl>Commission %</label>'
        f'<input class=inp name=rate value="{rate:g}" style="width:120px" type=number step=1 min=0 max=90></div>'
        f'<button class="btn" type=submit>Save rate</button>'
        f'<span class=muted style="font-size:.85rem">Applies to future conversions. Current: {rate:g}%</span>'
        f'</form></div>'
        f'<div class=card style="margin-bottom:18px"><h3 style="margin:0 0 10px">Pending payout requests</h3>'
        f'<div class=tbl-wrap><table><thead><tr><th>User</th><th>Amount</th><th>Payout details</th>'
        f'<th>Status</th><th>Date</th><th></th></tr></thead><tbody>{pending_rows}</tbody></table></div></div>'
        f'<div class=card style="margin-bottom:18px"><h3 style="margin:0 0 10px">Top affiliates</h3>'
        f'<div class=tbl-wrap><table><thead><tr><th>User</th><th>Code</th><th>Conversions</th>'
        f'<th style="text-align:right">Earned</th></tr></thead><tbody>{top_rows}</tbody></table></div></div>'
        f'<div class=card><h3 style="margin:0 0 10px">Recent payouts</h3>'
        f'<div class=tbl-wrap><table><thead><tr><th>User</th><th>Amount</th><th>Details</th>'
        f'<th>Status</th><th>Date</th><th></th></tr></thead><tbody>{recent_rows}</tbody></table></div></div>'
    ), flash)


def blog_list_page(flash="", err=""):
    """Admin: list admin-created blog posts + link to editor. Built-in posts are shown as
    read-only (they live in code)."""
    b = base_path()
    posts = db.blog_db_list()
    err_html = f'<div class="err">{_e(err)}</div>' if err else ""
    rows = ""
    for p in posts:
        st = ('<span class="pill on">published</span>' if p["published"]
              else '<span class="pill off">draft</span>')
        rows += (
            f'<tr><td><a href="/blog/{_e(p["slug"])}" target=_blank>{_e(p["title"])}</a> {st}'
            f'<div class=muted style="font-size:.8rem">/{_e(p["slug"])} &middot; {p["updated_at"][:10]}</div></td>'
            f'<td style="text-align:right;white-space:nowrap">'
            f'<a class="btn mini" href="{b}/blog/edit?slug={_e(p["slug"])}">Edit</a> '
            f'<form class=inline method=post action="{b}/blog/{_e(p["slug"])}/delete" '
            f'onsubmit="return confirm(\'Delete this post?\')">'
            f'<button class="btn mini danger" type=submit>Delete</button></form></td></tr>')
    if not rows:
        rows = '<tr><td colspan=2 class=muted style="text-align:center;padding:20px">No posts yet. Create your first one.</td></tr>'
    # built-in posts (read only)
    built = ""
    try:
        import blog_posts
        for p in blog_posts.all_posts():
            built += (f'<tr><td><a href="/blog/{_e(p["slug"])}" target=_blank>{_e(p["title"])}</a> '
                      f'<span class="pill">built-in</span>'
                      f'<div class=muted style="font-size:.8rem">/{_e(p["slug"])}</div></td>'
                      f'<td class=muted style="text-align:right;font-size:.8rem">in code</td></tr>')
    except Exception:
        pass
    return _shell("Blog", "blog", (
        f'<h1>Blog</h1>'
        f'<p class=sub>Write and manage blog posts. New posts you create here are stored in the '
        f'database and appear at /blog. The built-in guides live in code (read-only here).</p>'
        f'{err_html}'
        f'<div class=row style="margin-bottom:14px"><a class="btn" href="{b}/blog/edit">+ New post</a></div>'
        f'<div class=card style="margin-bottom:18px"><h3 style="margin:0 0 10px">Your posts</h3>'
        f'<div class=tbl-wrap><table><thead><tr><th>Post</th><th></th></tr></thead>'
        f'<tbody>{rows}</tbody></table></div></div>'
        f'<div class=card><h3 style="margin:0 0 10px">Built-in guides</h3>'
        f'<div class=tbl-wrap><table><tbody>{built}</tbody></table></div></div>'
    ), flash)


def blog_edit_page(post=None, flash="", err=""):
    """Admin: create or edit a blog post."""
    b = base_path()
    p = post or {}
    editing = bool(post)
    err_html = f'<div class="err">{_e(err)}</div>' if err else ""
    pub_checked = "checked" if (p.get("published", True)) else ""
    return _shell("Edit post" if editing else "New post", "blog", (
        f'<h1>{"Edit post" if editing else "New post"}</h1>'
        f'<p class=sub>Body accepts HTML. Use &lt;h2&gt;, &lt;p&gt;, &lt;ul&gt;&lt;li&gt;, '
        f'&lt;strong&gt;, &lt;a&gt; and &lt;img src="..."&gt;. Start each section with a '
        f'&lt;h2&gt; question and a short answer for best AI-search visibility.</p>'
        f'{err_html}'
        f'<form method=post action="{b}/blog/save">'
        f'<input type=hidden name=old_slug value="{_e(p.get("slug","")) if editing else ""}">'
        f'<div class=card>'
        f'<div class=fld><label class=lbl>Title</label>'
        f'<input class=inp name=title value="{_e(p.get("title",""))}" required style="width:100%" '
        f'placeholder="How to ... (clear, specific)"></div>'
        f'<div class=fld style="margin-top:14px"><label class=lbl>Slug (URL) '
        f'<span class=muted>optional, auto from title</span></label>'
        f'<input class=inp name=slug value="{_e(p.get("slug",""))}" style="width:100%" '
        f'placeholder="how-to-..."></div>'
        f'<div class=fld style="margin-top:14px"><label class=lbl>Meta description</label>'
        f'<input class=inp name=description value="{_e(p.get("description",""))}" style="width:100%" '
        f'placeholder="1-2 line summary for search results" maxlength=200></div>'
        f'<div class=fld style="margin-top:14px"><label class=lbl>Keywords '
        f'<span class=muted>comma separated</span></label>'
        f'<input class=inp name=keywords value="{_e(p.get("keywords",""))}" style="width:100%"></div>'
        f'<div class=row style="gap:14px;margin-top:14px">'
        f'<div style="flex:1"><label class=lbl>Hero image filename '
        f'<span class=muted>(in /assets)</span></label>'
        f'<input class=inp name=hero value="{_e(p.get("hero","hero-blog.webp"))}" style="width:100%"></div>'
        f'<div style="width:180px"><label class=lbl>Read time</label>'
        f'<input class=inp name=read_time value="{_e(p.get("read_time","5 min read"))}" style="width:100%"></div>'
        f'</div>'
        f'<div class=fld style="margin-top:14px"><label class=lbl>Body (HTML)</label>'
        f'<textarea class=inp name=body_html rows=18 required style="width:100%;font-family:monospace;'
        f'font-size:.85rem" placeholder="&lt;h2&gt;What is ...?&lt;/h2&gt;&#10;&lt;p&gt;Answer first...&lt;/p&gt;">'
        f'{_e(p.get("body_html",""))}</textarea></div>'
        f'<label class=chk style="margin-top:14px"><input type=checkbox name=published value=1 {pub_checked}> '
        f'Published (visible at /blog)</label>'
        f'<div style="margin-top:16px"><button class="btn" type=submit>Save post</button> '
        f'<a class="btn secondary" href="{b}/blog">Cancel</a></div>'
        f'</div></form>'
        f'<style>.fld .lbl{{display:block;font-size:.8rem;font-weight:600;color:var(--ink);'
        f'font-family:Sora,sans-serif;margin-bottom:6px}}.chk{{display:flex;align-items:center;gap:8px;'
        f'font-size:.9rem;color:var(--muted)}}</style>'
    ), flash)


def tax_page(flash="", err=""):
    """Admin: GST collected, editable rate, taxed transactions, and GSTIN list."""
    b = base_path()
    s = db.admin_tax_summary()
    err_html = f'<div class="err">{_e(err)}</div>' if err else ""

    def _inr(x):
        return f"₹{float(x):,.0f}"

    stats = "".join([
        f'<div class="stat rev"><b>{_inr(s["total_tax"])}</b><span>Total GST collected</span></div>',
        f'<div class="stat rev"><b>{_inr(s["tax_30"])}</b><span>GST (30 days)</span></div>',
        f'<div class=stat><b>{_inr(s["total_base"])}</b><span>Taxable sales (base)</span></div>',
        f'<div class=stat><b>{s["n_gstin"]}</b><span>Users with GSTIN</span></div>',
    ])

    txn_rows = "".join(
        f'<tr><td class=muted>{_e(t["created_at"][:10])}</td><td>{_e(t["email"])}</td>'
        f'<td>{_e(t["gstin"]) if t["gstin"] else "<span class=muted>-</span>"}</td>'
        f'<td>{_e(t["item"])}</td><td>{_inr(t["base"])}</td><td>{_inr(t["tax"])}</td>'
        f'<td><b>{_inr(t["total"])}</b></td></tr>' for t in s["txns"]) \
        or '<tr><td colspan=7 class=muted style="text-align:center;padding:20px">No taxed payments yet.</td></tr>'

    gstin_rows = "".join(
        f'<tr><td>{_e(g["email"])}</td><td><b style="font-family:Sora,sans-serif">{_e(g["gstin"])}</b></td></tr>'
        for g in s["gstins"]) \
        or '<tr><td colspan=2 class=muted style="text-align:center;padding:16px">No users have added a GSTIN yet.</td></tr>'

    rate_card = (
        f'<div class=card><h2>GST rate</h2>'
        f'<p class=hint>Applied to India (INR) payments only. International (USD) payments have no tax.</p>{err_html}'
        f'<form method=post action="{b}/tax/rate" class=row style="align-items:flex-end;gap:10px">'
        f'<div><label class=lbl style="display:block;font-size:.78rem;font-weight:600;'
        f'color:var(--muted2);margin-bottom:5px;font-family:Sora,sans-serif">Rate (%)</label>'
        f'<input class=inp name=rate type=number step=0.5 value="{s["rate"]:.0f}" style="width:120px"></div>'
        f'<button class="btn primary" type=submit>Save rate</button></form></div>')

    return _shell("Tax / GST", "tax", (
        f'<h1>Tax / GST</h1><p class=sub>GST collected on India payments (18% default). '
        f'International payments are not taxed.</p>'
        f'<div class=stats>{stats}</div>'
        f'{rate_card}'
        f'<div class=card><h2>Taxed transactions</h2>'
        f'<div class=tbl-wrap><table><thead><tr>'
        f'<th>Date</th><th>User</th><th>GSTIN</th><th>Item</th><th>Base</th><th>GST</th><th>Total</th>'
        f'</tr></thead><tbody>{txn_rows}</tbody></table></div></div>'
        f'<div class=card><h2>Users with GSTIN <span class=muted style="font-weight:400;font-size:.85rem">'
        f'(input tax credit claims)</span></h2>'
        f'<div class=tbl-wrap><table><thead><tr><th>User</th><th>GSTIN</th></tr></thead>'
        f'<tbody>{gstin_rows}</tbody></table></div></div>'
    ), flash)
