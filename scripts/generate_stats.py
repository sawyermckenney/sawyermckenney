#!/usr/bin/env python3
"""Render GitHub stats and top-language SVG cards from the public REST API."""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

USER = os.environ.get("GH_USER", "sawyermckenney")
TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN", "")
OUT_DIR = Path(os.environ.get("OUT_DIR", "dist"))
API = "https://api.github.com"
IGNORED_LANGS = {"handlebars", "html", "css", "powershell", "jupyter notebook", "dockerfile"}
LANG_LIMIT = 8
CARD_BG, BORDER, TITLE, TEXT, MUTED = "#0D1117", "#30363D", "#58A6FF", "#C9D1D9", "#8B949E"
LANG_COLORS = {
    "Python": "#3572A5", "TypeScript": "#3178C6", "JavaScript": "#F1E05A",
    "Swift": "#F05138", "Jupyter Notebook": "#DA5B0B", "Shell": "#89E051",
    "Dart": "#00B4AB", "Svelte": "#FF3E00", "C++": "#F34B7D", "Java": "#B07219",
}


def fetch(path: str) -> Any:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "profile-stats"}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    req = urllib.request.Request(path if path.startswith("http") else f"{API}{path}", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as err:
        raise SystemExit(f"GitHub API error {err.code} for {path}: {err.read().decode()[:200]}") from err


def fetch_all_repos() -> list[dict[str, Any]]:
    repos: list[dict[str, Any]] = []
    page = 1
    while True:
        batch = fetch(f"/users/{USER}/repos?per_page=100&type=owner&page={page}")
        if not batch:
            return repos
        repos = [*repos, *batch]
        page += 1


def collect_stats(repos: list[dict[str, Any]]) -> dict[str, int]:
    own = [r for r in repos if not r["fork"]]
    user = fetch(f"/users/{USER}")
    commits = fetch(f"/search/commits?q=author:{USER}&per_page=1")["total_count"]
    prs = fetch(f"/search/issues?q=author:{USER}+type:pr&per_page=1")["total_count"]
    return {
        "Total commits": commits,
        "Pull requests": prs,
        "Public repos": len(own),
        "Stars earned": sum(r["stargazers_count"] for r in own),
        "Followers": user["followers"],
    }


def collect_languages(repos: list[dict[str, Any]]) -> list[tuple[str, float]]:
    totals: dict[str, int] = {}
    for repo in (r for r in repos if not r["fork"]):
        for lang, size in fetch(repo["languages_url"]).items():
            if lang.lower() not in IGNORED_LANGS:
                totals = {**totals, lang: totals.get(lang, 0) + size}
    grand = sum(totals.values()) or 1
    ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)[:LANG_LIMIT]
    return [(lang, size / grand * 100) for lang, size in ranked]


def card(width: int, height: int, title: str, body: str) -> str:
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{title}">
<style>
  .t{{font:600 18px 'Segoe UI',Ubuntu,'Helvetica Neue',sans-serif;fill:{TITLE}}}
  .l{{font:400 14px 'Segoe UI',Ubuntu,'Helvetica Neue',sans-serif;fill:{TEXT}}}
  .v{{font:700 14px 'Segoe UI',Ubuntu,'Helvetica Neue',sans-serif;fill:{TEXT}}}
  .m{{font:400 12px 'Segoe UI',Ubuntu,'Helvetica Neue',sans-serif;fill:{MUTED}}}
</style>
<rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="6" fill="{CARD_BG}" stroke="{BORDER}"/>
<text x="25" y="35" class="t">{title}</text>
{body}
</svg>
"""


def render_stats(stats: dict[str, int]) -> str:
    rows = "\n".join(
        f'<text x="25" y="{70 + i * 26}" class="l">{label}</text>'
        f'<text x="{470}" y="{70 + i * 26}" class="v" text-anchor="end">{value:,}</text>'
        for i, (label, value) in enumerate(stats.items())
    )
    return card(495, 70 + len(stats) * 26, f"{USER}'s GitHub Stats", rows)


def render_languages(langs: list[tuple[str, float]]) -> str:
    bar_x, bar_w, x = 25, 445, 25.0
    segments = []
    for lang, pct in langs:
        w = bar_w * pct / 100
        segments.append(f'<rect x="{x:.1f}" y="52" width="{w:.1f}" height="10" fill="{LANG_COLORS.get(lang, "#8B949E")}"/>')
        x += w
    rows = []
    for i, (lang, pct) in enumerate(langs):
        col, row = i % 2, i // 2
        rx, ry = bar_x + col * 225, 90 + row * 24
        rows.append(
            f'<circle cx="{rx + 5}" cy="{ry - 5}" r="5" fill="{LANG_COLORS.get(lang, "#8B949E")}"/>'
            f'<text x="{rx + 18}" y="{ry}" class="l">{lang}</text>'
            f'<text x="{rx + 205}" y="{ry}" class="m" text-anchor="end">{pct:.1f}%</text>'
        )
    height = 90 + ((len(langs) + 1) // 2) * 24
    body = f'<clipPath id="bar"><rect x="{bar_x}" y="52" width="{bar_w}" height="10" rx="5"/></clipPath>' \
           f'<g clip-path="url(#bar)">{"".join(segments)}</g>' + "\n".join(rows)
    return card(495, height, "Most Used Languages", body)


def main() -> None:
    repos = fetch_all_repos()
    if not repos:
        raise SystemExit(f"No repositories found for {USER}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "stats.svg").write_text(render_stats(collect_stats(repos)))
    (OUT_DIR / "langs.svg").write_text(render_languages(collect_languages(repos)))
    print(f"wrote {OUT_DIR}/stats.svg and {OUT_DIR}/langs.svg", file=sys.stderr)


if __name__ == "__main__":
    main()
