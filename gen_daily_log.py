#!/usr/bin/env python3
"""Generate a printable daily music-practice log page as a PDF."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from reportlab.lib import colors, pagesizes
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import landscape, portrait
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

try:
    import yaml
except ImportError:
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
        "title_size": 22.0,
        "title_gap": 0.20,
        "line_height": 0.31,
        "line_width": 0.75,
        "line_color": "black",
        "box_width": 1.00,
        "box_line_width": 1.25,
        "box_color": "black",
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
            raise SystemExit("PyYAML is required for YAML input.")
        data = yaml.safe_load(text)
    else:
        data = json.loads(text)
    if not isinstance(data, dict):
        raise SystemExit("Input must contain a top-level object/map.")
    return data


def resolve_page_size(cfg: dict[str, Any]):
    page = cfg["page"]
    name = str(cfg.get("paper_size", page.get("paper_size", "letter"))).strip()
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
        raise SystemExit(f'Unknown paper size "{name}".')
    orientation = str(page.get("orientation", "portrait")).lower()
    if orientation == "landscape":
        return landscape(size)
    if orientation == "portrait":
        return portrait(size)
    raise SystemExit('orientation must be "portrait" or "landscape".')



def parse_color(value: Any):
    """Parse a ReportLab/CSS color name or a hex color such as #808080."""
    try:
        return colors.toColor(str(value))
    except Exception as exc:
        raise SystemExit(f'Invalid color "{value}".') from exc



def normalize_keywords(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return ", ".join(str(x) for x in value)
    return str(value)


def draw_daily_page(data: dict[str, Any], output: Path, start_page: int | None = None) -> None:
    cfg = deep_merge(DEFAULTS, data.get("config", {}))
    page = cfg["page"]
    style = cfg["style"]
    if start_page is not None and start_page < 1:
        raise SystemExit("--start-page must be at least 1.")
    logical_start_page = start_page if start_page is not None else 1
    page_width, page_height = resolve_page_size(cfg)

    top = float(page["margin_top"]) * inch
    bottom = float(page["margin_bottom"]) * inch
    mirrored = bool(page.get("mirrored_margins", False))

    c = canvas.Canvas(str(output), pagesize=(page_width, page_height))
    document_title = str(data.get("document_title", data.get("title", "Daily Practice Log")))
    c.setTitle(document_title)
    c.setAuthor(str(data.get("author", "")))
    c.setSubject(str(data.get("subject", "")))
    c.setKeywords(normalize_keywords(data.get("keywords")))

    title = str(data.get("title", document_title))
    title_style = ParagraphStyle(
        "DailyTitle",
        parent=getSampleStyleSheet()["Normal"],
        fontName=style["title_font"],
        fontSize=float(style["title_size"]),
        leading=float(style["title_size"]) * 1.1,
        alignment=TA_CENTER,
        spaceBefore=0,
        spaceAfter=0,
    )

    line_height = float(style["line_height"]) * inch
    line_width = float(style["line_width"])
    line_color = parse_color(style["line_color"])
    box_width = float(style["box_width"]) * inch
    box_line_width = float(style["box_line_width"])
    box_color = parse_color(style["box_color"])

    if line_height <= 0:
        raise SystemExit("line_height must be greater than zero.")

    # Generate two physical pages: front and back of one sheet.  Mirrored
    # margins follow the logical page numbers, so a document starting on an
    # even page gets the correct binding edge.
    for page_index in range(2):
        page_number = logical_start_page + page_index
        if mirrored:
            inside = float(page["margin_inside"]) * inch
            outside = float(page["margin_outside"]) * inch
            if page_number % 2 == 1:
                # Odd/right-hand page: binding edge is on the left.
                left, right = inside, outside
            else:
                # Even/left-hand page: binding edge is on the right.
                left, right = outside, inside
        else:
            left = float(page["margin_left"]) * inch
            right = float(page["margin_right"]) * inch

        usable_width = page_width - left - right

        p = Paragraph(title, title_style)
        _, title_h = p.wrap(usable_width, page_height)
        title_y = page_height - top - title_h
        p.drawOn(c, left, title_y)

        content_top = title_y - float(style["title_gap"]) * inch
        available_height = content_top - bottom
        part_height = available_height / 3.0

        for i in range(3):
            part_top = content_top - i * part_height
            part_bottom = content_top - (i + 1) * part_height

            box_bottom = part_top - line_height
            # Put the box on the outside edge of the bound page.
            if mirrored and page_number % 2 == 0:
                box_left = left
            else:
                box_left = page_width - right - box_width
            c.setStrokeColor(box_color)
            c.setLineWidth(box_line_width)
            c.rect(box_left, box_bottom, box_width, line_height, stroke=1, fill=0)

            # Calculate the ruled-line positions first so the final line in each
            # section can be drawn 1.5 times heavier than the normal ruled lines.
            line_positions = []
            y = box_bottom
            while y >= part_bottom - 0.01:
                line_positions.append(y)
                y -= line_height

            c.setStrokeColor(line_color)
            for line_index, y in enumerate(line_positions):
                if line_index == len(line_positions) - 1:
                    c.setLineWidth(line_width * 1.5)
                else:
                    c.setLineWidth(line_width)
                c.line(left, y, page_width - right, y)

        # Page number, centered in the bottom margin, only when requested.
        if start_page is not None:
            c.saveState()
            c.setFillColor(colors.black)
            c.setFont(style["font"], 9.0)
            c.drawCentredString(page_width / 2.0, bottom / 2.0, str(page_number))
            c.restoreState()

        c.showPage()

    c.save()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input", type=Path, help="YAML or JSON definition")
    ap.add_argument("output", type=Path, help="Output PDF")
    ap.add_argument(
        "--start-page", nargs="?", type=int, const=1, default=None, metavar="N",
        help="Add page numbers starting at N; if N is omitted, start at 1.",
    )
    args = ap.parse_args()
    draw_daily_page(load_data(args.input), args.output, args.start_page)


if __name__ == "__main__":
    main()
