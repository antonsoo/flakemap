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
| Go, one record per package | Kubernetes' pruned reports (gotestsum output passed through its `prune-junit-xml`) | `tests/fixtures/kubernetes_pruned/junit_20260803-100711.xml` | An excerpt of a real report: build 2084219256018309120 of `ci-kubernetes-integration-master`, from the public `kubernetes-ci-logs` bucket. Three of its 131 suites are kept, one of them failing; the failing record's `<system-out>`, a second copy of the same output, is removed. Nothing else is changed. `studies/kubernetes-ci` reads 4,315 such reports whole. |
| Maven/Gradle Surefire | [Maven Surefire Plugin](https://maven.apache.org/surefire/maven-surefire-plugin/) XML report; Gradle's `Test` task reuses the same shape | `tests/fixtures/surefire_report.xml` | Hand-authored to match the documented Surefire XML report schema (a bare `<testsuite>` root, one file per test class, `<properties>`, `<error>`/`<failure>` with `message`/`type` attributes). Not run locally -- no JDK/Maven/Gradle in the build environment. |
| GoogleTest | `--gtest_output=xml:report.xml` | `examples/googletest_history` and `examples/googletest_project/captures/failfast.xml` | Compiled and run locally with GoogleTest 1.17.0 and GCC 13.3.0; disabled test/suite, enabled failure, runtime skip and fail-fast controls. Unedited XML/stdout; controlled sequence sidecars. |
| .NET (TRX) | `dotnet test --logger trx` (MSTest, xUnit, NUnit) | `examples/trx_history/run-01.trx` … `run-12.trx` | Generated locally: twelve runs of `examples/trx_project` (MSTest 3.6.1, .NET SDK 8.0.425), machine details removed by its `capture.py`. TRX is not a JUnit dialect; `src/flakemap/parse/trx.py` reads it (see below). |

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

## JUnit summary counters

The source checkout checks `tests`, `failures`, `errors` and `skipped` on each
completed `<testsuite>` and `<testsuites>`. All supplied counters must agree
under one of two conventions: descendant testcase records, or explicit retry
attempts. Parent checks include each descendant once; child suites are also
checked independently. Missing counters are optional, not assumed zero. Invalid
or unexplained totals produce a coverage warning and make
`--fail-on-incomplete` exit 2, including for otherwise well-formed XML.

Surefire's retained six-test report counts thirteen attempts. GoogleTest can
record several failed assertions inside one failed test. Its `disabled` total
describes disabled names even when those tests were explicitly executed, so it
is not used as a skipped-outcome count. Runtime `result="skipped"` and
`<skipped>` records do support `skipped`; suppressed disabled tests do not.

Counters never create missing tests, change a testcase's status or enlarge a
rate denominator. Kubernetes' package rollups remain usable package records,
but their original per-test totals no longer look like verified individual
coverage. A pytest subtest report can also have totals that cannot be recovered
from the testcase records; it remains explicitly unverified. The warning names
the first three affected containers (in completion order), gives their opening
ordinals and counts, and reports how many additional containers were checked
but omitted from the warning. Counter text is limited to 20 characters before
integer conversion.

A matching counter is a consistency check, not proof that the original suite
finished or that all artifacts were supplied. Removing records *and* updating
their counters can evade this check. See the
[runner captures, transformations and replay](../studies/junit-counters/README.md).

## GoogleTest execution attributes

The [compiled fixture and comparison](../examples/googletest_project/README.md)
show why an empty testcase cannot be assumed to pass when it explicitly says
it was not run. A disabled name is not itself evidence of a skip: GoogleTest
can run those tests when requested.

| Execution attributes | Child markers | Observation |
| --- | --- | --- |
| `status="notrun"` or `result="suppressed"` | No failures/retries | Skip; never a pass or a duration measurement |
| `result="skipped"` | No failures/retries | Skip, including when no `<skipped>` child is present |
| `status="run" result="completed"` | No outcome marker | Pass |
| `status="run" result="completed"` | Failure/error | Failure/error; completion does not imply success |
| Contradictory attributes, skip mixed with failure/retry, or an unsupported attribute value | Any | Unknown; excluded with an input warning |
| No execution attributes | Ordinary JUnit markers | Existing child-marker and retry rules below |

Supported status values are `run` and `notrun`; supported result values are
`completed`, `skipped` and `suppressed`. Either attribute may be absent. A
`run/suppressed` or `notrun/completed` pair is contradictory. A skipped child
with a completed result is also retained as unknown. The first useful GoogleTest
diagnostic is retained after its source-location prefix and standalone `Failed`
line; full output remains in the original XML.

Skips stay in the history but do not contribute to failure rates, flip pairs,
timing correlations or stretches of clean executions. Known skips do not make
input parsing incomplete. Unsupported attributes do, and are covered by
`--fail-on-incomplete`. Test-list inventories with no execution attributes are
not supported; use XML produced by running tests.

## TRX (Visual Studio test results)

The source checkout reconciles the optional `total`, `executed`, `passed` and
`failed` attributes of `<ResultSummary><Counters>`. It counts structural results,
including nested rows; VSTest's executed total is passed plus failed. A second
supported convention excludes explicitly marked `DataDrivenTest` parents that
have retained rows. All supplied counters must fit one convention together.
Auxiliary fields such as `notExecuted` are not checked: VSTest writes these as
zero even when it retains skipped results. Unknown conventions remain unverified.

Counter mismatches, invalid primary counters and ambiguous duplicate summaries
warn and make `--fail-on-incomplete` exit 2. Missing counters remain optional.
Neither counters nor nested rows change the parent observations used for rates.
The [TRX counter study](../studies/trx-counters/README.md) retains twelve actual
`dotnet test` reports, an actual VSTest logger capture of controlled nested
events, and explicitly transformed copies used to reproduce missing evidence.

A file whose root element is `<TestRun>` in the
`http://microsoft.com/schemas/VisualStudio/TeamTest/2010` namespace is read as
TRX, whatever its extension; `.trx` files are picked up by the default
`--pattern` (`*.xml,*.trx`). From each `<UnitTestResult>`:

- **Identity.** The classname comes from the matching `<TestDefinitions>`
  `<TestMethod className>` (any `, Assembly` suffix dropped). The name is
  `testName`, minus the class name when it starts with it: MSTest and NUnit
  write the short name, xUnit the fully qualified one. A data row keeps its
  arguments (`CurrencyHasMinorUnits ("JPY",0)`), so each row is its own test.
  The rows nested under `<InnerResults>` are not read separately; their
  parent's outcome already aggregates them.
- **Outcome.** The mappings below follow VSTest's definitions. MSTest reports a
  test that throws as `Failed`. `Completed` only says execution ended; it does
  not establish success.
- **Duration** from `hh:mm:ss.fffffff` (optionally prefixed by `days.`), and
  the failure **message** from `<Output><ErrorInfo><Message>`. A first line
  ending in a colon (MSTest's `Test method ... threw exception:`) is joined to
  the next, which holds the exception.
- **Run time.** `<Times start>` orders the run when no sidecar or path gives a
  timestamp or sequence; the run's metadata source is then `report`. A sidecar
  still wins.

| TRX outcome | Observation |
| --- | --- |
| `Passed` | Pass |
| `PassedButRunAborted` | Pass, with an incomplete-run warning |
| `Failed` | Failure |
| `Error`, `Timeout`, `Aborted` | Error |
| `NotExecuted`, `NotRunnable` | Skip |
| `Completed`, `Inconclusive`, `Warning`, `Pending`, `InProgress`, `Disconnected`, missing or unrecognized values | Unknown; excluded from rates |

These semantics come from [VSTest's `TestOutcome` source](https://github.com/microsoft/vstest/blob/main/src/Microsoft.TestPlatform.Extensions.TrxLogger/ObjectModel/TestOutcome.cs).
Conflicting definitions for one `testId`, or a missing test name, also make the
observation unknown. Original messages and source positions remain in evidence.
An aborted/incomplete run summary warns without erasing known test results.
Multiple `Results` containers are retained with a warning; unsupported result
elements are omitted with a warning.

TRX durations accept nonnegative `TimeSpan` text: hours below 24, minutes and
seconds below 60, and at most seven fractional digits. Values above
[`TimeSpan.MaxValue`](https://learn.microsoft.com/en-us/dotnet/api/system.timespan.maxvalue?view=net-10.0)
(`10675199.02:48:05.4775807`) are unknown, as are malformed or negative durations.
Validation uses integer 100-nanosecond ticks before converting to float seconds;
there is no claim of preserving every tick at the largest magnitudes.

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
- **Nested suites and namespaces**: traverse suites in document order, retaining every supported
  testcase and using the nearest suite name when `classname` is absent. Source
  pointers use a 1-based testcase ordinal. In salvaged XML this is the ordinal
  among recovered records, not an assertion about the original file position.
- **JUnit durations**: negative, nonfinite, nonnumeric or greater-than-`1e100` durations become `null`,
  with a warning. They never become zero. Retry-bearing durations are kept as
  reported evidence but excluded from duration statistics.
- **DTD/entities**: declarations are rejected rather than expanded.
- **classname**: kept as an opaque grouping string, not assumed to be a
  dotted Java class. Go reports put a package path there; Jest sometimes puts
  a describe-block path with leading whitespace (see the real fixture). The
  "suite" grouping used for by-suite rollups is the classname with its last
  dot-separated segment stripped, unless the classname is a path: the suite of
  `k8s.io/client-go/tools/cache` is that package, not `k8s`.
- **Go tests named in a failure** (source checkout): `go test` ends every
  failed test and subtest with a `--- FAIL: Name (0.00s)` line. When a failure's
  text holds such lines for tests other than the testcase itself, they are kept
  as `failed_within`, in output order. That is the only place a report with one
  record per package names what failed. Reports count and place the top-level
  names (`TestDRA`, not `TestDRA/all/…`). At most 200 names are kept per record.
- **Go failure messages** (source checkout): gotestsum writes
  `message="Failed"` on every failure and puts the test's output in the body.
  For exactly that message, the message becomes the last log line
  (`file.go:123: text`) above the first `--- FAIL:`, from a `_test.go` file when
  there is one; a line that ends in a colon takes its continuation, and
  testify's `Error:` line when the block has one. With no `--- FAIL:` at all, a
  `panic:` line is used (`panic: test timed out after 10m0s`). Otherwise the
  message stays "Failed". On the Kubernetes histories this gives 344 of 354
  failures a message of their own.
- **Suite timestamps** (source checkout): the earliest `<testsuite timestamp>`
  that carries a UTC offset (`2026-10-08T04:35:50Z`, as gotestsum and pytest
  write) is the report's own start time. A bare local time, as jest-junit and
  Ant write, is not used: it orders runs from one machine and misorders runs
  from two.
- **Malformed/partial JUnit files**: a streaming XML parser retains completed
  testcase elements before the first syntax error, even inside an unclosed
  suite. It preserves suite context and XML order. Comments and CDATA remain
  text, including when they contain XML examples. Incomplete records and the
  remainder after the error are omitted with a warning; no later fragments are
  guessed. Malformed TRX is omitted because it also needs definitions and
  other document-level context. Empty, unreadable, and zero-result files warn.

## Text decoding and limits

Both parsers recognize UTF-8/16/32 signatures, including UTF-16/32 without a BOM,
and declared text encodings such as Windows-1252 and ISO-8859-1. Unsupported
encodings are not guessed. Invalid bytes produce an explicit warning and U+FFFD
replacement text. A name or classname containing U+FFFD in a lossy/repaired
report becomes unknown: two different broken identities must not merge into a
healthy history. A literal U+FFFD in an otherwise valid report is accepted.
ANSI color escapes in invalid XML are removed; other illegal XML characters
are replaced with a warning. DTD/entity declarations are rejected; quoted
examples in comments or CDATA are inert.

| Input | Bound and behavior |
| --- | --- |
| Report file | 64 MiB; larger files are omitted with a warning before decoding |
| Decoded input to the parser API | 64 Mi characters |
| XML structure | At most 256 nested elements and 250,000 elements; JUnit keeps the completed prefix, TRX is omitted |
| Metadata sidecar | 1 MiB and 128 nested levels; invalid sidecars warn and fall back to path/mtime |
| Failure message | First useful line, capped at 500 characters (TRX may join the first two lines) |

These are per-file limits, not a total history or output-size budget. A large
number of valid reports can still require substantial memory and produce a
large HTML file. Sidecars also reject duplicate JSON keys and nonfinite values;
UTF-8, UTF-16 and UTF-32 BOMs are supported.

[`examples/incomplete_history`](../examples/incomplete_history/README.md) is a
small, hand-authored walkthrough of recovery and unknown values. It is separate
from the real runner captures listed above.

## Run-metadata convention

JUnit XML says nothing about which CI run or commit produced it. flakemap
resolves that from the report file's location, tried in this order (see
`src/flakemap/parse/metadata.py`):

1. **Sidecar JSON.** `<report-stem>.meta.json` next to the report, or one
   `meta.json` from the nearest ancestor directory within the scan root (the
   specific file wins). Recognized keys, all optional: `run_id`, `commit`,
   `branch`, `timestamp` (ISO 8601 with an explicit UTC offset), `runner`, `os`, `sequence` (a nonnegative integer
   ordering key). Unknown keys are kept and
   shown in `--json` output under `extra` but not used statistically.

   In the source checkout, timestamps must include `Z` or an offset such as
   `+00:00`, `+05:45` or `-03:30`. A local clock (`2026-10-13T09:00:00`) or date
   alone (`2026-10-13`) does not identify an instant. It is ignored with a warning;
   the machine timezone, runner name and file copy time cannot supply its offset.
   `--fail-on-incomplete` returns 2 for this warning. A valid sequence or
   offset-bearing report timestamp can still supply chronology, so the
   new-flake gate remains usable when that fallback establishes a common order.
   An absent or null timestamp is optional and does not itself warn.
   [Mixed-zone CLI reproduction and migration examples](../studies/sidecar-timezones/README.md).

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

   Without a sidecar timestamp or sequence, the run's time is the report's own
   when it has one: a TRX file's `<Times start>` or, in the source checkout, a
   JUnit suite's offset-bearing `timestamp` (metadata source `report`). Several
   reports of one run take the earliest. Only two *sidecar* timestamps that
   disagree exclude a run.

   A sequence supplied by one shard does not change the source of a timestamp
   supplied by another. An explicit sidecar time takes precedence over report
   start times; report times retain their provenance while the sequence remains
   available. A sequence also supersedes an earlier shard's filesystem-time
   fallback. [Filename-permutation evidence](../studies/shard-timestamps/README.md)
   covers both merge directions and genuine sidecar conflicts.

3. **File mtime fallback.** If nothing supplies a timestamp or sequence, the
   report file's filesystem modification time is retained with source `mtime`.
   In the source checkout it is copy evidence, never a recorded CI time. It
   cannot establish chronology, enter the recorded timestamp range, or
   contradict a supplied sequence. The report warns about unavailable order
   instead of deriving a timeline from checkout or artifact-download times.

`examples/demo_project/generate_demo_data.py` uses layout 1 (a sidecar
`meta.json` per run directory) and is the reference implementation for a CI
job that wants to produce flakemap-ready output directly.

### Run ordering in the source checkout

A sequence-only run has **no fabricated timestamp**. The loader and `analyze`
resolve one ordering convention across the supplied history:

| Metadata | Temporal analysis |
|---|---|
| Unique nonnegative sequences for every run | Sequence order; recorded timestamps must not move backward |
| Otherwise, unique recorded timestamps for every run | Timestamp order; known sequence values must not move backward |
| Tied timestamps and complete unique sequences | Sequence resolves the ties |
| Mixed partial keys, unresolved ties, contradictory keys, or filesystem-only times | Unavailable; deterministic display order only |

Single-run input requires no inter-run ordering. File mtimes never contradict a
supplied sequence because they are copy evidence, not CI timestamps. Datetime
ordering retains microsecond precision and compares timezone-aware instants.
The library resolves order too; an arbitrary input list does not assert chronology.

Without chronology, rates, retries, same-commit comparisons, named failure counts
and exact shared-outcome cohorts remain available. Flip pairs are zero and their
rate is null; the heuristic score has no flip contribution. Activity, change points,
latest outcome, failure positions, named first/last runs and duration trends stay
null. Report columns are explicitly display order. `--fail-on-new-flake` returns
2, after writing the report, because it cannot evaluate recency. A chronological
decrease in failure rate remains a change point but does not trip that gate.
[Actual pytest reports and permutation replay](../studies/ordering-evidence/README.md).

Missing metadata is not evidence of identical environments. Rerun comparison groups by the provided
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
| No outcome/retry markers, with no non-execution attributes | pass | None reported; does not prove retries were disabled |
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

## JSON output version 3

Version 3 adds `summary.ordering` (`available`, `basis`, `reason`) and
`tests[].temporal_available`. Consumers of version 2 must accept null values for
`tests[].last_status`, `tests[].failures[].index`, and the `first_run_id` /
`last_run_id` / `activity` fields of named failures when chronology is unavailable.
The existing nullable activity, change-point and duration-trend fields also stay
null in that case. `summary.run_id_range` is null without chronology. File mtimes
are excluded from recorded timestamp ranges and failure timestamps; original run
metadata remains in `cofailure.runs`. Historical captured JSON files keep their
original schema version.

Version 2 changes the interpretation of ambiguous records and adds inspectable
retry evidence. Consumers of version 1 must account for these changes:

| Field | Meaning |
|---|---|
| `schema_version` | `3` in this source checkout |
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
| `summary.cofailure_groups` / `cofailure_tests` | Exact shared-outcome cohort count and number of member tests (source checkout) |
| `cofailure.method` | `exact_outcome_history`; descriptive matching, not causal inference |
| `cofailure.runs` | Ordered metadata for every supplied run, including runner/OS, commit, branch and metadata source |
| `cofailure.ambiguous_tests_excluded` | Tests excluded from grouping because any outcome was ambiguous |
| `cofailure.groups[]` | Report-local ID, members, all six `run_states`, final-failure/recovered counts, affected test-run count and original affected evidence |

The following evidence fields introduced during version 2 remain:

| Field | Meaning |
|---|---|
| `summary.flaky_new` / `flaky_quiet` | Flaky tests whose failures began after a long clean stretch, or have stopped for longer than ever before (see `activity`) |
| `tests[].activity` | `null` with no observed failure, unavailable chronology or ambiguous outcomes. Otherwise `state` (`new`, `ongoing`, `quiet`), `failures` (runs with any observed failure, including explicit retry recoveries), `events` (consecutive affected runs counted once), `longest_gap` (most runs without an observed failure between events; `null` with fewer than two), `runs_since_last_failure`, `runs_since_first_failure`, and `silence_ratio`. `quiet` needs 3 events and a silence of at least 3 times the longest gap and 10 runs; `new` is the mirror, and is never given to a name in `named_failures[]` |
| `tests[].activity.basis` / `final_failure_runs` / `recovered_runs` | Source checkout: `basis` is `runs_with_observed_failures`; the two counts sum to `failures`. Each run counts once regardless of retry count. This corrects the earlier source behavior in which activity discarded all recovered failures. `runs.fail` and `failure_rate` still describe final outcomes |
| `tests[].activity_unavailable_reason` | `chronology_unavailable`, `ambiguous_outcomes`, or `null`. The same field accompanies named-failure activity. Absence of observed failures has a null activity and a null reason |
| `tests[].same_commit` | Of the test's failures: `failures_passed_elsewhere`, `failures_failed_everywhere` and `failures_without_another_run`, by what the other runs of the same commit, branch, runner and OS did |
| `tests[].failures[]` | Every final failure, oldest first when chronology is available: `run_id`, `index` (position among the test's usable runs, from 0), `timestamp`, `commit`, `status`, `message`, `failed_within`, `same_commit` (`passed`, `failed`, `single`, `unknown`), `same_commit_other_runs`, `other_tests_failed` |
| `tests[].named_failures[]` | Top-level Go tests named inside this testcase's failures, most frequent first: `name`, `runs`, `first_run_id`, `last_run_id`, `passed_same_commit`, `checked_same_commit`, `activity` |
| `tests[].rerun_signal.value` | Now the share of same-commit pairs of runs that disagree, weighted by runs; equal to `groups_with_flip / groups_with_reruns` when every rerun group has two runs |

Each evidence entry contains `run_id`, `commit`, `reason`, and `records`.
A record carries the original `name` and `classname`, `source: {report, testcase}` (relative report path and 1-based
ordinal), `status`, `message`, `reported_duration_seconds`, `issue`, and optional
`retry: {outcome, attempts, failures}`. The `failures` array retains each marker's
`tag`, `status` and `message`. Library callers that construct records without
source information get `source: null`; provenance is never invented.

Shared-outcome evidence adds `test` to that same evidence shape. See
[matching rules and the complete download contract](shared-outcomes.md).

Use `--fail-on-incomplete` to make any warning exit 2. With all records unusable,
the CLI exits 2 even without this flag. JSON remains on stdout and diagnostics
on stderr, including when `--html` and a failing CI gate are combined.

Additive fields in version 2 expose `summary.input_complete` (false when the
analysis has input/ordering warnings) and `tests[].duration.observations` plus
`trend_axis: "supplied_history_run_index"`. A true `input_complete` only means
no supported integrity problem was detected; it cannot prove that all CI
artifacts were collected.

`trend_seconds_per_run` uses positions in the entire supplied, ordered history.
Missing timings, absent tests, retries, skips and unknown outcomes are not zero
measurements, and do not compress the run axis. This is not elapsed wall-clock
time or an external CI run number. `runs_since_change` includes the onset run
and all later supplied runs, even if the test is absent or skipped later.

HTML exports use an atomic replacement, so a failed write leaves the prior
report intact. The output cannot alias a scanned report or metadata file
(including hard links), and symbolic-link destinations are rejected. These
checks do not provide locking against a concurrently changing input tree.

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
