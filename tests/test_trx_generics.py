"""Native compiled NUnit fixtures must retain their separate outcome histories."""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from flakemap.loader import load_runs
from flakemap.models import Status
from flakemap.parse.trx import read_trx
from flakemap.stats.analyze import analyze

CAPTURE = Path(__file__).resolve().parents[1] / "studies/trx-generics/native-capture"
NS = "http://microsoft.com/schemas/VisualStudio/TeamTest/2010"


def test_native_nunit_generic_fixtures_keep_distinct_executions() -> None:
    result = analyze(load_runs(CAPTURE / "combined"))
    assert not result.warnings
    tests = {test.full_name: test for test in result.tests}
    assert len(tests) == 4
    for name, failed in [
        ("NativePairs.Pair<Int32,String>.Check", 0),
        ("NativePairs.Pair<Int32,Double>.Check", 1),
        ("NativePairs.Single<Int32>.Check", 0),
        ("NativePairs.Ordinary.Check", 0),
    ]:
        assert (tests[name].n, tests[name].n_fail, tests[name].n_unknown) == (1, failed, 0)


def test_native_history_cannot_invent_a_flake_from_two_constant_fixtures() -> None:
    result = analyze(load_runs(CAPTURE / "history"))
    assert not result.warnings
    tests = {test.full_name: test for test in result.tests}
    assert set(tests) == {
        "NativePairs.Pair<Int32,String>.Check",
        "NativePairs.Pair<Int32,Double>.Check",
    }
    passing = tests["NativePairs.Pair<Int32,String>.Check"]
    failing = tests["NativePairs.Pair<Int32,Double>.Check"]
    assert (passing.n, passing.n_fail, passing.classification) == (6, 0, "healthy")
    assert (failing.n, failing.n_fail, failing.classification) == (6, 6, "broken")


@pytest.mark.parametrize(
    ("native_name", "expected"),
    [
        ("Example.Pair<Int32,String>", "Example.Pair<Int32,String>"),
        ("Example.Pair<Int32,String>, Tests, Version=1.0.0.0", "Example.Pair<Int32,String>"),
        (
            "Example.Pair<Dictionary<Int32,String>,Double>, Tests",
            "Example.Pair<Dictionary<Int32,String>,Double>",
        ),
        ("Example.Pair<Int32[,],String>, Tests", "Example.Pair<Int32[,],String>"),
        (
            "Example.Pair`2[[System.Int32, Core],[System.String, Core]], Tests",
            "Example.Pair`2[[System.Int32, Core],[System.String, Core]]",
        ),
        (r"Example.Escaped\,Name, Tests", r"Example.Escaped\,Name"),
        ("Example.Unbalanced<Int32,String", "Example.Unbalanced<Int32,String"),
        ("Example.Mismatched<Int32],String", "Example.Mismatched<Int32],String"),
    ],
)
def test_type_argument_commas_are_identity_while_top_level_assembly_suffix_is_not(
    native_name: str,
    expected: str,
) -> None:
    # Authored grammar boundaries; native execution above establishes the observed defect.
    root = ET.Element("TestRun", xmlns=NS)
    results = ET.SubElement(root, "Results")
    ET.SubElement(results, "UnitTestResult", testId="t", testName="Check", outcome="Passed")
    definitions = ET.SubElement(root, "TestDefinitions")
    test = ET.SubElement(definitions, "UnitTest", id="t")
    ET.SubElement(test, "TestMethod", className=native_name, name="Check")
    (case,), warnings, _ = read_trx(ET.tostring(root, encoding="unicode"), "boundary.trx")
    assert not warnings
    assert case.status is Status.PASS
    assert (case.classname, case.name) == (expected, "Check")
