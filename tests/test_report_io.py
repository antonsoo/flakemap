from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from flakemap.cli import main
from flakemap.loader import load_runs
from flakemap.parse import metadata


def report(tmp_path: Path) -> Path:
    source = tmp_path / "input.xml"
    source.write_text('<testsuite><testcase name="test"/></testsuite>')
    source.with_suffix(".meta.json").write_text('{"sequence":1}')
    return source


@pytest.mark.parametrize("alias", ["same", "hardlink", "symlink", "metadata"])
def test_html_output_cannot_replace_input_evidence(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], alias: str
) -> None:
    source = report(tmp_path)
    target = tmp_path / "report.html"
    if alias == "same":
        target = source
    elif alias == "hardlink":
        os.link(source, target)
    elif alias == "symlink":
        target.symlink_to(source)
    else:
        target = source.with_suffix(".meta.json")
    before = {p: p.read_bytes() for p in tmp_path.iterdir()}
    assert main([str(tmp_path), "--html", str(target), "--json"]) == 2
    assert "error writing HTML" in capsys.readouterr().err
    assert all(p.read_bytes() == contents for p, contents in before.items())


def test_failed_report_write_keeps_the_previous_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    report(tmp_path)
    target = tmp_path / "report.html"
    target.write_text("previous report")

    def fail(*args: object) -> None:
        raise OSError("simulated rename failure")

    monkeypatch.setattr(os, "replace", fail)
    assert main([str(tmp_path), "--json", "--html", str(target)]) == 2
    assert "simulated rename failure" in capsys.readouterr().err
    assert target.read_text() == "previous report"
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "input.meta.json",
        "input.xml",
        "report.html",
    ]


@pytest.mark.parametrize("pattern", ["", ",,", "../*.xml", "/tmp/*.xml"])
def test_invalid_scan_patterns_report_an_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], pattern: str
) -> None:
    report(tmp_path)
    assert main([str(tmp_path), "--json", "--pattern", pattern]) == 2
    assert "relative globs" in capsys.readouterr().err


@pytest.mark.parametrize(
    "raw",
    [
        '{"sequence":1,"sequence":2}',
        '{"run_id":"first","run_id":"second"}',
        '{"sequence":1,"extra":NaN}',
        '{"sequence":1,"extra":1e999}',
    ],
)
def test_ambiguous_metadata_cannot_silently_choose_a_run(tmp_path: Path, raw: str) -> None:
    source = report(tmp_path)
    source.with_suffix(".meta.json").write_text(raw)
    (run,) = load_runs(tmp_path)
    assert run.metadata.run_id == "input"
    assert run.metadata.sequence is None
    assert any("invalid metadata sidecar" in warning for warning in run.warnings)


def test_metadata_read_is_bounded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = report(tmp_path)
    source.with_suffix(".meta.json").write_text(json.dumps({"sequence": 1, "value": "x" * 100}))
    monkeypatch.setattr(metadata, "MAX_METADATA_BYTES", 50)
    (run,) = load_runs(tmp_path)
    assert any("byte limit" in warning for warning in run.warnings)


def test_utf32_metadata_is_not_misread_as_utf16(tmp_path: Path) -> None:
    source = report(tmp_path)
    source.with_suffix(".meta.json").write_bytes(
        '{"sequence":7,"run_id":"résultat"}'.encode("utf-32")
    )
    (run,) = load_runs(tmp_path)
    assert run.metadata.run_id == "résultat"
    assert run.metadata.sequence == 7
    assert not run.warnings


def test_deep_metadata_never_crashes_analysis(tmp_path: Path) -> None:
    source = report(tmp_path)
    source.with_suffix(".meta.json").write_text('{"extra":' + "[" * 5000 + "0" + "]" * 5000 + "}")
    (run,) = load_runs(tmp_path)
    assert any("metadata" in warning for warning in run.warnings)
