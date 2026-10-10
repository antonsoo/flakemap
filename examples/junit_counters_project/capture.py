"""Run the controlled pytest project and retain its actual reports and console output."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

PROJECT = Path(__file__).resolve().parent


def main() -> None:
    output = PROJECT / "captures"
    output.mkdir(exist_ok=True)
    reports: list[dict[str, object]] = []
    manifest = {
        "pytest": pytest.__version__,
        "python": platform.python_version(),
        "reports": reports,
    }
    for name, selection in [("basic", "not teardown and not subtests"), ("complex", "")]:
        command = [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "test_outcomes.py",
            "-k",
            selection,
            f"--junitxml=captures/{name}.xml",
        ]
        run = subprocess.run(
            command,
            cwd=PROJECT,
            env={**os.environ, "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"},
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        if run.returncode != 1:
            raise RuntimeError(
                f"expected intentional test failures, got {run.returncode}: {run.stdout}"
            )
        (output / f"{name}.txt").write_text(run.stdout, encoding="utf-8")
        report = output / f"{name}.xml"
        raw_hash = hashlib.sha256(report.read_bytes()).hexdigest()
        tree = ET.parse(report)
        for suite in tree.iter("testsuite"):
            suite.attrib.pop("hostname", None)
        for element in tree.iter():
            if element.text:
                element.text = element.text.replace(str(PROJECT.parents[1]) + "/", "")
        tree.write(report, encoding="utf-8", xml_declaration=True)
        reports.append(
            {
                "file": report.name,
                "command": ["python", *command[1:]],
                "exit": run.returncode,
                "raw_sha256": raw_hash,
                "retained_sha256": hashlib.sha256(report.read_bytes()).hexdigest(),
                "transformation": "removed hostname; made repository paths in diagnostic text relative; outcomes and counters unchanged",
            }
        )
    (output / "capture.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
