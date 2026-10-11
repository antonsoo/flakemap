"""Synthetic histories composed from three retained actual Surefire executions."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from xml.etree import ElementTree as ET

HERE = Path(__file__).resolve().parent


def histories(output: Path) -> dict[str, Path]:
    early = {0, 2, 4}
    scenarios = {
        "continuing_retries": [
            "failed" if i in early else "pass" if i < 5 else "recovered" for i in range(20)
        ],
        "actually_quiet": ["recovered" if i in early else "pass" for i in range(20)],
        "new_retries": ["recovered" if i in {15, 17, 19} else "pass" for i in range(20)],
        "ambiguous_tail": ["failed" if i in early else "pass" for i in range(19)] + ["ambiguous"],
    }
    paths = {}
    for scenario, modes in scenarios.items():
        path = output / scenario
        paths[scenario] = path
        for sequence, mode in enumerate(modes):
            folder = path / f"run-{sequence:02}"
            folder.mkdir(parents=True, exist_ok=True)
            source = HERE / "fixtures" / f"{'pass' if mode == 'ambiguous' else mode}.xml"
            if mode == "ambiguous":
                # Deliberate duplicate-artifact perturbation, not a Surefire capture.
                root = ET.parse(source).getroot()
                testcase = root.find("testcase")
                assert testcase is not None
                root.append(copy.deepcopy(testcase))
                root.set("tests", "2")
                ET.ElementTree(root).write(
                    folder / "report.xml", encoding="utf-8", xml_declaration=True
                )
            else:
                (folder / "report.xml").write_bytes(source.read_bytes())
            (folder / "meta.json").write_text(
                json.dumps({"run_id": folder.name, "sequence": sequence}) + "\n"
            )
    return paths


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(json.dumps({key: str(path) for key, path in histories(args.output).items()}, indent=2))
