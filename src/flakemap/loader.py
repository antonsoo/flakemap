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
        source = path.relative_to(root).as_posix()
        cases, warnings = parse_junit_file(path, source=source)
        metadata = resolve_metadata(path, root, warnings=warnings)
        warnings = [f"{source}: {warning}" for warning in warnings]
        existing = by_run_id.get(metadata.run_id)
        if existing is None:
            by_run_id[metadata.run_id] = Run(
                metadata=metadata, testcases=cases, path=path, warnings=list(warnings)
            )
        else:
            existing.testcases.extend(cases)
            existing.warnings.extend(warnings)
            # A run id is a grouping key, not permission to silently mix commits
            # or environments. Separate CI matrix jobs need separate run ids.
            md = existing.metadata
            conflicts = []
            for key in ("commit", "branch", "runner", "os", "sequence"):
                before, after = getattr(md, key), getattr(metadata, key)
                if before is not None and after is not None and before != after:
                    conflicts.append(key)
                elif before is None:
                    setattr(md, key, after)
            if (
                md.source != "mtime"
                and metadata.source != "mtime"
                and md.timestamp
                and metadata.timestamp
                and md.timestamp != metadata.timestamp
            ):
                conflicts.append("timestamp")
            if conflicts:
                existing.integrity_issue = "reports sharing this run id disagree on " + ", ".join(
                    conflicts
                )
                existing.warnings.append(
                    f"{source}: {existing.integrity_issue}; run excluded from rates"
                )
            if md.source == "mtime" and metadata.source != "mtime":
                md.timestamp, md.source = metadata.timestamp, metadata.source
            elif md.timestamp is None and metadata.source != "mtime":
                md.timestamp = metadata.timestamp
            elif md.source == metadata.source == "mtime" and md.timestamp and metadata.timestamp:
                md.timestamp = min(md.timestamp, metadata.timestamp)

    return sorted(by_run_id.values(), key=run_sort_key)
