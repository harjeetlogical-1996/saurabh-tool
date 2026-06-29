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
    # em dash, en dash, minus, figure dash -> plain
    for ch in ("—", "–", "−", "‒"):
        text = text.replace(ch, "-")
    # collapse a spaced standalone hyphen used as a dash into a comma
    text = text.replace(" - ", ", ")
    return text


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
