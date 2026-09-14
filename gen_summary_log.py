#!/usr/bin/env python3
from __future__ import annotations

import argparse, json
from copy import deepcopy
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from reportlab.lib import colors, pagesizes
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import landscape, portrait
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, Table, TableStyle

try:
    import yaml
except ImportError:
    yaml = None

DEFAULTS = {
    "paper_size": "letter",
    "start_page": 1,
    "page": {
        "orientation": "portrait",
        "margin_left": 0.45, "margin_right": 0.45,
        "margin_top": 0.45, "margin_bottom": 0.45,
        "mirrored_margins": False,
        "margin_inside": 0.55, "margin_outside": 0.35,
    },
    "style": {
        "font": "Helvetica",
        "title_font": "Helvetica-Bold",
        "title_size": 22.0,
        "title_gap": 0.20,
        "table_font_size": 9.0,
        "header_font": "Helvetica-Bold",
        "row_height": 0.25,
        "header_height": 0.25,
        "date_col_width": 1.25,
        "line_width": 0.75,
        "weekly_line_width": 1.5,
        "outer_line_width": 1.0,
        "line_color": "black",
        "cell_left_padding": 4,
        "cell_right_padding": 4,
        "cell_top_padding": 1,
        "cell_bottom_padding": 1,
    },
}

def deep_merge(base, override):
    out = deepcopy(base)
    for k, v in override.items():
        out[k] = deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else deepcopy(v)
    return out

def load_data(path: Path):
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".yaml", ".yml"}:
        if yaml is None:
            raise SystemExit("PyYAML is required.")
        data = yaml.safe_load(text)
    else:
        data = json.loads(text)
    return data or {}

def resolve_page_size(cfg):
    page = cfg["page"]
    name = str(cfg.get("paper_size", "letter")).strip()
    key = name.upper()
    aliases = {"11X17":"ELEVENSEVENTEEN","JUNIORLEGAL":"JUNIOR_LEGAL",
               "HALFLETTER":"HALF_LETTER","GOVLETTER":"GOV_LETTER","GOVLEGAL":"GOV_LEGAL"}
    key = aliases.get(key.replace("-","").replace("_","").replace(" ",""), key)
    size = getattr(pagesizes, key, None)
    if size is None or not isinstance(size, tuple) or len(size) != 2:
        raise SystemExit(f'Unknown paper size "{name}".')
    o = str(page.get("orientation","portrait")).lower()
    if o == "landscape": return landscape(size)
    if o == "portrait": return portrait(size)
    raise SystemExit('orientation must be "portrait" or "landscape".')

def parse_date(v):
    if isinstance(v, datetime): return v.date()
    if isinstance(v, date): return v
    try: return date.fromisoformat(str(v))
    except ValueError: raise SystemExit("start date must be YYYY-MM-DD")

def topics_list(v):
    if v is None: return []
    if isinstance(v, str): return [x.strip() for x in v.split(",") if x.strip()]
    out=[]
    for x in v:
        if isinstance(x,str) and "," in x: out += [y.strip() for y in x.split(",") if y.strip()]
        else:
            s=str(x).strip()
            if s: out.append(s)
    return out

def keywords(v):
    if v is None: return ""
    return ", ".join(map(str,v)) if isinstance(v,(list,tuple)) else str(v)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input", type=Path)
    ap.add_argument("output", type=Path)
    ap.add_argument("--start-date")
    ap.add_argument("--topics", nargs="+")
    ap.add_argument(
        "--start-page", nargs="?", type=int, const=1, default=None, metavar="N",
        help="Add page numbers starting at N; if N is omitted, start at 1.",
    )
    args = ap.parse_args()

    data = load_data(args.input)
    cfg = deep_merge(DEFAULTS, data.get("config", {}))
    page, st = cfg["page"], cfg["style"]
    start_page = args.start_page
    if start_page is not None and start_page < 1:
        raise SystemExit("--start-page must be at least 1.")
    logical_start_page = start_page if start_page is not None else 1

    sv = args.start_date if args.start_date is not None else data.get("start_date")
    if sv is None: raise SystemExit("start_date is required")
    start = parse_date(sv)

    topics = topics_list(args.topics if args.topics is not None else data.get("topics"))
    if not topics: raise SystemExit("topics is required")

    pw, ph = resolve_page_size(cfg)
    top, bottom = float(page["margin_top"])*inch, float(page["margin_bottom"])*inch
    mirrored = bool(page.get("mirrored_margins", False))

    c = canvas.Canvas(str(args.output), pagesize=(pw,ph))
    c.setTitle(str(data.get("document_title","Practice Summary Log")))
    c.setAuthor(str(data.get("author","")))
    c.setSubject(str(data.get("subject","")))
    c.setKeywords(keywords(data.get("keywords")))

    title_style = ParagraphStyle(
        "Title", parent=getSampleStyleSheet()["Normal"],
        fontName=st["title_font"], fontSize=float(st["title_size"]),
        leading=float(st["title_size"])*1.1, alignment=TA_CENTER
    )

    rh = 0.25*inch
    hh = 0.25*inch
    lc = colors.toColor(str(st["line_color"]))

    # Two PDF pages: front and back of one physical sheet.
    # Dates continue from page 1 onto page 2.
    date_offset = 0

    for page_index in range(2):
        page_number = logical_start_page + page_index
        if mirrored:
            inside = float(page["margin_inside"])*inch
            outside = float(page["margin_outside"])*inch
            if page_number % 2 == 1:
                left, right = inside, outside
            else:
                left, right = outside, inside
        else:
            left = float(page["margin_left"])*inch
            right = float(page["margin_right"])*inch

        usable = pw - left - right

        p = Paragraph("Practice Summary Log", title_style)
        _, th = p.wrap(usable, ph)
        ty = ph - top - th
        p.drawOn(c, left, ty)

        table_top = ty - float(st["title_gap"])*inch
        available = table_top - bottom

        nrows = int((available - hh) // rh)
        if nrows < 1:
            raise SystemExit("No room for rows")

        rows = [["Date", *topics]]
        for i in range(nrows):
            d = start + timedelta(days=date_offset + i)
            rows.append([
                d.strftime("%a, %b %d").replace(" 0", " "),
                *([""] * len(topics))
            ])

        date_w = float(st["date_col_width"])*inch
        topic_w = (usable - date_w) / len(topics)
        table = Table(
            rows,
            colWidths=[date_w] + [topic_w] * len(topics),
            rowHeights=[hh] + [rh] * nrows,
            hAlign="LEFT"
        )

        style_commands = [
            ("FONTNAME",(0,0),(-1,-1),st["font"]),
            ("FONTNAME",(0,0),(-1,0),st["header_font"]),
            ("FONTSIZE",(0,0),(-1,-1),float(st["table_font_size"])),
            ("ALIGN",(1,0),(-1,0),"CENTER"),
            ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
            ("LEFTPADDING",(0,0),(-1,-1),float(st["cell_left_padding"])),
            ("RIGHTPADDING",(0,0),(-1,-1),float(st["cell_right_padding"])),
            ("TOPPADDING",(0,0),(-1,-1),float(st["cell_top_padding"])),
            ("BOTTOMPADDING",(0,0),(-1,-1),float(st["cell_bottom_padding"])),
            ("GRID",(0,0),(-1,-1),float(st["line_width"]),lc),
            ("BOX",(0,0),(-1,-1),float(st["outer_line_width"]),lc),
        ]

        weekly_line_width = float(st["weekly_line_width"])
        for local_row in range(1, nrows + 1):
            global_row = date_offset + local_row
            if global_row % 7 == 0:
                style_commands.append(
                    ("LINEBELOW", (0, local_row), (-1, local_row),
                     weekly_line_width, lc)
                )

        table.setStyle(TableStyle(style_commands))
        _table_w, table_h = table.wrapOn(c, usable, available)
        table.drawOn(c, left, table_top - table_h)

        date_offset += nrows

        # Page number, centered in the bottom margin, only when requested.
        if start_page is not None:
            c.saveState()
            c.setFillColor(colors.black)
            c.setFont(st["font"], 9.0)
            c.drawCentredString(pw / 2.0, bottom / 2.0, str(page_number))
            c.restoreState()

        c.showPage()

    c.save()

if __name__ == "__main__":
    main()
