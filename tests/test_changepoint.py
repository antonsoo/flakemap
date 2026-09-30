import random

from flakemap.stats.changepoint import MIN_STATISTIC, detect_change_point


def test_no_change_in_constant_series() -> None:
    assert detect_change_point([0] * 20) is None
    assert detect_change_point([1] * 20) is None


def test_too_short_series_returns_none() -> None:
    assert detect_change_point([0, 1, 0, 1]) is None


def test_detects_clean_step_function() -> None:
    series = [0] * 15 + [1] * 15
    cp = detect_change_point(series)
    assert cp is not None
    assert cp.index == 15
    assert cp.rate_before == 0.0
    assert cp.rate_after == 1.0


def test_detects_step_at_an_offset_index() -> None:
    series = [0] * 8 + [1] * 22
    cp = detect_change_point(series)
    assert cp is not None
    assert cp.index == 8


def test_small_noise_does_not_trigger_a_change_point() -> None:
    # A single stray failure in an otherwise-constant series shouldn't read as a
    # regime change: the rate shift at any valid split is too small.
    series = [0] * 14 + [1] + [0] * 15
    cp = detect_change_point(series)
    assert cp is None


def test_single_early_failure_is_not_a_change_point() -> None:
    # One failure in the first MIN_SEGMENT runs gives the 3-run "before" segment
    # a 33% rate, which clears the rate-shift threshold; the significance
    # threshold is what rejects it (statistic ~5).
    assert detect_change_point([1] + [0] * 29) is None


def test_steady_flaky_series_rarely_reports_a_change() -> None:
    # A test that fails at the same 25% rate throughout has no change point, but
    # the best split of a random sequence always looks like one. Over 300 seeded
    # series of 222 runs, the significance threshold keeps reports rare.
    rng = random.Random(20260930)
    reported = recent = 0
    for _ in range(300):
        series = [1 if rng.random() < 0.25 else 0 for _ in range(222)]
        cp = detect_change_point(series)
        if cp is not None:
            reported += 1
            recent += len(series) - cp.index <= 10
    assert reported <= 9  # ~1% expected; the threshold alone used to allow ~50%
    assert recent <= 2


def test_real_regressions_are_still_found() -> None:
    # Broken since a commit: 10 passes then 3 straight failures clears the bar.
    cp = detect_change_point([0] * 10 + [1] * 3)
    assert cp is not None and cp.index == 10
    # Rare failures that become frequent.
    series = [1 if i % 50 == 7 else 0 for i in range(200)] + [1, 0] * 11
    cp = detect_change_point(series)
    assert cp is not None and abs(cp.index - 200) <= 3
    assert cp.statistic >= MIN_STATISTIC
