#!/usr/bin/env python3
"""Render committed real-run histories plus explicitly synthetic boundary cases.

No test runner or network access is needed. Read scratch/browser/manifest.json
for fixture provenance and independently specified expected counts.
"""

from __future__ import annotations

import json
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


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    fixtures = [
        ("retry", "examples/retry_history", 1, 6),
        ("history", "examples/demo_project/runs", 222, 12),
        ("trx", "examples/trx_history", 12, 6),
        ("incomplete", "examples/incomplete_history", 3, 6),
        ("cofailure", "examples/cofailure_history", 12, 6),
        ("cofailure-bounds", "synthetic boundary case in scripts/browser_fixtures.py", 26, 69),
    ]
    manifest = []
    for name, source, run_count, test_count in fixtures:
        runs = cofailure_bounds() if name == "cofailure-bounds" else load_runs(ROOT / source)
        result = analyze(runs)
        payload = to_json_dict(result)
        assert len(runs) == run_count, (name, len(runs))
        assert len(result.tests) == test_count, (name, len(result.tests))
        (OUT / f"{name}.html").write_text(render_html(result, runs), encoding="utf-8")
        (OUT / f"{name}.json").write_text(
            json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8"
        )
        manifest.append({"name": name, "source": source, "runs": run_count, "tests": test_count})
    for item in build(OUT / "gallery"):
        manifest.append({**item, "name": f"gallery/{item['name']}"})
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Rendered {len(manifest)} report fixtures in {OUT}")


if __name__ == "__main__":
    main()
