"""
usa-leads: background scheduler for 24/7 auto-run on a host (e.g. Render).

Once a day (at AUTO_HOUR_UTC) it:
  1. finds fresh leads (AUTO_CITY / AUTO_CATEGORY)
  2. enriches their emails
  3. sends outreach (respects DAILY_SEND_CAP and AUTO_SEND_LIMIT)
  4. checks replies (auto-replies too if FULL_AUTO_REPLY=true)
  5. emails YOU a summary of what happened

Runs in a daemon thread started from server.py, so it lives as long as the
web service is up. State (last-run date) is kept in data/sched_state.json so a
restart on the same day does not double-run.
"""
import json
import time
import threading
import traceback
from datetime import datetime, timezone

import store
import leads as leadlib
import emailcopy as copylib
import mailer
import audit

STATE_FILE = store.DATA / "sched_state.json"


def _truthy(v) -> bool:
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def _load_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# The actual daily job (also callable manually as an MCP tool)
# ---------------------------------------------------------------------------
def run_daily_job(env: dict) -> str:
    log = []

    def step(label, fn):
        try:
            log.append(f"{label}: {fn()}")
        except Exception as e:
            log.append(f"{label}: ERROR {e}")

    city = env.get("AUTO_CITY", "").strip()
    category = env.get("AUTO_CATEGORY", "").strip()
    find_limit = int(env.get("AUTO_FIND_LIMIT", "20") or "20")
    send_limit = int(env.get("AUTO_SEND_LIMIT", "20") or "20")

    # 1. find (uses AUTO_SOURCE, default "osm" which needs no API key)
    auto_source = env.get("AUTO_SOURCE", "osm").strip() or "osm"
    if city and category:
        def _find():
            r = leadlib.find_leads(env, city, category, find_limit,
                                   only_no_website=False, source=auto_source)
            if r.get("error"):
                return r["error"]
            note = (" | " + "; ".join(r["errors"])) if r.get("errors") else ""
            return f"added {r['added']} ({r['no_website']} no-site), {r['already_known']} known{note}"
        step("find_leads", _find)
    else:
        log.append("find_leads: skipped (set AUTO_CITY and AUTO_CATEGORY)")

    # 2. enrich
    def _enrich():
        r = leadlib.enrich_emails(env, find_limit)
        return f"{r['enriched']} got email, {r['still_missing']} missing"
    step("enrich_emails", _enrich)

    # 3. send outreach
    def _send():
        leads = store.load_leads()
        quota = min(store.remaining_quota(env), send_limit)
        if quota <= 0:
            return "daily cap reached, nothing sent"
        sender = env.get("SENDER_NAME", "")
        company = env.get("COMPANY_NAME", "digitograffi")
        years = env.get("EXPERIENCE_YEARS", "15+")
        ps_key = env.get("PAGESPEED_API_KEY", "")
        sent = 0
        for lead in leads.values():
            if sent >= quota:
                break
            if lead.get("status") != "new" or not lead.get("email"):
                continue
            a = lead.get("audit") or audit.audit_site(lead.get("website", ""), ps_key)
            lead["audit"] = a
            mail = copylib.build_audit_outreach(lead, a, sender, company, years)
            mid = mailer.send_mail(env, lead["email"], mail["subject"], mail["body"])
            lead["status"] = "emailed"
            lead["message_id"] = mid
            lead["last_outreach"] = time.strftime("%Y-%m-%d %H:%M")
            store.bump_sent(1)
            sent += 1
            time.sleep(3)
        store.save_leads(leads)
        return f"sent {sent}"
    step("send_outreach", _send)

    # 4. check + (optionally) auto-reply
    def _replies():
        msgs = mailer.fetch_recent_inbox(env, since_days=7)
        leads = store.load_leads()
        by_mid = {l["message_id"]: l for l in leads.values() if l.get("message_id")}
        by_email = {(l.get("email") or "").lower(): l for l in leads.values() if l.get("email")}
        full_auto = _truthy(env.get("FULL_AUTO_REPLY"))
        matched = auto = 0
        for m in msgs:
            lead = None
            for r in (m["in_reply_to"] + " " + m["references"]).split():
                if r in by_mid:
                    lead = by_mid[r]
                    break
            if not lead:
                lead = by_email.get(m["from"])
            if not lead or lead.get("status") in ("replied", "drafted", "answered", "booked"):
                continue
            lead["status"] = "replied"
            lead["reply_snippet"] = m["body"][:500]
            lead["notes_subject"] = m["subject"]
            matched += 1
            if full_auto:
                mail = copylib.build_reply(lead, env.get("SENDER_NAME", ""), env.get("BOOKING_LINK", ""))
                mailer.send_mail(env, lead["email"], mail["subject"], mail["body"],
                                 in_reply_to=lead.get("message_id"))
                lead["status"] = "answered"
                auto += 1
        store.save_leads(leads)
        return f"{matched} new replies, {auto} auto-replied"
    step("check_replies", _replies)

    summary = "usa-leads daily run " + datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC") \
              + "\n\n" + "\n".join(log)

    # 5. email yourself the summary (to SUMMARY_EMAIL, else the sending account)
    try:
        if store.mail_address(env):
            to = env.get("SUMMARY_EMAIL", "").strip() or store.mail_address(env)
            mailer.send_mail(env, to, "usa-leads daily summary", summary)
    except Exception as e:
        summary += f"\n\n(could not email summary: {e})"
    return summary


# ---------------------------------------------------------------------------
# Background loop: wake every few minutes, run once per day at AUTO_HOUR_UTC
# ---------------------------------------------------------------------------
def _loop(env: dict):
    target_hour = int(env.get("AUTO_HOUR_UTC", "14") or "14")
    while True:
        try:
            now = datetime.now(timezone.utc)
            today = now.strftime("%Y-%m-%d")
            state = _load_state()
            if now.hour == target_hour and state.get("last_run") != today:
                summary = run_daily_job(env)
                state["last_run"] = today
                state["last_summary"] = summary[:2000]
                _save_state(state)
        except Exception:
            traceback.print_exc()
        time.sleep(300)  # check every 5 minutes


def start(env: dict):
    """Start the daily job in a daemon thread if AUTO_RUN is on."""
    if not _truthy(env.get("AUTO_RUN")):
        return False
    t = threading.Thread(target=_loop, args=(env,), daemon=True, name="usa-leads-sched")
    t.start()
    return True
