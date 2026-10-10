"""Counter evidence catches well-formed loss without manufacturing missing outcomes."""

from __future__ import annotations

import json
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from flakemap.cli import main
from flakemap.models import Status
from flakemap.parse.junit import parse_junit_file, read_junit

ROOT = Path(__file__).parents[1]
CAPTURES = ROOT / "examples/junit_counters_project/captures"


def test_real_pytest_report_and_removed_failure_records(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    cases, warnings = parse_junit_file(CAPTURES / "basic.xml")
    assert not warnings
    assert [case.status for case in cases] == [Status.PASS, Status.FAIL, Status.ERROR, Status.SKIP]

    tree = ET.parse(CAPTURES / "basic.xml")
    suite = tree.getroot().find("testsuite")
    assert suite is not None
    for case in list(suite.findall("testcase")):
        if case.find("failure") is not None or case.find("error") is not None:
            suite.remove(case)
    tree.write(tmp_path / "report.xml", encoding="utf-8")
    (tmp_path / "meta.json").write_text('{"sequence":1}')
    assert main([str(tmp_path), "--json", "--fail-on-incomplete"]) == 2
    output = capsys.readouterr()
    data = json.loads(output.out)
    assert data["summary"]["input_complete"] is False
    assert data["summary"]["total_tests"] == 2
    assert data["summary"]["excluded_test_runs"] == 0
    assert "declares tests=4, failures=1, errors=1, skipped=1" in data["warnings"][0]
    assert "testcase records (tests=2, failures=0, errors=0, skipped=1)" in data["warnings"][0]
    assert "report.xml" in data["warnings"][0]
    assert sum(test["runs"]["fail"] for test in data["tests"]) == 0


def test_removed_failure_marker_is_detected_even_when_test_count_matches() -> None:
    tree = ET.parse(CAPTURES / "basic.xml")
    for case in tree.iter("testcase"):
        for marker in list(case):
            if marker.tag in ("failure", "error"):
                case.remove(marker)
    cases, warnings = read_junit(ET.tostring(tree.getroot(), encoding="unicode"), "stripped.xml")
    assert len(cases) == 4
    assert len(warnings) == 1
    assert "failures=0, errors=0" in warnings[0]


def test_surefire_attempts_reconcile_without_becoming_extra_test_runs() -> None:
    path = ROOT / "examples/retry_history/surefire-001/report.xml"
    cases, warnings = parse_junit_file(path)
    assert warnings == []
    assert len(cases) == 6
    assert sum(case.retry.attempts if case.retry else 1 for case in cases) == 13
    tree = ET.parse(path)
    retried = tree.find(".//testcase[rerunFailure]")
    assert retried is not None
    marker = retried.find("rerunFailure")
    assert marker is not None
    retried.remove(marker)
    altered, warnings = read_junit(ET.tostring(tree.getroot(), encoding="unicode"), "retry.xml")
    assert len(altered) == 6
    assert len(warnings) == 1
    assert "explicit attempts (tests=12" in warnings[0]


def test_counter_convention_must_match_as_a_whole() -> None:
    # One recovered testcase, three attempts, two failures. Mixing a testcase
    # total with attempt failures cannot explain a coherent set of counters.
    _, warnings = read_junit(
        '<testsuite tests="1" failures="2"><testcase name="a">'
        "<flakyFailure/><flakyFailure/></testcase></testsuite>",
        "mixed.xml",
    )
    assert len(warnings) == 1


@pytest.mark.parametrize("run", ["run-01", "run-03"])
def test_googletest_disabled_counter_is_not_a_skip_count(run: str) -> None:
    # GoogleTest still reports disabled=2 when those tests were explicitly run.
    cases, warnings = parse_junit_file(ROOT / "examples/googletest_history" / run / "report.xml")
    assert warnings == []
    assert len(cases) == 5


def test_multiple_assertions_count_as_one_failed_test() -> None:
    cases, warnings = read_junit(
        '<testsuite tests="1" failures="1"><testcase name="a" status="run" result="completed">'
        "<failure>assertion one</failure><failure>assertion two</failure></testcase></testsuite>",
        "assertions.xml",
    )
    assert warnings == []
    assert cases[0].status == Status.FAIL


def test_runtime_skip_attribute_can_supply_a_skipped_counter_without_a_child() -> None:
    cases, warnings = read_junit(
        '<testsuite tests="1" skipped="1"><testcase name="a" status="run" result="skipped"/>'
        "</testsuite>",
        "skip.xml",
    )
    assert warnings == []
    assert cases[0].status == Status.SKIP


def test_pytest_subtest_counters_remain_unreconciled_without_inventing_subtests() -> None:
    cases, warnings = parse_junit_file(CAPTURES / "complex.xml")
    assert len(cases) == 8
    assert len(warnings) == 1
    assert "declares tests=11, failures=5" in warnings[0]
    assert "unsupported counting convention" in warnings[0]
    assert next(case for case in cases if case.name == "test_subtests").status == Status.FAIL


def test_nested_namespace_totals_check_descendants_once_and_each_sibling_separately() -> None:
    raw = (
        '<testsuites xmlns="urn:junit" tests="2" failures="1"><testsuite name="a" tests="1" failures="0">'
        '<testcase name="a"/></testsuite><testsuite name="b" tests="1" failures="1">'
        '<testcase name="b"><failure/></testcase></testsuite></testsuites>'
    )
    cases, warnings = read_junit(raw, "nested.xml")
    assert len(cases) == 2
    assert warnings == []
    # Totals still agree at the root, but the failure was reassigned between suites.
    _, warnings = read_junit(
        raw.replace('name="a" tests="1" failures="0"', 'name="a" tests="1" failures="1"').replace(
            'name="b" tests="1" failures="1"', 'name="b" tests="1" failures="0"'
        ),
        "siblings.xml",
    )
    assert len(warnings) == 1
    assert "in 2 container(s)" in warnings[0]
    assert "<testsuites> #1" not in warnings[0]
    _, warnings = read_junit(raw.replace('tests="2"', 'tests="3"', 1), "root.xml")
    assert "<testsuites> #1" in warnings[0]


def test_nested_payloads_cannot_satisfy_a_summary_counter() -> None:
    cases, warnings = read_junit(
        '<testsuite tests="2"><properties><testcase name="fake"/></properties>'
        '<system-out><![CDATA[<testcase name="fake"/>]]></system-out>'
        '<testcase name="real"/></testsuite>',
        "payload.xml",
    )
    assert [case.name for case in cases] == ["real"]
    assert "testcase records (tests=1)" in warnings[0]


@pytest.mark.parametrize("raw", ["-1", "1.0", "NaN", "1e3", "", "9" * 10_000, "\u0661"])
def test_malformed_counter_is_bounded_and_incomplete(raw: str) -> None:
    cases, warnings = read_junit(
        f'<testsuite tests="{raw}"><testcase name="a"/></testsuite>', "invalid.xml"
    )
    assert len(cases) == 1
    assert len(warnings) == 1
    assert "nonnegative integer" in warnings[0]
    assert len(warnings[0]) < 600


def test_missing_counters_are_optional_and_zero_is_checked() -> None:
    for attrs in ("", 'tests="+01"', 'errors="0" failures="0"', 'tests=" 1 "'):
        _, warnings = read_junit(f'<testsuite {attrs}><testcase name="a"/></testsuite>', "a.xml")
        assert warnings == []
    _, warnings = read_junit('<testsuite tests="0"><testcase name="a"/></testsuite>', "zero.xml")
    assert len(warnings) == 1


def test_warning_details_are_bounded_but_every_container_is_checked() -> None:
    raw = (
        "<testsuites>"
        + "".join(
            f'<testsuite name="s{i}" tests="2"><testcase name="a"/></testsuite>' for i in range(100)
        )
        + "</testsuites>"
    )
    cases, warnings = read_junit(raw, "large.xml")
    assert len(cases) == 100
    assert len(warnings) == 1
    assert "in 100 container(s)" in warnings[0]
    assert "97 more container(s) not shown" in warnings[0]
    assert len(warnings[0]) < 1000


def test_completed_summary_survives_later_xml_error() -> None:
    cases, warnings = read_junit(
        '<testsuites><testsuite tests="2"><testcase name="a"/></testsuite><broken>', "partial.xml"
    )
    assert len(cases) == 1
    assert any("summary counters" in warning for warning in warnings)
    assert any("not well-formed XML" in warning for warning in warnings)
