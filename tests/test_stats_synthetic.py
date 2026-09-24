"""End-to-end statistical recovery test on synthetic ground truth.

Builds a run history with known-by-construction healthy, flaky, and broken
tests and checks that `analyze` recovers each one's true properties: a
healthy test reads healthy, a test planted with a fixed independent failure
probability has its true rate fall inside the reported Wilson interval, and a
test planted with a hard step (always-pass then always-fail from a known
commit onward) is classified broken with its change point located at that
commit. This is the "does the estimator work" check the statistics module
otherwise has no way to validate against reality.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flakemap.models import Run, RunMetadata, Status, TestCaseResult
from flakemap.stats import analyze

_SYNTHETIC_PATH = Path("<synthetic>")

N_RUNS = 200
BROKEN_FROM = 140
FLAKY_P = 0.25
RARE_FLAKY_P = 0.05


def _build_runs(seed: int) -> list[Run]:
    rng = random.Random(seed)
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    runs = []
    for i in range(N_RUNS):
        healthy = TestCaseResult("test_healthy", "tests.suite", Status.PASS, duration=0.10)
        broken_status = Status.FAIL if i >= BROKEN_FROM else Status.PASS
        broken = TestCaseResult(
            "test_broken",
            "tests.suite",
            broken_status,
            duration=0.20,
            message="AssertionError: boom" if broken_status == Status.FAIL else None,
        )
        flaky_status = Status.FAIL if rng.random() < FLAKY_P else Status.PASS
        flaky = TestCaseResult(
            "test_flaky",
            "tests.suite",
            flaky_status,
            duration=0.15,
            message="TimeoutError" if flaky_status == Status.FAIL else None,
        )
        rare_status = Status.FAIL if rng.random() < RARE_FLAKY_P else Status.PASS
        rare = TestCaseResult(
            "test_rare_flaky",
            "tests.suite",
            rare_status,
            duration=0.12,
            message="AssertionError: race" if rare_status == Status.FAIL else None,
        )
        metadata = RunMetadata(
            run_id=f"run-{i:04d}",
            commit=f"c{i:04d}",
            branch="main",
            timestamp=base + timedelta(minutes=5 * i),
            runner="ubuntu-latest",
            os="linux",
            sequence=i,
            source="sidecar",
        )
        runs.append(
            Run(metadata=metadata, testcases=[healthy, broken, flaky, rare], path=_SYNTHETIC_PATH)
        )
    return runs


def test_healthy_test_is_classified_healthy() -> None:
    result = analyze(_build_runs(seed=1))
    t = next(t for t in result.tests if t.full_name == "tests.suite.test_healthy")
    assert t.classification == "healthy"
    assert t.failure_rate.point == 0.0
    assert t.flakiness_score == 0.0


def test_broken_test_change_point_recovered() -> None:
    result = analyze(_build_runs(seed=1))
    t = next(t for t in result.tests if t.full_name == "tests.suite.test_broken")
    assert t.classification == "broken"
    assert t.change_point is not None
    assert t.change_point.index == BROKEN_FROM
    assert t.change_point_commit == f"c{BROKEN_FROM:04d}"
    assert t.failure_rate.point > 0.25  # (N_RUNS - BROKEN_FROM) / N_RUNS = 0.30


def test_flaky_test_rate_recovered_within_its_own_wilson_ci() -> None:
    # Run several seeds: the true rate should land inside the *reported* CI in
    # the large majority of runs (it's a 95% interval, not a guarantee every time).
    hits = 0
    trials = 20
    for seed in range(trials):
        result = analyze(_build_runs(seed=seed))
        t = next(t for t in result.tests if t.full_name == "tests.suite.test_flaky")
        if t.failure_rate.low <= FLAKY_P <= t.failure_rate.high:
            hits += 1
        assert t.classification == "flaky"
    assert hits >= trials * 0.85  # allow some slack below the nominal 95%


def test_rare_flaky_test_still_flagged_flaky_not_healthy() -> None:
    result = analyze(_build_runs(seed=1))
    t = next(t for t in result.tests if t.full_name == "tests.suite.test_rare_flaky")
    assert t.classification == "flaky"
    assert t.flip_rate > 0.0
    assert 0.0 < t.failure_rate.point < 0.2


def test_broken_test_has_near_zero_flip_rate_after_change() -> None:
    # A hard step function shouldn't look like a coin flip: flips only happen
    # right at the boundary, so overall flip rate stays low.
    result = analyze(_build_runs(seed=1))
    t = next(t for t in result.tests if t.full_name == "tests.suite.test_broken")
    assert t.flip_rate < 0.05
