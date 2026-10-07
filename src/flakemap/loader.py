"""Turn a directory of JUnit XML (and TRX) files into an ordered list of `Run` objects."""

from __future__ import annotations

from pathlib import Path

from flakemap.models import Run, TestCaseResult, run_sort_key
from flakemap.parse.junit import read_junit
from flakemap.parse.metadata import resolve_metadata
from flakemap.parse.trx import is_trx, read_trx
from flakemap.parse.xmlinput import exclude_lossy_identifiers, read_xml_file

DEFAULT_PATTERN = "*.xml,*.trx"


def report_patterns(pattern: str) -> list[str]:
    globs = [glob.strip() for glob in pattern.split(",") if glob.strip()]
    if not globs or any(Path(glob).is_absolute() or ".." in Path(glob).parts for glob in globs):
        raise ValueError("report patterns must be nonempty relative globs within the scan root")
    return globs


def load_runs(root: Path, pattern: str = DEFAULT_PATTERN) -> list[Run]:
    """Recursively load every JUnit or TRX report under `root`, oldest run first.

    `pattern` is one glob or several separated by commas. Multiple report files
    that resolve to the same `run_id` (a multi-suite pytest run that wrote one XML
    per suite, say) are merged into a single `Run`. A TRX report's own start time
    orders its run when no sidecar or path metadata does (source ``report``).
    """
    root = root.resolve()
    globs = report_patterns(pattern)
    files = sorted({p for g in globs for p in root.rglob(g) if p.is_file()})

    by_run_id: dict[str, Run] = {}
    for path in files:
        source = path.relative_to(root).as_posix()
        started = None
        raw, warnings = read_xml_file(path)
        cases: list[TestCaseResult]
        if raw is None:
            cases = []
        elif path.suffix.lower() == ".trx" or is_trx(raw):
            cases, more, started = read_trx(raw, source)
            warnings.extend(more)
        else:
            cases, more = read_junit(raw, source)
            warnings.extend(more)
        cases = exclude_lossy_identifiers(cases, warnings)
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
