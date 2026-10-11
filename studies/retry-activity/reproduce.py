"""Capture CLI activity/rate/gate results from an installed or source package."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from compose import histories

import flakemap.stats.activity
import flakemap.stats.analyze

HERE = Path(__file__).resolve().parent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    captured = {}
    for scenario, path in histories(args.work / "histories").items():
        command = [sys.executable, "-m", "flakemap", str(path)]
        result = subprocess.run(
            [*command, "--json", "--fail-on-new-flake"],
            capture_output=True,
            text=True,
            check=False,
        )
        data = json.loads(result.stdout)
        assert len(data["tests"]) == 1
        test = data["tests"][0]
        captured[scenario] = {
            "command": ["flakemap", f"<histories>/{scenario}", "--json", "--fail-on-new-flake"],
            "gate_exit_code": result.returncode,
            "gate_stderr": result.stderr,
            "summary": data["summary"],
            "test": {
                key: test.get(key)
                for key in (
                    "classification",
                    "runs",
                    "failure_rate",
                    "activity",
                    "activity_unavailable_reason",
                )
            },
            "recovered_runs": test["retries"]["recovered_runs"],
            "exhausted_runs": test["retries"]["exhausted_runs"],
            "warnings": data["warnings"],
        }
        for mode, suffix in (("--json", "json"), ("--markdown", "md")):
            r = subprocess.run([*command, mode], capture_output=True, text=True, check=False)
            assert r.returncode == 0
            (args.work / f"{scenario}.{suffix}").write_text(r.stdout)
        report = args.work / f"{scenario}.html"
        r = subprocess.run(
            [*command, "--html", str(report)], capture_output=True, text=True, check=False
        )
        assert r.returncode == 0
        (args.work / f"{scenario}.txt").write_text(r.stdout)
    # File names, not machine paths, identify the implementation being tested.
    modules = {
        name: hashlib.sha256((Path(flakemap.__file__).parent / name).read_bytes()).hexdigest()
        for name in ("stats/activity.py", "stats/analyze.py", "cli.py")
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps({"implementation_sha256": modules, "cases": captured}, indent=2) + "\n"
    )
    print(json.dumps(captured, indent=2))


if __name__ == "__main__":
    main()
