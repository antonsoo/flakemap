"""The `flakemap` command-line entry point."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from rich.console import Console

from flakemap import __version__
from flakemap.loader import load_runs
from flakemap.report import render_html, render_markdown, render_terminal, to_json_dict
from flakemap.stats import analyze


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="flakemap",
        description="Find the flaky tests in your CI history from JUnit XML reports.",
    )
    parser.add_argument("--version", action="version", version=f"flakemap {__version__}")
    parser.add_argument(
        "reports_dir", type=Path, help="directory to scan recursively for JUnit XML reports"
    )
    parser.add_argument(
        "--pattern", default="*.xml", help="glob pattern for report files (default: *.xml)"
    )

    output = parser.add_mutually_exclusive_group()
    output.add_argument(
        "--json", action="store_true", help="print the full analysis as JSON instead of a table"
    )
    output.add_argument(
        "--markdown",
        action="store_true",
        help="print a Markdown summary suitable for a PR comment instead of a table",
    )
    parser.add_argument(
        "--html", type=Path, metavar="PATH", help="write a self-contained HTML report"
    )
    parser.add_argument(
        "--top", type=int, default=20, help="max rows in the terminal table (default: 20)"
    )
    parser.add_argument(
        "--fail-on-new-flake",
        action="store_true",
        help=(
            "exit 1 if any test's most likely change-point falls within the last "
            "--new-flake-window runs and it is classified flaky or broken (CI gating)"
        ),
    )
    parser.add_argument(
        "--new-flake-window",
        type=int,
        default=10,
        metavar="N",
        help="how many trailing runs count as 'new' for --fail-on-new-flake (default: 10)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    console = Console()

    if not args.reports_dir.is_dir():
        console.print(f"[red]error:[/red] {args.reports_dir} is not a directory")
        return 2

    runs = load_runs(args.reports_dir, pattern=args.pattern)
    if not runs:
        console.print(
            f"[red]error:[/red] no report files matching '{args.pattern}' found under "
            f"{args.reports_dir}"
        )
        return 2

    parse_issues = [(r.metadata.run_id, w) for r in runs for w in r.warnings]
    if parse_issues and not args.json:
        shown = parse_issues[:5]
        for run_id, warning in shown:
            console.print(f"[yellow]warning:[/yellow] run '{run_id}': {warning}")
        if len(parse_issues) > len(shown):
            console.print(f"[yellow]warning:[/yellow] ({len(parse_issues) - len(shown)} more)")

    result = analyze(runs)

    if args.json:
        print(json.dumps(to_json_dict(result), indent=2))
    elif args.markdown:
        print(render_markdown(result), end="")
    else:
        render_terminal(result, console, top_n=args.top)

    if args.html:
        args.html.write_text(render_html(result, runs), encoding="utf-8")
        console.print(f"[dim]HTML report written to {args.html}[/dim]")

    if args.fail_on_new_flake:
        new_flakes = [
            t
            for t in result.tests
            if t.classification in ("flaky", "broken")
            and t.runs_since_change is not None
            and t.runs_since_change <= args.new_flake_window
        ]
        if new_flakes:
            names = ", ".join(t.full_name for t in new_flakes[:5])
            more = f" (+{len(new_flakes) - 5} more)" if len(new_flakes) > 5 else ""
            console.print(f"[bold red]new flake(s) detected:[/bold red] {names}{more}")
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
