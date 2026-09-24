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
- **status**: a testcase with no ``<failure>``/``<error>``/``<skipped>`` child is a
  pass. A ``<skipped>`` child wins even if the runner (incorrectly) also emits a
  duration. flakemap treats FAIL and ERROR as "not green" everywhere except the
  raw per-test report, where the distinction is kept.
- **partial files**: a CI job killed mid-run can leave a JUnit file with an
  unclosed root tag. ``parse_junit_file`` falls back to salvaging every
  well-formed ``<testsuite>...</testsuite>`` or ``<testcase>...</testcase>``
  fragment it can find via a bounded regex scan, and records what it had to
  discard as a warning rather than raising.

Real-world samples used to validate each dialect are cited in ``docs/formats.md``.
"""

from __future__ import annotations

import re
from pathlib import Path
from xml.etree import ElementTree as ET

from flakemap.models import Status, TestCaseResult

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
    return value if value >= 0 else None


def _testcase_from_element(el: ET.Element, default_classname: str) -> TestCaseResult:
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

    duration = _parse_duration(el.get("time"))
    return TestCaseResult(
        name=name, classname=classname, status=status, duration=duration, message=message
    )


def _testcases_from_suite(suite_el: ET.Element) -> list[TestCaseResult]:
    suite_name = suite_el.get("name") or ""
    cases = []
    for case_el in suite_el.findall("testcase"):
        try:
            cases.append(_testcase_from_element(case_el, default_classname=suite_name))
        except Exception:  # noqa: BLE001 - one bad <testcase> must not sink the file
            continue
    return cases


def _suites_from_root(root: ET.Element) -> list[ET.Element]:
    if root.tag == "testsuites":
        suites = root.findall("testsuite")
        return suites if suites else [root]
    if root.tag == "testsuite":
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
        cases.extend(_testcases_from_suite(el))
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
        try:
            cases.append(_testcase_from_element(el, default_classname=""))
            ok += 1
        except Exception:  # noqa: BLE001
            continue
    if case_fragments:
        warnings.append(
            f"file was not well-formed XML; salvaged {ok}/{len(case_fragments)} "
            "<testcase> fragment(s) by regex recovery"
        )
    else:
        warnings.append("file was not well-formed XML and no recoverable fragments were found")
    return cases, warnings


def parse_junit_file(path: Path) -> tuple[list[TestCaseResult], list[str]]:
    """Parse one JUnit XML report file.

    Returns ``(testcases, warnings)``. Never raises on a malformed or empty file;
    an unparseable file yields ``([], [warning])`` instead so a whole batch job
    doesn't abort on one bad report.
    """
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return [], [f"could not read file: {exc}"]

    if not raw.strip():
        return [], ["file is empty"]

    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return _salvage(raw)

    warnings: list[str] = []
    suites = _suites_from_root(root)
    if not suites:
        return [], ["no <testsuite> or <testcase> elements found"]

    cases: list[TestCaseResult] = []
    for suite_el in suites:
        cases.extend(_testcases_from_suite(suite_el))

    if not cases:
        warnings.append("parsed successfully but contained zero <testcase> elements")

    return cases, warnings
