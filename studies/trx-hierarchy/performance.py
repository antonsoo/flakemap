"""Measure one authored large hierarchy, not execution of 10,000 application tests.

Rows copy the shape of retained native logger output. GNU time measures the
actual CLI process; input and output hashes retain the comparison's scope.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import platform
import subprocess
import sys
import uuid
from pathlib import Path
from xml.etree import ElementTree as ET

HERE = Path(__file__).resolve().parent
NS = "{http://microsoft.com/schemas/VisualStudio/TeamTest/2010}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--rows", type=int, default=10000)
    args = parser.parse_args()
    if not 1 <= args.rows <= 40000:
        parser.error("choose 1 to 40,000 child records")
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    source = out / "input"
    source.mkdir()
    tree = ET.parse(HERE / "fixtures/passed-parent-failed-row.trx")
    root = tree.getroot()
    root.set("name", "Authored large-hierarchy control")
    inner = root.find(f".//{NS}InnerResults")
    assert inner is not None
    passing, failing = list(inner)
    inner.clear()
    for index in range(args.rows):
        row = copy.deepcopy(failing if index == args.rows - 1 else passing)
        row.set("testName", f"Authored row {index + 1}")
        row.set("executionId", str(uuid.uuid5(uuid.NAMESPACE_URL, f"flakemap-child-{index}")))
        inner.append(row)
    counts = root.find(f"{NS}ResultSummary/{NS}Counters")
    assert counts is not None
    counts.attrib.update(
        total=str(args.rows + 3), executed=str(args.rows + 2), passed=str(args.rows + 1), failed="1"
    )
    ET.register_namespace("", NS[1:-1])
    content = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    (source / "report.trx").write_bytes(content)
    command = [
        "/usr/bin/time",
        "-q",
        "-f",
        '{"wallSeconds":%e,"peakRssKiB":%M}',
        "-o",
        str(out / "timing.json"),
        sys.executable,
        "-m",
        "flakemap",
        str(source),
        "--json",
        "--fail-on-incomplete",
    ]
    with (out / "analysis.json").open("w") as stdout, (out / "stderr.txt").open("w") as stderr:
        run = subprocess.run(command, stdout=stdout, stderr=stderr)
    data = json.loads((out / "analysis.json").read_text())
    parent = next(test for test in data["tests"] if test["test"] == "Capture.Example.Data")
    rows = (
        parent["excluded"][0]["records"][0]["nested_results"]["rows"] if parent["excluded"] else []
    )
    result = {
        "scope": "One authored large hierarchy based on native record shapes; not application execution or a performance guarantee.",
        "machine": "14-vCPU WSL2 Linux, 48 GB RAM",
        "python": platform.python_version(),
        "visibleCpus": len(os.sched_getaffinity(0)),
        "kernel": platform.release(),
        "memTotalKiB": int(
            next(
                line.split()[1]
                for line in Path("/proc/meminfo").read_text().splitlines()
                if line.startswith("MemTotal:")
            )
        ),
        "childRecords": args.rows,
        "sourceBytes": len(content),
        "sourceSha256": hashlib.sha256(content).hexdigest(),
        "analysisBytes": (out / "analysis.json").stat().st_size,
        "analysisSha256": hashlib.sha256((out / "analysis.json").read_bytes()).hexdigest(),
        "exitCode": run.returncode,
        "inputComplete": data["summary"]["input_complete"],
        "reportedTests": data["summary"]["total_tests"],
        "parent": parent["runs"],
        "retainedChildRecords": len(rows),
        **json.loads((out / "timing.json").read_text()),
    }
    (out / "performance.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
