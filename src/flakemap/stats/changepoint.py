"""Single change-point detection in a binary (pass/fail) sequence.

"When did this test start failing?" is a change-point problem: find the split
that best explains the sequence as two constant-rate Bernoulli segments instead
of one. flakemap uses the standard likelihood-ratio approach for a single
change-point in a Bernoulli process (see e.g. Chen & Gupta, *Parametric
Statistical Change Point Analysis*, 2nd ed., Birkhauser, 2012, ch. 3): for each
candidate split point k, compute the log-likelihood of the two-segment model at
its per-segment MLE (the segment's own failure rate) and compare it to the
log-likelihood of the one-segment (no change) model. The split that maximizes
the likelihood-ratio statistic is the most probable single change-point; a
minimum segment length and a minimum rate-shift keep it from firing on noise in
short or nearly-constant sequences. This is a single-change-point detector, not
full multi-breakpoint segmentation (e.g. PELT) — flakemap's tests rarely change
regime more than once in a bounded CI history window, and a simpler model is
easier to explain in a report than a multi-segment one.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

MIN_SEGMENT = 3
MIN_RATE_SHIFT = 0.2


@dataclass(frozen=True, slots=True)
class ChangePoint:
    index: int
    """Index into the sequence: `series[index:]` is the "after" segment."""
    rate_before: float
    rate_after: float
    statistic: float
    """The likelihood-ratio statistic, 2*(LL_two_segment - LL_one_segment).
    Larger means a more convincing break; not calibrated to a p-value."""


def _bernoulli_loglik(successes: int, n: int) -> float:
    if n == 0:
        return 0.0
    p = successes / n
    total = 0.0
    if successes > 0:
        total += successes * math.log(p)
    failures = n - successes
    if failures > 0:
        total += failures * math.log(1 - p)
    return total


def detect_change_point(series: list[int]) -> ChangePoint | None:
    """Find the most likely single change-point in a 0/1 sequence.

    `series` should already be in chronological (run) order, 1 for a failure,
    0 for a pass. Returns `None` if the series is too short, or if no split
    clears the minimum-segment and minimum-rate-shift thresholds.
    """
    n = len(series)
    if n < 2 * MIN_SEGMENT:
        return None

    total_successes = sum(series)
    ll_one_segment = _bernoulli_loglik(total_successes, n)

    best: ChangePoint | None = None
    running = 0
    for k in range(1, n):
        running += series[k - 1]
        before_n, after_n = k, n - k
        if before_n < MIN_SEGMENT or after_n < MIN_SEGMENT:
            continue
        before_s = running
        after_s = total_successes - running
        ll_two_segment = _bernoulli_loglik(before_s, before_n) + _bernoulli_loglik(after_s, after_n)
        statistic = 2 * (ll_two_segment - ll_one_segment)
        if best is None or statistic > best.statistic:
            best = ChangePoint(
                index=k,
                rate_before=before_s / before_n,
                rate_after=after_s / after_n,
                statistic=statistic,
            )

    if best is None:
        return None
    if abs(best.rate_after - best.rate_before) < MIN_RATE_SHIFT:
        return None
    return best
