"""Native failed rows cannot silently establish a passing parent observation."""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from flakemap.models import Status
from flakemap.parse.trx import parse_trx_file, read_trx
from flakemap.report.json_out import record_to_dict

FIXTURES = Path(__file__).resolve().parents[1] / "studies/trx-hierarchy/fixtures"
NS = "{http://microsoft.com/schemas/VisualStudio/TeamTest/2010}"


@pytest.mark.parametrize(
    ("case", "status", "count"),
    [
        ("passed-parent-failed-row", Status.UNKNOWN, 3),
        ("skipped-parent-failed-row", Status.UNKNOWN, 3),
        ("failed-parent-failed-row", Status.FAIL, 3),
        ("failed-parent-passing-rows", Status.FAIL, 3),
        ("passed-parent-passing-rows", Status.PASS, 3),
        ("passed-parent-skipped-row", Status.PASS, 3),
        ("grandchild-events-top-level", Status.PASS, 5),
    ],
)
def test_captured_native_parent_outcomes_do_not_inflate_trials(case, status, count) -> None:
    cases, warnings, _ = parse_trx_file(FIXTURES / f"{case}.trx")
    assert len(cases) == count
    parent = next(result for result in cases if result.full_name == "Capture.Example.Data")
    assert parent.status is status
    assert bool(warnings) == (status is Status.UNKNOWN)
    assert parent.nested_results is not None
    assert parent.retry is None
    if status is Status.UNKNOWN:
        rows = record_to_dict(parent)["nested_results"]
        assert rows["reported_parent_outcome"] in ("Passed", "NotExecuted")
        failed = next(row for row in rows["rows"] if row["status"] == "fail")
        assert failed["path"] == [2] and failed["message"] == "Controlled nested row failure"
        assert "conflicts with recorded failing inner results" in parent.issue


def test_authored_deep_xml_keeps_preorder_paths_without_extra_observations() -> None:
    # This is an explicit XML transformation. The captured SDK writes its deep
    # event relationships as additional top-level rows, not this nested tree.
    root = ET.parse(FIXTURES / "passed-parent-failed-row.trx").getroot()
    parent = next(
        row
        for row in root.findall(f"{NS}Results/{NS}UnitTestResult")
        if row.get("resultType") == "DataDrivenTest"
    )
    inner = parent.find(f"{NS}InnerResults")
    assert inner is not None
    passing, failing = list(inner)
    inner.remove(failing)
    ET.SubElement(passing, f"{NS}InnerResults").append(failing)
    sibling = ET.SubElement(inner, f"{NS}UnitTestResult", testName="last sibling", outcome="Passed")
    assert sibling is not None
    counters = root.find(f"{NS}ResultSummary/{NS}Counters")
    assert counters is not None
    counters.attrib.update(total="6", executed="5", passed="4", failed="1")
    cases, warnings, _ = read_trx(ET.tostring(root, encoding="unicode"), "authored.trx")
    assert len(cases) == 3 and len(warnings) == 1
    data = next(row for row in cases if row.full_name == "Capture.Example.Data")
    assert data.status is Status.UNKNOWN and data.nested_results is not None
    assert [row.path for row in data.nested_results.rows] == [(1,), (1, 1), (2,)]
    assert "row 1.1" in data.issue


def test_unknown_inner_outcome_never_leaves_coverage_clean() -> None:
    root = ET.parse(FIXTURES / "passed-parent-failed-row.trx").getroot()
    row = root.find(f".//{NS}InnerResults/{NS}UnitTestResult[@outcome='Failed']")
    assert row is not None
    row.set("outcome", "Pending")
    counts = root.find(f"{NS}ResultSummary/{NS}Counters")
    assert counts is not None
    counts.attrib.update(executed="3", passed="3", failed="0")
    summary = root.find(f"{NS}ResultSummary")
    assert summary is not None
    summary.set("outcome", "Passed")
    cases, warnings, _ = read_trx(ET.tostring(root, encoding="unicode"), "pending.trx")
    assert len(warnings) == 1 and "inner coverage is unverified" in warnings[0]
    parent = next(result for result in cases if result.full_name == "Capture.Example.Data")
    assert parent.nested_results is not None
    assert parent.nested_results.rows[1].reported_outcome == "Pending"
    assert parent.nested_results.rows[1].status is Status.UNKNOWN


def test_inner_evidence_is_escaped_in_the_existing_exclusion_report() -> None:
    from flakemap.models import Run, RunMetadata
    from flakemap.report.html_out import render_html
    from flakemap.stats.analyze import analyze

    root = ET.parse(FIXTURES / "passed-parent-failed-row.trx").getroot()
    row = root.find(f".//{NS}InnerResults/{NS}UnitTestResult[@outcome='Failed']")
    assert row is not None
    row.set("testName", '<img src=x onerror="alert(1)">')
    cases, warnings, _ = read_trx(ET.tostring(root, encoding="unicode"), "hostile.trx")
    run = Run(RunMetadata("native", sequence=1), cases, Path("hostile.trx"), warnings)
    html = render_html(analyze([run]), [run])
    assert "<img src=x" not in html and "&lt;img src=x" in html
    assert "reported Passed; normalized unknown" in html


def test_an_unknown_parent_is_not_relabelled_as_a_nonfailure_contradiction() -> None:
    root = ET.parse(FIXTURES / "passed-parent-failed-row.trx").getroot()
    parent = next(
        row
        for row in root.findall(f"{NS}Results/{NS}UnitTestResult")
        if row.get("resultType") == "DataDrivenTest"
    )
    parent.set("outcome", "Completed")
    counts = root.find(f"{NS}ResultSummary/{NS}Counters")
    assert counts is not None
    counts.attrib.update(executed="3", passed="2", failed="1")
    cases, warnings, _ = read_trx(ET.tostring(root, encoding="unicode"), "unknown.trx")
    data = next(row for row in cases if row.full_name == "Capture.Example.Data")
    assert data.status is Status.UNKNOWN and len(warnings) == 1
    assert "does not establish pass, failure or skip" in data.issue
    assert "conflicts" not in data.issue
    assert data.nested_results is not None
    assert data.nested_results.rows[1].status is Status.FAIL


@pytest.mark.parametrize("parser_warning", [True, False])
def test_exclusion_warns_once_with_or_without_a_parser_warning(parser_warning) -> None:
    from flakemap.models import Run, RunMetadata
    from flakemap.stats.analyze import analyze

    cases, warnings, _ = parse_trx_file(FIXTURES / "passed-parent-failed-row.trx")
    run = Run(
        RunMetadata("native", sequence=1),
        cases,
        Path("native.trx"),
        warnings if parser_warning else [],
    )
    result = analyze([run])
    assert len(result.warnings) == 1
    assert "conflicts with recorded failing inner results" in result.warnings[0]


def test_one_reported_issue_does_not_hide_another_tests_exclusion() -> None:
    from flakemap.models import Run, RunMetadata, SourceLocation, TestCaseResult
    from flakemap.stats.analyze import analyze

    records = [
        TestCaseResult(
            name,
            "C",
            Status.UNKNOWN,
            issue="missing outcome",
            source=SourceLocation("same.trx", index),
        )
        for index, name in enumerate(("A", "B"), 1)
    ]
    run = Run(
        RunMetadata("native", sequence=1),
        records,
        Path("same.trx"),
        ["same.trx: C.A: missing outcome; excluded from rates"],
    )
    warnings = analyze([run]).warnings
    assert len(warnings) == 2
    assert any("C.A: missing outcome" in warning for warning in warnings)
    assert any("C.B: missing outcome" in warning for warning in warnings)
