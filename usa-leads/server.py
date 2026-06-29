"""
usa-leads - MCP server.

Find USA (and later Jamaica / other) business leads, send free cold outreach
from Gmail, detect replies, and draft/send meeting replies. Zero paid tools:
Google Places (free tier) + Gmail SMTP/IMAP (app password) + Claude for copy.

Pipeline:
  find_leads      -> search Google Places, save new businesses
  enrich_emails   -> scrape their websites for a contact email
  preview_outreach-> eyeball the cold email for one lead before sending
  send_outreach   -> send cold emails (daily cap enforced), dry_run supported
  check_replies   -> poll Gmail inbox, match replies to leads
  draft_reply     -> build a warm reply (booking link or "what time works?")
  send_reply      -> send the reply in-thread (this call = your approval)
  pipeline_status -> dashboard of the whole funnel
  check_setup     -> verify keys + Gmail login work
"""
import time
import random

from fastmcp import FastMCP

import store
import leads as leadlib
import emailcopy as copylib
import mailer
import scheduler

mcp = FastMCP("usa-leads")
ENV = store.load_env()


def _truthy(v) -> bool:
    return str(v).strip().lower() in ("1", "true", "yes", "on")


# ---------------------------------------------------------------------------
@mcp.tool()
def check_setup() -> str:
    """Verify config keys and that Gmail SMTP+IMAP login works. Run this first."""
    lines = []
    for k in ("GOOGLE_PLACES_API_KEY", "GMAIL_ADDRESS", "GMAIL_APP_PASSWORD"):
        lines.append(f"{k}: {'set' if ENV.get(k) else 'MISSING'}")
    lines.append(f"SENDER_NAME: {ENV.get('SENDER_NAME')}")
    lines.append(f"SENDER_CITY: {ENV.get('SENDER_CITY')}")
    lines.append(f"BOOKING_LINK: {ENV.get('BOOKING_LINK') or '(empty - reply will ask for a time)'}")
    lines.append(f"DAILY_SEND_CAP: {ENV.get('DAILY_SEND_CAP')}  (sent today: {store.sent_today()})")
    lines.append(f"FULL_AUTO_REPLY: {ENV.get('FULL_AUTO_REPLY')}")
    try:
        store.require(ENV, "GMAIL_ADDRESS", "GMAIL_APP_PASSWORD")
        lines.append(mailer.verify_login(ENV))
    except Exception as e:
        lines.append(f"Gmail login check FAILED: {e}")
    return "\n".join(lines)


@mcp.tool()
def find_leads(city: str, category: str, limit: int = 20,
               only_no_website: bool = False) -> str:
    """
    Find businesses via Google Places and save the new ones as leads.

    city: e.g. "Austin TX" or "Kingston Jamaica".
    category: e.g. "plumbers", "dentists", "restaurants", "law firms".
    limit: max results (Places returns up to 20 per call).
    only_no_website: keep only businesses with NO website (best "build me a site" targets).
    """
    try:
        r = leadlib.find_leads(ENV, city, category, limit, only_no_website)
    except Exception as e:
        return f"find_leads failed: {e}"
    return (f"Query '{r['query']}': returned {r['returned']}, "
            f"added {r['added']} new leads ({r['no_website']} without a website), "
            f"{r['already_known']} already known. "
            f"Next: run enrich_emails to find their email addresses.")


@mcp.tool()
def enrich_emails(limit: int = 10) -> str:
    """Scrape websites of NEW leads to find a contact email. Marks dead leads (no site)."""
    try:
        r = leadlib.enrich_emails(ENV, limit)
    except Exception as e:
        return f"enrich_emails failed: {e}"
    return (f"Processed {r['processed']} leads: {r['enriched']} got an email, "
            f"{r['still_missing']} had a site but no email found, "
            f"{r['no_website_marked_dead']} had no site (marked no_email). "
            f"Next: preview_outreach or send_outreach.")


@mcp.tool()
def list_leads(status: str = "", limit: int = 30) -> str:
    """List saved leads, optionally filtered by status (new/emailed/replied/drafted/answered/no_email)."""
    rows = []
    for lead in store.load_leads().values():
        if status and lead.get("status") != status:
            continue
        rows.append(f"[{lead['status']:8}] {lead['name']}  "
                    f"<{lead.get('email') or 'no-email'}>  "
                    f"({lead.get('service_pitch')})  id={lead['place_id']}")
        if len(rows) >= limit:
            break
    if not rows:
        return "No leads match." if status else "No leads yet. Run find_leads."
    return "\n".join(rows)


@mcp.tool()
def preview_outreach(place_id: str) -> str:
    """Build and show the cold email for ONE lead (no send). Confirm copy before sending."""
    lead = store.get_lead(place_id)
    if not lead:
        return f"No lead with id {place_id}. Run list_leads to see ids."
    mail = copylib.build_outreach(lead, ENV.get("SENDER_NAME", ""), ENV.get("SENDER_CITY", ""))
    return (f"To: {lead.get('email') or '(no email yet - run enrich_emails)'}\n"
            f"Subject: {mail['subject']}\n\n{mail['body']}")


@mcp.tool()
def send_outreach(limit: int = 10, dry_run: bool = False) -> str:
    """
    Send cold outreach to leads that have an email and have not been emailed yet.
    Enforces DAILY_SEND_CAP. Use dry_run=true to preview without sending.
    """
    try:
        store.require(ENV, "GMAIL_ADDRESS", "GMAIL_APP_PASSWORD")
    except Exception as e:
        return str(e)

    leads = store.load_leads()
    quota = store.remaining_quota(ENV)
    if not dry_run and quota <= 0:
        return (f"Daily send cap reached ({ENV.get('DAILY_SEND_CAP')} sent today). "
                f"Try again tomorrow, or raise DAILY_SEND_CAP in .env.")

    sender = ENV.get("SENDER_NAME", "")
    city = ENV.get("SENDER_CITY", "")
    results, sent = [], 0
    for lead in leads.values():
        if sent >= limit:
            break
        if not dry_run and sent >= quota:
            results.append("... daily cap reached, stopping.")
            break
        if lead.get("status") != "new" or not lead.get("email"):
            continue
        mail = copylib.build_outreach(lead, sender, city)
        if dry_run:
            results.append(f"[DRY] -> {lead['email']} | {mail['subject']}")
            sent += 1
            continue
        try:
            mid = mailer.send_mail(ENV, lead["email"], mail["subject"], mail["body"])
            lead["status"] = "emailed"
            lead["message_id"] = mid
            lead["last_outreach"] = time.strftime("%Y-%m-%d %H:%M")
            store.bump_sent(1)
            sent += 1
            results.append(f"SENT -> {lead['email']} ({lead['name']})")
            # gentle spacing to look human (kept short so MCP does not hang)
            time.sleep(random.uniform(2, 5))
        except Exception as e:
            results.append(f"FAILED -> {lead['email']}: {e}")
    store.save_leads(leads)
    head = (f"Dry run, no emails sent. " if dry_run
            else f"Sent {sent}. Remaining today: {store.remaining_quota(ENV)}. ")
    if not results:
        return head + "No eligible leads (need status=new with an email)."
    return head + "\n" + "\n".join(results)


@mcp.tool()
def check_replies(since_days: int = 7) -> str:
    """
    Poll Gmail inbox for replies and match them to leads (by thread or sender).
    Marks matched leads as 'replied' and stores the reply snippet.
    If FULL_AUTO_REPLY=true, also drafts + sends a reply automatically.
    """
    try:
        store.require(ENV, "GMAIL_ADDRESS", "GMAIL_APP_PASSWORD")
        msgs = mailer.fetch_recent_inbox(ENV, since_days)
    except Exception as e:
        return f"check_replies failed: {e}"

    leads = store.load_leads()
    # index leads by message_id and by email for matching
    by_mid = {l["message_id"]: l for l in leads.values() if l.get("message_id")}
    by_email = {(l.get("email") or "").lower(): l for l in leads.values() if l.get("email")}

    matched, auto = [], []
    full_auto = _truthy(ENV.get("FULL_AUTO_REPLY"))
    for m in msgs:
        lead = None
        refs = (m["in_reply_to"] + " " + m["references"]).split()
        for r in refs:
            if r in by_mid:
                lead = by_mid[r]
                break
        if not lead:
            lead = by_email.get(m["from"])
        if not lead:
            continue
        if lead.get("status") in ("replied", "drafted", "answered", "booked"):
            continue  # already handled
        lead["status"] = "replied"
        lead["reply_snippet"] = m["body"][:500]
        lead["notes_subject"] = m["subject"]
        matched.append(f"{lead['name']} <{lead.get('email')}>: {m['body'][:80]}")

        if full_auto:
            mail = copylib.build_reply(lead, ENV.get("SENDER_NAME", ""), ENV.get("BOOKING_LINK", ""))
            try:
                mailer.send_mail(ENV, lead["email"], mail["subject"], mail["body"],
                                 in_reply_to=lead.get("message_id"))
                lead["status"] = "answered"
                auto.append(f"auto-replied {lead['name']}")
            except Exception as e:
                auto.append(f"auto-reply FAILED {lead['name']}: {e}")
    store.save_leads(leads)

    if not matched:
        return f"Checked {len(msgs)} inbox messages. No new replies matched leads."
    out = [f"Found {len(matched)} new replies:"] + matched
    if auto:
        out += ["", "Auto-reply (FULL_AUTO_REPLY on):"] + auto
    elif not full_auto:
        out += ["", "Next: draft_reply <place_id> then send_reply <place_id> to respond."]
    return "\n".join(out)


@mcp.tool()
def draft_reply(place_id: str) -> str:
    """Build a warm reply for a lead who replied. Stores the draft (does NOT send)."""
    lead = store.get_lead(place_id)
    if not lead:
        return f"No lead with id {place_id}."
    if lead.get("status") not in ("replied", "drafted"):
        return f"Lead status is '{lead.get('status')}'. draft_reply is for leads that replied."
    mail = copylib.build_reply(lead, ENV.get("SENDER_NAME", ""), ENV.get("BOOKING_LINK", ""))
    lead["draft_reply"] = mail["body"]
    lead["status"] = "drafted"
    store.upsert_lead(lead)
    return (f"Draft for {lead['name']} <{lead.get('email')}>:\n\n"
            f"Subject: {mail['subject']}\n\n{mail['body']}\n\n"
            f"They wrote: {lead.get('reply_snippet','')[:200]}\n\n"
            f"To send as-is: send_reply {place_id}. "
            f"To edit: send_reply {place_id} body=\"your text\".")


@mcp.tool()
def send_reply(place_id: str, body: str = "") -> str:
    """
    Send the reply to a lead in the same email thread (this call = your approval).
    If body is empty, uses the stored draft from draft_reply.
    """
    lead = store.get_lead(place_id)
    if not lead:
        return f"No lead with id {place_id}."
    if not lead.get("email"):
        return "Lead has no email."
    text = body.strip() or lead.get("draft_reply", "")
    if not text:
        return "No body given and no draft stored. Run draft_reply first."
    text = copylib.strip_dashes(text)
    subject = "Re: " + (lead.get("notes_subject") or "your reply")
    try:
        mailer.send_mail(ENV, lead["email"], copylib.strip_dashes(subject), text,
                         in_reply_to=lead.get("message_id"))
    except Exception as e:
        return f"send_reply failed: {e}"
    lead["status"] = "answered"
    store.upsert_lead(lead)
    return f"Reply sent to {lead['name']} <{lead['email']}>. Status -> answered."


@mcp.tool()
def mark_booked(place_id: str, notes: str = "") -> str:
    """Mark a lead as booked (meeting confirmed). Optional notes."""
    lead = store.get_lead(place_id)
    if not lead:
        return f"No lead with id {place_id}."
    lead["status"] = "booked"
    if notes:
        lead["notes"] = notes
    store.upsert_lead(lead)
    return f"{lead['name']} marked as booked. Congrats!"


@mcp.tool()
def run_daily_job() -> str:
    """
    Manually run the full daily pipeline now (same as the auto-scheduler):
    find_leads -> enrich -> send_outreach -> check_replies -> email summary.
    Uses AUTO_CITY / AUTO_CATEGORY from config.
    """
    return scheduler.run_daily_job(ENV)


@mcp.tool()
def pipeline_status() -> str:
    """Dashboard: lead counts per status, today's send count, and what needs action."""
    leads = store.load_leads()
    counts = {}
    need_action = []
    for l in leads.values():
        counts[l["status"]] = counts.get(l["status"], 0) + 1
        if l["status"] == "replied":
            need_action.append(f"  REPLY waiting: {l['name']} id={l['place_id']}")
    cap = ENV.get("DAILY_SEND_CAP")
    out = [f"Total leads: {len(leads)}"]
    for s in ("new", "emailed", "replied", "drafted", "answered", "booked", "no_email"):
        if counts.get(s):
            out.append(f"  {s}: {counts[s]}")
    out.append(f"Sent today: {store.sent_today()} / {cap}")
    if need_action:
        out.append("\nAction needed (draft_reply -> send_reply):")
        out += need_action
    return "\n".join(out)


def _bearer_auth(token: str):
    """Static Bearer-token verifier so a fixed MCP_AUTH_TOKEN protects the URL."""
    from fastmcp.server.auth.providers.jwt import StaticTokenVerifier
    return StaticTokenVerifier(tokens={token: {"client_id": "usa-leads"}})


def _run_http():
    """HTTP mode for hosting (Render). Uses PORT + MCP_AUTH_TOKEN from env."""
    port = int(ENV.get("PORT") or 8000)
    token = ENV.get("MCP_AUTH_TOKEN", "").strip()
    if token:
        try:
            mcp.auth = _bearer_auth(token)
            print("Auth ON (Bearer MCP_AUTH_TOKEN required).")
        except Exception as e:
            print(f"Could not enable auth ({e}); running OPEN.")
    else:
        print("WARNING: MCP_AUTH_TOKEN empty -> endpoint is OPEN. Set a token!")
    # start the daily auto-run thread (no-op unless AUTO_RUN=true)
    if scheduler.start(ENV):
        print(f"Auto-run scheduler ON (daily at {ENV.get('AUTO_HOUR_UTC')}:00 UTC).")
    mcp.run(transport="http", host="0.0.0.0", port=port)


if __name__ == "__main__":
    import sys
    # python server.py        -> stdio (Claude Code desktop / local)
    # python server.py http    -> HTTP (hosting: Render, etc.)
    # On Render the start command is: python server.py http
    if len(sys.argv) > 1 and sys.argv[1] == "http":
        _run_http()
    else:
        mcp.run()
