"""Wilson score interval for a binomial proportion.

The plain "failures / runs" estimate is misleading at low sample sizes: a test
that failed once in two runs reads as "50% failure rate" with no hint that two
observations tell you almost nothing. The normal (Wald) interval is worse here —
it can extend below 0% or above 100% and its coverage is poor for small n or
p near 0/1, exactly the regime most tests live in (either almost always passing
or almost always failing). The Wilson score interval (Wilson, E.B., 1927,
"Probable Inference, the Law of Succession, and Statistical Inference", Journal
of the American Statistical Association 22(158): 209-212) stays within [0, 1] and
has good coverage even for small n, which is why it's the default in most
statistics packages' `proportion_confint(method="wilson")`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

DEFAULT_Z = 1.959963984540054  # z for a 95% two-sided normal interval


@dataclass(frozen=True, slots=True)
class Interval:
    point: float
    low: float
    high: float


def wilson_interval(successes: int, n: int, z: float = DEFAULT_Z) -> Interval:
    """Wilson score interval for `successes` out of `n` Bernoulli trials.

    Returns the raw point estimate (`successes / n`) alongside the Wilson lower
    and upper bounds. `n == 0` returns a degenerate (0, 0, 1) interval: no data
    means no evidence, not zero risk.
    """
    if n <= 0:
        return Interval(point=0.0, low=0.0, high=1.0)
    if successes < 0 or successes > n:
        raise ValueError(f"successes={successes} out of range for n={n}")

    p = successes / n
    z2 = z * z
    denom = 1 + z2 / n
    center = (p + z2 / (2 * n)) / denom
    margin = (z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n))) / denom
    low = max(0.0, center - margin)
    high = min(1.0, center + margin)
    return Interval(point=p, low=low, high=high)
