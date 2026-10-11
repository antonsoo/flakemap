"""Capture actual pytest reports; the tied sidecar times are intentionally synthetic."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main() -> None:
    output = ROOT / "captures"
    output.mkdir(exist_ok=True)
    manifest = []
    for index in range(40):
        report = output / f"{index:02}.xml"
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "-o",
                "addopts=",
                "--override-ini",
                "python_classes=Test",
                "--rootdir=.",
                "--junitxml",
                str(report),
                "test_pipeline.py",
            ],
            cwd=ROOT / "project",
            env={
                "FLAKEMAP_CAPTURE_INDEX": str(index),
                "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
            },
            capture_output=True,
            text=True,
            timeout=20,
        )
        assert completed.returncode == (0 if index < 20 else 1), completed.stderr
        manifest.append(
            {"report": report.name, "pytest_exit": completed.returncode, "controlled_index": index}
        )
        # Deliberately erase chronology in the *metadata*, preserving original XML.
        report.with_suffix(".meta.json").write_text(
            json.dumps(
                {
                    "timestamp": "2026-01-01T00:00:00Z",
                    "commit": f"controlled-{index:02}",
                }
            )
            + "\n"
        )
        manifest[-1]["xml_sha256"] = hashlib.sha256(report.read_bytes()).hexdigest()
        manifest[-1]["metadata_sha256"] = hashlib.sha256(
            report.with_suffix(".meta.json").read_bytes()
        ).hexdigest()
    (ROOT / "capture-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
