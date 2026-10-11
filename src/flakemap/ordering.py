"""Choose a common chronology before computing temporal statistics.

Filesystem copy times and lexical identifiers can order a table, but cannot
establish when tests changed. Counts and same-run evidence do not need chronology.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from flakemap.models import Run, run_sort_key


@dataclass(frozen=True, slots=True)
class RunOrdering:
    available: bool
    basis: str
    reason: str | None = None


def recorded_time(run: Run) -> datetime | None:
    md = run.metadata
    time = md.timestamp
    if md.source == "mtime" or time is None or time.utcoffset() is None:
        return None
    return time.astimezone(timezone.utc)


def order_runs(runs: list[Run]) -> tuple[list[Run], RunOrdering]:
    """Return chronological runs when a common, unambiguous key exists.

    Complete unique sequences take precedence. Any recorded timestamps must
    agree with that order (ties are allowed). Otherwise complete unique recorded
    timestamps can supply order, provided known sequences do not contradict it.
    Unavailable histories keep a deterministic display order only.
    """
    if len(runs) <= 1:
        return list(runs), RunOrdering(True, "single_run")
    sequences = [run.metadata.sequence for run in runs]
    times = [recorded_time(run) for run in runs]
    if all(type(value) is int and value >= 0 for value in sequences) and len(set(sequences)) == len(
        runs
    ):
        ordered = sorted(runs, key=lambda run: run.metadata.sequence or 0)
        known_times = [time for run in ordered if (time := recorded_time(run)) is not None]
        if known_times == sorted(known_times):
            return ordered, RunOrdering(True, "sequence")
        reason = "Recorded timestamps contradict the supplied sequence order."
    elif all(time is not None for time in times) and len(set(times)) == len(runs):
        # The branch guarantees every timestamp is present and timezone aware.
        # Use datetime directly: float epoch seconds can merge distinct microseconds.
        ordered = sorted(runs, key=_time_key)
        known_sequences = [
            run.metadata.sequence for run in ordered if run.metadata.sequence is not None
        ]
        if known_sequences == sorted(known_sequences):
            return ordered, RunOrdering(True, "timestamp")
        reason = "Recorded sequence values contradict the timestamp order."
    else:
        reason = "Runs have missing or tied ordering values, or filesystem-only timestamps; no common chronology is available."
    reason += (
        " Supply consistent distinct sequences or recorded timestamps for every run. "
        "Temporal statistics and the new-flake gate are unavailable; display order is not chronology."
    )
    return sorted(runs, key=run_sort_key), RunOrdering(False, "unavailable", reason)


def _time_key(run: Run) -> datetime:
    time = recorded_time(run)
    assert time is not None
    return time
