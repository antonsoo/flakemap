"""Replay real reports and explicitly damaged copies through the installed CLI.

Use a fresh --output directory. --check expects the revised completeness behavior.
Run this same script with an older package on PYTHONPATH to retain a before result.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]


def cases() -> list[tuple[str, str, bytes, bool]]:
    basic_path = "examples/junit_counters_project/captures/basic.xml"
    basic = (ROOT / basic_path).read_bytes()
    result = [("pytest-original", basic_path, basic, True)]

    for name in (
        "removed-failing-tests",
        "removed-outcome-markers",
        "stale-zero-counters",
        "parent-counter",
        "invalid-counter",
    ):
        root = ET.fromstring(basic)
        suite = root.find("testsuite")
        assert suite is not None
        if name == "removed-failing-tests":
            for case in list(suite.findall("testcase")):
                if case.find("failure") is not None or case.find("error") is not None:
                    suite.remove(case)
        elif name == "removed-outcome-markers":
            for case in suite.findall("testcase"):
                for marker in list(case):
                    if marker.tag in ("failure", "error"):
                        case.remove(marker)
        elif name == "stale-zero-counters":
            for key in ("tests", "failures", "errors", "skipped"):
                suite.set(key, "0")
        elif name == "parent-counter":
            root.set("tests", "5")
        else:
            suite.set("tests", "1e3")
        result.append((name, basic_path, ET.tostring(root, encoding="utf-8"), False))

    surefire_path = "examples/retry_history/surefire-001/report.xml"
    surefire = (ROOT / surefire_path).read_bytes()
    result.append(("surefire-attempts", surefire_path, surefire, True))
    root = ET.fromstring(surefire)
    retried = root.find("testcase[rerunFailure]")
    assert retried is not None
    marker = retried.find("rerunFailure")
    assert marker is not None
    retried.remove(marker)
    result.append(
        ("removed-retry-attempt", surefire_path, ET.tostring(root, encoding="utf-8"), False)
    )

    for name, path, complete in (
        ("googletest-disabled-executed", "examples/googletest_history/run-01/report.xml", True),
        ("googletest-disabled-suppressed", "examples/googletest_history/run-03/report.xml", True),
        ("jest-original", "tests/fixtures/jest_junit_real.xml", True),
        ("kubernetes-pruned", "tests/fixtures/kubernetes_pruned/junit_20260803-100711.xml", False),
        (
            "pytest-subtests-and-teardown",
            "examples/junit_counters_project/captures/complex.xml",
            False,
        ),
    ):
        result.append((name, path, (ROOT / path).read_bytes(), complete))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    results = []
    for name, source, raw, expected_complete in cases():
        folder = output / name
        folder.mkdir()
        (folder / "report.xml").write_bytes(raw)
        (folder / "meta.json").write_text('{"sequence": 1}\n', encoding="utf-8")
        command = ["-m", "flakemap", ".", "--json", "--fail-on-incomplete", "--html", "report.html"]
        run = subprocess.run(
            [sys.executable, *command], cwd=folder, capture_output=True, text=True, check=False
        )
        (folder / "analysis.json").write_text(run.stdout, encoding="utf-8")
        (folder / "stderr.txt").write_text(run.stderr, encoding="utf-8")
        payload = json.loads(run.stdout)
        results.append(
            {
                "case": name,
                "source": source,
                "source_sha256": hashlib.sha256((ROOT / source).read_bytes()).hexdigest(),
                "input_sha256": hashlib.sha256(raw).hexdigest(),
                "transformed": raw != (ROOT / source).read_bytes(),
                "command": ["python", *command],
                "exit": run.returncode,
                "expected_complete": expected_complete,
                "input_complete": payload["summary"]["input_complete"],
                "summary": payload["summary"],
                "warnings": payload["warnings"],
                "test_outcomes_sha256": hashlib.sha256(
                    json.dumps(payload["tests"], sort_keys=True).encode()
                ).hexdigest(),
            }
        )
        if args.check:
            assert payload["summary"]["input_complete"] == expected_complete, name
            assert run.returncode == (0 if expected_complete else 2), name
        print(f"{name}: complete={payload['summary']['input_complete']}, exit={run.returncode}")
    (output / "results.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
