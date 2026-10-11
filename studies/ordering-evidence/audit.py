"""Check pinned Kubernetes XML bytes, then audit ordering without downloading data."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import time
from pathlib import Path

from flakemap.loader import load_runs
from flakemap.report import to_json_dict
from flakemap.stats import analyze


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--job", required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    rows = manifest["jobs"][args.job]
    files = 0
    for row in rows:
        for report in row["reports"]:
            path = args.cache / args.job / row["build"] / Path(report["name"]).name
            raw = path.read_bytes()
            assert len(raw) == report["size"], path
            assert base64.b64encode(hashlib.md5(raw).digest()).decode() == report["md5"], path
            files += 1
    started = time.perf_counter()
    runs = load_runs(args.cache / args.job)
    result = analyze(runs)
    payload = to_json_dict(result)
    print(
        json.dumps(
            {
                "job": args.job,
                "verified_xml_files": files,
                "elapsed_seconds": round(time.perf_counter() - started, 3),
                "runs": len(runs),
                "tests": len(result.tests),
                "ordering": payload["summary"].get("ordering"),
                "metadata_sources": {
                    key: sum(run.metadata.source == key for run in runs)
                    for key in sorted({run.metadata.source for run in runs})
                },
                "tests_with_temporal_fields": sum(
                    test.activity is not None for test in result.tests
                ),
                "test_summaries": {
                    test.full_name: {
                        "n": test.n,
                        "fail": test.n_fail,
                        "skipped": test.n_skip,
                        "unknown": test.n_unknown,
                        "same_commit_checked": test.failures_checked,
                        "same_commit_passed": test.failures_passed_same_commit,
                        "recovered": test.recovered_runs,
                        "exhausted": test.exhausted_runs,
                        "classification": test.classification,
                        "flip_rate": test.flip_rate if test.flip_pairs else None,
                        "change_point": test.change_point_run_id,
                        "activity": test.activity.state if test.activity else None,
                        "duration_trend": test.duration_trend,
                    }
                    for test in result.tests
                },
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
