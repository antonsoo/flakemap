"""Self-contained HTML report: the test x run heatmap plus per-test detail.

Design: an "inspection report" metaphor (a physical QC sheet for defects, not a
SaaS dashboard) — tests are inspected across runs, non-healthy ones get a stamp
("DEFECT" for broken, "INTERMITTENT" for flaky). No external requests: fonts are
system stacks, styling and layout are inline `<style>`, and there is no
JavaScript — expand/collapse per-test detail uses native `<details>`, and cell
tooltips use the native `title` attribute. That makes the file work offline,
in an email attachment, or opened straight from a CI artifact zip, which matters
more for a report than any interactivity JS could add.
"""

from __future__ import annotations

from collections import defaultdict
from html import escape

from flakemap.models import Run, Status, TestCaseResult
from flakemap.stats.analyze import AnalysisResult, TestStats

_STATUS_CLASS = {
    Status.PASS: "s-pass",
    Status.FAIL: "s-fail",
    Status.ERROR: "s-error",
    Status.SKIP: "s-skip",
}
_STATUS_LABEL = {
    Status.PASS: "pass",
    Status.FAIL: "fail",
    Status.ERROR: "error",
    Status.SKIP: "skip",
}
_STAMP = {"broken": "DEFECT", "flaky": "INTERMITTENT"}


def _build_matrix(runs: list[Run]) -> dict[str, dict[str, TestCaseResult]]:
    matrix: dict[str, dict[str, TestCaseResult]] = defaultdict(dict)
    for run in runs:
        for tc in run.testcases:
            matrix[tc.full_name][run.metadata.run_id] = tc
    return matrix


def _cell(run: Run, tc: TestCaseResult | None) -> str:
    md = run.metadata
    when = md.timestamp.strftime("%Y-%m-%d %H:%M") if md.timestamp else "unknown time"
    if tc is None:
        title = f"{md.run_id} · {when} · not present in this run"
        return f'<span class="cell s-missing" title="{escape(title)}"></span>'
    dur = f"{tc.duration:.2f}s" if tc.duration is not None else "n/a"
    label = _STATUS_LABEL[tc.status]
    title = f"{md.run_id} · {when} · {label} · {dur}"
    if md.commit:
        title += f" · {md.commit[:12]}"
    if tc.message:
        title += f" · {tc.message}"
    return f'<span class="cell {_STATUS_CLASS[tc.status]}" title="{escape(title)}"></span>'


def _stat_row(label: str, value: str) -> str:
    return f'<div class="stat"><span class="stat-label">{escape(label)}</span><span class="stat-value">{escape(value)}</span></div>'


def _test_detail(t: TestStats) -> str:
    parts = [
        _stat_row(
            "Failure rate (95% Wilson CI)",
            f"{t.failure_rate.point:.1%}  [{t.failure_rate.low:.1%}, {t.failure_rate.high:.1%}]",
        ),
        _stat_row("Flip rate", f"{t.flip_rate:.1%} of consecutive run pairs"),
        _stat_row(
            "Same-commit rerun disagreement",
            f"{t.rerun_commits_flaky}/{t.rerun_commits_total} commits with reruns"
            if t.rerun_commits_total
            else "no commits with multiple runs observed",
        ),
        _stat_row("Flakiness score", f"{t.flakiness_score:.3f}"),
    ]
    if t.change_point:
        parts.append(
            _stat_row(
                "Change point",
                f"{t.change_point.rate_before:.0%} → {t.change_point.rate_after:.0%} "
                f"failure rate at run {escape(t.change_point_run_id or '?')}"
                + (f" (commit {t.change_point_commit[:12]})" if t.change_point_commit else ""),
            )
        )
    if t.duration_trend is not None:
        parts.append(_stat_row("Duration trend", f"{t.duration_trend * 1000:+.1f} ms/run"))
    if t.duration_failure_correlation is not None:
        parts.append(
            _stat_row("Duration × failure correlation", f"{t.duration_failure_correlation:+.2f}")
        )
    for group_name, rates in (("runner", t.runner_rates), ("OS", t.os_rates)):
        if rates:
            spread = ", ".join(f"{g.label}: {g.interval.point:.0%} (n={g.n})" for g in rates)
            parts.append(_stat_row(f"Failure rate by {group_name}", spread))
    if t.message_clusters:
        msgs = "".join(
            f"<li><code>{escape(c.representative)}</code> ×{c.count}</li>"
            for c in t.message_clusters
        )
        parts.append(
            f'<div class="stat"><span class="stat-label">Failure messages</span></div><ul class="messages">{msgs}</ul>'
        )
    return "".join(parts)


def _test_row(t: TestStats, runs: list[Run], matrix: dict[str, dict[str, TestCaseResult]]) -> str:
    cells = "".join(
        _cell(run, matrix.get(t.full_name, {}).get(run.metadata.run_id)) for run in runs
    )
    stamp = _STAMP.get(t.classification)
    stamp_html = f'<span class="stamp stamp-{t.classification}">{stamp}</span>' if stamp else ""
    ci = f"{t.failure_rate.point:.0%}"
    return f"""
<details class="row row-{t.classification}">
  <summary>
    <span class="row-name">
      <span class="dot dot-{t.classification}"></span>
      <span class="name-text" title="{escape(t.full_name)}">{escape(t.full_name)}</span>
      {stamp_html}
    </span>
    <span class="row-heatmap">{cells}</span>
    <span class="row-rate">{ci}</span>
  </summary>
  <div class="detail">{_test_detail(t)}</div>
</details>"""


_CSS = """
:root {
  --paper: #e7edee; --paper-raised: #f4f7f7; --ink: #16232a; --ink-soft: #46585f;
  --grid-line: #c4d0d2; --pass: #2e6f4e; --fail: #b4392b; --error: #b8631a;
  --skip: #8b98a0; --missing: #d7dee0; --flaky: #c08a1b; --broken: #b4392b;
  --healthy: #2e6f4e; --accent: #1c4f63;
  --font-display: "Archivo Narrow", "Arial Narrow", "Helvetica Neue", Arial, sans-serif;
  --font-body: ui-sans-serif, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  --font-mono: ui-monospace, "Cascadia Mono", "SFMono-Regular", "Roboto Mono", Menlo, Consolas, monospace;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --paper: #10181b; --paper-raised: #172226; --ink: #dce7e9; --ink-soft: #93a6ac;
    --grid-line: #29383d; --pass: #52b788; --fail: #e2665a; --error: #e2924c;
    --skip: #5e6e75; --missing: #223034; --flaky: #e0a93a; --broken: #e2665a;
    --healthy: #52b788; --accent: #6fc3db;
  }
}
:root[data-theme="dark"] {
  --paper: #10181b; --paper-raised: #172226; --ink: #dce7e9; --ink-soft: #93a6ac;
  --grid-line: #29383d; --pass: #52b788; --fail: #e2665a; --error: #e2924c;
  --skip: #5e6e75; --missing: #223034; --flaky: #e0a93a; --broken: #e2665a;
  --healthy: #52b788; --accent: #6fc3db;
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--paper); color: var(--ink); font-family: var(--font-body);
  padding: 0 0 4rem;
}
.masthead {
  background-image: linear-gradient(var(--grid-line) 1px, transparent 1px),
    linear-gradient(90deg, var(--grid-line) 1px, transparent 1px);
  background-size: 24px 24px; background-position: -1px -1px;
  border-bottom: 3px solid var(--ink); padding: 2rem 1.5rem 1.5rem;
}
.masthead h1 {
  font-family: var(--font-display); font-weight: 800; text-transform: uppercase;
  letter-spacing: 0.06em; font-size: clamp(1.8rem, 5vw, 2.9rem); margin: 0 0 0.15rem;
}
.masthead .tagline { color: var(--ink-soft); margin: 0 0 1.1rem; font-size: 0.98rem; }
.meta-strip {
  display: flex; flex-wrap: wrap; gap: 0.4rem 1.6rem; font-family: var(--font-mono);
  font-size: 0.82rem; color: var(--ink-soft); background: var(--paper-raised);
  border: 1px solid var(--grid-line); padding: 0.6rem 0.9rem; max-width: fit-content;
}
.meta-strip b { color: var(--ink); font-weight: 600; }
.tally { display: flex; flex-wrap: wrap; gap: 0.6rem; padding: 1.25rem 1.5rem 0; }
.tally-item {
  font-family: var(--font-mono); font-size: 0.82rem; border: 1px solid var(--grid-line);
  padding: 0.35rem 0.7rem; background: var(--paper-raised); border-radius: 2px;
}
.tally-item b { font-family: var(--font-display); font-size: 1rem; margin-right: 0.35em; }
.tally-broken b { color: var(--broken); } .tally-flaky b { color: var(--flaky); }
.tally-healthy b { color: var(--healthy); } .tally-na b { color: var(--ink-soft); }
.warning {
  margin: 1rem 1.5rem 0; padding: 0.6rem 0.9rem; border: 1px solid var(--flaky);
  border-left-width: 4px; background: var(--paper-raised); font-size: 0.85rem; color: var(--ink-soft);
}
section.heatmap { padding: 1.75rem 1.5rem 0; }
section.heatmap h2 {
  font-family: var(--font-display); text-transform: uppercase; letter-spacing: 0.05em;
  font-size: 1.05rem; border-bottom: 2px solid var(--ink); padding-bottom: 0.4rem; margin-bottom: 0.9rem;
}
.rows { border: 1px solid var(--grid-line); background: var(--paper-raised); }
.row { border-bottom: 1px solid var(--grid-line); }
.row:last-child { border-bottom: none; }
.row summary {
  list-style: none; cursor: pointer; display: flex; align-items: center; gap: 0.9rem;
  padding: 0.4rem 0.75rem; font-family: var(--font-mono); font-size: 0.78rem;
}
.row summary::-webkit-details-marker { display: none; }
.row summary::marker { content: ""; }
.row summary:hover { background: rgba(28, 79, 99, 0.06); }
.row summary:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
.row-name {
  flex: 0 0 clamp(200px, 30vw, 420px); min-width: 0; display: flex; align-items: center; gap: 0.5em;
}
.name-text { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-width: 0; }
.dot { width: 8px; height: 8px; border-radius: 50%; flex: none; }
.dot-broken { background: var(--broken); } .dot-flaky { background: var(--flaky); }
.dot-healthy { background: var(--healthy); } .dot-insufficient_data { background: var(--ink-soft); }
.stamp {
  font-family: var(--font-display); font-weight: 800; font-size: 0.6rem; letter-spacing: 0.06em;
  border: 1.5px solid currentColor; border-radius: 3px; padding: 0.05em 0.35em; transform: rotate(-3deg);
  display: inline-block; flex: none; white-space: nowrap;
}
.stamp-broken { color: var(--broken); } .stamp-flaky { color: var(--flaky); }
.row-heatmap { flex: 1 1 auto; display: flex; gap: 1px; overflow-x: auto; padding: 2px 0; }
.cell { width: 6px; height: 14px; flex: none; border-radius: 1px; }
.s-pass { background: var(--pass); } .s-fail { background: var(--fail); }
.s-error { background: var(--error); } .s-skip { background: var(--skip); }
.s-missing { background: var(--missing); }
.row-rate { flex: 0 0 3.2rem; text-align: right; color: var(--ink-soft); }
.detail { padding: 0.7rem 1rem 1rem 2.4rem; background: var(--paper); font-size: 0.83rem; }
.stat { display: flex; gap: 0.6rem; padding: 0.15rem 0; }
.stat-label { flex: 0 0 15rem; color: var(--ink-soft); }
.stat-value { font-family: var(--font-mono); }
.messages { margin: 0.2rem 0 0.6rem; padding-left: 1.2rem; font-family: var(--font-mono); font-size: 0.78rem; }
.legend { display: flex; flex-wrap: wrap; gap: 1rem; padding: 0.9rem 0.1rem 0; font-size: 0.78rem; color: var(--ink-soft); align-items: center; }
.legend .cell { display: inline-block; vertical-align: middle; margin-right: 0.3em; }
footer { padding: 2rem 1.5rem 0; font-size: 0.8rem; color: var(--ink-soft); }
footer a { color: var(--accent); }
@media (max-width: 600px) {
  .row-name { flex-basis: 120px; font-size: 0.7rem; }
  .stat-label { flex-basis: 9rem; }
}
"""


def render_html(result: AnalysisResult, runs: list[Run], title: str = "flakemap report") -> str:
    """Render the full self-contained HTML report for `result` over `runs`."""
    matrix = _build_matrix(runs)
    tests_ranked = sorted(
        result.tests,
        key=lambda t: (
            {"broken": 0, "flaky": 1, "insufficient_data": 2, "healthy": 3}[t.classification],
            -t.flakiness_score,
        ),
    )
    rows_html = "".join(_test_row(t, runs, matrix) for t in tests_ranked)

    counts = {
        k: sum(1 for t in result.tests if t.classification == k)
        for k in ("broken", "flaky", "healthy", "insufficient_data")
    }
    run_range = (
        f"{result.run_id_range[0]} → {result.run_id_range[1]}" if result.run_id_range else "n/a"
    )
    ts_range = ""
    if result.timestamp_range:
        a, b = result.timestamp_range
        ts_range = f"<span><b>window</b> {a:%Y-%m-%d} → {b:%Y-%m-%d}</span>"

    warning_html = (
        f'<div class="warning">{escape(result.mtime_fallback_warning)}</div>'
        if result.mtime_fallback_warning
        else ""
    )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
<style>{_CSS}</style>
</head>
<body>
<header class="masthead">
  <h1>flakemap &mdash; inspection report</h1>
  <p class="tagline">Test reliability across CI history, computed from JUnit XML.</p>
  <div class="meta-strip">
    <span><b>runs</b> {result.total_runs}</span>
    <span><b>tests</b> {len(result.tests)}</span>
    <span><b>run range</b> {escape(run_range)}</span>
    {ts_range}
  </div>
</header>
{warning_html}
<div class="tally">
  <div class="tally-item tally-broken"><b>{counts["broken"]}</b>broken</div>
  <div class="tally-item tally-flaky"><b>{counts["flaky"]}</b>flaky</div>
  <div class="tally-item tally-healthy"><b>{counts["healthy"]}</b>healthy</div>
  <div class="tally-item tally-na"><b>{counts["insufficient_data"]}</b>insufficient data</div>
</div>
<section class="heatmap">
  <h2>Test &times; run heatmap</h2>
  <div class="rows">{rows_html}</div>
  <div class="legend">
    <span><span class="cell s-pass"></span>pass</span>
    <span><span class="cell s-fail"></span>fail</span>
    <span><span class="cell s-error"></span>error</span>
    <span><span class="cell s-skip"></span>skip</span>
    <span><span class="cell s-missing"></span>not run</span>
    <span>Rows sorted broken &rarr; flaky &rarr; insufficient data &rarr; healthy, then by score. Columns are runs in chronological order. Click a row for detail. Hover a cell for the run.</span>
  </div>
</section>
<footer>
  Generated by <a href="https://github.com/antonsoo/flakemap">flakemap</a>. Scoring formula and
  methodology: see the README. Pairs with <a href="https://github.com/antonsoo/logdelta">logdelta</a>
  for diffing the actual failing-run logs once you know which test to look at.
</footer>
</body>
</html>
"""
