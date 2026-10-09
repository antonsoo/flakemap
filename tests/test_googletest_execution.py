"""Execution attributes from a compiled GoogleTest program, not inferred from names."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from flakemap.cli import main
from flakemap.loader import load_runs
from flakemap.models import Status
from flakemap.parse.junit import parse_junit_file, read_junit
from flakemap.report.json_out import to_json_dict
from flakemap.stats.analyze import analyze

ROOT = Path(__file__).parents[1]
HISTORY = ROOT / "examples/googletest_history"


def test_disabled_test_and_disabled_suite_cannot_make_a_failure_look_intermittent() -> None:
    result = analyze(load_runs(HISTORY))
    assert result.warnings == []
    tests = {test.full_name: test for test in result.tests}
    for name in ("Execution.DISABLED_FailsWhenEnabled", "DISABLED_UnavailableDevice.NeedsHardware"):
        test = tests[name]
        assert (test.n, test.n_pass, test.n_fail, test.n_skip) == (1, 0, 1, 7)
        assert test.classification == "insufficient_data"
        assert test.failure_rate.point == 1
        assert test.flip_pairs == 0
        assert test.duration_n == 1  # suppressed tests' zero times are not measurements
        assert test.activity is not None
        assert test.activity.runs_since_last == 0  # seven skips are not seven clean runs
    cases, warnings = parse_junit_file(HISTORY / "run-02/report.xml")
    assert not warnings
    suppressed = [c for c in cases if c.status is Status.SKIP and "DISABLED_" in c.full_name]
    assert len(suppressed) == 2
    assert all("Not executed" in c.message for c in suppressed)
    assert all(c.source is not None for c in suppressed)


def test_real_failfast_and_runtime_skips_remain_non_successful_outcomes() -> None:
    path = ROOT / "examples/googletest_project/captures/failfast.xml"
    cases, warnings = parse_junit_file(path)
    assert not warnings
    outcomes = {c.name: c.status for c in cases}
    assert outcomes == {
        "AlwaysPasses": Status.PASS,
        "DISABLED_FailsWhenEnabled": Status.SKIP,
        "RuntimeSkip": Status.SKIP,
        "AFailFastTrigger": Status.FAIL,
        "ZAfterTrigger": Status.SKIP,
        "NeedsHardware": Status.SKIP,
    }
    messages = {c.name: c.message for c in cases}
    assert messages["AFailFastTrigger"] == "Controlled fail-fast trigger"
    assert messages["RuntimeSkip"] == "Controlled skip: no device attached"


@pytest.mark.parametrize(
    "attrs",
    [
        'status="notrun"',
        'result="suppressed"',
        'result="skipped"',
        'status="notrun" result="suppressed"',
        'status="run" result="skipped"',
    ],
)
def test_explicit_nonexecution_never_defaults_to_a_pass(attrs: str) -> None:
    cases, warnings = read_junit(
        f'<testsuite><testcase name="test" {attrs}/></testsuite>', "attributes.xml"
    )
    assert cases[0].status is Status.SKIP
    assert not warnings


@pytest.mark.parametrize(
    "attrs,body",
    [
        ('status="notrun"', "<failure/>"),
        ('result="suppressed"', "<error/>"),
        ('result="skipped"', "<failure/>"),
        ('status="notrun"', "<flakyFailure/>"),
        ('result="suppressed"', "<failure/><rerunFailure/>"),
        ('status="run" result="suppressed"', ""),
        ('status="notrun" result="completed"', ""),
        ('result="completed"', "<skipped/>"),
        ('result="aborted"', ""),
        ('status="in-progress"', ""),
        ('status=""', ""),
    ],
)
def test_unresolved_attributes_are_excluded_and_fail_the_integrity_gate(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    attrs: str,
    body: str,
) -> None:
    report = tmp_path / "result.xml"
    report.write_text(f'<testsuite><testcase name="test" {attrs}>{body}</testcase></testsuite>')
    report.with_suffix(".meta.json").write_text('{"sequence":1}')
    cases, warnings = parse_junit_file(report)
    assert warnings and "execution" in warnings[0]
    assert cases[0].status is Status.UNKNOWN
    assert cases[0].retry is None
    assert main([str(tmp_path), "--json", "--fail-on-incomplete"]) == 2
    output = json.loads(capsys.readouterr().out)
    assert output["tests"][0]["runs"]["total"] == 0
    assert output["tests"][0]["runs"]["unknown"] == 1
    assert output["tests"][0]["failure_rate"] is None


def test_completed_is_not_a_synonym_for_pass_and_a_disabled_name_can_run() -> None:
    raw = '<testsuite><testcase name="DISABLED_case" status="run" result="completed"><failure/></testcase><testcase name="plain"/></testsuite>'
    cases, warnings = read_junit(raw, "control.xml")
    assert not warnings
    assert [c.status for c in cases] == [Status.FAIL, Status.PASS]


def test_json_counts_and_cli_integrity_gate_use_only_actual_outcomes(
    capsys: pytest.CaptureFixture[str],
) -> None:
    data = to_json_dict(analyze(load_runs(HISTORY)))
    assert data["summary"]["input_complete"] is True
    test = next(t for t in data["tests"] if t["test"] == "Execution.DISABLED_FailsWhenEnabled")
    assert test["runs"] == {"total": 1, "pass": 0, "fail": 1, "skip": 7, "unknown": 0}
    assert main([str(HISTORY), "--json", "--fail-on-incomplete"]) == 0
    json.loads(capsys.readouterr().out)
