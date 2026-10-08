"""Run flakemap over the collected build histories and record what it finds.

    uv run python studies/kubernetes-ci/analyze.py
    uv run python studies/kubernetes-ci/analyze.py --released /tmp/flakemap-0.3.7

Reads cache/<job>/ (see collect.py) through flakemap's own loader and analysis,
the same code the CLI runs, and writes results.json: how many builds failed,
what the other builds of the same commit say about each failure, which tests
the failures name, and where in the 91 days each test's failures fall.

`--released DIR` adds what a released version made of the same histories. DIR
holds `<job>.json` and, where one was written, `<job>.html`: that version's
`--json` and `--html` output (the README has the commands).
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any

from flakemap import __version__
from flakemap.loader import load_runs
from flakemap.report import render_html, to_json_dict
from flakemap.stats import analyze
from flakemap.stats.analyze import AnalysisResult, TestStats

HERE = Path(__file__).parent
# A test needs a handful of failures before where they fall says anything.
ENOUGH_FAILURES = 5
# A name read from failure text cannot be called new: the test may have been added the day it
# first failed. These are the ones that first failed in the last RECENT_DAYS and failed
# RECENT_FAILURES times or more; the study looks them up beside the frequent ones.
RECENT_DAYS = 30
RECENT_FAILURES = 3


def iso(moment: datetime | None) -> str | None:
    return moment.astimezone(timezone.utc).isoformat(timespec="minutes") if moment else None


def package(test: TestStats) -> str:
    """`[sig-x] k8s.io/a/b` + `c`, as the pruned report splits it, back to `k8s.io/a/b/c`."""
    path = test.full_name.split("] ", 1)[-1]
    head, _, tail = path.rpartition(".")
    return f"{head}/{tail}" if head else path


def longest_gap_days(failures: list[Any]) -> float | None:
    """Days from the end of one stretch of failing runs to the start of the next, at most."""
    streaks: list[list[Any]] = []
    for f in failures:
        if streaks and f.index == streaks[-1][-1].index + 1:
            streaks[-1].append(f)
        else:
            streaks.append([f])
    gaps = [
        (later[0].timestamp - earlier[-1].timestamp).total_seconds() / 86400
        for earlier, later in zip(streaks, streaks[1:], strict=False)
        if later[0].timestamp and earlier[-1].timestamp
    ]
    return round(max(gaps), 1) if gaps else None


def named_tests(result: AnalysisResult) -> list[dict[str, Any]]:
    """One row per test named inside a failing package, most failures first."""
    when = {run_id: md.timestamp for md in result.cofailure.runs for run_id in [md.run_id]}
    end = max(moment for moment in when.values() if moment)
    rows = []
    for test in result.tests:
        for named in test.named_failures:
            activity = named.activity
            mine = [
                f
                for f in test.failures
                if named.name in {name.split("/", 1)[0] for name in f.failed_within}
            ]
            failed_on = [iso(f.timestamp) for f in mine]
            gap_days = longest_gap_days(mine)
            rows.append(
                {
                    "package": package(test),
                    "test": named.name,
                    "failed_runs": named.runs,
                    "passed_same_commit": named.passed_same_commit,
                    "checked_same_commit": named.checked,
                    "state": activity.state,
                    "first_failure": iso(when.get(named.first_run_id)),
                    "first_failed_recently": bool(
                        named.runs >= RECENT_FAILURES
                        and (first := when.get(named.first_run_id))
                        and (end - first).days < RECENT_DAYS
                    ),
                    "last_failure": iso(when.get(named.last_run_id)),
                    "runs_since_last_failure": activity.runs_since_last,
                    "runs_since_first_failure": activity.runs_since_first,
                    "events": activity.events,
                    "span_days": round(
                        (mine[-1].timestamp - mine[0].timestamp).total_seconds() / 86400, 1
                    )
                    if mine[0].timestamp and mine[-1].timestamp
                    else None,
                    "longest_gap_days": gap_days,
                    "silence_days": round((end - mine[-1].timestamp).total_seconds() / 86400, 1)
                    if mine[-1].timestamp
                    else None,
                    "longest_gap_runs": activity.longest_gap,
                    "silence_ratio": None
                    if activity.silence_ratio is None
                    else round(activity.silence_ratio, 1),
                    "failure_times": failed_on,
                }
            )
    rows.sort(key=lambda row: (-row["failed_runs"], row["package"], row["test"]))
    return rows


def job_summary(job: str, manifest_rows: list[dict[str, Any]], cache: Path) -> dict[str, Any]:
    runs = load_runs(cache / job)
    result = analyze(runs)
    payload = to_json_dict(result)
    html = render_html(result, runs)

    results = Counter(row.get("result") or "no result" for row in manifest_rows)
    commits = Counter(run.metadata.commit for run in runs if run.metadata.commit)
    failed_runs = Counter(f.run_id for test in result.tests for f in test.failures)
    failures = [f for test in result.tests for f in test.failures]
    same_commit = Counter(f.same_commit for f in failures)
    named = named_tests(result)
    enough = [row for row in named if row["failed_runs"] >= ENOUGH_FAILURES]
    recent = [row for row in named if row["first_failed_recently"] and row not in enough]
    named_total = sum(row["failed_runs"] for row in named)
    states = Counter(
        test.activity.state
        for test in result.tests
        if test.classification == "flaky" and test.activity
    )
    timestamps = [run.metadata.timestamp for run in runs if run.metadata.timestamp]
    return {
        "job": job,
        "builds_listed": len(manifest_rows),
        "build_results": dict(sorted(results.items())),
        "runs_with_a_report": len(runs),
        "window": [iso(min(timestamps)), iso(max(timestamps))],
        "commits": len(commits),
        "commits_built_more_than_once": sum(1 for n in commits.values() if n > 1),
        "most_builds_of_one_commit": max(commits.values()),
        "testcases": len(result.tests),
        "outcomes": sum(test.n for test in result.tests),
        "runs_with_a_failing_testcase": len(failed_runs),
        "failing_testcases_per_failed_run": dict(sorted(Counter(failed_runs.values()).items())),
        "testcase_failures": len(failures),
        "same_commit": {
            "passed_in_another_run": same_commit["passed"],
            "failed_in_every_run": same_commit["failed"],
            "no_other_run": same_commit["single"],
        },
        "failed_in_every_run_of_commit": [
            {
                "testcase": package(test),
                "run_id": f.run_id,
                "time": iso(f.timestamp),
                "commit": f.commit,
                "runs_of_commit": f.same_commit_runs + 1,
                "named": [name for name in f.failed_within if "/" not in name],
            }
            for test in result.tests
            for f in test.failures
            if f.same_commit == "failed"
        ],
        "classification": {
            key: payload["summary"][key]
            for key in ("broken", "flaky", "healthy", "insufficient_data")
        },
        "flaky_by_activity": dict(sorted(states.items())),
        "named_tests": len(named),
        "named_tests_failed_once": sum(1 for row in named if row["failed_runs"] == 1),
        "top5_share_of_named_failures": round(
            sum(row["failed_runs"] for row in named[:5]) / named_total, 3
        ),
        f"named_tests_with_{ENOUGH_FAILURES}_failures": {
            "count": len(enough),
            "by_state": dict(sorted(Counter(row["state"] for row in enough).items())),
        },
        "quiet_among_enough": {
            "count": sum(row["state"] == "quiet" for row in enough),
            "median_days_first_to_last_failure": median(
                row["span_days"] for row in enough if row["state"] == "quiet"
            ),
            "median_days_since_last_failure": median(
                row["silence_days"] for row in enough if row["state"] == "quiet"
            ),
        },
        "named_tests_first_failed_recently": [row["test"] for row in recent],
        "tests": named,
        "report_bytes": {"html": len(html.encode()), "json": len(json.dumps(payload).encode())},
        "warnings": len(result.warnings),
    }


def released_summary(job: str, directory: Path) -> dict[str, Any] | None:
    """What another version's own JSON and HTML say about the same history."""
    report = directory / f"{job}.json"
    if not report.is_file():
        return None
    payload = json.loads(report.read_text())
    tests = payload["tests"]
    top = max(tests, key=lambda t: t["runs"]["fail"])
    summary: dict[str, Any] = {
        "classification": {
            key: payload["summary"][key]
            for key in ("broken", "flaky", "healthy", "insufficient_data")
        },
        "tests_with_a_change_point": sum(1 for t in tests if t["change_point"]),
        "most_failed_testcase": {
            "failed_runs": top["runs"]["fail"],
            "failure_messages": top["top_failure_messages"],
        },
        "json_bytes": report.stat().st_size,
    }
    page = directory / f"{job}.html"
    if page.is_file():
        summary["html_bytes"] = page.stat().st_size
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--manifest", type=Path, default=HERE / "manifest.json")
    parser.add_argument("--cache", type=Path, default=HERE / "cache")
    parser.add_argument("--released", type=Path, help="directory of another version's output")
    parser.add_argument("--released-version", default="0.3.7")
    parser.add_argument(
        "--released-summary",
        type=Path,
        default=HERE / "released-0.3.7.json",
        help="what --released recorded earlier, per job; used when --released is not given",
    )
    parser.add_argument("--out", type=Path, default=HERE / "results.json")
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text())
    results: dict[str, Any] = {
        "flakemap": __version__,
        "listed": manifest["listed"],
        "source": manifest["source"],
        "jobs": {},
    }
    for job, rows in manifest["jobs"].items():
        summary = job_summary(job, rows, args.cache)
        released = released_summary(job, args.released) if args.released else None
        if released:
            summary["released"] = {"version": args.released_version, **released}
        elif not args.released and args.released_summary.is_file():
            kept = json.loads(args.released_summary.read_text()).get(job)
            if kept:
                summary["released"] = kept
        results["jobs"][job] = summary
        same = summary["same_commit"]
        print(
            f"{job}: {summary['runs_with_a_report']} runs, "
            f"{summary['testcase_failures']} testcase failures "
            f"({same['passed_in_another_run']} passed on the same commit, "
            f"{same['failed_in_every_run']} failed in every run of it, "
            f"{same['no_other_run']} had no other run), "
            f"{summary['named_tests']} named tests"
        )
    args.out.write_text(json.dumps(results, indent=1) + "\n")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
