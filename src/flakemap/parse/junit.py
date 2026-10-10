"""JUnit XML parsing that tolerates the dialects real tools actually emit.

There is no single "JUnit XML" spec; every test runner's report is a dialect of a
format Ant/Surefire popularized decades ago. The differences that matter here:

- **Root element**: pytest and Jest (jest-junit) usually wrap one or more
  ``<testsuite>`` in a ``<testsuites>`` root. Maven/Gradle Surefire write one bare
  ``<testsuite>`` per test class, no wrapper. Both are handled by treating a lone
  ``<testsuite>`` root as a single-element list.
- **classname**: present and dotted (``pkg.Class``) for pytest/Surefire; Jest often
  puts the describe-block path there instead of a Java-style class; Go reports
  (go-junit-report / gotestsum) put the Go package path there and may have no
  classname at all for package-level failures (build errors). flakemap does not
  assume a Java-style class exists, only that it's a grouping string.
- **status**: a testcase without outcome markers or execution attributes is a pass. GoogleTest's
  ``status="notrun" result="suppressed"`` is a skip, never a successful execution.
  Unknown or contradictory execution attributes remain unknown. Explicit
  flakyFailure/flakyError markers preserve failed attempts before that pass;
  rerunFailure/rerunError preserve exhausted retries. Contradictory markers are
  unknown. FAIL and ERROR both count toward final-failure frequency.
- **partial files**: a CI job killed mid-run can leave a JUnit file with an
  unclosed root tag. ``parse_junit_file`` retains completed testcase elements
  before the first XML error. Comments and CDATA are never interpreted as
  test records. Incomplete records and the unparsed remainder stay unknown.
- **summary counters**: completed suite/container totals must reconcile with
  descendant testcase records or their explicitly recorded retry attempts.
  Otherwise coverage is unverified, even when the XML is well-formed. Totals
  never create missing tests or overwrite individual outcomes.

Real-world samples used to validate each dialect are cited in ``docs/formats.md``.
"""

from __future__ import annotations

import math
import re
import sys
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from xml.etree import ElementTree as ET

from flakemap.models import AttemptFailure, RetryEvidence, SourceLocation, Status, TestCaseResult
from flakemap.parse.junit_counts import SummaryCounts, SummaryWarnings
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

_MAX_MESSAGE_LEN = 500
# `go test` ends every failed test and subtest with this line. A report that keeps one
# record per package (Kubernetes prunes its reports this way; so does a package that
# fails as a whole) names its failed tests nowhere else.
_GO_FAILED_TEST = re.compile(r"^[ \t]*--- FAIL: (\S+)", re.MULTILINE)
_MAX_FAILED_WITHIN = 200


# gotestsum gives every failure the message "Failed" and puts the test's output in the
# body. What the test said is a log line there: `    file_test.go:123: text`.
_GO_GENERIC_MESSAGE = "Failed"
_GO_LOG_LINE = re.compile(r"^[ \t]+(\S+\.go:\d+:[^\n]*)$", re.MULTILINE)
_GO_PANIC = re.compile(r"^panic: [^\n]+", re.MULTILINE)


def _go_message(text: str | None) -> str | None:
    """What a failed Go test last logged before it was marked failed, or its panic.

    The innermost failing test's output comes first, and an assertion is usually the
    last thing a test logs, so this is the last log line above the first `--- FAIL:`,
    from a `_test.go` file when there is one: helpers log their teardown after the
    assertion that failed. It is not always the cause. It is more than "Failed", and
    identical failures still share it.
    """
    if not text:
        return None
    marker = text.find("--- FAIL: ")
    if marker == -1:
        panic = _GO_PANIC.search(text)
        return panic.group()[:_MAX_MESSAGE_LEN] if panic else None
    lines = list(_GO_LOG_LINE.finditer(text, 0, marker))
    if not lines:
        return None
    from_test = [line for line in lines if "_test.go:" in line.group(1).split(" ", 1)[0]]
    last = (from_test or lines)[-1]
    line = last.group(1).strip()
    if line.endswith(":"):
        # The message starts on the next line. testify's has a labelled block there:
        # "Error Trace:", then "Error:" with what went wrong.
        rest = [part.strip() for part in text[last.end() : marker].splitlines() if part.strip()]
        at = next((i for i, part in enumerate(rest[:12]) if part.startswith("Error:")), None)
        if at is not None:
            line += " " + rest[at].removeprefix("Error:").strip()
            if line.endswith(":") and at + 1 < len(rest):  # "Received unexpected error:"
                line += " " + rest[at + 1]
        elif rest:
            line += " " + rest[0]
    return line[:_MAX_MESSAGE_LEN]


def _failed_within(text: str | None, own_name: str) -> tuple[str, ...]:
    """Go tests named as failed in a failure's output, bar the testcase itself."""
    if not text or "--- FAIL: " not in text:
        return ()
    names: dict[str, None] = {}
    for match in _GO_FAILED_TEST.finditer(text):
        name = match.group(1)
        if name != own_name and not name.startswith(own_name + "/"):
            names[name] = None
            if len(names) == _MAX_FAILED_WITHIN:
                break
    return tuple(names)


def _first_line(text: str | None, limit: int = _MAX_MESSAGE_LEN) -> str | None:
    if not text:
        return None
    first = re.search(r"\S", text)
    if first is None:
        return None
    # Never split an entire multi-megabyte log just to display its first line.
    return text[first.start() : first.start() + limit].splitlines()[0].strip() or None


def _parse_duration(raw: str | None) -> float | None:
    if raw is None:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    # Squared differences feed duration correlations; keep arithmetic finite
    # even for corrupt, astronomically large (but representable) input numbers.
    return value if math.isfinite(value) and 0 <= value <= 1e100 else None


def _execution_attributes(
    el: ET.Element, *, failed: bool, skipped: bool, retried: bool
) -> tuple[Status | None, str | None, str | None]:
    """Interpret GoogleTest's execution attributes alongside JUnit child markers.

    `completed` means execution finished, not that it passed. A disabled name
    alone says nothing: --gtest_also_run_disabled_tests can execute that test.
    Other attribute vocabularies must not fall through to an implicit pass.
    """
    raw = {key: el.get(key) for key in ("status", "result") if el.get(key) is not None}
    if not raw:
        return None, None, None
    status = (el.get("status") or "").strip().lower() if "status" in raw else None
    result = (el.get("result") or "").strip().lower() if "result" in raw else None
    label = ", ".join(f"{key}={str(value)[:60]!r}" for key, value in raw.items())
    if status not in (None, "run", "notrun") or result not in (
        None,
        "completed",
        "suppressed",
        "skipped",
    ):
        return Status.UNKNOWN, f"unsupported JUnit execution attributes: {label}", None
    not_executed = status == "notrun" or result in ("suppressed", "skipped")
    if (
        (status == "run" and result == "suppressed")
        or (status == "notrun" and result == "completed")
        or (result == "completed" and skipped)
        or (not_executed and (failed or retried))
    ):
        return Status.UNKNOWN, f"contradictory JUnit execution/outcome markers: {label}", None
    if not_executed:
        description = "Not executed" if status == "notrun" or result == "suppressed" else "Skipped"
        return Status.SKIP, None, f"{description}: {label}"
    return None, None, None


def _outcome_message(el: ET.Element, marker: ET.Element) -> str | None:
    raw = marker.get("message") or marker.text
    if el.get("status") == "run" and el.get("result") in ("completed", "skipped"):
        # GoogleTest prepends a source location and sometimes the uninformative
        # line "Failed". Retain the actual diagnostic, using only a bounded
        # prefix even if the failure body is a multi-megabyte log.
        lines = (raw or "")[:1500].splitlines()
        if lines and re.fullmatch(r".+:\d+", lines[0].strip()):
            lines = lines[1:]
            if lines and lines[0].strip() == "Failed":
                lines = lines[1:]
            meaningful = _first_line("\n".join(lines))
            if meaningful:
                return meaningful
    return _first_line(raw)


def _testcase_from_element(
    el: ET.Element,
    default_classname: str,
    warnings: list[str],
    source: SourceLocation | None = None,
) -> TestCaseResult:
    # A history repeats each name once per run; one shared string instead of thousands.
    name = sys.intern(el.get("name") or "(unnamed)")
    classname = sys.intern(el.get("classname") or el.get("class") or default_classname)

    skipped = el.find("skipped")
    failure = el.find("failure")
    error = el.find("error")

    message: str | None = None
    failed_within: tuple[str, ...] = ()
    if skipped is not None:
        status = Status.SKIP
        message = _outcome_message(el, skipped)
    elif failure is not None:
        status = Status.FAIL
        message = _outcome_message(el, failure)
        failed_within = _failed_within(failure.text, name)
        if message == _GO_GENERIC_MESSAGE:
            message = _go_message(failure.text) or message
    elif error is not None:
        status = Status.ERROR
        message = _outcome_message(el, error)
        failed_within = _failed_within(error.text, name)
        if message == _GO_GENERIC_MESSAGE:
            message = _go_message(error.text) or message
    else:
        status = Status.PASS

    flaky = [child for child in el if child.tag in ("flakyFailure", "flakyError")]
    reruns = [child for child in el if child.tag in ("rerunFailure", "rerunError")]
    terminal = [child for child in el if child.tag in ("failure", "error", "skipped")]
    retry = None
    issue = None
    if (
        (skipped is not None and (failure is not None or error is not None))
        or (flaky and (terminal or reruns))
        or (reruns and (len(terminal) != 1 or skipped is not None))
    ):
        status = Status.UNKNOWN
        issue = "contradictory or incomplete outcome/retry markers"
    elif flaky or reruns:
        failed = (
            flaky
            if flaky
            else [
                child
                for child in el
                if child.tag in ("failure", "error", "rerunFailure", "rerunError")
            ]
        )
        retry = RetryEvidence(
            outcome="recovered" if flaky else "exhausted",
            failures=tuple(
                AttemptFailure(
                    tag=child.tag,
                    status=Status.ERROR if child.tag.lower().endswith("error") else Status.FAIL,
                    message=_first_line(child.get("message"))
                    or _first_line(child.findtext("stackTrace"))
                    or _first_line(child.text),
                )
                for child in failed
            ),
        )

    execution, execution_issue, execution_message = _execution_attributes(
        el,
        failed=failure is not None or error is not None,
        skipped=skipped is not None,
        retried=bool(flaky or reruns),
    )
    if execution is Status.UNKNOWN:
        status, retry, issue = execution, None, execution_issue
    elif execution is Status.SKIP and status is not Status.UNKNOWN:
        status, retry = execution, None
        message = message or execution_message

    if not (el.get("name") or "").strip():
        status, retry = Status.UNKNOWN, None
        issue = "missing JUnit test name; cannot identify this observation"

    duration = _parse_duration(el.get("time"))
    if el.get("time") is not None and duration is None:
        warnings.append(f"{classname}.{name}: invalid duration; retained as unknown")
    return TestCaseResult(
        name=name,
        classname=classname,
        status=status,
        duration=duration,
        message=message,
        retry=retry,
        source=source,
        issue=issue,
        failed_within=failed_within if status.is_failure else (),
    )


@lru_cache(maxsize=256)
def _suite_started(raw: str | None) -> datetime | None:
    """A suite's `timestamp` as an instant, or None when it does not say which.

    gotestsum and pytest write an offset (`2026-10-08T04:35:50Z`); jest-junit and Ant
    write a bare local time, which orders runs from one machine and misorders runs from
    two. Only the first kind is used, as for a TRX file's start time.
    """
    if not raw:
        return None
    text = raw.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        started = datetime.fromisoformat(text)
    except ValueError:
        return None
    return started if started.tzinfo is not None else None


def _structural_cases(
    raw: str, started: list[datetime] | None = None, source: str | None = None
) -> tuple[list[TestCaseResult], list[str], str | None]:
    """Collect only completed records in recognized structural positions.

    Feed small chunks and detach consumed subtrees, so a long run does not keep
    a second copy of every testcase in an XML DOM. Child outcome markers stay
    attached until their testcase ends. Completed cases survive a truncated tail.
    Suites' own start times are appended to ``started`` when it is given, and each case
    is given its 1-based position in ``source``.
    """
    stack: list[tuple[ET.Element, str, bool, SummaryCounts | None]] = []
    cases: list[TestCaseResult] = []
    warnings: list[str] = []
    case_depth: int | None = None
    elements = 0
    containers = {"testsuite", "testsuites"}
    summaries = SummaryWarnings()
    container_ordinal = 0
    try:
        for event, element in xml_events(raw):
            if event == "start":
                elements += 1
                if elements > MAX_XML_ELEMENTS:
                    return cases, warnings, f"XML exceeds the {MAX_XML_ELEMENTS} element limit"
                if len(stack) >= MAX_XML_DEPTH:
                    return (
                        cases,
                        warnings,
                        f"XML nesting exceeds the {MAX_XML_DEPTH} level limit",
                    )
                element.tag = element.tag.rsplit("}", 1)[-1]
                parent_accepts = (
                    not stack
                    or (stack[-1][2] and stack[-1][0].tag in containers)
                    or (len(stack) == 1 and element.tag == "testcase" and case_depth is None)
                )
                eligible = parent_accepts and element.tag in (*containers, "testcase")
                suite_name = (
                    stack[-1][1]
                    if stack
                    else (element.get("name", "") if element.tag != "testcase" else "")
                )
                if eligible and element.tag in containers:
                    suite_name = element.get("name") or suite_name
                    moment = _suite_started(element.get("timestamp"))
                    if moment is not None and started is not None:
                        started.append(moment)
                counts = None
                if eligible and element.tag in containers:
                    container_ordinal += 1
                    counts = SummaryCounts(container_ordinal)
                stack.append((element, suite_name, eligible, counts))
                if eligible and element.tag == "testcase":
                    case_depth = len(stack)
            else:
                _, suite_name, eligible, counts = stack.pop()
                if eligible and element.tag == "testcase":
                    position = SourceLocation(source, len(cases) + 1) if source else None
                    result = _testcase_from_element(element, suite_name, warnings, position)
                    cases.append(result)
                    if stack and (parent_counts := stack[-1][3]) is not None:
                        parent_counts.observe(element, result)
                    case_depth = None
                if counts is not None:
                    summaries.check(element, counts)
                    if stack and (parent_counts := stack[-1][3]) is not None:
                        parent_counts.include(counts)
                if case_depth is None:
                    element.clear()
                    if stack:
                        stack[-1][0].remove(element)
    except ET.ParseError as exc:
        return cases, warnings, str(exc)
    finally:
        if warning := summaries.warning():
            warnings.append(warning)
    return cases, warnings, None


def read_junit(raw: str, source: str) -> tuple[list[TestCaseResult], list[str]]:
    """Read decoded XML, retaining completed records before the first error."""
    cases, warnings, _ = read_junit_with_start(raw, source)
    return cases, warnings


def read_junit_with_start(
    raw: str, source: str
) -> tuple[list[TestCaseResult], list[str], datetime | None]:
    """`read_junit`, and when the report says its earliest suite started."""
    if len(raw) > MAX_REPORT_BYTES:
        return (
            [],
            [f"decoded report exceeds the {MAX_REPORT_BYTES} character limit; report omitted"],
            None,
        )
    if not raw.strip():
        return [], ["file is empty"], None
    if contains_dtd(raw):
        return [], ["DTD and entity declarations are not supported"], None
    raw = without_declaration(raw)
    moments: list[datetime] = []
    cases, warnings, error = _structural_cases(raw, moments, source)
    if error:
        repaired, _, replaced = repair_xml_text(raw)
        if repaired != raw:
            moments = []
            cases, warnings, error = _structural_cases(repaired, moments, source)
        if replaced:
            warnings.append(replaced_warning(replaced))
    if error:
        warnings.append(
            f"file was not well-formed XML ({error}); salvaged {len(cases)} completed "
            "<testcase> element(s) before the error; incomplete records and the remainder omitted"
        )
    for case in cases:
        if case.issue:
            warnings.append(f"{case.full_name}: {case.issue}; excluded from rates")
    if not cases and not warnings:
        warnings.append("parsed successfully but contained zero <testcase> elements")
    return exclude_lossy_identifiers(cases, warnings), warnings, min(moments, default=None)


def parse_junit_file(
    path: Path, *, source: str | None = None
) -> tuple[list[TestCaseResult], list[str]]:
    """Read one bounded JUnit XML file; malformed reports return coverage warnings."""
    raw, warnings = read_xml_file(path)
    if raw is None:
        return [], warnings
    cases, more = read_junit(raw, source or path.name)
    warnings.extend(more)
    return exclude_lossy_identifiers(cases, warnings), warnings
