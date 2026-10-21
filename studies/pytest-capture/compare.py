"""Compare complete replay analyses, excluding only recorded clocks/durations.

Usage: python compare.py REFERENCE_JSON REPLAY_JSON
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

VOLATILE = {"timestamp_range", "timestamp", "first_seen", "last_seen", "reported_duration_seconds"}


def normalized(value: object) -> object:
    if isinstance(value, dict):
        return {key: normalized(item) for key, item in value.items() if key not in VOLATILE}
    if isinstance(value, list):
        return [normalized(item) for item in value]
    return value


reference, replay = (json.loads(Path(name).read_text()) for name in sys.argv[1:3])
a, b = normalized(reference), normalized(replay)
assert a == b, "Complete analysis objects differ beyond the documented clocks/durations"
print(
    json.dumps(
        {
            "completeAnalysisEqual": True,
            "excludedRecordedFields": sorted(VOLATILE),
            "normalizedSha256": hashlib.sha256(
                json.dumps(a, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
        },
        indent=2,
    )
)
