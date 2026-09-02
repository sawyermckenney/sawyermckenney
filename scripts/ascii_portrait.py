#!/usr/bin/env python3
"""Convert a headshot into an animated ASCII-art SVG (portrait left, figlet name right) that generates row by row."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

COLS = 80
CHAR_ASPECT = 0.5          # width / height of one monospace cell
RAMP = " .,-:;=+*#%@"      # light pixel -> dense glyph (bright-on-dark), background -> space
BG_TOLERANCE = 28          # flood-fill tolerance for the studio backdrop
GAMMA = 1.35               # >1 pushes midtones darker so skin detail survives
FONT_SIZE = 9
LINE_HEIGHT = 9
CHAR_WIDTH = FONT_SIZE * 0.6
PAD = 16
BG, FG_DIM, FG, FG_BRIGHT = "#0D1117", "#6E7681", "#C9D1D9", "#F0F6FC"
ROW_STAGGER_S = 0.06
NAME_WORDS = ("Sawyer", "McKenney")
NAME_FONT_SIZE = 12
NAME_LINE_HEIGHT = 12
NAME_GAP = 28              # px between portrait and name block
NAME_STAGGER_S = 0.12
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


def figlet_lines(words: tuple[str, ...]) -> list[str]:
    """Render each word with figlet slant; stacked words, blank line between."""
    blocks = []
    for word in words:
        try:
            out = subprocess.run(["figlet", "-f", "slant", word], capture_output=True, text=True, check=True).stdout
        except (OSError, subprocess.CalledProcessError) as err:
            raise SystemExit(f"figlet is required to render the name banner: {err}") from err
        blocks.append([line.rstrip() for line in out.rstrip("\n").splitlines()])
    merged: list[str] = []
    for i, block in enumerate(blocks):
        merged = [*merged, *([""] if i else []), *block]
    return merged


def escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def shade_class(row: str) -> str:
    """Rows dense in dark glyphs get the bright fill so hair and features pop."""
    dense = sum(ch in "@%#*" for ch in row)
    return "b" if dense > COLS * 0.18 else "n"


def render_svg(rows: list[str], name_lines: list[str]) -> str:
    portrait_w = COLS * CHAR_WIDTH
    portrait_h = len(rows) * LINE_HEIGHT
    name_w = max(len(line) for line in name_lines) * NAME_FONT_SIZE * 0.6
    name_h = len(name_lines) * NAME_LINE_HEIGHT
    width = round(PAD + portrait_w + NAME_GAP + name_w + PAD)
    height = round(max(portrait_h, name_h) + PAD * 2)
    fade_total = len(rows) * ROW_STAGGER_S + FADE_S
    name_start = fade_total + 0.2
    name_total = name_start + len(name_lines) * NAME_STAGGER_S + FADE_S
    hold_end = name_total + 6
    fade_out_end = hold_end + 1.5
    pct = lambda t: f"{t / CYCLE_S * 100:.2f}%"
    portrait_lines = "\n".join(
        f'<text x="{PAD}" y="{PAD + (i + 1) * LINE_HEIGHT - 2}" class="r {shade_class(row)}" '
        f'style="animation-delay:{i * ROW_STAGGER_S:.2f}s" xml:space="preserve">{escape(row)}</text>'
        for i, row in enumerate(rows)
    )
    name_x = PAD + portrait_w + NAME_GAP
    name_y0 = PAD + (portrait_h - name_h) / 2
    name_svg = "\n".join(
        f'<text x="{name_x:.1f}" y="{name_y0 + (i + 1) * NAME_LINE_HEIGHT - 2:.1f}" class="nm" '
        f'style="animation-delay:{name_start + i * NAME_STAGGER_S:.2f}s" xml:space="preserve">{escape(line)}</text>'
        for i, line in enumerate(name_lines)
    )
    mono = 'ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace'
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="ASCII portrait of Sawyer McKenney">
<style>
  .r {{ font: {FONT_SIZE}px/1 {mono}; white-space: pre; opacity: 0; animation: gen {CYCLE_S}s linear infinite; }}
  .nm {{ font: 700 {NAME_FONT_SIZE}px/1 {mono}; white-space: pre; --c: {FG_BRIGHT}; fill: {FG_BRIGHT}; opacity: 0; animation: gen {CYCLE_S}s linear infinite; }}
  .n {{ --c: {FG}; fill: {FG}; }}
  .b {{ --c: {FG_BRIGHT}; fill: {FG_BRIGHT}; }}
  .cursor {{ fill: #58A6FF; opacity: 0; animation: scan {CYCLE_S}s linear infinite; }}
  @keyframes gen {{
    0% {{ opacity: 0; fill: #58A6FF; }}
    {pct(FADE_S)} {{ opacity: 1; }}
    {pct(FADE_S + 0.6)} {{ fill: var(--c); }}
    {pct(hold_end)} {{ opacity: 1; }}
    {pct(fade_out_end)} {{ opacity: 0; }}
    100% {{ opacity: 0; }}
  }}
  @keyframes scan {{
    0% {{ transform: translateY(0); opacity: 0.55; }}
    {pct(fade_total)} {{ transform: translateY({portrait_h}px); opacity: 0.55; }}
    {pct(fade_total + 0.3)} {{ opacity: 0; }}
    100% {{ opacity: 0; }}
  }}
</style>
<rect width="100%" height="100%" rx="8" fill="{BG}"/>
<rect class="cursor" x="{PAD}" y="{PAD}" width="{portrait_w:.0f}" height="{LINE_HEIGHT}"/>
{portrait_lines}
{name_svg}
</svg>
"""


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: ascii_portrait.py <photo> <out.svg>")
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    if not src.is_file():
        raise SystemExit(f"photo not found: {src}")
    rows = to_rows(load_gray(src, crop_box=(0.06, 0.03, 0.96, 0.66)))
    out.write_text(render_svg(rows, figlet_lines(NAME_WORDS)))
    print("\n".join(rows))
    print(f"\nwrote {out} ({len(rows)} rows x {COLS} cols)", file=sys.stderr)


if __name__ == "__main__":
    main()
