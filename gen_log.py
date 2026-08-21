#!/usr/bin/env python3
"""Generate printable music-practice log sheets as a PDF.

Input: YAML or JSON.  Each unit has a title and a list of exercises.
Pagination rule:
  * keep a complete unit together when it fits on one page;
  * if it won't fit in the remaining space, move it to the next page;
  * split only units that are themselves taller than one usable page.

Usage:
    python practice_log_generator.py practice_logs.yaml practice_logs.pdf
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    CondPageBreak,
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
    "page": {
        "size": "letter",
        "orientation": "portrait",
        "margin_left": 0.45,
        "margin_right": 0.45,
        "margin_top": 0.45,
        "margin_bottom": 0.45,
    },
    "style": {
        "font": "Helvetica",
        "title_font": "Helvetica-Bold",
        "title_size": 11.0,
        "document_title_font": "Helvetica-Bold",
        "document_title_size": 22.0,
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
    if str(page.get("size", "letter")).lower() != "letter":
        raise SystemExit("This version currently supports US Letter only.")
    size = letter
    if str(page.get("orientation", "portrait")).lower() == "landscape":
        size = landscape(size)
    return size


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


def build_pdf(data: dict[str, Any], output: Path) -> None:
    cfg = deep_merge(DEFAULTS, data.get("config", {}))
    size = page_size(cfg)
    page = cfg["page"]
    st = cfg["style"]

    left = inches(page["margin_left"])
    right = inches(page["margin_right"])
    top = inches(page["margin_top"])
    bottom = inches(page["margin_bottom"])
    usable_width = size[0] - left - right
    usable_height = size[1] - top - bottom

    doc = BaseDocTemplate(
        str(output),
        pagesize=size,
        leftMargin=left,
        rightMargin=right,
        topMargin=top,
        bottomMargin=bottom,
        title=str(data.get("document_title", "Practice Logs")),
        author=str(data.get("author", "")),
    )
    frame = Frame(
        left, bottom, usable_width, usable_height,
        id="main",
        leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0,
    )

    document_title = str(data.get("document_title", "Practice Logs"))

    def draw_page_header(canvas, doc_obj):
        # Page 1 gets the large document title as part of the story.
        # On later pages, repeat the document title in the top margin.
        if canvas.getPageNumber() <= 1:
            return
        canvas.saveState()
        canvas.setFont(st["header_font"], float(st["header_size"]))
        header_y = size[1] - top + inches(st["header_offset"])
        canvas.drawCentredString(size[0] / 2.0, header_y, document_title)
        canvas.restoreState()

    doc.addPageTemplates([
        PageTemplate(id="practice", frames=[frame], onPage=draw_page_header)
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
        title_w, title_h = title.wrap(usable_width, usable_height)
        table_w, table_h = table.wrap(usable_width, usable_height)
        unit_height = title_h + inches(st["title_gap"]) + table_h

        if unit_height <= usable_height:
            story.append(CondPageBreak(unit_height))

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
