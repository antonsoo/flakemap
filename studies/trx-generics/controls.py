"""Record complete CLI JSON for existing captured histories, with an optional source override."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCES = [
    "examples/demo_project/runs",
    "examples/trx_history",
    "examples/cofailure_history",
    "examples/retry_history",
    "examples/googletest_history",
    "examples/incomplete_history",
    "examples/trx_counters_project/captures",
    "examples/googletest_project/captures",
    "examples/junit_counters_project/captures",
    "studies/trx-hierarchy/fixtures",
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--source", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "NO_COLOR": "1"}
    if args.source:
        env["PYTHONPATH"] = str(args.source.absolute() / "src")
    rows = []
    for index, source in enumerate(SOURCES):
        run = subprocess.run(
            [str(args.python.absolute()), "-m", "flakemap", str(ROOT / source), "--json"],
            env=env,
            capture_output=True,
            check=False,
        )
        parsed = json.loads(run.stdout)
        canonical = json.dumps(parsed, sort_keys=True, ensure_ascii=False).encode()
        (args.output / f"{index:02d}.json").write_bytes(run.stdout)
        rows.append(
            {
                "source": source,
                "exit": run.returncode,
                "jsonSha256": hashlib.sha256(canonical).hexdigest(),
                "tests": len(parsed["tests"]),
            }
        )
    (args.output / "controls.json").write_text(json.dumps(rows, indent=2) + "\n")
    print(json.dumps({"histories": len(rows), "tests": sum(row["tests"] for row in rows)}))


if __name__ == "__main__":
    main()
