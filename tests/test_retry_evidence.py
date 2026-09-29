"""Real reporter evidence plus adversarial histories that used to look healthy."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from flakemap.cli import main
from flakemap.loader import load_runs
from flakemap.models import Status
from flakemap.parse.junit import parse_junit_file
from flakemap.report.html_out import render_html
from flakemap.report.json_out import to_json_dict
from flakemap.report.markdown_out import render_markdown
from flakemap.stats.analyze import analyze

REAL_HISTORY = Path(__file__).parents[1] / "examples/retry_history"


def write_report(
    root: Path, name: str, cases: str, *, sequence: int = 1, **metadata: object
) -> Path:
    report = root / name
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(f'<testsuite name="suite">{cases}</testsuite>', encoding="utf-8")
    report.with_suffix(".meta.json").write_text(
        json.dumps({"sequence": sequence, **metadata}), encoding="utf-8"
    )
    return report


def case(body: str = "", *, name: str = "check", time: str = "0.1") -> str:
    return f'<testcase name="{name}" classname="pkg.Tests" time="{time}">{body}</testcase>'


def test_real_surefire_retries_are_evidence_not_extra_trials() -> None:
    runs = load_runs(REAL_HISTORY)
    result = analyze(runs)
    tests = {t.full_name.rsplit(".", 1)[-1]: t for t in result.tests}
    assert len(tests) == 6  # XML suite counter is 13, because it includes attempts.
    recovered = tests["recoversAfterTwoFailures"]
    assert recovered.classification == "flaky"
    assert (recovered.n, recovered.n_pass, recovered.n_fail) == (1, 1, 0)
    assert recovered.failure_rate.point == 0
    assert recovered.failure_rate.high > 0.79  # one green run is very weak rate evidence
    assert recovered.flakiness_score > 0
    assert recovered.recovered_runs == 1
    record = recovered.retry_observations[0].result
    assert record.retry is not None
    assert record.retry.attempts == 3
    assert [f.tag for f in record.retry.failures] == ["flakyFailure", "flakyFailure"]
    assert [f.message for f in record.retry.failures] == ["connection not ready"] * 2
    assert record.source is not None
    assert record.source.report == "surefire-001/report.xml"
    assert record.source.testcase == 5
    assert tests["recoversFromError"].recovered_runs == 1
    for name in ("alwaysFails", "alwaysErrors"):
        t = tests[name]
        assert (t.n, t.n_fail, t.exhausted_runs, t.recovered_runs) == (1, 1, 1, 0)
        assert t.classification == "insufficient_data"
        assert t.retry_observations[0].result.retry.attempts == 3
    assert tests["alwaysPasses"].recovered_runs == 0
    assert tests["skipped"].n == 0
    assert result.warnings == []


@pytest.mark.parametrize("tag", ["flakyFailure", "flakyError"])
def test_nested_stacktrace_fallback_and_unknown_attempt_duration(tmp_path: Path, tag: str) -> None:
    path = write_report(
        tmp_path, "r.xml", case(f"<{tag}><stackTrace>first line\nsecond line</stackTrace></{tag}>")
    )
    cases, warnings = parse_junit_file(path)
    assert not warnings
    assert cases[0].retry.failures[0].message == "first line"
    result = analyze(load_runs(tmp_path))
    assert result.tests[0].duration_trend is None
    evidence = to_json_dict(result)["tests"][0]["retries"]["evidence"][0]["records"][0]
    assert evidence["reported_duration_seconds"] == 0.1
    assert "duration" not in evidence["retry"]["failures"][0]


@pytest.mark.parametrize(
    "body",
    [
        "<failure/><flakyFailure/>",
        "<skipped/><flakyError/>",
        "<flakyFailure/><rerunFailure/>",
        "<rerunFailure/>",
        "<skipped/><rerunError/>",
        "<failure/><error/><rerunFailure/>",
        "<failure/><skipped/>",
    ],
)
def test_contradictory_outcomes_remain_unknown(tmp_path: Path, body: str) -> None:
    path = write_report(tmp_path, "r.xml", case(body))
    cases, warnings = parse_junit_file(path)
    assert warnings
    assert cases[0].status == Status.UNKNOWN
    assert cases[0].retry is None
    result = analyze(load_runs(tmp_path))
    t = result.tests[0]
    assert (t.n, t.n_unknown, t.recovered_runs) == (0, 1, 0)
    assert to_json_dict(result)["tests"][0]["failure_rate"] is None
    assert "s-unknown" in render_html(result, load_runs(tmp_path))


@pytest.mark.parametrize("time", ["NaN", "Infinity", "-1", "invalid", "1e308"])
def test_invalid_durations_cannot_produce_non_json_numbers(tmp_path: Path, time: str) -> None:
    write_report(tmp_path, "r.xml", case("<flakyFailure/>", time=time))
    data = to_json_dict(analyze(load_runs(tmp_path)))
    record = data["tests"][0]["retries"]["evidence"][0]["records"][0]
    assert record["reported_duration_seconds"] is None
    json.dumps(data, allow_nan=False)


def test_nested_suites_preserve_all_cases_and_document_order(tmp_path: Path) -> None:
    path = tmp_path / "nested.xml"
    path.write_text(
        '<testsuites><testcase name="root"/><testsuite name="outer">'
        '<testcase name="one"/><testsuite name="inner"><testcase name="two">'
        "<flakyFailure/></testcase></testsuite></testsuite></testsuites>"
    )
    cases, warnings = parse_junit_file(path)
    assert not warnings
    assert [(c.full_name, c.source.testcase) for c in cases] == [
        ("root", 1),
        ("outer.one", 2),
        ("inner.two", 3),
    ]


@pytest.mark.parametrize("second_body", ["", "<failure/>", "<flakyFailure/>"])
def test_duplicate_records_are_excluded_not_guessed_as_retries(
    tmp_path: Path, second_body: str
) -> None:
    write_report(tmp_path, "run/a.xml", case(), commit="same")
    write_report(tmp_path, "run/b.xml", case(second_body), commit="same")
    runs = load_runs(tmp_path)
    result = analyze(runs)
    t = result.tests[0]
    assert len(runs) == 1
    assert (t.n, t.n_unknown, t.recovered_runs, t.rerun_commits_total) == (0, 1, 0, 0)
    data = to_json_dict(result)
    sources = [r["source"]["report"] for r in data["tests"][0]["excluded"][0]["records"]]
    assert sources == ["run/a.xml", "run/b.xml"]
    html = render_html(result, runs)
    assert html.count('class="cell s-unknown" role="img"') == 1
    assert "duplicate artifacts" in html
    assert "run/a.xml" in html and "run/b.xml" in html


def test_exclusion_does_not_erase_usable_history_or_bridge_a_flip(tmp_path: Path) -> None:
    write_report(tmp_path, "r1.xml", case(), sequence=1)
    write_report(tmp_path, "r2.xml", case() + case("<failure/>"), sequence=2)
    write_report(tmp_path, "r3.xml", case("<failure/>"), sequence=3)
    t = analyze(load_runs(tmp_path)).tests[0]
    assert (t.n, t.n_unknown, t.n_pass, t.n_fail) == (2, 1, 1, 1)
    assert t.flip_pairs == 0
    assert t.flip_rate == 0
    assert t.change_point is None


def test_incomplete_green_history_does_not_get_a_healthy_label(tmp_path: Path) -> None:
    for i in range(6):
        write_report(tmp_path, f"r{i}.xml", case(), sequence=i)
    write_report(tmp_path, "r6.xml", case() + case("<failure/>"), sequence=6)
    t = analyze(load_runs(tmp_path)).tests[0]
    assert t.n == 6
    assert t.classification == "insufficient_data"


def test_distinct_shards_merge_without_inflating_per_test_samples(tmp_path: Path) -> None:
    write_report(tmp_path, "run/a.xml", case(name="one"))
    write_report(tmp_path, "run/b.xml", case(name="two"))
    result = analyze(load_runs(tmp_path))
    assert result.total_runs == 1
    assert len(result.tests) == 2
    assert [t.n for t in result.tests] == [1, 1]
    assert result.warnings == []


@pytest.mark.parametrize("field", ["commit", "branch", "runner", "os", "sequence", "timestamp"])
def test_conflicting_shard_metadata_excludes_the_run(tmp_path: Path, field: str) -> None:
    values = (
        (1, 2)
        if field == "sequence"
        else (
            ("2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z") if field == "timestamp" else ("a", "b")
        )
    )
    write_report(tmp_path, "run/a.xml", case(name="one"), **{field: values[0]})
    write_report(tmp_path, "run/b.xml", case(name="two"), **{field: values[1]})
    result = analyze(load_runs(tmp_path))
    assert all(t.n == 0 and t.n_unknown == 1 for t in result.tests)
    assert any(f"disagree on {field}" in w for w in result.warnings)


def test_sequence_is_not_overridden_by_reversed_filesystem_times(tmp_path: Path) -> None:
    first = write_report(tmp_path, "z.xml", case(), sequence=1)
    second = write_report(tmp_path, "a.xml", case("<failure/>"), sequence=2)
    os.utime(first, (200, 200))
    os.utime(second, (100, 100))
    runs = load_runs(tmp_path)
    assert [r.metadata.run_id for r in runs] == ["z", "a"]
    assert all(r.metadata.timestamp is None for r in runs)
    assert analyze(runs).warnings == []


def test_nested_shards_inherit_run_metadata(tmp_path: Path) -> None:
    p = tmp_path / "run/shards/unit.xml"
    p.parent.mkdir(parents=True)
    p.write_text(f"<testsuite>{case()}</testsuite>")
    (tmp_path / "run/meta.json").write_text('{"commit":"abc","sequence":7}')
    runs = load_runs(tmp_path)
    assert runs[0].metadata.commit == "abc"
    assert runs[0].metadata.sequence == 7
    assert runs[0].metadata.timestamp is None


def test_same_commit_different_platforms_is_not_rerun_disagreement(tmp_path: Path) -> None:
    write_report(tmp_path, "linux.xml", case(), commit="abc", os="linux")
    write_report(
        tmp_path, "windows.xml", case("<failure/>"), sequence=2, commit="abc", os="windows"
    )
    t = analyze(load_runs(tmp_path)).tests[0]
    assert t.rerun_commits_total == 0
    assert t.rerun_signal == 0


def test_same_context_reruns_still_supply_evidence(tmp_path: Path) -> None:
    write_report(tmp_path, "first.xml", case("<failure/>"), commit="abc", os="linux")
    write_report(tmp_path, "second.xml", case(), sequence=2, commit="abc", os="linux")
    t = analyze(load_runs(tmp_path)).tests[0]
    assert (t.rerun_commits_total, t.rerun_commits_flaky, t.rerun_signal) == (1, 1, 1)


def test_json_and_html_stay_valid_when_retry_gate_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    report = tmp_path / "report.html"
    code = main([str(REAL_HISTORY), "--json", "--html", str(report), "--fail-on-retry"])
    out = capsys.readouterr()
    data = json.loads(out.out)
    assert code == 1
    assert data["schema_version"] == 2
    assert data["summary"]["recovered_test_runs"] == 2
    assert data["summary"]["exhausted_test_runs"] == 2
    assert "passed-on-retry" in out.err
    assert "Recorded evidence" in report.read_text()


def test_machine_output_stays_json_when_change_point_gate_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    for i in range(18):
        write_report(tmp_path, f"r{i}.xml", case("<failure/>" if i >= 10 else ""), sequence=i)
    assert main([str(tmp_path), "--json", "--fail-on-new-flake"]) == 1
    out = capsys.readouterr()
    assert json.loads(out.out)["summary"]["broken"] == 1
    assert "new flake" in out.err


def test_salvage_is_visible_in_all_reports_and_can_fail_ci(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = write_report(tmp_path, "r.xml", case())
    path.write_text(path.read_text().replace("</testsuite>", ""))
    assert main([str(tmp_path), "--json", "--fail-on-incomplete"]) == 2
    assert json.loads(capsys.readouterr().out)["warnings"]
    runs = load_runs(tmp_path)
    result = analyze(runs)
    assert "salvaged" in render_html(result, runs)
    assert "salvaged" in render_markdown(result)


@pytest.mark.parametrize(
    "xml",
    ["garbage", "<testsuite/>", '<testsuite><testcase name="s"><skipped/></testcase></testsuite>'],
)
def test_no_usable_evidence_cannot_exit_success(
    tmp_path: Path, xml: str, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "r.xml").write_text(xml)
    assert main([str(tmp_path), "--json"]) == 2
    assert "no usable" in capsys.readouterr().err


def test_incomplete_gate_takes_precedence_over_retry_gate(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_report(tmp_path, "r.xml", case("<flakyFailure/>") + case(name="duplicate") * 2)
    assert main([str(tmp_path), "--json", "--fail-on-retry", "--fail-on-incomplete"]) == 2
    assert json.loads(capsys.readouterr().out)["summary"]["excluded_test_runs"] == 1


def test_retry_gate_ignores_exhausted_and_ordinary_passes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_report(tmp_path, "r.xml", case("<failure/><rerunFailure/>") + case(name="clean"))
    assert main([str(tmp_path), "--fail-on-retry", "--fail-on-incomplete"]) == 0


def test_report_evidence_escapes_user_text(tmp_path: Path) -> None:
    write_report(
        tmp_path,
        "r.xml",
        case(
            '<flakyFailure message="&lt;img src=x onerror=alert(1)&gt;"/>',
            name="pipe|`&lt;script&gt;",
        ),
    )
    runs = load_runs(tmp_path)
    result = analyze(runs)
    html = render_html(result, runs)
    assert "<img src=x" not in html
    assert "&lt;img src=x" in html
    assert "<script>" not in html
    markdown = render_markdown(result)
    assert "pipe&#124;&#96;&lt;script&gt;" in markdown


def test_dotted_name_collision_cannot_join_distinct_tests(tmp_path: Path) -> None:
    write_report(tmp_path, "r1.xml", '<testcase classname="a.b" name="c"/>')
    write_report(
        tmp_path, "r2.xml", '<testcase classname="a" name="b.c"><failure/></testcase>', sequence=2
    )
    runs = load_runs(tmp_path)
    result = analyze(runs)
    assert result.tests[0].n == 0
    assert result.tests[0].n_unknown == 2
    html = render_html(result, runs)
    assert html.count('class="cell s-unknown" role="img"') == 2
    records = [o["records"][0] for o in to_json_dict(result)["tests"][0]["excluded"]]
    assert [(r["classname"], r["name"]) for r in records] == [("a.b", "c"), ("a", "b.c")]


def test_duplicate_run_ids_in_library_input_rejected() -> None:
    run = load_runs(REAL_HISTORY)[0]
    with pytest.raises(ValueError, match="Run ids must be unique"):
        analyze([run, run])


@pytest.mark.parametrize(
    "metadata",
    [
        '{"sequence":NaN}',
        '{"sequence":1.5}',
        '{"sequence":true}',
        '{"commit":{}}',
        '{"timestamp":"not a date"}',
        "[]",
        "{",
    ],
)
def test_bad_metadata_is_reported_not_silently_used(tmp_path: Path, metadata: str) -> None:
    p = write_report(tmp_path, "r.xml", case())
    p.with_suffix(".meta.json").write_text(metadata)
    result = analyze(load_runs(tmp_path))
    assert any("metadata" in warning for warning in result.warnings)
    json.dumps(to_json_dict(result), allow_nan=False)


def test_tied_sequences_report_ambiguous_chronology(tmp_path: Path) -> None:
    write_report(tmp_path, "a.xml", case(), sequence=1)
    write_report(tmp_path, "b.xml", case("<failure/>"), sequence=1)
    assert any("tied ordering" in w for w in analyze(load_runs(tmp_path)).warnings)


def test_terminal_table_fits_an_80_column_console() -> None:
    import io

    from rich.console import Console

    from flakemap.report.terminal import render_terminal

    output = io.StringIO()
    render_terminal(
        analyze(load_runs(REAL_HISTORY)), Console(file=output, width=80, color_system=None)
    )
    lines = output.getvalue().splitlines()
    assert all(len(line) <= 80 for line in lines)
    assert any("Runs" in line for line in lines)
    assert any(line.endswith("┓") for line in lines)  # the table's right edge is visible


def test_dtd_is_not_expanded(tmp_path: Path) -> None:
    p = tmp_path / "r.xml"
    p.write_text(
        '<!DOCTYPE testsuite [<!ENTITY x "expanded">]><testsuite><testcase name="&x;"/></testsuite>'
    )
    cases, warnings = parse_junit_file(p)
    assert cases == []
    assert "DTD" in warnings[0]


def test_bad_encoding_is_visible_in_export(tmp_path: Path) -> None:
    p = tmp_path / "r.xml"
    p.write_bytes(b'<testsuite><testcase name="bad\xffname"/></testsuite>')
    data = to_json_dict(analyze(load_runs(tmp_path)))
    assert any("invalid UTF-8" in warning for warning in data["warnings"])


def test_partial_shard_metadata_keeps_explicit_timestamp(tmp_path: Path) -> None:
    write_report(tmp_path, "run/a.xml", case(name="one"), sequence=7)
    write_report(
        tmp_path, "run/b.xml", case(name="two"), sequence=7, timestamp="2026-01-01T00:00:00Z"
    )
    runs = load_runs(tmp_path)
    assert runs[0].metadata.timestamp is not None
    assert runs[0].metadata.timestamp.isoformat() == "2026-01-01T00:00:00+00:00"
    assert analyze(runs).warnings == []
