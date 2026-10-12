"""Prepare retained native captures, explicit synthetic probes and existing controls."""

import json
import shutil
import sys
from pathlib import Path
from xml.etree.ElementTree import Element, ElementTree, SubElement

study = Path(__file__).resolve().parent
root = study.parents[1]
out = Path(sys.argv[1]).resolve()
out.mkdir(parents=True, exist_ok=False)
shutil.copytree(study / "capture/history", out / "pytest")
shutil.copytree(study / "capture/history", out / "warning")
(out / "warning/![warning](warning.png).xml").write_text("<testsuite>")
(out / "nested-failures").mkdir()
for index in range(16):
    suite = Element("testsuite", name="synthetic Go-style package output")
    case = SubElement(suite, "testcase", classname="example", name="package")
    if index >= 8:
        marker = SubElement(case, "failure", message="Failed")
        marker.text = "\n".join(
            [
                "--- FAIL: TestLiteral/![nested](nested.png) (0.00s)",
                "--- FAIL: TestLiteral/[source](reference) (0.00s)",
                "--- FAIL: TestLiteral/**wildcard** (0.00s)",
            ]
        )
    ElementTree(suite).write(
        out / f"nested-failures/{index:02}.xml", encoding="utf-8", xml_declaration=True
    )
    (out / f"nested-failures/{index:02}.meta.json").write_text(
        json.dumps({"sequence": index, "run_id": f"run-{index:02}"}) + "\n"
    )
for name in ["retry", "cofailure", "googletest"]:
    shutil.copytree(root / f"examples/{name}_history", out / name)
print(
    json.dumps(
        {
            "workflows": sorted(p.name for p in out.iterdir()),
            "scope": "pytest XML unchanged; warning and nested-failure variants synthetic; three existing captured controls",
        }
    )
)
