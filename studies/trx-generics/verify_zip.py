"""Replay actual downloaded native TRX archives with an installed CLI."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--downloads", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--expected-json", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    expected = json.loads(args.expected_json.read_text())
    source = ROOT / "studies/trx-generics/native-capture/history"
    names = {path.name for path in source.glob("*.trx")}
    assert len(names) == 12
    records = []
    env = {**os.environ, "NO_COLOR": "1"}
    env.pop("PYTHONPATH", None)
    for archive in sorted(args.downloads.glob("*generic-inputs.zip")):
        with tempfile.TemporaryDirectory() as temporary, ZipFile(archive) as bundle:
            assert set(bundle.namelist()) == names
            directory = Path(temporary)
            for name in names:
                data = bundle.read(name)
                assert data == (source / name).read_bytes()
                (directory / name).write_bytes(data)
            run = subprocess.run(
                [
                    str(args.python.absolute()),
                    "-m",
                    "flakemap",
                    str(directory),
                    "--json",
                    "--fail-on-incomplete",
                ],
                cwd=directory,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            assert run.returncode == 0, run.stderr
            assert json.loads(run.stdout) == expected
            records.append(
                {
                    "file": archive.name,
                    "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
                    "nativeReportsByteIdentical": 12,
                    "cliExit": run.returncode,
                    "completeAnalysisEqualsGallery": True,
                }
            )
    assert records
    args.out.write_text(
        json.dumps(
            {
                "scope": "Actual offline browser native-input downloads, original TRX byte agreement and installed CLI reproduction of complete gallery JSON.",
                "records": records,
            },
            indent=2,
        )
        + "\n"
    )
    print(json.dumps({"archives": len(records), "nativeReportsPerArchive": 12}))


if __name__ == "__main__":
    main()
