"""Core data model: the shapes every parser produces and every statistic consumes.

Keeping this module free of I/O and of any particular JUnit dialect's quirks is what
lets `flakemap.parse` and `flakemap.stats` be tested independently of each other.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Literal


class Status(str, Enum):
    """A single testcase's outcome, normalized across JUnit dialects.

    Dialects disagree on vocabulary (pytest uses ``<failure>``/``<error>``, Jest's
    junit reporter never emits ``<error>``, Go's runner reports panics as failures,
    ...). Unknown is reserved for ambiguous or contradictory evidence and is
    excluded from statistics.
    """

    PASS = "pass"
    FAIL = "fail"
    ERROR = "error"
    SKIP = "skip"
    UNKNOWN = "unknown"

    @property
    def is_failure(self) -> bool:
        """Errors count as failures for flakiness purposes: both mean "not green"."""
        return self in (Status.FAIL, Status.ERROR)


@dataclass(frozen=True, slots=True)
class SourceLocation:
    report: str
    testcase: int
    """One-based testcase ordinal in this report (not a source line number)."""


@dataclass(frozen=True, slots=True)
class AttemptFailure:
    tag: str
    status: Status
    message: str | None


@dataclass(frozen=True, slots=True)
class RetryEvidence:
    outcome: Literal["recovered", "exhausted"]
    failures: tuple[AttemptFailure, ...]
    """Explicit failing records in XML order; no inferred timestamps or durations."""

    @property
    def attempts(self) -> int:
        return len(self.failures) + (self.outcome == "recovered")


@dataclass(frozen=True, slots=True)
class TestCaseResult:
    """One `<testcase>` element, normalized."""

    name: str
    classname: str
    status: Status
    duration: float | None = None
    message: str | None = None
    """First line of the failure/error message, if any. Used for clustering."""
    retry: RetryEvidence | None = None
    source: SourceLocation | None = None
    issue: str | None = None
    """Why the outcome is unknown, if the report is contradictory or ambiguous."""

    @property
    def full_name(self) -> str:
        if self.classname:
            return f"{self.classname}.{self.name}"
        return self.name

    @property
    def suite(self) -> str:
        """The grouping key used for "by suite/module" rollups.

        This is the classname with the final segment (the method/test name pattern)
        stripped, e.g. ``tests.test_login.TestLogin`` -> ``tests.test_login``. Falls
        back to the full classname when it has no dots.
        """
        if "." in self.classname:
            return self.classname.rsplit(".", 1)[0]
        return self.classname or "(default)"


@dataclass(slots=True)
class RunMetadata:
    """Where a report file came from: which CI run, which commit, which machine.

    Every field is optional because dialects and CI setups vary; downstream code
    must degrade gracefully (see `flakemap.stats`) when a field is missing rather
    than crash.
    """

    run_id: str
    commit: str | None = None
    branch: str | None = None
    timestamp: datetime | None = None
    runner: str | None = None
    os: str | None = None
    sequence: int | None = None
    """Explicit ordering hint (e.g. from a sidecar's ``"sequence"`` key) used when
    no timestamp is available. Lower runs first."""
    source: str = "unknown"
    """Where this metadata came from: 'sidecar', 'path', 'report' (a TRX file's own
    start time), 'mtime', or 'unknown'.
    Surfaced in reports so users can judge how trustworthy the ordering is."""
    extra: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class Run:
    """A logical run, potentially assembled from several report files."""

    metadata: RunMetadata
    testcases: list[TestCaseResult]
    path: Path
    warnings: list[str] = field(default_factory=list)
    """Non-fatal parse issues (unknown dialect quirks, malformed subtrees skipped)."""
    integrity_issue: str | None = None


def run_sort_key(run: Run) -> tuple[int, float, int, str]:
    """Order runs chronologically, using the best signal available.

    Timestamped runs sort first (by time); pure-sequence runs sort after, by their
    sequence number; anything else falls back to a lexical sort of run_id so output
    is at least deterministic. The leading int partitions the three tiers so they
    never interleave.
    """
    md = run.metadata
    if md.timestamp is not None:
        return (0, md.timestamp.timestamp(), 0, md.run_id)
    if md.sequence is not None:
        return (1, 0.0, md.sequence, md.run_id)
    return (2, 0.0, 0, md.run_id)
