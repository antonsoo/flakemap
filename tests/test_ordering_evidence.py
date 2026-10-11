"""An arbitrary display order must not manufacture a failure timeline."""

from __future__ import annotations

import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from flakemap.cli import main
from flakemap.loader import load_runs
from flakemap.models import AttemptFailure, RetryEvidence, Run, RunMetadata, Status, TestCaseResult
from flakemap.ordering import order_runs
from flakemap.report import render_html, to_json_dict
from flakemap.stats import analyze

START = datetime(2026, 1, 1, tzinfo=timezone.utc)


def history(*, ordered: bool = False) -> list[Run]:
    runs = []
    for i in range(40):
        status = Status.PASS if i < 20 else Status.FAIL
        cases = [
            TestCaseResult(
                name,
                "pkg",
                status,
                duration=i + 1.0,
                failed_within=("TestInside/sub",) if status.is_failure else (),
            )
            for name in ("a", "b")
        ]
        cases.append(
            TestCaseResult(
                "retry",
                "pkg",
                Status.PASS,
                retry=RetryEvidence(
                    "recovered", (AttemptFailure("flakyFailure", Status.FAIL, "retry"),)
                ),
            )
        )
        runs.append(
            Run(
                RunMetadata(
                    f"r{i:02}",
                    commit="unchanged",
                    timestamp=START,
                    sequence=i if ordered else None,
                    source="sidecar",
                ),
                cases,
                Path("synthetic.xml"),
            )
        )
    return runs


def test_renaming_tied_runs_cannot_invent_temporal_statistics() -> None:
    runs = history()
    first = analyze(copy.deepcopy(runs))
    for i, run in enumerate(runs):
        run.metadata.run_id = f"r{39 - i:02}"
    second = analyze(runs)
    for result in (first, second):
        assert not result.ordering.available
        assert result.run_id_range is None
        assert len(result.cofailure.groups) == 1
        test = next(test for test in result.tests if test.full_name == "pkg.a")
        assert (test.n_pass, test.n_fail, test.n) == (20, 20, 40)
        assert test.failure_rate.point == 0.5
        assert test.rerun_signal > 0 and test.failures_passed_same_commit == 20
        assert test.flip_pairs == 0 and test.change_point is None and test.activity is None
        assert test.duration_trend is None and test.duration_n == 40
        assert test.duration_failure_correlation is not None
        assert test.last_status is None
        assert all(failure.index is None for failure in test.failures)
        named = test.named_failures[0]
        assert named.runs == 20 and named.activity is None
        assert named.first_run_id is named.last_run_id is None
        assert next(t for t in result.tests if t.full_name == "pkg.retry").recovered_runs == 40
    assert first.tests[0].flakiness_score == second.tests[0].flakiness_score


def test_sequences_resolve_tied_timestamps_and_library_input_order() -> None:
    runs = history(ordered=True)
    # Unique commits allow the coherent regression to be classified broken.
    for i, run in enumerate(runs):
        run.metadata.commit = f"c{i}"
    result = analyze(list(reversed(runs)))
    assert result.ordering.available and result.ordering.basis == "sequence"
    test = next(t for t in result.tests if t.full_name == "pkg.a")
    assert test.change_point_run_id == "r20"
    assert test.classification == "broken" and test.last_status == Status.FAIL
    assert test.duration_trend == pytest.approx(1)
    assert test.flip_pairs == 39
    assert [obs.run.metadata.run_id for obs in result.observations["pkg.a"]] == [
        r.metadata.run_id for r in runs
    ]
    html = render_html(result, list(reversed(runs)))
    assert html.index("r00 ·") < html.index("r39 ·")


@pytest.mark.parametrize("kind", ["mtime", "mixed", "duplicate_sequence", "conflict", "missing"])
def test_unavailable_ordering_has_a_reason(kind: str) -> None:
    runs = history(ordered=True)
    for i, run in enumerate(runs):
        if kind == "mtime":
            run.metadata.sequence = None
            run.metadata.source = "mtime"
            run.metadata.timestamp = START + timedelta(seconds=i)
        elif kind == "mixed":
            run.metadata.sequence = i if i % 2 else None
            run.metadata.timestamp = None if i % 2 else START + timedelta(seconds=i)
        elif kind == "duplicate_sequence":
            run.metadata.sequence = 1
        elif kind == "conflict":
            run.metadata.timestamp = START - timedelta(seconds=i)
        else:
            run.metadata.sequence = None
            run.metadata.timestamp = None
    _, evidence = order_runs(runs)
    assert not evidence.available and evidence.reason
    assert "gate are unavailable" in evidence.reason


def test_sequence_order_ignores_copy_times_and_accepts_missing_recorded_times() -> None:
    runs = history(ordered=True)
    for i, run in enumerate(runs):
        run.metadata.source = "mtime" if i % 2 else "sidecar"
        run.metadata.timestamp = START - timedelta(seconds=i) if i % 2 else None
    ordered, evidence = order_runs(list(reversed(runs)))
    assert evidence.available and evidence.basis == "sequence"
    assert ordered == runs
    assert not analyze(runs).warnings


def test_timestamp_order_uses_exact_times_and_rejects_partial_sequence_conflicts() -> None:
    runs = history()
    for i, run in enumerate(runs):
        run.metadata.timestamp = datetime(9999, 1, 1, tzinfo=timezone.utc) + timedelta(
            microseconds=i
        )
    assert order_runs(list(reversed(runs)))[0] == runs
    assert order_runs(runs)[1].basis == "timestamp"
    runs[0].metadata.sequence = 3
    runs[-1].metadata.sequence = 2
    assert not order_runs(runs)[1].available


def test_unordered_reports_preserve_evidence_without_chronology_labels() -> None:
    runs = history()
    result = analyze(runs)
    payload = to_json_dict(result)
    assert payload["schema_version"] == 3
    assert payload["summary"]["ordering"]["available"] is False
    test = next(row for row in payload["tests"] if row["test"] == "pkg.a")
    assert test["last_status"] is test["activity"] is test["flip_rate"] is None
    assert test["temporal_available"] is False
    html = render_html(result, runs)
    assert "Chronology unavailable." in html
    assert "display order only" in html
    assert "newest first" not in html and "chronological order" not in html
    assert "first failed" not in html and "Duration trend (without retries)" not in html
    assert "TestInside" in html


def test_cli_writes_report_and_returns_unavailable_for_new_flake_gate(
    tmp_path: Path, capsys
) -> None:
    for i in range(40):
        directory = tmp_path / f"r{i:02}"
        directory.mkdir()
        failure = "<failure>--- FAIL: TestInside (1s)</failure>" if i >= 20 else ""
        (directory / "report.xml").write_text(
            f'<testsuite><testcase classname="pkg" name="a">{failure}</testcase></testsuite>'
        )
        (directory / "meta.json").write_text(
            json.dumps({"timestamp": START.isoformat(), "commit": f"c{i}"})
        )
    report = tmp_path / "report.html"
    assert main([str(tmp_path), "--json", "--html", str(report), "--fail-on-new-flake"]) == 2
    assert report.exists()
    captured = capsys.readouterr()
    assert "chronology unavailable" in captured.err
    assert json.loads(captured.out)["summary"]["ordering"]["available"] is False
    for i in range(40):
        (tmp_path / f"r{i:02}" / "meta.json").write_text(
            json.dumps({"sequence": i, "commit": f"c{i}"})
        )
    # A demonstrable recent regression still fails with exit 1 once order is supplied.
    assert main([str(tmp_path), "--json", "--fail-on-new-flake", "--new-flake-window", "25"]) == 1
    assert load_runs(tmp_path)[0].metadata.run_id == "r00"


def test_recovery_change_is_not_a_new_flake(tmp_path: Path, capsys) -> None:
    for i in range(40):
        report = tmp_path / f"{i:02}.xml"
        failure = "<failure>controlled failure</failure>" if i < 20 else ""
        report.write_text(
            f'<testsuite><testcase classname="C" name="test">{failure}</testcase></testsuite>'
        )
        report.with_suffix(".meta.json").write_text(json.dumps({"sequence": i, "commit": str(i)}))
    assert main([str(tmp_path), "--json", "--fail-on-new-flake", "--new-flake-window", "25"]) == 0
    test = json.loads(capsys.readouterr().out)["tests"][0]
    assert test["change_point"]["rate_before"] == 1
    assert test["change_point"]["rate_after"] == 0
