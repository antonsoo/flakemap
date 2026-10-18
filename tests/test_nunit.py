"""Native NUnit case identities, verdicts and suite failures stay separate evidence."""

from __future__ import annotations

import copy
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from flakemap.loader import load_runs
from flakemap.models import Status
from flakemap.parse import xmlinput
from flakemap.parse.nunit import is_nunit, parse_nunit_file, read_nunit
from flakemap.stats import analyze

STUDY = Path(__file__).resolve().parents[1] / "studies/nunit3"


@pytest.mark.parametrize("capture", ["captured-v3", "captured-v4"])
def test_native_nunit_cases_keep_full_identity_and_recorded_result(capture: str) -> None:
    cases, warnings, started = parse_nunit_file(STUDY / capture / "all/Capture.xml")
    expected = {
        "BrokenSetup.NeverReachedA": Status.ERROR,
        "BrokenSetup.NeverReachedB": Status.ERROR,
        "BrokenTeardown.PassedBody": Status.PASS,
        "InvalidSignature.MissingArgument": Status.ERROR,
        "MultipleAssertions.TwoFailures": Status.FAIL,
        "Outcomes.Error": Status.ERROR,
        "Outcomes.Explicit": Status.SKIP,
        "Outcomes.Failure": Status.FAIL,
        "Outcomes.Ignored": Status.SKIP,
        "Outcomes.Inconclusive": Status.UNKNOWN,
        'Outcomes.row.with.dots("a.b")': Status.PASS,
        'Outcomes.row.with.dots("x,y")': Status.PASS,
        "Outcomes.Pass": Status.PASS,
        "Outcomes.RetryRecovered": Status.PASS,
        "Outcomes.Skipped": Status.SKIP,
        "Outcomes.Warning": Status.UNKNOWN,
        "Pair<Int32,Double>.Check": Status.FAIL,
        "Pair<Int32,String>.Check": Status.PASS,
    }
    assert {case.full_name: case.status for case in cases} == {
        f"NativeNUnit.{name}": status for name, status in expected.items()
    }
    assert started is not None and started.utcoffset() is not None
    assert [case.source.testcase for case in cases if case.source] == list(range(1, 19))
    assert not any("counters do not reconcile" in warning for warning in warnings)
    assert any("BrokenTeardown" in warning and "TearDown" in warning for warning in warnings)
    setup = next(case for case in cases if case.name == "NeverReachedA")
    assert setup.message and "site=Parent" in setup.message and "OneTimeSetUp" in setup.message


@pytest.mark.parametrize("capture", ["captured-v3", "captured-v4"])
def test_native_filters_do_not_turn_discovery_count_into_missing_executions(capture: str) -> None:
    folder = STUDY / capture / "pass-filter"
    root = ET.parse(folder / "Capture.xml").getroot()
    assert (root.get("testcasecount"), root.get("total")) == ("18", "1")
    runs = load_runs(folder)
    assert len(runs) == 1 and runs[0].warnings == []
    assert runs[0].metadata.source == "report"
    assert runs[0].metadata.timestamp is not None
    result = analyze(runs)
    assert [(test.full_name, test.n, test.n_fail) for test in result.tests] == [
        ("NativeNUnit.Outcomes.Pass", 1, 0)
    ]
    assert not result.warnings


@pytest.mark.parametrize("capture", ["captured-v3", "captured-v4"])
def test_native_teardown_failure_does_not_fabricate_an_extra_failed_test(capture: str) -> None:
    runs = load_runs(STUDY / capture / "teardown-filter")
    result = analyze(runs)
    assert len(runs[0].testcases) == len(result.tests) == 1
    assert (result.tests[0].n, result.tests[0].n_pass, result.tests[0].n_fail) == (1, 1, 0)
    assert any(
        "TearDown" in warning and "Controlled one-time teardown failure" in warning
        for warning in result.warnings
    )


@pytest.mark.parametrize("capture", ["captured-v3", "captured-v4"])
def test_native_final_pass_does_not_establish_recovered_retry_history(capture: str) -> None:
    (case,), warnings, _ = parse_nunit_file(STUDY / capture / "retry-filter/Capture.xml")
    assert case.status is Status.PASS and case.retry is None and not warnings
    (test,) = analyze(load_runs(STUDY / capture / "retry-filter")).tests
    assert test.n == 1 and test.recovered_runs == test.exhausted_runs == 0


def test_native_missing_failed_case_is_a_counter_coverage_warning() -> None:
    root = ET.parse(STUDY / "captured-v3/pairs-filter/Capture.xml").getroot()
    for parent in root.iter():
        for child in list(parent):
            if child.tag == "test-case" and child.get("result") == "Failed":
                parent.remove(child)
    cases, warnings, _ = read_nunit(ET.tostring(root, encoding="unicode"), "pruned.xml")
    assert len(cases) == 1 and cases[0].status is Status.PASS
    assert any(
        "counters do not reconcile" in warning and "failed=1" in warning for warning in warnings
    )


def test_false_green_result_cannot_hide_native_failure_assertions() -> None:
    root = ET.parse(STUDY / "captured-v3/pairs-filter/Capture.xml").getroot()
    failed = next(case for case in root.iter("test-case") if case.get("result") == "Failed")
    failed.set("result", "Passed")
    cases, warnings, _ = read_nunit(ET.tostring(root, encoding="unicode"), "contradictory.xml")
    damaged = next(case for case in cases if "Double" in case.full_name)
    assert damaged.status is Status.UNKNOWN and damaged.issue
    assert "conflicts with recorded failure" in damaged.issue
    assert any("counters do not reconcile" in warning for warning in warnings)


def test_copied_native_case_identity_is_ambiguous_not_a_retry(tmp_path: Path) -> None:
    root = ET.parse(STUDY / "captured-v3/pass-filter/Capture.xml").getroot()
    case = next(root.iter("test-case"))
    parent = next(node for node in root.iter() if case in list(node))
    duplicate = copy.deepcopy(case)
    duplicate.set("id", "another-generated-id")
    parent.append(duplicate)
    ET.ElementTree(root).write(tmp_path / "duplicate.xml")
    (test,) = analyze(load_runs(tmp_path)).tests
    assert test.n == test.recovered_runs == test.exhausted_runs == 0
    assert test.n_unknown == 1
    assert "2 records share" in test.excluded_observations[0].result.issue


def test_opaque_output_and_filter_payloads_never_become_test_results() -> None:
    raw = """<?xml version="1.0"?><test-run total="1" passed="1">
      <filter><test-case fullname="NotAResult.Filter" result="Failed"/></filter>
      <output><test-case fullname="NotAResult.Output" result="Failed"/></output>
      <test-suite total="1" passed="1"><test-case fullname="Actual.Pass" result="Passed"/>
        <output><![CDATA[<test-case fullname="NotAResult.Cdata" result="Failed"/>]]></output>
      </test-suite></test-run>"""
    cases, warnings, _ = read_nunit(raw, "opaque.xml")
    assert [(case.full_name, case.status) for case in cases] == [("Actual.Pass", Status.PASS)]
    assert warnings == []
    assert is_nunit("<!-- <TestRun/> -->\n" + raw)
    assert not is_nunit("<testsuite><output><![CDATA[<test-run/>]]></output></testsuite>")


@pytest.mark.parametrize("result", [None, "Inconclusive", "Warning", "FutureResult"])
def test_only_declared_supported_results_establish_a_trial(result: str | None) -> None:
    root = ET.Element("test-run")
    case = ET.SubElement(root, "test-case", fullname="Example.Check")
    if result is not None:
        case.set("result", result)
    (parsed,), warnings, _ = read_nunit(ET.tostring(root, encoding="unicode"), "unknown.xml")
    assert parsed.status is Status.UNKNOWN and parsed.issue and warnings


def test_missing_fullname_does_not_merge_open_generic_class_names() -> None:
    raw = (
        '<test-run><test-case name="Check" classname="Example.Pair`2" result="Passed"/></test-run>'
    )
    (case,), warnings, _ = read_nunit(raw, "identity.xml")
    assert case.status is Status.UNKNOWN and "missing NUnit fullname" in (case.issue or "")
    assert warnings


def test_nunit_complete_document_limits_and_encoding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    text = '<test-run><test-case fullname="Example.Check" result="Passed"/></test-run>'
    path = tmp_path / "unicode.xml"
    path.write_bytes(text.encode("utf-16"))
    (case,), warnings, _ = parse_nunit_file(path)
    assert case.status is Status.PASS and not warnings
    assert not read_nunit(text[:-11], "truncated.xml")[0]
    assert not read_nunit('<!DOCTYPE test-run [<!ENTITY x "x">]>' + text, "dtd.xml")[0]
    monkeypatch.setattr(xmlinput, "MAX_XML_ELEMENTS", 1)
    cases, warnings, _ = read_nunit(text, "bounded.xml")
    assert not cases and any("element limit" in warning for warning in warnings)
