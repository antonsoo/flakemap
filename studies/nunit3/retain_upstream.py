"""Retain portable, compressed native reports from the pinned upstream executions.

No result, case attribute, assertion or counter is rewritten. Compression keeps
the full reports reviewable without checking in multi-megabyte uncompressed XML.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import socket
import subprocess
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET

STUDY = Path(__file__).resolve().parent


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def retain(name: str, checkout: Path, report: Path, output: Path) -> dict[str, object]:
    raw = report.read_bytes()
    root = ET.fromstring(raw)
    case_attributes = [dict(case.attrib) for case in root.iter("test-case")]
    case_xml = [ET.tostring(case, encoding="unicode") for case in root.iter("test-case")]
    for element in root.iter():
        if element.tag == "command-line":
            element.text = (
                "<native runner command; host paths and transient process/port fields omitted>"
            )
        if element.tag == "environment":
            for key in ("cwd", "machine-name", "user", "user-domain"):
                element.attrib.pop(key, None)
        for key, value in list(element.attrib.items()):
            if str(checkout) in value:
                element.set(key, value.replace(str(checkout), "<upstream-checkout>"))
            if key == "value" and value == str(report.parent):
                element.set(key, "<runner-work-directory>")
        if element.tag == "property" and element.get("name") == "_PID":
            element.set("value", "<process-id>")
        if element.text:
            element.text = element.text.replace(str(checkout) + "/", "")
    assert case_attributes == [dict(case.attrib) for case in root.iter("test-case")]
    assert [text.replace(str(checkout) + "/", "") for text in case_xml] == [
        ET.tostring(case, encoding="unicode") for case in root.iter("test-case")
    ]
    retained = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    for forbidden in (b"/tmp/", str(Path.home()).encode()):
        assert forbidden not in retained, (name, forbidden)
    # A host token can occur inside an unrelated literal case name (for example,
    # Math.NET's native PolyomnialFitsAtSamplePoints); never rewrite identities.
    assert re.search(rb"\b" + re.escape(socket.gethostname().encode()) + rb"\b", retained) is None
    compressed = gzip.compress(retained, mtime=0)
    (output / f"{name}.xml.gz").write_bytes(compressed)
    outcomes = Counter(case["result"] for case in case_attributes)
    names = Counter(case["fullname"] for case in case_attributes)
    return {
        "name": name,
        "sourceRevision": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=checkout, text=True
        ).strip(),
        "sourceTrackedChanges": subprocess.check_output(
            ["git", "status", "--porcelain", "--untracked-files=no"], cwd=checkout, text=True
        ).strip(),
        "rawSha256": digest(raw),
        "rawBytes": len(raw),
        "retainedSha256": digest(retained),
        "retainedBytes": len(retained),
        "gzipSha256": digest(compressed),
        "gzipBytes": len(compressed),
        "nativeRoot": dict(root.attrib),
        "nativeOutcomes": dict(outcomes),
        "nativeCaseRecords": len(case_attributes),
        "uniqueFullnames": len(names),
        "duplicateFullnames": {key: count for key, count in names.items() if count > 1},
        "normalization": "Root/assembly/work-directory/command/environment process metadata and local stack prefixes only. Every case attribute, result, label, site, duration, assertion, counter and recorded timestamp remains native.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nodatime", type=Path, required=True)
    parser.add_argument("--nodatime-report", type=Path, required=True)
    parser.add_argument("--mathnet", type=Path, required=True)
    parser.add_argument("--mathnet-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    rows = [
        retain(
            "nodatime-3.2.0", args.nodatime.absolute(), args.nodatime_report.absolute(), args.output
        ),
        retain(
            "mathnet-5.0.0", args.mathnet.absolute(), args.mathnet_report.absolute(), args.output
        ),
    ]
    assert all(not row["sourceTrackedChanges"] for row in rows)
    (args.output / "manifest.json").write_text(json.dumps({"reports": rows}, indent=2) + "\n")
    print(
        json.dumps(
            {
                "reports": len(rows),
                "nativeRecords": sum(row["nativeCaseRecords"] for row in rows),
                "gzipBytes": sum(row["gzipBytes"] for row in rows),
            }
        )
    )


if __name__ == "__main__":
    main()
