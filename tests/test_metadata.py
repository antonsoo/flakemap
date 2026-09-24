import json
from pathlib import Path

from flakemap.parse.metadata import resolve_metadata


def test_file_level_sidecar_wins(tmp_path: Path) -> None:
    run_dir = tmp_path / "flat"
    run_dir.mkdir()
    report = run_dir / "run-001.xml"
    report.write_text("<testsuites/>")
    (run_dir / "run-001.meta.json").write_text(
        json.dumps(
            {
                "run_id": "custom-id",
                "commit": "deadbeef",
                "branch": "main",
                "timestamp": "2026-01-02T03:04:05Z",
                "runner": "ubuntu-latest",
                "os": "linux",
                "sequence": 7,
                "extra_field": "kept",
            }
        )
    )
    md = resolve_metadata(report, tmp_path)
    assert md.run_id == "custom-id"
    assert md.commit == "deadbeef"
    assert md.branch == "main"
    assert md.runner == "ubuntu-latest"
    assert md.os == "linux"
    assert md.sequence == 7
    assert md.source == "sidecar"
    assert md.extra["extra_field"] == "kept"
    assert md.timestamp is not None
    assert md.timestamp.year == 2026


def test_directory_per_run_layout_shared_sidecar(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-042"
    run_dir.mkdir()
    report = run_dir / "results.xml"
    report.write_text("<testsuites/>")
    (run_dir / "meta.json").write_text(json.dumps({"commit": "abc123", "sequence": 42}))
    md = resolve_metadata(report, tmp_path)
    assert md.run_id == "run-042"
    assert md.commit == "abc123"
    assert md.sequence == 42


def test_mtime_fallback_when_no_sidecar(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-1"
    run_dir.mkdir()
    report = run_dir / "results.xml"
    report.write_text("<testsuites/>")
    md = resolve_metadata(report, tmp_path)
    assert md.run_id == "run-1"
    assert md.commit is None
    assert md.timestamp is not None
    assert md.source == "mtime"
