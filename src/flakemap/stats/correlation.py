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
    two observations in either outcome class, or when durations have zero
    variance (the coefficient is undefined).
    """
    n = len(durations)
    if n != len(outcomes) or n < 2:
        return None

    n1 = sum(outcomes)
    n0 = n - n1
    if n1 < 1 or n0 < 1:
        return None

    mean_all = sum(durations) / n
    variance = sum((d - mean_all) ** 2 for d in durations) / n
    if variance <= 0:
        return None
    std_all = math.sqrt(variance)

    mean1 = sum(d for d, o in zip(durations, outcomes, strict=True) if o == 1) / n1
    mean0 = sum(d for d, o in zip(durations, outcomes, strict=True) if o == 0) / n0

    p = n1 / n
    q = 1 - p
    return ((mean1 - mean0) / std_all) * math.sqrt(p * q)


def linear_trend(values: list[float]) -> float | None:
    """Ordinary-least-squares slope of `values` against their index (run order).

    Units are "value change per run". Returns `None` for fewer than two points or
    a constant index range (never happens with len >= 2, kept for symmetry).
    """
    n = len(values)
    if n < 2:
        return None
    xs = list(range(n))
    mean_x = (n - 1) / 2
    mean_y = sum(values) / n
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, values, strict=True))
    den = sum((x - mean_x) ** 2 for x in xs)
    if den == 0:
        return None
    return num / den


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
