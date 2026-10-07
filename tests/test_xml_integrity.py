"""XML recovery must not invent tests from logs, comments or broken byte sequences."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from flakemap.loader import load_runs
from flakemap.models import Run, RunMetadata, Status
from flakemap.parse import junit, trx, xmlinput
from flakemap.parse.junit import parse_junit_file, read_junit
from flakemap.parse.trx import parse_trx_file
from flakemap.report import render_html, to_json_dict
from flakemap.stats import analyze


def test_truncated_report_does_not_promote_comment_or_cdata_examples() -> None:
    fake = '<testcase name="imaginary"><failure message="not a result"/></testcase>'
    raw = '<testsuite name="real"><testcase name="actual"></testcase>'
    raw += f"<!-- {fake} --><system-out><![CDATA[{fake}]]></system-out>"
    cases, warnings = read_junit(raw, "partial.xml")
    assert [(case.full_name, case.status) for case in cases] == [("real.actual", Status.PASS)]
    assert warnings and "salvaged 1" in warnings[0]


def test_complete_testcases_in_an_unclosed_suite_are_retained_with_context() -> None:
    raw = '<testsuites><testsuite name="closed"><testcase name="first"/></testsuite>'
    raw += '<testsuite name="unclosed"><testcase name="last"><failure message="actual failure"/></testcase>'
    cases, warnings = read_junit(raw, "partial.xml")
    assert [case.full_name for case in cases] == ["closed.first", "unclosed.last"]
    assert cases[1].status is Status.FAIL
    assert cases[1].source is not None and cases[1].source.testcase == 2
    assert "salvaged 2" in warnings[0]


def test_recovery_stops_at_the_first_syntax_error() -> None:
    raw = (
        '<testsuite><testcase name="first"/><broken></mismatch><testcase name="later"/></testsuite>'
    )
    cases, warnings = read_junit(raw, "partial.xml")
    assert [case.name for case in cases] == ["first"]
    assert "remainder omitted" in warnings[0]


def test_an_unfinished_case_is_not_filled_in_as_a_pass() -> None:
    cases, warnings = read_junit(
        '<testsuite><testcase name="unknown"><failure message="cut', "partial.xml"
    )
    assert cases == []
    assert warnings


@pytest.mark.parametrize("partial", [False, True])
def test_namespaces_preserve_outcomes_and_retry_evidence(partial: bool) -> None:
    raw = '<j:testsuite xmlns:j="urn:synthetic-junit" name="namespaced">'
    raw += '<j:testcase name="fails"><j:failure message="expected"/></j:testcase>'
    raw += '<j:testcase name="recovers"><j:flakyFailure message="retry"/></j:testcase>'
    if not partial:
        raw += "</j:testsuite>"
    cases, warnings = read_junit(raw, "namespaced.xml")
    assert [case.status for case in cases] == [Status.FAIL, Status.PASS]
    assert cases[0].full_name == "namespaced.fails"
    assert cases[1].retry is not None and cases[1].retry.attempts == 2
    assert bool(warnings) == partial


@pytest.mark.parametrize(
    "encoding",
    [
        "utf-8-sig",
        "utf-16",
        "utf-16-le",
        "utf-16-be",
        "utf-32",
        "utf-32-le",
        "utf-32-be",
        "iso-8859-1",
        "windows-1252",
    ],
)
@pytest.mark.parametrize("kind", ["junit", "trx"])
def test_encoding_and_xml_declaration_preserve_identifiers(
    encoding: str, kind: str, tmp_path: Path
) -> None:
    declaration = "utf-8" if encoding == "utf-8-sig" else encoding
    body = (
        '<TestRun><Results><UnitTestResult testName="C.café" outcome="Failed"/></Results></TestRun>'
        if kind == "trx"
        else '<testsuite><testcase classname="C" name="café"><failure/></testcase></testsuite>'
    )
    raw = f'<?xml version="1.0" encoding="{declaration}"?>' + body
    path = tmp_path / "report.xml"  # TRX must be sniffed even with this extension
    path.write_bytes(raw.encode(encoding))
    runs = load_runs(tmp_path)
    assert runs[0].warnings == []
    assert [(case.full_name, case.status) for case in runs[0].testcases] == [
        ("C.café", Status.FAIL)
    ]


def test_long_comment_before_trx_does_not_hide_its_format(tmp_path: Path) -> None:
    raw = (
        "<!--"
        + "comment " * 10_000
        + '--><TestRun><Results><UnitTestResult testName="real" outcome="Failed"/></Results></TestRun>'
    )
    (tmp_path / "long-comment.xml").write_text(raw)
    runs = load_runs(tmp_path)
    assert len(runs) == 1
    assert runs[0].warnings == []
    assert runs[0].testcases[0].status is Status.FAIL


@pytest.mark.parametrize("complete", [False, True])
def test_deferred_xml_events_are_read_even_when_eof_is_malformed(complete: bool) -> None:
    raw = '<testsuite name="real"><!--' + "comment " * 10_000
    raw += '--><testcase name="after_comment"><failure/></testcase>'
    if complete:
        raw += "</testsuite>"
    cases, warnings = read_junit(raw, "deferred.xml")
    assert [(case.full_name, case.status) for case in cases] == [
        ("real.after_comment", Status.FAIL)
    ]
    assert bool(warnings) is not complete


@pytest.mark.parametrize("kind", ["junit", "trx"])
def test_repaired_identity_is_not_evidence_of_a_healthy_test(kind: str) -> None:
    if kind == "junit":
        cases, warnings = read_junit(
            '<testsuite><testcase name="bad&#1;"><flakyFailure/></testcase></testsuite>',
            "repair.xml",
        )
    else:
        cases, warnings, _ = trx.read_trx(
            '<TestRun><Results><UnitTestResult testName="bad&#1;" outcome="Passed"/></Results></TestRun>',
            "repair.trx",
        )
    assert cases[0].status is Status.UNKNOWN
    assert "cannot compare" in (cases[0].issue or "")
    assert len(warnings) == 2
    runs = [Run(metadata=RunMetadata(run_id="r", sequence=0), testcases=cases, path=Path("r.xml"))]
    result = analyze(runs)
    assert result.tests[0].n == 0
    assert result.tests[0].recovered_runs == 0
    assert 'class="cell s-unknown" role="img"' in render_html(result, runs)


@pytest.mark.parametrize("declaration", ["not-an-encoding", "base64_codec", "unicode_escape"])
def test_unsupported_encoding_is_not_guessed(tmp_path: Path, declaration: str) -> None:
    path = tmp_path / "report.xml"
    path.write_bytes(
        f'<?xml version="1.0" encoding="{declaration}"?><testsuite><testcase name="test"/></testsuite>'.encode()
    )
    cases, warnings = parse_junit_file(path)
    assert cases == [] and "unsupported" in warnings[0]


@pytest.mark.parametrize("kind", ["junit", "trx"])
def test_lossy_decoding_cannot_merge_distinct_test_identities(kind: str, tmp_path: Path) -> None:
    for i, invalid in enumerate([b"\xff", b"\xfe"]):
        directory = tmp_path / str(i)
        directory.mkdir()
        (directory / "meta.json").write_text(json.dumps({"sequence": i}))
        raw = (
            b'<TestRun><Results><UnitTestResult testName="bad'
            + invalid
            + b'" outcome="Passed"/></Results></TestRun>'
            if kind == "trx"
            else b'<testsuite><testcase name="bad' + invalid + b'"/></testsuite>'
        )
        path = directory / ("r.trx" if kind == "trx" else "r.xml")
        path.write_bytes(raw)
        cases = parse_trx_file(path)[0] if kind == "trx" else parse_junit_file(path)[0]
        assert cases[0].status is Status.UNKNOWN
    payload = to_json_dict(analyze(load_runs(tmp_path)))
    assert payload["tests"][0]["runs"]["total"] == 0
    assert payload["tests"][0]["runs"]["unknown"] == 2
    assert payload["summary"]["input_complete"] is False


def test_a_literal_replacement_character_is_not_itself_a_decode_error(tmp_path: Path) -> None:
    path = tmp_path / "r.xml"
    path.write_text('<testsuite><testcase name="literal-\ufffd"/></testsuite>', encoding="utf-8")
    (case,), warnings = parse_junit_file(path)
    assert case.status is Status.PASS
    assert not warnings


@pytest.mark.parametrize("kind", ["junit", "trx"])
def test_doctype_examples_in_text_are_not_executable_declarations(kind: str) -> None:
    example = '<!DOCTYPE example [<!ENTITY example "text">]>'
    if kind == "junit":
        cases, warnings = read_junit(
            f'<testsuite><!--{example}--><testcase name="real"/><system-out><![CDATA[{example}]]></system-out></testsuite>',
            "example.xml",
        )
    else:
        cases, warnings, _ = trx.read_trx(
            f'<TestRun><!--{example}--><Results><UnitTestResult testName="real" outcome="Passed"/></Results><Output><![CDATA[{example}]]></Output></TestRun>',
            "example.trx",
        )
    assert len(cases) == 1 and cases[0].status is Status.PASS
    assert not warnings


def test_deep_truncation_is_bounded_and_retains_completed_prefix() -> None:
    raw = '<testsuite><testcase name="completed"/>' + "<testsuite>" * 100_000
    cases, warnings = read_junit(raw, "deep.xml")
    assert [case.name for case in cases] == ["completed"]
    assert any("level limit" in warning for warning in warnings)


def test_element_limit_is_visible_in_both_parsers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(junit, "MAX_XML_ELEMENTS", 3)
    cases, warnings = read_junit(
        '<testsuite><testcase name="one"/><testcase name="two"/><testcase name="three"/></testsuite>',
        "limited.xml",
    )
    assert [case.name for case in cases] == ["one", "two"]
    assert any("element limit" in warning for warning in warnings)
    monkeypatch.setattr(trx, "MAX_XML_ELEMENTS", 2)
    cases, warnings, _ = trx.read_trx(
        '<TestRun><Results><UnitTestResult testName="one" outcome="Passed"/></Results></TestRun>',
        "limited.trx",
    )
    assert cases == [] and "element limit" in warnings[0]


def test_report_byte_limit_precedes_parsing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(xmlinput, "MAX_REPORT_BYTES", 20)
    path = tmp_path / "large.xml"
    path.write_text('<testsuite><testcase name="real"/></testsuite>')
    cases, warnings = parse_junit_file(path)
    assert cases == [] and "byte limit" in warnings[0]


def test_anonymous_junit_records_do_not_acquire_a_shared_identity() -> None:
    (case,), warnings = read_junit("<testsuite><testcase/></testsuite>", "anonymous.xml")
    assert case.status is Status.UNKNOWN
    assert "missing JUnit test name" in str(case.issue)
    assert warnings
