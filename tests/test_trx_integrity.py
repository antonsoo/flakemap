"""Adversarial TRX evidence, independent of the generated dotnet history."""

from __future__ import annotations

from pathlib import Path

import pytest

from flakemap.models import Status
from flakemap.parse.trx import parse_trx_file, read_trx


def report(result: str, definitions: str = "", rest: str = "") -> str:
    return f"<TestRun><Results>{result}</Results><TestDefinitions>{definitions}</TestDefinitions>{rest}</TestRun>"


@pytest.mark.parametrize(
    "raw",
    [
        "00:99:99",
        "24:00:00",
        "1.24:00:00",
        "00:00:60",
        "-00:00:01",
        "00:00:01.12345678",
        "10675199.02:48:05.4775808",
        "99999999.00:00:00",
        "1" * 5000 + ".00:00:00",
        "٠٠:٠٠:٠١",
        "",
    ],
)
def test_invalid_timespan_is_unknown_without_crashing(raw: str, tmp_path: Path) -> None:
    path = tmp_path / "bad.trx"
    path.write_text(
        report(f'<UnitTestResult testName="A.test" outcome="Passed" duration="{raw}"/>')
    )
    (case,), warnings, _ = parse_trx_file(path)
    assert case.status is Status.PASS
    assert case.duration is None
    assert any("invalid TRX duration" in warning for warning in warnings)
    assert all(len(warning) < 200 for warning in warnings)


@pytest.mark.parametrize(
    "raw,seconds",
    [
        ("00:00:00", 0),
        ("00:00:00.0000001", 1e-7),
        ("1.02:03:04.5000000", 93784.5),
        ("10675199.02:48:05.4775807", ((1 << 63) - 1) / 10_000_000),
    ],
)
def test_valid_timespan_boundaries(raw: str, seconds: float) -> None:
    (case,), warnings, _ = read_trx(
        report(f'<UnitTestResult testName="A.test" outcome="Passed" duration="{raw}"/>'),
        "synthetic.trx",
    )
    assert not warnings
    assert case.duration == seconds


@pytest.mark.parametrize(
    "outcome", ["Inconclusive", "Completed", "Warning", "Pending", "InProgress", "Disconnected"]
)
def test_nonqualitative_outcomes_retain_the_reason(outcome: str) -> None:
    (case,), warnings, _ = read_trx(
        report(
            f'<UnitTestResult testName="A.test" outcome="{outcome}"><Output><ErrorInfo><Message>Runner could not decide.</Message></ErrorInfo></Output></UnitTestResult>'
        ),
        "synthetic.trx",
    )
    assert case.status is Status.UNKNOWN
    assert case.message == "Runner could not decide."
    assert outcome in str(case.issue)
    assert warnings


def test_conflicting_definitions_do_not_choose_a_test_identity() -> None:
    definitions = "".join(
        f'<UnitTest id="same"><TestMethod className="{name}" name="test"/></UnitTest>'
        for name in ["A", "B", "B"]
    )
    (case,), warnings, _ = read_trx(
        report('<UnitTestResult testId="same" testName="test" outcome="Passed"/>', definitions),
        "synthetic.trx",
    )
    assert case.status is Status.UNKNOWN
    assert "conflicting" in str(case.issue)
    assert warnings


def test_identical_repeated_definitions_are_not_conflicting() -> None:
    definitions = '<UnitTest id="same"><TestMethod className="A" name="test"/></UnitTest>' * 2
    (case,), warnings, _ = read_trx(
        report('<UnitTestResult testId="same" testName="test" outcome="Passed"/>', definitions),
        "synthetic.trx",
    )
    assert case.status is Status.PASS
    assert case.full_name == "A.test"
    assert warnings == []


def test_unsupported_results_and_incomplete_summary_are_visible() -> None:
    raw = report(
        '<UnitTestResult testName="A.test" outcome="Passed"/><WebTestResult outcome="Failed"/>',
        rest='<ResultSummary outcome="Aborted"/>',
    )
    cases, warnings, _ = read_trx(raw, "synthetic.trx")
    assert len(cases) == 1 and cases[0].status is Status.PASS
    assert any("unsupported TRX result" in warning for warning in warnings)
    assert any("summary is aborted" in warning for warning in warnings)


def test_multiple_result_containers_are_retained_with_a_warning() -> None:
    raw = report(
        '<UnitTestResult testName="one" outcome="Passed"/>',
        rest='<Results><UnitTestResult testName="two" outcome="Failed"/></Results>',
    )
    cases, warnings, _ = read_trx(raw, "synthetic.trx")
    assert [case.name for case in cases] == ["one", "two"]
    assert any("multiple TRX Results" in warning for warning in warnings)


@pytest.mark.parametrize(
    "times",
    [
        '<Times start="not-a-time"/>',
        '<Times start="2026-10-01T00:00:00Z"/><Times start="2026-10-02T00:00:00Z"/>',
    ],
)
def test_invalid_or_multiple_start_times_cannot_order_a_run(times: str) -> None:
    _, warnings, started = read_trx(
        report('<UnitTestResult testName="test" outcome="Passed"/>', rest=times), "synthetic.trx"
    )
    assert started is None
    assert any("start time" in warning for warning in warnings)


def test_anonymous_results_are_unknown() -> None:
    (case,), warnings, _ = read_trx(report('<UnitTestResult outcome="Passed"/>'), "synthetic.trx")
    assert case.status is Status.UNKNOWN
    assert "missing TRX test name" in str(case.issue)
    assert warnings


def test_direct_text_entrypoint_rejects_entities() -> None:
    raw = '<!DOCTYPE TestRun [<!ENTITY hidden "x">]>' + report(
        '<UnitTestResult testName="&hidden;" outcome="Passed"/>'
    )
    assert read_trx(raw, "synthetic.trx") == (
        [],
        ["DTD and entity declarations are not supported"],
        None,
    )
