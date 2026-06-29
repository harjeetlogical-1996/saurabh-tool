"""
usa-leads: Gmail send (SMTP) + read replies (IMAP). Pure stdlib.
Requires a Gmail App Password (not the normal password).
"""
import ssl
import smtplib
import imaplib
import email
from email.message import EmailMessage
from email.utils import make_msgid, parsedate_to_datetime
from datetime import datetime, timedelta, timezone

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465
IMAP_HOST = "imap.gmail.com"


# ---------------------------------------------------------------------------
# Send
# ---------------------------------------------------------------------------
def send_mail(env, to_addr, subject, body,
              in_reply_to=None, message_id=None) -> str:
    """Send a plain-text email. Returns the Message-ID used (for threading)."""
    addr = env["GMAIL_ADDRESS"]
    pw = env["GMAIL_APP_PASSWORD"]
    sender_name = env.get("SENDER_NAME", "")

    msg = EmailMessage()
    msg["From"] = f"{sender_name} <{addr}>" if sender_name else addr
    msg["To"] = to_addr
    msg["Subject"] = subject
    mid = message_id or make_msgid()
    msg["Message-ID"] = mid
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = in_reply_to
    msg.set_content(body)

    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ctx, timeout=30) as s:
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
    addr = env["GMAIL_ADDRESS"]
    pw = env["GMAIL_APP_PASSWORD"]
    since = (datetime.now(timezone.utc) - timedelta(days=since_days)).strftime("%d-%b-%Y")

    out = []
    M = imaplib.IMAP4_SSL(IMAP_HOST)
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
    addr = env["GMAIL_ADDRESS"]
    pw = env["GMAIL_APP_PASSWORD"]
    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ctx, timeout=20) as s:
        s.login(addr, pw)
    M = imaplib.IMAP4_SSL(IMAP_HOST)
    M.login(addr, pw)
    M.logout()
    return f"OK Gmail SMTP + IMAP login works for {addr}"
