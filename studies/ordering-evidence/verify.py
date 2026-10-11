"""Replay retained pytest artifacts under controlled metadata and folder permutations.

Use the Python interpreter containing the package under review. --check asserts
corrected behavior. --out retains generated JSON/HTML and browser fixtures.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from flakemap.loader import load_runs
from flakemap.report import render_html, to_json_dict
from flakemap.stats import analyze

ROOT = Path(__file__).resolve().parent


def replay(
    root: Path, *, ordered: bool, reversed_order: bool, interleaved: bool = False
) -> tuple[dict, dict, str]:
    root.mkdir()
    for i in range(40):
        position = (i % 20) * 2 + i // 20 if interleaved else 39 - i if reversed_order else i
        directory = root / f"run-{position:02}"
        directory.mkdir()
        shutil.copyfile(ROOT / "captures" / f"{i:02}.xml", directory / "report.xml")
        metadata = json.loads((ROOT / "captures" / f"{i:02}.meta.json").read_text())
        if ordered:
            metadata["sequence"] = 39 - i if reversed_order else i
        (directory / "meta.json").write_text(json.dumps(metadata))
    runs = load_runs(root)
    result = analyze(runs)
    payload = to_json_dict(result)
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "flakemap",
            ".",
            "--json",
            "--fail-on-new-flake",
            "--new-flake-window",
            "25",
        ],
        cwd=root,
        text=True,
        capture_output=True,
        timeout=20,
    )
    assert completed.returncode in (0, 1, 2), completed.stderr
    report = json.loads(completed.stdout)
    assert report == payload
    test = next(row for row in payload["tests"] if row["test"].endswith("test_pipeline"))
    measured = {
        "ordering": payload["summary"].get("ordering"),
        "counts": test["runs"],
        "classification": test["classification"],
        "flip_rate": test["flip_rate"],
        "change_point": test["change_point"],
        "activity": test["activity"],
        "duration": test["duration"],
        "last_status": test["last_status"],
        "new_flake_gate_exit": completed.returncode,
        "cofailure_groups": payload["summary"]["cofailure_groups"],
    }
    return measured, payload, render_html(result, runs)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    captures = json.loads((ROOT / "capture-manifest.json").read_text())
    assert len(captures) == 40
    for capture in captures:
        source = ROOT / "captures" / capture["report"]
        assert hashlib.sha256(source.read_bytes()).hexdigest() == capture["xml_sha256"]
        assert (
            hashlib.sha256(source.with_suffix(".meta.json").read_bytes()).hexdigest()
            == capture["metadata_sha256"]
        )
    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
    measurements = {}
    manifest = []
    with tempfile.TemporaryDirectory(prefix="flakemap-order-") as temporary:
        for name, ordered, reversed_order, interleaved in (
            ("passes-first", False, False, False),
            ("failures-first", False, True, False),
            ("alternating", False, False, True),
            ("ordered-regression", True, False, False),
            ("ordered-recovery", True, True, False),
        ):
            measured, payload, html = replay(
                Path(temporary) / name,
                ordered=ordered,
                reversed_order=reversed_order,
                interleaved=interleaved,
            )
            measurements[name] = measured
            if args.check:
                assert measured["counts"] == {
                    "total": 40,
                    "pass": 20,
                    "fail": 20,
                    "skip": 0,
                    "unknown": 0,
                }
                assert measured["cofailure_groups"] == 1
                if not ordered:
                    assert measured["ordering"]["available"] is False
                    assert (
                        measured["flip_rate"]
                        is measured["change_point"]
                        is measured["activity"]
                        is None
                    )
                    assert measured["duration"]["trend_seconds_per_run"] is None
                    assert measured["last_status"] is None and measured["new_flake_gate_exit"] == 2
                else:
                    assert measured["ordering"]["basis"] == "sequence"
                    assert measured["new_flake_gate_exit"] == (0 if reversed_order else 1)
            if args.out:
                (args.out / f"{name}.json").write_text(json.dumps(payload, indent=2) + "\n")
                (args.out / f"{name}.html").write_text(html)
                manifest.append({"name": name, "runs": 40, "tests": 2, "chronology": ordered})
    if args.out:
        (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(
        json.dumps(
            {
                "capture_sha256": {
                    p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in sorted((ROOT / "captures").glob("*"))
                },
                "measurements": measurements,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
