from __future__ import annotations

import math
from decimal import Decimal, localcontext
from pathlib import Path

import pytest

from flakemap.models import AttemptFailure, RetryEvidence, Run, RunMetadata, Status, TestCaseResult
from flakemap.report.json_out import to_json_dict
from flakemap.stats.analyze import analyze
from flakemap.stats.correlation import linear_trend, point_biserial


def run(position: int, cases: list[TestCaseResult]) -> Run:
    return Run(
        RunMetadata(str(position), sequence=position, source="sidecar"), cases, Path("synthetic")
    )


@pytest.mark.parametrize("gap", ["missing_duration", "absent", "skip", "retry", "unknown"])
def test_missing_timing_does_not_compress_the_history_axis(gap: str) -> None:
    runs = []
    for position in range(11):
        result = TestCaseResult("test", "A", Status.PASS, duration=10 if position == 0 else 30)
        cases = [result]
        if position not in (0, 10):
            if gap == "absent":
                cases = []
            elif gap == "retry":
                cases = [
                    TestCaseResult(
                        "test",
                        "A",
                        Status.PASS,
                        duration=500,
                        retry=RetryEvidence(
                            "recovered", (AttemptFailure("flakyFailure", Status.FAIL, "retry"),)
                        ),
                    )
                ]
            else:
                status = {"skip": Status.SKIP, "unknown": Status.UNKNOWN}.get(gap, Status.PASS)
                cases = [TestCaseResult("test", "A", status)]
        runs.append(run(position, cases))
    result = analyze(runs)
    assert result.tests[0].duration_trend == pytest.approx(2.0)
    assert (
        to_json_dict(result)["tests"][0]["duration"]["trend_axis"] == "supplied_history_run_index"
    )


def test_old_change_point_does_not_become_recent_when_the_test_disappears() -> None:
    runs = [
        run(i, [TestCaseResult("test", "A", Status.PASS if i < 10 else Status.FAIL)])
        for i in range(20)
    ]
    runs.extend(run(i, []) for i in range(20, 50))
    result = analyze(runs).tests[0]
    assert result.change_point is not None
    assert result.change_point_run_id == "10"
    assert result.runs_since_change == 40


@pytest.mark.parametrize("scale", [1e-300, 1.0, 1e100, 1e300])
def test_trend_matches_decimal_least_squares_with_irregular_positions(scale: float) -> None:
    xs = [0, 2, 7, 9, 20]
    values = [value * scale for value in [1.0, 1.1, 1.2, 4.0, 6.0]]
    with localcontext() as context:
        context.prec = 80
        dx = [Decimal(x) for x in xs]
        dy = [Decimal.from_float(y) for y in values]
        mean_x, mean_y = sum(dx) / len(dx), sum(dy) / len(dy)
        expected = float(
            sum((x - mean_x) * (y - mean_y) for x, y in zip(dx, dy, strict=True))
            / sum((x - mean_x) ** 2 for x in dx)
        )
    assert math.isclose(linear_trend(values, xs), expected, rel_tol=1e-12, abs_tol=0)


def test_large_origin_does_not_erase_small_run_gaps() -> None:
    assert linear_trend([10.0, 30.0], [10**100, 10**100 + 10]) == pytest.approx(2.0)


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_nonfinite_numeric_inputs_remain_unknown(bad: float) -> None:
    assert linear_trend([1.0, bad, 2.0]) is None
    assert point_biserial([1.0, bad, 2.0], [0, 1, 1]) is None


def test_large_finite_correlation_does_not_overflow() -> None:
    assert point_biserial([1e308, 1e308, 1.5e308, 1.5e308], [0, 0, 1, 1]) == pytest.approx(1)
    assert linear_trend([-1e308, 1e308]) is None


@pytest.mark.parametrize("positions", [[0], [0, 0], [1, 0], [0, 1.5], [False, True]])
def test_invalid_positions_cannot_produce_a_trend(positions: list[int]) -> None:
    with pytest.raises(ValueError, match="positions"):
        linear_trend([1, 2], positions)
