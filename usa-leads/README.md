# usa-leads

Free lead-gen + cold outreach + auto-reply MCP server. Find businesses (USA first,
then Jamaica / other countries), email them from your Gmail, catch replies, and
respond to schedule a call. No paid tools.

- **Leads**: Google Places API (free tier)
- **Email send/read**: your Gmail (SMTP + IMAP via an App Password)
- **Copy**: written by Claude through this MCP
- **Booking**: optional Calendly link (or the reply just asks for a time)

## Setup

1. Install deps:
   ```
   pip install fastmcp
   ```
   (Everything else is Python standard library.)

2. Get keys:
   - **Google Places**: Google Cloud Console -> enable *Places API (New)* -> create API key.
   - **Gmail App Password**: turn on 2-Step Verification -> Google Account -> Security
     -> App passwords -> generate one (16 chars).

3. Copy config:
   ```
   cp .env.example .env
   ```
   Fill in `GOOGLE_PLACES_API_KEY` and `GMAIL_APP_PASSWORD`.

4. Register with Claude (same way as reels-factory): add an MCP server that runs
   `python server.py` in this folder (stdio).

## Daily workflow (talk to Claude)

```
check_setup
find_leads city="Austin TX" category="plumbers" limit=20 only_no_website=true
enrich_emails limit=20
preview_outreach <place_id>        # eyeball one
send_outreach limit=10 dry_run=true   # check, then dry_run=false to send
check_replies                       # poll inbox
draft_reply <place_id>              # for anyone who replied
send_reply <place_id>               # sends it (your approval)
mark_booked <place_id>              # when a call is set
pipeline_status                     # dashboard
```

## Tools

| Tool | What it does |
|------|--------------|
| `check_setup` | Verify keys + Gmail login |
| `find_leads` | Search Google Places, save new leads |
| `enrich_emails` | Scrape websites for a contact email |
| `list_leads` | List leads (filter by status) |
| `preview_outreach` | Show the cold email for one lead |
| `send_outreach` | Send cold emails (daily cap, dry_run) |
| `check_replies` | Poll Gmail, match replies to leads |
| `draft_reply` | Build a warm reply (draft only) |
| `send_reply` | Send the reply in-thread |
| `mark_booked` | Mark a lead as booked |
| `run_daily_job` | Run the whole pipeline now + email a summary |
| `pipeline_status` | Funnel dashboard |

## Safety

- Daily send cap (`DAILY_SEND_CAP`, default 40) so Gmail does not suspend you.
- Every email has a `Reply STOP` opt-out line (CAN-SPAM basics).
- Replies are draft/approve by default (`FULL_AUTO_REPLY=false`).
- LinkedIn is never scraped (ban risk). Google Places only.

## Targets beyond USA

`find_leads` takes any location string, so just pass `city="Kingston Jamaica"` etc.
No code change needed to expand.

## Permanent URL + 24/7 auto-run (host on Render, free)

Your laptop does not need to stay on. Deploy the server to Render once; it gets a
permanent HTTPS URL and runs the daily job by itself.

### Deploy

1. Push this repo to GitHub (the `usa-leads/` folder must be in it).
2. On Render: **New + -> Blueprint -> pick this repo**. It reads `render.yaml`.
3. In the Render dashboard, fill the secret env vars (marked `sync:false`):
   `GOOGLE_PLACES_API_KEY`, `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`.
   `MCP_AUTH_TOKEN` is auto-generated. Copy its value (you need it for Claude).
4. Deploy. Render gives you a URL like `https://usa-leads.onrender.com`.
   Your MCP endpoint is `https://usa-leads.onrender.com/mcp`.

### Connect Claude to the hosted server

In Claude (claude.ai or desktop), add a remote MCP server:
- URL: `https://usa-leads.onrender.com/mcp`
- Header: `Authorization: Bearer <MCP_AUTH_TOKEN>`

### Auto-run

With `AUTO_RUN=true` (set in render.yaml), every day at `AUTO_HOUR_UTC` the server
runs find_leads -> enrich -> send_outreach -> check_replies and **emails you a
summary** at `GMAIL_ADDRESS`. Tune `AUTO_CITY`, `AUTO_CATEGORY`, limits in Render.
You can also trigger it any time from Claude with the `run_daily_job` tool.

### IMPORTANT about Render's free tier

Render free **web services sleep after ~15 min of no traffic**. A sleeping service
will MISS its scheduled daily run. Two fixes:

- **Easiest (free):** keep it awake with an external pinger. Create a free
  [cron-job.org](https://cron-job.org) or [UptimeRobot](https://uptimerobot.com)
  monitor that hits `https://usa-leads.onrender.com/mcp` every 10 minutes.
- **Or** instead of the built-in scheduler, set `AUTO_RUN=false` and have
  cron-job.org call the `run_daily_job` once a day (it wakes the service and runs).
- **True always-on** without pings: use an **Oracle Cloud always-free VM** (a real
  Linux box that never sleeps) and run `python server.py http` under systemd.

For most use, Render free + a 10-min UptimeRobot ping is the simplest 24/7 setup.
