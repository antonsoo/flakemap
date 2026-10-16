"""Replay the retained public Kubernetes reports without changing their cache."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

from flakemap.loader import load_runs
from flakemap.report import to_json_dict
from flakemap.stats import analyze

ADDITIONS = {"run_axis", "first_failure_run_id", "history_runs_since_first_failure"}


def old_fields(value):
    if isinstance(value, dict):
        return {key: old_fields(child) for key, child in value.items() if key not in ADDITIONS}
    if isinstance(value, list):
        return [old_fields(child) for child in value]
    return value


def audit(study: Path) -> dict[str, object]:
    manifest_bytes = (study / "manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    jobs = {}
    for job, builds in manifest["jobs"].items():
        started = time.perf_counter()
        root = study / "cache" / job
        # Establish which actual bytes this replay inspected, rather than relying
        # on the earlier study's completion claims.
        inputs = hashlib.sha256()
        files = sorted(
            path for path in root.rglob("*") if path.is_file() and path.suffix in {".xml", ".json"}
        )
        for path in files:
            name = path.relative_to(root).as_posix().encode()
            data = path.read_bytes()
            inputs.update(len(name).to_bytes(8, "big") + name + hashlib.sha256(data).digest())
        runs = load_runs(root)
        result = analyze(runs)
        payload = to_json_dict(result)
        normalized = json.dumps(old_fields(payload), sort_keys=True, separators=(",", ":"))
        windows = {}
        for window in (10, 30, 100):
            found = []
            for test in result.tests:
                if test.classification not in {"flaky", "broken"}:
                    continue
                # The baseline has only execution distances. The corrected source
                # supplies the complete-history distance used by its CLI.
                age = getattr(test, "history_runs_since_first_failure", None)
                if age is None and test.activity is not None:
                    age = test.activity.runs_since_first
                named = [
                    n
                    for n in test.named_failures
                    if n.activity is not None
                    and n.runs > 1
                    and getattr(n, "history_runs_since_first_failure", n.activity.runs_since_first)
                    <= window
                ]
                changed = (
                    test.change_point is not None
                    and test.change_point.rate_after > test.change_point.rate_before
                )
                if (
                    (
                        changed
                        and test.runs_since_change is not None
                        and test.runs_since_change <= window
                    )
                    or (
                        test.activity is not None
                        and test.activity.state == "new"
                        and age is not None
                        and age <= window
                    )
                    or named
                ):
                    found.append(test.full_name)
            windows[str(window)] = sorted(found)
        jobs[job] = {
            "listed_builds": len(builds),
            "input_files": len(files),
            "input_tree_sha256": inputs.hexdigest(),
            "runs": result.total_runs,
            "tests": len(result.tests),
            "usable_test_runs": sum(t.n for t in result.tests),
            "final_failures": sum(t.n_fail for t in result.tests),
            "warnings": len(result.warnings),
            "ordering_available": result.ordering.available,
            "existing_json_fields_sha256": hashlib.sha256(normalized.encode()).hexdigest(),
            "new_flake_candidates_by_window": windows,
            "elapsed_seconds": round(time.perf_counter() - started, 3),
        }
        print(
            f"{job}: {result.total_runs} runs, {sum(t.n for t in result.tests)} observations",
            flush=True,
        )
    return {
        "source": manifest["source"],
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "claim": "Replay of the retained 2026-10-08 capture, not a fresh CI collection",
        "jobs": jobs,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("study", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    receipt = audit(args.study)
    args.out.write_text(json.dumps(receipt, indent=2) + "\n")
