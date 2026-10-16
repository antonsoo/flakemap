"""A CI window counts supplied builds, including missing and skipped tests."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from flakemap.cli import main
from flakemap.loader import load_runs
from flakemap.models import AttemptFailure, RetryEvidence, Run, RunMetadata, Status, TestCaseResult
from flakemap.report import to_json_dict
from flakemap.stats import analyze


def _history(*, tail: str, marker: str, first: int = 30) -> list[Run]:
    runs = []
    for index in range(56):
        cases = [TestCaseResult("control", "suite", Status.PASS)]
        if index < first + 6 or tail == "skip":
            status = (
                Status.SKIP
                if index >= first + 6
                else Status.FAIL
                if index in {first, first + 2, first + 4}
                else Status.PASS
            )
            retry = None
            names: tuple[str, ...] = ()
            if status == Status.FAIL and marker == "retry":
                status = Status.PASS
                retry = RetryEvidence(
                    "recovered", (AttemptFailure("flakyFailure", Status.FAIL, "boom"),)
                )
            elif status == Status.FAIL and marker == "named":
                names = ("TestRetired",)
            cases.append(
                TestCaseResult("sparse", "suite", status, retry=retry, failed_within=names)
            )
        runs.append(Run(RunMetadata(f"run-{index:02}", sequence=index), cases, Path(".")))
    return runs


def _write(root: Path, runs: list[Run]) -> None:
    for run in runs:
        folder = root / run.metadata.run_id
        folder.mkdir(parents=True)
        records = []
        for case in run.testcases:
            marker = "<skipped/>" if case.status == Status.SKIP else ""
            if case.status == Status.FAIL:
                text = (
                    "\n".join(f"--- FAIL: {name} (0.1s)" for name in case.failed_within) or "boom"
                )
                marker = f'<failure message="Failed">{text}</failure>'
            elif case.retry:
                marker = '<flakyFailure message="boom"/>'
            records.append(
                f'<testcase classname="{case.classname}" name="{case.name}">{marker}</testcase>'
            )
        (folder / "junit.xml").write_text(f"<testsuite>{''.join(records)}</testsuite>")
        (folder / "meta.json").write_text(json.dumps({"sequence": run.metadata.sequence}))


@pytest.mark.parametrize("tail", ["absent", "skip"])
@pytest.mark.parametrize("marker", ["final", "retry", "named"])
def test_gate_window_uses_build_positions_and_inclusive_boundary(tmp_path, capsys, tail, marker):
    runs = _history(tail=tail, marker=marker)
    _write(tmp_path, runs)
    result = analyze(runs)
    sparse = next(t for t in result.tests if t.full_name == "suite.sparse")
    assert sparse.activity is not None and sparse.activity.state == "new"
    assert sparse.activity.runs_since_first == 6  # activity's usable-execution axis is unchanged
    assert sparse.first_failure_run_id == "run-30"
    assert sparse.history_runs_since_first_failure == 26
    payload = next(t for t in to_json_dict(result)["tests"] if t["test"] == "suite.sparse")
    assert payload["activity"]["run_axis"] == "usable_test_executions"
    assert payload["history_runs_since_first_failure"] == 26
    if marker == "named":
        assert sparse.named_failures[0].history_runs_since_first_failure == 26
        assert payload["named_failures"][0]["history_runs_since_first_failure"] == 26
    # The window is [total-window, total): run-30 enters a 56-run history at 26.
    for window, expected in [(10, 0), (25, 0), (26, 1)]:
        assert (
            main(
                [str(tmp_path), "--json", "--fail-on-new-flake", "--new-flake-window", str(window)]
            )
            == expected
        )
        captured = capsys.readouterr()
        if expected:
            assert "new flake(s)" in captured.err


@pytest.mark.parametrize("marker", ["final", "retry", "named"])
def test_genuinely_recent_failures_still_fail_the_gate(tmp_path, capsys, marker):
    _write(tmp_path, _history(tail="absent", marker=marker, first=50))
    assert main([str(tmp_path), "--json", "--fail-on-new-flake"]) == 1
    assert "new flake(s) detected" in capsys.readouterr().err


def test_named_onset_does_not_inherit_an_older_parent_failure(tmp_path, capsys):
    runs = _history(tail="absent", marker="named", first=50)
    # Parent failed long ago too, under a different inner test name.
    runs[5].testcases[1] = replace(
        runs[5].testcases[1], status=Status.FAIL, failed_within=("TestOld",)
    )
    _write(tmp_path, runs)
    sparse = next(t for t in analyze(runs).tests if t.full_name == "suite.sparse")
    assert sparse.history_runs_since_first_failure == 51
    assert (
        next(
            n for n in sparse.named_failures if n.name == "TestRetired"
        ).history_runs_since_first_failure
        == 6
    )
    assert main([str(tmp_path), "--json", "--fail-on-new-flake"]) == 1
    assert "TestRetired" in capsys.readouterr().err


def test_no_chronology_does_not_invent_a_build_distance():
    runs = _history(tail="absent", marker="named")
    for run in runs:
        run.metadata.sequence = None
    sparse = next(t for t in analyze(runs).tests if t.full_name == "suite.sparse")
    assert sparse.first_failure_run_id is None
    assert sparse.history_runs_since_first_failure is None
    assert sparse.named_failures[0].history_runs_since_first_failure is None


def test_actual_pytest_retirement_keeps_build_distance_separate_from_executions():
    history = Path(__file__).resolve().parents[1] / "studies/gate-window/fixtures/history"
    result = analyze(load_runs(history))
    assert result.total_runs == 56 and not result.warnings
    for test in result.tests:
        if test.full_name.endswith(".test_control"):
            assert test.first_failure_run_id is None
            continue
        assert (test.n, test.n_fail) == (36, 3)
        assert test.activity is not None and test.activity.runs_since_first == 6
        assert test.history_runs_since_first_failure == 26
