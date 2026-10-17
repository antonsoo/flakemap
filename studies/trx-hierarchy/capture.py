"""Capture authored hierarchy events with the SDK's actual VSTest logger.

This runs the real logger, not a test adapter or application tests. Only machine
names and deployment identifiers are removed from its output; native hierarchy,
outcomes, counters and recorded times remain unchanged.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dotnet", default="dotnet")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    command = [args.dotnet, "run", "--project", "studies/trx-hierarchy/native", "--", str(output)]
    env = {**os.environ, "DOTNET_CLI_TELEMETRY_OPTOUT": "1"}
    run = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, check=True)
    sdk = subprocess.check_output([args.dotnet, "--version"], cwd=ROOT, text=True).strip()
    records = []
    ET.register_namespace("", "http://microsoft.com/schemas/VisualStudio/TeamTest/2010")
    for report in sorted(output.glob("*/nested.trx")):
        raw = report.read_bytes()
        tree = ET.fromstring(raw)
        tree.set("name", "Controlled TRX hierarchy capture")
        for element in tree.iter():
            element.attrib.pop("computerName", None)
            element.attrib.pop("runDeploymentRoot", None)
        retained = ET.tostring(tree, encoding="utf-8", xml_declaration=True)
        report.write_bytes(retained)
        records.append(
            {
                "scenario": report.parent.name,
                "rawSha256": hashlib.sha256(raw).hexdigest(),
                "retainedSha256": hashlib.sha256(retained).hexdigest(),
                "bytes": len(retained),
            }
        )
    assert len(records) == 7, records
    stdout = run.stdout.replace(str(output), "<capture-output>")
    (output / "stdout.txt").write_text(stdout)
    (output / "stderr.txt").write_text(run.stderr)
    result = {
        "sdk": sdk,
        "logger": [line for line in stdout.splitlines() if line.startswith("Logger")],
        "command": ["dotnet", *command[1:-1], "<capture-output>"],
        "exit": run.returncode,
        "scope": "Actual SDK logger with authored public events; no adapter or application execution.",
        "transformation": "Removed machine/deployment names and replaced TestRun name; outcomes, counters, hierarchy and recorded times unchanged.",
        "reports": records,
    }
    (output / "capture.json").write_text(json.dumps(result, indent=2) + "\n")
    print(f"Captured {len(records)} native reports using SDK {sdk}")


if __name__ == "__main__":
    main()
