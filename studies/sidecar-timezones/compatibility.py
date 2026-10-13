"""Compare existing example histories using baseline source and a chosen CLI.

Run from the repository root. The baseline source is explicit; both versions
read the same unchanged examples, including the same filesystem times.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HISTORIES = (
    "examples/demo_project/runs",
    "examples/cofailure_history",
    "examples/googletest_history",
    "examples/incomplete_history",
    "examples/retry_history",
    "examples/trx_history",
    "studies/ordering-evidence/captures",
)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-src", type=Path, required=True)
    parser.add_argument("--python", default=sys.executable)
    args = parser.parse_args()
    names = subprocess.check_output(["git", "ls-files", "-z"]).decode().strip("\0").split("\0")
    sidecars = {}
    offset_free = []
    for name in names:
        path = Path(name)
        if path.name == "meta.json" or path.name.endswith(".meta.json"):
            raw = path.read_bytes()
            timestamp = json.loads(raw).get("timestamp")
            if timestamp is not None:
                parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                sidecars[name] = sha(raw)
                if parsed.utcoffset() is None:
                    offset_free.append(name)
    results = []
    after_env = dict(os.environ)
    # For an installed interpreter, run without PYTHONPATH. For source, callers
    # supply it explicitly. Baseline always uses the frozen source argument.
    for directory in HISTORIES:
        commands = []
        payloads = []
        for env in ({**after_env, "PYTHONPATH": str(args.baseline_src.resolve())}, after_env):
            result = subprocess.run(
                [args.python, "-m", "flakemap", directory, "--json", "--fail-on-incomplete"],
                capture_output=True,
                text=True,
                env=env,
                timeout=120,
            )
            payload = json.loads(result.stdout)
            payloads.append(payload)
            commands.append(
                {"exit": result.returncode, "stdout_sha256": sha(result.stdout.encode())}
            )
        results.append(
            {
                "history": directory,
                "commands": commands,
                "summary": payloads[1]["summary"],
                "identical": commands[0] == commands[1] and payloads[0] == payloads[1],
            }
        )
    receipt = {
        "scope": "All tracked timestamp sidecars and seven existing histories; identical inputs for both CLIs.",
        "timestamp_sidecars": len(sidecars),
        "offset_free_sidecars": offset_free,
        "sidecar_manifest_sha256": sha(json.dumps(sidecars, sort_keys=True).encode()),
        "histories": results,
        "disagreements": sum(not row["identical"] for row in results),
    }
    print(json.dumps(receipt, indent=2))
    if receipt["disagreements"] or offset_free:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
