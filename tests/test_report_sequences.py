"""Report times are evidence even when a sidecar supplies a sequence."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_actual_cli_decisions_do_not_depend_on_sequence_sidecar_location() -> None:
    root = Path(__file__).resolve().parents[1]
    run = subprocess.run(
        [sys.executable, str(root / "studies/report-sequences/capture.py"), "--check"],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert run.returncode == 0, run.stderr or run.stdout
    receipt = json.loads(run.stdout)
    assert receipt["cases"] == 18
    assert receipt["incorrect_gate_decisions"] == 0
