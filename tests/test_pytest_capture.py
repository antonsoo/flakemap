"""Execute the actual retry producer; do not infer retries from duplicate XML."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from flakemap.cli import main
from flakemap.models import Status
from flakemap.parse.junit import parse_junit_file

NATIVE = Path(__file__).parents[1] / "studies/pytest-capture/native/test_retries.py"


def execute(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "flakemap.pytest_plugin", *args],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=45,
        env={
            **os.environ,
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
            "PYTEST_ADDOPTS": "",
            "FLAKEMAP_EXECUTION_LOG": str(root / "executed"),
        },
    )


@pytest.mark.parametrize("workers", [0, 2])
def test_native_retry_phases_and_independent_execution_counts(
    tmp_path: Path, workers: int, capsys: pytest.CaptureFixture[str]
) -> None:
    shutil.copyfile(NATIVE, tmp_path / "test_retries.py")
    arguments = [
        "test_retries.py",
        "-p",
        "rerunfailures",
        "--reruns",
        "2",
        "--flakemap-xml=capture.xml",
        "--junitxml=ordinary.xml",
        "-q",
    ]
    if workers:
        arguments += ["-p", "xdist.plugin", "-n", str(workers)]
    result = execute(tmp_path, *arguments)
    assert result.returncode == 1, result.stdout + result.stderr
    cases, warnings = parse_junit_file(tmp_path / "capture.xml")
    assert warnings == []
    actual = {c.name.split("::")[-1]: c for c in cases}
    assert len(actual) == 15
    for name, attempts, kind in [
        ("test_recovered_call", 3, "recovered"),
        ("test_recovered_setup", 2, "recovered"),
        ("test_recovered_teardown", 2, "recovered"),
        ("test_recovered_call_and_teardown", 2, "recovered"),
        ("test_exhausted_call", 3, "exhausted"),
        ("test_exhausted_setup", 3, "exhausted"),
        ("test_exhausted_teardown", 3, "exhausted"),
        ("test_exhausted_call_and_teardown", 3, "exhausted"),
    ]:
        retry = actual[name].retry
        assert retry and retry.attempts == attempts and retry.outcome == kind
    assert "connection not ready" in actual["test_recovered_call"].retry.failures[0].message
    assert actual["test_exhausted_call_and_teardown"].status is Status.ERROR
    assert actual["test_skipped"].status is Status.SKIP
    assert actual["test_xfail"].status is Status.SKIP
    assert actual["test_xpass"].status is Status.PASS
    assert actual["test_strict_xpass"].status is Status.FAIL
    assert actual["test_parameter_identity[<xml>&[name]]"].status is Status.PASS
    ledger: dict[str, list[int]] = {}
    for path in tmp_path.glob("executed-*.jsonl"):
        for line in path.read_text().splitlines():
            event = json.loads(line)
            ledger.setdefault(event["nodeid"], []).append(event["attempt"])
    for c in cases:
        if c.name.endswith("::test_skipped"):
            assert c.name not in ledger
        else:
            expected = (
                c.retry.attempts
                if c.retry
                else (3 if c.name.endswith("::test_strict_xpass") else 1)
            )
            assert ledger[c.name] == list(range(1, expected + 1))
    root = ET.parse(tmp_path / "capture.xml").getroot()
    dual = next(
        e
        for e in root.findall("testcase")
        if e.get("name", "").endswith("::test_recovered_call_and_teardown")
    )
    assert len(dual.findall("flakyError")) == 1
    trace = dual.findtext("flakyError/stackTrace")
    assert "call failed first" in trace and "teardown failed too" in trace
    assert "teardown failed too" in dual.find("flakyError").get("message")
    assert main([str(tmp_path), "--pattern", "capture.xml", "--fail-on-incomplete", "--json"]) == 0
    capsys.readouterr()
    assert main([str(tmp_path), "--pattern", "capture.xml", "--fail-on-retry", "--json"]) == 1
    capsys.readouterr()
    assert main([str(tmp_path), "--pattern", "ordinary.xml", "--fail-on-incomplete", "--json"]) == 2


def test_plain_pytest_and_collection_failure(tmp_path: Path) -> None:
    (tmp_path / "test_plain.py").write_text("def test_pass(): pass\n")
    result = execute(tmp_path, "test_plain.py", "--flakemap-xml=capture.xml", "-q")
    assert result.returncode == 0, result.stdout + result.stderr
    cases, warnings = parse_junit_file(tmp_path / "capture.xml")
    assert warnings == [] and len(cases) == 1 and cases[0].status is Status.PASS
    (tmp_path / "test_broken.py").write_text("raise RuntimeError('collection failed')\n")
    result = execute(tmp_path, "test_broken.py", "--flakemap-xml=capture.xml", "-q")
    assert result.returncode == 2
    cases, warnings = parse_junit_file(tmp_path / "capture.xml")
    assert warnings and all(c.status is Status.UNKNOWN for c in cases)
    assert "collection failed" in cases[0].issue


def test_pending_capture_replaces_stale_success(tmp_path: Path) -> None:
    path = tmp_path / "capture.xml"
    path.write_text('<testsuite><testcase name="old-success"/></testsuite>')
    (tmp_path / "test_hang.py").write_text(
        "from pathlib import Path\nimport time\ndef test_hang():\n"
        " Path('started').write_text('started')\n time.sleep(30)\n"
    )
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "flakemap.pytest_plugin",
            "test_hang.py",
            "--flakemap-xml=capture.xml",
            "-q",
        ],
        cwd=tmp_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**os.environ, "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1", "PYTEST_ADDOPTS": ""},
    )
    try:
        deadline = time.monotonic() + 10
        while (
            not (tmp_path / "started").exists()
            and time.monotonic() < deadline
            and process.poll() is None
        ):
            time.sleep(0.01)
        assert (tmp_path / "started").exists(), "pytest did not start the controlled hanging test"
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=5)
    cases, warnings = parse_junit_file(path)
    assert warnings and len(cases) == 1 and cases[0].status is Status.UNKNOWN
    assert "has not completed" in cases[0].issue


def test_same_output_path_is_refused_before_execution(tmp_path: Path) -> None:
    (tmp_path / "test_plain.py").write_text("def test_fail(): assert False\n")
    result = execute(tmp_path, "--flakemap-xml=same.xml", "--junitxml=same.xml", "-q")
    assert result.returncode == 4
    assert "must name different files" in result.stderr
    assert not (tmp_path / "same.xml").exists()


def test_early_stop_retains_failure_but_marks_unexecuted_selection(tmp_path: Path) -> None:
    (tmp_path / "test_stop.py").write_text("def test_a(): assert False\ndef test_b(): pass\n")
    result = execute(tmp_path, "test_stop.py", "-x", "--flakemap-xml=capture.xml", "-q")
    assert result.returncode == 1
    cases, warnings = parse_junit_file(tmp_path / "capture.xml")
    assert warnings
    assert [c.status for c in cases] == [Status.FAIL, Status.UNKNOWN]
    assert "selected 2 tests" in cases[-1].issue


def test_retry_ending_in_skip_is_not_recovery(tmp_path: Path) -> None:
    (tmp_path / "test_skip.py").write_text(
        "import pytest\ncalls = 0\ndef test_skip():\n"
        " global calls\n calls += 1\n if calls == 1: assert False\n pytest.skip('aborted')\n"
    )
    result = execute(
        tmp_path,
        "test_skip.py",
        "-p",
        "rerunfailures",
        "--reruns",
        "2",
        "--flakemap-xml=capture.xml",
        "-q",
    )
    assert result.returncode == 0
    cases, warnings = parse_junit_file(tmp_path / "capture.xml")
    assert warnings and len(cases) == 1 and cases[0].status is Status.UNKNOWN
    assert "recovery was not observed" in cases[0].issue


def test_pytest_retry_gate_keeps_its_exit_code(tmp_path: Path) -> None:
    shutil.copyfile(NATIVE, tmp_path / "test_retries.py")
    result = execute(
        tmp_path,
        "test_retries.py",
        "-k",
        "recovered",
        "-p",
        "rerunfailures",
        "--reruns",
        "2",
        "--fail-on-flaky",
        "--flakemap-xml=capture.xml",
        "-q",
    )
    assert result.returncode == 7, result.stdout + result.stderr
    cases, warnings = parse_junit_file(tmp_path / "capture.xml")
    assert warnings == [] and len(cases) == 4
    assert all(c.retry and c.retry.outcome == "recovered" for c in cases)
