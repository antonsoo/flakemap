"""Replay controlled mixed-zone CI histories through a chosen flakemap CLI.

Synthetic reports: 30 known instants, failures at indices 0/2/4, then 25 passes.
No collected production history or runner capture is implied. Each CLI runs in
UTC and again with a different host timezone; report mtimes are controlled.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

START = datetime(2026, 10, 13, tzinfo=timezone.utc)
PROFILES = (
    "aware-mixed",
    "aware-utc",
    "aware-quarter-offsets",
    "naive-mixed",
    "naive-one",
    "naive-with-sequence",
    "naive-with-report",
    "naive-with-trx",
    "naive-with-naive-report",
    "date-only",
    "missing-with-sequence",
    "report-only",
    "real-conflict",
    "invalid-with-sequence",
    "naive-renamed-mtimes",
)
UNAVAILABLE = {
    "naive-mixed",
    "naive-one",
    "naive-with-naive-report",
    "date-only",
    "real-conflict",
    "naive-renamed-mtimes",
}
SEQUENCED = {"naive-with-sequence", "missing-with-sequence", "invalid-with-sequence"}
REPORTED = {"naive-with-report", "naive-with-trx", "report-only"}


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def write_history(root: Path, profile: str) -> dict:
    root.mkdir(parents=True, exist_ok=False)
    truth = []
    for index in range(30):
        instant = START + (
            timedelta(days=index) if profile == "date-only" else timedelta(minutes=index)
        )
        offset = timedelta(hours=9 if index < 5 else 0)
        if profile == "aware-utc":
            offset = timedelta(0)
        elif profile == "aware-quarter-offsets":
            offset = timedelta(minutes=345 if index % 2 else -210)
        local = instant.astimezone(timezone(offset))
        timestamp = local.isoformat()
        if profile.startswith("naive") and (profile != "naive-one" or index == 0):
            timestamp = local.replace(tzinfo=None).isoformat()
        elif profile == "date-only":
            timestamp = instant.date().isoformat()
        elif profile == "invalid-with-sequence":
            timestamp = "not a timestamp"
        if profile == "aware-utc":
            timestamp = timestamp.replace("+00:00", "Z")
        metadata = {"run_id": f"run-{index:02}", "runner": "east" if index < 5 else "west"}
        if profile not in ("missing-with-sequence", "report-only"):
            metadata["timestamp"] = timestamp
        if profile in SEQUENCED or profile == "real-conflict":
            metadata["sequence"] = 29 - index if profile == "real-conflict" else index
        directory = (
            root / f"artifact-{29 - index if profile == 'naive-renamed-mtimes' else index:02}"
        )
        directory.mkdir()
        (directory / "meta.json").write_text(
            json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
        )
        failed = index in (0, 2, 4)
        if profile == "naive-with-trx":
            message = (
                "<Output><ErrorInfo><Message>upstream unavailable</Message></ErrorInfo></Output>"
                if failed
                else ""
            )
            report = directory / "results.trx"
            text = (
                '<TestRun xmlns="http://microsoft.com/schemas/VisualStudio/TeamTest/2010">'
                f'<Times start="{instant.isoformat()}"/>'
                '<TestDefinitions><UnitTest id="test-1" name="authorizes">'
                '<TestMethod className="Checkout" name="authorizes"/>'
                "</UnitTest></TestDefinitions><Results>"
                f'<UnitTestResult testId="test-1" testName="authorizes" outcome="{"Failed" if failed else "Passed"}">'
                f'{message}</UnitTestResult></Results><ResultSummary><Counters total="1" executed="1" '
                f'passed="{int(not failed)}" failed="{int(failed)}"/></ResultSummary></TestRun>'
            )
        else:
            report = directory / "results.xml"
            attribute = ""
            if profile in REPORTED:
                attribute = f' timestamp="{instant.isoformat()}"'
            elif profile == "naive-with-naive-report":
                attribute = f' timestamp="{instant.replace(tzinfo=None).isoformat()}"'
            message = '<failure message="upstream unavailable"/>' if failed else ""
            text = (
                f'<testsuite tests="1" failures="{int(failed)}"{attribute}>'
                f'<testcase classname="Checkout" name="authorizes">{message}</testcase></testsuite>'
            )
        report.write_text(text + "\n", encoding="utf-8")
        mtime = 1_700_000_000 + (29 - index if profile == "naive-renamed-mtimes" else index)
        os.utime(report, (mtime, mtime))
        truth.append(
            {
                "run_id": metadata["run_id"],
                "instant": instant.isoformat(),
                "outcome": "fail" if failed else "pass",
            }
        )
    manifest = {
        p.relative_to(root).as_posix(): sha(p.read_bytes())
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }
    return {
        "files": len(manifest),
        "tree_sha256": sha(canonical(manifest)),
        "truth_sha256": sha(canonical(truth)),
    }


def replay(python: str, work: Path) -> dict:
    work.mkdir(parents=True, exist_ok=False)
    artifacts = work / "html"
    artifacts.mkdir()
    rows = []
    for profile in PROFILES:
        root = work / profile
        inputs = write_history(root, profile)
        env = {**os.environ, "TZ": "UTC"}
        commands = {}
        payloads = {}
        for gate, host_tz in (
            ("new-flake", "UTC"),
            ("incomplete", "UTC"),
            ("new-flake", "Pacific/Honolulu"),
        ):
            label = gate if host_tz == "UTC" else "different-host-zone"
            command = [python, "-m", "flakemap", str(root), "--json", "--fail-on-" + gate]
            if label == "new-flake":
                command.extend(["--html", str(artifacts / (profile + ".html"))])
            result = subprocess.run(
                command, capture_output=True, text=True, env={**env, "TZ": host_tz}, timeout=60
            )
            if not result.stdout:
                raise RuntimeError(f"{profile}: {result.stderr}")
            payloads[label] = json.loads(result.stdout)
            commands[label] = {
                "exit": result.returncode,
                "report_sha256": sha(canonical(payloads[label])),
            }
        payload = payloads["new-flake"]
        (work / (profile + ".json")).write_text(
            json.dumps(payload, indent=2) + "\n", encoding="utf-8"
        )
        row = payload["tests"][0]
        summary = payload["summary"]
        warning = profile.startswith("naive") or profile in (
            "date-only",
            "invalid-with-sequence",
            "real-conflict",
        )
        available = profile not in UNAVAILABLE
        basis = "sequence" if profile in SEQUENCED else "timestamp" if available else "unavailable"
        expected = {
            "new_flake_exit": 0 if available else 2,
            "incomplete_exit": 2 if warning else 0,
            "ordering_available": available,
            "basis": basis,
            "activity": "quiet" if available else None,
        }
        runs = payload["cofailure"]["runs"]
        expected_source = (
            "report"
            if profile in REPORTED
            else "mtime"
            if profile in UNAVAILABLE - {"real-conflict", "naive-one"}
            else "sidecar"
        )
        sources = {run["metadata_source"] for run in runs}
        checks = {
            "new_flake_gate": commands["new-flake"]["exit"] == expected["new_flake_exit"],
            "incomplete_gate": commands["incomplete"]["exit"] == expected["incomplete_exit"],
            "ordering": summary["ordering"]["available"] == available
            and summary["ordering"]["basis"] == basis,
            "activity": (row["activity"]["state"] if row["activity"] else None)
            == expected["activity"],
            "silence": (row["activity"]["runs_since_last_failure"] if row["activity"] else None)
            == (25 if available else None),
            "counts": row["runs"] == {"total": 30, "pass": 27, "fail": 3, "skip": 0, "unknown": 0},
            "complete": summary["input_complete"] is not warning,
            "actionable_diagnostic": not (profile.startswith("naive") or profile == "date-only")
            or any("explicit UTC offset" in w for w in payload["warnings"]),
            "source": sources
            == ({"sidecar", "mtime"} if profile == "naive-one" else {expected_source}),
            "sequence_without_fabricated_time": profile not in SEQUENCED
            or all(run["timestamp"] is None for run in runs),
            "host_timezone_independent": commands["new-flake"] == commands["different-host-zone"],
            "same_report_for_both_gates": payloads["new-flake"] == payloads["incomplete"],
            "html_written": (artifacts / (profile + ".html")).is_file(),
        }
        rows.append(
            {
                "profile": profile,
                "inputs": inputs,
                "expected": expected,
                "commands": commands,
                "summary": summary,
                "activity": row["activity"],
                "counts": row["runs"],
                "run_order": [run["run_id"] for run in runs],
                "sources": sorted(sources),
                "warnings": payload["warnings"],
                "checks": checks,
                "agrees": all(checks.values()),
            }
        )
    return {
        "scope": "Synthetic histories through the real CLI, with controlled mtimes and two host timezones.",
        "python": subprocess.check_output([python, "--version"], text=True).strip(),
        "cases": len(rows),
        "cli_invocations": len(rows) * 3,
        "disagreements": sum(not row["agrees"] for row in rows),
        "results": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument(
        "--work",
        type=Path,
        required=True,
        help="New, nonexistent directory for reproducible inputs and reports",
    )
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    result = replay(args.python, args.work)
    print(json.dumps(result, indent=2))
    if args.check and result["disagreements"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
