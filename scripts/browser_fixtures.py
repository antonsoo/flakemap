#!/usr/bin/env python3
"""Render committed real-run histories plus explicitly synthetic boundary cases.

No test runner or network access is needed. Read scratch/browser/manifest.json
for fixture provenance and independently specified expected counts.
"""

from __future__ import annotations

import json
from pathlib import Path

from flakemap.loader import load_runs
from flakemap.report import render_html, to_json_dict
from flakemap.stats import analyze

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "scratch" / "browser"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    fixtures = [
        ("retry", "examples/retry_history", 1, 6),
        ("history", "examples/demo_project/runs", 222, 12),
        ("trx", "examples/trx_history", 12, 6),
        ("incomplete", "examples/incomplete_history", 3, 6),
    ]
    manifest = []
    for name, source, run_count, test_count in fixtures:
        runs = load_runs(ROOT / source)
        result = analyze(runs)
        payload = to_json_dict(result)
        assert len(runs) == run_count, (name, len(runs))
        assert len(result.tests) == test_count, (name, len(result.tests))
        (OUT / f"{name}.html").write_text(render_html(result, runs), encoding="utf-8")
        (OUT / f"{name}.json").write_text(
            json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8"
        )
        manifest.append({"name": name, "source": source, "runs": run_count, "tests": test_count})
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Rendered {len(fixtures)} report fixtures in {OUT}")


if __name__ == "__main__":
    main()
