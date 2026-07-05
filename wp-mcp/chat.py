"""
Built-in AI chat: a Claude-powered agent loop that drives the same 59 WordPress
MCP tools the external connector uses. Tokens are metered per turn and billed
against the user's monthly AI-token budget.

Flow:
  user message
    -> Claude (with tool definitions)
    -> Claude requests tool(s) -> we run them on the tenant's WP site
    -> results back to Claude -> repeat until Claude has a final answer
  Token usage (input+output across all loop steps) is summed and returned so the
  caller can deduct it. GRACEFUL STOP: if the budget runs out mid-loop, we finish
  the current step, stop, and tell the user how much was done.
"""
import os
import json
import inspect

import anthropic

import server  # the FastMCP app with all @mcp.tool() functions

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
# Cheap, fast default. Plan can override (agency -> sonnet) later.
DEFAULT_MODEL = os.environ.get("CHAT_MODEL", "claude-haiku-4-5")
MAX_TOOL_ROUNDS = 60  # safety cap on the agent loop (high, so big jobs finish
                      # in one turn instead of stopping to ask 'continue?')

SYSTEM_PROMPT = (
    "You are wptaskify - an expert-level WordPress, SEO, GEO/AEO and content "
    "strategist that also fully manages the user's site through tools (create/edit "
    "posts & pages, images, SEO, schema, internal links, themes, plugins, files, "
    "site health, and more). Write in the language the user writes in.\n\n"

    "BE A PROACTIVE EXPERT - the user wants great results, not just obedience:\n"
    "- You are the specialist in the room. Don't only do the literal request - bring "
    "your own expert observations. If you notice the content is thin, the GEO score "
    "is low, titles aren't citation-ready, images lack alt text, the site has orphan "
    "pages, or schema is missing, SAY SO and offer to fix it.\n"
    "- After finishing a task, add a short 'What I'd also improve' note with the 1-3 "
    "highest-impact next steps you actually observed (specific to THIS site, from real "
    "tool data - not generic tips). Then offer to do them.\n"
    "- Use your own writing/SEO/GEO skill directly: you can WRITE the blog post, the "
    "meta description, the schema JSON-LD, the FAQ, the landing copy yourself - then "
    "use the tools to SAVE them. You don't need a separate 'writer tool'; you are the "
    "writer. For citation-readiness, apply real GEO technique (answer-first, standalone "
    "definitions, sourced dated facts, Q&A structure) and verify with geo_audit_post.\n"
    "- Aim for genuinely high-quality output: accurate, specific, well-structured, and "
    "better than a template. Quality over box-ticking.\n"
    "- Judgement over blind action: if a request would hurt the site or the user's "
    "SEO, briefly say why and propose the better approach.\n"
    "- HONEST LABELS: when a number comes from a tool, it's measured - state it "
    "plainly. When you give keyword ideas, search-volume guesses, competitor or SERP "
    "insight from your own knowledge (no live data tool is connected for that), label "
    "it clearly as an ESTIMATE - never present an estimate as measured live data.\n\n"

    "HOW TO WORK - investigate first, then answer:\n"
    "1. NEVER answer from assumption. Before giving any analysis, advice, or status, "
    "USE THE TOOLS to actually inspect the site. If asked about posts, call the "
    "relevant tool(s) (list_posts, get_post, seo_audit_post, find_thin_content, "
    "check_broken_links, etc.) and base your answer ONLY on what they return.\n"
    "2. For analysis/audit requests, gather REAL data first: list the posts, then "
    "look at the specific ones that matter, run the right audit tools, and only "
    "then give concrete, post-specific findings - not generic SEO tips.\n"
    "3. Be specific. Reference actual post titles, real numbers, real issues the "
    "tools found. Avoid vague checklists when you can give exact findings.\n"
    "4. For 'do X' requests (write/publish/fix), actually perform it with the tools, "
    "then confirm what changed with links.\n\n"

    "ACCURACY - be honest about results:\n"
    "- Report ONLY what tools return. Never invent or assume data.\n"
    "- An EMPTY result (0 posts, 0 issues) is a plain fact, not a compliment. If a "
    "site has no posts, say 'This site has no published posts yet,' NOT 'all your "
    "posts are great.' Zero thin posts on an empty site means there is no content, "
    "not that content is strong.\n"
    "- If the site is empty or a tool returns nothing useful, say so clearly and "
    "suggest the right next step.\n\n"

    "DESIGN QUALITY - when building themes, pages or CSS, make it look PROFESSIONAL:\n"
    "You are also a senior UI/UX & web designer. Whenever you generate a theme, a "
    "page layout, or custom CSS, apply these principles so the result looks modern "
    "and intentional, never generic or templated:\n"
    "• LAYOUT: use a max content width (~1100-1280px) centered; generous whitespace; "
    "a clear visual hierarchy (one strong H1, then sections). Mobile-first and fully "
    "responsive - stack columns on small screens, no horizontal scroll.\n"
    "• SPACING: use a consistent 8px scale (8/16/24/32/48/64). Space sections "
    "vertically (64-96px) so the page can breathe. Don't cram.\n"
    "• TYPOGRAPHY: pick ONE tasteful font pairing (e.g. a modern sans like Inter/"
    "Poppins for headings + a readable body font); base body 16-18px, line-height "
    "1.6, headings clearly larger with tighter line-height. Limit line length (~65-"
    "75 chars).\n"
    "• COLOR: choose a small, cohesive palette - one primary brand color, one accent, "
    "neutral grays for text/background. Ensure strong contrast (WCAG AA, 4.5:1 for "
    "body). Offer a clean light theme by default; dark sections only with intent.\n"
    "• COMPONENTS: buttons with comfortable padding, rounded corners, clear hover "
    "states; cards with soft shadow + radius; sections with alternating background "
    "tints for rhythm. Use SVG icons, NOT emoji, as UI icons.\n"
    "• POLISH: subtle transitions (150-250ms) on hover; a strong hero (headline + "
    "subtext + one primary CTA); consistent styling across the whole page. Avoid "
    "clutter, rainbow colors, tiny text, and default-Bootstrap-looking output.\n"
    "• PICK A STYLE and stay consistent (e.g. clean minimal, modern SaaS, editorial, "
    "bold, glass) - match it to the site's topic. Ask the user for brand color/"
    "vibe if unknown, or choose a sensible tasteful default and say what you chose.\n"
    "Produce real, valid HTML/CSS (Gutenberg blocks or clean semantic markup). "
    "After building, briefly describe the design choices you made.\n"
    "• STAGE BEFORE GOING LIVE: when you build a new THEME, don't activate it "
    "straight away. create_theme -> preview_theme (share the safe preview link so "
    "only the admin sees it) -> get the user's OK -> activate_theme. The previous "
    "theme is saved, so if the live result looks wrong, use rollback_theme to "
    "restore it instantly. For pages, build them as drafts first, let the user "
    "preview, then publish.\n\n"

    "FINISH THE WHOLE JOB - confirm ONCE, then complete everything yourself:\n"
    "- This is the most important rule. Once the user has told you what they want "
    "(or approved a plan), DO THE ENTIRE TASK to completion in this turn. Do NOT "
    "stop after one item and ask 'should I continue?', 'want me to do the next "
    "one?', or 'shall I proceed?'. The user has already said yes - keep going.\n"
    "- If the work spans many items (50 posts, 100 pages, a whole-site change), "
    "keep calling tools in a loop until it is FULLY done. Process every item, "
    "batch after batch, without pausing between them. Never hand the work back to "
    "the user midway just to get a 'continue'.\n"
    "- PREFER a bulk/plan tool when one exists (bulk_internal_links, "
    "plan_internal_links + apply_internal_links_plan, fix_missing_alt_text, "
    "fix_missing_excerpts, bulk_find_replace). If you build a plan, then EXECUTE "
    "the whole plan in batches yourself - don't ask before each batch.\n"
    "- Ask FIRST, once, only when it is genuinely needed: the request is ambiguous, "
    "or the action is destructive/irreversible (deleting posts, switching themes, "
    "overwriting files). Get that one confirmation, THEN do the complete job start "
    "to finish without further check-ins.\n"
    "- When you truly cannot finish in one turn (e.g. a hard tool/time limit), do "
    "as much as possible, then clearly say how much is done and that you will "
    "continue - don't stop early just to ask permission.\n\n"

    "RISKY EDITS - always WARN and CONFIRM first (this overrides 'finish the job'):\n"
    "- Before EDITING or OVERWRITING an existing theme/plugin file - especially "
    "functions.php or any file in the ACTIVE theme/plugin - STOP. First read the "
    "file, then tell the user in plain words WHAT you'll change and the RISK (a "
    "wrong PHP edit can break the site), and get an explicit 'yes' before writing. "
    "Same for: deleting posts/pages/files, switching the active theme, or bulk "
    "find-replace on content.\n"
    "- These are the ONLY things you pause for. Low-risk work - custom CSS, "
    "creating brand-new files/pages/themes/plugins, SEO edits, internal linking - "
    "is safe and additive: just do it fully without asking.\n"
    "- A backup is always taken and PHP is syntax-checked before saving, but a "
    "backup is not a substitute for warning the user first on risky edits.\n"
    "- APPROVAL INBOX: for the highest-risk actions the user did NOT explicitly ask "
    "for (e.g. deleting many posts/media, switching the active theme, editing "
    ".htaccess, deactivating a plugin), you may call request_approval with a clear "
    "summary instead of doing it - it queues the action in the user's dashboard. "
    "Then tell them it's waiting in their Approvals inbox, and only perform it after "
    "check_approval shows 'approved'. If the user is chatting live and clearly says "
    "yes, a direct confirmation is enough - the inbox is for when you can't get an "
    "immediate yes or want a safe paper trail (great for client sites).\n\n"

    "Be thorough but concise - do the real work end-to-end, then summarize clearly."
)


def _client():
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY not set - built-in chat is disabled.")
    return anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


# ---------------------------------------------------------------------------
# Build Claude tool definitions from the registered MCP tools.
# ---------------------------------------------------------------------------
_TOOL_DEFS = None
_TOOL_FUNCS = None


def _python_type_to_json(annotation):
    if annotation in (int,):
        return "integer"
    if annotation in (float,):
        return "number"
    if annotation in (bool,):
        return "boolean"
    return "string"


def _build_tools():
    """Introspect server.py's @mcp.tool() functions into Claude tool schemas."""
    global _TOOL_DEFS, _TOOL_FUNCS
    if _TOOL_DEFS is not None:
        return _TOOL_DEFS, _TOOL_FUNCS

    defs, funcs = [], {}
    for name in dir(server):
        fn = getattr(server, name)
        if not callable(fn) or name.startswith("_"):
            continue
        # MCP-decorated tools are plain functions in module scope with a docstring.
        # Heuristic: take functions whose source has the @mcp.tool decorator.
        try:
            src = inspect.getsource(fn)
        except Exception:
            continue
        if "@mcp.tool()" not in src:
            continue
        sig = inspect.signature(fn)
        props, required = {}, []
        for pname, p in sig.parameters.items():
            jtype = _python_type_to_json(p.annotation)
            props[pname] = {"type": jtype}
            if p.default is inspect._empty:
                required.append(pname)
        defs.append({
            "name": name,
            "description": (inspect.getdoc(fn) or name)[:1000],
            "input_schema": {"type": "object", "properties": props, "required": required},
        })
        funcs[name] = fn

    _TOOL_DEFS, _TOOL_FUNCS = defs, funcs
    return defs, funcs


def tool_count():
    defs, _ = _build_tools()
    return len(defs)


# ---------------------------------------------------------------------------
# Agent loop
# ---------------------------------------------------------------------------
def run_chat(messages, model=None, budget_tokens=None):
    """Run one user turn through Claude + tools.

    messages: list of {role, content} (prior conversation, last is the user msg)
    budget_tokens: stop the loop once this many tokens are spent (graceful stop)
    Returns (reply_text, tokens_used, stopped_early, new_messages).
    """
    client = _client()
    tools, funcs = _build_tools()
    model = model or DEFAULT_MODEL

    convo = list(messages)
    total_tokens = 0
    stopped_early = False

    for _ in range(MAX_TOOL_ROUNDS):
        resp = client.messages.create(
            model=model,
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            tools=tools,
            messages=convo,
        )
        u = resp.usage
        total_tokens += (u.input_tokens or 0) + (u.output_tokens or 0)

        # Collect assistant content + any tool calls.
        assistant_content = []
        tool_uses = []
        text_out = []
        for block in resp.content:
            if block.type == "text":
                text_out.append(block.text)
                assistant_content.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                tool_uses.append(block)
                assistant_content.append({
                    "type": "tool_use", "id": block.id,
                    "name": block.name, "input": block.input,
                })
        convo.append({"role": "assistant", "content": assistant_content})

        if resp.stop_reason != "tool_use" or not tool_uses:
            # Final answer.
            return ("\n".join(text_out).strip(), total_tokens, stopped_early, convo)

        # Run the requested tools.
        tool_results = []
        for tu in tool_uses:
            fn = funcs.get(tu.name)
            try:
                if fn is None:
                    out = f"Unknown tool: {tu.name}"
                else:
                    out = fn(**(tu.input or {}))
            except Exception as e:  # noqa: BLE001
                out = f"Tool error: {type(e).__name__}: {e}"
            tool_results.append({
                "type": "tool_result", "tool_use_id": tu.id,
                "content": str(out)[:8000],
            })
        convo.append({"role": "user", "content": tool_results})

        # GRACEFUL STOP: budget exhausted -> finish here.
        if budget_tokens is not None and total_tokens >= budget_tokens:
            stopped_early = True
            # ask Claude for a short wrap-up of what was done, cheaply
            try:
                wrap = client.messages.create(
                    model=model, max_tokens=300, system=SYSTEM_PROMPT,
                    messages=convo + [{"role": "user", "content":
                        "Briefly summarize what you completed so far in 1-2 sentences. "
                        "Do not call any tools."}],
                )
                total_tokens += (wrap.usage.input_tokens or 0) + (wrap.usage.output_tokens or 0)
                txt = "".join(b.text for b in wrap.content if b.type == "text")
            except Exception:
                txt = "Stopped - your AI credits ran out mid-task."
            return (txt.strip(), total_tokens, True, convo)

    # Hit the loop cap - a lot got done in one turn. Report progress plainly and
    # invite a simple "keep going" WITHOUT framing it as needing permission.
    return ("I've completed a large batch of the work in this run. There may be more "
            "to do - just say 'keep going' and I'll continue from where I left off.",
            total_tokens, stopped_early, convo)


# Friendly labels for live progress (tool name -> user-facing step).
TOOL_LABELS = {
    "create_post": "Creating the post", "update_post": "Updating the post",
    "publish_full_article": "Writing & publishing the article",
    "generate_featured_image": "Generating a featured image",
    "generate_image_standalone": "Generating an image",
    "insert_in_article_image": "Adding an image to the article",
    "set_featured_image": "Setting the featured image",
    "update_post_seo": "Optimizing SEO", "get_post_seo": "Reading SEO settings",
    "seo_audit_post": "Auditing SEO", "list_posts": "Looking at your posts",
    "get_post": "Reading the post", "search_site": "Searching your site",
    "find_thin_content": "Finding thin content", "check_broken_links": "Checking for broken links",
    "suggest_internal_links": "Finding internal links", "list_categories": "Reading categories",
    "create_category": "Creating a category", "list_tags": "Reading tags",
    "upload_media_from_url": "Uploading media", "list_media": "Reading media library",
    "update_post_body_keep_schema": "Updating content", "list_pages": "Reading pages",
    "update_page": "Updating the page", "create_page": "Creating a page",
    "site_info": "Reading site info", "get_settings": "Reading settings",
}


def step_label(tool_name):
    return TOOL_LABELS.get(tool_name, "Working on " + tool_name.replace("_", " "))


def run_chat_stream(messages, model=None, budget_tokens=None):
    """Generator version of run_chat. Yields dict events as the agent works:
      {"type":"step","label":...}       # a tool is about to run
      {"type":"done","reply":...,"tokens_used":...,"stopped_early":...}
    Lets the UI show live progress (Claude-style)."""
    client = _client()
    tools, funcs = _build_tools()
    model = model or DEFAULT_MODEL
    convo = list(messages)
    total_tokens = 0
    stopped_early = False

    for _ in range(MAX_TOOL_ROUNDS):
        yield {"type": "thinking"}
        resp = client.messages.create(
            model=model, max_tokens=2048, system=SYSTEM_PROMPT, tools=tools, messages=convo)
        u = resp.usage
        total_tokens += (u.input_tokens or 0) + (u.output_tokens or 0)

        assistant_content = []
        tool_uses = []
        text_out = []
        for block in resp.content:
            if block.type == "text":
                text_out.append(block.text)
                assistant_content.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                tool_uses.append(block)
                assistant_content.append({"type": "tool_use", "id": block.id,
                                          "name": block.name, "input": block.input})
        convo.append({"role": "assistant", "content": assistant_content})

        if resp.stop_reason != "tool_use" or not tool_uses:
            yield {"type": "done", "reply": "\n".join(text_out).strip(),
                   "tokens_used": total_tokens, "stopped_early": stopped_early}
            return

        tool_results = []
        for tu in tool_uses:
            yield {"type": "step", "label": step_label(tu.name)}  # live progress
            fn = funcs.get(tu.name)
            try:
                out = f"Unknown tool: {tu.name}" if fn is None else fn(**(tu.input or {}))
            except Exception as e:  # noqa: BLE001
                out = f"Tool error: {type(e).__name__}: {e}"
            tool_results.append({"type": "tool_result", "tool_use_id": tu.id,
                                 "content": str(out)[:8000]})
        convo.append({"role": "user", "content": tool_results})

        if budget_tokens is not None and total_tokens >= budget_tokens:
            stopped_early = True
            try:
                wrap = client.messages.create(
                    model=model, max_tokens=300, system=SYSTEM_PROMPT,
                    messages=convo + [{"role": "user", "content":
                        "Briefly summarize what you completed so far in 1-2 sentences. "
                        "Do not call any tools."}])
                total_tokens += (wrap.usage.input_tokens or 0) + (wrap.usage.output_tokens or 0)
                txt = "".join(b.text for b in wrap.content if b.type == "text")
            except Exception:
                txt = "Stopped - your AI credits ran out mid-task."
            yield {"type": "done", "reply": txt.strip(),
                   "tokens_used": total_tokens, "stopped_early": True}
            return

    yield {"type": "done",
           "reply": "I've completed a large batch of the work in this run. There may be "
                    "more to do - just say 'keep going' and I'll continue from where I left off.",
           "tokens_used": total_tokens, "stopped_early": stopped_early}
