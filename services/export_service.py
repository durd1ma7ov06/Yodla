import io
import asyncio
from datetime import datetime
from typing import List, Dict, Any
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn

def _set_cell_background(cell, hex_color: str):
    shading = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{hex_color}"/>')
    cell._tc.get_or_add_tcPr().append(shading)

def _set_cell_margins(cell, top=100, bottom=100, left=120, right=120):
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = OxmlElement('w:tcMar')
    for m, val in [('top', top), ('bottom', bottom), ('left', left), ('right', right)]:
        node = OxmlElement(f'w:{m}')
        node.set(qn('w:w'), str(val))
        node.set(qn('w:type'), 'dxa')
        tcMar.append(node)
    tcPr.append(tcMar)

def _set_table_borders(table, color="CBD5E1"):
    tblPr = table._tbl.tblPr
    borders = parse_xml(
        f'<w:tblBorders {nsdecls("w")}>'
        f'<w:top w:val="single" w:sz="4" w:space="0" w:color="{color}"/>'
        f'<w:bottom w:val="single" w:sz="4" w:space="0" w:color="{color}"/>'
        f'<w:insideH w:val="single" w:sz="4" w:space="0" w:color="{color}"/>'
        f'<w:left w:val="none"/>'
        f'<w:right w:val="none"/>'
        f'<w:insideV w:val="single" w:sz="4" w:space="0" w:color="E2E8F0"/>'
        f'</w:tblBorders>'
    )
    tblPr.append(borders)

def _sync_generate_unit_docx(unit_name: str, words: List[Dict[str, Any]]) -> io.BytesIO:
    doc = Document()

    # Configure narrow clean margins
    for section in doc.sections:
        section.top_margin = Inches(0.6)
        section.bottom_margin = Inches(0.6)
        section.left_margin = Inches(0.5)
        section.right_margin = Inches(0.5)

    # Default font
    style = doc.styles['Normal']
    style.font.name = 'Calibri'
    style.font.size = Pt(10.5)

    # Brand Header
    brand_p = doc.add_paragraph()
    brand_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    brand_run = brand_p.add_run("SOZLA AI — SHAXSIY LUG'AT TO'PLAMI")
    brand_run.bold = True
    brand_run.font.size = Pt(11)
    brand_run.font.color.rgb = RGBColor(0x3B, 0x82, 0xF6)

    # Unit Title
    title_p = doc.add_paragraph()
    title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title_run = title_p.add_run(f"📚 {unit_name}")
    title_run.bold = True
    title_run.font.size = Pt(20)
    title_run.font.color.rgb = RGBColor(0x0F, 0x17, 0x2A)

    # Stats Summary
    total = len(words)
    mastered = sum(1 for w in words if w.get("status") == "mastered")
    unknown = sum(1 for w in words if w.get("status") == "unknown")
    date_str = datetime.now().strftime("%d.%m.%Y")

    meta_p = doc.add_paragraph()
    meta_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    meta_run = meta_p.add_run(
        f"Jami: {total} ta so'z   |   🟢 Yodlangan: {mastered}   |   🔴 Qiyin: {unknown}   |   📅 Sana: {date_str}"
    )
    meta_run.font.size = Pt(10)
    meta_run.font.color.rgb = RGBColor(0x64, 0x74, 0x8B)

    doc.add_paragraph()

    # Create Table
    headers = ["№", "Inglizcha so'z", "Transkripsiya", "O'zbekcha ma'nosi", "Misol (Example)", "Holat"]
    table = doc.add_table(rows=1, cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    _set_table_borders(table)

    col_widths = [Inches(0.35), Inches(1.3), Inches(1.1), Inches(1.8), Inches(2.15), Inches(0.8)]

    # Header Row
    hdr_cells = table.rows[0].cells
    for i, h_text in enumerate(headers):
        cell = hdr_cells[i]
        cell.width = col_widths[i]
        _set_cell_background(cell, "1E3A8A")
        _set_cell_margins(cell, top=120, bottom=120, left=100, right=100)
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER if i in (0, 5) else WD_ALIGN_PARAGRAPH.LEFT
        run = p.add_run(h_text)
        run.bold = True
        run.font.size = Pt(10)
        run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)

    # Data Rows
    for idx, w in enumerate(words, 1):
        row_cells = table.add_row().cells
        bg_color = "F8FAFC" if idx % 2 == 0 else "FFFFFF"

        status = w.get("status", "learning")
        status_label = "🟢 Yodlandi" if status == "mastered" else ("🔴 Qiyin" if status == "unknown" else "🟡 Yangi")
        pos = f" ({w['part_of_speech']})" if w.get("part_of_speech") else ""
        word_text = f"{w.get('word', '')}{pos}"
        trans_text = w.get("transcription", "") or "-"
        uz_text = w.get("translation", "")
        
        ex_en = w.get("example_en", "")
        ex_uz = w.get("example_uz", "")
        ex_text = ex_en
        if ex_en and ex_uz:
            ex_text = f"{ex_en}\n({ex_uz})"
        elif not ex_text:
            ex_text = "-"

        values = [str(idx), word_text, trans_text, uz_text, ex_text, status_label]

        for i, val in enumerate(values):
            cell = row_cells[i]
            cell.width = col_widths[i]
            _set_cell_background(cell, bg_color)
            _set_cell_margins(cell, top=90, bottom=90, left=100, right=100)
            p = cell.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER if i in (0, 5) else WD_ALIGN_PARAGRAPH.LEFT
            run = p.add_run(val)
            run.font.size = Pt(9.5)
            if i == 1:
                run.bold = True
                run.font.color.rgb = RGBColor(0x0F, 0x17, 0x2A)
            elif i == 2:
                run.italic = True
                run.font.color.rgb = RGBColor(0x47, 0x55, 0x69)
            elif i == 4:
                run.font.size = Pt(9)
                run.font.color.rgb = RGBColor(0x33, 0x41, 0x55)

    # Footer
    footer_p = doc.add_paragraph()
    footer_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    footer_p.paragraph_format.space_before = Pt(16)
    f_run = footer_p.add_run("🤖 Sozla AI (@yodla_Al_bot) yordamida tayyorlandi • Kunlik lug'at yodlash tizimi")
    f_run.italic = True
    f_run.font.size = Pt(9)
    f_run.font.color.rgb = RGBColor(0x94, 0xA3, 0xB8)

    output = io.BytesIO()
    doc.save(output)
    output.seek(0)
    return output

async def generate_unit_word_doc(unit_name: str, words: List[Dict[str, Any]]) -> io.BytesIO:
    """Asynchronously generate a styled Word (.docx) document for a unit."""
    return await asyncio.to_thread(_sync_generate_unit_docx, unit_name, words)
