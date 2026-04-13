"""Generates a formatted PDF from job description text."""
import io
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor, white
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.enums import TA_LEFT, TA_CENTER

RED         = HexColor("#DC2626")
RED_DARK    = HexColor("#B91C1C")
BLACK       = HexColor("#111111")
TEXT        = HexColor("#111111")
MUTED       = HexColor("#6B7280")
BORDER      = HexColor("#E5E5E5")

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
        leftMargin=0.85 * inch, rightMargin=0.85 * inch,
        topMargin=0.5 * inch, bottomMargin=0.85 * inch,
    )

    # ── Styles ────────────────────────────────────────────────────
    title_style = ParagraphStyle(
        "Title", fontSize=26, textColor=white,
        fontName="Helvetica-Bold", leading=32, spaceAfter=4,
    )
    company_style = ParagraphStyle(
        "Company", fontSize=13, textColor=HexColor("#FCA5A5"),
        fontName="Helvetica", spaceAfter=0,
    )
    section_style = ParagraphStyle(
        "Section", fontSize=10, textColor=RED,
        fontName="Helvetica-Bold", spaceBefore=18, spaceAfter=6,
        letterSpacing=1.2,
    )
    body_style = ParagraphStyle(
        "Body", fontSize=10, textColor=TEXT,
        fontName="Helvetica", spaceAfter=5, leading=16,
    )
    bullet_style = ParagraphStyle(
        "Bullet", fontSize=10, textColor=TEXT,
        fontName="Helvetica", spaceAfter=4, leading=16,
        leftIndent=16, firstLineIndent=0,
    )

    story = []

    # ── Header banner ─────────────────────────────────────────────
    page_width = letter[0] - 1.7 * inch
    header_data = [
        [Paragraph(job_title, title_style)],
        [Paragraph(company_name, company_style)],
    ]
    header_table = Table(header_data, colWidths=[page_width])
    header_table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), BLACK),
        ("ROUNDEDCORNERS", [8]),
        ("TOPPADDING",    (0, 0), (0, 0),   20),
        ("BOTTOMPADDING", (0, 0), (0, 0),   2),
        ("TOPPADDING",    (0, 1), (0, 1),   0),
        ("BOTTOMPADDING", (0, 1), (0, 1),   20),
        ("LEFTPADDING",   (0, 0), (-1, -1), 24),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 24),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 18))

    # ── Body ──────────────────────────────────────────────────────
    for line in content.split("\n"):
        stripped = line.strip()
        if not stripped:
            story.append(Spacer(1, 4))
            continue

        clean = stripped.rstrip(":").lower()
        if clean in SECTIONS:
            story.append(HRFlowable(width="100%", thickness=0.5, color=BORDER, spaceAfter=6))
            story.append(Paragraph(stripped.rstrip(":").upper(), section_style))
        elif stripped.startswith("- ") or stripped.startswith("• "):
            story.append(Paragraph("•  " + stripped[2:], bullet_style))
        else:
            story.append(Paragraph(stripped, body_style))

    # ── Footer ────────────────────────────────────────────────────
    story.append(Spacer(1, 24))
    story.append(HRFlowable(width="100%", thickness=0.5, color=BORDER))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        f"<font color='#94A3B8'>{company_name} — {job_title}</font>",
        ParagraphStyle("Footer", fontSize=8, fontName="Helvetica",
                       textColor=HexColor("#94A3B8"), alignment=TA_CENTER),
    ))

    doc.build(story)
    return buf.getvalue()
