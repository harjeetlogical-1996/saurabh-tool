"""
usa-leads: digitograffi-branded PDF audit report (pure Python via fpdf2).

build_pdf(audit, lead, env) -> path to a saved PDF in data/reports/.
Covers all four service angles: Website/SEO, Performance, Social, AI/App.
"""
from pathlib import Path
from fpdf import FPDF

import store

REPORTS = store.DATA / "reports"
REPORTS.mkdir(exist_ok=True)

# brand palette
INK = (28, 28, 34)
MUTED = (110, 110, 120)
BRAND = (124, 58, 237)     # purple
BRAND_DK = (76, 29, 149)
GOOD = (22, 163, 74)
WARN = (217, 119, 6)
BAD = (220, 38, 38)
LIGHT = (243, 240, 252)

SEV_COLOR = {"critical": BAD, "high": BAD, "medium": WARN, "low": MUTED}


def _clean(s: str) -> str:
    """fpdf core fonts are latin-1; replace anything outside it."""
    if not s:
        return ""
    repl = {"’": "'", "‘": "'", "“": '"', "”": '"',
            "–": "-", "—": "-", "…": "...", "•": "-"}
    for k, v in repl.items():
        s = s.replace(k, v)
    return s.encode("latin-1", "ignore").decode("latin-1")


class Report(FPDF):
    def __init__(self, company):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.company = company
        self.set_auto_page_break(auto=True, margin=18)

    def header(self):
        if self.page_no() == 1:
            return
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(*BRAND)
        self.cell(0, 8, _clean(self.company), align="L")
        self.set_text_color(*MUTED)
        self.set_font("Helvetica", "", 8)
        self.cell(0, 8, "Website Audit Report", align="R", new_x="LMARGIN", new_y="NEXT")
        self.ln(2)

    def footer(self):
        self.set_y(-14)
        self.set_font("Helvetica", "", 7)
        self.set_text_color(*MUTED)
        self.cell(0, 6, _clean(f"{self.company}  -  Prepared for you, free of charge"),
                  align="L")
        self.cell(0, 6, f"Page {self.page_no()}", align="R")

    def h2(self, text):
        self.ln(3)
        self.set_font("Helvetica", "B", 13)
        self.set_text_color(*BRAND_DK)
        self.cell(0, 8, _clean(text), new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(*BRAND)
        self.set_line_width(0.5)
        y = self.get_y()
        self.line(self.l_margin, y, self.l_margin + 40, y)
        self.ln(3)

    def para(self, text, size=10, color=INK):
        self.set_x(self.l_margin)
        self.set_font("Helvetica", "", size)
        self.set_text_color(*color)
        self.multi_cell(0, 5.5, _clean(text))
        self.ln(1)

    def bullet(self, text, size=10, color=INK):
        self.set_x(self.l_margin)
        self.set_font("Helvetica", "", size)
        self.set_text_color(*color)
        self.multi_cell(0, 5.5, _clean("-  " + text))


def _rating_color(score):
    return GOOD if score >= 75 else WARN if score >= 50 else BAD


def build_pdf(audit: dict, lead: dict, env: dict) -> str:
    company = env.get("COMPANY_NAME", "digitograffi")
    years = env.get("EXPERIENCE_YEARS", "15+")
    name = lead.get("name") or audit.get("business_name") or "Your Business"
    url = audit.get("url") or lead.get("website") or ""
    overall = audit.get("overall", 0)
    rating = audit.get("rating", "")

    pdf = Report(company)
    pdf.add_page()

    # ---- cover banner ----
    pdf.set_fill_color(*BRAND)
    pdf.rect(0, 0, 210, 55, "F")
    pdf.set_xy(0, 14)
    pdf.set_font("Helvetica", "B", 26)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(0, 12, _clean(company), align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 13)
    pdf.cell(0, 8, "Free Website & Growth Audit", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(18)

    pdf.set_text_color(*INK)
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 9, _clean(f"Prepared for: {name}"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(*MUTED)
    if url:
        pdf.cell(0, 6, _clean(url), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    # ---- overall score badge ----
    pdf.set_fill_color(*LIGHT)
    pdf.rect(pdf.l_margin, pdf.get_y(), 180, 26, "F")
    yy = pdf.get_y() + 5
    pdf.set_xy(pdf.l_margin + 4, yy)
    pdf.set_font("Helvetica", "B", 30)
    pdf.set_text_color(*_rating_color(overall))
    pdf.cell(40, 14, f"{overall}", align="L")
    pdf.set_xy(pdf.l_margin + 40, yy)
    pdf.set_font("Helvetica", "", 11)
    pdf.set_text_color(*INK)
    pdf.cell(0, 7, _clean(f"Overall score out of 100  -  {rating}"),
             new_x="LMARGIN", new_y="NEXT")
    pdf.set_xy(pdf.l_margin + 40, yy + 7)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*MUTED)
    pdf.multi_cell(130, 5, _clean("This report reviews your website, speed, social "
                                  "presence, and where AI and an app could help you grow."))
    pdf.ln(16)

    # ---- category scores ----
    pdf.h2("Score Breakdown")
    cats = audit.get("categories", {})
    pdf.set_font("Helvetica", "", 10)
    for cat, sc in cats.items():
        row_y = pdf.get_y()
        pdf.set_text_color(*INK)
        pdf.cell(55, 7, _clean(cat))
        # bar (drawn at a fixed x relative to the left margin)
        bx = pdf.l_margin + 55
        by = row_y + 1.5
        pdf.set_fill_color(225, 225, 230)
        pdf.rect(bx, by, 90, 4, "F")
        pdf.set_fill_color(*_rating_color(sc))
        pdf.rect(bx, by, 90 * sc / 100.0, 4, "F")
        pdf.set_xy(bx + 92, row_y)
        pdf.set_text_color(*_rating_color(sc))
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(20, 7, f"{sc}/100", align="L", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 10)

    # ---- speed ----
    ps = audit.get("pagespeed")
    if ps and ps.get("score") is not None:
        pdf.h2("Google Mobile Speed")
        pdf.para(f"Performance score: {ps['score']}/100. "
                 f"LCP {ps.get('lcp','?')}, CLS {ps.get('cls','?')}, "
                 f"Total Blocking Time {ps.get('tbt','?')}.")

    # ---- issues by severity ----
    issues = audit.get("issues", [])
    if issues:
        pdf.h2("What We Found (and How to Fix It)")
        order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        for it in sorted(issues, key=lambda x: order.get(x.get("sev"), 9)):
            sev = it.get("sev", "low")
            pdf.set_x(pdf.l_margin)
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_text_color(*SEV_COLOR.get(sev, MUTED))
            pdf.multi_cell(0, 5.5, _clean(f"[{sev.upper()}] {it['title']}"))
            pdf.set_font("Helvetica", "", 9)
            pdf.set_text_color(*MUTED)
            if it.get("why"):
                pdf.set_x(pdf.l_margin)
                pdf.multi_cell(0, 4.8, _clean("Why it matters: " + it["why"]))
            if it.get("fix"):
                pdf.set_x(pdf.l_margin)
                pdf.set_text_color(*GOOD)
                pdf.multi_cell(0, 4.8, _clean("Our fix: " + it["fix"]))
            pdf.ln(1.5)
    else:
        pdf.h2("Website Health")
        pdf.para("Good news: your website passed our core SEO and technical checks. "
                 "The biggest gains now are in social, AI, and an app (below).")

    # ---- social ----
    pdf.h2("Social Media Presence")
    pdf.para(audit.get("social_summary") or "No social profiles detected.")
    pdf.para(f"{company} can fully automate your social posting and replies, so it "
             f"runs every day without you lifting a finger.", color=BRAND_DK)

    # ---- AI + app ----
    pdf.h2("AI Tools We Recommend For You")
    for t in audit.get("ai_tools", [])[:5]:
        pdf.bullet(t)
    if audit.get("app_idea"):
        pdf.ln(1)
        pdf.para(f"App idea for you: {audit['app_idea']}.", color=BRAND_DK)

    # ---- CTA ----
    pdf.h2("Let's Talk")
    pdf.para(f"At {company} we have {years} years of experience helping local "
             f"businesses grow with better websites, apps, AI tools, and social "
             f"media automation. We would love to walk you through these findings "
             f"and show a quick demo. Reply to our email and we will set up a "
             f"15 minute call at a time that suits you.")
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(*BRAND)
    pdf.cell(0, 8, _clean(company), new_x="LMARGIN", new_y="NEXT")

    # ---- save ----
    safe = "".join(c for c in name if c.isalnum() or c in " -_").strip().replace(" ", "_")[:40]
    out = REPORTS / f"audit_{safe or 'site'}.pdf"
    pdf.output(str(out))
    return str(out)
