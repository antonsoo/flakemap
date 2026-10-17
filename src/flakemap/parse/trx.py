"""Visual Studio TRX test results: what ``dotnet test --logger trx`` writes for
MSTest, xUnit and NUnit projects, and what Azure DevOps keeps per run.

TRX is not a JUnit dialect. A ``<TestRun>`` (namespace
``http://microsoft.com/schemas/VisualStudio/TeamTest/2010``) holds:

- ``<Results>``: one ``<UnitTestResult>`` per test, with ``testName``,
  ``testId``, ``outcome``, ``duration`` (``hh:mm:ss.fffffff``, optionally
  prefixed by days) and ``<Output><ErrorInfo><Message>`` on a failure. A
  data-driven test nests its rows under ``<InnerResults>``. One parent
  observation is kept, with child records retained as evidence. A reported
  nonfailure parent conflicting with a recorded failing child is unknown;
  inner rows do not add independent trials or retries.
- ``<TestDefinitions>``: each ``<UnitTest id=...>`` has a ``<TestMethod
  className=... name=...>``. The class name, minus any ``, Assembly`` suffix,
  becomes the classname. ``testName`` becomes the name, minus the class name
  if it starts with it: MSTest and NUnit write the short name and xUnit the
  fully qualified one, and data rows carry their arguments
  (``CurrencyHasMinorUnits ("JPY",0)``), so each stays a distinct test.
- ``<Times start=...>``: when the run started, used to order runs that have
  no sidecar metadata (see `flakemap.loader`).

Outcomes, from VSTest's ``TestOutcome``: ``Passed`` and
``PassedButRunAborted`` establish a pass; ``Failed`` is a failure;
``Error``, ``Timeout`` and ``Aborted`` are errors;
``NotExecuted`` and ``NotRunnable`` are skips. ``Inconclusive``, ``Completed``
and the run-level ``Warning`` do not establish a test outcome; anything else
(``Pending``, ``InProgress``, ``Disconnected``) is unknown and excluded from
rates.
"""

from __future__ import annotations

import re
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree as ET

from flakemap.models import NestedResults, NestedTestResult, SourceLocation, Status, TestCaseResult
from flakemap.parse.junit import _first_line
from flakemap.parse.trx_counts import summary_warning
from flakemap.parse.xmlinput import (
    MAX_REPORT_BYTES,
    MAX_XML_DEPTH,
    MAX_XML_ELEMENTS,
    contains_dtd,
    exclude_lossy_identifiers,
    read_xml_file,
    without_declaration,
    xml_events,
)
from flakemap.parse.xmltext import repair_xml_text, replaced_warning

_OUTCOMES = {
    "passed": Status.PASS,
    "passedbutrunaborted": Status.PASS,
    "failed": Status.FAIL,
    "error": Status.ERROR,
    "timeout": Status.ERROR,
    "aborted": Status.ERROR,
    "notexecuted": Status.SKIP,
    "notrunnable": Status.SKIP,
}

_DURATION = re.compile(
    r"^(?:([0-9]{1,8})\.)?([0-9]{1,2}):([0-9]{2}):([0-9]{2})(?:\.([0-9]{1,7}))?$"
)
_TICKS_PER_SECOND = 10_000_000
_MAX_TIMESPAN_TICKS = (1 << 63) - 1


def _local(tag: str) -> str:
    """``{namespace}UnitTestResult`` -> ``UnitTestResult``."""
    return tag.rsplit("}", 1)[-1]


def _children(el: ET.Element, name: str) -> list[ET.Element]:
    return [child for child in el if _local(child.tag) == name]


def _child(el: ET.Element, name: str) -> ET.Element | None:
    found = _children(el, name)
    return found[0] if found else None


def is_trx(raw: str) -> bool:
    """True if the document's root element is a TRX ``<TestRun>``."""
    pos = 0
    while pos < len(raw):
        if raw[pos].isspace() or raw[pos] == "\ufeff":
            pos += 1
            continue
        terminator = (
            "-->" if raw.startswith("<!--", pos) else "?>" if raw.startswith("<?", pos) else None
        )
        if terminator is None:
            return re.compile(r"<(?:[\w.-]+:)?TestRun[\s>/]").match(raw, pos) is not None
        end = raw.find(terminator, pos + 2)
        if end == -1:
            return False
        pos = end + len(terminator)
    return False


def _parse_root(raw: str) -> ET.Element:
    depth = 0
    elements = 0
    root = None
    for event, element in xml_events(raw):
        if event == "start":
            elements += 1
            if elements > MAX_XML_ELEMENTS:
                raise ET.ParseError(f"XML exceeds the {MAX_XML_ELEMENTS} element limit")
            depth += 1
            if depth > MAX_XML_DEPTH:
                raise ET.ParseError(f"XML nesting exceeds the {MAX_XML_DEPTH} level limit")
            if root is None:
                root = element
        else:
            depth -= 1
    if root is None:
        raise ET.ParseError("no document element")
    return root


def _duration(raw: str | None) -> float | None:
    if not raw:
        return None
    match = _DURATION.match(raw.strip())
    if not match:
        return None
    days, hours, minutes, seconds, fraction = match.groups()
    if int(hours) >= 24 or int(minutes) >= 60 or int(seconds) >= 60:
        return None
    whole = int(days or 0) * 86400 + int(hours) * 3600 + int(minutes) * 60 + int(seconds)
    ticks = whole * _TICKS_PER_SECOND + int((fraction or "0").ljust(7, "0"))
    # TRX's standard TimeSpan representation cannot exceed a signed Int64
    # number of 100ns ticks. Validate before converting anything to float.
    return ticks / _TICKS_PER_SECOND if ticks <= _MAX_TIMESPAN_TICKS else None


def _started_at(root: ET.Element) -> datetime | None:
    times = _child(root, "Times")
    raw = times.get("start") if times is not None else None
    if not raw:
        return None
    # .NET writes seven fractional digits ("10:00:00.1234567+00:00"); Python reads six.
    raw = re.sub(r"(\.\d{6})\d+", r"\1", raw.strip()).replace("Z", "+00:00")
    try:
        started = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return started if started.tzinfo is not None else None


def _class_without_assembly(raw: str) -> str:
    """Strip only a top-level assembly qualifier, preserving generic arguments.

    NUnit prints ``Pair<Int32,String>``; CLR names can instead contain nested
    ``[[Type, Assembly]]`` and array ranks. Their commas belong to the identity.
    Keep unfamiliar/unbalanced names literally rather than truncating evidence.
    """
    stack: list[str] = []
    escaped = False
    for index, char in enumerate(raw):
        if escaped:
            escaped = False
        elif char == "\\":
            escaped = True
        elif char in "<[":
            stack.append(char)
        elif char in ">]":
            if not stack or stack.pop() != {">": "<", "]": "["}[char]:
                return raw.strip()
        elif char == "," and not stack:
            return raw[:index].strip()
    return raw.strip()


def _definitions(root: ET.Element) -> dict[str, tuple[str, str] | None]:
    """testId -> (class name, method name) from ``<TestDefinitions>``."""
    out: dict[str, tuple[str, str] | None] = {}
    for unit_test in (unit for group in _children(root, "TestDefinitions") for unit in group):
        method = _child(unit_test, "TestMethod")
        test_id = unit_test.get("id")
        if method is None or not test_id:
            continue
        class_name = _class_without_assembly(method.get("className") or "")
        identity = (class_name, method.get("name") or unit_test.get("name") or "")
        out[test_id] = None if test_id in out and out[test_id] != identity else identity
    return out


def _message(result: ET.Element) -> str | None:
    """The failure message's first line. MSTest's reads "Test method X threw exception:"
    with the exception itself on the next line, so a line ending in a colon takes the
    next one along."""
    output = _child(result, "Output")
    info = _child(output, "ErrorInfo") if output is not None else None
    message = _child(info, "Message") if info is not None else None
    if message is None or not message.text:
        return None
    lines = []
    for match in re.finditer(r"[^\r\n]+", message.text):
        line = _first_line(match.group())
        if line:
            lines.append(line)
            if len(lines) == 2:
                break
    if len(lines) > 1 and lines[0].endswith(":"):
        return _first_line(f"{lines[0]} {lines[1]}")
    return _first_line(lines[0] if lines else None)


def _nested_results(result: ET.Element, warnings: list[str]) -> NestedResults | None:
    """Keep the native result tree without flattening correlated data rows."""
    rows: list[NestedTestResult] = []
    issues: list[str] = []
    issue_count = 0
    pending: list[tuple[ET.Element, tuple[int, ...]]] = [(result, ())]
    while pending:
        node, path = pending.pop()
        if path:
            outcome = (node.get("outcome") or "").strip()
            status = _OUTCOMES.get(outcome.lower(), Status.UNKNOWN)
            duration_raw = node.get("duration")
            duration = _duration(duration_raw)
            if (
                status is Status.UNKNOWN
                or outcome.lower() == "passedbutrunaborted"
                or not (node.get("testName") or "").strip()
                or (duration_raw is not None and duration is None)
            ):
                issue_count += 1
                if len(issues) < 3:
                    issues.append(
                        f"inner row {'.'.join(map(str, path))} has "
                        "unknown/incomplete outcome, identity or duration"
                    )
            rows.append(
                NestedTestResult(
                    path,
                    node.get("testName") or "(unnamed)",
                    outcome,
                    status,
                    duration,
                    _message(node),
                )
            )
        supported = []
        for group in _children(node, "InnerResults"):
            for child in group:
                if _local(child.tag) in ("UnitTestResult", "TestResult"):
                    supported.append(child)
                else:
                    issue_count += 1
                    if len(issues) < 3:
                        issues.append(f"unsupported inner result element {_local(child.tag)!r}")
        pending.extend(
            (child, (*path, index)) for index, child in reversed(list(enumerate(supported, 1)))
        )
    if issue_count:
        warnings.append(
            f"{result.get('testName', '(unnamed)')}: {issue_count} nested TRX result issue(s): "
            + "; ".join(issues)
            + "; inner coverage is unverified"
        )
    return NestedResults(result.get("outcome") or "", tuple(rows)) if rows else None


def _nested_contradiction(nested: NestedResults) -> str | None:
    failures = [row for row in nested.rows if row.status.is_failure]
    declared = _OUTCOMES.get(nested.reported_parent_outcome.strip().lower(), Status.UNKNOWN)
    # Unknown is not an assertion of nonfailure. Keep an unsupported parent
    # outcome's own reason; a child failure cannot supply its aggregate result.
    if declared not in (Status.PASS, Status.SKIP) or not failures:
        return None
    evidence = "; ".join(
        f"row {'.'.join(map(str, row.path))} {row.name[:120]!r} "
        f"({row.reported_outcome[:60]}): {row.message or '(no message recorded)'}"
        for row in failures[:3]
    )
    more = f"; {len(failures) - 3} more recorded failing row(s)" if len(failures) > 3 else ""
    return (
        f"TRX parent outcome {nested.reported_parent_outcome[:60]!r} conflicts with "
        f"recorded failing inner results: {evidence}{more}. "
        "The parent outcome is unknown; inner rows are not independent trials"
    )


def read_trx(raw: str, source: str) -> tuple[list[TestCaseResult], list[str], datetime | None]:
    """Parse TRX text. Returns ``(testcases, warnings, run start time)``."""
    warnings: list[str] = []
    if len(raw) > MAX_REPORT_BYTES:
        return (
            [],
            [f"decoded report exceeds the {MAX_REPORT_BYTES} character limit; report omitted"],
            None,
        )
    if contains_dtd(raw):
        return [], ["DTD and entity declarations are not supported"], None
    # The text is already decoded; a declaration naming another encoding (utf-16) would
    # make the parser reject it.
    raw = without_declaration(raw)
    try:
        root = _parse_root(raw)
    except ET.ParseError as first_error:
        # As for JUnit: control characters from test output are the usual reason.
        repaired, _, replaced = repair_xml_text(raw)
        if repaired == raw:
            return [], [f"not well-formed TRX XML ({first_error})"], None
        try:
            root = _parse_root(repaired)
        except ET.ParseError as exc:
            return [], [f"not well-formed TRX XML ({exc})"], None
        if replaced:
            warnings.append(replaced_warning(replaced))
    if _local(root.tag) != "TestRun":
        return [], ["not a TRX <TestRun> document"], None

    definitions = _definitions(root)
    groups = _children(root, "Results")
    if len(groups) > 1:
        warnings.append("multiple TRX Results containers; all records retained for inspection")
    cases: list[TestCaseResult] = []
    for result in (result for group in groups for result in group):
        if _local(result.tag) not in ("UnitTestResult", "TestResult"):
            warnings.append(f"unsupported TRX result element {_local(result.tag)!r}; omitted")
            continue
        test_name = result.get("testName") or "(unnamed)"
        definition = definitions.get(result.get("testId") or "", ("", ""))
        class_name, _method = definition or ("", "")
        # MSTest and NUnit write the short name (data rows as `Method ("JPY",0)`), xUnit the
        # fully qualified one; either way testName carries the parameters, so it is kept.
        if class_name and test_name.startswith(class_name + "."):
            name = test_name[len(class_name) + 1 :]
        elif class_name:
            name = test_name
        else:
            # No definition: split "Namespace.Class.Method" at the last dot before any "(".
            head, paren, params = test_name.partition("(")
            class_name, _, short = head.rpartition(".")
            name = short + paren + params
        outcome = (result.get("outcome") or "").strip()
        status = _OUTCOMES.get(outcome.lower(), Status.UNKNOWN)
        issue = None
        if status is Status.UNKNOWN:
            issue = (
                f"TRX outcome {outcome!r} does not establish pass, failure or skip"
                if outcome
                else "no TRX outcome"
            )
        if not (result.get("testName") or "").strip():
            status = Status.UNKNOWN
            issue = "missing TRX test name; cannot identify this observation"
        if definition is None:
            status = Status.UNKNOWN
            issue = "conflicting TRX test definitions for this testId; identity is ambiguous"
        nested = _nested_results(result, warnings)
        contradiction = _nested_contradiction(nested) if nested else None
        if contradiction:
            status = Status.UNKNOWN
            issue = f"{issue}; {contradiction}" if issue else contradiction
        if outcome.lower() == "passedbutrunaborted":
            warnings.append(
                f"{test_name}: test passed but its run was aborted; history may be incomplete"
            )
        duration_raw = result.get("duration")
        duration = _duration(duration_raw)
        if duration_raw is not None and duration is None:
            warnings.append(f"{test_name}: invalid TRX duration; retained as unknown")
        cases.append(
            TestCaseResult(
                name=name,
                classname=class_name,
                status=status,
                duration=duration,
                message=_message(result) if status is not Status.PASS else None,
                issue=issue,
                nested_results=nested,
            )
        )

    cases = [replace(case, source=SourceLocation(source, i)) for i, case in enumerate(cases, 1)]
    for case in cases:
        if case.issue:
            warnings.append(f"{case.full_name}: {case.issue}; excluded from rates")
    if not cases:
        warnings.append("TRX file contained no test results")
    counters_warning = summary_warning(root)
    if counters_warning:
        warnings.append(counters_warning)
    started = _started_at(root)
    times = _children(root, "Times")
    if len(times) > 1 or (times and times[0].get("start") is not None and started is None):
        warnings.append("invalid or ambiguous TRX start time; report ordering is unavailable")
        started = None
    for summary in _children(root, "ResultSummary"):
        outcome = (summary.get("outcome") or "").lower()
        if outcome in (
            "aborted",
            "disconnected",
            "error",
            "inprogress",
            "pending",
            "passedbutrunaborted",
        ):
            warnings.append(
                f"TRX run summary is {outcome}; collected test results may be incomplete"
            )
    return exclude_lossy_identifiers(cases, warnings), warnings, started


def parse_trx_file(
    path: Path, *, source: str | None = None
) -> tuple[list[TestCaseResult], list[str], datetime | None]:
    """Parse one TRX file. Never raises on a malformed or empty file."""
    raw, warnings = read_xml_file(path)
    if raw is None:
        return [], warnings, None
    cases, more, started = read_trx(raw, source or path.name)
    warnings.extend(more)
    return exclude_lossy_identifiers(cases, warnings), warnings, started
