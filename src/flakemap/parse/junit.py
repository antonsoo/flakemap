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
- **status**: a testcase without terminal outcome markers is a pass. Explicit
  flakyFailure/flakyError markers preserve failed attempts before that pass;
  rerunFailure/rerunError preserve exhausted retries. Contradictory markers are
  unknown. FAIL and ERROR both count toward final-failure frequency.
- **partial files**: a CI job killed mid-run can leave a JUnit file with an
  unclosed root tag. ``parse_junit_file`` falls back to salvaging every
  well-formed ``<testsuite>...</testsuite>`` or ``<testcase>...</testcase>``
  fragment it can find via a bounded regex scan, and records what it had to
  discard as a warning rather than raising.

Real-world samples used to validate each dialect are cited in ``docs/formats.md``.
"""

from __future__ import annotations

import math
import re
from dataclasses import replace
from pathlib import Path
from xml.etree import ElementTree as ET

from flakemap.models import AttemptFailure, RetryEvidence, SourceLocation, Status, TestCaseResult
from flakemap.parse.xmltext import repair_xml_text, replaced_warning

_MAX_MESSAGE_LEN = 500

# Matches a complete <testsuite ...>...</testsuite> or self-closed <testsuite .../>
# fragment, used only as a last-resort recovery path for truncated/malformed files.
_SUITE_FRAGMENT_RE = re.compile(
    r"<testsuite\b[^>]*(?:/>|>.*?</testsuite\s*>)", re.DOTALL | re.IGNORECASE
)
_CASE_FRAGMENT_RE = re.compile(
    r"<testcase\b[^>]*(?:/>|>.*?</testcase\s*>)", re.DOTALL | re.IGNORECASE
)


def _first_line(text: str | None, limit: int = _MAX_MESSAGE_LEN) -> str | None:
    if not text:
        return None
    line = text.strip().splitlines()[0].strip() if text.strip() else None
    if not line:
        return None
    return line[:limit]


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


def _testcase_from_element(
    el: ET.Element, default_classname: str, warnings: list[str]
) -> TestCaseResult:
    name = el.get("name") or "(unnamed)"
    classname = el.get("classname") or el.get("class") or default_classname

    skipped = el.find("skipped")
    failure = el.find("failure")
    error = el.find("error")

    message: str | None = None
    if skipped is not None:
        status = Status.SKIP
        message = _first_line(skipped.get("message") or skipped.text)
    elif failure is not None:
        status = Status.FAIL
        message = _first_line(failure.get("message") or failure.text)
    elif error is not None:
        status = Status.ERROR
        message = _first_line(error.get("message") or error.text)
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
        issue=issue,
    )


def _testcases_from_suite(suite_el: ET.Element, warnings: list[str]) -> list[TestCaseResult]:
    cases = []
    pending = [(suite_el, "")]
    while pending:
        element, suite_name = pending.pop()
        if element.tag == "testcase":
            cases.append(
                _testcase_from_element(element, default_classname=suite_name, warnings=warnings)
            )
        else:
            suite_name = element.get("name") or suite_name
            pending.extend(
                (child, suite_name)
                for child in reversed(element)
                if child.tag in ("testcase", "testsuite", "testsuites")
            )
    return cases


def _suites_from_root(root: ET.Element) -> list[ET.Element]:
    if root.tag in ("testsuite", "testsuites"):
        return [root]
    # Some tools (older gotestsum configs) emit a bare list of <testcase> with no
    # <testsuite> wrapper at all.
    if root.findall("testcase"):
        return [root]
    return []


def _salvage(raw: str) -> tuple[list[TestCaseResult], list[str]]:
    """Best-effort recovery for a file that failed to parse as well-formed XML."""
    warnings: list[str] = []
    cases: list[TestCaseResult] = []

    suite_fragments = _SUITE_FRAGMENT_RE.findall(raw)
    consumed = set()
    for frag in suite_fragments:
        try:
            el = ET.fromstring(frag)
        except ET.ParseError:
            continue
        cases.extend(_testcases_from_suite(el, warnings))
        consumed.add(frag)
    if suite_fragments:
        warnings.append(
            f"file was not well-formed XML; salvaged {len(consumed)}/{len(suite_fragments)} "
            "<testsuite> fragment(s) by regex recovery"
        )
        return cases, warnings

    case_fragments = _CASE_FRAGMENT_RE.findall(raw)
    ok = 0
    for frag in case_fragments:
        try:
            el = ET.fromstring(frag)
        except ET.ParseError:
            continue
        cases.append(_testcase_from_element(el, default_classname="", warnings=warnings))
        ok += 1
    if case_fragments:
        warnings.append(
            f"file was not well-formed XML; salvaged {ok}/{len(case_fragments)} "
            "<testcase> fragment(s) by regex recovery"
        )
    else:
        warnings.append("file was not well-formed XML and no recoverable fragments were found")
    return cases, warnings


def parse_junit_file(
    path: Path, *, source: str | None = None
) -> tuple[list[TestCaseResult], list[str]]:
    """Parse one JUnit XML report file.

    Returns ``(testcases, warnings)``. Never raises on a malformed or empty file;
    an unparseable file yields ``([], [warning])`` instead so a whole batch job
    doesn't abort on one bad report.
    """
    warnings: list[str] = []
    try:
        raw_bytes = path.read_bytes()
    except OSError as exc:
        return [], [f"could not read file: {exc}"]
    try:
        raw = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        raw = raw_bytes.decode("utf-8-sig", errors="replace")
        warnings.append(
            "invalid UTF-8 bytes were replaced; verify test identifiers before using this report"
        )

    if not raw.strip():
        return [], ["file is empty"]

    if re.search(r"<!\s*(?:DOCTYPE|ENTITY)\b", raw, re.IGNORECASE):
        return [], ["DTD and entity declarations are not supported"]
    cases: list[TestCaseResult] = []
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        # A colour code or another control character in a failure message is the usual reason;
        # taking those out lets the whole file parse instead of losing every test in it.
        raw, _, replaced = repair_xml_text(raw)
        try:
            root = ET.fromstring(raw)
        except ET.ParseError:
            root = None
        if replaced:
            warnings.append(replaced_warning(replaced))
    if root is None:
        cases, recovery_warnings = _salvage(raw)
        warnings.extend(recovery_warnings)
    else:
        suites = _suites_from_root(root)
        if not suites:
            return [], ["no <testsuite> or <testcase> elements found"]
        for suite_el in suites:
            cases.extend(_testcases_from_suite(suite_el, warnings))

    cases = [
        replace(case, source=SourceLocation(source or path.name, i))
        for i, case in enumerate(cases, 1)
    ]
    for case in cases:
        if case.issue:
            warnings.append(f"{case.full_name}: {case.issue}; excluded from rates")

    if not cases and not warnings:
        warnings.append("parsed successfully but contained zero <testcase> elements")

    return cases, warnings
