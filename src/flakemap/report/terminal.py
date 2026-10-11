"""Rich terminal report: the default `flakemap` output."""

from __future__ import annotations

from rich.console import Console
from rich.table import Table
from rich.text import Text

from flakemap.report.names import common_prefix, short_name, visible
from flakemap.report.numbers import count, interval, of, percent
from flakemap.stats.analyze import AnalysisResult, TestStats

_STYLE = {
    "broken": "bold red",
    "flaky": "bold yellow",
    "healthy": "green",
    "insufficient_data": "dim",
}
_LABEL = {
    "broken": "broken",
    "flaky": "flaky",
    "healthy": "healthy",
    "insufficient_data": "n/a",
}


def activity_state(t: TestStats) -> str | None:
    """`new` or `quiet` for a flaky test whose failures say so; None otherwise."""
    if t.classification != "flaky" or t.activity is None or t.activity.state == "ongoing":
        return None
    return t.activity.state


def triage_order(tests: list[TestStats]) -> list[TestStats]:
    """Flaky and broken tests, the ones that have gone quiet last; by score within each."""
    notable = [t for t in tests if t.classification in ("flaky", "broken")]
    return sorted(notable, key=lambda t: (activity_state(t) == "quiet", -t.flakiness_score))


def _classification_cell(t: TestStats) -> Text:
    state = activity_state(t)
    if state == "quiet":
        return Text("flaky, quiet", style="yellow dim")
    label = _LABEL[t.classification] + (f", {state}" if state else "")
    return Text(label, style=_STYLE[t.classification])


def last_failed(runs_since_last: int) -> str:
    if runs_since_last == 0:
        return "latest run"
    return f"{count(runs_since_last)} run{'s' if runs_since_last != 1 else ''} ago"


def same_commit_cell(t: TestStats) -> str:
    """Of this test's failures with another run of the same commit, how many passed there."""
    if not t.failures_checked:
        return "-"
    return of(t.failures_passed_same_commit, t.failures_checked)


def named_failures(t: TestStats, limit: int = 3) -> list[str]:
    """The tests a rolled-up testcase's failures name, most frequent first."""
    shown = []
    for named in t.named_failures[:limit]:
        line = f"{visible(named.name)} ×{named.runs}"
        if named.activity is None:
            line += ", chronology unavailable"
        elif named.activity.state == "quiet":
            line += f", quiet for {count(named.activity.runs_since_last)} runs"
        else:
            line += f", first failed {count(named.activity.runs_since_first)} runs ago"
        shown.append(line)
    if len(t.named_failures) > limit:
        shown.append(f"+ {len(t.named_failures) - limit} more")
    return shown


def _cofailure_summary(result: AnalysisResult, console: Console) -> None:
    groups = result.cofailure.groups
    if not groups:
        return
    console.print("[bold]Tests that fail together[/bold]")
    console.print(
        "Exact matching outcomes and coverage; shared history does not establish a cause."
    )
    prefix = (
        common_prefix([name for group in groups for name in group.tests])
        if console.is_terminal
        else ""
    )
    table = Table(
        show_lines=True,
        caption=Text(f"tests under {visible(prefix.rstrip('.'))}") if prefix else None,
    )
    table.add_column("Members", overflow="fold", ratio=3)
    table.add_column("Final-failure runs", overflow="fold", ratio=2)
    table.add_column("Recovered runs", overflow="fold", ratio=2)
    for group in groups[:5]:
        names = [visible(short_name(name, prefix)) for name in group.tests[:3]]
        if len(group.tests) > 3:
            names.append(f"+ {len(group.tests) - 3} more tests")
        failed = set(group.states["failed"] + group.states["exhausted"])
        failed_ids = [md.run_id for md in result.cofailure.runs if md.run_id in failed]
        cells = [Text("\n".join(names))]
        for ids in (failed_ids, list(group.states["recovered"])):
            label = ", ".join(visible(run_id) for run_id in ids[:5]) or "none"
            if len(ids) > 5:
                label += f" (+ {len(ids) - 5} more)"
            cells.append(Text(label))
        table.add_row(*cells)
    console.print(table)
    console.print(
        f"Showing {min(len(groups), 5)} of {len(groups)} cohorts. "
        "Use --html or --json for all members, run states and source evidence."
    )
    if result.cofailure.excluded_tests:
        console.print(
            f"{len(result.cofailure.excluded_tests)} tests have ambiguous outcomes "
            "and are excluded from grouping."
        )
    console.print()


def render_terminal(result: AnalysisResult, console: Console, top_n: int = 20) -> None:
    """Print the human-facing report: a summary line plus a ranked table."""
    flaky = sum(1 for t in result.tests if t.classification == "flaky")
    broken = sum(1 for t in result.tests if t.classification == "broken")
    healthy = sum(1 for t in result.tests if t.classification == "healthy")
    insufficient = sum(1 for t in result.tests if t.classification == "insufficient_data")

    console.print(
        f"[bold]flakemap[/bold]  {result.total_runs} runs, {len(result.tests)} tests  "
        f"|  [bold red]{broken} broken[/bold red]  [bold yellow]{flaky} flaky[/bold yellow]  "
        f"[green]{healthy} healthy[/green]  [dim]{insufficient} insufficient data[/dim]"
    )
    recovered = sum(t.recovered_runs for t in result.tests)
    excluded = sum(t.n_unknown for t in result.tests)
    console.print(
        f"{recovered} test-runs passed on retry; {excluded} ambiguous test-runs excluded."
    )
    if not result.ordering.available:
        console.print(
            "Chronology unavailable: temporal statistics are omitted. Counts, retries and same-commit comparisons remain usable.",
            style="yellow",
        )
    states = [activity_state(t) for t in result.tests]
    if any(states):
        console.print(
            f"Of the flaky tests, {states.count('new')} new and {states.count('quiet')} quiet "
            "(no failure for three times the longest spell between failures, or a first failure after as long)."
        )
    for warning in result.warnings[:5]:
        console.print(Text(f"warning: {visible(warning)}", style="yellow"))
    if len(result.warnings) > 5:
        console.print(
            f"[yellow]{len(result.warnings) - 5} more warnings; see JSON or HTML.[/yellow]"
        )
    console.print()
    _cofailure_summary(result, console)

    ranked = triage_order(result.tests)[:top_n]
    if not ranked:
        console.print("No flaky or broken tests detected in the usable observations.")
        return

    prefix = common_prefix([t.full_name for t in result.tests])
    title = f"Top {len(ranked)} by flakiness score"
    if any(activity_state(t) == "quiet" for t in ranked):
        title += ", quiet tests last"
    checked = any(t.failures_checked for t in ranked)
    retried = any(t.recovered_runs for t in ranked)
    changed = any(t.change_point_run_id for t in ranked)
    table = Table(
        title=title,
        caption=Text(f"tests under {visible(prefix.rstrip('.'))}") if prefix else None,
        show_lines=False,
    )
    # In a terminal the name column is capped, so a long name folds and the numbers stay in
    # view. Written to a pipe, each name stays on one line, where a search can find it.
    name_cap = max(48, console.width - 78) if console.is_terminal else None
    table.add_column("Test", overflow="fold", min_width=16, max_width=name_cap, ratio=3)
    table.add_column("Status")
    table.add_column("Failed runs", justify="right")
    table.add_column("Final fail (95% CI)", justify="right")
    # 80 columns hold the counts and the rate; 110 add the evidence columns; the flip
    # rate, which the rate already implies for a steady flake, waits for 140.
    wide = console.width >= 110
    wider = console.width >= 140
    if wider:
        table.add_column("Flip rate", justify="right")
    if wide and checked:
        table.add_column("Passed on\nsame commit", justify="right")
    if wide:
        table.add_column("Last failed", justify="right")
    if retried:
        table.add_column("Recovered", justify="right")
    if wide and changed:
        table.add_column("Since")

    for t in ranked:
        ci = (
            f"{percent(t.failure_rate.point)} ({interval(t.failure_rate.low, t.failure_rate.high)})"
        )
        since = t.change_point_run_id or "-"
        name = Text(visible(short_name(t.full_name, prefix)))
        for line in named_failures(t):
            name.append(f"\n  {line}", style="dim")
        cells: list[str | Text] = [name, _classification_cell(t), of(t.n_fail, t.n), ci]
        if wider:
            cells.append(percent(t.flip_rate) if t.flip_pairs else "-")
        if wide and checked:
            cells.append(same_commit_cell(t))
        if wide:
            cells.append(last_failed(t.activity.runs_since_last) if t.activity else "-")
        if retried:
            cells.append(count(t.recovered_runs))
        if wide and changed:
            cells.append(Text(visible(since)))
        table.add_row(*cells)
    console.print(table)
    if wide and checked:
        console.print(
            "[dim]Passed on same commit = of the failures that have another run of the same "
            "commit, the ones that passed there: the same code, a different result.[/dim]"
        )
    if any(t.named_failures for t in ranked):
        console.print(
            "[dim]Indented names are the tests a testcase's own failure output names, "
            "with the number of runs each failed in.[/dim]"
        )
    if recovered:
        console.print(
            "[dim]Recovered = passed after explicit failed attempts. Final failure rate counts each run once. Use --html or --json for retry evidence.[/dim]"
        )
