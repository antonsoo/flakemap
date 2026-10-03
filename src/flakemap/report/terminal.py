"""Rich terminal report: the default `flakemap` output."""

from __future__ import annotations

from rich.console import Console
from rich.table import Table
from rich.text import Text

from flakemap.report.names import common_prefix, short_name, visible
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


def _classification_cell(t: TestStats) -> Text:
    return Text(_LABEL[t.classification], style=_STYLE[t.classification])


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
    for warning in result.warnings[:5]:
        console.print(Text(f"warning: {visible(warning)}", style="yellow"))
    if len(result.warnings) > 5:
        console.print(
            f"[yellow]{len(result.warnings) - 5} more warnings; see JSON or HTML.[/yellow]"
        )
    console.print()

    ranked = [t for t in result.tests if t.classification in ("flaky", "broken")][:top_n]
    if not ranked:
        console.print("No flaky or broken tests detected in the usable observations.")
        return

    prefix = common_prefix([t.full_name for t in result.tests])
    title = f"Top {len(ranked)} by flakiness score"
    table = Table(
        title=title,
        caption=Text(f"tests under {visible(prefix.rstrip('.'))}") if prefix else None,
        show_lines=False,
    )
    # In a terminal the name column is capped, so a long name folds and the numbers stay in
    # view. Written to a pipe, each name stays on one line, where a search can find it.
    name_cap = 48 if console.is_terminal else None
    table.add_column("Test", overflow="fold", min_width=16, max_width=name_cap, ratio=3)
    table.add_column("Status")
    table.add_column("Score", justify="right")
    table.add_column("Final fail (95% CI)", justify="right")
    wide = console.width >= 110
    if wide:
        table.add_column("Flip rate", justify="right")
    table.add_column("Recovered", justify="right")
    table.add_column("Runs", justify="right")
    if wide:
        table.add_column("Since")

    for t in ranked:
        ci = f"{t.failure_rate.point:.0%} ({t.failure_rate.low:.0%}–{t.failure_rate.high:.0%})"
        since = t.change_point_run_id or "-"
        cells: list[str | Text] = [
            Text(visible(short_name(t.full_name, prefix))),
            _classification_cell(t),
            f"{t.flakiness_score:.2f}",
            ci,
        ]
        if wide:
            cells.append(f"{t.flip_rate:.0%}" if t.flip_pairs else "-")
        cells.extend([str(t.recovered_runs), str(t.n)])
        if wide:
            cells.append(Text(visible(since)))
        table.add_row(*cells)
    console.print(table)
    if recovered:
        console.print(
            "[dim]Recovered = passed after explicit failed attempts. Final failure rate counts each run once. Use --html or --json for retry evidence.[/dim]"
        )
