"""Replay actual CLI reports against identities in the native NUnit TRX files."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from collections import defaultdict
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
NS = "{http://microsoft.com/schemas/VisualStudio/TeamTest/2010}"


def native(path: Path) -> dict[str, dict[str, int]]:
    counts: dict[str, dict[str, int]] = defaultdict(lambda: {"pass": 0, "fail": 0})
    for report in sorted(path.glob("*.trx")):
        root = ET.parse(report).getroot()
        definitions = {
            unit.get("id"): unit.find(NS + "TestMethod").get("className")
            for unit in root.findall(NS + "TestDefinitions/" + NS + "UnitTest")
        }
        for row in root.findall(NS + "Results/" + NS + "UnitTestResult"):
            identity = definitions[row.get("testId")] + "." + row.get("testName")
            counts[identity]["pass" if row.get("outcome") == "Passed" else "fail"] += 1
    return dict(counts)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--phase", required=True, choices=["before", "after"])
    args = parser.parse_args()
    output = args.output.absolute()
    output.mkdir(parents=True, exist_ok=True)
    interpreter = args.python.absolute()
    origin = subprocess.check_output(
        [
            str(interpreter),
            "-c",
            "import pathlib,flakemap;print(pathlib.Path(flakemap.__file__).parent)",
        ],
        text=True,
    ).strip()
    parser_file = Path(origin) / "parse/trx.py"
    rows = []
    for name in ["history", "combined"]:
        source = ROOT / "studies/trx-generics/native-capture" / name
        expected = native(source)
        command = [
            str(interpreter),
            "-m",
            "flakemap",
            str(source),
            "--json",
            "--html",
            str(output / f"{name}.html"),
            "--fail-on-incomplete",
        ]
        env = {**os.environ, "NO_COLOR": "1"}
        run = subprocess.run(
            command, cwd=output, env=env, text=True, capture_output=True, check=False
        )
        result = json.loads(run.stdout)
        (output / f"{name}.json").write_text(run.stdout)
        (output / f"{name}-stderr.txt").write_text(run.stderr)
        if args.phase == "after":
            assert run.returncode == 0 and not result["warnings"], run.stderr
            actual = {
                test["test"]: {"pass": test["runs"]["pass"], "fail": test["runs"]["fail"]}
                for test in result["tests"]
            }
            assert actual == expected, (actual, expected)
            assert all(test["runs"]["unknown"] == 0 for test in result["tests"])
            if name == "history":
                assert {test["test"]: test["classification"] for test in result["tests"]} == {
                    "NativePairs.Pair<Int32,String>.Check": "healthy",
                    "NativePairs.Pair<Int32,Double>.Check": "broken",
                }
        elif name == "history":
            assert run.returncode == 0 and len(result["tests"]) == 1
            assert result["tests"][0]["classification"] == "flaky"
            assert result["tests"][0]["runs"] == {
                "total": 12,
                "pass": 6,
                "fail": 6,
                "skip": 0,
                "unknown": 0,
            }
        else:
            assert run.returncode == 2
            assert sum(test["runs"]["unknown"] for test in result["tests"]) == 1
        rows.append(
            {
                "case": name,
                "exit": run.returncode,
                "nativeIdentities": expected,
                "reported": [
                    {
                        "test": test["test"],
                        "classification": test["classification"],
                        "runs": test["runs"],
                    }
                    for test in result["tests"]
                ],
                "warnings": result["warnings"],
            }
        )
    receipt = {
        "phase": args.phase,
        "parserSha256": hashlib.sha256(parser_file.read_bytes()).hexdigest(),
        "scope": "Actual CLI over compiled controlled NUnit native TRX captures; native XML identities and outcomes are the independent oracle. No production reliability inference.",
        "cases": rows,
    }
    (output / "replay.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(
        json.dumps(
            {"phase": args.phase, "histories": len(rows), "exits": [row["exit"] for row in rows]}
        )
    )


if __name__ == "__main__":
    main()
