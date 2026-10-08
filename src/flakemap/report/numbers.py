"""Numbers as a report prints them.

A flaky test in a maintained project fails in one run in a hundred, or one in a
thousand. Rounded to a whole percent that is "1%" or "0%", with an interval of
"0%-1%": the rate, and the difference between two tests, is in the digits the
rounding threw away.
"""

from __future__ import annotations

import math


def percent(proportion: float) -> str:
    """A proportion as a percentage, with two significant digits near 0 and near 100.

    ``0.32`` is ``32%``, ``0.0097`` is ``0.97%`` and ``0.00046`` is ``0.046%``. Only an
    exact 0 or 1 prints as ``0%`` or ``100%``.
    """
    if proportion <= 0.0:
        return "0%"
    if proportion >= 1.0:
        return "100%"
    value = 100.0 * proportion
    tail = min(value, 100.0 - value)
    if tail >= 10.0:
        digits = 0
    elif tail >= 1.0:
        digits = 1
    else:
        digits = 1 - math.floor(math.log10(tail))
    text = f"{value:.{digits}f}"
    # Rounding must not turn "some" into "none" or "all".
    while float(text) in (0.0, 100.0):
        digits += 1
        text = f"{value:.{digits}f}"
    return f"{text}%"


def interval(low: float, high: float) -> str:
    return f"{percent(low)}–{percent(high)}"


def count(value: int) -> str:
    return f"{value:,}"


def of(part: int, whole: int) -> str:
    return f"{count(part)} of {count(whole)}"
