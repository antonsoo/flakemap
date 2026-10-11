"""Compare two complete audit.py outputs, ignoring wall-clock runtime."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    args = parser.parse_args()
    before, after = (json.loads(path.read_text()) for path in (args.before, args.after))
    assert before["job"] == after["job"]
    assert before["verified_xml_files"] == after["verified_xml_files"]
    assert before["test_summaries"] == after["test_summaries"], "test statistics changed"
    print(
        json.dumps(
            {
                key: after[key]
                for key in (
                    "job",
                    "verified_xml_files",
                    "runs",
                    "tests",
                    "ordering",
                    "metadata_sources",
                )
            }
            | {
                "all_test_summaries_unchanged": True,
                "test_summaries_sha256": digest(after["test_summaries"]),
                "compared_fields": sorted(next(iter(after["test_summaries"].values()))),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
