#!/usr/bin/env python3
"""Convert a headshot into a terminal-window SVG whose ASCII rows type in left to right.

Animation is pure SMIL (no JavaScript) so it runs inside a README <img>.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

from terminal_svg import CHAR_ASPECT, FONT_SIZE, LINE_HEIGHT, PAD, TerminalFrame, escape

COLS = 80
RAMP = " .,-:;=+*#%@"      # light pixel -> dense glyph (bright-on-dark), backdrop -> space
BG_TOLERANCE = 28          # flood-fill tolerance for the studio backdrop
GAMMA = 1.35               # >1 pushes midtones darker so skin detail survives
CROP_BOX = (0.10, 0.03, 0.92, 0.58)   # fractional (left, top, right, bottom) of the photo
ROW_TYPE_S = 0.10          # seconds to type one row
ROW_GAP_S = 0.0            # extra pause between rows
FG, FG_BRIGHT, CURSOR = "#C9D1D9", "#F0F6FC", "#58A6FF"
TITLE = "sawyer@github: ~$ ./portrait.sh"


def remove_backdrop(rgb: Image.Image) -> Image.Image:
    """Flood-fill the uniform studio backdrop from the corners to black so it maps to spaces."""
    work = rgb.copy()
    w, h = work.size
    for corner in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1), (w // 2, 0)):
        ImageDraw.floodfill(work, corner, (0, 0, 0), thresh=BG_TOLERANCE)
    return work


def load_gray(path: Path) -> Image.Image:
    img = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    w, h = img.size
    l, t, r, b = CROP_BOX
    small = img.crop((int(w * l), int(h * t), int(w * r), int(h * b)))
    small.thumbnail((600, 600))            # flood fill is O(pixels); work at preview size
    gray = ImageOps.autocontrast(remove_backdrop(small).convert("L"), cutoff=1, ignore=0)
    return gray.point(lambda v: round(255 * (v / 255) ** GAMMA))


def to_rows(img: Image.Image) -> list[str]:
    w, h = img.size
    rows = max(1, round(COLS * (h / w) * CHAR_ASPECT))
    px = img.resize((COLS, rows), Image.LANCZOS).load()
    scale = (len(RAMP) - 1) / 255
    return ["".join(RAMP[round(px[x, y] * scale)] for x in range(COLS)) for y in range(rows)]


def row_fill(row: str) -> str:
    """Rows dense in bright glyphs get the brighter fill so highlights pop."""
    return FG_BRIGHT if sum(ch in "#%@" for ch in row) > COLS * 0.18 else FG


def render_svg(rows: list[str]) -> str:
    frame = TerminalFrame(cols=COLS, rows=len(rows), title=TITLE)
    row_w = frame.text_width
    body = []
    for i, row in enumerate(rows):
        begin = i * (ROW_TYPE_S + ROW_GAP_S)
        y_top = frame.text_top + i * LINE_HEIGHT
        body.append(
            f'<clipPath id="r{i}"><rect x="{PAD}" y="{y_top:.1f}" width="0" height="{LINE_HEIGHT}">'
            f'<animate attributeName="width" from="0" to="{row_w:.0f}" begin="{begin:.2f}s" dur="{ROW_TYPE_S}s" fill="freeze"/>'
            f'</rect></clipPath>'
            f'<g clip-path="url(#r{i})"><text xml:space="preserve" x="{PAD}" y="{y_top + LINE_HEIGHT - 2:.1f}" '
            f'fill="{row_fill(row)}" font-size="{FONT_SIZE}" textLength="{row_w:.0f}" lengthAdjust="spacing">{escape(row)}</text></g>'
        )
    total = len(rows) * (ROW_TYPE_S + ROW_GAP_S)
    cursor = (
        f'<rect y="{frame.text_top:.1f}" width="{FONT_SIZE * 0.6:.1f}" height="{LINE_HEIGHT}" fill="{CURSOR}" opacity="0.85">'
        f'<animate attributeName="x" values="{PAD};{PAD + row_w:.0f}" dur="{ROW_TYPE_S + ROW_GAP_S}s" repeatCount="{len(rows)}" fill="freeze"/>'
        f'<animate attributeName="y" calcMode="discrete" values="{";".join(f"{frame.text_top + i * LINE_HEIGHT:.1f}" for i in range(len(rows)))}" '
        f'dur="{total:.2f}s" fill="freeze"/>'
        f'<set attributeName="opacity" to="0" begin="{total:.2f}s"/></rect>'
    )
    return frame.wrap("\n".join(body) + "\n" + cursor, aria="ASCII portrait of Sawyer McKenney")


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: ascii_portrait.py <photo> <out.svg>")
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    if not src.is_file():
        raise SystemExit(f"photo not found: {src}")
    rows = to_rows(load_gray(src))
    out.write_text(render_svg(rows))
    print("\n".join(rows))
    print(f"\nwrote {out} ({len(rows)} rows x {COLS} cols)", file=sys.stderr)


if __name__ == "__main__":
    main()
