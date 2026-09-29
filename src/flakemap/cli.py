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
        "--fail-on-retry",
        action="store_true",
        help="exit 1 if any test passed after explicit failed attempts in the supplied history",
    )
    parser.add_argument(
        "--fail-on-incomplete",
        action="store_true",
        help="exit 2 if input/ordering warnings or ambiguous outcomes make this report incomplete",
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
    errors = Console(stderr=True)
    if args.top < 1 or args.new_flake_window < 1:
        parser.error("--top and --new-flake-window must be positive")

    if not args.reports_dir.is_dir():
        errors.print(f"error: {args.reports_dir} is not a directory", style="red", markup=False)
        return 2

    runs = load_runs(args.reports_dir, pattern=args.pattern)
    if not runs:
        errors.print(
            f"error: no report files matching '{args.pattern}' found under {args.reports_dir}",
            style="red",
            markup=False,
        )
        return 2

    result = analyze(runs)

    if args.json:
        print(json.dumps(to_json_dict(result), indent=2, allow_nan=False))
    elif args.markdown:
        print(render_markdown(result), end="")
    else:
        render_terminal(result, console, top_n=args.top)

    if args.html:
        try:
            args.html.write_text(render_html(result, runs), encoding="utf-8")
        except OSError as exc:
            errors.print(f"error writing HTML report: {exc}", style="red", markup=False)
            return 2
        errors.print(f"HTML report written to {args.html}", style="dim", markup=False)

    if not any(t.n for t in result.tests):
        errors.print("error: no usable pass/fail/error observations", style="red")
        return 2
    if args.fail_on_incomplete and result.warnings:
        errors.print("error: incomplete report; inspect the reported warnings", style="red")
        return 2
    if args.fail_on_retry and any(t.recovered_runs for t in result.tests):
        errors.print("passed-on-retry tests detected in the supplied history", style="red")
        return 1

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
            errors.print(f"new flake(s) detected: {names}{more}", style="bold red", markup=False)
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
