"""Helper định dạng DOCX (python-docx): tiêu đề, đoạn có `code` / **đậm**, bảng, khối code, hộp lưu ý, mục lục."""
from __future__ import annotations

import re

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

FONT = "Calibri"
MONO = "Consolas"
PRIMARY = RGBColor(0x1D, 0x4E, 0xD8)
DARK = RGBColor(0x0F, 0x17, 0x2A)
MUTED = RGBColor(0x47, 0x55, 0x69)
CODE_FILL = "F1F5F9"
HEAD_FILL = "1E3A8A"
ZEBRA_FILL = "F8FAFC"
BOX = {"info": ("EFF6FF", "2563EB", "ℹ "), "warn": ("FFFBEB", "D97706", "⚠ "), "danger": ("FEF2F2", "DC2626", "⛔ "),
       "ok": ("F0FDF4", "16A34A", "✔ ")}
_INLINE = re.compile(r"(\*\*[^*]+\*\*|`[^`]+`|(?<![\w*])\*[^*\s][^*]*\*(?![\w*]))")


def _shade(cell_or_par, fill: str) -> None:
    el = cell_or_par._tc.get_or_add_tcPr() if hasattr(cell_or_par, "_tc") else cell_or_par._p.get_or_add_pPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    el.append(shd)


def _set_font(run, name: str = FONT, size: float | None = None, color: RGBColor | None = None, bold=None) -> None:
    run.font.name = name
    run._element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), name)
    if size:
        run.font.size = Pt(size)
    if color is not None:
        run.font.color.rgb = color
    if bold is not None:
        run.bold = bold


def add_runs(par, text: str, size: float | None = None, color: RGBColor | None = None) -> None:
    """Văn bản có **đậm** và `code` inline."""
    for part in _INLINE.split(text):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**"):
            _set_font(par.add_run(part[2:-2].replace("`", "")), size=size, color=color, bold=True)
        elif part.startswith("`") and part.endswith("`") and len(part) > 1:
            r = par.add_run(part[1:-1])
            _set_font(r, MONO, (size or 10.5) - 1, RGBColor(0xB4, 0x23, 0x18))
        elif part.startswith("*") and part.endswith("*") and len(part) > 2:
            r = par.add_run(part[1:-1])
            _set_font(r, size=size, color=color)
            r.italic = True
        else:
            _set_font(par.add_run(part), size=size, color=color)


class Doc:
    def __init__(self) -> None:
        self.d = Document()
        sec = self.d.sections[0]
        sec.page_height, sec.page_width = Cm(29.7), Cm(21.0)
        sec.left_margin = sec.right_margin = Cm(2.0)
        sec.top_margin, sec.bottom_margin = Cm(2.0), Cm(1.8)
        normal = self.d.styles["Normal"]
        normal.font.name, normal.font.size = FONT, Pt(10.5)
        normal.element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), FONT)
        normal.paragraph_format.space_after = Pt(4)
        normal.paragraph_format.line_spacing = 1.15
        for lvl, size in ((1, 16), (2, 13), (3, 11.5)):
            st = self.d.styles[f"Heading {lvl}"]
            st.font.name, st.font.size, st.font.bold = FONT, Pt(size), True
            st.font.color.rgb = PRIMARY if lvl < 3 else DARK
            st.element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), FONT)
            st.paragraph_format.space_before = Pt(14 if lvl == 1 else 10)
            st.paragraph_format.space_after = Pt(4)
            st.paragraph_format.keep_with_next = True

    # ── khối cơ bản ──
    def h(self, text: str, level: int = 1) -> None:
        if level == 1 and len(self.d.paragraphs) > 3:
            self.page_break()
        self.d.add_heading(text.replace("`", ""), level)

    def p(self, text: str, italic=False, color: RGBColor | None = None, align=None, size: float | None = None):
        par = self.d.add_paragraph()
        add_runs(par, text, size=size, color=color)
        if italic:
            for r in par.runs:
                r.italic = True
        if align:
            par.alignment = align
        return par

    def bullets(self, items: list[str], numbered=False) -> None:
        style = "List Number" if numbered else "List Bullet"
        for it in items:
            par = self.d.add_paragraph(style=style)
            add_runs(par, it)
            par.paragraph_format.space_after = Pt(2)

    def code(self, text: str, title: str | None = None) -> None:
        if title:
            cap = self.d.add_paragraph()
            _set_font(cap.add_run(title), size=9, color=MUTED, bold=True)
            cap.paragraph_format.space_after = Pt(0)
            cap.paragraph_format.keep_with_next = True
        t = self.d.add_table(rows=1, cols=1)
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        cell = t.rows[0].cells[0]
        _shade(cell, CODE_FILL)
        cell.paragraphs[0].text = ""
        lines = text.strip("\n").split("\n")
        par = cell.paragraphs[0]
        for i, line in enumerate(lines):
            r = par.add_run(line)
            _set_font(r, MONO, 8.5, DARK)
            if i < len(lines) - 1:
                r.add_break(WD_BREAK.LINE)
        par.paragraph_format.space_after = Pt(0)
        self.d.add_paragraph().paragraph_format.space_after = Pt(2)

    def box(self, text: str, kind: str = "info", title: str | None = None) -> None:
        fill, border, icon = BOX[kind]
        t = self.d.add_table(rows=1, cols=1)
        cell = t.rows[0].cells[0]
        _shade(cell, fill)
        borders = OxmlElement("w:tcBorders")
        left = OxmlElement("w:left")
        for k, v in (("w:val", "single"), ("w:sz", "24"), ("w:color", border)):
            left.set(qn(k), v)
        borders.append(left)
        cell._tc.get_or_add_tcPr().append(borders)
        par = cell.paragraphs[0]
        if title:
            _set_font(par.add_run(icon + title + "  "), bold=True, color=RGBColor.from_string(border))
        add_runs(par, text)
        self.d.add_paragraph().paragraph_format.space_after = Pt(2)

    def table(self, header: list[str], rows: list[list[str]], widths: list[float] | None = None, size: float = 9.5) -> None:
        t = self.d.add_table(rows=1, cols=len(header))
        t.style = "Table Grid"
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        for i, text in enumerate(header):
            cell = t.rows[0].cells[i]
            _shade(cell, HEAD_FILL)
            cell.paragraphs[0].text = ""
            _set_font(cell.paragraphs[0].add_run(text), size=size, color=RGBColor(0xFF, 0xFF, 0xFF), bold=True)
        # Lặp lại hàng tiêu đề khi bảng sang trang
        trpr = t.rows[0]._tr.get_or_add_trPr()
        th = OxmlElement("w:tblHeader")
        th.set(qn("w:val"), "true")
        trpr.append(th)
        for ri, row in enumerate(rows):
            cells = t.add_row().cells
            for i, text in enumerate(row):
                cells[i].paragraphs[0].text = ""
                lines = str(text).split("\n")
                for li, line in enumerate(lines):
                    par = cells[i].paragraphs[0] if li == 0 else cells[i].add_paragraph()
                    add_runs(par, line, size=size)
                    par.paragraph_format.space_after = Pt(0)
                if ri % 2 == 1:
                    _shade(cells[i], ZEBRA_FILL)
        if widths:
            for row in t.rows:
                for i, w in enumerate(widths):
                    row.cells[i].width = Cm(w)
        self.d.add_paragraph().paragraph_format.space_after = Pt(2)

    def checklist(self, items: list[tuple[str, str, str]]) -> None:
        """(mã, nội dung, mức) – mức: Bắt buộc / Khuyến nghị."""
        self.table(["☐", "Mã", "Yêu cầu", "Mức"], [["☐", c, t, lv] for c, t, lv in items], [1.0, 1.6, 12.2, 2.2], 9)

    def page_break(self) -> None:
        self.d.add_paragraph().add_run().add_break(WD_BREAK.PAGE)

    def toc(self) -> None:
        """Trường mục lục – Word cập nhật khi mở (References → Update Table / F9)."""
        par = self.d.add_paragraph()
        r = par.add_run()
        for tag, text in (("begin", None), (None, 'TOC \\o "1-2" \\h \\z \\u'), ("separate", None)):
            if tag:
                el = OxmlElement("w:fldChar")
                el.set(qn("w:fldCharType"), tag)
            else:
                el = OxmlElement("w:instrText")
                el.set(qn("xml:space"), "preserve")
                el.text = text
            r._r.append(el)
        hint = par.add_run("Nhấn chuột phải → Update Field (hoặc F9) để hiển thị mục lục.")
        _set_font(hint, color=MUTED, size=9)
        end = OxmlElement("w:fldChar")
        end.set(qn("w:fldCharType"), "end")
        par.add_run()._r.append(end)
        # Yêu cầu Word tự cập nhật trường khi mở file
        settings = self.d.settings.element
        upd = OxmlElement("w:updateFields")
        upd.set(qn("w:val"), "true")
        settings.append(upd)

    def footer(self, text: str) -> None:
        for sec in self.d.sections:
            par = sec.footer.paragraphs[0]
            par.alignment = WD_ALIGN_PARAGRAPH.CENTER
            _set_font(par.add_run(text + "  ·  Trang "), size=8, color=MUTED)
            r = par.add_run()
            for tag, txt in (("begin", None), (None, "PAGE"), ("end", None)):
                if tag:
                    el = OxmlElement("w:fldChar")
                    el.set(qn("w:fldCharType"), tag)
                else:
                    el = OxmlElement("w:instrText")
                    el.text = txt
                r._r.append(el)
            _set_font(r, size=8, color=MUTED)

    def cover(self, title: str, subtitle: str, meta: list[tuple[str, str]]) -> None:
        for _ in range(5):
            self.d.add_paragraph()
        par = self.d.add_paragraph()
        _set_font(par.add_run(title), size=24, color=PRIMARY, bold=True)
        par = self.d.add_paragraph()
        _set_font(par.add_run(subtitle), size=13, color=MUTED)
        self.d.add_paragraph()
        self.table(["Thông tin", "Giá trị"], [[k, v] for k, v in meta], [4.5, 12.5], 10)
        self.page_break()

    def save(self, path: str) -> None:
        self.d.save(path)

