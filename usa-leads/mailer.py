"""
usa-leads: send (SMTP) + read replies (IMAP). Pure stdlib.
Works with ANY SMTP/IMAP provider (Hostinger, Gmail, Zoho, ...).
Configure via MAIL_* keys; falls back to the old GMAIL_* keys for compatibility.
"""
import ssl
import json
import base64
import smtplib
import imaplib
import email
import urllib.request
import urllib.error
from email.message import EmailMessage
from email.utils import make_msgid, parsedate_to_datetime
from datetime import datetime, timedelta, timezone


# ---------------------------------------------------------------------------
# Resolve mail settings from env (provider-agnostic)
# ---------------------------------------------------------------------------
def _cfg(env):
    """Return (address, password, smtp_host, smtp_port, imap_host, imap_port)."""
    addr = env.get("MAIL_ADDRESS") or env.get("GMAIL_ADDRESS") or ""
    pw = env.get("MAIL_PASSWORD") or env.get("GMAIL_APP_PASSWORD") or ""
    smtp_host = env.get("SMTP_HOST") or "smtp.gmail.com"
    smtp_port = int(env.get("SMTP_PORT") or 465)
    imap_host = env.get("IMAP_HOST") or "imap.gmail.com"
    imap_port = int(env.get("IMAP_PORT") or 993)
    return addr, pw, smtp_host, smtp_port, imap_host, imap_port


# ---------------------------------------------------------------------------
# Send
# ---------------------------------------------------------------------------
def _send_via_brevo(env, to_addr, subject, body, attachment_path=None) -> str:
    """Send through Brevo's HTTP API (port 443) - works where SMTP is blocked
    (e.g. Render). Sends FROM your MAIL_ADDRESS (verify the domain in Brevo)."""
    key = env.get("BREVO_API_KEY", "").strip()
    addr, _, _, _, _, _ = _cfg(env)
    sender_name = env.get("SENDER_NAME", "") or addr
    payload = {
        "sender": {"email": addr, "name": sender_name},
        "to": [{"email": to_addr}],
        "subject": subject,
        "textContent": body,
    }
    if attachment_path:
        import os
        with open(attachment_path, "rb") as f:
            payload["attachment"] = [{
                "content": base64.b64encode(f.read()).decode(),
                "name": os.path.basename(attachment_path),
            }]
    req = urllib.request.Request(
        "https://api.brevo.com/v3/smtp/email",
        data=json.dumps(payload).encode(),
        method="POST",
        headers={"api-key": key, "content-type": "application/json",
                 "accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode("utf-8", errors="ignore"))
        return data.get("messageId", "brevo-sent")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Brevo error {e.code}: {e.read().decode('utf-8','ignore')[:300]}")


def send_mail(env, to_addr, subject, body,
              in_reply_to=None, message_id=None, attachment_path=None) -> str:
    """Send a plain-text email (optional PDF attachment). Returns the Message-ID.

    If BREVO_API_KEY is set, send via Brevo's HTTP API (works on Render where
    SMTP ports are blocked). Otherwise send via SMTP (works locally)."""
    if env.get("BREVO_API_KEY", "").strip():
        return _send_via_brevo(env, to_addr, subject, body, attachment_path)

    addr, pw, smtp_host, smtp_port, _, _ = _cfg(env)
    sender_name = env.get("SENDER_NAME", "")

    msg = EmailMessage()
    msg["From"] = f"{sender_name} <{addr}>" if sender_name else addr
    msg["To"] = to_addr
    msg["Subject"] = subject
    # build a Message-ID using the sender's own domain (better deliverability)
    domain = addr.split("@")[-1] if "@" in addr else None
    mid = message_id or make_msgid(domain=domain)
    msg["Message-ID"] = mid
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = in_reply_to
    msg.set_content(body)

    if attachment_path:
        import os
        with open(attachment_path, "rb") as f:
            data = f.read()
        fname = os.path.basename(attachment_path)
        msg.add_attachment(data, maintype="application", subtype="pdf", filename=fname)

    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL(smtp_host, smtp_port, context=ctx, timeout=30) as s:
        s.login(addr, pw)
        s.send_message(msg)
    return mid


# ---------------------------------------------------------------------------
# Read replies
# ---------------------------------------------------------------------------
def _decode_part(msg) -> str:
    """Extract the best-effort plain text body from a parsed email."""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                try:
                    return part.get_payload(decode=True).decode(
                        part.get_content_charset() or "utf-8", errors="ignore")
                except Exception:
                    continue
        return ""
    try:
        return msg.get_payload(decode=True).decode(
            msg.get_content_charset() or "utf-8", errors="ignore")
    except Exception:
        return msg.get_payload() or ""


def fetch_recent_inbox(env, since_days: int = 7) -> list:
    """Return recent inbox messages as dicts: from, subject, in_reply_to, references, body."""
    addr, pw, _, _, imap_host, imap_port = _cfg(env)
    since = (datetime.now(timezone.utc) - timedelta(days=since_days)).strftime("%d-%b-%Y")

    out = []
    M = imaplib.IMAP4_SSL(imap_host, imap_port)
    try:
        M.login(addr, pw)
        M.select("INBOX")
        typ, data = M.search(None, f'(SINCE {since})')
        if typ != "OK":
            return out
        ids = data[0].split()
        for num in reversed(ids):  # newest first
            typ, msg_data = M.fetch(num, "(RFC822)")
            if typ != "OK" or not msg_data or not msg_data[0]:
                continue
            msg = email.message_from_bytes(msg_data[0][1])
            frm = email.utils.parseaddr(msg.get("From", ""))[1].lower()
            out.append({
                "from": frm,
                "subject": msg.get("Subject", ""),
                "in_reply_to": (msg.get("In-Reply-To", "") or "").strip(),
                "references": (msg.get("References", "") or "").strip(),
                "body": _decode_part(msg).strip(),
                "date": msg.get("Date", ""),
            })
    finally:
        try:
            M.close()
        except Exception:
            pass
        M.logout()
    return out


def verify_login(env) -> str:
    """Quick credential check for both SMTP and IMAP. Returns 'OK ...' or raises."""
    addr, pw, smtp_host, smtp_port, imap_host, imap_port = _cfg(env)
    if not addr or not pw:
        raise RuntimeError("Mail address/password not set (MAIL_ADDRESS / MAIL_PASSWORD).")
    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL(smtp_host, smtp_port, context=ctx, timeout=20) as s:
        s.login(addr, pw)
    M = imaplib.IMAP4_SSL(imap_host, imap_port)
    M.login(addr, pw)
    M.logout()
    return f"OK SMTP({smtp_host}) + IMAP({imap_host}) login works for {addr}"
