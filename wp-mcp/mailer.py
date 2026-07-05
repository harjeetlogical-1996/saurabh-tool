"""
Transactional email via Resend (https://resend.com).
Set RESEND_API_KEY (and optionally EMAIL_FROM) in the environment.

All emails share one branded, mobile-friendly template (_wrap). Each send_*
function is a specific notification: verification, password reset, welcome,
payment receipt, plan renewal reminder, low image credits, site connected.
"""
import os
import json
import urllib.request
import urllib.error

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
EMAIL_FROM = os.environ.get("EMAIL_FROM", "wptaskify <onboarding@resend.dev>")

# Seller (your business) details for the GST invoice. Set these in the environment.
SELLER_NAME = os.environ.get("SELLER_NAME", "wptaskify")
SELLER_ADDR = os.environ.get("SELLER_ADDRESS", "")
SELLER_GSTIN = os.environ.get("SELLER_GSTIN", "")
SELLER_EMAIL = os.environ.get("SELLER_EMAIL", "hello@wptaskify.com")
SAC_CODE = os.environ.get("SAC_CODE", "998314")  # SAC for IT/software services
SITE_URL = os.environ.get("PUBLIC_URL", "https://wptaskify.com").rstrip("/")
BRAND = "wptaskify"

# Brand colors (match the site)
_ACCENT = "#F97316"
_ACCENT_HI = "#FB923C"


def enabled():
    return bool(RESEND_API_KEY)


def _send(to, subject, html):
    if not RESEND_API_KEY:
        return False, "no_api_key"
    payload = json.dumps({
        "from": EMAIL_FROM, "to": [to], "subject": subject, "html": html,
    }).encode()
    req = urllib.request.Request(
        "https://api.resend.com/emails", data=payload, method="POST",
        headers={"Authorization": "Bearer " + RESEND_API_KEY,
                 "Content-Type": "application/json",
                 "Accept": "application/json",
                 "User-Agent": "wptaskify/1.0 (+https://wptaskify.com)"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return True, r.read().decode()
    except urllib.error.HTTPError as e:
        return False, f"{e.code}: {e.read().decode()[:200]}"
    except Exception as e:  # noqa: BLE001
        return False, str(e)[:200]


# --- Branded template ---------------------------------------------------------
# Light, clean, mobile-friendly. Inline styles only (email clients need it).
_LOGO = (
    f'<table role=presentation cellpadding=0 cellspacing=0><tr>'
    f'<td style="vertical-align:middle">'
    f'<div style="width:34px;height:34px;border-radius:9px;'
    f'background:linear-gradient(135deg,{_ACCENT},#FBBF24);display:inline-block;'
    f'text-align:center;line-height:34px;color:#0A0A0A;font-weight:800;'
    f'font-family:Arial,sans-serif;font-size:18px">W</div></td>'
    f'<td style="vertical-align:middle;padding-left:10px">'
    f'<span style="font-family:Arial,sans-serif;font-size:19px;font-weight:800;color:#14131A">'
    f'wp<span style="color:{_ACCENT}">taskify</span></span></td>'
    f'</tr></table>')


def _wrap(heading, body_html, button_text=None, button_url=None, accent=_ACCENT, footer_note=""):
    """One shared branded email shell. body_html is the main paragraph(s)."""
    button = ""
    if button_text and button_url:
        button = (
            f'<a href="{button_url}" style="display:inline-block;background:{accent};'
            f'color:#ffffff;font-weight:700;text-decoration:none;padding:13px 28px;'
            f'border-radius:11px;margin:22px 0 6px;font-family:Arial,sans-serif;font-size:15px">'
            f'{button_text}</a>'
            f'<p style="color:#8A8792;font-size:12px;margin:14px 0 0;line-height:1.5;'
            f'font-family:Arial,sans-serif">Button not working? Copy this link:<br>'
            f'<a href="{button_url}" style="color:{accent};word-break:break-all">{button_url}</a></p>')
    note = (f'<p style="color:#8A8792;font-size:13px;margin:18px 0 0;line-height:1.6;'
            f'font-family:Arial,sans-serif">{footer_note}</p>') if footer_note else ""
    return f"""<!doctype html><html><body style="margin:0;background:#F5F4F8;
font-family:Arial,Helvetica,sans-serif;padding:32px 14px">
<div style="max-width:520px;margin:0 auto">
<div style="padding:0 4px 20px">{_LOGO}</div>
<div style="background:#ffffff;border:1px solid #EAE8F0;border-radius:18px;
padding:36px 34px;box-shadow:0 8px 30px -18px rgba(20,19,26,.15)">
<h1 style="font-size:22px;margin:0 0 12px;color:#14131A;font-family:Arial,sans-serif;
letter-spacing:-.3px">{heading}</h1>
<div style="color:#5B5966;line-height:1.65;font-size:15px;font-family:Arial,sans-serif">{body_html}</div>
{button}
{note}
</div>
<p style="color:#9A98A4;font-size:12px;margin:20px 4px 0;line-height:1.6;font-family:Arial,sans-serif">
You're receiving this because you have a {BRAND} account.
<a href="{SITE_URL}/dashboard" style="color:{_ACCENT}">Manage your account</a> ·
&copy; 2026 {BRAND}. Connect WordPress to AI.</p>
</div></body></html>"""


# --- Auth emails --------------------------------------------------------------
def send_verify(to, link):
    body = ("Welcome to wptaskify! Confirm your email address to unlock your dashboard "
            "and start connecting your WordPress site to your own Claude or ChatGPT.")
    return _send(to, "Verify your wptaskify account",
                 _wrap("Verify your email", body, "Verify email", link,
                       footer_note="This link expires in 24 hours."))


def send_reset(to, link):
    body = ("We received a request to reset your wptaskify password. Click below to choose "
            "a new one. If you didn't ask for this, you can safely ignore this email.")
    return _send(to, "Reset your wptaskify password",
                 _wrap("Reset your password", body, "Reset password", link,
                       footer_note="This link expires in 1 hour."))


# --- Lifecycle / notification emails -----------------------------------------
def send_welcome(to, name=""):
    hi = f"Hi {name}," if name else "Hi there,"
    body = (f"{hi}<br><br>Welcome to wptaskify. Your site is one step away from running on "
            "autopilot with AI. Here's how to get started:<br><br>"
            "<b>1.</b> Install the free wptaskify plugin on your WordPress site<br>"
            "<b>2.</b> Click Connect - no passwords to copy<br>"
            "<b>3.</b> Add the connector in Claude or ChatGPT and just ask<br><br>"
            "You get 100+ tools, and nothing goes live without your approval.")
    return _send(to, "Welcome to wptaskify 🎉",
                 _wrap("Welcome to wptaskify", body, "Open your dashboard",
                       f"{SITE_URL}/dashboard"))


def send_payment_receipt(to, item, amount, currency="INR"):
    sym = "₹" if currency == "INR" else "$"
    body = (f"Thanks for your purchase! Your payment was successful and your account has "
            f"been updated.<br><br>"
            f"<b>Item:</b> {item}<br><b>Amount:</b> {sym}{amount}<br><br>"
            "You can view your plan, usage and billing history any time in your dashboard.")
    return _send(to, f"Payment received - {item}",
                 _wrap("Payment received ✓", body, "View billing",
                       f"{SITE_URL}/dashboard#plan", accent="#059669"))


def send_invoice(to, invoice_no, date_str, item, base, tax, total, rate,
                 currency="INR", buyer_gstin="", buyer_name=""):
    """Send a proper tax invoice email. For INR shows a full GST invoice (base +
    CGST/SGST or IGST); for USD a simple invoice (no tax)."""
    sym = "₹" if currency == "INR" else "$"

    def m(x):
        return f"{sym}{float(x):,.2f}"

    # tax rows: intra-state -> CGST+SGST split. Split so the two halves ALWAYS sum back
    # to the exact `tax` charged (CGST rounded, SGST is the remainder) - otherwise an odd
    # last paisa makes CGST+SGST != GST != amount paid, which fails GST reconciliation.
    tax_rows = ""
    if currency == "INR" and tax:
        cgst = round(float(tax) / 2, 2)
        sgst = round(float(tax) - cgst, 2)
        tax_rows = (
            f'<tr><td style="padding:8px 10px;color:#5B5966">CGST ({rate/2:.1f}%)</td>'
            f'<td style="padding:8px 10px;text-align:right;color:#5B5966">{m(cgst)}</td></tr>'
            f'<tr><td style="padding:8px 10px;color:#5B5966">SGST ({rate/2:.1f}%)</td>'
            f'<td style="padding:8px 10px;text-align:right;color:#5B5966">{m(sgst)}</td></tr>')

    seller_lines = f"<b>{SELLER_NAME}</b>"
    if SELLER_ADDR:
        seller_lines += f"<br>{SELLER_ADDR}"
    if SELLER_GSTIN:
        seller_lines += f"<br>GSTIN: {SELLER_GSTIN}"
    seller_lines += f"<br>{SELLER_EMAIL}"

    buyer_lines = f"<b>{buyer_name or to}</b><br>{to}"
    if buyer_gstin:
        buyer_lines += f"<br>GSTIN: {buyer_gstin}"

    inner = f"""
<table role=presentation width=100% style="font-family:Arial,sans-serif;font-size:13px;color:#5B5966;margin:6px 0 18px">
  <tr>
    <td style="vertical-align:top;width:50%;line-height:1.6">
      <div style="font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:#8A8792;margin-bottom:4px">From</div>
      {seller_lines}
    </td>
    <td style="vertical-align:top;width:50%;line-height:1.6">
      <div style="font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:#8A8792;margin-bottom:4px">Billed to</div>
      {buyer_lines}
    </td>
  </tr>
</table>
<table role=presentation width=100% style="font-family:Arial,sans-serif;font-size:13px;color:#5B5966;margin-bottom:16px">
  <tr><td>Invoice #: <b style="color:#14131A">{invoice_no}</b></td>
      <td style="text-align:right">Date: <b style="color:#14131A">{date_str}</b></td></tr>
</table>
<table role=presentation width=100% style="border:1px solid #EAE8F0;border-radius:10px;border-collapse:separate;
border-spacing:0;overflow:hidden;font-family:Arial,sans-serif;font-size:13px">
  <tr style="background:#F7F6FA">
    <td style="padding:10px;font-weight:700;color:#14131A">Description (SAC {SAC_CODE})</td>
    <td style="padding:10px;text-align:right;font-weight:700;color:#14131A">Amount</td>
  </tr>
  <tr><td style="padding:8px 10px;color:#5B5966">{item}</td>
      <td style="padding:8px 10px;text-align:right;color:#5B5966">{m(base)}</td></tr>
  {tax_rows}
  <tr style="border-top:1px solid #EAE8F0">
    <td style="padding:11px 10px;font-weight:800;color:#14131A">Total {'(incl. GST)' if tax else ''}</td>
    <td style="padding:11px 10px;text-align:right;font-weight:800;color:#14131A;font-size:15px">{m(total)}</td></tr>
</table>
<p style="color:#8A8792;font-size:12px;margin:16px 0 0;font-family:Arial,sans-serif">
{'GST charged as per applicable Indian tax law. ' if tax else ''}Payment received - thank you.
This is a computer-generated invoice.</p>"""
    return _send(to, f"Invoice {invoice_no} - {item}",
                 _wrap(f"Tax invoice", inner, "View billing",
                       f"{SITE_URL}/dashboard#plan", accent="#059669"))


def send_renew_reminder(to, plan, days, renews_on=""):
    when = f"in {days} day{'s' if days != 1 else ''}"
    body = (f"Your <b>{plan}</b> plan renews {when}"
            f"{(' on ' + renews_on) if renews_on else ''}.<br><br>"
            "No action is needed - your plan and all 100+ tools stay active. If you'd like "
            "to change or cancel, you can do it any time from your dashboard.")
    return _send(to, f"Your {plan} plan renews soon",
                 _wrap("Plan renewal reminder", body, "Manage plan",
                       f"{SITE_URL}/dashboard#plan"))


def send_low_images(to, left, plan):
    body = (f"Heads up - you have only <b>{left} AI image credit{'s' if left != 1 else ''}</b> "
            f"left this month on your {plan} plan.<br><br>"
            "Your credits reset on the 1st. Need more before then? Top up a one-time image "
            "pack, or upgrade your plan for a higher monthly limit.")
    return _send(to, f"Only {left} AI image credits left",
                 _wrap("Running low on image credits", body, "Buy more images",
                       f"{SITE_URL}/dashboard#plan", accent=_ACCENT_HI))


def send_low_actions(to, left, plan):
    body = (f"Heads up - you have only <b>{left} AI action{'s' if left != 1 else ''}</b> "
            f"left this month on your {plan} plan.<br><br>"
            "Actions reset on the 1st. To keep your AI working without interruption, "
            "upgrade your plan for a higher monthly limit.")
    return _send(to, f"Only {left} AI actions left",
                 _wrap("Running low on AI actions", body, "Upgrade plan",
                       f"{SITE_URL}/dashboard#plan", accent=_ACCENT_HI))


def send_site_connected(to, site_url):
    body = (f"Your WordPress site <b>{site_url}</b> is now connected to wptaskify. 🎉<br><br>"
            "The next step is to link your AI: add the wptaskify connector in Claude or "
            "ChatGPT, then just ask it to write, optimize or publish - it'll use your site's "
            "100+ tools for you.")
    return _send(to, "Your site is connected ✓",
                 _wrap("Site connected", body, "Connect your AI",
                       f"{SITE_URL}/dashboard", accent="#059669"))
