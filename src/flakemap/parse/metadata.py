"""Resolving *run* metadata (commit, branch, timestamp, runner) for a report file.

JUnit XML says nothing reliable about which CI run or commit produced it — that
context lives in the CI system, not the file. flakemap supports three ways to get
it back, tried in this order for each report file:

1. **Sidecar JSON.** A file named ``<report-stem>.meta.json`` next to the report,
   or a single ``meta.json`` shared by every report in that directory (checked in
   that order — the more specific file wins). Recognized keys, all optional:
   ``run_id``, ``commit``, ``branch``, ``timestamp`` (ISO 8601), ``runner``, ``os``,
   ``sequence`` (an integer used to order runs when there is no timestamp). Unknown
   keys are kept under ``extra`` and shown in reports but not used statistically.
2. **Directory-per-run layout.** ``<root>/<run_id>/*.xml`` — the immediate parent
   directory's name becomes ``run_id`` even with no sidecar present. This is the
   natural shape of "download each CI run's artifact into its own folder".
3. **File mtime fallback.** If nothing above supplies a timestamp, the report
   file's modification time is used, and the run is marked so reports can flag
   that its ordering is only as reliable as the filesystem's mtimes (e.g. after a
   `git clone`, mtimes may all collapse to checkout time — flakemap warns about
   this in the CLI when many runs share one mtime).

See ``docs/formats.md`` for worked examples of both layouts.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flakemap.models import RunMetadata


def _parse_timestamp(raw: Any) -> datetime | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _load_sidecar(path: Path) -> dict[str, Any] | None:
    candidates = [
        path.parent / f"{path.stem}.meta.json",
        path.parent / "meta.json",
    ]
    for candidate in candidates:
        if candidate.is_file():
            try:
                data = json.loads(candidate.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(data, dict):
                return data
    return None


_KNOWN_KEYS = {"run_id", "commit", "branch", "timestamp", "runner", "os", "sequence"}


def resolve_metadata(path: Path, root: Path) -> RunMetadata:
    """Build a `RunMetadata` for a single report file found under `root`."""
    try:
        rel = path.relative_to(root)
    except ValueError:
        rel = path

    # Directory-per-run layout: <root>/<run_id>/anything.xml
    dir_run_id = rel.parts[0] if len(rel.parts) > 1 else path.stem

    sidecar = _load_sidecar(path)

    if sidecar:
        run_id = str(sidecar.get("run_id") or dir_run_id)
        commit = sidecar.get("commit")
        branch = sidecar.get("branch")
        runner = sidecar.get("runner")
        os_name = sidecar.get("os")
        sequence = sidecar.get("sequence")
        sequence = int(sequence) if isinstance(sequence, (int, float)) else None
        timestamp = _parse_timestamp(sidecar.get("timestamp"))
        extra = {k: str(v) for k, v in sidecar.items() if k not in _KNOWN_KEYS}
        source = "sidecar" if timestamp is not None or sequence is not None else "path"
        if timestamp is None:
            mtime = path.stat().st_mtime if path.exists() else None
            timestamp = (
                datetime.fromtimestamp(mtime, tz=timezone.utc) if mtime is not None else None
            )
            if source == "path" and sequence is None:
                source = "mtime"
        return RunMetadata(
            run_id=run_id,
            commit=commit,
            branch=branch,
            timestamp=timestamp,
            runner=runner,
            os=os_name,
            sequence=sequence,
            source=source,
            extra=extra,
        )

    mtime = path.stat().st_mtime if path.exists() else None
    timestamp = datetime.fromtimestamp(mtime, tz=timezone.utc) if mtime is not None else None
    return RunMetadata(
        run_id=dir_run_id,
        timestamp=timestamp,
        source="mtime" if timestamp is not None else "unknown",
    )
