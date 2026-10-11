"""Capture three actual Surefire reports; only environment properties are removed."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from xml.etree import ElementTree as ET

HERE = Path(__file__).resolve().parent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mvn", default="mvn")
    args = parser.parse_args()
    destination = HERE / "fixtures"
    destination.mkdir(exist_ok=True)
    receipts = []
    for scenario in ("pass", "failed", "recovered"):
        command = [args.mvn, "-B", "-q", "test", f"-Dscenario={scenario}"]
        result = subprocess.run(
            command, cwd=HERE / "project", capture_output=True, text=True, check=False
        )
        assert result.returncode == (1 if scenario == "failed" else 0), (
            result.stderr + result.stdout
        )
        report = HERE / "project/target/surefire-reports/TEST-example.ActivityTest.xml"
        root = ET.parse(report).getroot()
        assert len(root.findall("testcase")) == 1
        expected = {"pass": (0, 0, 0), "failed": (1, 2, 0), "recovered": (0, 0, 1)}[scenario]
        counts = tuple(
            len(root.findall(f".//{tag}")) for tag in ("failure", "rerunFailure", "flakyFailure")
        )
        assert counts == expected, (scenario, counts)
        for properties in root.findall("properties"):
            root.remove(properties)
        ET.indent(root)
        target = destination / f"{scenario}.xml"
        ET.ElementTree(root).write(target, encoding="utf-8", xml_declaration=True)
        receipts.append(
            {
                "scenario": scenario,
                "command": ["mvn", *command[1:]],
                "exit_code": result.returncode,
                "markers": dict(
                    zip(("failure", "rerunFailure", "flakyFailure"), counts, strict=True)
                ),
                "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            }
        )
    (destination / "capture.json").write_text(json.dumps(receipts, indent=2) + "\n")
    print(json.dumps(receipts, indent=2))


if __name__ == "__main__":
    main()
