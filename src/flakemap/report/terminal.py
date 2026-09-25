"""Rich terminal report: the default `flakemap` output."""

from __future__ import annotations

from rich.console import Console
from rich.table import Table
from rich.text import Text

from flakemap.report.names import common_prefix, short_name
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
    if result.mtime_fallback_warning:
        console.print(f"[yellow]warning:[/yellow] {result.mtime_fallback_warning}")
    console.print()

    ranked = [t for t in result.tests if t.classification in ("flaky", "broken")][:top_n]
    if not ranked:
        console.print("[green]No flaky or broken tests in this window.[/green]")
        return

    prefix = common_prefix([t.full_name for t in result.tests])
    title = f"Top {len(ranked)} by flakiness score"
    table = Table(
        title=title,
        caption=f"tests under {prefix.rstrip('.')}" if prefix else None,
        show_lines=False,
    )
    table.add_column("Test", overflow="fold", min_width=16, max_width=48, ratio=3)
    table.add_column("Status")
    table.add_column("Score", justify="right")
    table.add_column("Fail rate (95% CI)", justify="right")
    table.add_column("Flip rate", justify="right")
    table.add_column("Reruns", justify="right")
    table.add_column("Runs", justify="right")
    table.add_column("Since")

    for t in ranked:
        ci = f"{t.failure_rate.point:.0%} ({t.failure_rate.low:.0%}–{t.failure_rate.high:.0%})"
        reruns = (
            f"{t.rerun_commits_flaky}/{t.rerun_commits_total}" if t.rerun_commits_total else "-"
        )
        since = t.change_point_run_id or "-"
        table.add_row(
            short_name(t.full_name, prefix),
            _classification_cell(t),
            f"{t.flakiness_score:.2f}",
            ci,
            f"{t.flip_rate:.0%}",
            reruns,
            str(t.n),
            since,
        )
    console.print(table)
