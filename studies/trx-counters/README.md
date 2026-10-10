# TRX counters must account for retained results

At revision `8542d33`, removing the failed result from the real
`examples/trx_history/run-02.trx` report left five records and counters declaring
six results and one failure. Flakemap reported `input_complete: true`, and
`--fail-on-incomplete` exited 0. Changing the failed outcome to `Passed` also
passed the gate even though the retained failure counter contradicted it.

The source fix checks the four primary VSTest counters against structural
results, including nested rows. Both damaged reports now warn and exit 2.
Counters never supply missing identities or change retained observations.
These are source changes. The [publication verification](../../docs/verification-summary-counters-2026-10-10.md)
distinguishes them from a registry release or hosted demo update.

## Evidence and conventions

The controls are twelve retained reports from actual MSTest execution
([project and capture](../../examples/trx_project/README.md)), plus a new
[VSTest logger capture](../../examples/trx_counters_project/README.md) of
controlled public result events. The latter runs the actual logger from .NET
SDK 8.0.425, version 17.11.1, without invoking a test adapter. It captures
nested rows, which the existing MSTest fixture reports as separate top-level
tests instead.

| Captured nested evidence | Count |
| --- | ---: |
| Top-level observations (failed parent, pass, skip) | 3 |
| Nested rows (pass, failure) | 2 |
| VSTest 17.11 `total` | 5 |
| VSTest 17.11 `executed` | 4 |
| VSTest 17.11 `passed` / `failed` | 2 / 2 |
| Raw `NotExecuted` results / auxiliary `notExecuted` counter | 1 / 0 |

The [17.11 logger](https://github.com/microsoft/vstest/blob/v17.11.1/src/Microsoft.TestPlatform.Extensions.TrxLogger/TrxLogger.cs)
counts both parents and rows. The
[newer logger at `05cd78191d1e42585744353e492f81dc3f2c2470`](https://github.com/microsoft/vstest/blob/05cd78191d1e42585744353e492f81dc3f2c2470/src/Microsoft.TestPlatform.Extensions.TrxLogger/TrxLogger.cs#L335-L350)
subtracts a parent when the first data-driven row arrives. Both conventions
define `executed` as `passed + failed`. The
[summary writer](https://github.com/microsoft/vstest/blob/v17.11.1/src/Microsoft.TestPlatform.Extensions.TrxLogger/ObjectModel/TestRunSummary.cs)
initializes auxiliary counters to zero, including `notExecuted`.

Flakemap therefore checks `total`, `executed`, `passed` and `failed`, using one
whole convention at a time. The parent-excluding alternative requires a
`DataDrivenTest` marker and retained inner rows. It does not flatten those rows
into extra history observations. A manually transformed counter set tests the
newer convention; it is **not** a capture from a second logger version.

## Before and after

`replay.py` runs the actual CLI with `--json --fail-on-incomplete --html` for
21 scenarios. [Before](results/before.json) and [after](results/after.json)
receipts retain process exits, warnings, input hashes and normalized
test/statistics hashes. All 21 have identical input and normalized-statistics
hashes across the two implementations. Seven gates change from 0 to 2.

| Scenario | Before: complete / exit | After: complete / exit |
| --- | --- | --- |
| Twelve original `dotnet test` reports | true / 0 | true / 0 |
| Original nested logger capture | true / 0 | true / 0 |
| Failed result removed | true / 0 | false / 2 |
| Failed outcome rewritten to `Passed` | true / 0 | false / 2 |
| Skipped result removed | true / 0 | false / 2 |
| Invalid negative `total` | true / 0 | false / 2 |
| Duplicate `ResultSummary` | true / 0 | false / 2 |
| Failed nested row removed | true / 0 | false / 2 |
| Counters transformed to newer parent-excluding convention | true / 0 | true / 0 |
| Mixture of parent-inclusive and parent-exclusive counters | true / 0 | false / 2 |

From a source checkout, with a fresh output directory:

```sh
uv sync --locked
uv run python studies/trx-counters/replay.py --output scratch/trx-counter-replay --check
node studies/junit-counters/check-browser.mjs scratch/trx-counter-replay \
  removed-failed-result logger-nested-original dotnet-run-02
```

The browser command needs `npm ci` and installed Chromium/Firefox. The shared
checker opens standalone reports offline at 375 and 1200 pixels, light and
dark: 24 views. It compares report rows with JSON, expands the warning by
keyboard, checks declared/observed counts and rejects external requests, page
errors and horizontal overflow. [Browser receipt](results/browser.json).
Inspected screenshots: [desktop](../../docs/assets/trx-counters-desktop.png),
[phone](../../docs/assets/trx-counters-mobile.png).

To rerun the old behavior, extract `src/` from `8542d33` into a separate
directory, set `PYTHONPATH` to that directory's `src`, and run the same replay
without `--check`. Each output directory retains its transformed TRX, metadata,
CLI JSON, stderr and HTML. No live service or runner is needed for the replay.

## Limits

- Only the four primary counters above are reconciled. Auxiliary outcome
  counters and legacy producers with different executed-count semantics are
  not fully validated; unexplained primary totals remain unverified.
- Absent counters remain optional. Invalid primary counters and duplicate
  summaries are warnings, not invented failed observations.
- Matching totals do not prove completeness. Removing records and updating
  counters can evade reconciliation. Different nested conventions can also
  coincide after changes; no producer version is inferred from matching totals.
- Result records are recognized only under `Results` and nested `InnerResults`.
  Result-shaped diagnostic payloads do not participate in the count.
- Nested parent outcomes retain the existing aggregation policy. The check
  does not establish that a parent's outcome correctly aggregates every row.
