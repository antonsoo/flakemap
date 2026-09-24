#!/usr/bin/env python3
"""Generate the demo JUnit XML corpus committed under `examples/demo_project/runs/`.

What this actually does (no simulation of *results* -- only of CI metadata):

1. Walks a fake commit sequence of `NUM_COMMITS` commits on `main`.
2. For each commit, runs the real `pytest` suite in `tests/test_suite.py`
   against `test-suite/` once (most commits) or twice (every `RERUN_EVERY`th
   commit, modeling "CI reran the job") with a fresh `pytest-randomly` seed
   each time, so test order and the suite's own randomized assertions differ
   run to run exactly as they would in real CI.
3. A fraction of runs are tagged as having come from a `macos-latest` runner,
   which is given a small constant extra delay via
   `FLAKEMAP_DEMO_RUNNER_EXTRA_DELAY` (see `tests/test_suite.py`) to model a
   consistently slower runner class -- a real, common CI phenomenon. Every
   duration in the resulting XML is a real measured `pytest` duration; only
   that one offset is scripted.
4. Writes each run's `pytest --junitxml` output plus a flakemap sidecar
   `meta.json` (commit, branch, timestamp, runner, os, sequence) to
   `runs/run-XXXX/`.

Every failure/pass outcome in the resulting XML is genuinely produced by
running real Python test code with real timing and real `random` calls --
nothing here hand-edits an XML file or fabricates a result. Run this script
yourself to regenerate the corpus (it's deterministic given `--seed-base`):

    uv run python examples/demo_project/generate_demo_data.py

Takes about a minute for the default 190 commits / ~220 runs. The repo commits
the output directly (`runs/`, ~2.7 MB across ~440 small files, each well under
1 MB) so `flakemap examples/demo_project/runs` works right after cloning.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).parent
TEST_FILE = HERE / "tests" / "test_suite.py"
DEFAULT_OUT = HERE / "runs"

NUM_COMMITS = 190
RERUN_EVERY = 6
BASE_TIME = datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc)
COMMIT_SPACING = timedelta(minutes=23)
RUNNERS = ["ubuntu-latest", "ubuntu-latest", "ubuntu-latest", "macos-latest"]
OS_BY_RUNNER = {"ubuntu-latest": "linux", "macos-latest": "macos"}
RUNNER_EXTRA_DELAY = {"ubuntu-latest": "0", "macos-latest": "0.003"}


def _run_once(
    out_dir: Path,
    run_index: int,
    commit_seq: int,
    commit: str,
    seed: int,
    runner: str,
    when: datetime,
) -> None:
    run_dir = out_dir / f"run-{run_index:04d}"
    run_dir.mkdir(parents=True, exist_ok=True)
    report = run_dir / "report.xml"

    env = {
        "FLAKEMAP_DEMO_COMMIT_SEQ": str(commit_seq),
        "FLAKEMAP_DEMO_RUNNER_EXTRA_DELAY": RUNNER_EXTRA_DELAY[runner],
    }
    import os as _os

    full_env = {**_os.environ, **env}
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(TEST_FILE),
            "-p",
            "randomly",
            f"--randomly-seed={seed}",
            f"--junitxml={report}",
            "-q",
            "--no-header",
        ],
        env=full_env,
        cwd=HERE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,  # test failures are expected and are the point
    )

    meta = {
        "run_id": f"run-{run_index:04d}",
        "commit": commit,
        "branch": "main",
        "timestamp": when.isoformat(),
        "runner": runner,
        "os": OS_BY_RUNNER[runner],
        "sequence": run_index,
    }
    (run_dir / "meta.json").write_text(json.dumps(meta, indent=2))


def generate(out_dir: Path, num_commits: int, seed_base: int) -> int:
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    run_index = 0
    for commit_seq in range(num_commits):
        commit = f"{commit_seq:05x}{'a' * 7}"[:12]
        runner = RUNNERS[commit_seq % len(RUNNERS)]
        when = BASE_TIME + commit_seq * COMMIT_SPACING
        _run_once(
            out_dir,
            run_index,
            commit_seq,
            commit,
            seed_base + run_index,
            runner,
            when,
        )
        run_index += 1

        if commit_seq % RERUN_EVERY == 0:
            # A same-commit rerun: same commit, a little later, a different seed.
            _run_once(
                out_dir,
                run_index,
                commit_seq,
                commit,
                seed_base + run_index,
                runner,
                when + timedelta(minutes=4),
            )
            run_index += 1

        if (commit_seq + 1) % 20 == 0:
            print(f"  ... {commit_seq + 1}/{num_commits} commits, {run_index} runs so far")

    print(f"wrote {run_index} runs to {out_dir}")
    return run_index


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--num-commits", type=int, default=NUM_COMMITS)
    parser.add_argument("--seed-base", type=int, default=20260601)
    args = parser.parse_args()
    generate(args.out, args.num_commits, args.seed_base)


if __name__ == "__main__":
    main()
