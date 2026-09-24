"""Turn a directory of JUnit XML files into an ordered list of `Run` objects."""

from __future__ import annotations

from pathlib import Path

from flakemap.models import Run, run_sort_key
from flakemap.parse.junit import parse_junit_file
from flakemap.parse.metadata import resolve_metadata


def load_runs(root: Path, pattern: str = "*.xml") -> list[Run]:
    """Recursively load every JUnit report under `root`, oldest run first.

    Multiple report files that resolve to the same `run_id` (a multi-suite pytest
    run that wrote one XML per suite, say) are merged into a single `Run`.
    """
    root = root.resolve()
    files = sorted(p for p in root.rglob(pattern) if p.is_file())

    by_run_id: dict[str, Run] = {}
    for path in files:
        cases, warnings = parse_junit_file(path)
        metadata = resolve_metadata(path, root)
        existing = by_run_id.get(metadata.run_id)
        if existing is None:
            by_run_id[metadata.run_id] = Run(
                metadata=metadata, testcases=cases, path=path, warnings=list(warnings)
            )
        else:
            existing.testcases.extend(cases)
            existing.warnings.extend(warnings)

    return sorted(by_run_id.values(), key=run_sort_key)
