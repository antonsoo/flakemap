"""Replay filename permutations through a chosen Python's installed flakemap CLI.

All JUnit reports and sidecars are synthetic. Filenames alone change between
permutations; no remote service or CI account is used.
"""

from __future__ import annotations

import argparse
import itertools
import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

EARLY = "2026-01-01T00:00:00+00:00"
LATE = "2026-01-01T01:00:00+00:00"


def capture(python: str, artifacts: Path | None) -> dict:
    results = []
    profiles = [
        (
            "sidecar-over-report",
            ("sequence", "report_late", "timestamp_early"),
            EARLY,
            "sidecar",
            False,
        ),
        ("earliest-report", ("sequence", "report_late", "report_early"), EARLY, "report", False),
        ("real-conflict", ("sequence", "timestamp_late", "timestamp_early"), None, "sidecar", True),
        ("sequence-and-mtime", ("sequence", "mtime"), None, None, False),
    ]
    for label, kinds, expected_time, expected_source, conflict in profiles:
        for order in itertools.permutations(kinds):
            with TemporaryDirectory(prefix="flakemap-shards-") as temporary:
                root = Path(temporary)
                for index, kind in enumerate(order):
                    path = root / f"{index}.xml"
                    time = EARLY if kind.endswith("early") else LATE
                    attribute = f' timestamp="{time}"' if kind.startswith("report_") else ""
                    path.write_text(
                        f'<testsuite{attribute}><testcase classname="pkg" name="{kind}"/></testsuite>',
                        encoding="utf-8",
                    )
                    metadata = {"run_id": "ci-42"}
                    if kind == "sequence":
                        metadata["sequence"] = 42
                    elif kind.startswith("timestamp_"):
                        metadata["timestamp"] = time
                    path.with_suffix(".meta.json").write_text(
                        json.dumps(metadata), encoding="utf-8"
                    )
                    os.utime(path, (1_700_000_000 + index, 1_700_000_000 + index))
                html = root / "report.html"
                run = subprocess.run(
                    [
                        python,
                        "-m",
                        "flakemap",
                        str(root),
                        "--json",
                        "--html",
                        str(html),
                        "--fail-on-incomplete",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if not run.stdout:
                    raise RuntimeError(run.stderr)
                payload = json.loads(run.stdout)
                summary = payload["summary"]
                metadata = payload["cofailure"]["runs"][0]
                checks = {
                    "gate": run.returncode == (2 if conflict else 0),
                    "complete": summary["input_complete"] is not conflict,
                    "retained_observations": sum(row["runs"]["pass"] for row in payload["tests"])
                    == (0 if conflict else len(kinds)),
                    "excluded_observations": summary["excluded_test_runs"]
                    == (len(kinds) if conflict else 0),
                    "sequence": metadata["sequence"] == 42,
                    "time": conflict
                    or (
                        summary["timestamp_range"] == [expected_time, expected_time]
                        if expected_time
                        else summary["timestamp_range"] is None
                    ),
                    "source": expected_source is None
                    or metadata["metadata_source"] == expected_source,
                    "html_written": html.is_file(),
                }
                results.append(
                    {
                        "profile": label,
                        "order": list(order),
                        "exit": run.returncode,
                        "metadata": metadata,
                        "summary": summary,
                        "warnings": payload["warnings"],
                        "checks": checks,
                        "agrees": all(checks.values()),
                    }
                )
                if artifacts and order == kinds:
                    artifacts.mkdir(parents=True, exist_ok=True)
                    (artifacts / f"{label}.html").write_bytes(html.read_bytes())
    return {
        "scope": "Synthetic JUnit shards, controlled file times, real CLI and report generation.",
        "cases": len(results),
        "disagreements": sum(not row["agrees"] for row in results),
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--artifacts", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    receipt = capture(args.python, args.artifacts)
    print(json.dumps(receipt, indent=2))
    if args.check and receipt["disagreements"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
