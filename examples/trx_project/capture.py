"""Run this MSTest project 12 times with `dotnet test --logger trx` and keep the
real TRX files, removing machine details only.

FLAKE_RUN tells each run which behavior to show (see CheckoutTests.cs). Outcomes,
messages, durations and each run's own start time are untouched; the machine
name, user name and local paths (in attributes and stack traces) are replaced.
No metadata sidecar is written: the runs are ordered by the start time each
TRX file records.

    uv run python examples/trx_project/capture.py
"""

import os
import shutil
import socket
import subprocess
from pathlib import Path
from xml.etree import ElementTree as ET

NS = "http://microsoft.com/schemas/VisualStudio/TeamTest/2010"
RUNS = 12
project = Path(__file__).resolve().parent
output = project.parent / "trx_history"
dotnet = shutil.which("dotnet") or str(Path.home() / ".dotnet" / "dotnet")
env = {**os.environ, "DOTNET_CLI_TELEMETRY_OPTOUT": "1", "DOTNET_NOLOGO": "1"}

subprocess.run([dotnet, "build", "-v", "q", "-nologo"], cwd=project, env=env, check=True)
results = project / "TestResults"
shutil.rmtree(results, ignore_errors=True)
for run in range(1, RUNS + 1):
    # A failing test makes `dotnet test` exit 1, which is expected here.
    subprocess.run(
        [dotnet, "test", "--no-build", "--logger", f"trx;LogFileName=run-{run:02d}.trx"],
        cwd=project,
        env={**env, "FLAKE_RUN": str(run)},
        stdout=subprocess.DEVNULL,
    )

ET.register_namespace("", NS)
q = f"{{{NS}}}"
shutil.rmtree(output, ignore_errors=True)
output.mkdir()
for run in range(1, RUNS + 1):
    tree = ET.parse(results / f"run-{run:02d}.trx")
    root = tree.getroot()
    outcomes = {r.get("testName"): r.get("outcome") for r in root.iter(f"{q}UnitTestResult")}
    # The behavior CheckoutTests.cs scripts for this run, checked before anything is kept.
    assert outcomes["CacheWarmsBeforeFirstRequest"] == ("Failed" if run in (2, 5, 9) else "Passed")
    assert outcomes["DiscountCodeIsCaseInsensitive"] == ("Failed" if run >= 7 else "Passed")
    assert outcomes["RefundReachesSandbox"] == "NotExecuted"
    assert len(outcomes) == 6

    root.set("name", f"flakemap-example run-{run:02d}")
    root.attrib.pop("runUser", None)
    for deployment in root.iter(f"{q}Deployment"):
        deployment.set("runDeploymentRoot", f"run-{run:02d}")
    for result in root.iter(f"{q}UnitTestResult"):
        result.set("computerName", "ci-runner")
    for el in root.iter():
        for attr in ("storage", "codeBase"):
            if attr in el.attrib:
                el.set(attr, Path(el.get(attr, "")).name)
    for trace in root.iter(f"{q}StackTrace"):
        trace.text = (trace.text or "").replace(f"{project}/", "")
    text = ET.tostring(root, encoding="unicode")
    assert str(Path.home()) not in text and socket.gethostname() not in text, (
        "a machine detail survived"
    )
    tree.write(output / f"run-{run:02d}.trx", encoding="utf-8", xml_declaration=True)

print(f"Captured {RUNS} real TRX runs into {output.relative_to(project.parent.parent)}")
