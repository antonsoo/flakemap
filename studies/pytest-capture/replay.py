"""Run an installed capture plugin against real pytest and independent side effects.

Usage: python studies/pytest-capture/replay.py INSTALLED_PYTHON OUTPUT_DIRECTORY
No source checkout is put on the producer's Python path.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from xml.etree import ElementTree as ET

PYTHON = str(Path(sys.argv[1]).absolute())  # Preserve a venv's interpreter symlink.
OUTPUT = Path(sys.argv[2]).resolve()
if OUTPUT.exists() and any(OUTPUT.iterdir()):
    raise SystemExit(
        "Choose an empty output directory; execution ledgers must not mix invocations."
    )
OUTPUT.mkdir(parents=True, exist_ok=True)
SOURCE = Path(__file__).parent / "native/test_retries.py"
ENV = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
ENV.update(PYTEST_DISABLE_PLUGIN_AUTOLOAD="1", PYTEST_ADDOPTS="")


def run(arguments: list[str], directory: Path, expected: int, name: str) -> str:
    result = subprocess.run(
        [PYTHON, *arguments], cwd=directory, env=ENV, capture_output=True, text=True, timeout=60
    )
    (directory / f"{name}.stdout.txt").write_text(result.stdout)
    (directory / f"{name}.stderr.txt").write_text(result.stderr)
    assert result.returncode == expected, (name, result.returncode, result.stdout, result.stderr)
    return result.stdout


def ordinary_fingerprint(path: Path) -> list[object]:
    # Retain outcomes and messages; exclude only measured duration and suite clock.
    return [
        {
            "classname": case.get("classname"),
            "name": case.get("name"),
            "markers": [ET.tostring(child, encoding="unicode") for child in case],
        }
        for case in ET.parse(path).iter("testcase")
    ]


versions = json.loads(
    run(
        [
            "-c",
            "import json, platform, importlib.metadata as m; print(json.dumps({'python':platform.python_version(), **{p:m.version(p) for p in ['flakemap','pytest','pytest-rerunfailures','pytest-xdist']}}))",
        ],
        OUTPUT,
        0,
        "versions",
    )
)
runtime = json.loads(
    run(
        [
            "-c",
            "import json, hashlib, pathlib, flakemap.pytest_plugin as p, flakemap.parse.junit as j; print(json.dumps({name:hashlib.sha256(pathlib.Path(mod.__file__).read_bytes()).hexdigest() for name, mod in [('pytest_plugin.py',p),('parse/junit.py',j)]}))",
        ],
        OUTPUT,
        0,
        "runtime",
    )
)
summary: dict[str, object] = {
    "versions": versions,
    "runtimeSha256": runtime,
    "fixtureSha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
    "runs": [],
}
for workers in (0, 2):
    directory = OUTPUT / ("serial" if workers == 0 else "parallel")
    directory.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SOURCE, directory / "test_retries.py")
    baseline, captured = directory / "ordinary", directory / "captured"
    baseline.mkdir(exist_ok=True)
    captured.mkdir(exist_ok=True)
    common = ["-m", "pytest", "test_retries.py", "-p", "rerunfailures", "--reruns", "2", "-q"]
    if workers:
        common += ["-p", "xdist.plugin", "-n", str(workers)]
    ENV["FLAKEMAP_EXECUTION_LOG"] = str(directory / "baseline-ledger")
    run([*common, "--junitxml=ordinary/report.xml"], directory, 1, "ordinary-producer")
    ENV["FLAKEMAP_EXECUTION_LOG"] = str(directory / "capture-ledger")
    run(
        [
            *common,
            "-p",
            "flakemap.pytest_plugin",
            "--flakemap-xml=captured/report.xml",
            "--junitxml=captured-ordinary.xml",
        ],
        directory,
        1,
        "capture-producer",
    )
    before = ordinary_fingerprint(baseline / "report.xml")
    after = ordinary_fingerprint(directory / "captured-ordinary.xml")
    assert sorted(before, key=lambda d: json.dumps(d, sort_keys=True)) == sorted(
        after, key=lambda d: json.dumps(d, sort_keys=True)
    ), "companion plugin changed ordinary JUnit outcomes"
    ledgers = {}
    for prefix in ("baseline", "capture"):
        ledger: dict[str, list[int]] = defaultdict(list)
        for path in sorted(directory.glob(f"{prefix}-ledger-*.jsonl")):
            for line in path.read_text().splitlines():
                event = json.loads(line)
                ledger[event["nodeid"]].append(event["attempt"])
        ledgers[prefix] = dict(ledger)
    assert ledgers["baseline"] == ledgers["capture"], (
        "companion plugin changed actual test execution counts"
    )
    (directory / "execution-ledger.json").write_text(
        json.dumps(ledgers, indent=2, sort_keys=True) + "\n"
    )
    root = ET.parse(captured / "report.xml").getroot()
    assert len(root.findall("testcase")) == 15
    marker_counts: Counter[str] = Counter()
    for case in root.findall("testcase"):
        name = case.get("name")
        assert name
        markers = [
            child
            for child in case
            if child.tag
            in ("flakyFailure", "flakyError", "rerunFailure", "rerunError", "failure", "error")
        ]
        marker_counts.update(child.tag for child in markers)
        if name.endswith("::test_skipped"):
            assert name not in ledgers["capture"] and case.find("skipped") is not None
            continue
        attempts = len(markers) + (case.find("failure") is None and case.find("error") is None)
        assert ledgers["capture"][name] == list(range(1, attempts + 1)), (
            name,
            attempts,
            ledgers["capture"][name],
        )
        phases = json.loads(
            case.find("./properties/property[@name='flakemap.pytest.phases']").get("value")
        )
        assert max(p["attempt"] for p in phases) == attempts
    before_analysis = json.loads(
        run(
            ["-m", "flakemap", str(baseline), "--json", "--fail-on-incomplete"],
            directory,
            2,
            "before-analysis",
        )
    )
    after_analysis = json.loads(
        run(
            [
                "-m",
                "flakemap",
                str(captured),
                "--json",
                "--fail-on-incomplete",
                "--html",
                str(directory / "report.html"),
            ],
            directory,
            0,
            "after-analysis",
        )
    )
    run(["-m", "flakemap", str(captured), "--json", "--fail-on-retry"], directory, 1, "retry-gate")
    assert not after_analysis["warnings"]
    recovered = sum(t["retries"]["recovered_runs"] for t in after_analysis["tests"])
    exhausted = sum(t["retries"]["exhausted_runs"] for t in after_analysis["tests"])
    assert recovered == 4 and exhausted == 5
    record = {
        "workers": workers,
        "testcaseRecords": len(root.findall("testcase")),
        "ordinaryTestcaseRecords": len(before),
        "ordinaryDeclaredTests": ET.parse(baseline / "report.xml")
        .getroot()
        .find("testsuite")
        .get("tests"),
        "executionLedgerAttempts": sum(map(len, ledgers["capture"].values())),
        "markers": dict(marker_counts),
        "recoveredRuns": recovered,
        "exhaustedRuns": exhausted,
        "unchangedOrdinaryOutcomes": True,
        "unchangedExecutionLedger": True,
        "beforeIncompleteExit": 2,
        "captureIncompleteExit": 0,
        "captureRetryGateExit": 1,
        "beforeWarnings": len(before_analysis["warnings"]),
    }
    summary["runs"].append(record)
(OUTPUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
print(json.dumps(summary, indent=2))
