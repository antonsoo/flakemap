"""Reconcile declared JUnit totals without inventing individual test outcomes.

Some reporters count testcase elements; Surefire can count explicitly recorded
retry attempts instead. A whole set of supplied counters must fit one convention.
Neither convention proves that an upstream runner/exporter included every test.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from xml.etree import ElementTree as ET

from flakemap.models import Status, TestCaseResult

_COUNTERS = ("tests", "failures", "errors", "skipped")
_MAX_EXAMPLES = 3


@dataclass(slots=True)
class SummaryCounts:
    ordinal: int
    tests: int = 0
    failures: int = 0
    errors: int = 0
    skipped: int = 0
    attempts: int = 0
    attempt_failures: int = 0
    attempt_errors: int = 0

    def observe(self, element: ET.Element, result: TestCaseResult) -> None:
        self.tests += 1
        # Count testcases with markers, not assertions: GoogleTest can put several
        # <failure> elements in one failed test. Disabled tests have no <skipped>
        # marker and Google's `disabled` counter can include executed tests too.
        failed = int(element.find("failure") is not None)
        errored = int(element.find("error") is not None)
        self.failures += failed
        self.errors += errored
        self.skipped += int(
            element.find("skipped") is not None
            or (element.get("result") or "").strip().lower() == "skipped"
        )
        if result.retry is None:
            self.attempts += 1
            self.attempt_failures += failed
            self.attempt_errors += errored
        else:
            self.attempts += result.retry.attempts
            self.attempt_failures += sum(f.status == Status.FAIL for f in result.retry.failures)
            self.attempt_errors += sum(f.status == Status.ERROR for f in result.retry.failures)

    def include(self, child: SummaryCounts) -> None:
        """Fold a completed child once; parent totals cover descendant records."""
        self.tests += child.tests
        self.failures += child.failures
        self.errors += child.errors
        self.skipped += child.skipped
        self.attempts += child.attempts
        self.attempt_failures += child.attempt_failures
        self.attempt_errors += child.attempt_errors

    def mismatch(self, element: ET.Element) -> str | None:
        declared: dict[str, int] = {}
        for key in _COUNTERS:
            raw = element.get(key)
            if raw is None:
                continue
            text = raw.strip()
            # Bounded conversion even on Python versions without an integer digit
            # limit. These counts cannot be reached within the XML element limit.
            if len(text) > 20 or re.fullmatch(r"\+?[0-9]+", text) is None:
                return f"{key}={raw[:60]!r} is not a supported nonnegative integer"
            declared[key] = int(text)
        if not declared:
            return None
        cases = (self.tests, self.failures, self.errors, self.skipped)
        attempts = (self.attempts, self.attempt_failures, self.attempt_errors, self.skipped)
        for counts in (cases, attempts):
            if all(
                declared.get(key, value) == value
                for key, value in zip(_COUNTERS, counts, strict=True)
            ):
                return None

        def describe(counts: tuple[int, ...]) -> str:
            return ", ".join(
                f"{key}={value}"
                for key, value in zip(_COUNTERS, counts, strict=True)
                if key in declared
            )

        evidence = f"testcase records ({describe(cases)})"
        if attempts != cases:
            evidence += f" or explicit attempts ({describe(attempts)})"
        reported = ", ".join(f"{key}={value}" for key, value in declared.items())
        return f"declares {reported}; retained {evidence}"


@dataclass(slots=True)
class SummaryWarnings:
    """Check every suite, retaining bounded warning detail for large reports."""

    affected: int = 0
    examples: list[str] = field(default_factory=list)

    def check(self, element: ET.Element, counts: SummaryCounts) -> None:
        mismatch = counts.mismatch(element)
        if mismatch is None:
            return
        self.affected += 1
        if len(self.examples) < _MAX_EXAMPLES:
            label = f"<{element.tag}> #{counts.ordinal} {element.get('name', '')[:100]!r}"
            self.examples.append(f"{label}: {mismatch}")

    def warning(self) -> str | None:
        if not self.affected:
            return None
        remaining = self.affected - len(self.examples)
        more = f"; {remaining} more container(s) not shown" if remaining else ""
        return (
            f"JUnit summary counters do not reconcile in {self.affected} container(s): "
            + "; ".join(self.examples)
            + more
            + ". Counts may describe filtered/aggregated records or an unsupported counting "
            "convention; individual coverage is unverified. Retained outcomes are unchanged."
        )
