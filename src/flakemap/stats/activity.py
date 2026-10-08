"""When a test's failures fell within its history: still going, new, or over.

A failure rate over a whole history assumes the test failed at one rate
throughout. Real flakes do not: one appears with a commit, fails a few times a
week, and stops when somebody fixes it. Three months later its rate still says
"0.9%", for a problem that ended two months ago, and a flake that started
yesterday has a rate too small to notice.

The check here asks only where the failures sit. Given that a test failed in
``k`` of its ``n`` runs, a constant failure rate makes every placement of those
``k`` failures among the ``n`` runs equally likely. So:

- the chance that all of them fall in the first ``L`` runs is
  ``C(L, k) / C(n, k)``. When the last failure is at run ``L`` and that chance
  is under 1%, the silence since is not what a steady flake produces: the test
  is **quiet**.
- the chance that all of them fall in the last ``m`` runs is
  ``C(m, k) / C(n, k)``. When the first failure is ``m`` runs from the end and
  that chance is under 1%, the test is **new**.

Both are exact for any rate and any history length; there is no fitted rate and
no simulated threshold. A test that is neither is **ongoing**, which for a test
with a failure or two means only that nothing can be said yet. One failure is
never enough for either label: wherever it sits, a single failure does not say
what the rate was before or after it.

Consecutive failing runs count as one failure. A broken build fails every run
until it is fixed, and five failures in a row are one event, not five
independent ones; counting them separately would make any silence after them
look more surprising than it is. Failures that cluster without being adjacent
still overstate the evidence, so the 1% is a bound for a steady flake, not for
a bursty one.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

ActivityState = Literal["new", "ongoing", "quiet"]

SIGNIFICANCE = 0.01
MIN_EVENTS = 2


@dataclass(frozen=True, slots=True)
class Activity:
    state: ActivityState
    failures: int
    """Failing runs."""
    events: int
    """Failures with consecutive failing runs counted once; what the two chances use."""
    first_index: int
    last_index: int
    """Positions of the first and last failing run among the test's usable runs, from 0."""
    runs_since_last: int
    """Usable runs after the last failure."""
    runs_since_first: int
    """Usable runs from the first failure to the end of the history, inclusive."""
    quiet_chance: float
    """Chance of a silence at least this long since the last failure, at a constant rate."""
    new_chance: float
    """Chance of a clean stretch at least this long before the first, at a constant rate."""


def _log_choose(n: int, k: int) -> float:
    return math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)


def _all_within(span: int, events: int, runs: int) -> float:
    """Chance that ``events`` evenly placed failures all fall within ``span`` of ``runs``."""
    if span >= runs:
        return 1.0
    if span < events:
        return 0.0
    return math.exp(_log_choose(span, events) - _log_choose(runs, events))


def assess(failure_indexes: list[int], runs: int) -> Activity | None:
    """Place a test's failures in its history.

    ``failure_indexes`` are the ascending positions, from 0, of its failing runs
    among its ``runs`` usable ones. Returns None for a test that never failed.
    """
    if not failure_indexes:
        return None
    # Collapse each streak of consecutive failing runs onto its first run, and close the
    # gap, so positions and the history length describe events, not runs.
    events: list[int] = []
    collapsed = 0
    previous: int | None = None
    for index in failure_indexes:
        if previous is not None and index == previous + 1:
            collapsed += 1
        else:
            events.append(index - collapsed)
        previous = index
    length = runs - collapsed
    since_last = runs - 1 - failure_indexes[-1]
    since_first = runs - failure_indexes[0]
    quiet = _all_within(events[-1] + 1, len(events), length)
    new = _all_within(length - events[0], len(events), length)
    state: ActivityState = "ongoing"
    if len(events) >= MIN_EVENTS and quiet < SIGNIFICANCE:
        state = "quiet"
    elif len(events) >= MIN_EVENTS and new < SIGNIFICANCE:
        state = "new"
    return Activity(
        state=state,
        failures=len(failure_indexes),
        events=len(events),
        first_index=failure_indexes[0],
        last_index=failure_indexes[-1],
        runs_since_last=since_last,
        runs_since_first=since_first,
        quiet_chance=quiet,
        new_chance=new,
    )
