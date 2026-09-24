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
    OUT.write_text(render_html(result, runs, title="flakemap — live demo report"), encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size:,} bytes) from {len(runs)} runs")


if __name__ == "__main__":
    main()
