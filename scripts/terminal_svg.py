"""Shared terminal-window chrome for the profile SVGs."""
from __future__ import annotations

from dataclasses import dataclass

FONT_SIZE = 9
LINE_HEIGHT = 10
CHAR_WIDTH = FONT_SIZE * 0.6
CHAR_ASPECT = CHAR_WIDTH / LINE_HEIGHT
PAD = 16
TITLE_BAR = 30
BG_TOP, BG_BOTTOM, BORDER, MUTED = "#111722", "#0D1117", "#30363D", "#7D8590"
MONO = 'ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace'


def escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


@dataclass(frozen=True)
class TerminalFrame:
    cols: int
    rows: int
    title: str

    @property
    def text_width(self) -> float:
        return self.cols * CHAR_WIDTH

    @property
    def text_top(self) -> float:
        return TITLE_BAR + PAD * 0.5

    @property
    def width(self) -> int:
        return round(self.text_width + PAD * 2)

    @property
    def height(self) -> int:
        return round(self.text_top + self.rows * LINE_HEIGHT + PAD * 0.75)

    def wrap(self, body: str, aria: str) -> str:
        w, h = self.width, self.height
        return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="{escape(aria)}" font-family='{MONO}'>
<defs><linearGradient id="bg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{BG_TOP}"/><stop offset="1" stop-color="{BG_BOTTOM}"/></linearGradient></defs>
<rect width="{w}" height="{h}" rx="10" fill="url(#bg)"/>
<rect x="0.5" y="0.5" width="{w - 1}" height="{h - 1}" rx="10" fill="none" stroke="{BORDER}"/>
<line x1="0" y1="{TITLE_BAR}" x2="{w}" y2="{TITLE_BAR}" stroke="{BORDER}"/>
<circle cx="18" cy="{TITLE_BAR / 2}" r="4.5" fill="#FF5F56"/><circle cx="33" cy="{TITLE_BAR / 2}" r="4.5" fill="#FFBD2E"/><circle cx="48" cy="{TITLE_BAR / 2}" r="4.5" fill="#27C93F"/>
<text x="{w / 2}" y="{TITLE_BAR / 2 + 4}" fill="{MUTED}" font-size="11" text-anchor="middle">{escape(self.title)}</text>
{body}
</svg>
"""
