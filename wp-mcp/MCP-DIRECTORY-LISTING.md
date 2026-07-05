# wptaskify — MCP Directory Listing Kit

Ready-to-submit content for MCP directories (Smithery, mcp.so, PulseMCP, Glama,
awesome-mcp-servers, MCP.market, etc.). Copy-paste the fields each directory asks for.

---

## 1. Basic fields (most directories ask these)

**Name:** wptaskify

**Tagline (one line):**
> Connect WordPress to Claude or ChatGPT and let AI write, optimize, and publish — 110+ tools, nothing goes live without your approval.

**Short description (≈160 chars):**
> A remote MCP server that gives Claude & ChatGPT full control of your WordPress site: SEO, content, images, schema, themes, plugins — safely, with approvals and backups.

**Category / Tags:**
`wordpress`, `seo`, `content`, `cms`, `publishing`, `ai-writing`, `automation`, `web`

**Author:** wptaskify
**Website / Homepage:** https://wptaskify.com
**Documentation:** https://wptaskify.com/how-it-works
**License:** Proprietary (free tier available)
**Server type:** Remote (hosted, streamable HTTP)
**Auth:** OAuth 2.1 (per-user, bring your own AI account)

---

## 2. Full description (long-form)

**wptaskify** turns Claude or ChatGPT into a hands-on WordPress manager. Connect your
site once and your AI gains **110+ real WordPress tools** — not just chat, but actual
actions on your live site.

**What the AI can do:**
- ✍️ **Content** — write full SEO articles, create/update posts & pages, manage categories, tags, media, menus, and internal links.
- 🔍 **SEO & AI-SEO** — set meta titles/descriptions, generate schema (Article, FAQ, HowTo, Product), build sitemaps, and run an AI SEO Score covering On-Page, Technical, AEO and GEO so your content ranks in Google *and* gets cited by AI answer engines.
- 🖼️ **Images** — generate featured images with AI, write alt text, and bulk-optimize/convert to WebP.
- 🎨 **Design & build** — set custom CSS, create whole themes and plugins, edit files — all with **automatic backups and PHP syntax checks** before anything is written.
- 🛡️ **Safety-first** — every account is isolated, credentials are encrypted (AES-256), risky actions wait for your approval, and automatic backups let you roll back.

**Bring your own AI.** wptaskify plugs into the Claude or ChatGPT plan you already have —
no second AI subscription. Free to start; paid plans add more monthly usage and sites.

**Who it's for:** bloggers, small businesses, and agencies who want their WordPress site
on autopilot without hiring a team.

---

## 3. How to connect (install instructions for the listing)

wptaskify is a **remote MCP server** — nothing to run locally.

1. Install the free **wptaskify** plugin on your WordPress site (from wptaskify.com).
2. Click **Connect** in the plugin; sign in / create a free wptaskify account.
3. In Claude or ChatGPT, add the connector:
   - **MCP server URL:** `https://wptaskify.com/mcp`
   - Approve access in the same browser where you're logged in.
4. Ask your AI to manage your site: *"Write an SEO article about X and publish it as a draft."*

**Requirements:** self-hosted WordPress 5.6+ over HTTPS; a Claude or ChatGPT account that supports connectors.

---

## 4. MCP client config (for directories that show a config block)

### Claude (remote connector) — no local config needed
Add via Settings → Connectors → Add custom connector:
```
https://wptaskify.com/mcp
```

### Generic MCP client config (JSON)
```json
{
  "mcpServers": {
    "wptaskify": {
      "url": "https://wptaskify.com/mcp",
      "transport": "streamable-http"
    }
  }
}
```
> Auth is OAuth 2.1: the client is redirected to authorize, then uses a per-user bearer
> token. No API key is pasted into config.

---

## 5. Key facts block (for structured directories)

| Field | Value |
|---|---|
| Transport | Streamable HTTP (`/mcp`) |
| Auth | OAuth 2.1 (PKCE, per-user tokens) |
| Tools | 110+ |
| Hosting | Remote / hosted (no local install) |
| Data | Per-tenant isolated; credentials encrypted (AES-256-GCM) |
| Pricing | Free tier + paid plans (INR/USD) |
| Works with | Claude, ChatGPT (any MCP client) |

---

## 6. Example prompts (nice for listings that show usage)

- "Write a 1,200-word SEO article on '[topic]', add a featured image, set the meta title and description, and save it as a draft."
- "Audit my homepage for on-page, technical, AEO and GEO SEO and fix what you can."
- "Add FAQ schema to my top 5 posts."
- "Generate and set featured images for every post missing one."
- "Create a simple child theme and preview it before activating."

---

## 7. Where to submit (directory list)

Submit to these (most are free, PR- or form-based). Order = rough traffic/value:

1. **PulseMCP** — https://www.pulsemcp.com/ (submit form) — large, curated.
2. **mcp.so** — https://mcp.so/submit — big index.
3. **Smithery** — https://smithery.ai/ (best for installable/remote servers).
4. **Glama MCP** — https://glama.ai/mcp/servers (auto-crawls + manual submit).
5. **MCP.market** — https://mcp.market/ (submit form).
6. **awesome-mcp-servers** (GitHub) — open a PR adding wptaskify under a WordPress/CMS or "Web/SEO" category: https://github.com/punkpeye/awesome-mcp-servers
7. **Anthropic / Claude connectors directory** — if/when open; keep the connector polished.
8. **mcpservers.org**, **mcp-get.com**, **cursor.directory** (if targeting Cursor users).

**Tip:** most GitHub-based lists (awesome-mcp-servers) want a one-line entry:
```
- [wptaskify](https://wptaskify.com) — Connect WordPress to Claude/ChatGPT: 110+ tools for SEO, content, images, schema, themes and plugins, with approvals and backups.
```

---

## 8. Submission checklist (before you submit anywhere)

- [ ] `https://wptaskify.com/mcp` responds to the OAuth discovery (`/.well-known/oauth-protected-resource`) — already live.
- [ ] Homepage, pricing, how-it-works, privacy, security pages live — done.
- [ ] A short demo (GIF/video) of connecting + one AI action — **nice to add**, boosts approvals.
- [ ] Logo/icon (square, 256×256+) ready for directories that show one.
- [ ] Consistent tagline everywhere (use the one above).
