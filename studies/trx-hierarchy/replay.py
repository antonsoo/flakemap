"""Run actual CLI gates on retained native VSTest hierarchy controls."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

HERE = Path(__file__).resolve().parent
NS = "{http://microsoft.com/schemas/VisualStudio/TeamTest/2010}"
EXPECTED = {
    "passed-parent-failed-row": ("unknown", False, 3),
    "skipped-parent-failed-row": ("unknown", False, 3),
    "failed-parent-failed-row": ("fail", True, 3),
    "failed-parent-passing-rows": ("fail", True, 3),
    "passed-parent-passing-rows": ("pass", True, 3),
    "passed-parent-skipped-row": ("pass", True, 3),
    # SDK 17.11 writes the grandchild events as additional top-level results,
    # rather than the three-level XML tree those event relationships suggest.
    "grandchild-events-top-level": ("pass", True, 5),
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    rows = []
    for name, (expected_status, expected_complete, expected_tests) in EXPECTED.items():
        folder = output / name
        folder.mkdir()
        content = (HERE / "fixtures" / f"{name}.trx").read_bytes()
        (folder / "report.trx").write_bytes(content)
        root = ET.fromstring(content)
        counters = root.find(f"{NS}ResultSummary/{NS}Counters")
        summary = root.find(f"{NS}ResultSummary")
        assert counters is not None and summary is not None
        command = [
            sys.executable,
            "-m",
            "flakemap",
            str(folder),
            "--json",
            "--fail-on-incomplete",
            "--html",
            str(folder / "report.html"),
        ]
        run = subprocess.run(command, capture_output=True, text=True)
        analysis = json.loads(run.stdout)
        (folder / "analysis.json").write_text(run.stdout)
        (folder / "stderr.txt").write_text(run.stderr)
        data = next(test for test in analysis["tests"] if test["test"] == "Capture.Example.Data")
        actual_status = "unknown" if data["runs"]["unknown"] else data["last_status"]
        matches = (
            actual_status == expected_status
            and analysis["summary"]["input_complete"] == expected_complete
            and run.returncode == (0 if expected_complete else 2)
            and analysis["summary"]["total_tests"] == expected_tests
        )
        rows.append(
            {
                "case": name,
                "sourceSha256": hashlib.sha256(content).hexdigest(),
                "nativeSummary": summary.get("outcome"),
                "nativeCounters": counters.attrib,
                "exitCode": run.returncode,
                "matches": matches,
                "expected": {
                    "parent": expected_status,
                    "complete": expected_complete,
                    "tests": expected_tests,
                },
                "analysis": analysis,
            }
        )
    code = "import hashlib, pathlib, flakemap.parse.trx; print(hashlib.sha256(pathlib.Path(flakemap.parse.trx.__file__).read_bytes()).hexdigest())"
    implementation = subprocess.check_output([sys.executable, "-c", code], text=True).strip()
    inventory_code = """
import hashlib, json
from pathlib import Path
import flakemap
root = Path(flakemap.__file__).parent
print(json.dumps({str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
    for p in sorted(root.rglob('*')) if p.is_file() and (p.suffix == '.py' or p.name == 'py.typed')}))
"""
    inventory = json.loads(
        subprocess.check_output([sys.executable, "-c", inventory_code], text=True)
    )
    result = {
        "scope": __doc__,
        "implementationTrxSha256": implementation,
        "implementationFiles": inventory,
        "cases": len(rows),
        "mismatches": sum(not row["matches"] for row in rows),
        "observations": rows,
    }
    (output / "results.json").write_text(json.dumps(result, indent=2) + "\n")
    print({key: result[key] for key in ("cases", "mismatches", "implementationTrxSha256")})
    if args.check and result["mismatches"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
