"""Resolving *run* metadata (commit, branch, timestamp, runner) for a report file.

JUnit XML says nothing reliable about which CI run or commit produced it — that
context lives in the CI system, not the file. flakemap supports three ways to get
it back, tried in this order for each report file:

1. **Sidecar JSON.** A file named ``<report-stem>.meta.json`` next to the report,
   or the nearest ancestor ``meta.json`` within the scan root (checked in
   that order — the more specific file wins). Recognized keys, all optional:
   ``run_id``, ``commit``, ``branch``, ``timestamp`` (ISO 8601 with a UTC offset), ``runner``, ``os``,
   ``sequence`` (an integer ordering key). Unknown
   keys are kept under ``extra`` and shown in reports but not used statistically.
2. **Directory-per-run layout.** ``<root>/<run_id>/*.xml`` — the first directory
   beneath the scan root becomes ``run_id`` even with no sidecar present. This is the
   natural shape of "download each CI run's artifact into its own folder".
3. **File mtime fallback.** If nothing supplies a timestamp or sequence, the report
   file's modification time is retained with source ``mtime``. This is copy
   evidence, not a recorded run time; it cannot establish chronology.

See ``docs/formats.md`` for worked examples of both layouts.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flakemap.models import RunMetadata

MAX_METADATA_BYTES = 1024 * 1024
MAX_METADATA_DEPTH = 128


def _validate_structure(data: Any) -> None:
    """Keep metadata behavior consistent across Python JSON implementations."""
    pending = [(data, 0)]
    while pending:
        value, depth = pending.pop()
        if depth > MAX_METADATA_DEPTH:
            raise ValueError(f"exceeds the {MAX_METADATA_DEPTH} level nesting limit")
        if isinstance(value, dict):
            pending.extend((item, depth + 1) for item in value.values())
        elif isinstance(value, list):
            pending.extend((item, depth + 1) for item in value)
        elif isinstance(value, float) and not math.isfinite(value):
            raise ValueError("nonfinite JSON number")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def _nonfinite(_: str) -> Any:
    raise ValueError("nonfinite JSON number")


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
    # A local clock reading is not an instant. Inventing UTC can reverse the
    # history when artifacts came from runners in different time zones.
    return dt if dt.utcoffset() is not None else None


def _sidecar_text(raw: bytes) -> str:
    """A sidecar's text, as shells write it.

    Windows PowerShell's `>` and `Out-File` write UTF-16 with a byte-order mark, and its
    `-Encoding utf8` writes UTF-8 with one. Read as plain UTF-8, either lost the run its
    commit and its place in the order, with a warning about a file that looked fine.
    """
    if raw.startswith((b"\xff\xfe\x00\x00", b"\x00\x00\xfe\xff")):
        return raw.decode("utf-32")
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16")
    return raw.decode("utf-8-sig")


def _load_sidecar(path: Path, root: Path, warnings: list[str]) -> dict[str, Any] | None:
    candidates = [path.with_suffix(".meta.json")]
    for parent in path.parents:
        candidates.append(parent / "meta.json")
        if parent == root or not parent.is_relative_to(root):
            break
    for candidate in candidates:
        if candidate.is_file():
            try:
                with candidate.open("rb") as handle:
                    raw = handle.read(MAX_METADATA_BYTES + 1)
                if len(raw) > MAX_METADATA_BYTES:
                    raise ValueError(f"exceeds the {MAX_METADATA_BYTES} byte limit")
                data = json.loads(
                    _sidecar_text(raw), object_pairs_hook=_unique_object, parse_constant=_nonfinite
                )
                _validate_structure(data)
            except (OSError, ValueError, RecursionError) as exc:
                warnings.append(f"invalid metadata sidecar {candidate.name}: {exc}")
                return None
            if isinstance(data, dict):
                return data
            warnings.append(f"metadata sidecar {candidate.name} must contain an object")
            return None
    return None


_KNOWN_KEYS = {"run_id", "commit", "branch", "timestamp", "runner", "os", "sequence"}


def resolve_metadata(path: Path, root: Path, *, warnings: list[str] | None = None) -> RunMetadata:
    """Build a `RunMetadata` for a single report file found under `root`."""
    try:
        rel = path.relative_to(root)
    except ValueError:
        rel = path

    # Directory-per-run layout: <root>/<run_id>/anything.xml
    dir_run_id = rel.parts[0] if len(rel.parts) > 1 else path.stem

    warnings = warnings if warnings is not None else []
    sidecar = _load_sidecar(path, root, warnings)

    if sidecar:
        for key in ("run_id", "commit", "branch", "runner", "os"):
            value = sidecar.get(key)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                warnings.append(f"metadata {key} must be a nonempty string; ignored")
                sidecar.pop(key)
        run_id = str(sidecar.get("run_id") or dir_run_id)
        commit = sidecar.get("commit")
        branch = sidecar.get("branch")
        runner = sidecar.get("runner")
        os_name = sidecar.get("os")
        sequence = sidecar.get("sequence")
        if sequence is not None and (type(sequence) is not int or sequence < 0):
            warnings.append("metadata sequence must be a nonnegative integer; ignored")
            sequence = None
        timestamp = _parse_timestamp(sidecar.get("timestamp"))
        if sidecar.get("timestamp") is not None and timestamp is None:
            warnings.append(
                "metadata timestamp must be an ISO 8601 string with an explicit UTC offset "
                "(for example Z or +00:00); ignored"
            )
        extra = {}
        for key, value in sidecar.items():
            if key not in _KNOWN_KEYS:
                try:
                    extra[key] = str(value)
                except RecursionError:
                    warnings.append("nested metadata value omitted: too deeply nested")
        source = "sidecar" if timestamp is not None or sequence is not None else "path"
        if timestamp is None and sequence is None:
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
