# Renaming shards must not change which results count

Three report shards can describe the same CI run while contributing different
metadata: a sequence from one sidecar, a suite's start time from another report,
and an explicit timestamp from a third sidecar. The loader previously adopted
the report time but retained the sequence-only shard's `sidecar` source. It then
treated the real sidecar timestamp as conflicting evidence and excluded every
test observation in the run. Renaming the files to change their scan order made
the same run valid again.

```text
sequence-only sidecar -> report start -> explicit sidecar time
                        |
before:                 called a sidecar time -> false conflict, results excluded
after:                  remains a report time -> sidecar time takes precedence
```

The merge now keeps each adopted time and its source together. Report starts can
still select their earliest value, explicit sidecar timestamps still take
precedence, and two disagreeing sidecar times still invalidate the run. A
sequence discovered in another shard also supersedes filesystem-time fallback,
matching the behavior when that shard is scanned first.

## Actual CLI reproduction

[Before](results/before.json) uses source `3d2dcd0`; [after](results/after.json)
uses the fix. The capture constructs synthetic JUnit XML and sidecars, controls
file modification times, and runs every filename permutation through the real
CLI with JSON, standalone HTML and `--fail-on-incomplete`.

| Input family | Permutations | Disagreements before | After |
| --- | ---: | ---: | ---: |
| Sequence + report start + sidecar timestamp | 6 | 1 | 0 |
| Sequence + two report starts | 6 | 2 | 0 |
| Sequence + genuinely conflicting sidecar times | 6 | 0 | 0 |
| Sequence + filesystem-time fallback | 2 | 1 | 0 |

The false-conflict case changes from exit 2 and three excluded observations to
exit 0 and three retained passes. The genuine-conflict controls still exit 2 and
exclude all three observations. The earliest report timestamp and its `report`
source are identical across permutations; no filesystem time enters the
recorded timestamp range.

```sh
uv sync --locked
uv run python studies/shard-timestamps/capture.py --check
```

Use `--python /path/to/installed/environment/bin/python` to inspect an installed
wheel and `--artifacts /tmp/shard-reports` to retain one HTML report per family.
Omit `--check` when recording a version known to fail. This is controlled merge
evidence, not a claim about how often public CI artifacts have this layout.
The change does not infer missing metadata or resolve genuine disagreements.

## Installed wheel and visible reports

[Verification receipt](results/verification.json): a clean source archive passes
lint, formatting, type checking and 361 tests, then builds an sdist and a wheel
from that sdist. Fresh installations pass the full suite and all 20 CLI cases
on Python 3.14.7 / Rich 15.0.0 and Python 3.10.21 / minimum Rich 13.7.0. The receipt
includes source commits and artifact SHA-256 values.

[Eight offline browser checks](results/browser.json) inspect the original and
installed-wheel reports in Chromium and Firefox. They verify excluded/retained
cells, tally counts and keyboard-opened evidence. The captured
[before](../../docs/assets/shard-timestamps-before.png) and
[after](../../docs/assets/shard-timestamps-after.png) screenshots show the same
three synthetic observations. One pass per test still means insufficient data;
the fix does not turn them into established healthy tests.

```sh
npm ci
node studies/shard-timestamps/browser.mjs /tmp/before-reports /tmp/after-reports
```

Generate those directories with the capture script's `--artifacts` option
against each version. No hosted page was changed by this source-only update.
