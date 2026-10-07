"""Capture twelve real pytest/JUnit runs against a controlled loopback service.

uv run python examples/cofailure_project/capture.py [DESTINATION]
The service returns 503 in runs 4, 5 and 10. An unrelated math assertion fails in
run 7. The optional endpoint check is skipped in run 4 and deselected in run 10.
These are planted failures, not production reliability data. XML is not rewritten.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
import threading
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUTAGES = {4, 5, 10}


def capture(destination: Path) -> None:
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("Choose a new or empty capture directory")
    destination.mkdir(parents=True, exist_ok=True)
    state = {"run": 0}
    requests: list[dict[str, object]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            code = 503 if state["run"] in OUTAGES else 200
            bodies = {
                "/inventory": {"quantity": 3},
                "/shipping": {"days": 2},
                "/pricing": {"cents": 1200},
                "/optional": {"enabled": True},
            }
            assert self.path in bodies
            body = json.dumps(
                bodies[self.path] if code == 200 else {"error": "controlled outage"}
            ).encode()
            requests.append({"run": state["run"], "path": self.path, "status": code})
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, _format: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    manifest: dict[str, object] = {
        "description": "Controlled pytest failures against a real loopback HTTP service; not production data",
        "python": platform.python_version(),
        "platform": platform.system(),
        "test_source_sha256": hashlib.sha256(
            (ROOT / "tests/test_service.py").read_bytes()
        ).hexdigest(),
        "outage_runs": sorted(OUTAGES),
        "independent_failure_run": 7,
        "runs": [],
    }
    captured = []
    try:
        for sequence in range(1, 13):
            state["run"] = sequence
            directory = destination / f"run-{sequence:02d}"
            directory.mkdir()
            report = directory / "report.xml"
            started = datetime.now(timezone.utc).isoformat()
            args = [
                sys.executable,
                "-m",
                "pytest",
                "tests/test_service.py",
                "-q",
                "-p",
                "no:cacheprovider",
                f"--rootdir={ROOT}",
                f"--junitxml={report.resolve()}",
            ]
            if sequence == 10:
                args += ["--deselect", "tests/test_service.py::test_optional_endpoint"]
            process = subprocess.run(
                args,
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=30,
                env={
                    **os.environ,
                    "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
                    "CAPTURE_RUN": str(sequence),
                    "CAPTURE_SERVICE_URL": f"http://127.0.0.1:{server.server_port}",
                },
            )
            assert process.returncode == (1 if sequence in OUTAGES | {7} else 0), (
                process.stdout + process.stderr
            )
            cases = {
                case.attrib["name"]: (
                    "fail"
                    if case.find("failure") is not None
                    else "error"
                    if case.find("error") is not None
                    else "skip"
                    if case.find("skipped") is not None
                    else "pass"
                )
                for case in ET.parse(report).iter("testcase")
            }
            for name in ("inventory", "shipping", "pricing"):
                assert cases[f"test_{name}_endpoint"] == ("fail" if sequence in OUTAGES else "pass")
            assert cases["test_independent_math"] == ("fail" if sequence == 7 else "pass")
            assert cases["test_healthy_control"] == "pass"
            if sequence == 10:
                assert "test_optional_endpoint" not in cases
            else:
                assert cases["test_optional_endpoint"] == (
                    "skip" if sequence == 4 else "fail" if sequence in OUTAGES else "pass"
                )
            captured.append(
                {"run_id": directory.name, "exit_code": process.returncode, "outcomes": cases}
            )
            (directory / "meta.json").write_text(
                json.dumps(
                    {
                        "run_id": directory.name,
                        "sequence": sequence,
                        "timestamp": started,
                        "runner": "controlled-loopback-capture",
                        "os": platform.system(),
                    },
                    indent=2,
                )
                + "\n"
            )
            print(f"{directory.name}: {cases}", flush=True)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    assert len(requests) == 46
    manifest["runs"] = captured
    manifest["requests"] = requests
    (destination / "capture.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    capture(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT.parent / "cofailure_history")
