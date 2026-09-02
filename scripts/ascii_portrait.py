#!/usr/bin/env python3
"""Convert a headshot into an animated ASCII-art SVG that fades in row by row."""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

COLS = 96
CHAR_ASPECT = 0.5          # width / height of one monospace cell
RAMP = " .,-:;=+*#%@"      # light pixel -> dense glyph (bright-on-dark), background -> space
BG_TOLERANCE = 28          # flood-fill tolerance for the studio backdrop
GAMMA = 1.7                # >1 pushes midtones darker so skin detail survives
FONT_SIZE = 9
LINE_HEIGHT = 9
CHAR_WIDTH = FONT_SIZE * 0.6
PAD = 16
BG, FG_DIM, FG, FG_BRIGHT = "#0D1117", "#6E7681", "#C9D1D9", "#F0F6FC"
ROW_STAGGER_S = 0.06
FADE_S = 0.9
CYCLE_S = 14


def remove_backdrop(rgb: Image.Image) -> Image.Image:
    """Flood-fill the uniform studio backdrop from the corners to black so it maps to spaces."""
    work = rgb.copy()
    w, h = work.size
    for corner in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1), (w // 2, 0)):
        ImageDraw.floodfill(work, corner, (0, 0, 0), thresh=BG_TOLERANCE)
    return work


def load_gray(path: Path, crop_box: tuple[float, float, float, float]) -> Image.Image:
    """Load, crop by fractional box (l, t, r, b), knock out the backdrop, return grayscale."""
    img = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    w, h = img.size
    l, t, r, b = crop_box
    small = img.crop((int(w * l), int(h * t), int(w * r), int(h * b)))
    small.thumbnail((600, 600))            # flood fill is O(pixels); work at preview size
    gray = remove_backdrop(small).convert("L")
    gray = ImageOps.autocontrast(gray, cutoff=1, ignore=0)
    return gray.point(lambda v: round(255 * (v / 255) ** GAMMA))


def to_rows(img: Image.Image) -> list[str]:
    w, h = img.size
    rows = max(1, round(COLS * (h / w) * CHAR_ASPECT))
    small = img.resize((COLS, rows), Image.LANCZOS)
    px = small.load()
    scale = (len(RAMP) - 1) / 255
    return ["".join(RAMP[round(px[x, y] * scale)] for x in range(COLS)) for y in range(rows)]


def escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def shade_class(row: str) -> str:
    """Rows dense in dark glyphs get the bright fill so hair and features pop."""
    dense = sum(ch in "@%#*" for ch in row)
    return "b" if dense > COLS * 0.18 else "n"


def render_svg(rows: list[str]) -> str:
    width = round(COLS * CHAR_WIDTH + PAD * 2)
    height = round(len(rows) * LINE_HEIGHT + PAD * 2)
    fade_total = len(rows) * ROW_STAGGER_S + FADE_S
    lines = "\n".join(
        f'<text x="{PAD}" y="{PAD + (i + 1) * LINE_HEIGHT - 2}" class="r {shade_class(row)}" '
        f'style="animation-delay:{i * ROW_STAGGER_S:.2f}s" xml:space="preserve">{escape(row)}</text>'
        for i, row in enumerate(rows)
    )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="ASCII portrait of Sawyer McKenney">
<style>
  .r {{ font: {FONT_SIZE}px/1 ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace; letter-spacing: 0; white-space: pre; opacity: 0; animation: gen {CYCLE_S}s linear infinite; }}
  .n {{ --c: {FG}; fill: {FG}; }}
  .b {{ --c: {FG_BRIGHT}; fill: {FG_BRIGHT}; }}
  .cursor {{ fill: #58A6FF; opacity: 0; animation: scan {CYCLE_S}s linear infinite; }}
  @keyframes gen {{
    0% {{ opacity: 0; fill: #58A6FF; }}
    {FADE_S / CYCLE_S * 100:.2f}% {{ opacity: 1; }}
    {(FADE_S + 0.6) / CYCLE_S * 100:.2f}% {{ fill: var(--c); }}
    {(fade_total + 6) / CYCLE_S * 100:.2f}% {{ opacity: 1; }}
    {(fade_total + 7.5) / CYCLE_S * 100:.2f}% {{ opacity: 0; }}
    100% {{ opacity: 0; }}
  }}
  @keyframes scan {{
    0% {{ transform: translateY(0); opacity: 0.55; }}
    {fade_total / CYCLE_S * 100:.2f}% {{ transform: translateY({len(rows) * LINE_HEIGHT}px); opacity: 0.55; }}
    {(fade_total + 0.3) / CYCLE_S * 100:.2f}% {{ opacity: 0; }}
    100% {{ opacity: 0; }}
  }}
</style>
<rect width="100%" height="100%" rx="8" fill="{BG}"/>
<rect class="cursor" x="{PAD}" y="{PAD}" width="{width - PAD * 2}" height="{LINE_HEIGHT}"/>
{lines}
</svg>
"""


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: ascii_portrait.py <photo> <out.svg>")
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    if not src.is_file():
        raise SystemExit(f"photo not found: {src}")
    rows = to_rows(load_gray(src, crop_box=(0.08, 0.02, 0.92, 0.72)))
    out.write_text(render_svg(rows))
    print("\n".join(rows))
    print(f"\nwrote {out} ({len(rows)} rows x {COLS} cols)", file=sys.stderr)


if __name__ == "__main__":
    main()
