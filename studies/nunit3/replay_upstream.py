"""Compare actual CLI imports with the full retained upstream NUnit populations.

The oracle reads XML fullnames/result fields directly. Repeated fullnames have
one unknown run observation; distinct generated NUnit IDs do not establish a
stable cross-run identity or separate retries.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import subprocess
from collections import defaultdict
from pathlib import Path
from xml.etree import ElementTree as ET

STUDY = Path(__file__).resolve().parent


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def oracle(raw: bytes) -> dict[str, dict[str, int]]:
    groups = defaultdict(list)
    for case in ET.fromstring(raw).iter("test-case"):
        groups[case.get("fullname")].append(case.get("result"))
    expected = {}
    for name, results in groups.items():
        outcome = (
            {"Passed": "pass", "Failed": "fail", "Skipped": "skip"}.get(results[0], "unknown")
            if len(results) == 1
            else "unknown"
        )
        expected[name] = {key: int(outcome == key) for key in ("pass", "fail", "skip", "unknown")}
    return expected


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--phase", choices=("before", "after"), required=True)
    args = parser.parse_args()
    interpreter, output = args.python.absolute(), args.output.absolute()
    output.mkdir(parents=True, exist_ok=True)
    records = []
    for item in json.loads((STUDY / "upstream/manifest.json").read_text())["reports"]:
        name = item["name"]
        compressed = (STUDY / "upstream" / f"{name}.xml.gz").read_bytes()
        assert digest(compressed) == item["gzipSha256"]
        raw = gzip.decompress(compressed)
        assert digest(raw) == item["retainedSha256"]
        folder = output / "inputs" / name
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{name}.xml").write_bytes(raw)
        expected = oracle(raw)
        command = [
            str(interpreter),
            "-m",
            "flakemap",
            str(folder),
            "--json",
            "--fail-on-incomplete",
        ]
        run = subprocess.run(
            command,
            cwd=output,
            env={**os.environ, "NO_COLOR": "1"},
            capture_output=True,
            check=False,
        )
        result = json.loads(run.stdout)
        (output / f"{name}.json").write_bytes(run.stdout)
        (output / f"{name}-stderr.txt").write_bytes(run.stderr)
        actual = {
            test["test"]: {key: test["runs"][key] for key in ("pass", "fail", "skip", "unknown")}
            for test in result["tests"]
        }
        discrepancies = [
            {"test": key, "expected": expected.get(key), "actual": actual.get(key)}
            for key in sorted(expected.keys() | actual.keys())
            if expected.get(key) != actual.get(key)
        ]
        if args.phase == "before":
            assert run.returncode == 2 and not actual
        else:
            assert not discrepancies, discrepancies[:3]
            assert run.returncode == (2 if name.startswith("mathnet") else 0)
            assert not any("counters do not reconcile" in warning for warning in result["warnings"])
        canonical = json.dumps(result, sort_keys=True, ensure_ascii=False).encode()
        records.append(
            {
                "case": name,
                "cliExit": run.returncode,
                "nativeCaseRecords": item["nativeCaseRecords"],
                "uniqueNativeFullnames": len(expected),
                "reportedTests": len(actual),
                "discrepancies": len(discrepancies),
                "firstDiscrepancies": discrepancies[:3],
                "summary": result["summary"],
                "warnings": len(result["warnings"]),
                "counterMismatchWarnings": sum(
                    "counters do not reconcile" in warning for warning in result["warnings"]
                ),
                "canonicalJsonSha256": digest(canonical),
                "canonicalJsonBytes": len(canonical),
            }
        )
    receipt = {
        "phase": args.phase,
        "scope": "Complete retained native reports from unchanged NodaTime 3.2.0 and Math.NET Numerics 5.0.0 source executions. Actual CLI outputs compared to an independent XML grouping/verdict oracle. This verifies import accounting on these two executions, not upstream reliability or general NUnit compatibility.",
        "cases": records,
    }
    (output / "replay.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(
        json.dumps(
            {
                "phase": args.phase,
                "reports": len(records),
                "discrepancies": [row["discrepancies"] for row in records],
            }
        )
    )


if __name__ == "__main__":
    main()
