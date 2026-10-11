"""Renaming shards must not change metadata trust or exclude valid observations."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_filename_permutations_through_cli_preserve_timestamp_evidence() -> None:
    root = Path(__file__).resolve().parents[1]
    capture = subprocess.run(
        [sys.executable, str(root / "studies/shard-timestamps/capture.py"), "--check"],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert capture.returncode == 0, capture.stderr or capture.stdout
    receipt = json.loads(capture.stdout)
    assert receipt["cases"] == 20
    assert receipt["disagreements"] == 0
