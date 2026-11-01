#!/usr/bin/env python3
"""Generate a double-sided sheet of lined paper as a PDF.

The sheet is B5, to match the practice logs and printlog.sh.  Page 1 is the
front and page 2 the back; each has a wider gutter on the binding edge for
punched holes (left on the front, right on the back).  Lines run the full
width between the margins in light gray.

Usage:
    python gen_paper.py 7        # writes pdfs/lined-paper-7mm.pdf
"""

from __future__ import annotations

import argparse
from pathlib import Path

from reportlab.lib.pagesizes import B5
from reportlab.lib.units import inch, mm
from reportlab.pdfgen import canvas

PAGE_SIZE = B5
MARGIN = 0.25 * inch          # top, bottom, and outside edge
GUTTER = 0.5 * inch           # binding edge, leaves room for holes
LINE_GRAY = 0.75              # 0 = black, 1 = white
EDGE_LINE_GRAY = 0.0          # first and last lines
LINE_WIDTH = 0.4              # points


def draw_lines(c: canvas.Canvas, left: float, right: float, spacing: float) -> None:
    width, height = PAGE_SIZE
    usable = height - 2 * MARGIN
    count = int(usable // spacing) + 1
    # Center the block of lines vertically so the top and bottom margins match.
    top = height - MARGIN - (usable - (count - 1) * spacing) / 2

    c.setLineWidth(LINE_WIDTH)
    for i in range(count):
        edge = i in (0, count - 1)
        c.setStrokeGray(EDGE_LINE_GRAY if edge else LINE_GRAY)
        y = top - i * spacing
        c.line(left, y, width - right, y)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spacing", type=float, help="Line spacing in millimeters")
    args = ap.parse_args()
    if args.spacing <= 0:
        raise SystemExit("Line spacing must be greater than 0.")

    label = f"{args.spacing:g}"
    output = Path(__file__).resolve().parent / "pdfs" / f"lined-paper-{label}mm.pdf"
    output.parent.mkdir(exist_ok=True)

    c = canvas.Canvas(str(output), pagesize=PAGE_SIZE)
    c.setTitle(f"Lined Paper ({label} mm)")
    spacing = args.spacing * mm

    # Front: gutter on the left.
    draw_lines(c, GUTTER, MARGIN, spacing)
    c.showPage()
    # Back: gutter on the right, behind the front's gutter.
    draw_lines(c, MARGIN, GUTTER, spacing)
    c.showPage()

    c.save()
    print(output)


if __name__ == "__main__":
    main()
