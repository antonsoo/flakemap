"""Synthetic CI histories with report times and sequence-only sidecars.

Run the actual CLI and retain its decision, ordering evidence and report hashes.
Use --source for a checkout, or omit it to exercise a separately installed wheel.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

START = datetime(2026, 10, 1, tzinfo=timezone.utc)
PLACEMENTS = ("same-report", "sibling-report", "run-directory")
PROFILES = ("contradictory", "consistent", "explicit-override")


def write_history(root: Path, kind: str, placement: str, profile: str) -> dict[str, str]:
    for index in range(30):
        directory = root / f"run-{index:02}"
        directory.mkdir(parents=True)
        instant = START + timedelta(minutes=index)
        sequence = index if profile == "consistent" else (index - 5) % 30
        failed = index in (0, 2, 4)
        if kind == "junit":
            primary = directory / "a.xml"
            outcome = '<failure message="upstream unavailable"/>' if failed else ""
            primary.write_text(
                f'<testsuite timestamp="{instant.isoformat()}" tests="1" failures="{int(failed)}">'
                f'<testcase classname="Checkout" name="authorizes">{outcome}</testcase></testsuite>',
                encoding="utf-8",
            )
        else:
            primary = directory / "a.trx"
            primary.write_text(
                '<TestRun xmlns="http://microsoft.com/schemas/VisualStudio/TeamTest/2010">'
                f'<Times start="{instant.isoformat()}"/>'
                '<TestDefinitions><UnitTest id="test-1"><TestMethod className="Checkout" '
                'name="authorizes"/></UnitTest></TestDefinitions><Results>'
                f'<UnitTestResult testId="test-1" testName="authorizes" '
                f'outcome="{"Failed" if failed else "Passed"}"/>'
                '</Results><ResultSummary><Counters total="1" executed="1" '
                f'passed="{int(not failed)}" failed="{int(failed)}"/></ResultSummary></TestRun>',
                encoding="utf-8",
            )
        sibling = directory / "b.xml"
        sibling.write_text(
            '<testsuite tests="1"><testcase classname="Support" name="control"/></testsuite>',
            encoding="utf-8",
        )
        metadata: dict[str, int | str] = {"sequence": sequence, "commit": f"commit-{index:02}"}
        if profile == "explicit-override":
            metadata["timestamp"] = (START + timedelta(minutes=sequence)).isoformat()
        target = {
            "same-report": primary.with_suffix(".meta.json"),
            "sibling-report": sibling.with_suffix(".meta.json"),
            "run-directory": directory / "meta.json",
        }[placement]
        target.write_text(json.dumps(metadata, sort_keys=True), encoding="utf-8")
        # Copy time intentionally disagrees; it must not supply chronology.
        for report in (primary, sibling):
            os.utime(report, (1_700_000_000 + 29 - index,) * 2)
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--artifacts", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    if args.source:
        env["PYTHONPATH"] = str(args.source.resolve() / "src")
    rows = []
    with TemporaryDirectory(prefix="flakemap-report-sequences-") as temporary:
        work = Path(temporary)
        artifacts = args.artifacts.resolve() if args.artifacts else work / "html"
        artifacts.mkdir(parents=True, exist_ok=True)
        for kind, placement, profile in itertools.product(("junit", "trx"), PLACEMENTS, PROFILES):
            name = f"{kind}-{placement}-{profile}"
            root = work / name
            manifest = write_history(root, kind, placement, profile)
            html = artifacts / f"{name}.html"
            command = [args.python, "-m", "flakemap", str(root), "--json", "--html", str(html)]
            run = subprocess.run(
                [*command, "--fail-on-new-flake"],
                env=env,
                text=True,
                capture_output=True,
                timeout=30,
            )
            report = json.loads(run.stdout)
            target = next(test for test in report["tests"] if test["test"] == "Checkout.authorizes")
            expected_exit = {"contradictory": 2, "consistent": 0, "explicit-override": 1}[profile]
            metadata = report["cofailure"]["runs"]
            row = {
                "case": name,
                "exit_code": run.returncode,
                "expected_exit_code": expected_exit,
                "ordering": report["summary"]["ordering"],
                "timestamp_range": report["summary"]["timestamp_range"],
                "activity": target["activity"],
                "runs": target["runs"],
                "metadata_sources": sorted({item["metadata_source"] for item in metadata}),
                "recorded_timestamps": sum(item["timestamp"] is not None for item in metadata),
                "warnings": report["warnings"],
                "stderr": run.stderr.replace(str(artifacts), "<html-artifacts>").replace(
                    str(work), "<study-work>"
                ),
                "html_sha256": hashlib.sha256(html.read_bytes()).hexdigest(),
                "input_tree_sha256": hashlib.sha256(
                    json.dumps(manifest, sort_keys=True).encode()
                ).hexdigest(),
            }
            if args.check:
                assert run.returncode == expected_exit, row
                assert row["recorded_timestamps"] == 30, row
                assert row["runs"] == {
                    "total": 30,
                    "pass": 27,
                    "fail": 3,
                    "skip": 0,
                    "unknown": 0,
                }, row
                if profile == "contradictory":
                    assert not row["ordering"]["available"] and row["activity"] is None, row
                else:
                    assert row["ordering"]["available"], row
                    assert row["activity"]["state"] == (
                        "quiet" if profile == "consistent" else "new"
                    ), row
            rows.append(row)
    print(
        json.dumps(
            {
                "cases": len(rows),
                "incorrect_gate_decisions": sum(
                    row["exit_code"] != row["expected_exit_code"] for row in rows
                ),
                "rows": rows,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
