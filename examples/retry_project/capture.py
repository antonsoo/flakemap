"""Retain real Surefire output, removing machine-specific properties only.

Run `mvn test` in this directory first. Its nonzero exit is expected: two tests
never recover. Outcomes, attempt records, messages, and timings are untouched.
"""

import json
from pathlib import Path
from xml.etree import ElementTree as ET

project = Path(__file__).resolve().parent
report = project / "target/surefire-reports/TEST-example.RetryEvidenceTest.xml"
root = ET.parse(report).getroot()
assert len(root.findall("testcase")) == 6
assert len(root.findall(".//flakyFailure")) == 2
assert len(root.findall(".//flakyError")) == 1
assert len(root.findall(".//rerunFailure")) == 2
assert len(root.findall(".//rerunError")) == 2
for properties in root.findall("properties"):
    root.remove(properties)
output = project.parent / "retry_history/surefire-001"
output.mkdir(parents=True, exist_ok=True)
ET.indent(root)
ET.ElementTree(root).write(output / "report.xml", encoding="utf-8", xml_declaration=True)
(output / "meta.json").write_text(
    json.dumps({"run_id": "surefire-001", "sequence": 1}, indent=2) + "\n", encoding="utf-8"
)
print(f"Captured {len(root.findall('testcase'))} real testcases; removed environment properties.")
