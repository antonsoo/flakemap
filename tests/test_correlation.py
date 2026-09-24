import math

from flakemap.stats.correlation import group_failure_rates, linear_trend, point_biserial


def test_point_biserial_positive_when_failures_run_longer() -> None:
    durations = [1.0, 1.1, 0.9, 5.0, 5.5, 4.8]
    outcomes = [0, 0, 0, 1, 1, 1]
    r = point_biserial(durations, outcomes)
    assert r is not None
    assert r > 0.9


def test_point_biserial_none_with_no_variance() -> None:
    assert point_biserial([1.0, 1.0, 1.0], [0, 1, 0]) is None


def test_point_biserial_none_with_single_class() -> None:
    assert point_biserial([1.0, 2.0, 3.0], [0, 0, 0]) is None


def test_linear_trend_detects_upward_slope() -> None:
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    slope = linear_trend(values)
    assert slope is not None
    assert math.isclose(slope, 1.0, abs_tol=1e-9)


def test_linear_trend_flat_series_is_zero() -> None:
    slope = linear_trend([2.0, 2.0, 2.0, 2.0])
    assert slope is not None
    assert math.isclose(slope, 0.0, abs_tol=1e-9)


def test_group_failure_rates_orders_worst_first() -> None:
    labels = ["a", "a", "a", "b", "b", "b"]
    outcomes = [1, 1, 0, 0, 0, 0]
    groups = group_failure_rates(labels, outcomes)
    assert groups[0].label == "a"
    assert groups[0].failures == 2
    assert groups[1].label == "b"
    assert groups[1].failures == 0
