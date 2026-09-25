#!/usr/bin/env python3
"""Build the static site published to GitHub Pages as flakemap's live demo.

It is exactly `flakemap`'s own `--html` report, rendered from the synthetic
JUnit XML corpus committed under `examples/demo_project/runs/` (see
`examples/demo_project/generate_demo_data.py` and `docs/formats.md` for how
that corpus was produced). No fabricated numbers: every cell in the heatmap
comes from a real, planted `pytest` run.

    uv run python scripts/build_demo_site.py

writes `site/index.html`.
"""

from __future__ import annotations

from pathlib import Path

from flakemap.loader import load_runs
from flakemap.report import render_html
from flakemap.stats import analyze

ROOT = Path(__file__).resolve().parent.parent
RUNS_DIR = ROOT / "examples" / "demo_project" / "runs"
OUT = ROOT / "site" / "index.html"

TITLE = "flakemap · live demo report on 222 CI runs"
DESCRIPTION = (
    "Find the flaky tests in your CI history: JUnit XML from past runs in, a ranked, "
    "statistically honest flake report out. This page is flakemap's own HTML report."
)
OG_IMAGE = "https://raw.githubusercontent.com/antonsoo/flakemap/main/docs/assets/og.png"
# Link-preview metadata for the published page only; the report itself stays
# self-contained and makes no network requests.
HEAD_EXTRA = f"""
<meta name="description" content="{DESCRIPTION}">
<link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 32 32%22><rect width=%2232%22 height=%2232%22 rx=%224%22 fill=%22%23e8ecee%22/><rect x=%224%22 y=%229%22 width=%2224%22 height=%224%22 fill=%22%232e6b4f%22/><rect x=%224%22 y=%2215%22 width=%2214%22 height=%224%22 fill=%22%232e6b4f%22/><rect x=%2218%22 y=%2215%22 width=%2210%22 height=%224%22 fill=%22%23b23a2e%22/><rect x=%224%22 y=%2221%22 width=%2224%22 height=%224%22 fill=%22%232e6b4f%22/></svg>">
<meta property="og:type" content="website">
<meta property="og:title" content="{TITLE}">
<meta property="og:description" content="{DESCRIPTION}">
<meta property="og:url" content="https://antonsoo.github.io/flakemap/">
<meta property="og:image" content="{OG_IMAGE}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:image" content="{OG_IMAGE}">
"""


def main() -> None:
    if not RUNS_DIR.is_dir():
        raise SystemExit(
            f"{RUNS_DIR} is missing; run "
            "'uv run python examples/demo_project/generate_demo_data.py' first "
            "(or check it out -- it's committed)."
        )
    runs = load_runs(RUNS_DIR)
    result = analyze(runs)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    page = render_html(result, runs, title=TITLE).replace("</head>", HEAD_EXTRA + "</head>", 1)
    OUT.write_text(page, encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size:,} bytes) from {len(runs)} runs")


if __name__ == "__main__":
    main()
