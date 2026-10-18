"""NUnit counters describe native case results, including warnings/inconclusives.

`testcasecount` is discovery coverage, not the count of selected executions.
Assertions, suites and inferred retry attempts never become extra cases.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from xml.etree import ElementTree as ET

_BUCKETS = {
    "Passed": "passed",
    "Failed": "failed",
    "Warning": "warnings",
    "Inconclusive": "inconclusive",
    "Skipped": "skipped",
}


@dataclass(slots=True)
class NUnitCounts:
    values: dict[str, int] = field(
        default_factory=lambda: dict.fromkeys(("total", *_BUCKETS.values()), 0)
    )

    def observe(self, element: ET.Element) -> None:
        self.values["total"] += 1
        bucket = _BUCKETS.get(element.get("result") or "")
        if bucket:
            self.values[bucket] += 1

    def include(self, child: NUnitCounts) -> None:
        for key, value in child.values.items():
            self.values[key] += value

    def mismatch(self, element: ET.Element) -> str | None:
        declared: dict[str, int] = {}
        for key in (*self.values, "testcasecount"):
            raw = element.get(key)
            if raw is None:
                continue
            if len(raw) > 20 or re.fullmatch(r"[0-9]+", raw) is None:
                return f"{key}={raw[:60]!r} is not a supported nonnegative integer"
            declared[key] = int(raw)
        actual = {key: self.values[key] for key in declared if key != "testcasecount"}
        if any(declared[key] != value for key, value in actual.items()):
            return (
                "declares "
                + ", ".join(f"{key}={declared[key]}" for key in actual)
                + "; retained case results "
                + ", ".join(f"{key}={value}" for key, value in actual.items())
            )
        discovered = declared.get("testcasecount")
        # Filters can legitimately select fewer cases than were discovered.
        if discovered is not None and discovered < self.values["total"]:
            return (
                f"testcasecount={discovered} is smaller than {self.values['total']} retained cases"
            )
        return None


@dataclass(slots=True)
class NUnitSummaryWarnings:
    count: int = 0
    examples: list[str] = field(default_factory=list)

    def check(self, element: ET.Element, counts: NUnitCounts) -> None:
        mismatch = counts.mismatch(element)
        if mismatch is not None:
            self.count += 1
            if len(self.examples) < 3:
                self.examples.append(f"{element.tag} {element.get('name', '')[:100]!r}: {mismatch}")

    def warning(self) -> str | None:
        if not self.count:
            return None
        more = (
            f"; {self.count - len(self.examples)} more container(s)"
            if self.count > len(self.examples)
            else ""
        )
        return (
            f"NUnit summary counters do not reconcile in {self.count} container(s): "
            + "; ".join(self.examples)
            + more
            + ". Individual coverage is unverified. Retained outcomes are unchanged."
        )
