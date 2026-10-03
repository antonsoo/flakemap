"""TRX (Visual Studio test results), checked against the real `dotnet test --logger trx`
output in examples/trx_history (12 runs of examples/trx_project) and against
hand-written documents for the outcome mapping and edge cases the capture doesn't
produce."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from flakemap.loader import load_runs
from flakemap.models import Status
from flakemap.parse.trx import is_trx, parse_trx_file
from flakemap.stats.analyze import analyze

HISTORY = Path(__file__).resolve().parent.parent / "examples" / "trx_history"
NS = "http://microsoft.com/schemas/VisualStudio/TeamTest/2010"


def by_name(result):  # type: ignore[no-untyped-def]
    return {t.full_name.removeprefix("FlakyDotnet.Tests.CheckoutTests."): t for t in result.tests}


def test_real_history_is_ordered_by_each_report_start_time() -> None:
    runs = load_runs(HISTORY)
    assert [r.metadata.run_id for r in runs] == [f"run-{i:02d}" for i in range(1, 13)]
    assert {r.metadata.source for r in runs} == {"report"}
    assert all(len(r.testcases) == 6 for r in runs)


def test_real_history_classification() -> None:
    tests = by_name(analyze(load_runs(HISTORY)))
    assert tests["CacheWarmsBeforeFirstRequest"].classification == "flaky"
    regression = tests["DiscountCodeIsCaseInsensitive"]
    assert regression.classification == "broken"
    assert regression.change_point is not None
    # Each data row of the data-driven test is its own test.
    assert tests['CurrencyHasMinorUnits ("EUR",2)'].classification == "healthy"
    assert tests['CurrencyHasMinorUnits ("JPY",0)'].classification == "healthy"
    assert tests["RefundReachesSandbox"].classification == "insufficient_data"


def test_real_failure_message_carries_the_exception() -> None:
    cases, warnings, started = parse_trx_file(HISTORY / "run-07.trx")
    assert not warnings and started is not None and started.tzinfo is not None
    failed = next(c for c in cases if c.status is Status.FAIL)
    assert failed.classname == "FlakyDotnet.Tests.CheckoutTests"
    assert (
        failed.message is not None and "InvalidOperationException: discount code" in failed.message
    )
    skipped = next(c for c in cases if c.status is Status.SKIP)
    assert skipped.message == "payment sandbox is down"


def test_report_time_beats_file_mtime(tmp_path: Path) -> None:
    for i, path in enumerate(sorted(HISTORY.glob("*.trx"))):
        copy = tmp_path / path.name
        shutil.copy(path, copy)
        os.utime(copy, (2_000_000_000 - i * 60, 2_000_000_000 - i * 60))  # newest file = run-01
    assert [r.metadata.run_id for r in load_runs(tmp_path)][:3] == ["run-01", "run-02", "run-03"]


def test_a_sidecar_timestamp_still_wins(tmp_path: Path) -> None:
    run = tmp_path / "late"
    run.mkdir()
    shutil.copy(HISTORY / "run-01.trx", run / "results.trx")
    (run / "meta.json").write_text('{"timestamp": "2030-01-01T00:00:00Z"}')
    (meta,) = [r.metadata for r in load_runs(tmp_path)]
    assert meta.source == "sidecar" and meta.timestamp.year == 2030


def trx(
    results: str, definitions: str = "", start: str = "2026-09-30T10:00:00.1234567+00:00"
) -> str:
    return (
        f'<?xml version="1.0" encoding="utf-8"?><TestRun id="1" name="x" xmlns="{NS}">'
        f'<Times start="{start}"/><Results>{results}</Results>'
        f"<TestDefinitions>{definitions}</TestDefinitions></TestRun>"
    )


def write(tmp_path: Path, text: str, name: str = "r.trx", encoding: str = "utf-8") -> Path:
    path = tmp_path / name
    path.write_bytes(text.encode(encoding))
    return path


@pytest.mark.parametrize(
    "outcome,status",
    [
        ("Passed", Status.PASS),
        ("PassedButRunAborted", Status.PASS),
        ("Failed", Status.FAIL),
        ("Error", Status.ERROR),
        ("Timeout", Status.ERROR),
        ("Aborted", Status.ERROR),
        ("NotExecuted", Status.SKIP),
        ("Inconclusive", Status.SKIP),
        ("Pending", Status.UNKNOWN),
    ],
)
def test_outcome_mapping(tmp_path: Path, outcome: str, status: Status) -> None:  # hand-written
    (case,), warnings, _ = parse_trx_file(
        write(tmp_path, trx(f'<UnitTestResult testName="A.B.c" outcome="{outcome}"/>'))
    )
    assert case.status is status
    assert bool(case.issue) == (status is Status.UNKNOWN)


def test_xunit_style_qualified_names_and_long_durations(tmp_path: Path) -> None:  # hand-written
    results = '<UnitTestResult testId="t1" testName="Shop.Tests.CartTests.Adds(qty: 2)" outcome="Passed" duration="1.02:03:04.5000000"/>'
    definitions = '<UnitTest id="t1" name="Adds"><TestMethod className="Shop.Tests.CartTests, Shop.Tests, Version=1.0.0.0" name="Adds"/></UnitTest>'
    (case,), _, _ = parse_trx_file(write(tmp_path, trx(results, definitions)))
    assert (case.classname, case.name) == ("Shop.Tests.CartTests", "Adds(qty: 2)")
    assert case.duration == pytest.approx(93784.5)


def test_without_definitions_the_test_name_is_split(tmp_path: Path) -> None:  # hand-written
    (case,), _, _ = parse_trx_file(
        write(
            tmp_path, trx('<UnitTestResult testName="Shop.CartTests.Adds(a.b)" outcome="Failed"/>')
        )
    )
    assert (case.classname, case.name) == ("Shop.CartTests", "Adds(a.b)")


def test_utf16_with_declaration(tmp_path: Path) -> None:  # hand-written
    text = trx('<UnitTestResult testName="A.B.c" outcome="Passed"/>').replace(
        'encoding="utf-8"', 'encoding="utf-16"'
    )
    cases, warnings, started = parse_trx_file(write(tmp_path, "﻿" + text, encoding="utf-16-le"))
    assert [c.status for c in cases] == [Status.PASS] and not warnings and started is not None


def test_dtd_rejected(tmp_path: Path) -> None:  # hand-written
    text = f'<!DOCTYPE TestRun [<!ENTITY x "y">]><TestRun xmlns="{NS}"><Results/></TestRun>'
    assert parse_trx_file(write(tmp_path, text)) == (
        [],
        ["DTD and entity declarations are not supported"],
        None,
    )


def test_trx_saved_as_xml_is_sniffed_and_junit_is_not(tmp_path: Path) -> None:  # hand-written
    write(tmp_path, trx('<UnitTestResult testName="A.B.c" outcome="Failed"/>'), name="dotnet.xml")
    write(
        tmp_path,
        '<testsuite name="s"><testcase classname="x" name="y"/></testsuite>',
        name="junit.xml",
    )
    assert is_trx((tmp_path / "dotnet.xml").read_text()) and not is_trx(
        (tmp_path / "junit.xml").read_text()
    )
    statuses = sorted(c.status.value for r in load_runs(tmp_path) for c in r.testcases)
    assert statuses == ["fail", "pass"]


def test_a_colour_code_in_a_message_does_not_cost_the_report(tmp_path: Path) -> None:
    # The same report with a colour code in the failure message, as test output carries it:
    # XML 1.0 does not allow the ESC, and the whole report used to be refused.
    text = (HISTORY / "run-07.trx").read_text(encoding="utf-8-sig")
    marked = text.replace(
        "InvalidOperationException", "&#x1B;[31mInvalidOperationException&#x1B;[0m", 1
    )
    assert marked != text
    path = tmp_path / "run-07.trx"
    path.write_text(marked, encoding="utf-8")
    cases, warnings, _ = parse_trx_file(path)
    assert warnings == []
    assert len(cases) == 6
    failed = next(c for c in cases if c.status is Status.FAIL)
    assert (
        failed.message is not None and "InvalidOperationException: discount code" in failed.message
    )
