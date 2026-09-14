#!/usr/bin/env python3
"""Generate printable music-practice log sheets as a PDF.

Input: YAML or JSON.  Each unit has a title and a list of exercises.
Pagination rule:
  * keep a complete unit together when it fits on one page;
  * if it won't fit in the remaining space, move it to the next page;
  * split only units that are themselves taller than one usable page.

Usage:
    python gen_log.py practice_logs.yaml practice_logs.pdf
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from reportlab.lib import colors, pagesizes
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import landscape, portrait
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate,
    CondPageBreak,
    Frame,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


DEFAULTS: dict[str, Any] = {
    "paper_size": "letter",
    "start_page": 1,
    "page": {
        "orientation": "portrait",
        "margin_left": 0.45,
        "margin_right": 0.45,
        "margin_top": 0.45,
        "margin_bottom": 0.45,
        "mirrored_margins": False,
        "margin_inside": 0.55,
        "margin_outside": 0.35,
    },
    "style": {
        "font": "Helvetica",
        "title_font": "Helvetica-Bold",
        "title_size": 11.0,
        "document_title_font": "Helvetica-Bold",
        "document_title_size": 16.0,
        "document_title_gap": 0.20,
        "header_font": "Helvetica",
        "header_size": 9.0,
        "header_offset": 0.12,
        "continued_title_font": "Helvetica-Bold",
        "continued_title_size": 9.0,
        "continued_title_gap": 0.08,
        "table_font_size": 9.0,
        "title_gap": 0.08,
        "unit_gap": 0.16,
        "row_height": 0.31,
        "header_height": 0.29,
        "exercise_col_fraction": 0.34,
        "line_width": 0.75,
        "outer_line_width": 1.0,
        "repeat_line_width": 1.75,
        "cell_left_padding": 5,
        "cell_right_padding": 4,
        "cell_top_padding": 2,
        "cell_bottom_padding": 2,
        "repeat_header_on_split": True,
    },
    "table": {
        "exercise_header": "Exercise",
        "session_headers": [],
        "sessions": 7,
    },
}


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_data(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".yaml", ".yml"}:
        if yaml is None:
            raise SystemExit("PyYAML is required for YAML input. Use JSON or install pyyaml.")
        data = yaml.safe_load(text)
    else:
        data = json.loads(text)
    if not isinstance(data, dict):
        raise SystemExit("Input must contain a top-level object/map.")
    return data


def page_size(cfg: dict[str, Any]):
    page = cfg["page"]

    # Preferred syntax:
    #
    #   config:
    #     paper_size: b5
    #
    # For backward compatibility, config.page.paper_size is also accepted.
    name = str(
        cfg.get("paper_size", page.get("paper_size", "letter"))
    ).strip()
    key = name.upper()
    compact = key.replace("-", "").replace("_", "").replace(" ", "")
    aliases = {
        "11X17": "ELEVENSEVENTEEN",
        "11X17IN": "ELEVENSEVENTEEN",
        "JUNIORLEGAL": "JUNIOR_LEGAL",
        "HALFLETTER": "HALF_LETTER",
        "GOVLETTER": "GOV_LETTER",
        "GOVLEGAL": "GOV_LEGAL",
    }
    key = aliases.get(compact, key)
    size = getattr(pagesizes, key, None)
    if size is None or not isinstance(size, tuple) or len(size) != 2:
        accepted = sorted(
            n.lower() for n in dir(pagesizes)
            if n.isupper() and isinstance(getattr(pagesizes, n), tuple)
            and len(getattr(pagesizes, n)) == 2
        )
        raise SystemExit(
            f'Unknown paper size "{name}". Accepted sizes: ' + ", ".join(accepted)
        )

    orientation = str(page.get("orientation", "portrait")).lower()
    if orientation == "landscape":
        return landscape(size)
    if orientation == "portrait":
        return portrait(size)
    raise SystemExit(
        f'Unknown orientation "{orientation}". Use "portrait" or "landscape".'
    )


def inches(value: Any) -> float:
    return float(value) * inch



class ContinuedTable(Table):
    """A Table that inserts '<unit title> (continued)' before continuation fragments."""

    def __init__(
        self,
        *args,
        continuation_title: str | None = None,
        continuation_style: ParagraphStyle | None = None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self._continuation_title = continuation_title
        self._continuation_style = continuation_style

    def onSplit(self, table, byRow=1):
        # ReportLab creates split fragments using self.__class__, so copy our
        # continuation metadata onto each fragment for splits spanning 3+ pages.
        table._continuation_title = getattr(self, "_continuation_title", None)
        table._continuation_style = getattr(self, "_continuation_style", None)

    def split(self, availWidth, availHeight):
        parts = super().split(availWidth, availHeight)
        if len(parts) <= 1 or not self._continuation_title:
            return parts

        # Put the continuation heading immediately before the second fragment.
        # keepWithNext prevents the heading from being stranded at the bottom
        # of a page without at least part of the continued table following it.
        heading = Paragraph(
            f"{self._continuation_title} (continued)",
            self._continuation_style,
        )
        return [parts[0], heading, *parts[1:]]

def make_table(unit: dict[str, Any], cfg: dict[str, Any], usable_width: float, continuation_style: ParagraphStyle) -> Table:
    st = cfg["style"]
    tc = cfg["table"]

    sessions = int(unit.get("sessions", tc.get("sessions", 7)))
    session_headers = unit.get("session_headers", tc.get("session_headers", [])) or []
    if len(session_headers) < sessions:
        session_headers = list(session_headers) + [""] * (sessions - len(session_headers))
    else:
        session_headers = list(session_headers[:sessions])

    exercise_header = unit.get("exercise_header", tc.get("exercise_header", "Exercise"))

    repeats = int(unit.get("repeats", 1))
    if repeats < 1:
        raise ValueError(
            f'Unit "{unit.get("title", "")}" has repeats={repeats}; repeats must be at least 1.'
        )

    exercises = list(unit.get("exercises", []))
    exercise_rows = []
    for ex in exercises:
        if isinstance(ex, dict):
            name = str(ex.get("name", ""))
        else:
            name = str(ex)
        exercise_rows.append([name] + [""] * sessions)

    data = [[exercise_header, *session_headers]]
    for _ in range(repeats):
        # Copy each row so ReportLab receives independent row objects.
        data.extend([list(row) for row in exercise_rows])

    first_fraction = float(st.get("exercise_col_fraction", 0.34))
    first_width = usable_width * first_fraction
    session_width = (usable_width - first_width) / sessions
    col_widths = [first_width] + [session_width] * sessions

    row_heights = [inches(st["header_height"])] + [inches(st["row_height"])] * (len(data) - 1)

    table = ContinuedTable(
        data,
        continuation_title=str(unit.get("title", "")),
        continuation_style=continuation_style,
        colWidths=col_widths,
        rowHeights=row_heights,
        repeatRows=1 if st.get("repeat_header_on_split", True) else 0,
        splitByRow=1,
        hAlign="LEFT",
    )

    line_width = float(st["line_width"])
    outer_line_width = float(st["outer_line_width"])
    style_commands = [
        ("FONTNAME", (0, 0), (-1, -1), st["font"]),
        ("FONTNAME", (0, 0), (-1, 0), st["title_font"]),
        ("FONTSIZE", (0, 0), (-1, -1), float(st["table_font_size"])),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), float(st["cell_left_padding"])),
        ("RIGHTPADDING", (0, 0), (-1, -1), float(st["cell_right_padding"])),
        ("TOPPADDING", (0, 0), (-1, -1), float(st["cell_top_padding"])),
        ("BOTTOMPADDING", (0, 0), (-1, -1), float(st["cell_bottom_padding"])),
        ("GRID", (0, 0), (-1, -1), line_width, colors.black),
        ("BOX", (0, 0), (-1, -1), outer_line_width, colors.black),
    ]

    # A repeated exercise list is rendered as one continuous table.  Mark the
    # end of each repetition except the last with a heavier horizontal rule.
    if repeats > 1 and exercise_rows:
        repeat_line_width = float(st["repeat_line_width"])
        rows_per_repeat = len(exercise_rows)
        for repetition in range(1, repeats):
            # Row 0 is the table header, so the last row of repetition N is
            # N * rows_per_repeat.
            boundary_row = repetition * rows_per_repeat
            style_commands.append(
                ("LINEBELOW", (0, boundary_row), (-1, boundary_row),
                 repeat_line_width, colors.black)
            )

    table.setStyle(TableStyle(style_commands))
    return table




class MirroredDocTemplate(BaseDocTemplate):
    """Choose odd/even page templates from the actual PDF page number."""

    def handle_pageBegin(self):
        # self.page is the number of the page that has just ended.  The base
        # implementation increments it at the start of the new page, so choose
        # the template for self.page + 1 here.
        if hasattr(self, "_mirrored_template_ids"):
            pdf_page_number = self.page + 1
            logical_page_number = (
                getattr(self, "_start_page", 1) + pdf_page_number - 1
            )
            wanted = (
                self._mirrored_template_ids[0]
                if logical_page_number % 2 == 1
                else self._mirrored_template_ids[1]
            )
            for template in self.pageTemplates:
                if template.id == wanted:
                    self.pageTemplate = template
                    break
            else:
                raise ValueError(f"Cannot find page template {wanted!r}")

        super().handle_pageBegin()



def pdf_keywords(value: Any):
    """Normalize YAML/JSON keywords for ReportLab PDF metadata."""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value]
    return str(value)



def build_pdf(data: dict[str, Any], output: Path) -> None:
    cfg = deep_merge(DEFAULTS, data.get("config", {}))
    size = page_size(cfg)
    page = cfg["page"]
    st = cfg["style"]
    start_page = int(cfg.get("start_page", 1))
    if start_page < 1:
        raise SystemExit("start_page must be at least 1.")

    top = inches(page["margin_top"])
    bottom = inches(page["margin_bottom"])
    mirrored = bool(page.get("mirrored_margins", False))

    if mirrored:
        inside = inches(page["margin_inside"])
        outside = inches(page["margin_outside"])
        # Odd/right-hand pages: binding edge is on the left.
        odd_left, odd_right = inside, outside
        # Even/left-hand pages: binding edge is on the right.
        even_left, _even_right = outside, inside
        usable_width = size[0] - inside - outside
        left, right = odd_left, odd_right
    else:
        left = inches(page["margin_left"])
        right = inches(page["margin_right"])
        odd_left, odd_right = left, right
        even_left, _even_right = left, right
        usable_width = size[0] - left - right

    usable_height = size[1] - top - bottom

    doc = MirroredDocTemplate(
        str(output),
        pagesize=size,
        leftMargin=left,
        rightMargin=right,
        topMargin=top,
        bottomMargin=bottom,
        title=str(data.get("document_title", "Practice Logs")),
        author=str(data.get("author", "")),
        subject=str(data.get("subject", "")),
        keywords=pdf_keywords(data.get("keywords")),
    )
    doc._start_page = start_page

    odd_frame = Frame(
        odd_left, bottom, usable_width, usable_height,
        id="odd",
        leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0,
    )
    even_frame = Frame(
        even_left, bottom, usable_width, usable_height,
        id="even",
        leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0,
    )

    document_title = str(data.get("document_title", "Practice Logs"))

    def draw_page_header(canvas, doc_obj):
        pdf_page_number = canvas.getPageNumber()
        logical_page_number = start_page + pdf_page_number - 1

        canvas.saveState()

        # Page 1 gets the large document title as part of the story.
        # On later PDF pages, repeat the document title in the top margin.
        if pdf_page_number > 1:
            canvas.setFont(st["header_font"], float(st["header_size"]))
            header_y = size[1] - top + inches(st["header_offset"])
            canvas.drawCentredString(size[0] / 2.0, header_y, document_title)

        # Page number, centered in the bottom margin.
        canvas.setFont(st["font"], 9.0)
        canvas.drawCentredString(size[0] / 2.0, bottom / 2.0, str(logical_page_number))

        canvas.restoreState()

    if mirrored:
        # Select the frame from the actual physical page number.  Do not use
        # autoNextPageTemplate here: when a ReportLab Table splits itself
        # across a page boundary, automatic template switching is not reliable
        # enough for mirrored margins.
        doc.addPageTemplates([
            PageTemplate(
                id="odd",
                frames=[odd_frame],
                onPage=draw_page_header,
                pagesize=size,
            ),
            PageTemplate(
                id="even",
                frames=[even_frame],
                onPage=draw_page_header,
                pagesize=size,
            ),
        ])
        doc._mirrored_template_ids = ("odd", "even")
    else:
        doc.addPageTemplates([
            PageTemplate(
                id="practice",
                frames=[odd_frame],
                onPage=draw_page_header,
                pagesize=size,
            )
        ])

    document_title_style = ParagraphStyle(
        "DocumentTitle",
        parent=getSampleStyleSheet()["Normal"],
        fontName=st["document_title_font"],
        fontSize=float(st["document_title_size"]),
        leading=float(st["document_title_size"]) * 1.1,
        alignment=TA_CENTER,
        spaceBefore=0,
        spaceAfter=0,
    )

    continued_title_style = ParagraphStyle(
        "ContinuedUnitTitle",
        parent=getSampleStyleSheet()["Normal"],
        fontName=st["continued_title_font"],
        fontSize=float(st["continued_title_size"]),
        leading=float(st["continued_title_size"]) * 1.1,
        alignment=TA_LEFT,
        spaceBefore=0,
        spaceAfter=inches(st["continued_title_gap"]),
        keepWithNext=1,
    )

    title_style = ParagraphStyle(
        "UnitTitle",
        parent=getSampleStyleSheet()["Normal"],
        fontName=st["title_font"],
        fontSize=float(st["title_size"]),
        leading=float(st["title_size"]) * 1.1,
        alignment=TA_LEFT,
        spaceBefore=0,
        spaceAfter=0,
    )

    story = [
        Paragraph(document_title, document_title_style),
        Spacer(1, inches(st["document_title_gap"])),
    ]

    for i, unit in enumerate(data.get("units", [])):
        title = Paragraph(str(unit.get("title", f"Unit {i + 1}")), title_style)
        table = make_table(unit, cfg, usable_width, continued_title_style)
        block = [title, Spacer(1, inches(st["title_gap"])), table]

        # Measure the complete unit before placing it.  KeepTogether is not used
        # here: with maxHeight set it may unwrap the contents when the remaining
        # frame is short, which lets an otherwise page-sized unit split.
        #
        # CondPageBreak gives us the exact rule we want:
        #   * if this unit can fit on a fresh page, require that much remaining
        #     space before starting it;
        #   * if the unit is taller than a whole page, do not force a break, so
        #     the Table can split naturally by rows.
        _title_w, title_h = title.wrap(usable_width, usable_height)
        _table_w, table_h = table.wrap(usable_width, usable_height)
        unit_height = title_h + inches(st["title_gap"]) + table_h

        if unit_height <= usable_height:
            # The whole unit fits on one fresh page, so require enough room for
            # the complete title + table before starting it.
            required_start_height = unit_height
        else:
            # The unit must span pages. Do not start it near the bottom of a
            # page unless there is room for the title, table header, and at
            # least eight exercise rows. If the complete table has fewer than
            # eight exercise rows, require the whole table instead.
            minimum_start_rows = 8
            table_start_height = min(
                table_h,
                inches(st["header_height"])
                + minimum_start_rows * inches(st["row_height"]),
            )
            required_start_height = (
                title_h + inches(st["title_gap"]) + table_start_height
            )

        story.append(CondPageBreak(required_start_height))
        story.extend(block)
        if i != len(data.get("units", [])) - 1:
            story.append(Spacer(1, inches(st["unit_gap"])))

    doc.build(story)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input", type=Path, help="YAML or JSON definition")
    ap.add_argument("output", type=Path, help="Output PDF")
    args = ap.parse_args()
    data = load_data(args.input)
    build_pdf(data, args.output)


if __name__ == "__main__":
    main()
