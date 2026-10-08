"""What a three-month history of an hourly job needs from the analysis and the report.

These follow the Kubernetes CI study in `studies/kubernetes-ci`: flakes that fail one
run in a hundred, commits built from once to a hundred times, reports that keep one
record per Go package, and two thousand runs to draw.
"""

from __future__ import annotations

import itertools
import json
import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from flakemap.cli import main
from flakemap.loader import load_runs
from flakemap.models import Run, RunMetadata, Status, TestCaseResult
from flakemap.parse.junit import parse_junit_file
from flakemap.report import render_html, to_json_dict
from flakemap.report.html_out import MAX_CELL_RUNS
from flakemap.report.numbers import percent
from flakemap.stats import analyze
from flakemap.stats.activity import SIGNIFICANCE, assess

FIXTURES = Path(__file__).parent / "fixtures"
START = datetime(2026, 7, 9, tzinfo=timezone.utc)


def _history(
    failing: dict[str, set[int]], runs: int, *, builds_per_commit: int = 1, healthy: int = 2
) -> list[Run]:
    """`runs` hourly runs; each named test fails in the listed run positions."""
    history = []
    for i in range(runs):
        cases = [
            TestCaseResult(
                name, "pkg", Status.FAIL if i in positions else Status.PASS, duration=1.0
            )
            for name, positions in failing.items()
        ]
        cases += [
            TestCaseResult(f"steady_{n}", "pkg", Status.PASS, duration=1.0) for n in range(healthy)
        ]
        history.append(
            Run(
                RunMetadata(
                    run_id=f"run-{i:05d}",
                    commit=f"c{i // builds_per_commit:05d}",
                    branch="main",
                    timestamp=START + timedelta(hours=i),
                    source="sidecar",
                ),
                cases,
                Path("<synthetic>"),
            )
        )
    return history


# --- where the failures fall -------------------------------------------------------------


def _placements(runs: int, events: int) -> list[tuple[int, ...]]:
    return list(itertools.combinations(range(runs), events))


@pytest.mark.parametrize(("runs", "failures"), [(12, [0, 3, 5]), (15, [2, 4]), (11, [1, 3, 6, 8])])
def test_the_two_chances_are_exact_shares_of_placements(runs: int, failures: list[int]) -> None:
    placed = assess(failures, runs)
    assert placed is not None
    ways = _placements(runs, len(failures))
    none_later = sum(max(way) <= failures[-1] for way in ways) / len(ways)
    none_earlier = sum(min(way) >= failures[0] for way in ways) / len(ways)
    assert placed.quiet_chance == pytest.approx(none_later)
    assert placed.new_chance == pytest.approx(none_earlier)


def test_consecutive_failing_runs_count_once() -> None:
    # Runs 3, 4 and 5 are one stretch: two events in a history two runs shorter.
    placed = assess([3, 4, 5, 9], 20)
    separate = assess([3, 7], 18)
    assert placed is not None and separate is not None
    assert (placed.failures, placed.events) == (4, 2)
    assert placed.quiet_chance == pytest.approx(separate.quiet_chance)
    assert placed.new_chance == pytest.approx(separate.new_chance)
    assert placed.runs_since_last == 10 and placed.runs_since_first == 17


def test_a_flake_that_stopped_is_quiet_and_one_that_started_is_new() -> None:
    stopped = assess([40, 90, 130, 200, 260, 300], 2000)
    started = assess([1930, 1960, 1995], 2000)
    steady = assess(list(range(100, 2000, 190)), 2000)
    assert stopped is not None and started is not None and steady is not None
    assert stopped.state == "quiet" and stopped.runs_since_last == 1699
    assert started.state == "new" and started.runs_since_first == 70
    assert steady.state == "ongoing"


def test_one_failure_or_one_unbroken_outage_is_never_placed() -> None:
    # A first-ever failure in the latest run is 1 chance in 5,000 of being "this late",
    # and says nothing about a rate. Neither does one outage, however long.
    single = assess([4999], 5000)
    outage = assess(list(range(3, 40)), 5000)
    assert single is not None and outage is not None
    assert single.state == outage.state == "ongoing"
    assert outage.events == 1 and outage.failures == 37


def test_a_steady_flake_is_rarely_called_quiet_or_new() -> None:
    rng = random.Random(20261008)
    labels = []
    for _ in range(4000):
        failures = [i for i in range(600) if rng.random() < 0.02]
        placed = assess(failures, 600)
        labels.append(placed.state if placed else "ongoing")
    # Each label is an exact one-sided test at 1%; adjacent failures counted once make
    # it slightly conservative.
    assert labels.count("quiet") / len(labels) <= SIGNIFICANCE * 1.3
    assert labels.count("new") / len(labels) <= SIGNIFICANCE * 1.3


def test_still_failing_is_not_quiet() -> None:
    broken = assess(list(range(150, 220)), 220)
    assert broken is not None
    assert broken.runs_since_last == 0 and broken.quiet_chance == 1.0


# --- the same commit, run again -----------------------------------------------------------


def test_each_failure_is_judged_by_the_other_runs_of_its_commit() -> None:
    # Commits are built four times. `flake` fails once on commit 3; `regress` fails every
    # build of commits 10 and 11.
    runs = _history({"flake": {13}, "regress": set(range(40, 48))}, runs=60, builds_per_commit=4)
    stats = {t.full_name: t for t in analyze(runs).tests}
    flake, regress = stats["pkg.flake"], stats["pkg.regress"]
    assert [f.same_commit for f in flake.failures] == ["passed"]
    assert flake.failures[0].same_commit_runs == 3
    assert flake.failures_passed_same_commit == 1 and flake.failures_repeated_same_commit == 0
    assert {f.same_commit for f in regress.failures} == {"failed"}
    assert regress.failures_repeated_same_commit == 8


def test_a_commit_built_once_proves_nothing() -> None:
    stats = {t.full_name: t for t in analyze(_history({"flake": {5, 30}}, runs=50)).tests}
    assert [f.same_commit for f in stats["pkg.flake"].failures] == ["single", "single"]
    assert stats["pkg.flake"].failures_checked == 0


def test_rerun_signal_weighs_commits_by_their_runs() -> None:
    # Two runs per commit: the signal is the share of commits whose two runs disagree,
    # as it always was.
    pairs = _history({"t": {0, 7, 20}}, runs=40, builds_per_commit=2)
    t = next(t for t in analyze(pairs).tests if t.full_name == "pkg.t")
    assert t.rerun_signal == pytest.approx(t.rerun_commits_flaky / t.rerun_commits_total)

    # One commit built 100 times with 2 failures, and nine built twice without any.
    uneven = []
    for i in range(118):
        commit = "big" if i < 100 else f"small{(i - 100) // 2}"
        status = Status.FAIL if i in (10, 60) else Status.PASS
        uneven.append(
            Run(
                RunMetadata(f"r{i:03d}", commit=commit, timestamp=START + timedelta(hours=i)),
                [TestCaseResult("t", "pkg", status)],
                Path("<synthetic>"),
            )
        )
    t = analyze(uneven).tests[0]
    # 2 * 98 of the 100-run commit's 4,950 pairs disagree: an unbiased 2p(1-p) for those
    # 100 runs, which are 100 of the 118 runs on commits built more than once.
    assert t.rerun_signal == pytest.approx((2 * 2 * 98 / 99) / 118)
    assert t.rerun_commits_flaky == 1 and t.rerun_commits_total == 10


def test_an_old_flake_does_not_keep_a_broken_test_from_being_called_broken() -> None:
    # Flaked once on a commit that also passed, months ago; fails every run since run 150.
    runs = _history({"t": {21} | set(range(150, 200))}, runs=200, builds_per_commit=2)
    t = next(t for t in analyze(runs).tests if t.full_name == "pkg.t")
    assert t.failures[0].same_commit == "passed"
    assert t.classification == "broken"
    assert t.change_point_run_id == "run-00150"


# --- reports that keep one record per Go package ------------------------------------------


def test_a_pruned_go_report_names_the_tests_that_failed() -> None:
    """An excerpt of a real Kubernetes integration report (see docs/formats.md)."""
    cases, warnings = parse_junit_file(FIXTURES / "kubernetes_pruned" / "junit_20260803-100711.xml")
    assert not warnings
    failed = [c for c in cases if c.status is Status.FAIL]
    assert [c.full_name for c in failed] == [
        "[sig-api-machinery] k8s.io/apiextensions-apiserver/test/integration.conversion"
    ]
    assert failed[0].failed_within == (
        "TestWebhookConverterWithWatchCache/empty-response-v1beta1/check-0/get",
        "TestWebhookConverterWithWatchCache/empty-response-v1beta1/check-0",
        "TestWebhookConverterWithWatchCache/empty-response-v1beta1",
        "TestWebhookConverterWithWatchCache",
    )
    # The report's own message is the one word "Failed".
    assert failed[0].message == (
        "conversion_test.go:839: expected error with message returned 0 objects, "
        "expected 1, but got no error"
    )
    # A Go import path is not a dotted module: its suite is the package, not "k8s".
    assert failed[0].suite == "[sig-api-machinery] k8s.io/apiextensions-apiserver/test/integration"
    assert all(not c.failed_within for c in cases if c.status is Status.PASS)


def test_a_go_test_that_reports_itself_is_not_named_inside_itself(tmp_path: Path) -> None:
    report = tmp_path / "r.xml"
    report.write_text(
        '<testsuite name="pkg"><testcase classname="pkg" name="TestA">'
        '<failure message="Failed">=== RUN   TestA\n    a_test.go:9: want 1, got 2\n'
        "--- FAIL: TestA (0.00s)\n    --- FAIL: TestA/sub (0.00s)\n</failure></testcase></testsuite>"
    )
    (case,), _ = parse_junit_file(report)
    assert case.failed_within == ()
    assert case.message == "a_test.go:9: want 1, got 2"


def test_named_failures_are_placed_separately_from_their_package(tmp_path: Path) -> None:
    def package(*names: str) -> TestCaseResult:
        return TestCaseResult(
            "plugins",
            "k8s.io/x/scheduler",
            Status.FAIL if names else Status.PASS,
            message="Failed" if names else None,
            failed_within=names,
        )

    early, late = {30, 80, 150, 210, 260}, {1890, 1940, 1985}
    runs = [
        Run(
            RunMetadata(f"r{i:04d}", commit=f"c{i // 2}", timestamp=START + timedelta(hours=i)),
            [
                package(
                    *(
                        ["TestOld"]
                        if i in early
                        else ["TestFresh/sub", "TestFresh"]
                        if i in late
                        else []
                    )
                )
            ],
            Path("<synthetic>"),
        )
        for i in range(2000)
    ]
    result = analyze(runs)
    (test,) = result.tests
    named = {n.name: n for n in test.named_failures}
    assert set(named) == {"TestOld", "TestFresh"}
    assert named["TestOld"].activity.state == "quiet" and named["TestOld"].runs == 5
    assert named["TestFresh"].activity.state == "new" and named["TestFresh"].runs == 3
    assert named["TestFresh"].passed_same_commit == named["TestFresh"].checked == 3
    # The package as a whole failed early and late: neither quiet nor new.
    assert test.activity is not None and test.activity.state == "ongoing"
    payload = to_json_dict(result)["tests"][0]
    assert [n["name"] for n in payload["named_failures"]] == ["TestOld", "TestFresh"]
    assert payload["named_failures"][1]["activity"]["state"] == "new"
    assert payload["failures"][0]["same_commit"] == "passed"


# --- two thousand runs on one page -------------------------------------------------------


def test_a_long_history_is_drawn_as_strips_and_healthy_tests_are_listed() -> None:
    runs = _history({"flaky": {100, 900, 1500}}, runs=2000, builds_per_commit=3, healthy=400)
    result = analyze(runs)
    page = render_html(result, runs)
    assert len(runs) > MAX_CELL_RUNS
    # 401 tests x 2,000 runs is 800,000 cells; a cell with its tooltip was 200 bytes.
    assert len(page) < 400_000
    assert page.count('class="strip"') == 1
    assert page.count("<g><title>") == 3  # one mark per failure, each with its run
    assert 'class="cell s-pass"' not in page
    assert "<b>400</b> tests passed in every run" in page
    assert "steady_399" in page
    assert "passed in another run (3 of this commit)" in page


def test_a_short_history_keeps_a_cell_per_run() -> None:
    runs = _history({"flaky": {3, 9}}, runs=40)
    page = render_html(analyze(runs), runs)
    assert page.count('class="cell s-fail" role="img"') == 2
    assert 'class="strip"' not in page


def test_small_rates_keep_their_digits() -> None:
    assert [percent(p) for p in (0.0, 0.32, 0.0971, 0.0097, 0.00046, 1.0)] == [
        "0%",
        "32%",
        "9.7%",
        "0.97%",
        "0.046%",
        "100%",
    ]
    assert percent(1 - 1e-7) != "100%" and percent(1e-9) != "0%"
    assert all(math.isfinite(float(percent(p).rstrip("%"))) for p in (0.004, 0.5, 0.9999))


# --- order and gates ---------------------------------------------------------------------


def _write_go_run(root: Path, run_id: str, started: str, fail: bool, files: int = 1) -> None:
    run = root / run_id
    run.mkdir(parents=True)
    for n in range(files):
        body = '<failure message="Failed"/>' if fail and n == 0 else ""
        (run / f"junit_{n}.xml").write_text(
            f'<testsuites><testsuite name="pkg{n}" timestamp="{started}">'
            f'<testcase classname="pkg{n}" name="TestA">{body}</testcase></testsuite></testsuites>'
        )


def test_a_suite_timestamp_with_an_offset_orders_runs_without_a_sidecar(tmp_path: Path) -> None:
    # Written newest first, so file modification times run backwards.
    _write_go_run(tmp_path, "b", "2026-08-03T10:08:19Z", fail=True)
    _write_go_run(tmp_path, "a", "2026-08-02T10:08:19Z", fail=False)
    _write_go_run(tmp_path, "c", "2026-08-04T12:00:00+02:00", fail=False)
    runs = load_runs(tmp_path)
    assert [r.metadata.run_id for r in runs] == ["a", "b", "c"]
    assert {r.metadata.source for r in runs} == {"report"}
    assert not analyze(runs).warnings


def test_a_bare_local_timestamp_is_not_trusted(tmp_path: Path) -> None:
    _write_go_run(tmp_path, "a", "2026-08-02T10:08:19", fail=False)
    assert load_runs(tmp_path)[0].metadata.source == "mtime"


def test_reports_of_one_run_may_start_at_different_moments(tmp_path: Path) -> None:
    run = tmp_path / "run-1"
    run.mkdir()
    for n, started in enumerate(("2026-08-03T10:08:19Z", "2026-08-03T10:20:00Z")):
        (run / f"junit_{n}.xml").write_text(
            f'<testsuite name="pkg{n}" timestamp="{started}">'
            f'<testcase classname="pkg{n}" name="TestA"/></testsuite>'
        )
    (loaded,) = load_runs(tmp_path)
    assert loaded.integrity_issue is None
    assert loaded.metadata.timestamp == datetime(2026, 8, 3, 10, 8, 19, tzinfo=timezone.utc)
    assert len(loaded.testcases) == 2


def test_a_run_placed_by_mtime_among_dated_runs_is_reported(tmp_path: Path) -> None:
    _write_go_run(tmp_path, "a", "2026-08-02T10:08:19Z", fail=False)
    _write_go_run(tmp_path, "stray", "2026-08-01T10:08:19", fail=False)
    warnings = analyze(load_runs(tmp_path)).warnings
    assert any(
        "placed by file mtime among runs placed by their recorded time" in w for w in warnings
    )
    assert any("stray" in w for w in warnings)


def test_the_new_flake_gate_sees_a_flake_that_fails_one_run_in_thirty(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    failing = {330, 361, 395}
    for i in range(400):
        run = tmp_path / f"run-{i:04d}"
        run.mkdir()
        body = "<failure message='boom'/>" if i in failing else ""
        (run / "junit.xml").write_text(
            f'<testsuite name="s"><testcase classname="s" name="t">{body}</testcase></testsuite>'
        )
        (run / "meta.json").write_text(json.dumps({"sequence": i, "commit": f"c{i}"}))
    # No change point: 0% to 4% is nowhere near a 20-point shift.
    assert main([str(tmp_path), "--fail-on-new-flake", "--new-flake-window", "100"]) == 1
    assert "new flake(s) detected: s.t" in capsys.readouterr().err
    assert main([str(tmp_path), "--fail-on-new-flake", "--new-flake-window", "10"]) == 0
