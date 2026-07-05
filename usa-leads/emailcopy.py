"""
usa-leads: email copy builders (outreach + reply).
Rule: NO em/en dashes in any generated text (reviewshub-content-style).
"""

# ---------------------------------------------------------------------------
# Dash stripper - applied to every generated body before it leaves
# ---------------------------------------------------------------------------
def strip_dashes(text: str) -> str:
    if not text:
        return text
    # em dash, en dash, minus, figure dash -> plain hyphen
    for ch in ("—", "–", "−", "‒"):
        text = text.replace(ch, "-")
    # collapse a hyphen used as a sentence dash (mid-line ", word - word,")
    # into a comma, but DO NOT touch bullet lines that start with "- " or "  - ".
    out_lines = []
    for line in text.split("\n"):
        if line.lstrip().startswith("- "):
            out_lines.append(line)          # keep bullet hyphens
        else:
            out_lines.append(line.replace(" - ", ", "))
    return "\n".join(out_lines)


# ---------------------------------------------------------------------------
# Outreach: subject + body per service pitch
# ---------------------------------------------------------------------------
def _first_name_guess(business_name: str) -> str:
    # for a business we just greet the business itself
    return business_name.strip() or "there"


def _pitch_block(pitch: str, name: str, city: str) -> tuple:
    """Return (subject, opening, value) tuples per pitch type."""
    if pitch == "website":
        subject = f"Quick idea for {name}"
        opening = (f"I came across {name} while looking at businesses in {city} "
                   f"and noticed you do not have a website yet (or it is hard to find online).")
        value = ("I build clean, fast websites that help local customers find and "
                 "trust a business. I could put together a simple one for you so you "
                 "show up when people search for what you offer.")
    elif pitch == "ai tools":
        subject = f"AI tools that could save {name} hours"
        opening = (f"I was checking out {name} in {city} and thought you might be a "
                   f"good fit for some simple AI tools.")
        value = ("I help small teams set up AI that handles repetitive work like "
                 "replies, content, and lead follow up, so you spend less time on "
                 "busywork and more on customers.")
    else:  # digital marketing
        subject = f"Getting {name} in front of more local customers"
        opening = (f"I found {name} while looking at businesses in {city} and saw "
                   f"there is room to bring in more customers online.")
        value = ("I help local businesses get more calls and bookings through Google, "
                 "social, and a stronger online presence, without a big budget.")
    return subject, opening, value


def build_outreach(lead: dict, sender_name: str, sender_city: str) -> dict:
    name = _first_name_guess(lead.get("name", ""))
    city = lead.get("city", "your area")
    pitch = lead.get("service_pitch", "website")
    subject, opening, value = _pitch_block(pitch, name, city)

    body = (
        f"Hi {name},\n\n"
        f"{opening}\n\n"
        f"{value}\n\n"
        f"Would you be open to a quick 15 minute call this week? "
        f"If it is not useful, no problem at all.\n\n"
        f"Best,\n{sender_name}\n\n"
        f"Not interested? Just reply STOP and I will not write again. "
        f"{sender_name}, {sender_city}"
    )
    return {"subject": strip_dashes(subject), "body": strip_dashes(body)}


# ---------------------------------------------------------------------------
# Audit-based personalized outreach.
# Leads with specifics from the website audit, then offers the full service
# menu (website, app, AI tools, social media automation). Handles BOTH a weak
# site (lead with fixes) and a strong site (lead with growth ideas).
# ---------------------------------------------------------------------------
SERVICE_MENU = ("a faster modern website", "a mobile app",
                "AI tools to handle repetitive work",
                "social media automation that posts and replies for you")


def build_audit_outreach(lead: dict, audit: dict, sender_name: str,
                         company: str, years: str) -> dict:
    name = _first_name_guess(lead.get("name", ""))
    issues = audit.get("issues", [])
    has_site = bool(audit.get("reachable"))
    services = ", ".join(SERVICE_MENU[:-1]) + ", and " + SERVICE_MENU[-1]

    if not has_site:
        subject = f"{name} is hard to find on Google right now"
        opening = (f"I looked for {name} online and could not find a proper website. "
                   f"That means customers searching for what you do are landing on "
                   f"your competitors instead.")
        findings = ""
    elif issues:
        top = issues[:3]
        subject = f"A few things holding {name}'s website back"
        opening = ("I had a look at your website and a few things stood out that are "
                   "quietly costing you customers.")
        findings = "Here is what I noticed:\n" + "\n".join(f"  - {t}" for t in top) + "\n\n"
    else:
        subject = f"Ideas to get {name} even more customers"
        opening = ("I had a look at your website and honestly it is already solid. "
                   "So instead of a redesign, I want to share a few ways to pull in "
                   "more customers from it.")
        findings = ("A clean site like yours is the perfect base to add online booking, "
                    "an app for repeat customers, and automation that follows up with "
                    "every lead.\n\n")

    body = (
        f"Hi {name},\n\n"
        f"{opening}\n\n"
        f"{findings}"
        f"I have attached a short free audit report so you can see exactly what I mean.\n\n"
        f"At {company} we have {years} years of experience helping local businesses "
        f"grow online. We can help with {services}, whatever fits you best.\n\n"
        f"If it looks useful, I can walk you through it and show a quick demo. "
        f"Want to hop on a 15 minute call this week?\n\n"
        f"Best,\n{sender_name}\n{company}\n\n"
        f"Not interested? Just reply STOP and I will not write again. {company}"
    )
    return {"subject": strip_dashes(subject), "body": strip_dashes(body)}


# ---------------------------------------------------------------------------
# Reply: warm response that moves toward a call
# ---------------------------------------------------------------------------
def build_reply(lead: dict, sender_name: str, booking_link: str = "") -> dict:
    name = _first_name_guess(lead.get("name", ""))
    if booking_link:
        cta = (f"You can grab a time that suits you here: {booking_link}\n"
               f"Pick any slot and I will be there.")
    else:
        cta = ("What time works for a quick 15 minute call this week? "
               "I am flexible to your timezone.")
    body = (
        f"Hi {name},\n\n"
        f"Thanks for getting back to me, really appreciate it.\n\n"
        f"{cta}\n\n"
        f"Looking forward to it.\n\n"
        f"Best,\n{sender_name}"
    )
    subject = f"Re: " + (lead.get("notes_subject") or "your reply")
    return {"subject": strip_dashes(subject), "body": strip_dashes(body)}
