"""Check native XML/counters and actual CLI replays without importing Flakemap."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from xml.etree import ElementTree as ET

HERE = Path(__file__).resolve().parent
NS = "{http://microsoft.com/schemas/VisualStudio/TeamTest/2010}"


def children(node: ET.Element):
    return [
        row
        for group in node.findall(f"{NS}InnerResults")
        for row in group
        if row.tag in (f"{NS}UnitTestResult", f"{NS}TestResult")
    ]


def descendants(node: ET.Element, path: tuple[int, ...] = ()):
    rows = []
    for index, child in enumerate(children(node), 1):
        position = (*path, index)
        rows.append(
            {
                "path": list(position),
                "name": child.get("testName"),
                "reported_outcome": child.get("outcome"),
            }
        )
        rows.extend(descendants(child, position))
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    before = {row["case"]: row for row in json.loads(args.before.read_text())["observations"]}
    after = {row["case"]: row for row in json.loads(args.after.read_text())["observations"]}
    checks = []
    for source in sorted((HERE / "fixtures").glob("*.trx")):
        root = ET.fromstring(source.read_bytes())
        top = root.findall(f"{NS}Results/{NS}UnitTestResult")
        all_results = root.findall(f".//{NS}UnitTestResult")
        outcomes = [row.get("outcome") for row in all_results]
        assert set(outcomes) <= {"Passed", "Failed", "NotExecuted"}
        observed = {
            "total": len(outcomes),
            "passed": outcomes.count("Passed"),
            "failed": outcomes.count("Failed"),
        }
        observed["executed"] = observed["passed"] + observed["failed"]
        counts = root.find(f"{NS}ResultSummary/{NS}Counters")
        assert counts is not None
        assert {key: int(counts.get(key)) for key in observed} == observed
        original, corrected = before[source.stem], after[source.stem]
        sha = hashlib.sha256(source.read_bytes()).hexdigest()
        assert original["sourceSha256"] == corrected["sourceSha256"] == sha
        contradictions = []
        for record in top:
            nested = descendants(record)
            if record.get("outcome") != "Failed" and any(
                row["reported_outcome"] == "Failed" for row in nested
            ):
                name = record.get("testName")
                data = next(test for test in corrected["analysis"]["tests"] if test["test"] == name)
                assert data["runs"] == {"total": 0, "pass": 0, "fail": 0, "skip": 0, "unknown": 1}
                assert data["failure_rate"] is None
                retained = data["excluded"][0]["records"][0]["nested_results"]
                assert retained["reported_parent_outcome"] == record.get("outcome")
                assert [
                    {key: row[key] for key in ("path", "name", "reported_outcome")}
                    for row in retained["rows"]
                ] == nested
                contradictions.append(
                    {
                        "parent": name,
                        "reportedOutcome": record.get("outcome"),
                        "retainedChildRows": len(nested),
                    }
                )
        assert corrected["analysis"]["summary"]["total_tests"] == len(top)
        assert corrected["exitCode"] == (2 if contradictions else 0)
        assert corrected["analysis"]["summary"]["input_complete"] == (not contradictions)
        if not contradictions:
            assert original["analysis"] == corrected["analysis"]
        else:
            changed = {item["parent"] for item in contradictions}
            original_untouched = [
                test for test in original["analysis"]["tests"] if test["test"] not in changed
            ]
            corrected_untouched = [
                test for test in corrected["analysis"]["tests"] if test["test"] not in changed
            ]
            assert original_untouched == corrected_untouched
        checks.append(
            {
                "case": source.stem,
                "sourceSha256": sha,
                "nativeCounters": observed,
                "topLevelObservations": len(top),
                "contradictions": contradictions,
                "beforeExit": original["exitCode"],
                "afterExit": corrected["exitCode"],
                "unaffectedTestStatisticsIdentical": True,
            }
        )
    assert len(checks) == 7
    result = {
        "scope": "Independent ElementTree inspection of actual SDK 17.11 all-result counters and replay outputs; no Flakemap imports.",
        "nativeFiles": len(checks),
        "contradictoryFiles": sum(bool(c["contradictions"]) for c in checks),
        "checks": checks,
    }
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print({key: result[key] for key in ("nativeFiles", "contradictoryFiles")})


if __name__ == "__main__":
    main()
