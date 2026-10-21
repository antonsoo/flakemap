"""Opt-in pytest capture: ``-p flakemap.pytest_plugin --flakemap-xml=PATH``.

Observe reports without changing outcomes, scheduling retries, or replacing
pytest's JUnit reporter. The controller alone writes the companion report.
"""

from __future__ import annotations

import json
import math
import os
import tempfile
import time
from collections.abc import Generator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from flakemap import __version__

_PHASES = ("setup", "call", "teardown")
_TRACE_LIMIT = 16_000


def _xml(value: object) -> str:
    """XML 1.0 text cannot contain every character a Python exception can."""
    text = str(value)
    text = "".join(
        ch
        if ch in "\t\n\r"
        or 0x20 <= ord(ch) <= 0xD7FF
        or 0xE000 <= ord(ch) <= 0xFFFD
        or 0x10000 <= ord(ch) <= 0x10FFFF
        else "\ufffd"
        for ch in text
    )
    return text


def _text(value: object) -> str:
    text = _xml(value)
    if len(text) > _TRACE_LIMIT:
        text = text[:_TRACE_LIMIT] + "\n[traceback truncated after 16000 characters]"
    return text


@dataclass(frozen=True)
class _Phase:
    attempt: int
    when: str
    outcome: str
    original: str
    duration: float
    detail: str
    message: str


@dataclass
class _Test:
    phases: list[_Phase] = field(default_factory=list)
    issue: str | None = None

    def classify(self) -> tuple[str, list[list[_Phase]], str | None]:
        """Require complete, ordered attempts, with only explicit reruns between."""
        if self.issue:
            return "unknown", [], self.issue
        attempts: list[list[_Phase]] = []
        for phase in self.phases:
            if phase.attempt == len(attempts):
                attempts.append([])
            if not attempts or phase.attempt != len(attempts) - 1:
                return "unknown", [], "missing, repeated or unordered attempt index"
            attempts[-1].append(phase)
        if not attempts:
            return "unknown", [], "no execution phases were received"
        for index, phases in enumerate(attempts):
            order = [p.when for p in phases]
            if order not in (["setup", "call", "teardown"], ["setup", "teardown"]):
                return "unknown", attempts, "missing, duplicate or unordered execution phases"
            if order == ["setup", "teardown"] and phases[0].original == "passed":
                return "unknown", attempts, "successful setup has no call report"
            failed = [p for p in phases if p.original == "failed"]
            reruns = [p for p in phases if p.outcome == "rerun"]
            if index < len(attempts) - 1:
                if not failed or not reruns:
                    return "unknown", attempts, "extra attempt without an explicit failed rerun"
            elif reruns:
                return "unknown", attempts, "retry was announced but its final attempt is absent"
        final = attempts[-1]
        if any(p.original == "failed" for p in final):
            return (
                "error"
                if any(p.when != "call" and p.original == "failed" for p in final)
                else "fail",
                attempts,
                None,
            )
        if any(p.original == "skipped" for p in final):
            if len(attempts) > 1:
                return "unknown", attempts, "retry ended in a skip; recovery was not observed"
            return "skip", attempts, None
        return "pass", attempts, None


def _failure(parent: ET.Element, tag: str, phases: list[_Phase], attempt: int) -> None:
    failed = [p for p in phases if p.original == "failed"]
    # A call failure and teardown error are two phase failures in ONE attempt.
    detail = "\n\n".join(f"[{p.when}]\n{p.detail}" for p in failed)
    message = "; ".join(f"{p.when}: {p.message or 'failed'}" for p in failed)
    marker = ET.SubElement(parent, tag, {"message": message, "attempt": str(attempt)})
    ET.SubElement(marker, "stackTrace").text = detail


class _Capture:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.tests: dict[str, _Test] = {}
        self.issues: list[str] = []
        self.started = datetime.now(timezone.utc).isoformat()
        self.clock = time.perf_counter()

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        test = self.tests.setdefault(report.nodeid, _Test())
        if type(report) is not pytest.TestReport:
            test.issue = "nonstandard phase report (including subtests) is not supported"
            return
        attempt = getattr(report, "rerun", 0)
        original = getattr(report, "flakemap_original_outcome", None)
        outcome = str(report.outcome)  # Retry plugins extend pytest's outcome vocabulary.
        if (
            type(attempt) is not int
            or attempt < 0
            or report.when not in _PHASES
            or outcome not in ("passed", "failed", "skipped", "rerun")
            or original not in ("passed", "failed", "skipped")
            or (outcome == "rerun" and original != "failed")
            or (outcome != "rerun" and outcome != original)
        ):
            test.issue = "unsupported or incomplete attempt/phase metadata"
            return
        if not math.isfinite(report.duration) or report.duration < 0:
            test.issue = "invalid phase duration"
            return
        test.phases.append(
            _Phase(
                attempt,
                report.when,
                outcome,
                original,
                report.duration,
                _text(report.longreprtext),
                _text(
                    getattr(
                        getattr(report.longrepr, "reprcrash", None), "message", report.longreprtext
                    )
                ).splitlines()[0]
                if report.longreprtext
                else "",
            )
        )

    def pytest_collectreport(self, report: pytest.CollectReport) -> None:
        if report.failed:
            self.issues.append(f"collection failed: {_text(report.nodeid)}")

    @pytest.hookimpl(optionalhook=True)
    def pytest_testnodedown(self, node: object, error: object | None) -> None:
        if error is not None:
            self.issues.append("an xdist worker stopped unexpectedly; capture is incomplete")

    def pytest_sessionstart(self) -> None:
        # Replace stale success before running anything. A killed process leaves
        # a visibly incomplete report instead of last invocation's green result.
        self.write(pending=True)

    def write(self, *, pending: bool = False) -> None:
        suite = ET.Element("testsuite", {"name": "pytest retry capture", "timestamp": self.started})
        properties = ET.SubElement(suite, "properties")
        ET.SubElement(properties, "property", {"name": "flakemap.version", "value": __version__})
        ET.SubElement(
            properties, "property", {"name": "pytest.version", "value": pytest.__version__}
        )
        counts = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
        for nodeid, test in sorted(self.tests.items()):
            status, attempts, issue = test.classify()
            if _xml(nodeid) != nodeid:
                status, issue = "unknown", "node ID contains characters XML cannot preserve"
            case = ET.SubElement(
                suite,
                "testcase",
                {"name": _xml(nodeid), "time": str(sum(p.duration for p in test.phases))},
            )
            props = ET.SubElement(case, "properties")
            ET.SubElement(
                props, "property", {"name": "flakemap.pytest.nodeid", "value": json.dumps(nodeid)}
            )
            ET.SubElement(
                props,
                "property",
                {
                    "name": "flakemap.pytest.phases",
                    "value": json.dumps(
                        [
                            {
                                "attempt": p.attempt + 1,
                                "phase": p.when,
                                "outcome": p.outcome,
                                "original_outcome": p.original,
                                "duration": p.duration,
                            }
                            for p in test.phases
                        ],
                        separators=(",", ":"),
                    ),
                },
            )
            counts["tests"] += 1
            if status == "unknown":
                # The existing reader excludes explicit unknown execution
                # attributes. No missing outcome is synthesized as a failure.
                case.set("status", "unknown")
                ET.SubElement(
                    props,
                    "property",
                    {"name": "flakemap.capture_issue", "value": issue or "unknown phases"},
                )
                ET.SubElement(case, "system-out").text = issue
                continue
            if status == "skip":
                counts["skipped"] += 1
                skipped = next(p for p in test.phases if p.original == "skipped")
                ET.SubElement(case, "skipped", {"message": skipped.detail})
                continue
            if status in ("fail", "error"):
                counts["errors" if status == "error" else "failures"] += 1
            for index, phases in enumerate(attempts):
                if not any(p.original == "failed" for p in phases):
                    continue
                error = any(p.original == "failed" and p.when != "call" for p in phases)
                if status == "pass":
                    tag = "flakyError" if error else "flakyFailure"
                elif index == len(attempts) - 1:
                    tag = "error" if error else "failure"
                else:
                    tag = "rerunError" if error else "rerunFailure"
                _failure(case, tag, phases, index + 1)
        issues = ["capture started; pytest has not completed"] if pending else self.issues
        if issues:
            case = ET.SubElement(
                suite, "testcase", {"name": "[flakemap capture incomplete]", "status": "unknown"}
            )
            ET.SubElement(case, "system-out").text = "\n".join(issues)
            props = ET.SubElement(case, "properties")
            ET.SubElement(
                props, "property", {"name": "flakemap.capture_issue", "value": "\n".join(issues)}
            )
            counts["tests"] += 1
        suite.attrib.update({key: str(value) for key, value in counts.items()})
        suite.set("time", str(time.perf_counter() - self.clock))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Same-directory replacement keeps concurrent readers from observing a
        # partially rewritten XML document. No pytest outcome is changed.
        temporary: str | None = None
        try:
            with tempfile.NamedTemporaryFile(dir=self.path.parent, delete=False) as stream:
                temporary = stream.name
                ET.ElementTree(suite).write(stream, encoding="utf-8", xml_declaration=True)
            os.replace(temporary, self.path)
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)

    def pytest_sessionfinish(self, session: pytest.Session, exitstatus: int) -> None:
        if exitstatus not in (0, 1):
            self.issues.append(f"pytest did not finish normally (exit status {exitstatus})")
        if not self.tests:
            self.issues.append("no execution reports were received")
        if session.testscollected != len(self.tests):
            self.issues.append(
                f"selected {session.testscollected} tests but received execution reports for {len(self.tests)} unique node IDs"
            )
        self.write()


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.getgroup("flakemap").addoption(
        "--flakemap-xml",
        metavar="PATH",
        help="Write a companion JUnit report retaining explicit retry attempts",
    )


def pytest_configure(config: pytest.Config) -> None:
    destination = config.getoption("--flakemap-xml")
    if not destination or hasattr(config, "workerinput"):
        return
    path = Path(destination).resolve()
    junit = config.getoption("xmlpath", default=None)
    if junit and Path(junit).resolve() == path:
        raise pytest.UsageError("--flakemap-xml and --junitxml must name different files")
    capture = _Capture(path)
    config.pluginmanager.register(capture)


@pytest.hookimpl(wrapper=True, tryfirst=True)
def pytest_runtest_makereport(
    item: pytest.Item,
) -> Generator[None, pytest.TestReport, pytest.TestReport]:
    report = yield
    if item.config.getoption("--flakemap-xml"):
        # pytest-rerunfailures changes failed to rerun after makereport. This
        # small public report attribute also travels through xdist serialization.
        report.__dict__["flakemap_original_outcome"] = report.outcome
    return report
