"""Capture 56 actual pytest reports with old failures and a sparse tail."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent


def capture(output: Path) -> dict[str, object]:
    if output.exists() and any(output.iterdir()):
        raise ValueError("capture output must be empty; keep earlier evidence separate")
    output.mkdir(parents=True, exist_ok=True)
    records = []
    for sequence in range(56):
        folder = output / f"run-{sequence:02}"
        folder.mkdir()
        command = [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "test_history.py",
            "--junitxml",
            str(
                (folder / "junit.xml").resolve(),
            ),
        ]
        if sequence >= 36:
            command += ["-k", "not test_removed_after_build_35"]
        process = subprocess.run(
            command,
            cwd=HERE / "project",
            env={
                **os.environ,
                "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
                "FLAKEMAP_STUDY_SEQUENCE": str(sequence),
            },
            capture_output=True,
            text=True,
            check=False,
        )
        expected = 1 if sequence in {30, 32, 34} else 0
        if process.returncode != expected:
            raise RuntimeError(
                f"pytest run {sequence} returned {process.returncode}: {process.stderr}"
            )
        # Remove only machine-specific absolute path prefixes. Keep every outcome,
        # counter, diagnostic, duration and timestamp produced by the reporter.
        prefix = str(HERE.parents[1]) + os.sep
        console = (process.stdout + process.stderr).replace(str(output.resolve()), "<capture>")
        console = console.replace(prefix, "")
        (folder / "pytest.txt").write_text(console, encoding="utf-8")
        (folder / "meta.json").write_text(
            json.dumps({"sequence": sequence, "run_id": folder.name}) + "\n",
            encoding="utf-8",
        )
        raw_data = (folder / "junit.xml").read_bytes()
        data = raw_data.replace(prefix.encode(), b"")
        (folder / "junit.xml").write_bytes(data)
        records.append(
            {
                "run_id": folder.name,
                "pytest_exit": process.returncode,
                "raw_xml_sha256": hashlib.sha256(raw_data).hexdigest(),
                "xml_sha256": hashlib.sha256(data).hexdigest(),
                "xml_bytes": len(data),
            }
        )
    return {
        "python": platform.python_version(),
        "pytest": pytest.__version__,
        "provenance": "56 controlled pytest executions; not production failures",
        "sanitization": "Only the absolute repository path prefix is removed from XML and console text.",
        "reports": records,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    receipt = capture(args.output)
    (args.output / "capture.json").write_text(
        json.dumps(receipt, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"runs": len(receipt["reports"]), "output": str(args.output)}))
