"""Download a Kubernetes CI job's public build history as flakemap input.

    uv run python studies/kubernetes-ci/collect.py                 # the manifest's builds
    uv run python studies/kubernetes-ci/collect.py --rescan JOB... # list the jobs afresh

Kubernetes' CI (Prow) publishes every build of every job to a public bucket:
`started.json` (start time, commit), `finished.json` (result) and the JUnit
reports under `artifacts/`. This script reads them over plain HTTPS; it runs
no Kubernetes code and needs no account.

Each build lands in cache/<job>/<build>/ with the reports as published and a
`meta.json` sidecar in flakemap's convention (run_id, commit, branch,
timestamp), so `flakemap cache/<job>` reads the history directly.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HERE = Path(__file__).parent
BUCKET = "kubernetes-ci-logs"
API = f"https://storage.googleapis.com/storage/v1/b/{BUCKET}/o"
OBJECTS = f"https://storage.googleapis.com/{BUCKET}"
USER_AGENT = "flakemap-study (+https://github.com/antonsoo/flakemap)"
DEFAULT_JOBS = ("ci-kubernetes-integration-master", "ci-kubernetes-unit")


def fetch(url: str, attempts: int = 4) -> bytes | None:
    """The object's bytes, or None when the bucket does not have it."""
    for attempt in range(attempts):
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return bytes(response.read())
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            if attempt == attempts - 1:
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if attempt == attempts - 1:
                raise
        time.sleep(2.0 * (attempt + 1))
    return None


def listing(prefix: str, *, directories: bool) -> list[dict[str, Any]]:
    """Objects under a prefix, or its immediate sub-prefixes."""
    found: list[dict[str, Any]] = []
    token = ""
    while True:
        query = {"prefix": prefix, "maxResults": "1000"}
        if directories:
            query |= {"delimiter": "/", "fields": "prefixes,nextPageToken"}
        else:
            query |= {"delimiter": "/", "fields": "items(name,size,md5Hash),nextPageToken"}
        if token:
            query["pageToken"] = token
        body = fetch(f"{API}?{urllib.parse.urlencode(query)}")
        page = json.loads(body or b"{}")
        if directories:
            found += [{"name": name} for name in page.get("prefixes", [])]
        else:
            found += page.get("items", [])
        token = page.get("nextPageToken", "")
        if not token:
            return found


def scan_build(job: str, build: str) -> dict[str, Any]:
    """What one build published: its metadata and the JUnit reports beside it."""
    base = f"logs/{job}/{build}/"
    started = json.loads(fetch(f"{OBJECTS}/{base}started.json") or b"null")
    finished = json.loads(fetch(f"{OBJECTS}/{base}finished.json") or b"null")
    reports = [
        {"name": item["name"].rsplit("/", 1)[1], "size": int(item["size"]), "md5": item["md5Hash"]}
        for item in listing(base + "artifacts/", directories=False)
        if item["name"].rsplit("/", 1)[1].startswith("junit") and item["name"].endswith(".xml")
    ]
    row: dict[str, Any] = {"build": build, "reports": sorted(reports, key=lambda r: r["name"])}
    if isinstance(started, dict):
        row["started"] = started.get("timestamp")
        row["commit"] = started.get("repo-commit")
    if isinstance(finished, dict):
        row["finished"] = finished.get("timestamp")
        row["result"] = finished.get("result")
    return row


def download_build(job: str, row: dict[str, Any], cache: Path) -> int:
    """Fetch one build's reports and write its sidecar. Returns bytes downloaded."""
    target = cache / job / row["build"]
    target.mkdir(parents=True, exist_ok=True)
    fetched = 0
    for report in row["reports"]:
        path = target / report["name"]
        if path.exists() and path.stat().st_size == report["size"]:
            continue
        body = fetch(f"{OBJECTS}/logs/{job}/{row['build']}/artifacts/{report['name']}")
        if body is None:
            continue
        path.write_bytes(body)
        fetched += len(body)
    meta: dict[str, Any] = {"run_id": row["build"], "branch": "master", "job": job}
    if row.get("commit"):
        meta["commit"] = row["commit"]
    if row.get("started"):
        moment = datetime.fromtimestamp(row["started"], tz=timezone.utc)
        meta["timestamp"] = moment.isoformat().replace("+00:00", "Z")
    if row.get("result"):
        meta["result"] = row["result"]
    (target / "meta.json").write_text(json.dumps(meta, indent=1) + "\n")
    return fetched


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--manifest", type=Path, default=HERE / "manifest.json")
    parser.add_argument("--cache", type=Path, default=HERE / "cache")
    parser.add_argument("--workers", type=int, default=24)
    parser.add_argument(
        "--rescan",
        nargs="*",
        metavar="JOB",
        help="list these jobs' builds as the bucket has them now and rewrite the manifest",
    )
    args = parser.parse_args()

    if args.rescan is not None:
        jobs: dict[str, list[dict[str, Any]]] = {}
        for job in args.rescan or DEFAULT_JOBS:
            builds = sorted(
                (
                    row["name"].rstrip("/").rsplit("/", 1)[1]
                    for row in listing(f"logs/{job}/", directories=True)
                ),
                key=int,
            )
            with ThreadPoolExecutor(args.workers) as pool:
                rows = list(pool.map(lambda build, job=job: scan_build(job, build), builds))
            jobs[job] = rows
            print(f"{job}: {len(rows)} builds", file=sys.stderr)
        manifest = {
            "source": f"https://storage.googleapis.com/{BUCKET}/logs/<job>/<build>/",
            "listed": datetime.now(tz=timezone.utc).isoformat(timespec="seconds"),
            "jobs": jobs,
        }
        args.manifest.write_text(json.dumps(manifest, separators=(",", ":")) + "\n")
    else:
        manifest = json.loads(args.manifest.read_text())

    for job, rows in manifest["jobs"].items():
        with ThreadPoolExecutor(args.workers) as pool:
            sizes = list(pool.map(lambda row, job=job: download_build(job, row, args.cache), rows))
        print(f"{job}: {len(rows)} builds, {sum(sizes) / 1e6:.1f} MB fetched", file=sys.stderr)


if __name__ == "__main__":
    main()
