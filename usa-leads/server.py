"""
usa-leads - MCP server (the "plumbing" between Claude and the outside world).

Division of work:
  CLAUDE does the thinking: audits websites, writes the emails, writes replies,
  makes the PDF (all with its own built-in skills).
  THIS SERVER only connects things: pulls leads (max data), sends the email
  Claude wrote, reads the inbox, and sends the reply Claude wrote.

Tools:
  get_leads      -> find businesses with as much data as possible
                    (name, email, website, phone, address, rating, hours, social)
  add_lead       -> manually add one business you already have
  list_leads     -> see saved leads + their status
  send_email     -> send an email Claude wrote (optional PDF attachment, optional
                    save as a lead). Enforces a daily cap.
  get_replies    -> read recent inbox replies (so Claude can write responses)
  send_reply     -> send a reply Claude wrote, in the same thread
  fetch_page     -> return a page's raw text (helper if Claude needs the HTML)
  status         -> quick dashboard
  check_setup    -> verify mail login + which lead sources are available
"""
import time
import random

from fastmcp import FastMCP

import store
import leads as leadlib
import mailer

INSTRUCTIONS = """
usa-leads is the connection layer for digitograffi's client outreach.
Company: digitograffi. Experience: 15+ years. Services we sell:
website development, app development, AI tools, social media automation.

This SERVER only moves data (get_leads, add_lead, send_email, get_replies,
send_reply, fetch_page). YOU (Claude) do all the smart work with your own
skills: research, audit, write the email, write replies, make a PDF if useful.

============================================================
PLAYBOOK - follow this for every lead
============================================================

DATA YOU GET per lead: business name, person name (if found), email, website
(or none), phone, address, rating, source.

--- STEP 0: GREETING ---
- If a person's name is present, greet them by name: "Hi John,".
- If no person name, greet with the business name: "Hi Joe's Plumbing,".
  (Do not waste time hunting for the owner's name; business name is fine.)

--- STEP 1: FIND THEIR SOCIAL MEDIA (always, both cases) ---
Use your own web search: look up the business name + city to find their
Facebook / Instagram. Judge:
  - active (recent posts), or
  - exists but dead/empty (old or no posts), or
  - no social presence at all.
This shapes the social-media-automation angle of your pitch.

============================================================
CASE A - the business has NO website
============================================================
Open the email by naming the real problem, using the social finding:
  - If they HAVE social: "You are on [Instagram] but have no website, so people
    who find you cannot fully trust you or book/buy easily."
  - If NO social either: "Right now you are essentially invisible online, no
    website and no active social, so customers searching are going to competitors."
Then explain WHY it matters (local customers search Google first; without a site
they pick a competitor; reviews and trust live on a real site).
Offer: a professional website FIRST, then app, AI tools, and social media
automation as the growth plan.

============================================================
CASE B - the business HAS a website
============================================================
Audit the site yourself (fetch it, optionally use fetch_page): check title +
meta description, single H1, mobile-friendliness, HTTPS, rough speed/weight,
whether social is linked + active, whether they have live chat / online booking,
and where AI tools would fit. Then:
  - WEAK site: name the 2-4 concrete problems you found and how digitograffi
    fixes each, then add the other services.
  - STRONG site: do NOT push a redesign. Say the site is solid, then pitch
    GROWTH: an app for repeat customers, AI tools (booking/chatbot/review
    replies/lead follow-up), and social media automation.

============================================================
EMAIL STYLE (both cases) - detailed and professional
============================================================
- Greeting by name (step 0).
- A specific opening tied to THEIR site/social/business (not generic).
- A clear, professional explanation of what you found and WHY it costs them
  customers/money, with concrete points (a few sentences, not one line).
- Map the findings to digitograffi's services; mention 15+ years of experience.
- Offer a free audit report and a short demo; ask for a 15-minute call this week.
- Soft opt-out in the footer only: reply "unsubscribe". Never "STOP" in the body.
- Plain, professional English. NO em dashes or en dashes anywhere.

--- SENDING ---
Call send_email(to, subject, body, place_id=<lead id>). If you made a PDF,
pass attachment_path. Send automatically unless the user says "show me first".

============================================================
STAGED SALES FLOW (this is how outreach actually runs)
============================================================
PDF strategy is TWO TIERS (see PDF-AUDIT-FRAMEWORK.md):
  - TEASER PDF: attach to Email 1. Short, branded, shows overall score + 3-4 of
    the DEEPEST findings (the ones the owner does NOT already know - AI-search
    readiness, why a competitor outranks them, etc.). NOT basics, NOT the fixes.
    It states the full audit is ready and will be walked through on the call.
  - FULL PDFs (2 of them): revealed on/after the CALL only, never before.

Email 1 - TEASER + teaser PDF (sent): 80-120 words. Hook with the single biggest
  issue you found, name the competitor ranking above them for "{service} {city}",
  say you ran a full audit (site, SEO, AI-search readiness, social, ads) and N
  things stood out, give one concrete proof of digitograffi's work (15+ yrs),
  offer a 15-min screen-share where they keep the full reports. Build the teaser
  PDF with your own skill and pass its path as attachment_path to send_email.
  Subject must be specific (business name or a Google observation), never generic.

Email 2 - BOOKING (after they reply): acknowledge, answer their question, give
  TWO specific time slots in THEIR timezone (you are in India, they are US/UK),
  plus the booking link if one is configured. Two options beats "what time?".

Email 3 - SOFT NUDGE (replied but did not book, 2-3 days): one line, audit still
  ready, ask for a time in their timezone.

Email 4 - FOLLOW-UP (NO reply, ~4-5 days after Email 1): short nudge, offer open.
Email 5 - BREAKUP (NO reply, ~7-8 days after Email 4): "looks like not a priority,
  here are the top 3 fixes anyway, all the best." Often the highest reply rate.

Call due_followups() to see which emailed leads need Email 4 or 5, then send them.

TONE (every email): Hinglish in your head, clean English on the page. 80-120 words.
NO "I hope this email finds you well", NO "I wanted to reach out", avoid em dashes
(they flag as AI). One clear CTA. Confident, not needy. Always pair a time slot
with the client's timezone. Soft opt-out in the footer: reply "unsubscribe".
Do NOT put "STOP" in the body (spam-trigger in US/UK).

--- REPLIES ---
Call get_replies. For each reply, write Email 2 (booking) and send_reply(
place_id, subject, body). Add the booking link only if one is configured.

INPUTS: works both ways - a city + niche (call get_leads) OR a single business
the user names manually (call add_lead, then follow the playbook).
Safety: a daily send cap and the soft "unsubscribe" opt-out are required.
Never scrape LinkedIn. Full templates: EMAIL-TEMPLATES.md in the repo.
"""

mcp = FastMCP("usa-leads", instructions=INSTRUCTIONS)
ENV = store.load_env()


def _truthy(v) -> bool:
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def _lead_brief(l: dict) -> dict:
    """The data Claude needs to personalize, trimmed to the useful fields."""
    return {
        "id": l.get("place_id"), "name": l.get("name"), "email": l.get("email", ""),
        "website": l.get("website", ""), "phone": l.get("phone", ""),
        "address": l.get("address", ""), "rating": l.get("rating"),
        "rating_count": l.get("rating_count"), "hours": l.get("hours", ""),
        "maps_url": l.get("maps_url", ""), "category": l.get("category", ""),
        "city": l.get("city", ""), "source": l.get("source", ""),
        "status": l.get("status", "new"),
    }


# ---------------------------------------------------------------------------
@mcp.tool()
def check_setup() -> str:
    """Verify mail login works and show which lead sources are available."""
    lines = [f"Mail account: {store.mail_address(ENV) or 'MISSING'}",
             f"SMTP: {ENV.get('SMTP_HOST') or 'smtp.gmail.com'}:{ENV.get('SMTP_PORT') or '465'}",
             f"IMAP: {ENV.get('IMAP_HOST') or 'imap.gmail.com'}:{ENV.get('IMAP_PORT') or '993'}",
             "Lead sources:",
             "  osm: YES (no key)", "  yellowpages: YES (no key)",
             f"  google: {'YES' if ENV.get('GOOGLE_PLACES_API_KEY') else 'no key'}",
             f"  yelp: {'YES' if ENV.get('YELP_API_KEY') else 'no key'}",
             f"Daily send cap: {ENV.get('DAILY_SEND_CAP')} (sent today: {store.sent_today()})"]
    try:
        store.require_mail(ENV)
        lines.append(mailer.verify_login(ENV))
    except Exception as e:
        lines.append(f"Mail login FAILED: {e}")
    return "\n".join(lines)


@mcp.tool()
def get_leads(city: str, category: str, limit: int = 20, source: str = "all") -> str:
    """
    Find businesses and return as much data as possible for each
    (name, website, email, phone, address, rating, hours, Google Maps link).

    city: e.g. "Austin TX" or "Kingston Jamaica".
    category: the niche, e.g. "plumbers", "mobile pet grooming", "med spa".
    limit: how many leads to return.
    source: "all" (default) or osm / google / yelp / yellowpages.
            osm + yellowpages need no API key.

    After this, also try to enrich emails for leads that have a website.
    Returns a readable list; use the ids with send_email.
    """
    try:
        r = leadlib.find_leads(ENV, city, category, limit, False, source)
        if r.get("error"):
            return r["error"]
        # try to fill in emails from websites
        leadlib.enrich_emails(ENV, max(limit, 10))
    except Exception as e:
        return f"get_leads failed: {e}"

    leads = store.load_leads()
    rows, shown = [], 0
    for l in leads.values():
        if l.get("city") == city and l.get("category") == category and shown < limit:
            b = _lead_brief(l)
            rating = f"{b['rating']}*({b['rating_count']})" if b['rating'] else "no rating"
            rows.append(
                f"- {b['name']} | id={b['id']}\n"
                f"    email: {b['email'] or 'NOT FOUND'} | phone: {b['phone'] or '-'}\n"
                f"    website: {b['website'] or 'NONE'} | {rating}\n"
                f"    address: {b['address'] or '-'}\n"
                f"    maps: {b['maps_url'] or '-'} | source: {b['source']}")
            shown += 1
    per = ", ".join(f"{s}={n}" for s, n in r.get("per_source", {}).items())
    head = (f"Added {r['added']} new leads for '{category} in {city}' "
            f"(sources: {per}). Showing {shown}:\n")
    if r.get("errors"):
        head += "Notes: " + " | ".join(r["errors"]) + "\n"
    if not rows:
        return head + "(no leads - try source='osm' or a broader category)"
    return head + "\n".join(rows) + (
        "\n\nNext: audit each website yourself, write a tailored email, then "
        "call send_email(to=<email>, subject=..., body=..., place_id=<id>).")


@mcp.tool()
def add_lead(name: str, website: str = "", email: str = "", phone: str = "",
             city: str = "", category: str = "") -> str:
    """Manually add a single business you already have (e.g. the user named it)."""
    import hashlib
    pid = "manual:" + hashlib.md5((name + website).encode()).hexdigest()[:12]
    lead = store.new_lead_record(
        place_id=pid, name=name, city=city, website=website, phone=phone,
        category=category, has_website=bool(website), source="manual")
    lead["email"] = email
    if website and not email:
        try:
            found = leadlib.extract_email_from_site(website)
            if found:
                lead["email"] = found
        except Exception:
            pass
    store.upsert_lead(lead)
    b = _lead_brief(lead)
    return (f"Added: {b['name']} (id={b['id']})\n"
            f"email: {b['email'] or 'NOT FOUND'} | website: {b['website'] or '-'}\n"
            f"Now audit the site yourself and call send_email when ready.")


@mcp.tool()
def list_leads(status: str = "", limit: int = 40) -> str:
    """List saved leads, optionally filtered by status (new/emailed/replied/answered)."""
    rows = []
    for l in store.load_leads().values():
        if status and l.get("status") != status:
            continue
        rows.append(f"[{l.get('status','new'):8}] {l.get('name')} "
                    f"<{l.get('email') or 'no-email'}> id={l.get('place_id')}")
        if len(rows) >= limit:
            break
    return "\n".join(rows) if rows else "No leads. Run get_leads."


@mcp.tool()
def fetch_page(url: str) -> str:
    """Return a web page's visible text (helper if you need raw HTML to audit a site)."""
    try:
        html = leadlib._get(url if url.startswith("http") else "https://" + url, timeout=20)
    except Exception as e:
        return f"fetch failed: {e}"
    import re
    text = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:6000]


@mcp.tool()
def send_email(to: str, subject: str, body: str, place_id: str = "",
               attachment_path: str = "", dry_run: bool = False) -> str:
    """
    Send an email YOU wrote. Enforces the daily send cap.

    to: recipient email.
    subject / body: the email you composed (plain text, no em dashes).
    place_id: optional - the lead id, so we mark it emailed + can thread replies.
    attachment_path: optional - path to a PDF report you generated.
    dry_run: True = do not actually send, just confirm.
    """
    try:
        store.require_mail(ENV)
    except Exception as e:
        return str(e)
    if not to or "@" not in to:
        return "Invalid 'to' email."
    if not dry_run and store.remaining_quota(ENV) <= 0:
        return (f"Daily send cap reached ({ENV.get('DAILY_SEND_CAP')}). "
                f"Try tomorrow or raise DAILY_SEND_CAP.")
    if dry_run:
        return f"[DRY] would send to {to} | subject: {subject}"
    try:
        mid = mailer.send_mail(ENV, to, subject, body,
                               attachment_path=attachment_path or None)
    except Exception as e:
        return f"send failed: {e}"
    store.bump_sent(1)
    if place_id:
        lead = store.get_lead(place_id)
        if lead:
            lead["status"] = "emailed"
            lead["message_id"] = mid
            lead["last_outreach"] = time.strftime("%Y-%m-%d %H:%M")
            store.upsert_lead(lead)
    return (f"SENT to {to}. Remaining today: {store.remaining_quota(ENV)}. "
            f"Use get_replies later to catch a response.")


@mcp.tool()
def get_replies(since_days: int = 7) -> str:
    """
    Read recent inbox replies and match them to leads. Returns the reply text
    so YOU can write a response, then call send_reply.
    """
    try:
        store.require_mail(ENV)
        msgs = mailer.fetch_recent_inbox(ENV, since_days)
    except Exception as e:
        return f"get_replies failed: {e}"
    leads = store.load_leads()
    by_mid = {l["message_id"]: l for l in leads.values() if l.get("message_id")}
    by_email = {(l.get("email") or "").lower(): l for l in leads.values() if l.get("email")}
    out = []
    for m in msgs:
        lead = None
        for r in (m["in_reply_to"] + " " + m["references"]).split():
            if r in by_mid:
                lead = by_mid[r]
                break
        if not lead:
            lead = by_email.get(m["from"])
        if not lead:
            continue
        if lead.get("status") in ("answered", "booked"):
            continue
        lead["status"] = "replied"
        lead["reply_snippet"] = m["body"][:800]
        lead["notes_subject"] = m["subject"]
        store.upsert_lead(lead)
        out.append(f"REPLY from {lead['name']} <{lead.get('email')}> id={lead['place_id']}\n"
                   f"  subject: {m['subject']}\n  says: {m['body'][:300]}")
    if not out:
        return f"Checked {len(msgs)} inbox messages. No new replies from known leads."
    return ("New replies (write a response for each, then send_reply):\n\n"
            + "\n\n".join(out))


@mcp.tool()
def send_reply(place_id: str, subject: str, body: str) -> str:
    """Send a reply YOU wrote to a lead, in the same email thread."""
    lead = store.get_lead(place_id)
    if not lead:
        return f"No lead with id {place_id}."
    if not lead.get("email"):
        return "Lead has no email."
    try:
        store.require_mail(ENV)
        mailer.send_mail(ENV, lead["email"], subject, body,
                         in_reply_to=lead.get("message_id"))
    except Exception as e:
        return f"send_reply failed: {e}"
    lead["status"] = "answered"
    store.upsert_lead(lead)
    return f"Reply sent to {lead['name']} <{lead['email']}>. Status -> answered."


def _days_since(stamp: str) -> int:
    """Whole days since a 'YYYY-MM-DD HH:MM' stamp. Big number if unknown."""
    if not stamp:
        return 999
    try:
        t = time.strptime(stamp[:10], "%Y-%m-%d")
        return int((time.time() - time.mktime(t)) // 86400)
    except Exception:
        return 999


@mcp.tool()
def due_followups() -> str:
    """
    Show which emailed leads are due for a follow-up, by the cadence:
      - Email 4 (follow-up): emailed >= 4 days ago, still status 'emailed', no reply
      - Email 5 (breakup): emailed >= 11 days ago, still status 'emailed'
    Leads that replied are not chased here (use get_replies for those).
    For each due lead, write the right template and call send_email(place_id=...).
    """
    leads = store.load_leads()
    followup, breakup = [], []
    for l in leads.values():
        if l.get("status") != "emailed":
            continue
        d = _days_since(l.get("last_outreach", ""))
        line = (f"  {l['name']} <{l.get('email')}> id={l['place_id']} "
                f"(emailed {d}d ago, website: {l.get('website') or 'none'})")
        if d >= 11:
            breakup.append(line)
        elif d >= 4:
            followup.append(line)
    out = []
    if followup:
        out.append("DUE: Email 4 (follow-up):")
        out += followup
    if breakup:
        out.append("\nDUE: Email 5 (breakup):")
        out += breakup
    if not out:
        return "No follow-ups due right now."
    out.append("\nWrite the matching template and send_email(place_id=...) for each.")
    return "\n".join(out)


@mcp.tool()
def status() -> str:
    """Quick dashboard: lead counts per status + today's send count."""
    leads = store.load_leads()
    counts = {}
    waiting = []
    for l in leads.values():
        counts[l["status"]] = counts.get(l["status"], 0) + 1
        if l["status"] == "replied":
            waiting.append(f"  reply waiting: {l['name']} id={l['place_id']}")
    out = [f"Total leads: {len(leads)}"]
    for s in ("new", "emailed", "replied", "answered", "booked"):
        if counts.get(s):
            out.append(f"  {s}: {counts[s]}")
    out.append(f"Sent today: {store.sent_today()} / {ENV.get('DAILY_SEND_CAP')}")
    if waiting:
        out.append("\nReplies to answer (send_reply):")
        out += waiting
    return "\n".join(out)


# ---------------------------------------------------------------------------
def _bearer_auth(token: str):
    from fastmcp.server.auth.providers.jwt import StaticTokenVerifier
    return StaticTokenVerifier(tokens={token: {"client_id": "usa-leads"}})


def _oauth_auth(public_url: str):
    """OAuth 2.1 + Dynamic Client Registration + PKCE for Claude connectors."""
    from fastmcp.server.auth.providers.in_memory import (
        InMemoryOAuthProvider, ClientRegistrationOptions)
    return InMemoryOAuthProvider(
        base_url=public_url,
        client_registration_options=ClientRegistrationOptions(enabled=True),
        required_scopes=[],
    )


def _run_http():
    port = int(ENV.get("PORT") or 8000)
    public_url = (ENV.get("PUBLIC_URL", "").strip()
                  or "https://usa-leads.onrender.com").rstrip("/")
    token = ENV.get("MCP_AUTH_TOKEN", "").strip()
    if public_url:
        try:
            mcp.auth = _oauth_auth(public_url)
            print(f"Auth ON (OAuth, base_url={public_url}).")
        except Exception as e:
            print(f"OAuth setup failed ({e}); falling back.")
            if token:
                mcp.auth = _bearer_auth(token)
    elif token:
        mcp.auth = _bearer_auth(token)
        print("Auth ON (Bearer).")
    else:
        print("WARNING: endpoint OPEN (no PUBLIC_URL / MCP_AUTH_TOKEN).")
    mcp.run(transport="http", host="0.0.0.0", port=port)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "http":
        _run_http()
    else:
        mcp.run()
