"""Continuing failed attempts must not disappear when retries make a build green."""

from __future__ import annotations

import json
import runpy
from dataclasses import replace
from io import StringIO
from pathlib import Path

import pytest
from rich.console import Console

from flakemap.cli import main
from flakemap.loader import load_runs
from flakemap.report import render_html, render_markdown, render_terminal, to_json_dict
from flakemap.stats import analyze
from flakemap.stats.activity import assess

STUDY = Path(__file__).resolve().parents[1] / "studies/retry-activity"


@pytest.fixture
def histories(tmp_path: Path) -> dict[str, Path]:
    return runpy.run_path(str(STUDY / "compose.py"))["histories"](tmp_path)


def test_continuing_failed_attempts_are_ongoing_without_changing_final_rates(histories) -> None:
    runs = load_runs(histories["continuing_retries"])
    result = analyze(runs)
    test = result.tests[0]
    assert not result.warnings
    assert (test.n, test.n_pass, test.n_fail, test.recovered_runs, test.exhausted_runs) == (
        20,
        17,
        3,
        15,
        3,
    )
    assert test.failure_rate.point == 3 / 20
    activity = test.activity
    assert activity is not None
    assert (activity.state, activity.failures, activity.recovered_runs) == ("ongoing", 18, 15)
    # Final failures at 0, 2, 4; recoveries at 5..19: three stretches, latest at 19.
    assert (activity.events, activity.longest_gap, activity.runs_since_last) == (3, 1, 0)
    assert to_json_dict(result)["summary"]["flaky_quiet"] == 0
    evidence = to_json_dict(result)["tests"][0]
    assert evidence["activity"]["basis"] == "runs_with_observed_failures"
    assert evidence["activity"]["final_failure_runs"] == 3
    assert evidence["activity"]["recovered_runs"] == 15
    assert len(evidence["retries"]["evidence"]) == 18
    html = render_html(result, runs)
    assert "18 runs with observed failures (15 passed on retry)" in html
    assert "last failure was 0 runs ago" in html
    assert "The burst is over" not in html
    output = StringIO()
    render_terminal(result, Console(file=output, width=160, force_terminal=False))
    assert "flaky, quiet" not in output.getvalue()
    assert "latest run" in output.getvalue()
    assert "Activity and Last failed include" in output.getvalue()
    markdown = render_markdown(result)
    assert "flaky, quiet" not in markdown
    assert "latest run" in markdown


@pytest.mark.parametrize(
    "scenario,state,since,code",
    [
        ("actually_quiet", "quiet", 15, 0),
        ("new_retries", "new", 0, 1),
    ],
)
def test_recovered_only_history_has_observed_activity_and_correct_new_gate(
    histories,
    capsys,
    scenario,
    state,
    since,
    code,
) -> None:
    result = analyze(load_runs(histories[scenario]))
    test = result.tests[0]
    assert (test.n_fail, test.n_pass, test.recovered_runs) == (0, 20, 3)
    assert test.failure_rate.point == 0
    assert test.activity is not None
    assert (test.activity.state, test.activity.failures, test.activity.recovered_runs) == (
        state,
        3,
        3,
    )
    assert test.activity.runs_since_last == since
    assert main([str(histories[scenario]), "--json", "--fail-on-new-flake"]) == code
    payload = json.loads(capsys.readouterr().out)
    assert payload["tests"][0]["activity"]["state"] == state
    assert main([str(histories[scenario]), "--json", "--fail-on-retry"]) == 1
    capsys.readouterr()


def test_ambiguous_outcome_blocks_activity_and_new_flake_gate_but_keeps_evidence(
    histories, capsys
) -> None:
    path = histories["ambiguous_tail"]
    runs = load_runs(path)
    # The same gap also makes a named inner test's silence unknowable.
    for run in runs:
        run.testcases = [
            replace(case, failed_within=("TestCheckout",)) if case.status.is_failure else case
            for case in run.testcases
        ]
    result = analyze(runs)
    test = result.tests[0]
    assert (test.n, test.n_fail, test.n_unknown) == (19, 3, 1)
    assert test.activity is None and test.activity_unavailable_reason == "ambiguous_outcomes"
    assert test.named_failures[0].runs == 3 and test.named_failures[0].activity is None
    assert len(test.failures) == 3 and len(test.excluded_observations) == 1
    payload = to_json_dict(result)
    assert payload["tests"][0]["activity_unavailable_reason"] == "ambiguous_outcomes"
    assert (
        payload["tests"][0]["named_failures"][0]["activity_unavailable_reason"]
        == "ambiguous_outcomes"
    )
    assert "ambiguous outcomes interrupt the failure history" in render_html(result, runs)
    assert main([str(path), "--json", "--fail-on-new-flake"]) == 2
    captured = capsys.readouterr()
    assert "ambiguous outcomes" in captured.err
    assert json.loads(captured.out)["summary"]["flaky_quiet"] == 0


def test_one_run_is_one_activity_observation_even_with_multiple_failed_attempts() -> None:
    activity = assess([1, 4], 12, recovered_indexes=[1, 2, 2, 5, 8])
    assert activity is not None
    assert (activity.failures, activity.recovered_runs, activity.events) == (5, 3, 3)
    assert (activity.first_index, activity.last_index, activity.runs_since_last) == (1, 8, 3)
