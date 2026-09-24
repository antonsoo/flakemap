import math

from flakemap.stats.wilson import wilson_interval


def test_no_data_is_maximally_uncertain() -> None:
    iv = wilson_interval(0, 0)
    assert iv.point == 0.0
    assert iv.low == 0.0
    assert iv.high == 1.0


def test_point_estimate_is_plain_proportion() -> None:
    iv = wilson_interval(3, 10)
    assert math.isclose(iv.point, 0.3)


def test_interval_always_contains_point_and_is_within_bounds() -> None:
    for successes, n in [(0, 5), (5, 5), (1, 5), (50, 100), (1, 1000), (999, 1000)]:
        iv = wilson_interval(successes, n)
        assert 0.0 <= iv.low <= iv.point <= iv.high <= 1.0


def test_matches_hand_computed_reference_value() -> None:
    # Reference value from the closed-form Wilson formula (Wilson 1927), computed
    # independently by hand: for 3/10 successes and z=1.959964 (95%),
    # center = (p + z^2/2n) / (1 + z^2/n), margin = z*sqrt(p(1-p)/n + z^2/4n^2) / (1 + z^2/n)
    # gives low=0.10779, high=0.60322.
    iv = wilson_interval(3, 10)
    assert math.isclose(iv.low, 0.10779, abs_tol=1e-4)
    assert math.isclose(iv.high, 0.60322, abs_tol=1e-4)


def test_interval_narrows_as_n_grows_for_fixed_proportion() -> None:
    small = wilson_interval(3, 10)
    large = wilson_interval(300, 1000)
    assert (large.high - large.low) < (small.high - small.low)


def test_zero_n_never_divides_by_zero() -> None:
    iv = wilson_interval(0, 0)
    assert iv is not None


def test_rejects_impossible_counts() -> None:
    import pytest

    with pytest.raises(ValueError):
        wilson_interval(11, 10)
