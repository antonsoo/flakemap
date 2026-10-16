"""Replay the CI-window counterexample with the active installed Flakemap."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import flakemap

HERE = Path(__file__).resolve().parent


def replay(history: Path, work: Path) -> dict[str, object]:
    if work.exists() and any(work.iterdir()):
        raise ValueError("replay work directory must be empty")
    work.mkdir(parents=True, exist_ok=True)
    # The prefix is the actual captured history as of build 35, before retirement.
    recent = work / "recent"
    recent.mkdir()
    for index in range(36):
        shutil.copytree(history / f"run-{index:02}", recent / f"run-{index:02}")
    results = {}
    for name, source, window in (
        ("retired", history, 10),
        ("outside_boundary", history, 25),
        ("inside_boundary", history, 26),
        ("recent", recent, 10),
    ):
        folder = work / name
        folder.mkdir(exist_ok=True)
        process = subprocess.run(
            [
                sys.executable,
                "-m",
                "flakemap",
                str(source),
                "--json",
                "--fail-on-incomplete",
                "--fail-on-new-flake",
                "--new-flake-window",
                str(window),
                "--html",
                str(folder / "report.html"),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        if process.returncode not in (0, 1):
            raise RuntimeError(f"{name}: {process.stderr}")
        (folder / "report.json").write_text(process.stdout, encoding="utf-8")
        payload = json.loads(process.stdout)
        tests = []
        for test in payload["tests"]:
            tests.append(
                {
                    key: test[key]
                    for key in (
                        "test",
                        "classification",
                        "runs",
                        "failure_rate",
                        "activity",
                        "first_failure_run_id",
                        "history_runs_since_first_failure",
                    )
                    if key in test
                }
            )
        exports = {}
        for kind, flag in (("terminal", []), ("markdown", ["--markdown"])):
            output = subprocess.run(
                [sys.executable, "-m", "flakemap", str(source), *flag],
                text=True,
                capture_output=True,
                check=True,
            )
            (folder / f"report.{kind}").write_text(output.stdout, encoding="utf-8")
            exports[kind] = hashlib.sha256(output.stdout.encode()).hexdigest()
        exports["html"] = hashlib.sha256((folder / "report.html").read_bytes()).hexdigest()
        results[name] = {
            "window": window,
            "exit": process.returncode,
            "total_runs": payload["summary"]["total_runs"],
            "warnings": payload["warnings"],
            "gate_message": "\n".join(
                line for line in process.stderr.splitlines() if "HTML report written" not in line
            ),
            "tests": tests,
            "exports_sha256": exports,
        }
    package = Path(flakemap.__file__).resolve().parent
    return {
        "package_version": flakemap.__version__,
        "package_location_kind": "site-packages" if "site-packages" in package.parts else "source",
        "implementation_sha256": {
            path: hashlib.sha256((package / path).read_bytes()).hexdigest()
            for path in ("cli.py", "stats/analyze.py", "report/json_out.py")
        },
        "scenarios": results,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history", type=Path, default=HERE / "fixtures/history")
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    receipt = replay(args.history.resolve(), args.work.resolve())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({name: item["exit"] for name, item in receipt["scenarios"].items()}))
