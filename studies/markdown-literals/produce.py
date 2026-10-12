"""Capture actual pytest XML. Run with the checkout's locked development Python.

python studies/markdown-literals/produce.py OUTPUT_DIRECTORY
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

source = Path(__file__).resolve().parent / "producer/test_roundtrip.py"
target = Path(sys.argv[1]).resolve()
target.mkdir(parents=True, exist_ok=False)
shutil.copyfile(source, target / source.name)
reports = target / "history"
reports.mkdir()
records = []
for index in range(16):
    relative = f"history/{index:02}.xml"
    failing = index >= 8
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-p",
        "no:randomly",
        "--rootdir=.",
        "--tb=short",
        f"--junitxml={relative}",
        "test_roundtrip.py",
    ]
    run = subprocess.run(
        command,
        cwd=target,
        env={**os.environ, "CONTROLLED_OUTCOME": "fail" if failing else "pass"},
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    assert run.returncode == (1 if failing else 0), run.stdout.decode()
    (target / f"pytest-{index:02}.log").write_bytes(run.stdout)
    data = (target / relative).read_bytes()
    records.append(
        {
            "path": relative,
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "exitCode": run.returncode,
        }
    )
    # Run IDs are explicitly supplied sidecar metadata, not claimed as pytest output.
    marker = (
        "![run](https://example.invalid/run.png)"
        if index % 2
        else "[run](https://example.invalid/run)"
    )
    (reports / f"{index:02}.meta.json").write_text(
        json.dumps({"sequence": index, "run_id": f"run-{index:02}-{marker}"}) + "\n"
    )
(target / "capture.json").write_text(
    json.dumps(
        {
            "scope": "Actual pytest XML from controlled failures and literal parameter IDs; synthetic history, not production CI.",
            "python": sys.version.split()[0],
            "pytest": pytest.__version__,
            "runs": 16,
            "testsPerRun": 12,
            "producerSha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "reports": records,
        },
        indent=2,
    )
    + "\n"
)
print(
    json.dumps({"runs": len(records), "pytest": pytest.__version__, "records": len(records) * 12})
)
