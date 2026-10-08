"""Ask Kubernetes' own tracker what it knows about the tests that failed most.

    uv run python studies/kubernetes-ci/tracker.py

For each test in results.json that failed five times or more, searches
kubernetes/kubernetes for issues and pull requests that name the test, and
writes what comes back to tracker.json: number, title, state, when it was
opened, closed or merged, and whether the name is in the title, the body or
only a comment. That is an independent record of when a flake was reported and
when a fix landed, to hold flakemap's "quiet" and "new" against.

Uses GitHub's public search API. It works without a token at ten searches a
minute; GH_TOKEN or GITHUB_TOKEN, when set, is sent as a bearer token for the
higher limit and nothing else.
"""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HERE = Path(__file__).parent
REPOSITORY = "kubernetes/kubernetes"
SEARCH = "https://api.github.com/search/issues"
ENOUGH_FAILURES = 5


def search(query: str, token: str | None) -> list[dict[str, Any]]:
    url = f"{SEARCH}?{urllib.parse.urlencode({'q': query, 'per_page': '50'})}"
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "flakemap-study"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    for attempt in range(5):
        try:
            with urllib.request.urlopen(
                urllib.request.Request(url, headers=headers), timeout=60
            ) as response:
                items = json.loads(response.read())["items"]
                return list(items)
        except urllib.error.HTTPError as exc:
            if exc.code not in (403, 429) or attempt == 4:
                raise
            time.sleep(20.0 * (attempt + 1))  # the search API's rate limit is per minute
    return []


def record(item: dict[str, Any], test: str) -> dict[str, Any]:
    pull = item.get("pull_request")
    name = test.lower()
    where = (
        "title"
        if name in item["title"].lower()
        else "body"
        if name in (item.get("body") or "").lower()
        else "comment"
    )
    return {
        "number": item["number"],
        "names_test_in": where,
        "kind": "pull request" if pull else "issue",
        "title": item["title"],
        "state": item["state"],
        "opened": item["created_at"],
        "closed": item.get("closed_at"),
        "merged": (pull or {}).get("merged_at"),
        "labels": sorted(label["name"] for label in item.get("labels", [])),
        "url": item["html_url"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--results", type=Path, default=HERE / "results.json")
    parser.add_argument("--out", type=Path, default=HERE / "tracker.json")
    args = parser.parse_args()
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")

    results = json.loads(args.results.read_text())
    tests: dict[str, Any] = {}
    for job, summary in results["jobs"].items():
        for row in summary["tests"]:
            if row["failed_runs"] < ENOUGH_FAILURES:
                continue
            items = search(f'repo:{REPOSITORY} "{row["test"]}"', token)
            found = [record(item, row["test"]) for item in items]
            found.sort(key=lambda entry: entry["opened"])
            tests[f"{job}:{row['package']}:{row['test']}"] = found
            titles = sum(entry["names_test_in"] == "title" for entry in found)
            print(f"{row['test']}: {len(found)} mention it, {titles} in the title")
            time.sleep(2.5 if token else 7.0)
    out = {
        "repository": REPOSITORY,
        "searched": datetime.now(tz=timezone.utc).isoformat(timespec="seconds"),
        "query": 'repo:kubernetes/kubernetes "<test name>"',
        "tests": tests,
    }
    args.out.write_text(json.dumps(out, indent=1) + "\n")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
