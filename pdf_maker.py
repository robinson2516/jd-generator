"""Generates a formatted PDF from job description text."""
import io
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable

ACCENT  = HexColor("#6366F1")
TEXT    = HexColor("#1E293B")
MUTED   = HexColor("#64748B")
BG_LINE = HexColor("#E2E8F0")

SECTIONS = {
    "job overview",
    "key responsibilities",
    "required qualifications",
    "preferred qualifications",
    "what we offer",
}


def make_pdf(job_title: str, company_name: str, content: str) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=letter,
        leftMargin=inch, rightMargin=inch,
        topMargin=0.9 * inch, bottomMargin=0.9 * inch,
    )

    title_style = ParagraphStyle(
        "JDTitle", fontSize=24, textColor=ACCENT,
        fontName="Helvetica-Bold", spaceAfter=4,
    )
    company_style = ParagraphStyle(
        "JDCompany", fontSize=13, textColor=MUTED,
        fontName="Helvetica", spaceAfter=16,
    )
    section_style = ParagraphStyle(
        "JDSection", fontSize=11, textColor=ACCENT,
        fontName="Helvetica-Bold", spaceBefore=14, spaceAfter=6,
        textTransform="uppercase",
    )
    body_style = ParagraphStyle(
        "JDBody", fontSize=10, textColor=TEXT,
        fontName="Helvetica", spaceAfter=4, leading=16,
    )
    bullet_style = ParagraphStyle(
        "JDBullet", fontSize=10, textColor=TEXT,
        fontName="Helvetica", spaceAfter=3, leading=16,
        leftIndent=14,
    )

    story = [
        Paragraph(job_title, title_style),
        Paragraph(company_name, company_style),
        HRFlowable(width="100%", thickness=1, color=BG_LINE, spaceAfter=10),
    ]

    for line in content.split("\n"):
        stripped = line.strip()
        if not stripped:
            story.append(Spacer(1, 4))
            continue

        # Section header detection
        clean = stripped.rstrip(":").lower()
        if clean in SECTIONS:
            story.append(Paragraph(stripped.rstrip(":"), section_style))
        elif stripped.startswith("- ") or stripped.startswith("• "):
            story.append(Paragraph("• " + stripped[2:], bullet_style))
        else:
            story.append(Paragraph(stripped, body_style))

    doc.build(story)
    return buf.getvalue()
