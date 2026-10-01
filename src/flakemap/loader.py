"""Turn a directory of JUnit XML (and TRX) files into an ordered list of `Run` objects."""

from __future__ import annotations

from pathlib import Path

from flakemap.models import Run, run_sort_key
from flakemap.parse.junit import parse_junit_file
from flakemap.parse.metadata import resolve_metadata
from flakemap.parse.trx import is_trx, parse_trx_file

DEFAULT_PATTERN = "*.xml,*.trx"


def _looks_like_trx(path: Path) -> bool:
    if path.suffix.lower() == ".trx":
        return True
    try:
        with path.open("rb") as handle:
            head = handle.read(4096)
    except OSError:
        return False
    encoding = "utf-16" if head[:2] in (b"\xff\xfe", b"\xfe\xff") else "utf-8-sig"
    return is_trx(head.decode(encoding, errors="ignore"))


def load_runs(root: Path, pattern: str = DEFAULT_PATTERN) -> list[Run]:
    """Recursively load every JUnit or TRX report under `root`, oldest run first.

    `pattern` is one glob or several separated by commas. Multiple report files
    that resolve to the same `run_id` (a multi-suite pytest run that wrote one XML
    per suite, say) are merged into a single `Run`. A TRX report's own start time
    orders its run when no sidecar or path metadata does (source ``report``).
    """
    root = root.resolve()
    globs = [g.strip() for g in pattern.split(",") if g.strip()]
    files = sorted({p for g in globs for p in root.rglob(g) if p.is_file()})

    by_run_id: dict[str, Run] = {}
    for path in files:
        source = path.relative_to(root).as_posix()
        started = None
        if _looks_like_trx(path):
            cases, warnings, started = parse_trx_file(path, source=source)
        else:
            cases, warnings = parse_junit_file(path, source=source)
        metadata = resolve_metadata(path, root, warnings=warnings)
        # Without a sidecar timestamp or sequence the run would be ordered by file mtime
        # (sources "path", "mtime"); the report's own start time is more trustworthy.
        if (
            started is not None
            and metadata.sequence is None
            and metadata.source in ("path", "mtime", "unknown")
        ):
            metadata.timestamp, metadata.source = started, "report"
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
