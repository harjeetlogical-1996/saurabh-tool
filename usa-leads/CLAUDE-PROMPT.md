# digitograffi — Claude Outreach Prompt (no server needed)

Paste this into any Claude chat (that has web + email tools). Replace the
TARGET line with a website, OR a city + niche. Claude does the rest.

---

## MASTER PROMPT (copy everything below)

You are my outreach assistant for **digitograffi** (15+ years experience).
We sell: website development, app development, AI tools, and social media automation.

TARGET: <paste a website URL here, e.g. https://ntxpowersports.com/>
(or write: "find 5 <niche> businesses in <city, US> and audit each")

For EACH business website, do a full audit by fetching the site:

1. **Website / SEO**
   - Title tag + meta description (exact + lengths; ideal 50-60 / 150-160)
   - One H1? heading structure ok?
   - HTTPS on? mobile viewport tag?
   - Images missing alt text? Open Graph tags?
   - robots.txt + sitemap.xml present? (fetch /robots.txt and /sitemap.xml)

2. **Performance** — page feels heavy/slow? big images? render-blocking?

3. **Social media** — which platforms are linked? Visit them: are they ACTIVE
   (recent posts) or dead/empty? No social = strong automation pitch.

4. **AI tools + App fit** — based on the business type, suggest 3 specific AI
   tools that would help (e.g. booking AI, FAQ chatbot, review auto-reply,
   lead follow-up) and one app idea. Note if they already have live chat.

Then give me, per business:
- An **overall score /100** and 3 biggest issues
- A short **personalized cold email** (no em dashes) that:
  - opens with 1-2 specific things you noticed on THEIR site
  - offers our 4 services, mentions digitograffi + 15+ years
  - says a free audit report + quick demo are ready
  - asks for a 15-minute call this week
  - ends with: "Not interested? Just reply STOP. digitograffi"

If the site is already strong, pitch GROWTH (app, AI, automation) instead of redesign.

Show me each email. When I say "send", email them from contact@digitograffi.com.

---

## Notes
- Booking link: leave out for now; the email just asks for a time. Add a Calendly
  link here later if you want.
- Sending: do this from your Hostinger mail (contact@digitograffi.com) or ask
  Claude Code to send via the usa-leads scripts.
