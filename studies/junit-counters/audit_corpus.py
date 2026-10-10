"""Read a local XML corpus and hash every normalized observation in path order.

No downloading; run the Kubernetes study collector separately if its cache is absent.
Timing includes file reads, parsing and evidence hashing, not downstream statistics.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import time
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from flakemap.parse.junit import parse_junit_file


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    paths = sorted(args.root.rglob("*.xml"))
    if not paths:
        raise ValueError("corpus contains no XML reports")
    records_hash, input_hash = hashlib.sha256(), hashlib.sha256()
    statuses: Counter[str] = Counter()
    examples = []
    warning_files = counter_files = total_bytes = 0
    start = time.perf_counter()
    for index, path in enumerate(paths, 1):
        relative = path.relative_to(args.root).as_posix()
        raw = path.read_bytes()
        total_bytes += len(raw)
        input_hash.update(relative.encode() + b"\0" + hashlib.sha256(raw).digest())
        cases, warnings = parse_junit_file(path, source=relative)
        records_hash.update(relative.encode() + b"\0")
        for case in cases:
            statuses[case.status.value] += 1
            records_hash.update(json.dumps(asdict(case), sort_keys=True).encode() + b"\n")
        warning_files += bool(warnings)
        counter_warnings = [warning for warning in warnings if "JUnit summary counters" in warning]
        counter_files += bool(counter_warnings)
        if counter_warnings and len(examples) < 3:
            examples.append({"path": relative, "warnings": counter_warnings})
        if index % 1000 == 0:
            print(f"{index}/{len(paths)} files; {sum(statuses.values())} records", flush=True)
    result = {
        "python": platform.python_version(),
        "files": len(paths),
        "bytes": total_bytes,
        "records": sum(statuses.values()),
        "statuses": dict(statuses),
        "input_manifest_sha256": input_hash.hexdigest(),
        "normalized_records_sha256": records_hash.hexdigest(),
        "files_with_warnings": warning_files,
        "files_with_unreconciled_counters": counter_files,
        "counter_warning_examples": examples,
        "seconds": time.perf_counter() - start,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {key: value for key, value in result.items() if key != "counter_warning_examples"},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
