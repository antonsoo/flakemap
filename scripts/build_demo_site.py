#!/usr/bin/env python3
"""Build four navigable, offline examples using the CLI's own HTML renderer.

All inputs are committed. Captured controlled runs and hand-authored boundary
cases are explicitly distinguished. No data is fetched and nothing is deployed.
Run `uv run python scripts/build_demo_site.py` to write the `site/` directory.
"""

from __future__ import annotations

import base64
import json
from html import escape
from pathlib import Path

from flakemap.loader import load_runs
from flakemap.report import render_html, to_json_dict
from flakemap.stats import analyze

ROOT = Path(__file__).resolve().parent.parent
DEMOS = (
    (
        "index",
        "Long history",
        "examples/demo_project/runs",
        "222 captured pytest runs with planted intermittent failures and a regression. "
        "Open a test row to inspect its history and uncertainty. "
        "This is a controlled demonstration, not production reliability data.",
    ),
    (
        "cofailure",
        "Shared outages",
        "examples/cofailure_history",
        "Twelve captured pytest runs against a real loopback HTTP service with controlled outages. "
        "Three endpoint tests fail together on runs 04, 05 and 10. "
        "Open their group to investigate; an independent failure and partial coverage stay separate.",
    ),
    (
        "retry",
        "Hidden retries",
        "examples/retry_history",
        "Captured Maven Surefire output from intentionally failing Java tests. "
        "Two tests passed only after failed attempts. Open their evidence to see why "
        "a green final result does not erase a failure, and why attempts are not extra runs.",
    ),
    (
        "incomplete",
        "Interrupted input",
        "examples/incomplete_history",
        "Hand-authored boundary case, not captured runner output. "
        "A truncated report preserves completed cases, ambiguous TRX outcomes stay unknown, "
        "and missing timings do not become zero. Open the warnings and affected test rows.",
    ),
)
OG_IMAGE = "https://raw.githubusercontent.com/antonsoo/flakemap/main/docs/assets/og.png"
# Link-preview metadata for the published page only; the report itself stays
# self-contained and makes no network requests.
HEAD_EXTRA = f"""
<link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 32 32%22><rect width=%2232%22 height=%2232%22 rx=%224%22 fill=%22%23e8ecee%22/><rect x=%224%22 y=%229%22 width=%2224%22 height=%224%22 fill=%22%232e6b4f%22/><rect x=%224%22 y=%2215%22 width=%2214%22 height=%224%22 fill=%22%232e6b4f%22/><rect x=%2218%22 y=%2215%22 width=%2210%22 height=%224%22 fill=%22%23b23a2e%22/><rect x=%224%22 y=%2221%22 width=%2224%22 height=%224%22 fill=%22%232e6b4f%22/></svg>">
<meta property="og:type" content="website">
<meta property="og:image" content="{OG_IMAGE}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:image" content="{OG_IMAGE}">
"""

GALLERY_CSS = """
<style>
.demo-context { margin: 1.25rem 1.5rem; padding: 1rem; border: 1px solid var(--grid-line);
  background: var(--paper-raised); font-size: .88rem; line-height: 1.6; overflow-wrap: anywhere; }
.demo-context h2 { font-size: 1rem; margin: .75rem 0 .25rem; }
.demo-context p { margin: .25rem 0 .7rem; }
.demo-context nav ul { display: flex; flex-wrap: wrap; gap: .5rem; list-style: none; padding: 0; margin: 0; }
.demo-context nav a { display: block; padding: .4rem .65rem; border: 1px solid var(--grid-line); }
.demo-context a { color: var(--accent); text-underline-offset: .2em; }
.demo-context a[aria-current] { color: var(--paper-raised); background: var(--ink); border-color: var(--ink); }
.demo-context a:focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; }
</style>
"""


def build(output: Path) -> list[dict[str, object]]:
    output.mkdir(parents=True, exist_ok=True)
    manifest = []
    for slug, label, source, description in DEMOS:
        runs = load_runs(ROOT / source)
        result = analyze(runs)
        payload = json.dumps(to_json_dict(result), indent=2, allow_nan=False) + "\n"
        encoded = base64.b64encode(payload.encode()).decode("ascii")
        title = f"flakemap · {label}"
        links = "".join(
            f'<li><a href="{other}.html"'
            + (' aria-current="page"' if other == slug else "")
            + f">{escape(other_label)}</a></li>"
            for other, other_label, _, _ in DEMOS
        )
        context = (
            '<aside class="demo-context" aria-label="Example context">'
            f'<nav aria-label="Report examples"><ul>{links}</ul></nav>'
            f"<h2>{escape(label)}</h2><p>{escape(description)}</p>"
            f'<a href="data:application/json;base64,{encoded}" download="{slug}.json">'
            "Download this analysis as JSON</a> · "
            f'<a href="https://github.com/antonsoo/flakemap/tree/main/{source}">Source fixture</a></aside>'
        )
        metadata = (
            HEAD_EXTRA
            + GALLERY_CSS
            + f'<meta name="description" content="{escape(description, quote=True)}">'
            + f'<meta property="og:title" content="{escape(title, quote=True)}">'
            + f'<meta property="og:description" content="{escape(description, quote=True)}">'
            + f'<meta property="og:url" content="https://antonsoo.github.io/flakemap/{slug}.html">'
        )
        page = render_html(result, runs, title=title).replace("</head>", metadata + "</head>", 1)
        page = page.replace("<main>", "<main>" + context, 1)
        (output / f"{slug}.html").write_text(page, encoding="utf-8")
        (output / f"{slug}.json").write_text(payload, encoding="utf-8")
        manifest.append(
            {"name": slug, "source": source, "runs": len(runs), "tests": len(result.tests)}
        )
        print(f"wrote {output / (slug + '.html')} from {len(runs)} runs")
    return manifest


def main() -> None:
    build(ROOT / "site")


if __name__ == "__main__":
    main()
