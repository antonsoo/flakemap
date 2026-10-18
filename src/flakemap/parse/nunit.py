"""NUnit 3 result XML, emitted by the native runner or adapter TestOutputXml.

Only structural test-case children of test-run/test-suite are observations.
The runner's fullname is the identity: classname can name an *open* generic
class and cannot distinguish its closed fixtures. Warning and Inconclusive
are retained as unknown outcomes, never passing trials. A final pass without
attempt records supplies no evidence of retry recovery.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree as ET

from flakemap.models import SourceLocation, Status, TestCaseResult
from flakemap.parse.junit import _first_line, _parse_duration
from flakemap.parse.nunit_counts import NUnitCounts, NUnitSummaryWarnings
from flakemap.parse.xmlinput import (
    MAX_REPORT_BYTES,
    contains_dtd,
    exclude_lossy_identifiers,
    has_xml_root,
    parse_xml_root,
    read_xml_file,
    without_declaration,
)
from flakemap.parse.xmltext import repair_xml_text, replaced_warning

_OUTCOMES = {"Passed": Status.PASS, "Failed": Status.FAIL, "Skipped": Status.SKIP}
_ERROR_LABELS = {"Error", "Cancelled", "Invalid"}
_SUITE_METADATA = {
    "command-line",
    "filter",
    "environment",
    "settings",
    "properties",
    "reason",
    "failure",
    "output",
    "attachments",
    "assertions",
}


def _local(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _children(element: ET.Element, name: str) -> list[ET.Element]:
    return [child for child in element if _local(child) == name]


def _message(element: ET.Element) -> str | None:
    for tag in ("failure", "reason"):
        for group in _children(element, tag):
            for message in _children(group, "message"):
                if text := _first_line(message.text):
                    return text
    return None


def is_nunit(raw: str) -> bool:
    return has_xml_root(raw, "test-run")


def _identity(element: ET.Element, fixture: str) -> tuple[str, str, str | None]:
    full = element.get("fullname") or ""
    if not full.strip():
        return (
            element.get("classname") or "",
            element.get("name") or "(unnamed)",
            "missing NUnit fullname; cannot identify this observation across runs",
        )
    # A closed fixture's native fullname preserves type and constructor arguments.
    # Prefix removal is literal; dots/commas in custom case names stay intact.
    for prefix in (fixture, element.get("classname") or ""):
        if prefix and full.startswith(prefix + ".") and len(full) > len(prefix) + 1:
            return prefix, full[len(prefix) + 1 :], None
    # No trusted class prefix is needed to retain the runner's complete identity.
    return "", full, None


def _case(
    element: ET.Element, fixture: str, source: str, ordinal: int, warnings: list[str]
) -> TestCaseResult:
    classname, name, identity_issue = _identity(element, fixture)
    raw = element.get("result") or ""
    label = element.get("label") or ""
    status = _OUTCOMES.get(raw, Status.UNKNOWN)
    if raw == "Failed" and label in _ERROR_LABELS:
        status = Status.ERROR
    issue = None
    if status is Status.UNKNOWN:
        issue = f"NUnit result {raw[:100]!r} does not establish pass, failure or skip"
    failed_assertions = any(
        assertion.get("result") in ("Failed", "Error")
        for group in _children(element, "assertions")
        for assertion in _children(group, "assertion")
    )
    if raw in ("Passed", "Skipped", "Warning", "Inconclusive") and (
        _children(element, "failure") or failed_assertions
    ):
        issue = "NUnit nonfailure result conflicts with recorded failure/assertion evidence"
    if identity_issue:
        issue = f"{issue}; {identity_issue}" if issue else identity_issue
    if issue:
        status = Status.UNKNOWN
        warnings.append(f"{element.get('fullname') or name}: {issue}; excluded from rates")
    duration_raw = element.get("duration")
    duration = _parse_duration(duration_raw)
    if duration_raw is not None and duration is None:
        warnings.append(
            f"{element.get('fullname') or name}: invalid NUnit duration; retained as unknown"
        )
    message = _message(element) if status is not Status.PASS else None
    if status is not Status.PASS and (label or element.get("site")):
        context = ", ".join(
            value
            for value in (
                f"label={label}" if label else "",
                f"site={element.get('site')}" if element.get("site") else "",
            )
            if value
        )
        message = _first_line(f"NUnit {context}: {message or raw}")
    return TestCaseResult(
        name=name,
        classname=classname,
        status=status,
        duration=duration,
        message=message,
        source=SourceLocation(source, ordinal),
        issue=issue,
    )


def _started_at(root: ET.Element) -> datetime | None:
    text = root.get("start-time")
    if not text:
        return None
    try:
        result = datetime.fromisoformat(
            text.removesuffix("Z") + "+00:00" if text.endswith("Z") else text
        )
    except ValueError:
        return None
    return result if result.utcoffset() is not None else None


def read_nunit(raw: str, source: str) -> tuple[list[TestCaseResult], list[str], datetime | None]:
    """Parse one complete native report. A malformed document never asserts coverage."""
    warnings: list[str] = []
    if len(raw) > MAX_REPORT_BYTES:
        return (
            [],
            [f"decoded report exceeds the {MAX_REPORT_BYTES} character limit; report omitted"],
            None,
        )
    if contains_dtd(raw):
        return [], ["DTD and entity declarations are not supported"], None
    raw = without_declaration(raw)
    try:
        root = parse_xml_root(raw)
    except ET.ParseError as first_error:
        repaired, _, replaced = repair_xml_text(raw)
        if repaired == raw:
            return [], [f"not well-formed NUnit XML ({first_error})"], None
        try:
            root = parse_xml_root(repaired)
        except ET.ParseError as exc:
            return [], [f"not well-formed NUnit XML ({exc})"], None
        if replaced:
            warnings.append(replaced_warning(replaced))
    if _local(root) != "test-run":
        return [], ["not an NUnit 3 <test-run> document"], None

    cases: list[TestCaseResult] = []
    summaries = NUnitSummaryWarnings()
    suite_issues: list[str] = []
    suite_issue_count = 0
    unsupported_count = 0
    unsupported: list[str] = []

    def visit(element: ET.Element, fixture: str) -> NUnitCounts:
        nonlocal suite_issue_count, unsupported_count
        counts = NUnitCounts()
        if element.get("type") == "TestFixture":
            fixture = element.get("fullname") or ""
        for child in element:
            tag = _local(child)
            if tag == "test-suite":
                counts.include(visit(child, fixture))
            elif tag == "test-case":
                cases.append(_case(child, fixture, source, len(cases) + 1, warnings))
                counts.observe(child)
            elif tag not in _SUITE_METADATA:
                unsupported_count += 1
                if len(unsupported) < 3:
                    unsupported.append(
                        f"<{tag[:100]}> in {element.get('name', '(unnamed)')[:100]!r}"
                    )
        summaries.check(element, counts)
        outcome = element.get("result")
        # A suite teardown can fail after all child tests passed. Preserve its
        # failure as a warning; never create a fabricated test or change the cases.
        own_failure = outcome == "Failed" and (
            counts.values["failed"] == 0 or element.get("site") == "TearDown"
        )
        contradiction = (
            outcome in ("Passed", "Skipped", "Inconclusive", "Warning")
            and counts.values["failed"] > 0
        )
        unsupported_outcome = outcome is not None and outcome not in (
            "Passed",
            "Failed",
            "Skipped",
            "Inconclusive",
            "Warning",
        )
        if own_failure or contradiction or unsupported_outcome:
            suite_issue_count += 1
            if len(suite_issues) < 3:
                suite_issues.append(
                    f"{element.get('name', '(unnamed)')[:100]!r} result={outcome!r}"
                    + (f" site={element.get('site')!r}" if element.get("site") else "")
                    + (f": {_message(element)}" if _message(element) else "")
                )
        return counts

    visit(root, "")
    if unsupported_count:
        warnings.append(
            f"NUnit contains {unsupported_count} unsupported structural element(s): "
            + "; ".join(unsupported)
            + ". Their contained test coverage is unknown; no results were inferred."
        )
    if warning := summaries.warning():
        warnings.append(warning)
    if suite_issue_count:
        more = (
            f"; {suite_issue_count - len(suite_issues)} more container(s)"
            if suite_issue_count > len(suite_issues)
            else ""
        )
        warnings.append(
            f"NUnit suite outcomes have {suite_issue_count} failure/coverage issue(s): "
            + "; ".join(suite_issues)
            + more
            + ". Suite failures are not extra test observations. Retained case outcomes are unchanged."
        )
    if not cases:
        warnings.append("NUnit file contained no structural test-case results")
    started = _started_at(root)
    if root.get("start-time") is not None and started is None:
        warnings.append("invalid NUnit start-time; report ordering is unavailable")
    return exclude_lossy_identifiers(cases, warnings), warnings, started


def parse_nunit_file(
    path: Path, *, source: str | None = None
) -> tuple[list[TestCaseResult], list[str], datetime | None]:
    raw, warnings = read_xml_file(path)
    if raw is None:
        return [], warnings, None
    cases, more, started = read_nunit(raw, source or path.name)
    warnings.extend(more)
    return exclude_lossy_identifiers(cases, warnings), warnings, started
