"""When a test's failures fell within its history: still going, new, or over.

A failure rate over a whole history assumes the test failed at one rate
throughout. Real flakes do not: one appears with a commit, fails a few times a
week, and stops when somebody fixes it. Three months later its rate still says
"0.9%", for a problem that ended two months ago, and a flake that started
yesterday has a rate too small to notice.

The rule here compares a silence with the silences the test has already had.
Consecutive failing runs count as one **event**. ``longest_gap`` is the
longest stretch of passing runs between two successive events.

- **quiet**: at least ``MIN_EVENTS`` events, and the runs since the last failure
  are at least ``RATIO`` times ``longest_gap`` and at least ``MIN_RUNS``. It
  has now been quiet three times longer than it ever was between failures.
- **new**: the mirror image. At least ``MIN_EVENTS`` events, and the runs before
  the first failure are at least ``RATIO`` times ``longest_gap`` and at least
  ``MIN_RUNS``. Only for a test whose passing runs the history records; a name
  read out of a failure's text may not have existed before it first failed, and
  the caller says so with ``can_be_new=False``.
- **ongoing**: neither, including every test with fewer events.

A flake that arrives in bursts has its long gaps on record and needs a
correspondingly longer silence. One burst followed by a long silence is labelled
quiet; that claims only that the burst is over, not that it cannot come back,
and not why it stopped (a fix, a revert, a deleted or renamed test look alike).

Calibration, for a steady flake only (independent runs, constant rate): the
chance that the open silence is at least ``s`` times the longest of ``n``
earlier gaps is ``n! / ((s+1)(s+2)...(s+n))``. At s = 3 that is 10% with 2
gaps (3 events), 5% with 3 gaps, under 1% from 7 gaps. Failures that cluster
are not steady, so this is a statement about steady flakes and nothing is
claimed for others; the label is a rule to read by eye, not a p-value.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ActivityState = Literal["new", "ongoing", "quiet"]

MIN_EVENTS = 3
RATIO = 3
MIN_RUNS = 10


@dataclass(frozen=True, slots=True)
class Activity:
    state: ActivityState
    failures: int
    """Failing runs."""
    events: int
    """Failures with consecutive failing runs counted once."""
    longest_gap: int | None
    """Most passing runs between two successive events; None with fewer than two events."""
    first_index: int
    last_index: int
    """Positions of the first and last failing run among the test's usable runs, from 0."""
    runs_since_last: int
    """Usable runs after the last failure."""
    runs_since_first: int
    """Usable runs from the first failure to the end of the history, inclusive."""

    @property
    def silence_ratio(self) -> float | None:
        """Runs since the last failure over the longest gap between failures."""
        return self.runs_since_last / self.longest_gap if self.longest_gap else None

    @property
    def lead_ratio(self) -> float | None:
        """Clean runs before the first failure over the longest gap between failures."""
        return self.first_index / self.longest_gap if self.longest_gap else None


def assess(failure_indexes: list[int], runs: int, *, can_be_new: bool = True) -> Activity | None:
    """Place a test's failures in its history.

    ``failure_indexes`` are the ascending positions, from 0, of its failing runs
    among its ``runs`` usable ones. Returns None for a test that never failed.
    """
    if not failure_indexes:
        return None
    # Each streak of consecutive failing runs is one event: (first run, last run).
    streaks: list[tuple[int, int]] = []
    for index in failure_indexes:
        if streaks and index == streaks[-1][1] + 1:
            streaks[-1] = (streaks[-1][0], index)
        else:
            streaks.append((index, index))
    gaps = [later[0] - earlier[1] - 1 for earlier, later in zip(streaks, streaks[1:], strict=False)]
    longest = max(gaps) if gaps else None
    since_last = runs - 1 - failure_indexes[-1]
    since_first = runs - failure_indexes[0]
    state: ActivityState = "ongoing"
    if len(streaks) >= MIN_EVENTS and longest:
        if since_last >= max(RATIO * longest, MIN_RUNS):
            state = "quiet"
        elif can_be_new and failure_indexes[0] >= max(RATIO * longest, MIN_RUNS):
            state = "new"
    return Activity(
        state=state,
        failures=len(failure_indexes),
        events=len(streaks),
        longest_gap=longest,
        first_index=failure_indexes[0],
        last_index=failure_indexes[-1],
        runs_since_last=since_last,
        runs_since_first=since_first,
    )
