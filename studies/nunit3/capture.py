"""Execute pinned NUnit tests and retain native NUnit 3 XML, not converted TRX.

Only host/user paths and machine/command metadata are normalized. Case identities,
results, labels, sites, durations, assertions, counters and recorded times stay native.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import subprocess
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
SCENARIOS = [
    ("all", None, 1),
    ("pass-filter", "FullyQualifiedName=NativeNUnit.Outcomes.Pass", 0),
    ("pairs-filter", "FullyQualifiedName~NativeNUnit.Pair", 1),
    ("warning-filter", "FullyQualifiedName=NativeNUnit.Outcomes.Warning", 0),
    ("inconclusive-filter", "FullyQualifiedName=NativeNUnit.Outcomes.Inconclusive", 0),
    ("setup-filter", "FullyQualifiedName~NativeNUnit.BrokenSetup", 1),
    ("teardown-filter", "FullyQualifiedName~NativeNUnit.BrokenTeardown", 0),
    ("invalid-filter", "FullyQualifiedName~NativeNUnit.InvalidSignature", 1),
    ("retry-filter", "FullyQualifiedName=NativeNUnit.Outcomes.RetryRecovered", 0),
]


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dotnet", default="dotnet")
    parser.add_argument("--project", type=Path, default=ROOT / "studies/nunit3/native")
    args = parser.parse_args()
    project = args.project.absolute()
    output = args.output.absolute()
    output.mkdir(parents=True, exist_ok=False)
    env = {**os.environ, "DOTNET_CLI_TELEMETRY_OPTOUT": "1", "DOTNET_NOLOGO": "1"}
    build = subprocess.run(
        [args.dotnet, "build", str(project), "-p:RestoreLockedMode=true", "-v", "q"],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    records = []
    for name, selection, expected_exit in SCENARIOS:
        folder = output / name
        folder.mkdir()
        command = [args.dotnet, "test", str(project), "--no-build"]
        if selection:
            command += ["--filter", selection]
        command += ["--", f"NUnit.TestOutputXml={folder}"]
        run = subprocess.run(command, env=env, capture_output=True, text=True, check=False)
        # The pinned adapter's process exit is retained independently of XML.
        assert run.returncode == expected_exit, (name, run.returncode, run.stdout, run.stderr)
        report = folder / "Capture.xml"
        raw = report.read_bytes()
        root = ET.fromstring(raw)
        native_cases = [dict(case.attrib) for case in root.iter("test-case")]
        before = [ET.tostring(case, encoding="unicode") for case in root.iter("test-case")]
        # Path attributes live on Assembly/root/settings, not case identities.
        for element in root.iter():
            if element.tag == "command-line":
                element.text = (
                    "<native NUnit adapter command; host paths and transient ports omitted>"
                )
            if element.tag == "environment":
                for key in ("cwd", "machine-name", "user", "user-domain"):
                    element.attrib.pop(key, None)
            for key, value in list(element.attrib.items()):
                if str(project) in value:
                    element.set(key, value.replace(str(project), "<native-project>"))
            if element.tag == "property" and element.get("name") == "_PID":
                element.set("value", "<process-id>")
            if element.text:
                element.text = element.text.replace(str(project) + "/", "").replace(
                    str(ROOT) + "/", ""
                )
        # All case attributes are untouched, including exact native clocks.
        assert native_cases == [dict(case.attrib) for case in root.iter("test-case")]
        retained = ET.tostring(root, encoding="utf-8", xml_declaration=True)
        assert str(Path.home()).encode() not in retained
        assert socket.gethostname().encode() not in retained
        report.write_bytes(retained)
        native_after = [ET.tostring(case, encoding="unicode") for case in root.iter("test-case")]
        # Case text changes only by removing the local stack trace prefix.
        assert [
            text.replace(str(project) + "/", "").replace(str(ROOT) + "/", "") for text in before
        ] == native_after
        for stream, data in (("stdout", run.stdout), ("stderr", run.stderr)):
            portable = (
                data.replace(str(project), "<native-project>")
                .replace(str(ROOT), "<source-root>")
                .replace(str(output), "<capture-output>")
            )
            (folder / f"{stream}.txt").write_text(portable)
        records.append(
            {
                "scenario": name,
                "selection": selection,
                "processExit": run.returncode,
                "report": report.relative_to(output).as_posix(),
                "rawSha256": digest(raw),
                "retainedSha256": digest(retained),
                "bytes": len(retained),
                "nativeRoot": dict(root.attrib),
                "nativeCases": native_cases,
            }
        )
    manifest = {
        "sdk": subprocess.check_output([args.dotnet, "--version"], text=True).strip(),
        "packages": {
            key: value["resolved"]
            for key, value in json.loads((project / "packages.lock.json").read_text())[
                "dependencies"
            ]["net8.0"].items()
            if value["type"] == "Direct"
        },
        "scope": "Actual compiled controlled executions, native adapter TestOutputXml; not production reliability evidence.",
        "normalization": "Host/user/command metadata and local stack paths only. Every case attribute, result, label, site, duration, assertion, counter and native recorded time stays unchanged.",
        "projectFiles": [
            {"file": p.name, "sha256": digest(p.read_bytes())}
            for p in sorted(project.iterdir())
            if p.is_file()
        ],
        "reports": records,
    }
    (output / "capture.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (output / "build.txt").write_text(
        (build.stdout + build.stderr)
        .replace(str(project), "<native-project>")
        .replace(str(ROOT), "<source-root>")
    )
    print(
        json.dumps(
            {"reports": len(records), "nativeCases": sum(len(r["nativeCases"]) for r in records)}
        )
    )


if __name__ == "__main__":
    main()
