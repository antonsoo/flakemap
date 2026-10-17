"""Execute controlled native NUnit fixtures through VSTest and retain native TRX.

No production incidence claim. Class names, outcomes, counters and native run
start times are untouched. Local paths and machine names are normalized.
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
NS = "{http://microsoft.com/schemas/VisualStudio/TeamTest/2010}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--dotnet", default="dotnet")
    args = parser.parse_args()
    output = args.output.absolute()
    output.mkdir(parents=True, exist_ok=False)
    project = ROOT / "studies/trx-generics/native"
    env = {**os.environ, "DOTNET_CLI_TELEMETRY_OPTOUT": "1", "DOTNET_NOLOGO": "1"}
    build = subprocess.run(
        [args.dotnet, "build", str(project), "-v", "q"],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    records = []
    ET.register_namespace("", NS[1:-1])
    scenarios = [
        (f"run-{index:02d}", "Double" if index % 2 == 0 else "String") for index in range(1, 13)
    ] + [("combined", None)]
    for name, selection in scenarios:
        folder = output / ("history" if selection else "combined")
        folder.mkdir(exist_ok=True)
        command = [
            args.dotnet,
            "test",
            str(project),
            "--no-build",
            "--logger",
            f"trx;LogFileName={name}.trx",
            "--results-directory",
            str(folder),
        ]
        if selection:
            command += [
                "--filter",
                f"FullyQualifiedName~NativePairs.Pair&FullyQualifiedName~{selection}",
            ]
        run = subprocess.run(command, env=env, capture_output=True, text=True, check=False)
        assert run.returncode == (1 if selection != "String" else 0), run.stdout + run.stderr
        report = folder / f"{name}.trx"
        raw = report.read_bytes()
        root = ET.fromstring(raw)
        definitions = {
            unit.get("id"): unit.find(NS + "TestMethod").get("className")
            for unit in root.findall(NS + "TestDefinitions/" + NS + "UnitTest")
        }
        observed = [
            {
                "className": definitions[row.get("testId")],
                "testName": row.get("testName"),
                "outcome": row.get("outcome"),
            }
            for row in root.findall(NS + "Results/" + NS + "UnitTestResult")
        ]
        expected = (
            [("NativePairs.Pair<Int32,String>", "Passed")]
            if selection == "String"
            else [("NativePairs.Pair<Int32,Double>", "Failed")]
            if selection == "Double"
            else [
                ("NativePairs.Pair<Int32,String>", "Passed"),
                ("NativePairs.Pair<Int32,Double>", "Failed"),
                ("NativePairs.Single<Int32>", "Passed"),
                ("NativePairs.Ordinary", "Passed"),
            ]
        )
        assert sorted((row["className"], row["outcome"]) for row in observed) == sorted(expected), (
            observed
        )
        root.set("name", f"Controlled NUnit generic fixture identity {name}")
        root.attrib.pop("runUser", None)
        for node in root.iter():
            node.attrib.pop("computerName", None)
            node.attrib.pop("runDeploymentRoot", None)
            for attribute in ["storage", "codeBase"]:
                if attribute in node.attrib:
                    node.set(attribute, Path(node.attrib[attribute]).name)
            if node.text:
                node.text = node.text.replace(str(project) + "/", "")
        retained = ET.tostring(root, encoding="utf-8", xml_declaration=True)
        assert (
            str(Path.home()).encode() not in retained
            and socket.gethostname().encode() not in retained
        )
        report.write_bytes(retained)
        for stream, data in [("stdout", run.stdout), ("stderr", run.stderr)]:
            text = data.replace(str(output), "<capture-output>").replace(
                str(project), "<native-project>"
            )
            (folder / f"{name}-{stream}.txt").write_text(text)
        records.append(
            {
                "scenario": name,
                "selection": selection,
                "processExit": run.returncode,
                "report": report.relative_to(output).as_posix(),
                "rawSha256": hashlib.sha256(raw).hexdigest(),
                "retainedSha256": hashlib.sha256(retained).hexdigest(),
                "nativeOutcomes": observed,
            }
        )
    result = {
        "sdk": subprocess.check_output([args.dotnet, "--version"], text=True).strip(),
        "packages": {
            "Microsoft.NET.Test.Sdk": "17.11.1",
            "NUnit": "3.14.0",
            "NUnit3TestAdapter": "4.6.0",
        },
        "scope": "Actual compiled controlled NUnit test execution and native TRX logger, not production reliability evidence.",
        "normalization": "Only machine/user/deployment details and local code/stack paths. Native class names, outcomes, counters and recorded run times unchanged.",
        "projectFiles": [
            {"file": p.name, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
            for p in sorted(project.glob("*"))
            if p.is_file()
        ],
        "reports": records,
    }
    (output / "capture.json").write_text(json.dumps(result, indent=2) + "\n")
    (output / "build.txt").write_text(
        build.stdout.replace(str(project), "<native-project>") + build.stderr
    )
    print(
        json.dumps(
            {
                "reports": len(records),
                "nativeExecutions": sum(len(r["nativeOutcomes"]) for r in records),
            }
        )
    )


if __name__ == "__main__":
    main()
