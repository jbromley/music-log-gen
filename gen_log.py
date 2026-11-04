#!/usr/bin/env python3
"""Generate printable music-practice log sheets as a PDF.

Input: YAML or JSON.  The "contents" map lists units, each with a title and a
list of exercises.  The whole document is printed as one table: each unit's
title and any "section" labels are merged rows inside it.
Pagination rule: the table splits across pages by rows, but
  * a repeats_each block is never split;
  * a unit title or section row stays on the same page as the exercises
    that follow it.

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
from reportlab.lib.fonts import ps2tt, tt2ps
from reportlab.lib.pagesizes import landscape, portrait
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate,
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
        "document_title_font": "Helvetica-Bold",
        "document_title_size": 12.0,
        "document_title_gap": 0.20,
        "header_font": "Helvetica",
        "header_size": 9.0,
        "header_offset": 0.12,
        "continued_title_font": "Helvetica",
        "continued_title_size": 9.0,
        "continued_title_gap": 0.08,
        "table_font_size": 9.0,
        "row_height": 0.25,
        "exercise_col_fraction": 0.34,
        "line_width": 0.5,
        "outer_line_width": 1.0,
        "repeat_line_width": 1.75,
        "cell_left_padding": 5,
        "cell_right_padding": 4,
        "cell_top_padding": 2,
        "cell_bottom_padding": 2,
    },
    "table": {
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


def positive_int(mapping: dict[str, Any], key: str, default: int, where: str) -> int:
    """Read a count such as repeats_each (or repeats-each) that must be >= 1."""
    value = int(mapping.get(key, mapping.get(key.replace("_", "-"), default)))
    if value < 1:
        raise SystemExit(f"{where} has {key}={value}; {key} must be at least 1.")
    return value


def text_of(value: Any) -> str:
    """Cell text for a YAML value; a missing or null value prints nothing."""
    return "" if value is None else str(value).strip()


def font_variant(font: str, bold: int, italic: int) -> str:
    """Return a face of a font's family, e.g. (Helvetica, 0, 1) -> Helvetica-Oblique."""
    try:
        family, _bold, _italic = ps2tt(font)
        return tt2ps(family, bold, italic)
    except ValueError:
        # Not a registered family; fall back to the font as given.
        return font


def merge_ranges(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Merge overlapping or touching (first, last) row ranges.

    ReportLab's NOSPLIT ranges must not overlap: a later overlapping range
    clobbers an earlier one instead of combining with it.
    """
    merged: list[tuple[int, int]] = []
    for first, last in sorted(ranges):
        if merged and first <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], last))
        else:
            merged.append((first, last))
    return merged


class ContinuedTable(Table):
    """A Table that inserts "(continued)" before each continuation fragment."""

    def __init__(self, *args, continuation_style: ParagraphStyle | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self._continuation_style = continuation_style

    def onSplit(self, table, byRow=1):
        # ReportLab creates split fragments using self.__class__, so copy our
        # continuation style onto each fragment for splits spanning 3+ pages.
        table._continuation_style = getattr(self, "_continuation_style", None)

    def split(self, availWidth, availHeight):
        parts = super().split(availWidth, availHeight)
        if len(parts) <= 1 or self._continuation_style is None:
            return parts

        # Put the continuation heading immediately before the second fragment.
        # keepWithNext prevents the heading from being stranded at the bottom
        # of a page without at least part of the continued table following it.
        heading = Paragraph("(continued)", self._continuation_style)
        return [parts[0], heading, *parts[1:]]


class TableRows:
    """Collects the table's rows and the row indices that need styling."""

    def __init__(self, sessions: int):
        self.sessions = sessions
        self.rows: list[list[str]] = []
        self.headings: list[tuple[int, str]] = []      # (row, font)
        self.groups: list[tuple[int, int, bool]] = []  # (first, last, ruled)
        self.boundaries: list[int] = []                # rows ending a repeat

    def heading(self, text: str, font: str) -> None:
        self.headings.append((len(self.rows), font))
        self.rows.append([text] + [""] * self.sessions)

    def exercise(self, name: str, count: int) -> None:
        # repeats_each lists the exercise that many times in a row; the block
        # gets a slightly heavier rule after it when count > 1.
        first = len(self.rows)
        for _ in range(count):
            self.rows.append([name] + [""] * self.sessions)
        self.groups.append((first, len(self.rows) - 1, count > 1))

    def boundary(self) -> None:
        if self.rows:
            self.boundaries.append(len(self.rows) - 1)

    def keep_together(self) -> list[tuple[int, int]]:
        """Row ranges that must not be split across pages.

        * a repeats_each block stays together;
        * a heading stays with the exercise block that follows it (so a unit
          title followed by a section stays with both).
        """
        ranges = [(first, last) for first, last, ruled in self.groups if ruled]
        for row, _font in self.headings:
            following = [g for g in self.groups if g[0] > row]
            if following:
                ranges.append((row, following[0][1]))
        return merge_ranges(ranges)


def collect_rows(contents: dict[str, Any], sessions: int, unit_font: str, section_font: str) -> TableRows:
    """Lay out the contents as table rows.

        contents:
          repeats: 1          # whole list
          repeats_each: 3     # default for every unit
          units:
            - unit: Day 1     # bold heading row
              repeats: 2      # this unit's exercise list
              repeats_each: 1 # overrides the contents default
              exercises:
                - Lesson
                - section: Toggles   # italic heading row
                - Add 9 toggle
            - section: Bonus         # a section between units
    """
    out = TableRows(sessions)
    repeats = positive_int(contents, "repeats", 1, "contents")
    default_each = positive_int(contents, "repeats_each", 1, "contents")
    units = contents.get("units") or []

    for repetition in range(repeats):
        for unit in units:
            if not isinstance(unit, dict):
                raise SystemExit(f"contents.units entries must be maps, got {unit!r}.")
            if "section" in unit and "unit" not in unit:
                out.heading(text_of(unit["section"]), section_font)
                continue

            title = text_of(unit.get("unit"))
            if title:
                # An untitled unit gets no heading row.
                out.heading(title, unit_font)
            where = f'Unit "{title}"'
            unit_repeats = positive_int(unit, "repeats", 1, where)
            each = positive_int(unit, "repeats_each", default_each, where)

            for pass_number in range(unit_repeats):
                for ex in unit.get("exercises") or []:
                    if isinstance(ex, dict) and "section" in ex:
                        # Sections print once, not repeated by repeats_each.
                        out.heading(text_of(ex["section"]), section_font)
                        continue
                    if isinstance(ex, dict):
                        ex = ex.get("name")
                    out.exercise(text_of(ex), each)
                if pass_number < unit_repeats - 1:
                    out.boundary()

        if repetition < repeats - 1:
            out.boundary()

    return out


def make_table(contents: dict[str, Any], cfg: dict[str, Any], usable_width: float,
               continuation_style: ParagraphStyle) -> Table | None:
    st = cfg["style"]
    sessions = int(contents.get("sessions", cfg["table"].get("sessions", 7)))

    # Heading rows are single merged cells at the table font size: unit
    # titles in bold, sections in italics.
    unit_font = st.get("unit_font") or font_variant(st["font"], 1, 0)
    section_font = st.get("section_font") or font_variant(st["font"], 0, 1)
    layout = collect_rows(contents, sessions, unit_font, section_font)
    if not layout.rows:
        return None
    last_row = len(layout.rows) - 1

    first_width = usable_width * float(st.get("exercise_col_fraction", 0.34))
    session_width = (usable_width - first_width) / sessions
    table = ContinuedTable(
        layout.rows,
        continuation_style=continuation_style,
        colWidths=[first_width] + [session_width] * sessions,
        rowHeights=[inches(st["row_height"])] * len(layout.rows),
        splitByRow=1,
        hAlign="LEFT",
    )

    line_width = float(st["line_width"])
    outer_line_width = float(st["outer_line_width"])
    repeat_line_width = float(st["repeat_line_width"])
    style_commands = [
        ("FONTNAME", (0, 0), (-1, -1), st["font"]),
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

    for row, font in layout.headings:
        style_commands += [
            ("SPAN", (0, row), (-1, row)),
            ("FONTNAME", (0, row), (-1, row), font),
        ]

    # A slightly heavier rule after each repeats_each block, then a heavier
    # one at the end of each repeat, drawn over it.  The table's outer box
    # covers the last row.
    for _first, last, ruled in layout.groups:
        if ruled and last < last_row:
            style_commands.append(
                ("LINEBELOW", (0, last), (-1, last), outer_line_width, colors.black)
            )
    for row in layout.boundaries:
        if row < last_row:
            style_commands.append(
                ("LINEBELOW", (0, row), (-1, row), repeat_line_width, colors.black)
            )

    for first, last in layout.keep_together():
        style_commands.append(("NOSPLIT", (0, first), (-1, last)))

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



def build_pdf(data: dict[str, Any], output: Path, start_page: int | None = None) -> None:
    cfg = deep_merge(DEFAULTS, data.get("config", {}))
    size = page_size(cfg)
    page = cfg["page"]
    st = cfg["style"]
    # Page numbering is enabled only by the --start-page command-line switch.
    # With no explicit value, --start-page starts numbering at 1.
    if start_page is not None and start_page < 1:
        raise SystemExit("--start-page must be at least 1.")
    logical_start_page = start_page if start_page is not None else 1

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
    doc._start_page = logical_start_page

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
        logical_page_number = logical_start_page + pdf_page_number - 1

        canvas.saveState()

        # Page 1 gets the large document title as part of the story.
        # On later PDF pages, repeat the document title in the top margin.
        if pdf_page_number > 1:
            canvas.setFont(st["header_font"], float(st["header_size"]))
            header_y = size[1] - top + inches(st["header_offset"])
            canvas.drawCentredString(size[0] / 2.0, header_y, document_title)

        # Page number, centered in the bottom margin, only when requested.
        if start_page is not None:
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

    story = [
        Paragraph(document_title, document_title_style),
        Spacer(1, inches(st["document_title_gap"])),
    ]

    if "units" in data and "contents" not in data:
        raise SystemExit(
            'The top-level "units" list is no longer supported; put the units '
            'under "contents" (see README.md).'
        )
    # The whole document is one table; it splits across pages by rows.
    table = make_table(data.get("contents") or {}, cfg, usable_width, continued_title_style)
    if table is not None:
        story.append(table)

    doc.build(story)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input", type=Path, help="YAML or JSON definition")
    ap.add_argument("output", type=Path, help="Output PDF")
    ap.add_argument(
        "--start-page",
        nargs="?",
        type=int,
        const=1,
        default=None,
        metavar="N",
        help="Add page numbers starting at N; if N is omitted, start at 1.",
    )
    args = ap.parse_args()
    data = load_data(args.input)
    build_pdf(data, args.output, args.start_page)


if __name__ == "__main__":
    main()
