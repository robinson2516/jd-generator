"""Generates a formatted PDF from job description text."""
import io
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor, white, black
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, Image
from reportlab.lib.enums import TA_CENTER

BURNT_ORANGE = HexColor("#CC5500")
BODY_TEXT    = HexColor("#1A1A1A")
BORDER       = HexColor("#E0E0E0")

SECTIONS = {
    "job overview",
    "key responsibilities",
    "required qualifications",
    "preferred qualifications",
    "what we offer",
}


def make_pdf(
    job_title: str,
    company_name: str,
    content: str,
    logo_bytes=None,
) -> bytes:
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
        "Company", fontSize=13, textColor=HexColor("#FFD4B3"),
        fontName="Helvetica", spaceAfter=0,
    )
    section_style = ParagraphStyle(
        "Section", fontSize=10, textColor=BURNT_ORANGE,
        fontName="Helvetica-Bold", spaceBefore=18, spaceAfter=6,
        letterSpacing=1.2,
    )
    body_style = ParagraphStyle(
        "Body", fontSize=10, textColor=BODY_TEXT,
        fontName="Helvetica", spaceAfter=5, leading=16,
    )
    bullet_style = ParagraphStyle(
        "Bullet", fontSize=10, textColor=BODY_TEXT,
        fontName="Helvetica", spaceAfter=4, leading=16,
        leftIndent=16,
    )

    story = []

    # ── Header banner ─────────────────────────────────────────────
    page_width = letter[0] - 1.7 * inch
    LOGO_SIZE  = 56

    logo_cell = Paragraph("", company_style)
    if logo_bytes:
        try:
            from PIL import Image as PILImage
            is_svg = logo_bytes[:200].lstrip().startswith(b"<") and b"svg" in logo_bytes[:200].lower()
            if is_svg:
                raise ValueError("SVG not supported")
            pil_img = PILImage.open(io.BytesIO(logo_bytes)).convert("RGBA")
            png_buf = io.BytesIO()
            pil_img.save(png_buf, format="PNG")
            png_buf.seek(0)
            logo_img = Image(png_buf)
            ratio = min(LOGO_SIZE / logo_img.imageWidth, LOGO_SIZE / logo_img.imageHeight)
            logo_img.drawWidth  = logo_img.imageWidth  * ratio
            logo_img.drawHeight = logo_img.imageHeight * ratio
            logo_cell = logo_img
        except Exception:
            pass

    text_width  = page_width - LOGO_SIZE - 16
    header_data = [
        [Paragraph(job_title, title_style),    logo_cell],
        [Paragraph(company_name, company_style), ""],
    ]
    header_table = Table(header_data, colWidths=[text_width, LOGO_SIZE + 16])
    header_table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), BURNT_ORANGE),
        ("ROUNDEDCORNERS", [8]),
        ("TOPPADDING",    (0, 0), (-1, 0),  20),
        ("BOTTOMPADDING", (0, 0), (-1, 0),  2),
        ("TOPPADDING",    (0, 1), (-1, 1),  0),
        ("BOTTOMPADDING", (0, 1), (-1, 1),  20),
        ("LEFTPADDING",   (0, 0), (-1, -1), 24),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 16),
        ("VALIGN",        (1, 0), (1, 0),   "MIDDLE"),
        ("SPAN",          (1, 0), (1, 1)),
        ("ALIGN",         (1, 0), (1, 1),   "RIGHT"),
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
