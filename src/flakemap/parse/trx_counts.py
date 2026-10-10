"""Reconcile TRX's primary VSTest counters against structural result records.

VSTest counts Passed + Failed as executed, and writes auxiliary counters such as
notExecuted as zero even when skipped results exist. Only total/executed/passed/
failed are checked here. Nested rows participate in counters but do not become
extra observations in Flakemap's history.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from xml.etree import ElementTree as ET

_COUNTERS = ("total", "executed", "passed", "failed")
_RESULTS = ("UnitTestResult", "TestResult")


def _children(element: ET.Element, *names: str) -> list[ET.Element]:
    return [child for child in element if child.tag.rsplit("}", 1)[-1] in names]


@dataclass(slots=True)
class _Counts:
    total: int = 0
    passed: int = 0
    failed: int = 0

    def observe(self, result: ET.Element) -> None:
        self.total += 1
        outcome = (result.get("outcome") or "").strip().lower()
        self.passed += outcome == "passed"
        self.failed += outcome == "failed"

    def values(self) -> dict[str, int]:
        return {
            "total": self.total,
            "executed": self.passed + self.failed,
            "passed": self.passed,
            "failed": self.failed,
        }


def summary_warning(root: ET.Element) -> str | None:
    summaries = _children(root, "ResultSummary")
    if len(summaries) > 1:
        return "multiple TRX ResultSummary containers; summary counter coverage is ambiguous"
    if not summaries:
        return None
    counters = _children(summaries[0], "Counters")
    if len(counters) > 1:
        return "multiple TRX Counters elements; summary counter coverage is ambiguous"
    if not counters:
        return None
    declared: dict[str, int] = {}
    for key in _COUNTERS:
        raw = counters[0].get(key)
        if raw is None:
            continue
        text = raw.strip()
        if len(text) > 20 or re.fullmatch(r"\+?[0-9]+", text) is None:
            return (
                f"TRX summary counter {key}={raw[:60]!r} is not a supported nonnegative "
                "integer; individual coverage is unverified"
            )
        declared[key] = int(text)
    if not declared:
        return None

    all_results = _Counts()
    without_data_parents = _Counts()

    def observe(result: ET.Element) -> None:
        all_results.observe(result)
        inner = [
            row
            for group in _children(result, "InnerResults")
            for row in _children(group, *_RESULTS)
        ]
        # VSTest 17.11 counts the parent plus its rows; newer logger source
        # subtracts an explicitly marked data-driven parent when rows arrive.
        # Do not infer a data-driven parent from arbitrary nested XML.
        if not (inner and result.get("resultType") == "DataDrivenTest"):
            without_data_parents.observe(result)
        for row in inner:
            observe(row)

    for group in _children(root, "Results"):
        for result in _children(group, *_RESULTS):
            observe(result)
    profiles = [all_results.values()]
    if without_data_parents.values() != profiles[0]:
        profiles.append(without_data_parents.values())
    # Every supplied counter must agree with the same convention.
    if any(all(profile[key] == value for key, value in declared.items()) for profile in profiles):
        return None

    def describe(values: dict[str, int]) -> str:
        return ", ".join(f"{key}={values[key]}" for key in declared)

    evidence = f"all result records ({describe(profiles[0])})"
    if len(profiles) > 1:
        evidence += f" or excluding data-driven parents ({describe(profiles[1])})"
    return (
        f"TRX summary counters do not reconcile: declares {describe(declared)}; retained "
        f"{evidence}. Counts may describe filtered/aggregated records or an unsupported "
        "counting convention; individual coverage is unverified. Retained outcomes are unchanged."
    )
