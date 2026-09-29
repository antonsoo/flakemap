# JUnit XML dialects, and the run-metadata convention

There is no single "JUnit XML" specification; every test runner emits a dialect
of a format Ant/Surefire popularized decades ago. `flakemap` normalizes across
the differences that matter for flakiness statistics: root element shape,
`classname` semantics, and how pass/fail/error/skip is spelled. The parser is
`src/flakemap/parse/junit.py`; its module docstring has the exact rules.

## Dialects tested

| Dialect | Tool | Fixture | How it was obtained |
|---|---|---|---|
| pytest | `pytest --junitxml=report.xml` | `tests/fixtures/pytest_real.xml` | Generated locally: `pytest test_sample.py --junitxml=out.xml` (pytest 9.1.1, this repo's `uv.lock`). |
| Jest | [jest-junit](https://github.com/jest-community/jest-junit) reporter | `tests/fixtures/jest_junit_real.xml` | Generated locally: `npx jest --reporters=default --reporters=jest-junit` (jest-junit installed via `npm install jest jest-junit`, current npm registry versions as of 2026-09-24). |
| Go | [go-junit-report](https://github.com/jstemmer/go-junit-report) / `gotestsum --junitfile` | `tests/fixtures/go_junit_report.xml` | Hand-authored to match the shape documented in the go-junit-report README (`<testsuites><testsuite><properties>` + `<testcase><failure message type>`), since a Go toolchain was not available in the build environment. Not run locally -- flagged here rather than left unstated. |
| Maven/Gradle Surefire | [Maven Surefire Plugin](https://maven.apache.org/surefire/maven-surefire-plugin/) XML report; Gradle's `Test` task reuses the same shape | `tests/fixtures/surefire_report.xml` | Hand-authored to match the documented Surefire XML report schema (a bare `<testsuite>` root, one file per test class, `<properties>`, `<error>`/`<failure>` with `message`/`type` attributes). Not run locally -- no JDK/Maven/Gradle in the build environment. |
| .NET (trx) | `dotnet test --logger trx` | -- | **Not supported.** TRX is a different XML schema (MSTest's own format, not JUnit-derived); a stretch goal explicitly called out as unimplemented. Feeding a `.trx` file to flakemap produces a parse warning and zero testcases for that file, not a crash. |

The additional `examples/retry_history/surefire-001/report.xml` fixture was
generated on 2026-09-29 with **Surefire 3.5.4, JUnit 4.13.2, Maven 3.9.11 and
OpenJDK 25**, after a Java/Maven toolchain became available. It contains real
reporter output from deliberately controlled failures. Only environment
properties were removed; the included Java source and capture script reproduce
it. The original basic Surefire fixture above remains hand-authored. Gradle itself
has not been run for this verification; its
[documented `mergeReruns` format](https://docs.gradle.org/current/userguide/java_testing.html#sec:java_test_reporting)
uses the same recovered-failure convention.

Where a dialect couldn't be run locally, the fixture is marked as hand-authored
in `tests/test_junit_parsing.py`'s module docstring too -- this is stated
rather than silently presented as "verified".

## What the parser normalizes

- **Root shape**: `<testsuites><testsuite>...</testsuite></testsuites>` (pytest,
  Jest) and a bare `<testsuite>` (Surefire, one file per class) are both
  accepted; a `<testsuite>` with no `<testsuites>` wrapper is treated as a
  single-element suite list.
- **Status**: a skip combined with failure/error or retry evidence is unknown;
  an ordinary `<skipped>` is excluded from the denominator. `<failure>` and
  `<error>` are kept as distinct statuses in the raw model (`Status.FAIL` /
  `Status.ERROR`) but treated identically ("not green") by every flakiness
  statistic, since the distinction is dialect-specific and not reliable (pytest
  reports uncaught exceptions in test bodies as `<failure>`, not `<error>` --
  see `tests/fixtures/pytest_real.xml`).
- **Nested suites**: traverse suites in document order, retaining every supported
  testcase and using the nearest suite name when `classname` is absent. Source
  pointers use a 1-based testcase ordinal. In salvaged XML this is the ordinal
  among recovered records, not an assertion about the original file position.
- **Durations**: negative, nonfinite, nonnumeric or greater-than-`1e100` durations become `null`,
  with a warning. They never become zero. Retry-bearing durations are kept as
  reported evidence but excluded from duration statistics.
- **DTD/entities**: declarations are rejected rather than expanded.
- **classname**: kept as an opaque grouping string, not assumed to be a
  dotted Java class. Go reports put a package path there; Jest sometimes puts
  a describe-block path with leading whitespace (see the real fixture). The
  "suite" grouping used for by-suite rollups is the classname with its last
  dot-separated segment stripped.
- **Malformed/partial files**: a truncated file (a CI job killed mid-run,
  leaving an unclosed root tag) fails a well-formed-XML parse; flakemap then
  salvages every complete `<testsuite>...</testsuite>` fragment it can find
  with a bounded regex scan and reports what it had to discard as a warning
  rather than raising. An empty file, an unreadable file, and a file with zero
  `<testcase>` elements all degrade to `(No testcases, warning)` instead of an
  exception. See `tests/test_junit_parsing.py` for the exact cases.

## Run-metadata convention

JUnit XML says nothing about which CI run or commit produced it. flakemap
resolves that from the report file's location, tried in this order (see
`src/flakemap/parse/metadata.py`):

1. **Sidecar JSON.** `<report-stem>.meta.json` next to the report, or one
   `meta.json` from the nearest ancestor directory within the scan root (the
   specific file wins). Recognized keys, all optional: `run_id`, `commit`,
   `branch`, `timestamp` (ISO 8601), `runner`, `os`, `sequence` (a nonnegative integer
   used to order runs when there's no timestamp). Unknown keys are kept and
   shown in `--json` output under `extra` but not used statistically.

   ```
   runs/
     run-0001/
       report.xml
       meta.json      # {"commit": "a1b2c3d", "branch": "main", "timestamp": "2026-06-01T09:00:00Z", ...}
   ```

2. **Directory-per-run layout, no sidecar.** `<root>/<run_id>/*.xml` -- the
   first directory beneath `<root>` becomes `run_id`, including nested shards.
   This is the natural shape of "download each CI run's artifact into its own
   folder", e.g. from `actions/download-artifact` with a matrix build.

3. **File mtime fallback.** If nothing supplies a timestamp or sequence, the
   report file's filesystem modification time is used, and `flakemap`'s CLI
   warns when more than half the runs in a batch fall back to mtime -- a
   fresh `git clone` or artifact re-download can collapse many files to the
   same mtime, which would silently corrupt run ordering (and therefore flip
   rate, change-point, and duration trend) without the warning.

`examples/demo_project/generate_demo_data.py` uses layout 1 (a sidecar
`meta.json` per run directory) and is the reference implementation for a CI
job that wants to produce flakemap-ready output directly.

A sequence-only run has **no fabricated timestamp**. Its sequence controls its
order even if files are copied or touched in reverse order. Mixed timestamp and
sequence-only runs are ordered in separate tiers and produce a warning; supply
one common ordering convention for temporal statistics. Missing metadata is not
evidence of identical environments. Rerun comparison groups by the provided
commit, branch, runner and OS; additional configuration remains unobserved.

Reports with the same `run_id` merge only as a logical run. If supplied commit,
branch, runner, OS, sequence or explicit timestamp values disagree, every outcome
in that run is excluded with a warning. Use distinct IDs for different CI matrix
jobs and full job reruns; do not put them under one ID as if they were shards.

Repeated test identifiers within a run are **unknown**, including identical
copies. Neither file order nor matching content proves whether these are retries,
shards or duplicate artifacts. Their original records remain in JSON/HTML, but
none contribute to rates, rerun counts, or change-point inference. The heatmap
uses the same normalized observations as the statistics.

## Explicit retry markers

These rules follow [Surefire's retry XML documentation](https://maven.apache.org/surefire/maven-surefire-plugin/examples/rerun-failing-tests.html).

| Direct children of a testcase | Final outcome | Retry evidence |
|---|---|---|
| No outcome/retry markers | pass | None reported; does not prove retries were disabled |
| `flakyFailure` / `flakyError` only | pass | Recovered; each marker is a failed attempt, plus one eventual pass |
| `failure` / `error`, with `rerunFailure` / `rerunError` | fail / error, using the original terminal marker's kind | Exhausted; original failure plus every recorded retry failure |
| `rerunFailure` / `rerunError` without an original failure | unknown | Incomplete evidence; excluded |
| Recovered markers mixed with terminal or exhausted markers | unknown | Contradictory evidence; excluded |
| Skip mixed with failures or retries | unknown | Contradictory evidence; excluded |

The overall testcase `time` is the successful attempt's duration for recovered
tests, or the original failure's duration for exhausted tests. It is **not** the
sum of attempts. No per-attempt duration or retry cost is inferred. Failed records
retain XML order, tag, status and the first message/stack-trace line, capped at
500 characters. Suite-level `tests`/`failures` counters are not used as independent
observation counts: the real fixture's total of 13 includes retries and a skipped
testcase, across only six testcase elements.

Gradle's default unmerged repeated testcases are deliberately ambiguous here.
Enable `reports.junitXml.mergeReruns = true` to emit explicit recovered markers.
Other retry dialects need their own documented format support; a name repeated
near a passing result is not enough to infer recovery.

## JSON output version 2

Version 2 changes the interpretation of ambiguous records and adds inspectable
retry evidence. Consumers of version 1 must account for these changes:

| Field | Meaning |
|---|---|
| `schema_version` | `2` |
| `summary.recovered_test_runs` | Number of usable test/run observations that passed on retry |
| `summary.exhausted_test_runs` | Number with explicit retries that never passed |
| `summary.excluded_test_runs` | Ambiguous test/run observations excluded from statistics |
| `warnings` | Input, metadata, omission and ordering warnings in all output modes |
| `tests[].runs.total` | Usable final outcomes, one per test/run; excludes skips and unknowns |
| `tests[].runs.unknown` | Excluded test/run observations |
| `tests[].failure_rate` | Final-failure Wilson interval, or `null` when no usable outcomes exist |
| `tests[].flip_pairs` | Number of eligible pairs underlying `flip_rate` |
| `tests[].flip_rate` | `null` when no usable pairs exist |
| `tests[].rerun_signal.groups_with_reruns` / `groups_with_flip` | Replace the version 1 `commits_with_*` keys; groups include branch/runner/OS |
| `tests[].retries` | Recovered/exhausted counts, observed failed-attempt count, and evidence |
| `tests[].excluded` | Excluded observations with reason and original records |

Each evidence entry contains `run_id`, `commit`, `reason`, and `records`.
A record carries the original `name` and `classname`, `source: {report, testcase}` (relative report path and 1-based
ordinal), `status`, `message`, `reported_duration_seconds`, `issue`, and optional
`retry: {outcome, attempts, failures}`. The `failures` array retains each marker's
`tag`, `status` and `message`. Library callers that construct records without
source information get `source: null`; provenance is never invented.

Use `--fail-on-incomplete` to make any warning exit 2. With all records unusable,
the CLI exits 2 even without this flag. JSON remains on stdout and diagnostics
on stderr, including when `--html` and a failing CI gate are combined.

Distinct `(classname, name)` pairs that collapse to the same dotted display
identifier are also excluded across the history, with the original fields kept
in evidence. Library callers must provide unique run IDs (the loader already
merges shards); repeated IDs passed directly to `analyze` raise `ValueError`.

## Recommended CI recipe

Collect JUnit XML as a build artifact on every run, accumulate a rolling
window of them (e.g. the last 200 runs, via `actions/upload-artifact` +
`actions/download-artifact` or a dedicated storage step), and run `flakemap
--fail-on-new-flake` on a schedule. See the README's CI recipe section for a
worked example workflow.
