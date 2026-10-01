"""Visual Studio TRX test results: what ``dotnet test --logger trx`` writes for
MSTest, xUnit and NUnit projects, and what Azure DevOps keeps per run.

TRX is not a JUnit dialect. A ``<TestRun>`` (namespace
``http://microsoft.com/schemas/VisualStudio/TeamTest/2010``) holds:

- ``<Results>``: one ``<UnitTestResult>`` per test, with ``testName``,
  ``testId``, ``outcome``, ``duration`` (``hh:mm:ss.fffffff``, optionally
  prefixed by days) and ``<Output><ErrorInfo><Message>`` on a failure. A
  data-driven test nests its rows under ``<InnerResults>``; the parent's
  outcome already aggregates them, so the parent is the one record kept.
- ``<TestDefinitions>``: each ``<UnitTest id=...>`` has a ``<TestMethod
  className=... name=...>``. The class name, minus any ``, Assembly`` suffix,
  becomes the classname. ``testName`` becomes the name, minus the class name
  if it starts with it: MSTest and NUnit write the short name and xUnit the
  fully qualified one, and data rows carry their arguments
  (``CurrencyHasMinorUnits ("JPY",0)``), so each stays a distinct test.
- ``<Times start=...>``: when the run started, used to order runs that have
  no sidecar metadata (see `flakemap.loader`).

Outcomes, from the TRX schema's ``TestOutcome``: ``Passed``,
``PassedButRunAborted``, ``Warning`` and ``Completed`` are passes; ``Failed``
is a failure; ``Error``, ``Timeout`` and ``Aborted`` are errors;
``NotExecuted``, ``NotRunnable`` and ``Inconclusive`` are skips; anything else
(``Pending``, ``InProgress``, ``Disconnected``) is unknown and excluded from
rates.
"""

from __future__ import annotations

import re
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree as ET

from flakemap.models import SourceLocation, Status, TestCaseResult
from flakemap.parse.junit import _first_line

_OUTCOMES = {
    "passed": Status.PASS,
    "passedbutrunaborted": Status.PASS,
    "warning": Status.PASS,
    "completed": Status.PASS,
    "failed": Status.FAIL,
    "error": Status.ERROR,
    "timeout": Status.ERROR,
    "aborted": Status.ERROR,
    "notexecuted": Status.SKIP,
    "notrunnable": Status.SKIP,
    "inconclusive": Status.SKIP,
}

_DURATION = re.compile(r"^(?:(\d+)\.)?(\d{1,2}):(\d{2}):(\d{2}(?:\.\d+)?)$")


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
    head = re.sub(r"<\?xml[^>]*\?>|<!--.*?-->", "", raw[:4096], flags=re.DOTALL).lstrip()
    return re.match(r"<(?:[\w.-]+:)?TestRun[\s>/]", head) is not None


def _duration(raw: str | None) -> float | None:
    if not raw:
        return None
    match = _DURATION.match(raw.strip())
    if not match:
        return None
    days, hours, minutes, seconds = match.groups()
    return int(days or 0) * 86400 + int(hours) * 3600 + int(minutes) * 60 + float(seconds)


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


def _definitions(root: ET.Element) -> dict[str, tuple[str, str]]:
    """testId -> (class name, method name) from ``<TestDefinitions>``."""
    out: dict[str, tuple[str, str]] = {}
    definitions = _child(root, "TestDefinitions")
    if definitions is None:
        return out
    for unit_test in definitions:
        method = _child(unit_test, "TestMethod")
        test_id = unit_test.get("id")
        if method is None or not test_id:
            continue
        class_name = (method.get("className") or "").split(",", 1)[0].strip()
        out[test_id] = (class_name, method.get("name") or unit_test.get("name") or "")
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
    lines = [line.strip() for line in message.text.strip().splitlines() if line.strip()]
    if len(lines) > 1 and lines[0].endswith(":"):
        return _first_line(f"{lines[0]} {lines[1]}")
    return _first_line(lines[0] if lines else None)


def read_trx(raw: str, source: str) -> tuple[list[TestCaseResult], list[str], datetime | None]:
    """Parse TRX text. Returns ``(testcases, warnings, run start time)``."""
    warnings: list[str] = []
    # The text is already decoded; a declaration naming another encoding (utf-16) would
    # make the parser reject it.
    raw = re.sub(r"^\s*<\?xml[^>]*\?>", "", raw)
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        return [], [f"not well-formed TRX XML ({exc})"], None
    if _local(root.tag) != "TestRun":
        return [], ["not a TRX <TestRun> document"], None

    definitions = _definitions(root)
    results = _child(root, "Results")
    cases: list[TestCaseResult] = []
    for result in results if results is not None else []:
        if _local(result.tag) not in ("UnitTestResult", "TestResult"):
            continue
        test_name = result.get("testName") or "(unnamed)"
        class_name, _method = definitions.get(result.get("testId") or "", ("", ""))
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
            issue = f"unrecognized TRX outcome {outcome!r}" if outcome else "no TRX outcome"
        duration_raw = result.get("duration")
        duration = _duration(duration_raw)
        if duration_raw and duration is None:
            warnings.append(f"{test_name}: invalid duration {duration_raw!r}; retained as unknown")
        cases.append(
            TestCaseResult(
                name=name,
                classname=class_name,
                status=status,
                duration=duration,
                message=_message(result) if status.is_failure or status is Status.SKIP else None,
                issue=issue,
            )
        )

    cases = [replace(case, source=SourceLocation(source, i)) for i, case in enumerate(cases, 1)]
    for case in cases:
        if case.issue:
            warnings.append(f"{case.full_name}: {case.issue}; excluded from rates")
    if not cases:
        warnings.append("TRX file contained no test results")
    return cases, warnings, _started_at(root)


def parse_trx_file(
    path: Path, *, source: str | None = None
) -> tuple[list[TestCaseResult], list[str], datetime | None]:
    """Parse one TRX file. Never raises on a malformed or empty file."""
    try:
        raw_bytes = path.read_bytes()
    except OSError as exc:
        return [], [f"could not read file: {exc}"], None
    warnings: list[str] = []
    encoding = "utf-16" if raw_bytes[:2] in (b"\xff\xfe", b"\xfe\xff") else "utf-8-sig"
    try:
        raw = raw_bytes.decode(encoding)
    except UnicodeDecodeError:
        raw = raw_bytes.decode(encoding, errors="replace")
        warnings.append("invalid text bytes were replaced; verify test identifiers")
    if re.search(r"<!\s*(?:DOCTYPE|ENTITY)\b", raw, re.IGNORECASE):
        return [], ["DTD and entity declarations are not supported"], None
    cases, more, started = read_trx(raw, source or path.name)
    return cases, warnings + more, started
