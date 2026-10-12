"""Exact histories checked against real captures and a separate dense-matrix oracle."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import random
import re
from pathlib import Path

import pytest
from rich.console import Console

from flakemap.loader import load_runs
from flakemap.models import (
    AttemptFailure,
    RetryEvidence,
    Run,
    RunMetadata,
    SourceLocation,
    Status,
    TestCaseResult,
)
from flakemap.report.cofailure_html import render_cofailure
from flakemap.report.json_out import cofailure_to_dict, to_json_dict
from flakemap.report.markdown_out import render_markdown
from flakemap.report.terminal import render_terminal
from flakemap.stats.analyze import analyze

ROOT = Path(__file__).parents[1]


def history(matrix: dict[str, str]) -> list[Run]:
    """P pass, F fail, E error, R recovered, X exhausted, S skip, U unknown, - absent."""
    runs = []
    for index in range(len(next(iter(matrix.values()), ""))):
        cases = []
        for name, states in matrix.items():
            state = states[index]
            if state == "-":
                continue
            status = {
                "P": Status.PASS,
                "F": Status.FAIL,
                "E": Status.ERROR,
                "R": Status.PASS,
                "X": Status.FAIL,
                "S": Status.SKIP,
                "U": Status.UNKNOWN,
            }[state]
            retry = (
                RetryEvidence(
                    "recovered" if state == "R" else "exhausted",
                    (
                        AttemptFailure(
                            "flakyFailure" if state == "R" else "failure", Status.FAIL, "network"
                        ),
                    ),
                )
                if state in "RX"
                else None
            )
            cases.append(
                TestCaseResult(
                    name,
                    "suite",
                    status,
                    message="network" if status.is_failure else None,
                    retry=retry,
                    source=SourceLocation(f"r{index}.xml", len(cases) + 1),
                )
            )
        runs.append(Run(RunMetadata(f"r{index}", sequence=index), cases, Path(f"r{index}.xml")))
    return runs


def memberships(runs: list[Run]) -> set[tuple[str, ...]]:
    return {group.tests for group in analyze(runs).cofailure.groups}


def test_real_loopback_capture_finds_shared_outages_not_independent_failure() -> None:
    root = ROOT / "examples/cofailure_history"
    capture = json.loads((root / "capture.json").read_text())
    source = (ROOT / "examples/cofailure_project/tests/test_service.py").read_bytes()
    assert hashlib.sha256(source).hexdigest() == capture["test_source_sha256"]
    assert len(capture["requests"]) == 46
    assert sum(request["status"] == 503 for request in capture["requests"]) == 10
    for run in capture["runs"]:
        assert run["exit_code"] == (
            1 if run["run_id"] in {"run-04", "run-05", "run-07", "run-10"} else 0
        )
    runs = load_runs(root)
    result = analyze(runs)
    assert not result.warnings
    assert (result.total_runs, len(result.tests)) == (12, 6)
    (group,) = result.cofailure.groups
    assert group.tests == tuple(
        f"tests.test_service.test_{name}_endpoint" for name in ("inventory", "pricing", "shipping")
    )
    assert group.states["failed"] == ("run-04", "run-05", "run-10")
    assert len(group.states["pass"]) == 9
    assert (group.failed_runs, group.recovered_runs, group.affected_test_runs) == (3, 0, 9)
    assert len(group.evidence) == 9
    for obs in group.evidence:
        assert obs.result.source.report == f"{obs.run.metadata.run_id}/report.xml"
        assert obs.result.source.testcase in (1, 2, 3)
        assert "HTTP 503" in obs.result.message
    optional = next(t for t in result.tests if t.full_name.endswith("test_optional_endpoint"))
    assert (optional.n, optional.n_skip, optional.n_fail) == (10, 1, 1)
    payload = to_json_dict(result)
    assert (payload["summary"]["cofailure_groups"], payload["summary"]["cofailure_tests"]) == (1, 3)
    assert payload["cofailure"]["runs"][0]["runner"] == "controlled-loopback-capture"
    assert len(payload["cofailure"]["groups"][0]["evidence"]) == 9


def test_same_failure_rate_is_not_the_same_history() -> None:
    assert memberships(history({"a": "PFPF", "b": "FPFP", "c": "PFPF"})) == {("suite.a", "suite.c")}


@pytest.mark.parametrize("second", ["FP", "FS", "FU", "FR", "FF", "FX"])
def test_absence_is_not_any_observed_state(second: str) -> None:
    assert memberships(history({"a": "F-", "b": second})) == set()


def test_shared_missing_and_skipped_runs_remain_explicit() -> None:
    result = analyze(history({"a": "P-FS", "b": "P-FS", "other": "PPFS"}))
    (group,) = result.cofailure.groups
    assert group.tests == ("suite.a", "suite.b")
    assert group.states == {
        "pass": ("r0",),
        "failed": ("r2",),
        "recovered": (),
        "exhausted": (),
        "skip": ("r3",),
        "absent": ("r1",),
    }


def test_ambiguous_history_is_excluded_even_when_unknown_positions_match() -> None:
    result = analyze(history({"a": "PFU", "b": "PFU", "c": "PFF", "d": "PFF"}))
    assert result.cofailure.excluded_tests == ("suite.a", "suite.b")
    assert [g.tests for g in result.cofailure.groups] == [("suite.c", "suite.d")]


@pytest.mark.parametrize("ambiguity", ["duplicate", "metadata", "dotted_identity"])
def test_normalization_exclusions_are_respected(ambiguity: str) -> None:
    runs = history({"a": "PF", "b": "PF"})
    if ambiguity == "duplicate":
        runs[0].testcases.append(runs[0].testcases[0])
    elif ambiguity == "metadata":
        runs[0].integrity_issue = "conflicting metadata"
    else:
        runs[0].testcases[0] = TestCaseResult("suite.a", "", Status.PASS)
    result = analyze(runs)
    assert result.cofailure.groups == []
    assert "suite.a" in result.cofailure.excluded_tests


def test_retry_states_are_not_plain_passes_or_failures() -> None:
    runs = history({"a": "PRX", "b": "PRX", "plain_pass": "PPX", "plain_fail": "PRF"})
    (group,) = analyze(runs).cofailure.groups
    assert group.tests == ("suite.a", "suite.b")
    assert (group.failed_runs, group.recovered_runs, group.affected_test_runs) == (1, 1, 4)
    assert group.states["recovered"] == ("r1",)
    assert group.states["exhausted"] == ("r2",)
    assert len(group.evidence) == 4


def test_real_surefire_attempt_counts_do_not_inflate_group_counts() -> None:
    result = analyze(load_runs(ROOT / "examples/retry_history"))
    groups = result.cofailure.groups
    assert len(groups) == 2
    assert {g.affected_test_runs for g in groups} == {2}
    recovered = next(g for g in groups if g.recovered_runs)
    assert {obs.result.retry.attempts for obs in recovered.evidence} == {2, 3}
    exhausted = next(g for g in groups if g.failed_runs)
    assert {obs.result.status for obs in exhausted.evidence} == {Status.FAIL, Status.ERROR}
    assert exhausted.states["failed"] == ()
    assert len(exhausted.states["exhausted"]) == 1


def test_single_run_is_a_shared_observation_not_a_rate_estimate() -> None:
    result = analyze(history({"a": "F", "b": "E"}))
    assert {t.classification for t in result.tests} == {"insufficient_data"}
    assert len(result.cofailure.groups) == 1
    assert "Tests that fail together" in render_markdown(result)
    assert "Final-failure runs" in render_markdown(result)
    for width in (40, 80, 120):
        output = io.StringIO()
        render_terminal(result, Console(file=output, width=width, color_system=None))
        assert "Tests that fail together" in output.getvalue()
        assert "suite.a" in output.getvalue()


@pytest.mark.parametrize("matrix", [{}, {"a": "PPP", "b": "PPP"}, {"a": "SSS", "b": "---"}])
def test_no_groups_without_failure_or_retry_evidence(matrix: dict[str, str]) -> None:
    assert memberships(history(matrix)) == set()


def test_sparse_grouping_matches_independent_dense_oracle() -> None:
    rng = random.Random(46102)
    for _ in range(160):
        length = rng.randrange(1, 15)
        # Include replicated histories and small mutations, not only unrelated random vectors.
        vectors = ["".join(rng.choices("PFERXSU-", k=length)) for _ in range(6)]
        matrix = {f"t{index}": rng.choice(vectors) for index in range(24)}
        expected = set()
        # Pairwise full-grid comparison is intentionally independent of sparse signatures.
        for vector in matrix.values():
            if "U" in vector or not any(char in vector for char in "FERX"):
                continue
            matches = tuple(
                sorted(
                    f"suite.{other}"
                    for other, candidate in matrix.items()
                    if all(
                        left.replace("E", "F") == right.replace("E", "F")
                        for left, right in zip(vector, candidate, strict=True)
                    )
                )
            )
            if len(matches) > 1:
                expected.add(matches)
        assert memberships(history(matrix)) == expected
        shuffled = list(matrix.items())
        rng.shuffle(shuffled)
        first = analyze(history(matrix)).cofailure
        second = analyze(history(dict(shuffled))).cofailure
        assert [(g.id, g.tests, g.states) for g in first.groups] == [
            (g.id, g.tests, g.states) for g in second.groups
        ]


def test_html_download_keeps_full_text_with_inert_bounded_previews() -> None:
    marker = '<img src="https://example.invalid/leak" onerror="alert(1)">|`\x9b'
    runs = history({f"{marker}{index}": "FR" for index in range(25)})
    result = analyze(runs)
    html = render_cofailure(result, {})
    assert html.count("<li>") == 20
    assert html.count('<th scope="row">') == 40
    assert "5 more members" in html
    assert "Showing 40 of 50" in html
    assert "<img " not in html
    assert "&lt;img " in html
    assert "\\x9b" in html
    assert "\x9b" not in html
    match = re.search('href="data:application/json;base64,([^"]+)"', html)
    payload = json.loads(base64.b64decode(match[1]))
    assert payload == {
        "schema_version": 1,
        "input_complete": True,
        "warnings": [],
        "cofailure": cofailure_to_dict(result.cofailure),
    }
    assert len(payload["cofailure"]["groups"][0]["tests"]) == 25
    assert len(payload["cofailure"]["groups"][0]["evidence"]) == 50
    md = render_markdown(result)
    # Literal HTML is safe inside native Markdown code spans; the retained
    # cmark-gfm/browser replay verifies rendered text and absence of images.
    assert '``suite.<img src="https://example.invalid/leak"' in md
    assert r"\|`\x9b" in md and "\x9b" not in md


def test_warning_survives_download_without_inventing_other_test_outcomes() -> None:
    runs = history({"a": "FP", "b": "FP"})
    runs[0].warnings.append("partial report: later cases missing")
    result = analyze(runs)
    html = render_cofailure(result, {})
    payload = json.loads(base64.b64decode(re.search('base64,([^"]+)"', html)[1]))
    assert payload["input_complete"] is False
    assert payload["warnings"] == result.warnings
    assert len(payload["cofailure"]["groups"]) == 1
