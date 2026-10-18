"""Compare every built report-site file and the canonical root with public bytes."""

from __future__ import annotations

import argparse
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

BASE = "https://antonsoo.github.io/flakemap/"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--deployment", required=True)
    args = parser.parse_args()
    paths = sorted(p.relative_to(args.site).as_posix() for p in args.site.rglob("*") if p.is_file())

    def check(relative: str) -> dict[str, object]:
        expected = hashlib.sha256((args.site / (relative or "index.html")).read_bytes()).hexdigest()
        with urlopen(BASE + relative, timeout=30) as response:
            body, status = response.read(), response.status
        actual = hashlib.sha256(body).hexdigest()
        return {
            "path": relative or "(canonical root)",
            "status": status,
            "bytes": len(body),
            "sha256": actual,
            "expectedSha256": expected,
            "matches": actual == expected,
        }

    with ThreadPoolExecutor(max_workers=4) as pool:
        checks = list(pool.map(check, ["", *paths]))
    receipt = {
        "checkedAtUtc": datetime.now(timezone.utc).isoformat(),
        "baseUrl": BASE,
        "sourceRevision": args.source,
        "deploymentRevision": args.deployment,
        "scope": "Every fresh built file and the canonical root, using direct public requests without query cache busters.",
        "checks": checks,
    }
    args.output.write_text(json.dumps(receipt, indent=2) + "\n")
    assert all(row["matches"] for row in checks), [
        row["path"] for row in checks if not row["matches"]
    ]
    print(f"{len(paths)} built files plus the canonical root match")


if __name__ == "__main__":
    main()
