"""Markdown output sized for a PR comment: a compact top-N table."""

from __future__ import annotations

from html import escape

from flakemap.report.names import visible
from flakemap.report.numbers import count, interval, of, percent
from flakemap.report.terminal import (
    activity_state,
    last_failed,
    named_failures,
    same_commit_cell,
    triage_order,
)
from flakemap.stats.analyze import AnalysisResult, TestStats

_BADGE = {
    "broken": "🔴 broken",
    "flaky": "🟡 flaky",
    "healthy": "🟢 healthy",
    "insufficient_data": "⚪ n/a",
}


def _safe(text: str) -> str:
    return (
        escape(visible(text))
        .replace("|", "&#124;")
        .replace("`", "&#96;")
        .replace("\n", " ")
        .replace("\r", " ")
    )


def _row(t: TestStats) -> str:
    ci = interval(t.failure_rate.low, t.failure_rate.high)
    since = f" since <code>{_safe(t.change_point_run_id)}</code>" if t.change_point_run_id else ""
    state = activity_state(t)
    badge = _BADGE[t.classification] + (f", {state}" if state else "")
    name = f"<code>{_safe(t.full_name)}</code>"
    for line in named_failures(t):
        name += f"<br>&nbsp;&nbsp;{_safe(line)}"
    last = last_failed(t.activity.runs_since_last) if t.activity else "n/a"
    return (
        f"| {name} | {badge} | {of(t.n_fail, t.n)}{since} "
        f"| {percent(t.failure_rate.point)} ({ci}) | {same_commit_cell(t)} | {last} "
        f"| {count(t.recovered_runs)} |"
    )


def _cofailure_summary(result: AnalysisResult) -> list[str]:
    groups = result.cofailure.groups
    if not groups:
        return []
    lines = [
        "## Tests that fail together",
        "",
        "Exact matching outcomes and coverage; shared history does not establish a cause.",
        "",
        "| Members | Final-failure runs | Recovered runs |",
        "|---|---|---|",
    ]
    for group in groups[:5]:
        names = [f"<code>{_safe(name)}</code>" for name in group.tests[:3]]
        if len(group.tests) > 3:
            names.append(f"+ {len(group.tests) - 3} more tests")
        failed = set(group.states["failed"] + group.states["exhausted"])
        failed_ids = [md.run_id for md in result.cofailure.runs if md.run_id in failed]
        cells = ["<br>".join(names)]
        for ids in (failed_ids, list(group.states["recovered"])):
            label = ", ".join(f"<code>{_safe(run_id)}</code>" for run_id in ids[:5]) or "none"
            if len(ids) > 5:
                label += f" (+ {len(ids) - 5} more)"
            cells.append(label)
        lines.append("| " + " | ".join(cells) + " |")
    lines.extend(
        [
            "",
            f"Showing {min(len(groups), 5)} of {len(groups)} cohorts. "
            "Use `--html` or `--json` for all members, run states and source evidence.",
            "",
        ]
    )
    if result.cofailure.excluded_tests:
        lines.extend(
            [
                f"{len(result.cofailure.excluded_tests)} tests have ambiguous outcomes "
                "and are excluded from grouping.",
                "",
            ]
        )
    return lines


def render_markdown(result: AnalysisResult, top_n: int = 15) -> str:
    lines = ["# flakemap report", ""]
    lines.append(
        f"{result.total_runs} runs analyzed, {len(result.tests)} tests seen. "
        f"{sum(1 for t in result.tests if t.classification == 'flaky')} flaky, "
        f"{sum(1 for t in result.tests if t.classification == 'broken')} broken."
    )
    lines.append(
        f"{sum(t.recovered_runs for t in result.tests)} test-runs passed on retry; "
        f"{sum(t.n_unknown for t in result.tests)} ambiguous test-runs excluded."
    )
    if not result.ordering.available:
        lines.append(
            "\n**Chronology unavailable.** Temporal statistics are omitted. "
            "Counts, retries and same-commit comparisons remain usable."
        )
    states = [activity_state(t) for t in result.tests]
    if any(states):
        lines.append(
            f"Of the flaky tests, {states.count('new')} are new and {states.count('quiet')} "
            "have gone quiet."
        )
    for warning in result.warnings:
        lines.append(f"\n> Warning: {_safe(warning)}")
    lines.append("")
    lines.extend(_cofailure_summary(result))

    notable = triage_order(result.tests)[:top_n]
    if not notable:
        lines.append("No flaky or broken tests detected in this window.")
        return "\n".join(lines) + "\n"

    if result.cofailure.groups:
        lines.extend(["## Individual tests", ""])
    lines.append(
        "| Test | Status | Failed runs | Final failure rate (95% CI) "
        "| Passed on same commit | Last failed | Recovered |"
    )
    lines.append("|---|---|---|---|---|---|---|")
    for t in notable:
        lines.append(_row(t))
    lines.append("")
    lines.append(
        "*Passed on same commit: of the failures with another run of the same commit, the "
        "ones that passed there. Recovered counts runs that passed after explicit failed "
        "attempts. New and quiet say where the failures fall in the history; rows are "
        "ordered by flakiness score, quiet tests last. See the README's formula section. "
        "Generated by [flakemap](https://github.com/antonsoo/flakemap).*"
    )
    return "\n".join(lines) + "\n"
