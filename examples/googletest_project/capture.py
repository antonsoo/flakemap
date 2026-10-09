"""Run the compiled controlled GoogleTest fixture; retain unedited XML and stdout."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path)
    parser.add_argument("--output", type=Path, default=Path("examples/googletest_history"))
    parser.add_argument(
        "--controls", type=Path, default=Path("examples/googletest_project/captures")
    )
    args = parser.parse_args()
    executable = args.executable.resolve()
    records = []
    for number in range(1, 9):
        directory = args.output / f"run-{number:02d}"
        directory.mkdir(parents=True, exist_ok=True)
        report = directory / "report.xml"
        flags = ["--gtest_filter=-Execution.AFailFastTrigger"]
        # First run actually executes the disabled tests and fails. Seven
        # ordinary runs then suppress them; suppression cannot prove a repair.
        if number == 1:
            flags.append("--gtest_also_run_disabled_tests")
        result = subprocess.run(
            [str(executable), *flags, f"--gtest_output=xml:{report.resolve()}"],
            check=False,
            text=True,
            capture_output=True,
        )
        assert result.returncode == (1 if number == 1 else 0), result.stdout
        (directory / "stdout.txt").write_text(result.stdout + result.stderr)
        (directory / "meta.json").write_text(
            json.dumps({"sequence": number, "run_id": f"gtest-{number:02d}"}) + "\n"
        )
        records.append(
            {
                "file": str(report),
                "flags": flags,
                "exit_code": result.returncode,
                "sha256": hashlib.sha256(report.read_bytes()).hexdigest(),
            }
        )
    args.controls.mkdir(parents=True, exist_ok=True)
    report = args.controls / "failfast.xml"
    result = subprocess.run(
        [str(executable), "--gtest_fail_fast", f"--gtest_output=xml:{report.resolve()}"],
        check=False,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 1, result.stdout
    (args.controls / "failfast-stdout.txt").write_text(result.stdout + result.stderr)
    (args.controls / "capture.json").write_text(
        json.dumps(
            {
                "reporter": "GoogleTest 1.17.0",
                "archive_sha256": "65fab701d9829d38cb77c14acdc431d2108bfdbf8979e40eb8ae567edf10b27c",
                "history": records,
                "failfast_sha256": hashlib.sha256(report.read_bytes()).hexdigest(),
            },
            indent=2,
        )
        + "\n"
    )
    print(f"Captured {len(records)} history runs and a fail-fast control")


if __name__ == "__main__":
    main()
