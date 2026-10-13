# Local runner clocks must not become UTC instants

A missing timezone could reverse Flakemap's conclusion about when failures
happened. The metadata parser accepted `2026-10-13T09:00:00` and silently attached
UTC. In the controlled history here, early failures came from a +09:00 runner
and the later passes came from a UTC runner. Dropping the offsets moved the old
failures after the passes: **quiet became new**, the new-flake gate changed from
exit 0 to exit 1, and the completeness gate still passed without a warning.

```text
Known UTC history:  F P F P F P ... P  -> 25 passes after last failure -> quiet
Offsets removed:    P ... P F P F P F  -> invented UTC order           -> new
Corrected reader:   retained outcomes -> chronology unavailable       -> gate 2
                  + explicit sequence or report times                -> quiet
```

These are **synthetic** JUnit/TRX reports and metadata, not production artifacts
or a prevalence estimate. The generator knows 30 UTC instants and failures at
indices 0, 2 and 4. The reader only gets the metadata written for each profile.
The date-only profile uses 30 distinct dates; all others span 30 minutes.

## Behavior and migration

A sidecar timestamp now needs an explicit UTC offset, including `Z`. The parser
ignores unsupported times with a warning that gives accepted examples. A valid
sequence or offset-bearing report start can still establish chronology. The
warning remains visible and `--fail-on-incomplete` exits 2, even when temporal
analysis is otherwise possible. Counts remain 27 passes and 3 failures; no
observations become excluded because their timestamp lacks an offset.

| Metadata supplied | Result in this checkout |
| --- | --- |
| `2026-10-13T00:00:00Z` | Accepted UTC instant |
| `2026-10-13T05:45:00+05:45` | Same instant, original offset retained |
| `2026-10-12T20:30:00-03:30` | Same instant, original offset retained |
| `2026-10-13T09:00:00` or `2026-10-13` | Warning; no recorded instant inferred |
| Invalid timestamp plus complete unique sequences | Warning; sequence order remains usable |
| Invalid timestamp plus reliable report starts | Warning; report timestamp and provenance retained |
| Missing or null timestamp plus sequences | Optional absence; no timestamp warning |
| Contradictory explicit timestamps and sequences | Chronology remains unavailable |

Record the run's actual instant with an offset at its source. For example,
Python's `datetime.now(timezone.utc).isoformat()` produces an aware UTC timestamp
when the run starts. If a historic clock's timezone is unknown, omit the
unsupported timestamp and supply trustworthy unique run sequences if available.
Do not append `Z` to an unknown local clock. Python's
[aware/naive datetime distinction](https://docs.python.org/3.10/library/datetime.html#aware-and-naive-objects)
explains why a clock without timezone information does not identify an instant.

Runner names, the analyzing machine's timezone and filesystem copy times are
not timezone evidence. File mtimes remain labeled as such in original run
metadata but never enter recorded-time ranges or failure timestamps. An
explicit offset can itself be wrong; this change cannot verify that the CI
producer recorded the true time or resolve genuine contradictory evidence.

## Reproduce the failure and controls

[Before](results/before.json) uses source
`ae3158e7a1fb7f6609e614c771500c02400a8058`; [after](results/after.json) uses the fix.
Each of the 15 histories goes through the real CLI, both gates, and standalone
HTML generation. The new-flake gate runs again with a different host timezone.
Each receipt retains input-tree/truth hashes, outcome counts, order, activity,
diagnostics and complete JSON-report hashes. No report fields are normalized.

| History | Before: activity; new / incomplete exits | After: activity; new / incomplete exits |
| --- | --- | --- |
| Explicit mixed, UTC and quarter-hour offsets (3 controls) | quiet; 0 / 0 | quiet; 0 / 0 |
| All local clocks; renamed files and changed mtimes (2) | new; 1 / 0 | unavailable; 2 / 2 |
| One local clock among 29 aware timestamps | ongoing; 0 / 0 | unavailable; 2 / 2 |
| Local clocks with sequences | unavailable; 2 / 2 | quiet; 0 / 2 |
| Local clocks with aware JUnit or TRX times (2) | new; 1 / 0 | quiet; 0 / 2 |
| Local clocks with naive report times | new; 1 / 0 | unavailable; 2 / 2 |
| Date-only sidecars | quiet; 0 / 0 | unavailable; 2 / 2 |
| Absent timestamps with sequences; report-only times (2) | quiet; 0 / 0 | quiet; 0 / 0 |
| Genuine timestamp/sequence conflict | unavailable; 2 / 2 | unavailable; 2 / 2 |
| Malformed timestamp with sequences | quiet; 0 / 2 | quiet; 0 / 2 |

The baseline disagrees in 8 of 15 profiles; the correction agrees in all 15.
Six unaffected profiles produce identical complete JSON reports. The malformed
control retains its behavior with a more actionable warning.

```sh
uv sync --locked
PYTHONPATH=src uv run python studies/sidecar-timezones/replay.py \
  --work /tmp/flakemap-timezones-after --check
```

Use a **new** work directory. For the baseline, export the recorded commit to a
separate directory and point `PYTHONPATH` at its `src`; omit `--check` to capture
the known disagreements. For an installed wheel, unset `PYTHONPATH` and supply
`--python /path/to/environment/bin/python`. Inputs, full JSON and HTML remain in
the requested work directory.

[Compatibility receipt](results/compatibility.json) audits every tracked
sidecar with a timestamp: all 274 include an offset. It compares seven existing
histories (298 runs) through both CLIs, using identical inputs and filesystem
times. Every complete JSON report and exit code remains identical, including
the two histories that already require an incomplete/unavailable result:

```sh
PYTHONPATH=src uv run python studies/sidecar-timezones/compatibility.py \
  --baseline-src /path/to/baseline/src
```

## Installed package and visible reports

The verification and browser receipts are recorded alongside these results
when the implementation has passed clean-archive and installed-wheel checks.
The browser workflow opens before and installed-after standalone HTML offline,
checks the visible activity, 30 outcome cells, warnings and keyboard-accessible
failure details, and verifies there is no page overflow at 1200 and 375 pixels.

```sh
npm ci
node studies/sidecar-timezones/browser.mjs \
  /tmp/flakemap-timezones-before/html /tmp/flakemap-timezones-installed/html \
  /tmp/flakemap-timezones-screenshots
```

Source changes are unreleased. This study does not imply a registry release or
an update to the hosted demo.
