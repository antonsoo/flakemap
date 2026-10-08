"""The study's figure: when each frequently failing test failed, as dependency-free SVG.

    uv run python studies/kubernetes-ci/figures.py

One row per test that failed five times or more (and the two flagged as new),
a tick per failed build at its start time, and, where Kubernetes' tracker
records one, the moment a fix for that test merged. Reads results.json; the
fix dates are the entries of `FIXES`, picked by hand from tracker.json and
checked against each pull request's own page.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path
from typing import Any

HERE = Path(__file__).parent
FONT = "system-ui, -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif"
MONO = "ui-monospace, 'Cascadia Mono', 'SFMono-Regular', Menlo, Consolas, monospace"
THEMES: dict[str, dict[str, str]] = {
    "light": {
        "surface": "#fcfcfb",
        "ink": "#0b0b0b",
        "secondary": "#52514e",
        "muted": "#898781",
        "grid": "#e1e0d9",
        "rail": "#e9e8e2",
        "ongoing": "#eb6834",
        "new": "#2a78d6",
        "quiet": "#898781",
    },
    "dark": {
        "surface": "#1a1a19",
        "ink": "#ffffff",
        "secondary": "#c3c2b7",
        "muted": "#898781",
        "grid": "#2c2c2a",
        "rail": "#2a2a28",
        "ongoing": "#d95926",
        "new": "#3987e5",
        "quiet": "#898781",
    },
}
ENOUGH_FAILURES = 5
# The merged pull request that names the test (in its title or description) and whose
# merge is nearest the test's last failure. From tracker.json; each `merged_at` is as
# https://github.com/kubernetes/kubernetes/pull/<number> shows it.
FIXES: dict[str, tuple[int, str]] = {
    "TestTimeTravelHealthcheck": (140575, "2026-09-03T17:52+00:00"),
    "TestDRA": (141060, "2026-08-04T16:54+00:00"),
    "TestFullFlow": (140826, "2026-07-23T07:07+00:00"),
    "TestReconstructedVolumeShouldUnmountSucceedAfterSetupFailed": (
        141062,
        "2026-08-03T09:47+00:00",
    ),
}
WIDTH, LEFT, RIGHT, ROW = 880, 252, 170, 24


def _shorten(name: str, limit: int = 34) -> str:
    return name if len(name) <= limit else name[: limit - 1] + "…"


def _since(row: dict[str, Any], end: datetime) -> str:
    last = datetime.fromisoformat(row["last_failure"])
    days = (end - last).days
    if row["state"] == "quiet":
        return f"quiet for {days} days"
    if row["state"] == "new":
        first = datetime.fromisoformat(row["first_failure"])
        return f"new, first {(end - first).days} days ago"
    return f"ongoing, {days} days ago" if days else "ongoing, today"


def timeline(results: dict[str, Any], theme: str) -> str:
    c = THEMES[theme]
    jobs = []
    for job, summary in results["jobs"].items():
        rows = [
            row
            for row in summary["tests"]
            if row["failed_runs"] >= ENOUGH_FAILURES or row["state"] == "new"
        ]
        order = {"new": 0, "ongoing": 1, "quiet": 2}
        rows.sort(key=lambda row: (order[row["state"]], -row["failed_runs"]))
        jobs.append((job, summary, rows))
    start = min(datetime.fromisoformat(s["window"][0]) for _, s, _ in jobs)
    end = max(datetime.fromisoformat(s["window"][1]) for _, s, _ in jobs)
    span = (end - start).total_seconds()
    plot = WIDTH - LEFT - RIGHT

    def x(moment: datetime) -> float:
        return LEFT + plot * (moment - start).total_seconds() / span

    height = 96 + sum(34 + ROW * len(rows) for _, _, rows in jobs) + 44
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {height}" width="{WIDTH}" '
        f'height="{height}" role="img" font-family="{FONT}">',
        "<title>When each frequently failing test failed, 9 July to 8 October 2026</title>",
        f'<rect width="{WIDTH}" height="{height}" fill="{c["surface"]}"/>',
        f'<text x="24" y="30" font-size="16" font-weight="600" fill="{c["ink"]}">'
        "Flakes come and go: 91 days of two Kubernetes CI jobs</text>",
        f'<text x="24" y="50" font-size="12.5" fill="{c["secondary"]}">One tick per failed '
        "build. Every test that failed five times or more, and the two flagged as new.</text>",
    ]
    # Legend: state is also written at the end of every row, so colour is never alone.
    lx = 24.0
    for key, label in (("new", "new"), ("ongoing", "ongoing"), ("quiet", "quiet")):
        out.append(f'<rect x="{lx}" y="64" width="3" height="13" fill="{c[key]}"/>')
        out.append(
            f'<text x="{lx + 9}" y="75" font-size="12" fill="{c["secondary"]}">{label}</text>'
        )
        lx += 9 + 7.2 * len(label) + 18
    out.append(
        f'<path d="M{lx} 65 l5 9 l5 -9 z" fill="none" stroke="{c["ink"]}" stroke-width="1.4"/>'
        f'<text x="{lx + 16}" y="75" font-size="12" fill="{c["secondary"]}">'
        "a fix for the test merged (Kubernetes' tracker)</text>"
    )

    y = 96.0
    months = []
    cursor = datetime(start.year, start.month, 1, tzinfo=timezone.utc)
    while cursor <= end:
        if cursor >= start:
            months.append(cursor)
        cursor = (cursor + timedelta(days=32)).replace(day=1)
    for job, summary, rows in jobs:
        failed = summary["build_results"].get("FAILURE", 0)
        out.append(
            f'<text x="24" y="{y + 14}" font-size="12.5" font-weight="600" fill="{c["ink"]}">'
            f"{escape(job)}</text>"
            f'<text x="{WIDTH - RIGHT + 12}" y="{y + 14}" font-size="11.5" '
            f'fill="{c["secondary"]}">{failed} of {summary["builds_listed"]:,} builds failed</text>'
        )
        top = y + 24
        bottom = top + ROW * len(rows)
        for month in months:
            mx = x(month)
            out.append(
                f'<line x1="{mx:.1f}" y1="{top}" x2="{mx:.1f}" y2="{bottom}" '
                f'stroke="{c["grid"]}" stroke-width="1"/>'
            )
            out.append(
                f'<text x="{mx + 4:.1f}" y="{y + 14}" font-size="11" fill="{c["muted"]}">'
                f"{month:%b}</text>"
            )
        for index, row in enumerate(rows):
            cy = top + ROW * index + ROW / 2
            out.append(
                f'<text x="24" y="{cy + 4}" font-size="11" font-family="{MONO}" '
                f'fill="{c["ink"]}"><title>{escape(row["package"])}: {escape(row["test"])}</title>'
                f"{escape(_shorten(row['test']))}</text>"
            )
            out.append(
                f'<rect x="{LEFT}" y="{cy - 1}" width="{plot}" height="2" fill="{c["rail"]}"/>'
            )
            for moment in row["failure_times"]:
                fx = x(datetime.fromisoformat(moment))
                out.append(
                    f'<rect x="{fx - 1:.1f}" y="{cy - 7}" width="2" height="14" '
                    f'fill="{c[row["state"]]}"><title>{escape(row["test"])} failed, '
                    f"{moment[:16].replace('T', ' ')} UTC</title></rect>"
                )
            fix = FIXES.get(row["test"])
            if fix:
                fx = x(datetime.fromisoformat(fix[1]))
                out.append(
                    f'<path d="M{fx - 5:.1f} {cy - 11} l5 9 l5 -9 z" fill="{c["surface"]}" '
                    f'stroke="{c["ink"]}" stroke-width="1.4"><title>#{fix[0]} merged '
                    f"{fix[1][:16].replace('T', ' ')} UTC</title></path>"
                )
            out.append(
                f'<text x="{WIDTH - RIGHT + 12}" y="{cy + 4}" font-size="11.5" fill="{c["ink"]}">'
                f'<tspan font-weight="600">{row["failed_runs"]}</tspan>'
                f'<tspan fill="{c["secondary"]}">  {escape(_since(row, end))}</tspan></text>'
            )
        y = bottom + 10
    out.append(
        f'<text x="24" y="{height - 16}" font-size="11" fill="{c["muted"]}">'
        "Builds from the public Prow bucket; tests named in each failed package's own output. "
        "Quiet and new are flakemap's calls from where the ticks fall.</text>"
    )
    out.append("</svg>")
    return "\n".join(out) + "\n"


def main() -> None:
    results = json.loads((HERE / "results.json").read_text())
    figures = HERE / "figures"
    figures.mkdir(exist_ok=True)
    for theme in THEMES:
        (figures / f"timeline-{theme}.svg").write_text(timeline(results, theme))
        print(f"wrote {figures / f'timeline-{theme}.svg'}")


if __name__ == "__main__":
    main()
