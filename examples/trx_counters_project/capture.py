"""Capture controlled result events using the .NET SDK's actual TRX logger."""

from __future__ import annotations

import argparse
import hashlib
import json
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
    command = [
        args.dotnet,
        "run",
        "--project",
        "examples/trx_counters_project",
        "--",
        str(output),
    ]
    run = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=True)
    report = output / "nested.trx"
    raw_hash = hashlib.sha256(report.read_bytes()).hexdigest()
    tree = ET.parse(report)
    tree.getroot().set("name", "Controlled nested-result capture")
    for element in tree.iter():
        element.attrib.pop("computerName", None)
        element.attrib.pop("runDeploymentRoot", None)
    ET.register_namespace("", "http://microsoft.com/schemas/VisualStudio/TeamTest/2010")
    tree.write(report, encoding="utf-8", xml_declaration=True)
    stdout = run.stdout.replace(str(output), "<capture-output>")
    (output / "stdout.txt").write_text(stdout, encoding="utf-8")
    (output / "stderr.txt").write_text(run.stderr, encoding="utf-8")
    sdk = subprocess.check_output([args.dotnet, "--version"], cwd=ROOT, text=True).strip()
    manifest = {
        "sdk": sdk,
        "logger_version_output": stdout.splitlines()[1:],
        "command": ["dotnet", *command[1:-1], "<capture-output>"],
        "exit": run.returncode,
        "raw_sha256": raw_hash,
        "retained_sha256": hashlib.sha256(report.read_bytes()).hexdigest(),
        "transformation": "removed machine and deployment names; replaced TestRun name; counters, outcomes and result hierarchy unchanged",
        "scope": "real VSTest logger with controlled public events; no adapter or test execution",
    }
    (output / "capture.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(stdout, end="")


if __name__ == "__main__":
    main()
