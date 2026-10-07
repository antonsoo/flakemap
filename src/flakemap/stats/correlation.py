"""Correlating failures with duration and with categorical run metadata."""

from __future__ import annotations

import math
from dataclasses import dataclass

from flakemap.stats.wilson import Interval, wilson_interval


def point_biserial(durations: list[float], outcomes: list[int]) -> float | None:
    """Correlation between a continuous variable (duration) and a binary one
    (1 = failure, 0 = pass): the point-biserial correlation coefficient, which is
    exactly a Pearson correlation where one variable is binary (Tate, R.F., 1954,
    "Correlation Between a Discrete and a Continuous Variable", Annals of
    Mathematical Statistics 25(3): 603-607).

    A positive value means failures tend to run longer than passes — the
    signature of a timeout-driven flake. Returns `None` when there are fewer than
    one observation in either outcome class, or when durations have zero
    variance (the coefficient is undefined).
    """
    n = len(durations)
    if n != len(outcomes) or n < 2:
        return None
    if not all(math.isfinite(value) for value in durations) or any(
        o not in (0, 1) for o in outcomes
    ):
        return None

    n1 = sum(outcomes)
    n0 = n - n1
    if n1 < 1 or n0 < 1:
        return None

    scale = max(abs(value) for value in durations)
    if scale == 0:
        return None
    scaled = [value / scale for value in durations]
    mean_all = math.fsum(scaled) / n
    variance = math.fsum((d - mean_all) ** 2 for d in scaled) / n
    if variance <= 0:
        return None
    std_all = math.sqrt(variance)

    mean1 = math.fsum(d for d, o in zip(scaled, outcomes, strict=True) if o == 1) / n1
    mean0 = math.fsum(d for d, o in zip(scaled, outcomes, strict=True) if o == 0) / n0

    p = n1 / n
    q = 1 - p
    return max(-1.0, min(1.0, ((mean1 - mean0) / std_all) * math.sqrt(p * q)))


def linear_trend(values: list[float], positions: list[int] | None = None) -> float | None:
    """Ordinary-least-squares slope of `values` against their index (run order).

    Supply original run positions when some runs have no duration measurement;
    dropping the measurements must not compress the time axis. Without positions,
    the index is 0, 1, ... . Nonfinite or unrepresentable results are unknown.
    """
    n = len(values)
    xs = positions if positions is not None else list(range(n))
    if (
        len(xs) != n
        or any(type(x) is not int for x in xs)
        or any(a >= b for a, b in zip(xs, xs[1:], strict=False))
    ):
        raise ValueError("positions must be distinct increasing integers, one per value")
    if n < 2:
        return None
    if not all(math.isfinite(value) for value in values):
        return None
    scale = max(abs(value) for value in values)
    if scale == 0:
        return 0.0
    # Subtract the integer origin before float conversion so a large run index
    # cannot erase small gaps. Scaling y keeps sums and squares finite.
    offsets = [x - xs[0] for x in xs]
    mean_x = sum(offsets) / n
    scaled = [value / scale for value in values]
    mean_y = math.fsum(scaled) / n
    num = math.fsum((x - mean_x) * (y - mean_y) for x, y in zip(offsets, scaled, strict=True))
    den = math.fsum((x - mean_x) ** 2 for x in offsets)
    slope = (num / den) * scale
    return slope if math.isfinite(slope) else None


@dataclass(frozen=True, slots=True)
class GroupRate:
    label: str
    n: int
    failures: int
    interval: Interval


def group_failure_rates(labels: list[str], outcomes: list[int]) -> list[GroupRate]:
    """Per-category (e.g. per-runner, per-OS) failure rate with a Wilson interval.

    This is deliberately descriptive rather than a hypothesis test: with the
    small per-category sample sizes typical of a CI matrix (a handful of runners,
    dozens of runs each), a chi-square or G-test p-value would overstate
    precision. Reports should read this as "here is the spread", and treat a
    category whose interval doesn't overlap the others as the notable case.
    """
    by_label: dict[str, list[int]] = {}
    for label, outcome in zip(labels, outcomes, strict=True):
        by_label.setdefault(label, []).append(outcome)

    result = []
    for label, group in sorted(by_label.items()):
        n = len(group)
        failures = sum(group)
        result.append(
            GroupRate(label=label, n=n, failures=failures, interval=wilson_interval(failures, n))
        )
    result.sort(key=lambda g: g.interval.point, reverse=True)
    return result
