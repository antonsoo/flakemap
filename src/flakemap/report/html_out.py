"""Self-contained HTML report: the test x run heatmap plus per-test detail.

Design: an "inspection report" metaphor (a physical QC sheet for defects, not a
SaaS dashboard) — tests are inspected across runs, non-healthy ones get a stamp
("DEFECT" for broken, "INTERMITTENT" for flaky). No external requests: fonts are
system stacks, styling and layout are inline `<style>`, and there is no
JavaScript — expand/collapse per-test detail uses native `<details>`, and cell
tooltips use the native `title` attribute. That makes the file work offline,
in an email attachment, or opened straight from a CI artifact zip, which matters
more for a report than any interactivity JS could add.

A cell per test per run is the right picture for a few hundred runs. An hourly job
kept for three months is 2,000 runs, and a suite of 1,500 tests then has three
million cells, almost all of them green. Past `MAX_CELL_RUNS` a row is drawn as a
rail with a tick for each failure, and past `MAX_HEALTHY_ROWS` the tests that never
failed are listed by name instead of drawn, so the page grows with what happened
and not with tests x runs.
"""

from __future__ import annotations

from collections import defaultdict
from html import escape

from flakemap.models import Run, Status, TestCaseResult
from flakemap.observations import history_observations
from flakemap.ordering import order_runs, recorded_time
from flakemap.report.cofailure_html import COFAILURE_CSS, render_cofailure
from flakemap.report.names import common_prefix, short_name, visible
from flakemap.report.numbers import count, interval, of, percent
from flakemap.stats.activity import MIN_EVENTS, Activity
from flakemap.stats.analyze import AnalysisResult, FailureEvidence, TestStats

MAX_CELL_RUNS = 300
MAX_HEALTHY_ROWS = 30
MAX_LISTED_FAILURES = 40
MAX_NAMED_FAILURES = 25

_STATUS_CLASS = {
    Status.PASS: "s-pass",
    Status.FAIL: "s-fail",
    Status.ERROR: "s-error",
    Status.SKIP: "s-skip",
    Status.UNKNOWN: "s-unknown",
}
_STATUS_LABEL = {
    Status.PASS: "pass",
    Status.FAIL: "fail",
    Status.ERROR: "error",
    Status.SKIP: "skip",
    Status.UNKNOWN: "unknown; excluded",
}
_STAMP = {"broken": "DEFECT", "flaky": "INTERMITTENT", "new": "NEW FLAKE", "quiet": "QUIET"}
_SAME_COMMIT = {
    "passed": "passed in another run",
    "failed": "failed in every run",
    "single": "no other run",
    "unknown": "commit not recorded",
}


def _state(t: TestStats) -> str:
    """The row's kind: its classification, or `new` / `quiet` for a flaky test that is."""
    if t.classification == "flaky" and t.activity and t.activity.state != "ongoing":
        return t.activity.state
    return t.classification


def _build_matrix(
    result: AnalysisResult, runs: list[Run], names: set[str]
) -> dict[str, dict[str, TestCaseResult]]:
    """The normalized result of each named test in each run it appears in."""
    matrix: dict[str, dict[str, TestCaseResult]] = defaultdict(dict)
    if result.observations:
        for name in names:
            for observation in result.observations.get(name, ()):
                matrix[name][observation.run.metadata.run_id] = observation.result
        return matrix
    for observation in history_observations(runs):
        tc = observation.result
        if tc.full_name in names:
            matrix[tc.full_name][observation.run.metadata.run_id] = tc
    return matrix


def _run_title(run: Run, tc: TestCaseResult) -> str:
    md = run.metadata
    moment = recorded_time(run)
    when = moment.strftime("%Y-%m-%d %H:%M") if moment else "unknown time"
    label = _STATUS_LABEL[tc.status]
    if tc.retry and tc.status is not Status.UNKNOWN:
        label += f"; {tc.retry.outcome} after {len(tc.retry.failures)} recorded failure(s)"
    title = f"{md.run_id} · {when} · {label}"
    if md.commit:
        title += f" · {md.commit[:12]}"
    if tc.failed_within:
        title += " · " + ", ".join(tc.failed_within[:3])
    elif tc.message:
        title += f" · {tc.message}"
    if tc.issue:
        title += f" · {tc.issue}"
    return visible(title)


def _mark_kind(tc: TestCaseResult | None) -> str:
    if tc is None:
        return "missing"
    if tc.retry and tc.retry.outcome == "recovered" and tc.status is Status.PASS:
        return "recovered"
    return tc.status.value


def _strip(t: TestStats, runs: list[Run], results: dict[str, TestCaseResult]) -> str:
    """A row's history as a rail of passing runs with a full-height mark where it did not pass.

    Consecutive runs of one kind are one element, so a row costs what changed in it.
    Marks keep a 2px stroke at any width: one run in 2,000 is a third of a pixel.
    """
    kinds = [_mark_kind(results.get(run.metadata.run_id)) for run in runs]
    parts: list[str] = []
    start = 0
    for end in range(1, len(runs) + 1):
        if end < len(runs) and kinds[end] == kinds[start]:
            continue
        kind, width = kinds[start], end - start
        if kind in ("pass", "skip"):
            parts.append(f'<rect class="r-{kind}" x="{start}" y="6" width="{width}" height="4"/>')
        elif kind != "missing":
            first = results[runs[start].metadata.run_id]
            title = _run_title(runs[start], first)
            if width > 1:
                title = (
                    f"{width} {'consecutive runs' if t.temporal_available else 'adjacent displayed runs'}, {_STATUS_LABEL[first.status]} · first: {title}"
                    f" · last: {runs[end - 1].metadata.run_id}"
                )
            parts.append(
                f"<g><title>{escape(title)}</title>"
                f'<rect class="hit" x="{start}" y="0" width="{width}" height="16"/>'
                f'<rect class="m-{kind}" x="{start}" y="0" width="{width}" height="16"/></g>'
            )
        start = end
    label = f"{of(t.n_fail, t.n)} runs failed" if t.n else "no usable outcomes"
    if t.activity:
        label += f"; last observed failure {count(t.activity.runs_since_last)} runs before the end"
    return (
        f'<svg class="strip" viewBox="0 0 {len(runs)} 16" preserveAspectRatio="none" '
        f'role="img" aria-label="{escape(label)}">{"".join(parts)}</svg>'
    )


def _activity_text(activity: Activity, runs: int) -> str:
    """What the placement of the failures says, in a sentence."""
    events = (
        f"{activity.failures} failures"
        if activity.events == activity.failures
        else f"{activity.failures} failures in {activity.events} separate stretches"
    )
    if activity.recovered_runs:
        unit = "run" if activity.failures == 1 else "runs"
        stretches = "stretch" if activity.events == 1 else "stretches"
        events = (
            f"{activity.failures} {unit} with observed failures "
            f"({activity.recovered_runs} passed on retry) in {activity.events} separate {stretches}"
        )
    if activity.longest_gap is None or activity.events < MIN_EVENTS:
        return f"{events}: too few to place."
    gap = f"the longest quiet spell between failures was {count(activity.longest_gap)} runs"
    if activity.state == "quiet":
        return (
            f"Quiet: {events}; {gap}, and it has now been "
            f"{count(activity.runs_since_last)} runs ({activity.silence_ratio:.1f} times as "
            "long). The burst is over; this does not say it cannot return, or why it stopped."
        )
    if activity.state == "new":
        return (
            f"New: {events}; {gap}, and the first failure came after "
            f"{count(activity.first_index)} clean runs of {count(runs)}."
        )
    return (
        f"Ongoing: {events}; {gap}, and the last failure was "
        f"{count(activity.runs_since_last)} runs ago."
    )


def _when(failure: FailureEvidence) -> str:
    return failure.timestamp.strftime("%Y-%m-%d %H:%M") if failure.timestamp else "unknown time"


def _failure_rows(t: TestStats) -> str:
    """The most recent failures, newest first: when, where, and what else is known of each."""
    shown = (list(reversed(t.failures)) if t.temporal_available else t.failures)[
        :MAX_LISTED_FAILURES
    ]
    rows = []
    for f in shown:
        what = ", ".join(f.failed_within[:4]) if f.failed_within else (f.message or "")
        if len(f.failed_within) > 4:
            what += f", + {len(f.failed_within) - 4} more"
        same = _SAME_COMMIT[f.same_commit]
        if f.same_commit in ("passed", "failed"):
            same += f" ({f.same_commit_runs + 1} of this commit)"
        rows.append(
            f'<tr><th scope="row"><code>{escape(visible(f.run_id))}</code><br>{_when(f)}</th>'
            f"<td>{f'<code>{escape(f.commit[:12])}</code><br>' if f.commit else ''}{same}</td>"
            f"<td>{f.failed_with or 'none'}</td>"
            f"<td><code>{escape(visible(what))}</code></td></tr>"
        )
    more = (
        f'<p class="evidence-note">Showing {"the latest " if t.temporal_available else ""}{len(shown)} of {count(len(t.failures))} '
        "failures; <code>--json</code> has every one.</p>"
        if len(t.failures) > len(shown)
        else ""
    )
    return (
        f'<h3>Failures, {"newest first" if t.temporal_available else "display order only"}</h3><div class="scroll" role="region" tabindex="0" '
        f'aria-label="Failures of {escape(visible(t.full_name))}"><table class="failures"><thead><tr>'
        '<th scope="col">Run</th><th scope="col">Same commit, other runs</th>'
        '<th scope="col">Other tests failed</th><th scope="col">Named in output, or message</th>'
        f"</tr></thead><tbody>{''.join(rows)}</tbody></table></div>{more}"
    )


def _named_rows(t: TestStats) -> str:
    rows = []
    for named in t.named_failures[:MAX_NAMED_FAILURES]:
        activity = named.activity
        state = (
            "activity unavailable"
            if activity is None
            else {
                "quiet": f"quiet for {count(activity.runs_since_last)} runs",
                "new": f"first failed {count(activity.runs_since_first)} runs ago",
                "ongoing": f"first failed {count(activity.runs_since_first)} runs ago, "
                f"last {count(activity.runs_since_last)} runs ago",
            }[activity.state]
        )
        same = of(named.passed_same_commit, named.checked) if named.checked else "none to compare"
        rows.append(
            f'<tr><th scope="row"><code>{escape(visible(named.name))}</code></th>'
            f"<td>{count(named.runs)}</td><td>{same}</td><td>{state}</td></tr>"
        )
    more = (
        f'<p class="evidence-note">{len(t.named_failures) - MAX_NAMED_FAILURES} more named '
        "tests are in <code>--json</code>.</p>"
        if len(t.named_failures) > MAX_NAMED_FAILURES
        else ""
    )
    return (
        "<h3>Tests named in this testcase's failures</h3>"
        '<p class="evidence-note">The report keeps one record for the whole package; these '
        "names come from the failure output (<code>--- FAIL:</code> lines).</p>"
        '<div class="scroll" role="region" tabindex="0" '
        f'aria-label="Tests named in the failures of {escape(visible(t.full_name))}">'
        '<table class="failures"><thead><tr><th scope="col">Test</th>'
        '<th scope="col">Failed runs</th><th scope="col">Passed on same commit</th>'
        f'<th scope="col">Activity</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>{more}'
    )


def _cell(run: Run, tc: TestCaseResult | None) -> str:
    md = run.metadata
    moment = recorded_time(run)
    when = moment.strftime("%Y-%m-%d %H:%M") if moment else "unknown time"
    if tc is None:
        title = f"{md.run_id} · {when} · not present in this run"
        return f'<span class="cell s-missing" title="{escape(title)}"></span>'
    dur = f"{tc.duration:.2f}s" if tc.duration is not None else "n/a"
    label = _STATUS_LABEL[tc.status]
    css = _STATUS_CLASS[tc.status]
    if tc.retry and tc.status is not Status.UNKNOWN:
        label += f"; {tc.retry.outcome} after {len(tc.retry.failures)} recorded failure(s)"
        if tc.retry.outcome == "recovered":
            css = "s-recovered"
    title = f"{md.run_id} · {when} · {label} · {dur}"
    if md.commit:
        title += f" · {md.commit[:12]}"
    if tc.message:
        title += f" · {tc.message}"
    if tc.issue:
        title += f" · {tc.issue}"
    return f'<span class="cell {css}" role="img" aria-label="{escape(title)}" title="{escape(title)}"></span>'


def _stat_row(label: str, value: str) -> str:
    return f'<div class="stat"><span class="stat-label">{escape(label)}</span><span class="stat-value">{escape(value)}</span></div>'


def _test_detail(t: TestStats) -> str:
    parts = [
        _stat_row(
            "Final failure rate (95% CI)",
            f"{percent(t.failure_rate.point)}  [{interval(t.failure_rate.low, t.failure_rate.high)}]"
            f"  ·  {of(t.n_fail, t.n)} runs"
            if t.n
            else "unknown: no usable outcomes",
        ),
        _stat_row(
            "Usable outcomes",
            f"runs: {count(t.n)}; skipped: {count(t.n_skip)}; excluded: {count(t.n_unknown)}",
        ),
        _stat_row(
            "Passed on retry", f"{t.recovered_runs} (explicit failed attempts before a pass)"
        ),
        _stat_row("Retry exhaustion", f"{t.exhausted_runs} (every recorded attempt failed)"),
        _stat_row(
            "Flip rate",
            f"{percent(t.flip_rate)} of {count(t.flip_pairs)} usable consecutive pairs"
            if t.flip_pairs
            else "unavailable: chronology is unknown"
            if not t.temporal_available
            else "unavailable: no usable consecutive pairs",
        ),
        _stat_row(
            "Same-context rerun disagreement",
            f"{t.rerun_commits_flaky}/{t.rerun_commits_total} commit/branch/runner/OS groups"
            f"; {percent(t.rerun_signal)} of same-commit run pairs"
            if t.rerun_commits_total
            else "no commits with multiple runs observed",
        ),
        _stat_row("Flakiness score", f"{t.flakiness_score:.3f}"),
    ]
    if t.failures_checked:
        alone = len(t.failures) - t.failures_checked
        parts.append(
            _stat_row(
                "Failures on a commit run again",
                f"{of(t.failures_passed_same_commit, t.failures_checked)} passed in another run "
                f"of the same commit; {t.failures_repeated_same_commit} failed in every run of it"
                + (f"; {alone} more had no other run" if alone else ""),
            )
        )
    if not t.temporal_available:
        parts.append(
            _stat_row(
                "Chronology",
                "Unavailable: no flip rate, activity, onset, latest outcome or duration trend. The score omits its flip component.",
            )
        )
    if t.activity and t.classification != "broken":  # a broken test's story is its change point
        parts.append(_stat_row("Activity", _activity_text(t.activity, t.n)))
    elif t.activity_unavailable_reason == "ambiguous_outcomes":
        parts.append(
            _stat_row("Activity", "Unavailable: ambiguous outcomes interrupt the failure history.")
        )
    if t.change_point:
        parts.append(
            _stat_row(
                "Change point",
                f"{t.change_point.rate_before:.0%} → {t.change_point.rate_after:.0%} "
                f"failure rate at run {t.change_point_run_id or '?'}"
                + (f" (commit {t.change_point_commit[:12]})" if t.change_point_commit else ""),
            )
        )
    if t.duration_trend is not None:
        parts.append(
            _stat_row(
                "Duration trend (without retries)", f"{t.duration_trend * 1000:+.1f} ms/history run"
            )
        )
    parts.append(_stat_row("Timing observations (without retries)", str(t.duration_n)))
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
    if t.named_failures:
        parts.append(_named_rows(t))
    if t.failures:
        parts.append(_failure_rows(t))
    if t.retry_observations or t.excluded_observations:
        parts.append(
            '<h3>Recorded evidence</h3><p class="evidence-note">Sources identify a file and its '
            "1-based testcase position. Failure records follow XML order. Attempt timing and "
            "total retry cost are not inferred.</p>"
        )
    for obs in t.retry_observations + t.excluded_observations:
        label = obs.result.retry.outcome if obs.result.retry else "excluded"
        parts.append(
            f'<article class="evidence"><h4><code>{escape(obs.run.metadata.run_id)}</code> '
            f"&mdash; {label}</h4>"
        )
        if obs.result.issue:
            parts.append(f"<p>{escape(obs.result.issue)}</p>")
        for record in obs.records:
            source = (
                f"{record.source.report} :: testcase {record.source.testcase}"
                if record.source
                else "source location not supplied"
            )
            reported = (
                f"reported {escape(record.nested_results.reported_parent_outcome or '(missing)')}; "
                f"normalized {record.status.value}"
                if record.nested_results
                else f"reported {record.status.value}"
            )
            parts.append(f'<p class="source"><code>{escape(source)}</code> &mdash; {reported}</p>')
            if record.retry:
                parts.append(
                    f"<p>{record.retry.attempts} recorded attempts; "
                    f'{len(record.retry.failures)} failed.</p><ul class="messages">'
                )
                for failure in record.retry.failures:
                    parts.append(
                        f"<li><code>&lt;{escape(failure.tag)}&gt;</code> "
                        f"{escape(failure.message or '(no message recorded)')}</li>"
                    )
                parts.append("</ul>")
            elif record.message:
                parts.append(f"<p>{escape(record.message)}</p>")
        parts.append("</article>")
    return "".join(parts)


def _name(full_name: str, prefix: str) -> str:
    """A test's name in two parts, so a narrow column cuts the package and keeps the test.

    Names differ at the end: `k8s.io/kubernetes/test/integration/scheduler.plugins` and
    its forty neighbours share everything before the last component.
    """
    name = visible(short_name(full_name, prefix))
    cut = max(name.rfind("/"), name.rfind(".", 0, len(name) - 1)) + 1
    head = f'<span class="name-head">{escape(name[:cut])}</span>' if 0 < cut < len(name) else ""
    return (
        f'<span class="name-text" title="{escape(full_name)}">{head}'
        f'<span class="name-tail">{escape(name[cut:] if head else name)}</span></span>'
    )


def _test_row(
    t: TestStats,
    runs: list[Run],
    matrix: dict[str, dict[str, TestCaseResult]],
    prefix: str = "",
    anchor: str = "",
    strips: bool = False,
) -> str:
    results = matrix.get(t.full_name, {})
    state = _state(t)
    stamp = _STAMP.get(state)
    stamp_html = f'<span class="stamp stamp-{state}">{stamp}</span>' if stamp else ""
    ci = percent(t.failure_rate.point) if t.n else "n/a"
    if strips:
        history = f'<span class="row-heatmap row-strip">{_strip(t, runs, results)}</span>'
        rate = (
            f'<span class="row-rate row-count" title="Runs with a final failure, and their share">'
            f"<b>{count(t.n_fail)}</b> {ci}</span>"
        )
    else:
        cells = "".join(_cell(run, results.get(run.metadata.run_id)) for run in runs)
        history = f'<span class="row-heatmap" style="--runs:{len(runs)}">{cells}</span>'
        rate = f'<span class="row-rate" title="Final failure rate; one outcome per run">{ci}</span>'
    return f"""
<details class="row row-{t.classification}">
  <summary id="{anchor}">
    <span class="row-name">
      <span class="dot dot-{t.classification}"></span>
      {_name(t.full_name, prefix)}
      {stamp_html}
    </span>
    {history}
    {rate}
  </summary>
  <div class="detail"><h3 class="test-identity">{escape(t.full_name)}</h3>{_test_detail(t)}</div>
</details>"""


def _axis(runs: list[Run], chronological: bool = True) -> str:
    """Where in the history a position along a strip is: five runs, by date or by id."""
    last = len(runs) - 1
    labels = []
    for step in range(5):
        run = runs[round(last * step / 4)]
        md = run.metadata
        text = (
            f"{md.timestamp:%b} {md.timestamp.day}"
            if chronological and md.timestamp and md.source != "mtime"
            else visible(md.run_id)[:12]
        )
        labels.append(f'<span style="left:{25 * step}%">{escape(text)}</span>')
    return (
        '<div class="axis" aria-hidden="true"><span class="row-name"></span>'
        f'<span class="axis-ticks">{"".join(labels)}</span><span class="row-rate row-count">'
        "failed runs</span></div>"
    )


def _healthy_list(tests: list[TestStats], prefix: str, anchors: dict[str, str]) -> str:
    """Tests that passed every time, by name: a row each would be a page of solid green."""
    items = "".join(
        f'<li id="{anchors[t.full_name]}"><code>{escape(short_name(t.full_name, prefix))}</code> '
        f"<span>{count(t.n)} runs</span></li>"
        for t in sorted(tests, key=lambda t: t.full_name)
    )
    return (
        f'<details class="healthy"><summary><b>{count(len(tests))}</b> tests passed in every '
        "run that has an outcome for them &mdash; listed, not drawn</summary>"
        f'<ul class="healthy-list">{items}</ul></details>'
    )


_CSS = """
:root {
  --paper: #e7edee; --paper-raised: #f4f7f7; --ink: #16232a; --ink-soft: #46585f;
  --grid-line: #c4d0d2; --pass: #2e6f4e; --fail: #b4392b; --error: #b8631a;
  --skip: #8b98a0; --missing: #d7dee0; --flaky: #c08a1b; --broken: #b4392b;
  --healthy: #2e6f4e; --accent: #1c4f63;
  --flaky-ink: #926915;  /* --flaky as text: 4.5:1 on the raised paper, where the cell colour is 2.8:1 */
  --font-display: "Archivo Narrow", "Arial Narrow", "Helvetica Neue", Arial, sans-serif;
  --font-body: ui-sans-serif, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  --font-mono: ui-monospace, "Cascadia Mono", "SFMono-Regular", "Roboto Mono", Menlo, Consolas, monospace;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --paper: #10181b; --paper-raised: #172226; --ink: #dce7e9; --ink-soft: #93a6ac;
    --grid-line: #29383d; --pass: #52b788; --fail: #e2665a; --error: #e2924c;
    --skip: #5e6e75; --missing: #223034; --flaky: #e0a93a; --broken: #e2665a;
    --healthy: #52b788; --accent: #6fc3db; --flaky-ink: #e0a93a;
  }
}
:root[data-theme="dark"] {
  --paper: #10181b; --paper-raised: #172226; --ink: #dce7e9; --ink-soft: #93a6ac;
  --grid-line: #29383d; --pass: #52b788; --fail: #e2665a; --error: #e2924c;
  --skip: #5e6e75; --missing: #223034; --flaky: #e0a93a; --broken: #e2665a;
  --healthy: #52b788; --accent: #6fc3db; --flaky-ink: #e0a93a;
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
.tally-broken b { color: var(--broken); } .tally-flaky b { color: var(--flaky-ink); }
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
.name-text { display: flex; min-width: 0; white-space: nowrap; }
.name-head { flex: 0 1 auto; min-width: 0; overflow: hidden; text-overflow: ellipsis; }
.name-tail { flex: 0 0 auto; max-width: 100%; overflow: hidden; text-overflow: ellipsis; }
.dot { width: 8px; height: 8px; border-radius: 50%; flex: none; }
.dot-broken { background: var(--broken); } .dot-flaky { background: var(--flaky); }
.dot-healthy { background: var(--healthy); } .dot-insufficient_data { background: var(--ink-soft); }
.stamp {
  font-family: var(--font-display); font-weight: 800; font-size: 0.6rem; letter-spacing: 0.06em;
  border: 1.5px solid currentColor; border-radius: 3px; padding: 0.05em 0.35em; transform: rotate(-3deg);
  display: inline-block; flex: none; white-space: nowrap;
}
.stamp-broken { color: var(--broken); } .stamp-flaky { color: var(--flaky-ink); }
.stamp-new { color: var(--paper-raised); background: var(--flaky-ink); border-color: var(--flaky-ink); }
.stamp-quiet { color: var(--ink-soft); transform: none; }
/* Every run gets a column that fits the row: a scrolling strip would hide the most
   recent runs, which is exactly where a newly broken test shows up. */
.row-heatmap {
  flex: 1 1 auto; min-width: 0; padding: 2px 0;
  display: grid; grid-template-columns: repeat(var(--runs, 1), minmax(0, 1fr)); column-gap: 1px;
}
.cell { height: 14px; border-radius: 1px; }
.s-pass { background: var(--pass); } .s-fail { background: var(--fail); }
.s-error { background: var(--error); } .s-skip { background: var(--skip); }
.s-missing { background: var(--missing); }
.s-recovered { background: var(--flaky); box-shadow: inset 0 -3px var(--pass); }
.s-unknown { background: repeating-linear-gradient(135deg, var(--ink-soft) 0 2px, var(--paper) 2px 4px); }
.row-rate { flex: 0 0 3.2rem; text-align: right; color: var(--ink-soft); }
/* A long history: a rail of passing runs, and a mark standing clear of it wherever a run
   did not pass, so a failure is read from its shape and not only from its colour. */
.row-strip { display: block; padding: 0; }
.strip { display: block; width: 100%; height: 16px; overflow: visible; }
.strip .r-pass { fill: var(--pass); opacity: 0.55; } .strip .r-skip { fill: var(--skip); }
.strip [class^="m-"] { stroke-width: 2px; vector-effect: non-scaling-stroke; }
.strip .m-fail { fill: var(--fail); stroke: var(--fail); }
.strip .m-error { fill: var(--error); stroke: var(--error); }
.strip .m-recovered { fill: var(--flaky); stroke: var(--flaky); }
.strip .m-unknown { fill: var(--ink-soft); stroke: var(--ink-soft); stroke-dasharray: 2 2; }
.strip .hit { fill: transparent; stroke: transparent; stroke-width: 9px; vector-effect: non-scaling-stroke; }
.row-count { flex-basis: 6.6rem; white-space: nowrap; }
.row-count b { color: var(--ink); font-weight: 600; margin-right: 0.5em; }
.axis {
  display: flex; align-items: flex-end; gap: 0.9rem; padding: 0.3rem 0.75rem 0.2rem;
  font-family: var(--font-mono); font-size: 0.68rem; color: var(--ink-soft);
  border-bottom: 1px solid var(--grid-line);
}
.axis-ticks { flex: 1 1 auto; min-width: 0; position: relative; height: 1.1rem; }
.axis-ticks span { position: absolute; bottom: 0; transform: translateX(-50%); white-space: nowrap; }
.axis-ticks span:first-child { transform: none; }
.axis-ticks span:last-child { transform: translateX(-100%); }
.healthy { border: 1px solid var(--grid-line); border-top: none; background: var(--paper-raised); font-size: 0.83rem; }
.healthy summary { cursor: pointer; padding: 0.6rem 0.75rem; color: var(--ink-soft); }
.healthy summary b { color: var(--healthy); font-family: var(--font-display); font-size: 1rem; margin-right: 0.2em; }
.healthy summary:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
.healthy-list {
  margin: 0; padding: 0.4rem 0.75rem 0.9rem; list-style: none; columns: 26rem auto; column-gap: 2rem;
  font-family: var(--font-mono); font-size: 0.74rem; overflow-wrap: anywhere;
}
.healthy-list li { padding: 0.12rem 0; break-inside: avoid; }
.healthy-list span { color: var(--ink-soft); white-space: nowrap; }
.healthy-list li:target { outline: 2px solid var(--accent); outline-offset: 2px; }
.detail h3 { font-size: 0.85rem; margin: 1.1rem 0 0.4rem; }
.scroll { overflow-x: auto; }
.scroll:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
table.failures { border-collapse: collapse; width: 100%; font-size: 0.78rem; }
table.failures th, table.failures td {
  text-align: left; vertical-align: top; padding: 0.4rem 0.9rem 0.4rem 0;
  border-bottom: 1px solid var(--grid-line); font-weight: normal;
}
table.failures thead th { color: var(--ink-soft); white-space: nowrap; }
table.failures tbody th { white-space: nowrap; }
table.failures code { font-family: var(--font-mono); }
.detail { padding: 0.7rem 1rem 1rem 2.4rem; background: var(--paper); font-size: 0.83rem; }
.test-identity { font-family: var(--font-mono); font-size: 0.85rem; margin: 0 0 0.65rem; }
.stat { display: flex; gap: 0.6rem; padding: 0.15rem 0; }
.stat-label { flex: 0 0 15rem; color: var(--ink-soft); }
.stat-value { font-family: var(--font-mono); min-width: 0; }
.detail, .warning, .meta-strip { overflow-wrap: anywhere; }
.evidence { border-left: 3px solid var(--flaky); padding: 0.1rem 1rem; margin: 0.8rem 0; background: var(--paper-raised); }
.evidence h4 { margin: 0.65rem 0; }
.evidence p { margin: 0.5rem 0; }
.evidence-note, .source { color: var(--ink-soft); }
.chronology-note { margin: 1.25rem 1.5rem 0; overflow-wrap: anywhere; }
.warning summary { cursor: pointer; }
.messages { margin: 0.2rem 0 0.6rem; padding-left: 1.2rem; font-family: var(--font-mono); font-size: 0.78rem; }
.prefix { margin: -0.4rem 0 0.8rem; font-size: 0.8rem; color: var(--ink-soft); }
.legend { display: flex; flex-wrap: wrap; gap: 1rem; padding: 0.9rem 0.1rem 0; font-size: 0.78rem; color: var(--ink-soft); align-items: center; }
.legend .cell { display: inline-block; width: 6px; vertical-align: middle; margin-right: 0.3em; }
.legend .key { display: inline-block; width: 14px; vertical-align: middle; margin-right: 0.4em; }
footer { padding: 2rem 1.5rem 0; font-size: 0.8rem; color: var(--ink-soft); }
footer a { color: var(--accent); }
@media (max-width: 900px) { .row-heatmap { column-gap: 0; } .cell { border-radius: 0; } }
@media (max-width: 600px) {
  .row summary { flex-wrap: wrap; gap: 0.5rem; }
  .row-name { flex: 1 1 70%; font-size: 0.7rem; }
  .row-heatmap { order: 3; flex-basis: 100%; }
  .row-count { flex-basis: auto; }
  .axis .row-name, .axis .row-rate { display: none; }
  table.failures { min-width: 34rem; }
  .stat { display: block; padding: 0.35rem 0; }
  .stat-label, .stat-value { display: block; }
  .detail { padding: 0.8rem; }
}
"""


# The report is one file with no script in it, and this has the browser hold it to that:
# nothing in it may run or be fetched, whatever a test's name or a failure message says.
# Test names and messages are escaped; the policy is for the day one is not.
_CSP = "default-src 'none'; style-src 'unsafe-inline'; img-src data:; base-uri 'none'; form-action 'none'"


def render_html(result: AnalysisResult, runs: list[Run], title: str = "flakemap report") -> str:
    """Render the full self-contained HTML report for `result` over `runs`."""
    runs, _ = order_runs(runs)
    order = {"broken": 0, "new": 1, "flaky": 2, "quiet": 3, "insufficient_data": 4, "healthy": 5}
    tests_ranked = sorted(result.tests, key=lambda t: (order[_state(t)], -t.flakiness_score))
    strips = len(runs) > MAX_CELL_RUNS
    healthy = [t for t in tests_ranked if t.classification == "healthy"]
    listed = healthy if len(healthy) > MAX_HEALTHY_ROWS else []
    drawn = tests_ranked[: len(tests_ranked) - len(listed)]
    matrix = _build_matrix(result, runs, {t.full_name for t in drawn})
    prefix = common_prefix([t.full_name for t in result.tests])
    test_anchors = {test.full_name: f"test-{index}" for index, test in enumerate(tests_ranked)}
    rows_html = (_axis(runs, result.ordering.available) if strips and drawn else "") + "".join(
        _test_row(t, runs, matrix, prefix, test_anchors[t.full_name], strips) for t in drawn
    )
    healthy_html = _healthy_list(listed, prefix, test_anchors) if listed else ""
    states = [_state(t) for t in result.tests]
    activity_tally = (
        f'<div class="tally-item tally-flaky"><b>{states.count("new")}</b>new flakes</div>'
        f'<div class="tally-item tally-na"><b>{states.count("quiet")}</b>flaky, now quiet</div>'
        if "new" in states or "quiet" in states
        else ""
    )
    if strips:
        legend = """<span><svg class="strip key" viewBox="0 0 10 16" preserveAspectRatio="none" aria-hidden="true"><rect class="r-pass" y="6" width="10" height="4"/></svg>pass</span>
    <span><svg class="strip key" viewBox="0 0 10 16" preserveAspectRatio="none" aria-hidden="true"><rect class="m-fail" x="4" width="2" height="16"/></svg>fail</span>
    <span><svg class="strip key" viewBox="0 0 10 16" preserveAspectRatio="none" aria-hidden="true"><rect class="m-error" x="4" width="2" height="16"/></svg>error</span>
    <span><svg class="strip key" viewBox="0 0 10 16" preserveAspectRatio="none" aria-hidden="true"><rect class="m-recovered" x="4" width="2" height="16"/></svg>passed on retry</span>
    <span><svg class="strip key" viewBox="0 0 10 16" preserveAspectRatio="none" aria-hidden="true"><rect class="r-skip" y="6" width="10" height="4"/></svg>skip</span>
    <span>A gap in the rail is a run without this test.</span>
    <span>Rates use the final outcome of each run; retry attempts do not increase the sample size.</span>
    <span>Rows sorted broken &rarr; new &rarr; flaky &rarr; quiet &rarr; insufficient data &rarr; healthy, then by score. Left to right is oldest to newest run. Click a row for its failures. Hover a mark for the run.</span>"""
    else:
        legend = """<span><span class="cell s-pass"></span>pass</span>
    <span><span class="cell s-recovered"></span>passed on retry</span>
    <span><span class="cell s-fail"></span>fail</span>
    <span><span class="cell s-error"></span>error</span>
    <span><span class="cell s-skip"></span>skip</span>
    <span><span class="cell s-missing"></span>not run</span>
    <span><span class="cell s-unknown"></span>unknown / excluded</span>
    <span>Rates use the final outcome of each run; retry attempts do not increase the sample size.</span>
    <span>Rows sorted broken &rarr; new &rarr; flaky &rarr; quiet &rarr; insufficient data &rarr; healthy, then by score. Columns are runs in chronological order. Click a row for detail. Hover a cell for the run.</span>"""
    prefix_html = (
        f'<p class="prefix">Tests under <code>{escape(prefix.rstrip("."))}</code></p>'
        if prefix
        else ""
    )
    if not result.ordering.available:
        legend = legend.replace(
            "Left to right is oldest to newest run.",
            "Left to right is display order only; chronology is unavailable.",
        )
        legend = legend.replace(
            "Columns are runs in chronological order.",
            "Columns are runs in display order only; chronology is unavailable.",
        )

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
        (
            '<details class="warning"><summary>'
            f"{len(result.warnings)} input / ordering warnings &mdash; inspect before using this report"
            "</summary><ul>"
            + "".join(f"<li>{escape(w)}</li>" for w in result.warnings)
            + "</ul></details>"
        )
        if result.warnings
        else ""
    )
    if not result.ordering.available:
        warning_html = (
            '<p class="evidence-note chronology-note"><b>Chronology unavailable.</b> Counts, retries and shared outcomes remain usable. Temporal conclusions require consistent run timestamps or sequences.</p>'
            + warning_html
        )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="{_CSP}">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
<style>{_CSS}{COFAILURE_CSS}</style>
</head>
<body>
<header class="masthead">
  <h1>flakemap &mdash; inspection report</h1>
  <p class="tagline">Test reliability across CI history, computed from JUnit, NUnit XML and TRX.</p>
  <div class="meta-strip">
    <span><b>runs</b> {count(result.total_runs)}</span>
    <span><b>tests</b> {count(len(result.tests))}</span>
    <span><b>run range</b> {escape(run_range)}</span>
    {ts_range}
  </div>
</header>
<main>
{warning_html}
<div class="tally">
  <div class="tally-item tally-broken"><b>{count(counts["broken"])}</b>broken</div>
  <div class="tally-item tally-flaky"><b>{count(counts["flaky"])}</b>flaky</div>
  {activity_tally}
  <div class="tally-item tally-healthy"><b>{count(counts["healthy"])}</b>healthy</div>
  <div class="tally-item tally-na"><b>{count(counts["insufficient_data"])}</b>insufficient data</div>
  <div class="tally-item tally-flaky"><b>{count(sum(t.recovered_runs for t in result.tests))}</b>test-runs passed on retry</div>
  <div class="tally-item tally-na"><b>{count(sum(t.n_unknown for t in result.tests))}</b>test-runs excluded</div>
</div>
{render_cofailure(result, test_anchors)}
<section class="heatmap">
  <h2>Test &times; run {"history" if strips else "heatmap"}</h2>
  {prefix_html}
  <div class="rows">{rows_html}</div>
  {healthy_html}
  <div class="legend">
    {legend}
  </div>
</section>
</main>
<footer>
  Generated by <a href="https://github.com/antonsoo/flakemap">flakemap</a>. Scoring formula and
  methodology: see the README. Pairs with <a href="https://github.com/antonsoo/logdelta">logdelta</a>
  for diffing the actual failing-run logs once you know which test to look at.
</footer>
</body>
</html>
"""
