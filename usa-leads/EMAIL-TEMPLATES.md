# digitograffi — Email Templates (review draft)

Rules for all: 80-120 words, Hinglish soch / clean English likho, no "I hope this
email finds you well", no "I wanted to reach out", one clear CTA, confident not
needy, every time slot with the client's timezone. Soft opt-out in footer
("reply 'unsubscribe' to opt out"), never "STOP" in the body.

Placeholders Claude fills: {first_name} {business} {city} {service}
{competitor} {top_issue} {issue_count} {proof_example} {BOOKING_LINK}

---

## EMAIL 1 — Teaser (the one that gets sent; NO PDF attached)

**Subject options (pick the most specific):**
- `{business} — quick thing I noticed on your site`
- `{competitor} is ranking above you for {service}`
- `{business} — found a few issues on Google`

**Body:**
```
Hi {first_name},

I was looking at {business} and noticed {top_issue} — the kind of thing
that quietly sends customers to people like {competitor}, who currently
show up above you for "{service} {city}".

So I ran a full audit of your site: SEO, speed, AI-search readiness, plus
your social and ads setup. {issue_count} things stood out, a few of them
easy wins.

At digitograffi (15+ years) this is exactly what we fix. We recently got
{proof_example}.

The full report and both analyses are ready. Happy to screen-share them on
a quick 15-minute call, then they are yours to keep.

Worth a look?

{first_name}, digitograffi

Not the right time? No worries, just ignore this. To opt out, reply "unsubscribe".
```

---

## EMAIL 2 — Reply aaya, ab booking (2 slots + link, their TZ)

**Subject:** `Re: {original subject}`

**Body:**
```
Hi {first_name},

Great to hear back, and good question about {thing_they_asked}.

Easiest is a quick screen-share so I can walk you through what I found.
Two times that work my side, in your timezone:

  - {Tue} 4:00 PM {their_TZ}
  - {Thu} 11:00 AM {their_TZ}

Either of those? Or grab whatever suits you here: {BOOKING_LINK}

It is 15 minutes, no pitch-y stuff, and you keep both reports after.

{first_name}, digitograffi
```
> If no {BOOKING_LINK} is set, drop that line and keep the two slots.

---

## EMAIL 3 — Reply but no booking (soft nudge, 2-3 days later)

**Subject:** `Re: {original subject}`

**Body:**
```
Hi {first_name},

Floating this back up — that audit of {business} is still ready whenever
you have 15 minutes. I will walk you through both reports and you keep them.

Just tell me a time that works in your timezone and I will send an invite.

{first_name}, digitograffi
```

---

## EMAIL 4 — No reply at all (follow-up, 4-5 days after Email 1)

**Subject:** `Re: {business} — quick thing I noticed`

**Body:**
```
Hi {first_name},

Quick nudge in case this slipped past — I put together a full audit of
{business} (site, SEO, AI-readiness, social, ads) and the free walkthrough
offer is still open.

15 minutes, I share my screen, you keep the reports. Want me to send a time?

{first_name}, digitograffi

To opt out, reply "unsubscribe".
```

---

## EMAIL 5 — Breakup (7-8 days after follow-up, no reply)

Breakup emails often get the highest reply rate.

**Subject:** `{business} — last note from me`

**Body:**
```
Hi {first_name},

Looks like this is not a priority right now, which is totally fair.

So you do not leave empty-handed, here are the top 3 things I would fix on
{business} first:

  1. {issue_1}
  2. {issue_2}
  3. {issue_3}

Hope they help. If things change, you know where I am. All the best.

{first_name}, digitograffi

To opt out, reply "unsubscribe".
```

---

## Notes
- Email 1 NEVER attaches the PDFs. PDFs are revealed on/after the call.
- Email 2/3 only after a reply. Email 4/5 only when NO reply (parallel track).
- Claude tracks which stage each lead is at and uses send_email / send_reply.
