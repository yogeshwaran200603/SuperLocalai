"""
Astra-Local Document Generation Tools
Generates Microsoft PowerPoint (.pptx), Word (.docx), Excel (.xlsx),
and PDF reports via python-pptx, python-docx, openpyxl, and reportlab.
"""

import os
from pathlib import Path
from typing import Dict, Any, List, Optional
from config import DESKTOP_DIR


def doc_create_pptx(
    title: str,
    slides: List[Dict[str, Any]],
    output_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Creates a PowerPoint presentation (.pptx).
    Default output is on Desktop.
    slides format:
    [
        {"title": "Slide Title", "bullets": ["Point 1", "Point 2"], "subtitle": "Optional Subtitle"}
    ]
    """
    try:
        from pptx import Presentation
        from pptx.util import Inches, Pt
        from pptx.dml.color import RGBColor

        prs = Presentation()
        # Slide width & height 16:9 standard
        prs.slide_width = Inches(13.333)
        prs.slide_height = Inches(7.5)

        # Title Slide Layout (0)
        title_slide_layout = prs.slide_layouts[0]
        first_slide = prs.slides.add_slide(title_slide_layout)
        first_slide.shapes.title.text = title
        if slides and "subtitle" in slides[0]:
            first_slide.placeholders[1].text = slides[0]["subtitle"]
        elif len(slides) > 0 and "bullets" in slides[0] and len(slides[0]["bullets"]) > 0:
            first_slide.placeholders[1].text = slides[0]["bullets"][0]

        # Remaining content slides
        bullet_slide_layout = prs.slide_layouts[1]
        for slide_data in slides[1:] if len(slides) > 1 and "subtitle" in slides[0] else slides:
            s_title = slide_data.get("title", "")
            bullets = slide_data.get("bullets", [])

            slide = prs.slides.add_slide(bullet_slide_layout)
            slide.shapes.title.text = s_title

            tf = slide.placeholders[1].text_frame
            tf.word_wrap = True

            for idx, bullet_text in enumerate(bullets):
                if idx == 0:
                    p = tf.paragraphs[0]
                    p.text = bullet_text
                    p.font.size = Pt(22)
                else:
                    p = tf.add_paragraph()
                    p.text = bullet_text
                    p.font.size = Pt(20)

        if not output_path:
            clean_name = "".join(c for c in title if c.isalnum() or c in (" ", "_", "-")).strip()
            out = DESKTOP_DIR / f"{clean_name or 'Presentation'}.pptx"
        else:
            out = Path(os.path.expandvars(output_path)).resolve()

        out.parent.mkdir(parents=True, exist_ok=True)
        prs.save(str(out))

        return {
            "success": True,
            "saved_path": str(out),
            "slide_count": len(prs.slides),
            "title": title,
            "message": f"Successfully created presentation at {out} with {len(prs.slides)} slides."
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def doc_create_docx(
    title: str,
    sections: List[Dict[str, Any]],
    output_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Creates a Word document (.docx).
    sections format:
    [
        {"heading": "Introduction", "text": "Paragraph...", "bullets": ["Item 1", "Item 2"]}
    ]
    """
    try:
        from docx import Document
        from docx.shared import Pt, Inches, RGBColor

        doc = Document()
        doc.add_heading(title, level=0)

        for sec in sections:
            heading = sec.get("heading")
            if heading:
                doc.add_heading(heading, level=1)
            text = sec.get("text")
            if text:
                doc.add_paragraph(text)
            bullets = sec.get("bullets", [])
            for b in bullets:
                doc.add_paragraph(b, style="List Bullet")

        if not output_path:
            clean_name = "".join(c for c in title if c.isalnum() or c in (" ", "_", "-")).strip()
            out = DESKTOP_DIR / f"{clean_name or 'Document'}.docx"
        else:
            out = Path(os.path.expandvars(output_path)).resolve()

        out.parent.mkdir(parents=True, exist_ok=True)
        doc.save(str(out))

        return {
            "success": True,
            "saved_path": str(out),
            "sections": len(sections),
            "message": f"Word document created at {out}"
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def doc_create_xlsx(
    output_path: str,
    sheets_data: Dict[str, List[Dict[str, Any]]]
) -> Dict[str, Any]:
    """
    Creates an Excel spreadsheet (.xlsx) with styled headers.
    sheets_data format:
    {
        "Sales": [{"Month": "Jan", "Revenue": 1000}, {"Month": "Feb", "Revenue": 1500}]
    }
    """
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

        wb = openpyxl.Workbook()
        # remove default sheet
        default_sheet = wb.active

        header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="1F497D", end_color="1F497D", fill_type="solid")

        first = True
        for sheet_name, rows in sheets_data.items():
            ws = wb.create_sheet(title=sheet_name) if not first else wb.active
            if first:
                ws.title = sheet_name
                first = False

            if not rows:
                continue

            headers = list(rows[0].keys())
            ws.append(headers)

            # Style headers
            for col_num in range(1, len(headers) + 1):
                cell = ws.cell(row=1, column=col_num)
                cell.font = header_font
                cell.fill = header_fill
                cell.alignment = Alignment(horizontal="center")

            # Add rows
            for r in rows:
                ws.append([r.get(h, "") for h in headers])

            # Auto-adjust column width
            for col in ws.columns:
                max_len = max(len(str(cell.value or "")) for cell in col)
                col_letter = col[0].column_letter
                ws.column_dimensions[col_letter].width = max(max_len + 3, 12)

        out = Path(os.path.expandvars(output_path)).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        wb.save(str(out))

        return {
            "success": True,
            "saved_path": str(out),
            "sheets": list(sheets_data.keys()),
            "message": f"Excel workbook saved to {out}"
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def doc_create_pdf(
    title: str,
    sections: List[Dict[str, Any]],
    output_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Generates a PDF document report using ReportLab.
    """
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, ListItem, ListFlowable
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib import colors

        if not output_path:
            clean_name = "".join(c for c in title if c.isalnum() or c in (" ", "_", "-")).strip()
            out = DESKTOP_DIR / f"{clean_name or 'Report'}.pdf"
        else:
            out = Path(os.path.expandvars(output_path)).resolve()

        out.parent.mkdir(parents=True, exist_ok=True)
        doc = SimpleDocTemplate(str(out), pagesize=letter, rightMargin=54, leftMargin=54, topMargin=54, bottomMargin=54)

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle("CustomTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=24, spaceAfter=20, textColor=colors.HexColor("#1A237E"))
        heading_style = ParagraphStyle("CustomHeading", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=16, spaceBefore=15, spaceAfter=8, textColor=colors.HexColor("#283593"))
        body_style = ParagraphStyle("CustomBody", parent=styles["BodyText"], fontName="Helvetica", fontSize=10, spaceAfter=6, leading=14)

        story = [Paragraph(title, title_style), Spacer(1, 15)]

        for sec in sections:
            h = sec.get("heading")
            if h:
                story.append(Paragraph(h, heading_style))
            t = sec.get("text")
            if t:
                story.append(Paragraph(t, body_style))
            bullets = sec.get("bullets", [])
            if bullets:
                list_items = [ListItem(Paragraph(b, body_style)) for b in bullets]
                story.append(ListFlowable(list_items, bulletType="bullet", leftIndent=15))
            story.append(Spacer(1, 10))

        doc.build(story)

        return {
            "success": True,
            "saved_path": str(out),
            "message": f"PDF report generated at {out}"
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
