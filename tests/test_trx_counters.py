"""Counter checks on actual dotnet reports and an actual nested VSTest logger capture."""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from flakemap.models import Status
from flakemap.parse.trx import read_trx

ROOT = Path(__file__).resolve().parents[1]
NS = "{http://microsoft.com/schemas/VisualStudio/TeamTest/2010}"
FLAT = ROOT / "examples/trx_history/run-02.trx"
NESTED = ROOT / "examples/trx_counters_project/captures/nested.trx"


def read(root: ET.Element):  # type: ignore[no-untyped-def]
    return read_trx(ET.tostring(root, encoding="unicode"), "report.trx")


def counters(root: ET.Element) -> ET.Element:
    element = root.find(f"{NS}ResultSummary/{NS}Counters")
    assert element is not None
    return element


def test_all_real_dotnet_captures_reconcile_despite_zero_notexecuted() -> None:
    for path in sorted(FLAT.parent.glob("*.trx")):
        root = ET.parse(path).getroot()
        cases, warnings, _ = read(root)
        assert not warnings, path
        assert len(cases) == 6
        assert sum(case.status is Status.SKIP for case in cases) == 1
        assert counters(root).get("notExecuted") == "0"


@pytest.mark.parametrize("outcome", ["Failed", "Passed", "NotExecuted"])
def test_removed_real_result_is_unverified_without_reconstructing_it(outcome: str) -> None:
    root = ET.parse(FLAT).getroot()
    group = root.find(f"{NS}Results")
    assert group is not None
    group.remove(next(result for result in group if result.get("outcome") == outcome))
    cases, warnings, _ = read(root)
    assert len(cases) == 5
    assert len(warnings) == 1 and "declares total=6" in warnings[0]
    assert "retained all result records (total=5" in warnings[0]


def test_rewritten_outcome_is_detected_even_when_record_count_matches() -> None:
    root = ET.parse(FLAT).getroot()
    failed = root.find(f"{NS}Results/{NS}UnitTestResult[@outcome='Failed']")
    assert failed is not None
    failed.set("outcome", "Passed")
    cases, warnings, _ = read(root)
    assert len(cases) == 6 and len(warnings) == 1
    assert "failed=1" in warnings[0] and "failed=0" in warnings[0]


def test_real_nested_capture_counts_rows_but_keeps_one_history_observation() -> None:
    root = ET.parse(NESTED).getroot()
    cases, warnings, _ = read(root)
    assert not warnings
    assert counters(root).get("total") == "5"
    assert len(cases) == 3
    assert sorted(case.status.value for case in cases) == ["fail", "pass", "skip"]


def test_nested_row_removal_is_detected_without_changing_parent_observations() -> None:
    root = ET.parse(NESTED).getroot()
    before, _, _ = read(root)
    inner = root.find(f"{NS}Results/{NS}UnitTestResult/{NS}InnerResults")
    assert inner is not None
    inner.remove(next(row for row in inner if row.get("outcome") == "Failed"))
    after, warnings, _ = read(root)
    assert after == before
    assert len(warnings) == 1 and "do not reconcile" in warnings[0]


def test_newer_vstest_convention_excludes_explicit_data_driven_parent() -> None:
    # Deliberately transformed counters, based on upstream logger source.
    # The actual retained capture uses VSTest 17.11's parent-inclusive convention.
    root = ET.parse(NESTED).getroot()
    counters(root).attrib.update(total="4", executed="3", passed="2", failed="1")
    assert not read(root)[1]
    parent = root.find(f"{NS}Results/{NS}UnitTestResult[@resultType='DataDrivenTest']")
    assert parent is not None
    del parent.attrib["resultType"]
    assert "do not reconcile" in read(root)[1][0]


def test_counters_cannot_mix_parent_inclusive_and_exclusive_profiles() -> None:
    root = ET.parse(NESTED).getroot()
    counters(root).set("failed", "1")
    assert "do not reconcile" in read(root)[1][0]


@pytest.mark.parametrize("value", ["-1", "NaN", "1.0", "1e1", "", "９", "9" * 10000])
def test_invalid_counts_are_bounded_diagnostics(value: str) -> None:
    root = ET.parse(FLAT).getroot()
    counters(root).set("total", value)
    cases, warnings, _ = read(root)
    assert len(cases) == 6
    assert len(warnings) == 1 and "nonnegative integer" in warnings[0]
    assert len(warnings[0]) < 200


def test_supplied_counters_are_optional_and_whitespace_integers_are_supported() -> None:
    root = ET.parse(FLAT).getroot()
    counts = counters(root)
    counts.attrib.clear()
    assert not read(root)[1]
    counts.set("total", " +6 ")
    assert not read(root)[1]
    counts.set("failed", "2")
    assert "do not reconcile" in read(root)[1][0]


def test_result_shaped_payload_does_not_count_as_a_record() -> None:
    root = ET.parse(NESTED).getroot()
    result = root.find(f"{NS}Results/{NS}UnitTestResult")
    assert result is not None
    output = ET.SubElement(result, f"{NS}Output")
    ET.SubElement(output, f"{NS}UnitTestResult", outcome="Failed", testName="fake")
    ET.SubElement(root, f"{NS}UnitTestResult", outcome="Failed", testName="fake")
    assert not read(root)[1]


@pytest.mark.parametrize("element", ["ResultSummary", "Counters"])
def test_multiple_summary_elements_are_ambiguous(element: str) -> None:
    root = ET.parse(FLAT).getroot()
    container = root if element == "ResultSummary" else root.find(f"{NS}ResultSummary")
    assert container is not None
    ET.SubElement(container, NS + element)
    assert "ambiguous" in read(root)[1][0]
