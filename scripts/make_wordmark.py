#!/usr/bin/env python3
"""Render a word as a 3D-extruded ASCII slab inside a terminal window.

The slab wipes in left to right, then rocks on its vertical axis as a SMIL flipbook:
every frame is pre-rendered text, and a discrete opacity animation cycles through them.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from terminal_svg import CHAR_ASPECT, FONT_SIZE, LINE_HEIGHT, PAD, TerminalFrame, escape

WORDS = ("SAWYER", "MCKENNEY")
WORD_GAP_ROWS = 1
FONT_PATH, FONT_INDEX = "/System/Library/Fonts/Supplemental/Futura.ttc", 4   # Futura Condensed ExtraBold
COLS = 110
MASK_HEIGHT = 110           # letter height in mask pixels; more = smoother, slower
TRACKING = 0.14             # extra letter spacing as a fraction of letter height
DEPTH_FRAC = 0.22           # extrusion depth as a fraction of letter height
FRONT_BIAS = -0.6           # front cap sits proud of the walls so it wins z-buffer ties
CAM_DIST = 6.0              # in units of letter height; larger = flatter projection
TILT_DEG = 4.0
SWING_DEG = 11.0
FRAMES = 24
ROCK_S = 5.0
WIPE_S = 1.6
LIGHT = (-0.15, -0.45, -1.0)
RAMP = " .`:-=+*csS#%@"
FOG = 0.35
FG = "#C9D1D9"
TITLE = "sawyer@github: ~$ ./wordmark.sh --3d"
TAG_FONT_SIZE = 11
TAG_LINE_HEIGHT = 16
TAG_TYPE_S = 0.9
TAG_GAP_S = 0.25
PROMPT, PROMPT_FG, TAG_FG, ACCENT = "$ ", "#7EE787", "#C9D1D9", "#58A6FF"
TAGLINES = (
    ("cmd", "whoami"),
    ("out", "Sawyer McKenney  ·  Software Engineer"),
    ("cmd", "cat focus.txt"),
    ("out", "Full-stack  ·  Native iOS  ·  Cloud Infrastructure  ·  Applied ML"),
    ("cmd", "echo $LOCATION"),
    ("out", "Boulder, CO"),
    ("cmd", "./deploy.sh 2> /dev/null"),
    ("out", "✓ deployed  ·  errors redirected, as is tradition"),
)


def text_mask(text: str) -> np.ndarray:
    """Draw text with tracking and threshold it to a boolean mask."""
    font = ImageFont.truetype(FONT_PATH, MASK_HEIGHT, index=FONT_INDEX)
    gap = int(MASK_HEIGHT * TRACKING)
    widths = [font.getbbox(ch)[2] for ch in text]
    canvas_w = sum(widths) + gap * (len(text) - 1) + MASK_HEIGHT
    img = Image.new("L", (canvas_w, int(MASK_HEIGHT * 1.6)), 0)
    draw = ImageDraw.Draw(img)
    x = MASK_HEIGHT // 2
    for ch, w in zip(text, widths):
        draw.text((x, MASK_HEIGHT * 0.2), ch, fill=255, font=font)
        x += w + gap
    mask = np.array(img) > 128
    ys, xs = np.nonzero(mask)
    return mask[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


def build_shell(mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Surface point cloud (N,3) with outward normals (N,3): caps plus extruded side walls."""
    h, w = mask.shape
    depth = max(2, int(h * DEPTH_FRAC))
    ys, xs = np.nonzero(mask)
    front = np.column_stack([xs, ys, np.full(xs.shape, FRONT_BIAS)])
    back = np.column_stack([xs, ys, np.full(xs.shape, float(depth))])
    normals = [np.tile([0.0, 0.0, -1.0], (len(xs), 1)), np.tile([0.0, 0.0, 1.0], (len(xs), 1))]
    points = [front, back]

    padded = np.pad(mask, 1)
    empty_left = mask & ~padded[1:-1, :-2]
    empty_right = mask & ~padded[1:-1, 2:]
    empty_up = mask & ~padded[:-2, 1:-1]
    empty_down = mask & ~padded[2:, 1:-1]
    nx = empty_right.astype(float) - empty_left.astype(float)
    ny = empty_down.astype(float) - empty_up.astype(float)
    boundary = (nx != 0) | (ny != 0)
    by, bx = np.nonzero(boundary)
    n = np.column_stack([nx[by, bx], ny[by, bx], np.zeros(len(bx))])
    n /= np.linalg.norm(n, axis=1, keepdims=True)
    for z in range(depth):
        points.append(np.column_stack([bx, by, np.full(bx.shape, float(z))]))
        normals.append(n)
    return np.vstack(points).astype(float), np.vstack(normals)


def project(points: np.ndarray, normals: np.ndarray, yaw_deg: float, size: tuple[int, int]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Rotate, cull back faces, perspective-project. Returns (xy, depth, brightness) for visible points."""
    h, w = size
    depth = max(2, int(h * DEPTH_FRAC))
    p = points - np.array([w / 2, h / 2, depth / 2])
    p /= h                                  # letter height = 1 unit
    yaw, tilt = math.radians(yaw_deg), math.radians(TILT_DEG)
    ry = np.array([[math.cos(yaw), 0, math.sin(yaw)], [0, 1, 0], [-math.sin(yaw), 0, math.cos(yaw)]])
    rx = np.array([[1, 0, 0], [0, math.cos(tilt), -math.sin(tilt)], [0, math.sin(tilt), math.cos(tilt)]])
    rot = rx @ ry
    p = p @ rot.T
    n = normals @ rot.T
    cam = np.array([0.0, 0.0, -CAM_DIST])
    visible = np.einsum("ij,ij->i", n, cam - p) > 0
    p, n = p[visible], n[visible]
    f = CAM_DIST / (CAM_DIST + p[:, 2])
    xy = p[:, :2] * f[:, None]
    light = np.array(LIGHT) / np.linalg.norm(LIGHT)
    lambert = np.clip(n @ light, 0, 1)     # LIGHT points from the surface toward the lamp
    z_norm = (p[:, 2] + 0.5) / 1.0
    brightness = (0.18 + 0.82 * lambert) * (1 - FOG * np.clip(z_norm, 0, 1))
    return xy, p[:, 2], brightness


Projected = tuple[np.ndarray, np.ndarray, np.ndarray]


def rasterize(word_frames: list[list[Projected]]) -> list[list[str]]:
    """word_frames[w][f] -> projected word w at frame f. One shared scale so letter heights match;
    each word is fitted to its own union bbox, centred horizontally, and the words are stacked."""
    spans = [np.vstack([f[0] for f in frames]) for frames in word_frames]
    los = [xy.min(axis=0) for xy in spans]
    his = [xy.max(axis=0) for xy in spans]
    widest = max(hi[0] - lo[0] for lo, hi in zip(los, his))
    scale = (COLS - 1) / widest
    word_rows = [int(math.ceil((hi[1] - lo[1]) * scale * CHAR_ASPECT)) + 1 for lo, hi in zip(los, his)]
    word_cols = [int(round((hi[0] - lo[0]) * scale)) + 1 for lo, hi in zip(los, his)]
    total_rows = sum(word_rows) + WORD_GAP_ROWS * (len(word_frames) - 1)
    n_frames = len(word_frames[0])
    out = []
    for f in range(n_frames):
        grid = np.zeros((total_rows, COLS), dtype=int)
        row_off = 0
        for w, frames in enumerate(word_frames):
            xy, z, bright = frames[f]
            col_off = (COLS - word_cols[w]) // 2
            col = np.clip(((xy[:, 0] - los[w][0]) * scale).round().astype(int) + col_off, 0, COLS - 1)
            row = np.clip(((xy[:, 1] - los[w][1]) * scale * CHAR_ASPECT).round().astype(int) + row_off, 0, total_rows - 1)
            idx = np.clip((bright * (len(RAMP) - 1)).round().astype(int), 0, len(RAMP) - 1)
            order = np.argsort(-z)                # far -> near, nearest wins
            grid[row[order], col[order]] = idx[order]
            row_off += word_rows[w] + WORD_GAP_ROWS
        out.append(["".join(RAMP[i] for i in line) for line in grid])
    return out


def frame_group(lines: list[str], frame: TerminalFrame, extra: str = "") -> str:
    row_w = frame.text_width
    texts = "".join(
        f'<text xml:space="preserve" x="{PAD}" y="{frame.text_top + (i + 1) * LINE_HEIGHT - 2:.1f}" '
        f'font-size="{FONT_SIZE}" textLength="{row_w:.0f}" lengthAdjust="spacing">{escape(line)}</text>'
        for i, line in enumerate(lines)
    )
    return f'<g fill="{FG}"{extra}>{texts}</g>'


def taglines_svg(top: float, row_w: float) -> str:
    """Prompt lines typed in one after another, starting after the wordmark wipe."""
    parts = []
    t = WIPE_S + 0.3
    for i, (kind, text) in enumerate(TAGLINES):
        y = top + i * TAG_LINE_HEIGHT
        label = PROMPT + text if kind == "cmd" else text
        fill = ACCENT if kind == "cmd" else TAG_FG
        dur = TAG_TYPE_S if kind == "cmd" else TAG_TYPE_S * 0.6
        est_w = min(row_w, len(label) * TAG_FONT_SIZE * 0.6)
        parts.append(
            f'<clipPath id="t{i}"><rect x="{PAD}" y="{y:.1f}" width="0" height="{TAG_LINE_HEIGHT}">'
            f'<animate attributeName="width" from="0" to="{est_w:.0f}" begin="{t:.2f}s" dur="{dur:.2f}s" fill="freeze"/></rect></clipPath>'
            f'<g clip-path="url(#t{i})"><text xml:space="preserve" x="{PAD}" y="{y + TAG_LINE_HEIGHT - 4:.1f}" font-size="{TAG_FONT_SIZE}" fill="{fill}">'
            + (f'<tspan fill="{PROMPT_FG}">{escape(PROMPT)}</tspan>{escape(text)}' if kind == "cmd" else escape(text))
            + '</text></g>'
        )
        t += dur + TAG_GAP_S
    # blinking block cursor on a final prompt line
    y = top + len(TAGLINES) * TAG_LINE_HEIGHT
    parts.append(
        f'<text x="{PAD}" y="{y + TAG_LINE_HEIGHT - 4:.1f}" font-size="{TAG_FONT_SIZE}" fill="{PROMPT_FG}" opacity="0">'
        f'{escape(PROMPT.strip())}<set attributeName="opacity" to="1" begin="{t:.2f}s"/></text>'
        f'<rect x="{PAD + TAG_FONT_SIZE * 1.3:.1f}" y="{y + 2:.1f}" width="{TAG_FONT_SIZE * 0.6:.1f}" height="{TAG_LINE_HEIGHT - 4}" fill="{TAG_FG}" opacity="0">'
        f'<animate attributeName="opacity" values="1;1;0;0" keyTimes="0;0.5;0.5;1" dur="1.1s" begin="{t:.2f}s" repeatCount="indefinite"/></rect>'
    )
    return "\n".join(parts)


def emit(frames: list[list[str]]) -> str:
    tag_rows = math.ceil(((len(TAGLINES) + 1) * TAG_LINE_HEIGHT + LINE_HEIGHT) / LINE_HEIGHT)
    frame = TerminalFrame(cols=COLS, rows=len(frames[0]) + tag_rows, title=TITLE)
    row_w, top = frame.text_width, frame.text_top
    text_h = len(frames[0]) * LINE_HEIGHT
    intro = (
        f'<clipPath id="wipe"><rect x="{PAD}" y="{top:.1f}" height="{text_h}" width="0">'
        f'<animate attributeName="width" from="0" to="{row_w:.0f}" begin="0s" dur="{WIPE_S}s" fill="freeze"/></rect></clipPath>'
        f'<g clip-path="url(#wipe)">{frame_group(frames[0], frame)}<set attributeName="opacity" to="0" begin="{WIPE_S}s"/></g>'
        f'<rect x="{PAD}" y="{top:.1f}" width="{FONT_SIZE * 1.6:.1f}" height="{text_h}" fill="{FG}" opacity="0.16">'
        f'<animate attributeName="x" from="{PAD}" to="{PAD + row_w:.0f}" begin="0s" dur="{WIPE_S}s" fill="freeze"/>'
        f'<set attributeName="opacity" to="0" begin="{WIPE_S}s"/></rect>'
    )
    n = len(frames)
    flipbook = []
    for i, lines in enumerate(frames):
        k0, k1 = i / n, (i + 1) / n
        anim = (
            f'<animate attributeName="opacity" calcMode="discrete" values="0;1;0" keyTimes="0;{k0:.4f};{k1:.4f}" '
            f'dur="{ROCK_S:.2f}s" begin="{WIPE_S}s" repeatCount="indefinite"/>'
        ) if i else (
            f'<animate attributeName="opacity" calcMode="discrete" values="1;0;1" keyTimes="0;{k1:.4f};1" '
            f'dur="{ROCK_S:.2f}s" begin="{WIPE_S}s" repeatCount="indefinite"/>'
        )
        flipbook.append(frame_group(lines, frame, ' opacity="0"').replace("</g>", anim + "</g>"))
    tags = taglines_svg(top + text_h + LINE_HEIGHT, row_w)
    return frame.wrap(intro + "\n" + "\n".join(flipbook) + "\n" + tags, aria=f"{' '.join(WORDS)} 3D ASCII wordmark")


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("assets/wordmark.svg")
    yaws = [SWING_DEG * math.sin(2 * math.pi * i / FRAMES) for i in range(FRAMES)]
    word_frames = []
    for word in WORDS:
        mask = text_mask(word)
        points, normals = build_shell(mask)
        word_frames.append([project(points, normals, yaw, mask.shape) for yaw in yaws])
    frames = rasterize(word_frames)
    while all(not f[-1].strip() for f in frames):
        frames = [f[:-1] for f in frames]
    out.write_text(emit(frames))
    print("\n".join(frames[FRAMES // 4]))
    print(f"\nwrote {out}: {len(frames[0])} rows x {COLS} cols, {FRAMES} frames, {out.stat().st_size // 1024} KB", file=sys.stderr)


if __name__ == "__main__":
    main()
