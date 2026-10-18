"""Replay actual installed CLI commands against independent native XML verdicts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
STUDY = ROOT / "studies/nunit3"


def native(report: Path) -> dict[str, dict[str, int]]:
    # No production parser imports. Native fullnames are the complete join key.
    expected = {}
    for row in ET.parse(report).getroot().iter("test-case"):
        outcome = {"Passed": "pass", "Failed": "fail", "Skipped": "skip"}.get(
            row.get("result"), "unknown"
        )
        expected[row.get("fullname")] = {
            key: int(key == outcome) for key in ("pass", "fail", "skip", "unknown")
        }
    return expected


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--phase", required=True, choices=("before", "after"))
    args = parser.parse_args()
    output = args.output.absolute()
    output.mkdir(parents=True, exist_ok=True)
    interpreter = args.python.absolute()
    env = {**os.environ, "NO_COLOR": "1"}
    rows = []
    for capture in ("captured-v3", "captured-v4"):
        manifest = json.loads((STUDY / capture / "capture.json").read_text())
        for item in manifest["reports"]:
            name = f"{capture}-{item['scenario']}"
            source = STUDY / capture / item["scenario"]
            report = source / "Capture.xml"
            assert hashlib.sha256(report.read_bytes()).hexdigest() == item["retainedSha256"]
            expected = native(report)
            command = [
                str(interpreter),
                "-m",
                "flakemap",
                str(source),
                "--json",
                "--fail-on-incomplete",
            ]
            if capture == "captured-v4" and item["scenario"] in ("all", "teardown-filter"):
                command += ["--html", str(output / f"{name}.html")]
            run = subprocess.run(
                command, cwd=output, env=env, text=True, capture_output=True, check=False
            )
            result = json.loads(run.stdout)
            (output / f"{name}.json").write_text(run.stdout)
            if run.stderr:
                (output / f"{name}-stderr.txt").write_text(
                    run.stderr.replace(str(source), "<native-input>").replace(
                        str(output), "<replay-output>"
                    )
                )
            actual = {
                test["test"]: {
                    key: test["runs"][key] for key in ("pass", "fail", "skip", "unknown")
                }
                for test in result["tests"]
            }
            if args.phase == "before":
                assert run.returncode == 2 and not actual
            else:
                assert actual == expected, (name, actual, expected)
                expected_incomplete = item["scenario"] in (
                    "all",
                    "warning-filter",
                    "inconclusive-filter",
                    "teardown-filter",
                )
                assert run.returncode == (2 if expected_incomplete else 0), (
                    name,
                    run.returncode,
                    run.stderr,
                )
                assert bool(result["warnings"]) == expected_incomplete, (name, result["warnings"])
                assert (
                    result["summary"]["recovered_test_runs"]
                    == result["summary"]["exhausted_test_runs"]
                    == 0
                )
                assert result["cofailure"]["runs"][0]["metadata_source"] == "report"
            rows.append(
                {
                    "case": name,
                    "producerExit": item["processExit"],
                    "cliExit": run.returncode,
                    "nativeCases": len(expected),
                    "reportedCases": len(actual),
                    "identitiesAndCountsMatch": actual == expected,
                    "reported": actual,
                    "warnings": result["warnings"],
                }
            )
    receipt = {
        "phase": args.phase,
        "scope": "Actual CLI JSON and standalone HTML exports over compiled controlled NUnit 3.14.0 and 4.3.2 native reports. Independent XML fullnames/verdicts, not adapter console summaries, are the case oracle. No production reliability inference.",
        "cases": rows,
    }
    (output / "replay.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(
        json.dumps(
            {
                "phase": args.phase,
                "reports": len(rows),
                "nativeCases": sum(row["nativeCases"] for row in rows),
                "matchingReports": sum(row["identitiesAndCountsMatch"] for row in rows),
            }
        )
    )


if __name__ == "__main__":
    main()
