"""Parsing tests against real and documented JUnit XML dialects.

`pytest_real.xml` and `jest_junit_real.xml` were generated locally by running the
actual tools (see `docs/formats.md` for the exact commands). `go_junit_report.xml`
and `surefire_report.xml` are hand-authored to match the documented output shape
of go-junit-report and Maven/Gradle Surefire respectively, since those toolchains
are not installed in this environment; sources are cited in `docs/formats.md`.
"""

from pathlib import Path

from flakemap.models import Status
from flakemap.parse.junit import parse_junit_file

FIXTURES = Path(__file__).parent / "fixtures"


def test_pytest_dialect() -> None:
    cases, warnings = parse_junit_file(FIXTURES / "pytest_real.xml")
    assert warnings == []
    by_name = {c.name: c for c in cases}
    assert set(by_name) == {"test_pass", "test_fail", "test_error", "test_skip"}
    assert by_name["test_pass"].status == Status.PASS
    assert by_name["test_fail"].status == Status.FAIL
    assert by_name["test_fail"].message and "assert" in by_name["test_fail"].message
    # pytest reports uncaught exceptions as <failure>, not <error>, unless they
    # happen during setup/teardown -- flakemap must not assume otherwise.
    assert by_name["test_error"].status == Status.FAIL
    assert by_name["test_skip"].status == Status.SKIP
    assert by_name["test_pass"].classname == "test_sample"


def test_jest_junit_dialect() -> None:
    cases, warnings = parse_junit_file(FIXTURES / "jest_junit_real.xml")
    assert warnings == []
    statuses = {c.name.strip(): c.status for c in cases}
    assert statuses[" passes".strip()] == Status.PASS
    assert statuses["fails"] == Status.FAIL
    assert statuses["skipped"] == Status.SKIP
    fail_case = next(c for c in cases if c.name.strip() == "fails")
    assert fail_case.message and "toBe" in fail_case.message


def test_go_junit_report_dialect() -> None:
    cases, warnings = parse_junit_file(FIXTURES / "go_junit_report.xml")
    assert warnings == []
    by_name = {c.name: c for c in cases}
    assert by_name["TestAdd"].status == Status.PASS
    assert by_name["TestDivide"].status == Status.FAIL
    assert by_name["TestSlow"].status == Status.SKIP
    assert by_name["TestAdd"].classname == "github.com/example/pkg"


def test_surefire_dialect() -> None:
    cases, warnings = parse_junit_file(FIXTURES / "surefire_report.xml")
    assert warnings == []
    by_name = {c.name: c for c in cases}
    assert by_name["testAdd"].status == Status.PASS
    assert by_name["testDivideByZero"].status == Status.ERROR
    assert by_name["testSubtract"].status == Status.FAIL
    assert by_name["testDivideByZero"].message == "/ by zero"


def test_malformed_file_is_salvaged_not_raised() -> None:
    cases, warnings = parse_junit_file(FIXTURES / "malformed_truncated.xml")
    assert warnings, "a malformed file must produce a warning, not raise"
    names = {c.name for c in cases}
    # The first, well-formed <testsuite> should still be recovered.
    assert "test_ok" in names
    assert "test_bad" in names


def test_empty_file(tmp_path: Path) -> None:
    empty = tmp_path / "empty.xml"
    empty.write_text("")
    cases, warnings = parse_junit_file(empty)
    assert cases == []
    assert "empty" in warnings[0]


def test_missing_file(tmp_path: Path) -> None:
    cases, warnings = parse_junit_file(tmp_path / "does_not_exist.xml")
    assert cases == []
    assert warnings


def test_garbage_file(tmp_path: Path) -> None:
    garbage = tmp_path / "garbage.xml"
    garbage.write_text("{not xml at all}")
    cases, warnings = parse_junit_file(garbage)
    assert cases == []
    assert warnings
