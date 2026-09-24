from flakemap.stats.changepoint import detect_change_point


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


def test_single_early_failure_is_a_known_edge_case() -> None:
    # A single failure inside the first MIN_SEGMENT runs does register as a
    # change point (the 3-run "before" segment has a 33% rate, clearing the
    # rate-shift threshold): this is a documented limitation of using a fixed
    # minimum segment length rather than a sample-size-aware significance test.
    # It rarely affects classification in practice because `_classify` only
    # calls a test "broken" when the *after* segment has a high failure rate,
    # which isn't the case here.
    series = [1] + [0] * 29
    cp = detect_change_point(series)
    assert cp is not None
    assert cp.index == 3
    assert cp.rate_after == 0.0
