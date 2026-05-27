#!/usr/bin/env python3
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html import escape
from typing import Dict, Iterable, List

API_BASE = "https://api.github.com"
DEFAULT_USERNAME = "Overwatch886"
DEFAULT_OUTPUT_PATH = "assets/top-langs.svg"
MAX_LANGUAGES_DISPLAYED = 10

PALETTE = [
    "#58A6FF",
    "#F1E05A",
    "#3572A5",
    "#E34C26",
    "#3178C6",
    "#B07219",
    "#C6538C",
    "#A97BFF",
    "#00ADD8",
    "#89E051",
    "#FF6B6B",
]


def api_get(url: str, token: str = ""):
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "top-langs-svg-generator",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = "Bearer " + token

    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        message = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API request failed ({exc.code}) for {url}: {message}") from exc


def list_public_repos(username: str, token: str, include_forks: bool) -> List[dict]:
    repos: List[dict] = []
    page = 1
    while True:
        query = urllib.parse.urlencode(
            {
                "type": "owner",
                "sort": "updated",
                "per_page": 100,
                "page": page,
            }
        )
        url = f"{API_BASE}/users/{username}/repos?{query}"
        page_items = api_get(url, token=token)
        if not page_items:
            break
        repos.extend(page_items)
        page += 1

    if include_forks:
        return repos
    return [repo for repo in repos if not repo.get("fork", False)]


def aggregate_languages(repos: Iterable[dict], token: str) -> Dict[str, int]:
    totals: Dict[str, int] = {}
    for repo in repos:
        languages_url = repo.get("languages_url")
        if not languages_url:
            continue
        lang_bytes = api_get(languages_url, token=token)
        for lang, byte_count in lang_bytes.items():
            totals[lang] = totals.get(lang, 0) + int(byte_count)
    return totals


def as_percentages(lang_totals: Dict[str, int]) -> List[tuple[str, float]]:
    grand_total = sum(lang_totals.values())
    if grand_total <= 0:
        return []

    sorted_langs = sorted(lang_totals.items(), key=lambda item: item[1], reverse=True)
    percentages = [(lang, (count / grand_total) * 100) for lang, count in sorted_langs]

    if len(percentages) <= MAX_LANGUAGES_DISPLAYED:
        return percentages

    shown = percentages[: MAX_LANGUAGES_DISPLAYED - 1]
    others = sum(percent for _, percent in percentages[MAX_LANGUAGES_DISPLAYED - 1 :])
    shown.append(("Other", others))
    return shown


def build_svg(rows: List[tuple[str, float]], username: str, include_forks: bool) -> str:
    width = 780
    row_height = 34
    padding = 24
    title_space = 88
    footer_space = 32
    body_height = max(1, len(rows)) * row_height
    height = padding + title_space + body_height + footer_space

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
        "  <title id=\"title\">Top Languages</title>",
        f"  <desc id=\"desc\">Language distribution for public repositories owned by {escape(username)}</desc>",
        "  <defs>",
        "    <linearGradient id=\"bg\" x1=\"0\" x2=\"0\" y1=\"0\" y2=\"1\">",
        "      <stop offset=\"0%\" stop-color=\"#0D1117\"/>",
        "      <stop offset=\"100%\" stop-color=\"#161B22\"/>",
        "    </linearGradient>",
        "  </defs>",
        f"  <rect x=\"0.5\" y=\"0.5\" width=\"{width - 1}\" height=\"{height - 1}\" rx=\"12\" fill=\"url(#bg)\" stroke=\"#30363D\"/>",
        "  <text x=\"24\" y=\"38\" fill=\"#E6EDF3\" font-family=\"-apple-system,Segoe UI,Helvetica,Arial,sans-serif\" font-size=\"24\" font-weight=\"700\">Top Languages</text>",
        f"  <text x=\"24\" y=\"62\" fill=\"#8B949E\" font-family=\"-apple-system,Segoe UI,Helvetica,Arial,sans-serif\" font-size=\"14\">User: {escape(username)} · Public repositories · {'Including' if include_forks else 'Excluding'} forks</text>",
    ]

    if not rows:
        lines.append(
            "  <text x=\"24\" y=\"100\" fill=\"#8B949E\" font-family=\"-apple-system,Segoe UI,Helvetica,Arial,sans-serif\" font-size=\"14\">No language data available.</text>"
        )
    else:
        bar_left = 250
        bar_width = 480
        start_y = padding + title_space

        for index, (lang, percent) in enumerate(rows):
            y = start_y + index * row_height
            color = PALETTE[index % len(PALETTE)]
            bar_fill = max(2.0, bar_width * (percent / 100.0))
            lines.extend(
                [
                    f"  <text x=\"24\" y=\"{y + 18}\" fill=\"#E6EDF3\" font-family=\"-apple-system,Segoe UI,Helvetica,Arial,sans-serif\" font-size=\"14\">{escape(lang)}</text>",
                    f"  <text x=\"215\" y=\"{y + 18}\" text-anchor=\"end\" fill=\"#8B949E\" font-family=\"-apple-system,Segoe UI,Helvetica,Arial,sans-serif\" font-size=\"13\">{percent:.2f}%</text>",
                    f"  <rect x=\"{bar_left}\" y=\"{y + 4}\" width=\"{bar_width}\" height=\"12\" rx=\"6\" fill=\"#21262D\"/>",
                    f"  <rect x=\"{bar_left}\" y=\"{y + 4}\" width=\"{bar_fill:.2f}\" height=\"12\" rx=\"6\" fill=\"{color}\"/>",
                ]
            )

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines.append(
        f"  <text x=\"24\" y=\"{height - 12}\" fill=\"#8B949E\" font-family=\"-apple-system,Segoe UI,Helvetica,Arial,sans-serif\" font-size=\"12\">Auto-generated via GitHub Actions · Updated {timestamp}</text>"
    )
    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def main() -> int:
    username = os.environ.get("GITHUB_USERNAME", DEFAULT_USERNAME).strip() or DEFAULT_USERNAME
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    output_path = os.environ.get("OUTPUT_PATH", DEFAULT_OUTPUT_PATH)
    include_forks = os.environ.get("INCLUDE_FORKS", "false").lower() == "true"
    mock_lang_totals = os.environ.get("MOCK_LANG_TOTALS", "").strip()

    if mock_lang_totals:
        repos = []
        lang_totals = {k: int(v) for k, v in json.loads(mock_lang_totals).items()}
    else:
        repos = list_public_repos(username=username, token=token, include_forks=include_forks)
        lang_totals = aggregate_languages(repos, token=token)
    percentages = as_percentages(lang_totals)
    svg = build_svg(percentages, username=username, include_forks=include_forks)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as file:
        file.write(svg)

    print(f"Wrote {output_path} with {len(percentages)} language rows from {len(repos)} repositories.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
