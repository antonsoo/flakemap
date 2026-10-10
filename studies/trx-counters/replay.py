"""Replay actual TRX reports and explicitly transformed copies through an installed CLI."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
NS = "{http://microsoft.com/schemas/VisualStudio/TeamTest/2010}"


def cases() -> list[tuple[str, str, bytes, bool]]:
    result = [
        (f"dotnet-{path.stem}", path.relative_to(ROOT).as_posix(), path.read_bytes(), True)
        for path in sorted((ROOT / "examples/trx_history").glob("*.trx"))
    ]
    flat_path = "examples/trx_history/run-02.trx"
    for name in (
        "removed-failed-result",
        "rewritten-failed-outcome",
        "removed-skipped-result",
        "invalid-total",
        "ambiguous-summary",
    ):
        root = ET.parse(ROOT / flat_path).getroot()
        group = root.find(f"{NS}Results")
        counts = root.find(f"{NS}ResultSummary/{NS}Counters")
        assert group is not None and counts is not None
        if name == "ambiguous-summary":
            ET.SubElement(root, f"{NS}ResultSummary")
        elif name == "invalid-total":
            counts.set("total", "-6")
        else:
            outcome = "NotExecuted" if name == "removed-skipped-result" else "Failed"
            record = next(record for record in group if record.get("outcome") == outcome)
            if name == "rewritten-failed-outcome":
                record.set("outcome", "Passed")
            else:
                group.remove(record)
        result.append((name, flat_path, ET.tostring(root, encoding="utf-8"), False))
    nested_path = "examples/trx_counters_project/captures/nested.trx"
    result.append(("logger-nested-original", nested_path, (ROOT / nested_path).read_bytes(), True))
    for name in (
        "nested-removed-failed-row",
        "nested-newer-count-convention",
        "nested-mixed-count-conventions",
    ):
        root = ET.parse(ROOT / nested_path).getroot()
        counts = root.find(f"{NS}ResultSummary/{NS}Counters")
        assert counts is not None
        if name == "nested-removed-failed-row":
            inner = root.find(f"{NS}Results/{NS}UnitTestResult/{NS}InnerResults")
            assert inner is not None
            inner.remove(next(row for row in inner if row.get("outcome") == "Failed"))
        elif name == "nested-newer-count-convention":
            counts.attrib.update(total="4", executed="3", passed="2", failed="1")
        else:
            counts.set("failed", "1")
        result.append(
            (
                name,
                nested_path,
                ET.tostring(root, encoding="utf-8"),
                name == "nested-newer-count-convention",
            )
        )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    results = []
    for name, source, raw, expected_complete in cases():
        folder = output / name
        folder.mkdir()
        (folder / "report.trx").write_bytes(raw)
        (folder / "meta.json").write_text('{"sequence": 1}\n', encoding="utf-8")
        command = ["-m", "flakemap", ".", "--json", "--fail-on-incomplete", "--html", "report.html"]
        run = subprocess.run(
            [sys.executable, *command], cwd=folder, capture_output=True, text=True, check=False
        )
        (folder / "analysis.json").write_text(run.stdout, encoding="utf-8")
        (folder / "stderr.txt").write_text(run.stderr, encoding="utf-8")
        payload = json.loads(run.stdout)
        results.append(
            {
                "case": name,
                "source": source,
                "source_sha256": hashlib.sha256((ROOT / source).read_bytes()).hexdigest(),
                "input_sha256": hashlib.sha256(raw).hexdigest(),
                "transformed": raw != (ROOT / source).read_bytes(),
                "command": ["python", *command],
                "exit": run.returncode,
                "expected_complete": expected_complete,
                "input_complete": payload["summary"]["input_complete"],
                "summary": payload["summary"],
                "warnings": payload["warnings"],
                "test_outcomes_sha256": hashlib.sha256(
                    json.dumps(payload["tests"], sort_keys=True).encode()
                ).hexdigest(),
            }
        )
        if args.check:
            assert payload["summary"]["input_complete"] == expected_complete, name
            assert run.returncode == (0 if expected_complete else 2), name
        print(f"{name}: complete={payload['summary']['input_complete']}, exit={run.returncode}")
    (output / "results.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
