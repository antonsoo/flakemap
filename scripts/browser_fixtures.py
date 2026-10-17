#!/usr/bin/env python3
"""Render committed real-run histories plus explicitly synthetic boundary cases.

No test runner or network access is needed. Read scratch/browser/manifest.json
for fixture provenance and independently specified expected counts.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from build_demo_site import build

from flakemap.loader import load_runs
from flakemap.models import Run, RunMetadata, SourceLocation, Status, TestCaseResult
from flakemap.report import render_html, to_json_dict
from flakemap.stats import analyze

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "scratch" / "browser"


def cofailure_bounds() -> list[Run]:
    """Synthetic 22-cohort boundary fixture, not captured test execution."""
    runs = []
    hostile = '<img src="https://example.invalid/leak" onerror="alert(1)">' + "x" * 260
    for index in range(26):
        cases = []
        for member in range(25):
            cases.append(
                TestCaseResult(
                    hostile if member == 0 else f"shared_{member:02}",
                    "bounds",
                    Status.FAIL if index < 25 else Status.PASS,
                    message=hostile + " long failure message" * 60 if index < 25 else None,
                    source=SourceLocation(f"boundary-{index}.xml", len(cases) + 1),
                )
            )
        for group in range(21):
            for member in range(2):
                cases.append(
                    TestCaseResult(
                        f"group_{group:02}_{member}",
                        "bounds",
                        Status.FAIL if index == group else Status.PASS,
                        source=SourceLocation(f"boundary-{index}.xml", len(cases) + 1),
                    )
                )
        for member in range(2):
            cases.append(
                TestCaseResult(
                    f"ambiguous_{member}",
                    "bounds",
                    Status.UNKNOWN if index == 25 else Status.FAIL,
                    issue="synthetic contradictory outcome" if index == 25 else None,
                    source=SourceLocation(f"boundary-{index}.xml", len(cases) + 1),
                )
            )
        runs.append(Run(RunMetadata(f"run-{index:02}", sequence=index), cases, Path("synthetic")))
    return runs


def long_history() -> list[Run]:
    """Synthetic 1,200-run history in the shape of an hourly job, not captured execution.

    Forty tests that never fail (listed, not drawn) and six that do: a flake that
    stopped, one that just started, a steady one whose package-level record names the Go
    tests inside it, one skipped for a stretch, one that arrived late and errors, and one
    with an ambiguous outcome.
    """
    start = datetime(2026, 7, 9, tzinfo=timezone.utc)
    stopped, started = {40, 90, 91, 150, 230, 300}, {1130, 1160, 1190}
    steady = {i for i in range(60, 1200, 170)}
    runs = []
    for index in range(1200):
        cases = [
            TestCaseResult(f"TestSteady{n:02}", "example.com/pkg/ok", Status.PASS)
            for n in range(40)
        ]
        cases.append(
            TestCaseResult(
                "TestStopped",
                "example.com/pkg/a",
                Status.FAIL if index in stopped else Status.PASS,
                message="a_test.go:41: want 3 pods, got 2" if index in stopped else None,
            )
        )
        cases.append(
            TestCaseResult(
                "TestStarted",
                "example.com/pkg/a",
                Status.FAIL if index in started else Status.PASS,
                message='<img src=x onerror="alert(1)"> timed out' if index in started else None,
            )
        )
        cases.append(
            TestCaseResult(
                "scheduler",
                "[sig-x] example.com/pkg/integration",
                Status.FAIL if index in steady else Status.PASS,
                message="plugins_test.go:88: context deadline exceeded"
                if index in steady
                else None,
                failed_within=("TestPermit/sub", "TestPermit") if index in steady else (),
            )
        )
        cases.append(
            TestCaseResult(
                "TestSkippedForAWhile",
                "example.com/pkg/b",
                Status.SKIP if 400 <= index < 700 else Status.FAIL if index == 900 else Status.PASS,
            )
        )
        if index >= 800:
            cases.append(
                TestCaseResult(
                    "TestArrivedLate",
                    "example.com/pkg/b",
                    Status.ERROR if index in (950, 1100) else Status.PASS,
                )
            )
        cases.append(
            TestCaseResult(
                "TestAmbiguous",
                "example.com/pkg/b",
                Status.UNKNOWN if index == 600 else Status.PASS,
                issue="synthetic contradictory outcome" if index == 600 else None,
            )
        )
        runs.append(
            Run(
                RunMetadata(
                    f"build-{index:04}",
                    commit=f"c{index // 3:04}",
                    timestamp=start + timedelta(hours=index),
                    source="sidecar",
                ),
                cases,
                Path("synthetic"),
            )
        )
    return runs


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    fixtures = [
        ("retry", "examples/retry_history", 1, 6),
        ("googletest", "examples/googletest_history", 8, 5),
        ("history", "examples/demo_project/runs", 222, 12),
        ("trx", "examples/trx_history", 12, 6),
        ("trx-generics", "studies/trx-generics/native-capture/history", 12, 2),
        ("trx-generics-combined", "studies/trx-generics/native-capture/combined", 1, 4),
        ("incomplete", "examples/incomplete_history", 3, 6),
        ("cofailure", "examples/cofailure_history", 12, 6),
        ("cofailure-bounds", "synthetic boundary case in scripts/browser_fixtures.py", 26, 69),
        ("long", "synthetic long-history case in scripts/browser_fixtures.py", 1200, 46),
        ("ordering", "studies/ordering-evidence/captures", 40, 2),
    ]
    synthetic = {"cofailure-bounds": cofailure_bounds, "long": long_history}
    manifest = []
    for name, source, run_count, test_count in fixtures:
        runs = synthetic[name]() if name in synthetic else load_runs(ROOT / source)
        result = analyze(runs)
        payload = to_json_dict(result)
        assert len(runs) == run_count, (name, len(runs))
        assert len(result.tests) == test_count, (name, len(result.tests))
        (OUT / f"{name}.html").write_text(render_html(result, runs), encoding="utf-8")
        (OUT / f"{name}.json").write_text(
            json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8"
        )
        entry = {"name": name, "source": source, "runs": run_count, "tests": test_count}
        if name == "long":
            # Drawn as strips: six rows with marks, no cells, and forty names in a list.
            entry |= {"rows": 6, "cells": 0, "listed": 40}
        if name == "ordering":
            entry["chronology"] = False
        manifest.append(entry)
    for item in build(OUT / "gallery"):
        manifest.append({**item, "name": f"gallery/{item['name']}"})
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Rendered {len(manifest)} report fixtures in {OUT}")


if __name__ == "__main__":
    main()
