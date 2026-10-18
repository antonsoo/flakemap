# Changelog

All notable changes to this project are documented in this file.

## Unreleased

### Native NUnit reports

- Read native NUnit 3 result XML directly, including NUnit 4 and NUnitLite
  output. Preserve closed fixture full names, custom case names, per-case
  results, durations, source ordinals and offset-bearing recorded start times.
- Check native counters on every suite and the run. Discovery count may exceed
  filtered execution count. Assertions and aggregate suites never add trials;
  final passes without attempt records do not establish retry recovery.
- Keep warning/inconclusive and duplicate identities unknown. Surface separate
  suite teardown failures without changing passing body outcomes.
- Retain actual pinned NUnit 3/4 captures, unchanged NodaTime/Math.NET source
  executions, installed-CLI replay and an offline native-input gallery example
  in the [study](studies/nunit3/README.md). This adds no runtime dependency or
  registry release.

### Distinct native generic fixtures

- Keep type-argument commas in TRX class names. NUnit's `Pair<Int32,String>` and
  `Pair<Int32,Double>` previously collapsed into one ambiguous observation or a
  false 50% flaky history, depending on whether both ran together.
- Strip assembly qualifiers only outside generic/array brackets and escaped
  characters. Preserve unfamiliar unbalanced names literally. Retain actual
  compiled NUnit TRX, complete CLI before/after reports and unchanged captured
  histories in the [generic fixture study](studies/trx-generics/README.md).

### Wilson interval endpoints

- Keep the analytic lower bound exactly zero for 0/n and the upper bound exactly
  one for n/n. Floating-point subtraction could exclude the point estimate by a
  tiny amount and print a long decimal in reports. Retain the independent SciPy
  comparison of 74 endpoint/interior cases found during native-report review.

### TRX parent/child evidence

- Retain nested native results without making them extra trials or retries.
  A passed/skipped parent containing a recorded failure now becomes unknown;
  `--fail-on-incomplete` exits 2 even when primary counters reconcile. Keep
  already-failed parents and unsupported parent outcomes distinct.
- Include the reported parent outcome and child paths, names, outcomes,
  durations and messages in record evidence. HTML identifies the reported
  outcome separately from its normalized eligibility. Keep the parser's
  source-specific warning once instead of repeating it during analysis.
- Retain seven actual VSTest logger controls, independent XML checks, unchanged
  counter-study results, before/after standalone reports and a labelled authored
  large-hierarchy measurement in `studies/trx-hierarchy`. The controls use public
  events, not a test adapter or production CI. Source changes remain separate
  from the registry release.

### New-flake gate windows

- Count every supplied history run in the trailing new-flake window, including
  skipped and absent tests. Execution-based activity distances previously made
  old failures look recent when a test stopped running. The correction covers
  final failures, recovered retries and names inside package failures.
- Expose the first observed-failure run and its distance in the complete history
  in JSON; identify the separate activity axis as usable test executions.
  Retain 56 actual controlled pytest reports, boundary controls and before/after
  CLI captures in the [gate-window study](studies/gate-window/README.md).

### Literal Markdown evidence

- Render imported names, run IDs and warnings as native Markdown code spans.
  HTML code wrappers still interpreted images, links and emphasis; entity
  escaping alone also allowed email autolinks. Choose delimiters longer than
  imported backtick runs and preserve GFM table pipes and boundary spaces.
- Retain actual pytest XML, six CLI workflows, independent cmark-gfm rendering
  and offline Chromium/Firefox evidence in the
  [Markdown study](studies/markdown-literals/README.md). JSON, terminal reports,
  standalone HTML and statistical results retain their existing contents.

### Retry activity

- Include explicit failed attempts before retry recovery in new/ongoing/quiet
  activity and the last-observed-failure position. Persistent retries no longer
  become a quiet flake merely because their final outcomes pass. Final failure
  rates, retry counts and source evidence keep their existing meaning.
- Activity JSON identifies its basis and separates final-failure and recovered
  runs. Ambiguous outcomes withhold activity, including named inner tests, and
  make the new-flake gate return 2. Newly recurring recovered failures can now
  trigger the existing new-flake rule.
- Retain three fresh controlled Surefire executions and four explicitly
  composed histories in the [retry-activity study](studies/retry-activity/README.md).

### Run chronology

- Retain offset-bearing report timestamps beside sequence-only sidecars,
  including metadata on the same report or its run directory. Previously these
  layouts discarded recorded time and could silently accept a contradictory
  sequence, turning old failures into a false new-flake alert. Preserve explicit
  sidecar timestamp precedence and retain all rate evidence when chronology is
  unavailable. [JUnit/TRX CLI controls](studies/report-sequences/README.md).

- Require an explicit UTC offset in sidecar timestamps. Local clocks and dates
  alone previously became UTC, which could move old failures after newer passes
  and trigger a false new-flake alert. Ignore the unsupported time with an
  actionable warning; preserve outcomes and ordering from valid sequences or
  report start times. `--fail-on-incomplete` returns 2 for the warning, even
  when another source supplies chronology.
  [Controlled mixed-zone histories](studies/sidecar-timezones/README.md) reproduce
  the alert and cover both gates, report fallback and valid offsets.

- Preserve a timestamp's source while merging report shards. A sequence-only
  sidecar no longer turns a later report start into a sidecar timestamp, causing
  false conflicts or preventing selection of the earliest report time. A
  sequence found in another shard also supersedes filesystem-time fallback.
  [Twenty CLI filename permutations](studies/shard-timestamps/README.md) retain
  valid observations while continuing to exclude genuine sidecar conflicts.

- Require a common, unambiguous sequence or recorded timestamp order before
  temporal analysis. Tied times, filesystem copy times, mixed incomplete keys
  and conflicting metadata no longer invent regression commits, activity,
  flip rates, latest outcomes or duration trends. Retain counts, retry records,
  same-commit comparisons and co-failure groups. Reports label display order.
- Resolve complete sequences consistently in the loader, library and HTML,
  including sequences that disambiguate tied timestamps. `--fail-on-new-flake`
  returns 2 without chronology, and no longer flags a fall in the final failure
  rate as a new failure. JSON advances to version 3 to identify newly nullable temporal fields.
- Retain 40 actual controlled pytest reports, folder-permutation replays,
  ordered regression/recovery controls and browser checks in the
  [ordering study](studies/ordering-evidence/README.md).

### TRX summary coverage

- Reconcile VSTest's `total`, `executed`, `passed` and `failed` counters against
  retained results, including nested rows. Removed results, rewritten outcomes,
  invalid primary counters and duplicate summaries now mark coverage unverified
  and make `--fail-on-incomplete` exit 2. History observations remain unchanged.
- Preserve parent-inclusive and explicitly marked data-parent-exclusive counting
  conventions. Do not equate VSTest's always-zero auxiliary `notExecuted` field
  with the count of skipped records. Retain an actual nested logger capture,
  twelve existing `dotnet test` controls and seven damaged variants in the
  [TRX counter study](studies/trx-counters/README.md).

### JUnit summary coverage

- Reconcile `tests`, `failures`, `errors` and `skipped` totals in completed
  JUnit containers with their descendant testcase records or explicit retry
  attempts. Well-formed but filtered reports and stripped outcome markers
  previously passed `--fail-on-incomplete`; unexplained totals now exit 2.
- Preserve observed outcomes and rates. Counters cannot identify missing tests
  or prove that a retained passing record failed. Surefire attempt totals,
  GoogleTest disabled tests and multiple assertion failures keep their distinct
  meanings. Missing counters stay optional; unsupported conventions remain
  unverified. Bound warning detail while checking every completed container.
- Retain a real pytest capture, six deliberately damaged report variants,
  unchanged runner controls and a before/after Kubernetes corpus replay in
  [the counter study](studies/junit-counters/README.md).

### GoogleTest execution evidence

- Honor `status="notrun"` and `result="suppressed"` as skips. Previously, a
  disabled test became a pass, reducing failure rates and introducing false
  recovery and duration observations. Do not infer skips from `DISABLED_` names.
- Recognize `result="skipped"`; preserve failure markers on completed executions.
  Contradictory or unsupported execution attributes are unknown and cause the
  existing `--fail-on-incomplete` gate to exit 2.
- Keep the first useful GoogleTest diagnostic after its location/`Failed` prefix.
- Retain eight runs of a compiled GoogleTest 1.17.0 program and a fail-fast
  control, including XML/stdout, a pinned source archive and before/after reports.

### On real data

- `studies/kubernetes-ci` reads 91 days of two Kubernetes CI jobs, 4,334 hourly
  builds, from the public Prow bucket. 329 builds failed; of the 314 package
  failures on a commit built more than once, 310 passed in another build of the
  same commit. Ten of the sixteen tests that failed five times or more had
  stopped failing weeks before the end, and Kubernetes' tracker shows a pull
  request naming the test merging within three days of the last failure for
  three of them. The entries marked "Kubernetes" below are what those histories
  exposed.

### Added

- New, ongoing or quiet: where a flaky test's failures fall in its history.
  Consecutive failing runs are one event. A test with three events or more is
  quiet when the runs since its last failure are at least three times the
  longest gap between two of them (and at least ten), and new when the clean
  stretch before its first failure is. Shown in every output with the gap and
  the silence, and no probability. A test named only in failure output (Go's
  `--- FAIL:` lines) is never called new, because the history cannot show it
  existed before it failed. (Kubernetes: one rate per test described ten flakes
  that had stopped failing. An earlier, unreleased form of this label printed
  odds from an exact test that assumed independent failures; an audit of the
  study showed they did not hold for failures that come in bursts.)
- Evidence for each failure: whether the test passed, or failed, in the other
  runs of the same commit, and how many other tests failed in that run. Tables
  show "19 of 19 passed on the same commit".
- Go tests named in a failure's output (`--- FAIL:` lines) are kept, counted and
  placed separately, for reports that hold one record per package. gotestsum's
  constant message "Failed" is replaced by the failing test's last log line.
  (Kubernetes: 354 failures, each with the message "Failed" and no test name.)
- `--fail-on-new-flake` also fires for a test, or a test named inside one, that
  is new and first failed inside the window. The change point it relied on
  needs a 20-point shift in failure rate, which a flake that fails one run in
  fifty never produces.
- A JUnit suite's own `timestamp`, when it carries a UTC offset, orders a run
  that has no sidecar timestamp, ahead of the file's modification time.

### Changed

- The HTML report draws a history longer than 300 runs as a rail per test with
  a mark per failure, lists tests that never failed once there are more than 30
  of them, and gives each opened row a table of its failures. (Kubernetes: 687 MB
  for 1,524 tests over 2,153 runs, now 0.4 MB; 62 MB for 136 tests, now 1 MB.)
- Rates print with two significant digits near 0% and 100%, beside a count:
  "0.93% (0.60%–1.4%)" and "20 of 2,162", where the table said "1% (1%–1%)".
  The terminal and Markdown tables show failed runs, same-commit evidence and
  the last failure instead of the score, and list quiet tests last.
- The rerun signal is the share of same-commit pairs of runs that disagree,
  weighted by runs, instead of the share of commits with both outcomes. The two
  are equal when every rerun is one extra run; with commits built from twice to
  116 times the old one ranked a test failing 0.56% of runs above one failing
  0.88%.
- A test that once flaked can be called broken again: only a same-commit
  disagreement since the change point rules it out.
- A long test name keeps its last component in the report's name column; the
  package is what gets cut.

### Fixed

- A run with no recorded time, placed by its file's modification time among
  runs placed by theirs, is now reported by name. One such build out of 2,162
  was silently ordered last.
- Reports of one run that each carry their own start time no longer count as
  conflicting metadata.
- The suite of a Go test is its package: `k8s.io/client-go/tools/cache` was
  grouped under `k8s`.
- Loading is lighter: names are shared between runs and source positions are
  set as records are read. Reading three million outcomes and writing their
  report took 3 min 51 s and 3.3 GB; it takes 2 min 12 s and 1.2 GB on the same
  machine.

### Added earlier in this cycle

- Exact shared-outcome cohorts across tests in terminal, Markdown, JSON and HTML.
  Matching includes run coverage and retry states; ambiguous histories are excluded.
  Source evidence and member links support investigation without claiming a common
  cause. Bounded HTML previews have a complete offline JSON download.
- A captured twelve-run pytest/loopback-service example separates shared outages,
  an independent failure and partial coverage. The demo builder adds navigable
  shared-failure, retry and interrupted-input examples with explicit provenance.

### Fixed

- Truncated JUnit reports retain completed testcases with their suite context;
  XML examples inside logs and comments can no longer become invented results.
  Recovery stops at the first syntax error. Namespaced outcomes and deferred
  end-of-file parser events preserve their original meaning.
- TRX `Completed`, `Warning` and `Inconclusive` outcomes remain unknown instead
  of becoming passes or skips. Ambiguous identities and incomplete run summaries
  stay visible. Invalid or overflowing `TimeSpan` durations remain unknown.
- Duration trends retain missing runs on the horizontal axis. Old change points
  continue aging when a test disappears, so they no longer trip a recent-onset gate.
- Report decoding recognizes UTF-16/32 and declared text encodings. Corrupted
  identities are excluded from cross-run inference. XML and metadata have
  explicit resource limits; ambiguous sidecars cannot silently choose a run.
- HTML output cannot overwrite input evidence; failed writes preserve prior output.

### Reports and verification

- JSON exposes detected input completeness, timing sample count and trend axis.
  Opened HTML rows show the full test identity, including on narrow screens.
- Added a documented synthetic interrupted-run walkthrough and repeatable
  Chromium/Firefox checks over it and captured pytest, Surefire and MSTest histories.

### Maintenance

- The uv configuration and lock now explicitly prefer stable dependency releases,
  keeping local development and CI consistent.

## [0.3.7] - 2026-10-03

### Fixed

- A report whose failure message held a terminal colour code lost every test in it. Test output
  carries colour codes (ESC `[31m`) into failure messages, and some reporters write that ESC
  into the XML raw or as `&#27;`, which XML 1.0 does not allow: the file failed to parse, and
  so did every fragment the recovery scan tried. Since only failing runs carry those messages,
  a test failing one run in three read as healthy. Such reports are repaired and read in full
  now: colour codes are dropped, and any other control character becomes U+FFFD, with a
  warning saying how many. The same holds for TRX.

### Security

- XML allows the C1 control characters, among them U+009B, an 8-bit CSI some terminals act on.
  One in a test name, run id or warning reached the terminal and the Markdown report as it
  was; each is now written as a visible escape (`t_\x9b8m`).

## [0.3.6] - 2026-10-03

### Compatibility

- Python 3.13 and 3.14 are tested and declared. CI runs the suite on 3.14
  as well, and the package's classifiers list both versions. The code is
  unchanged: with the newest release of every dependency, the tests pass on
  3.14 and on 3.15's release candidate.

## [0.3.5] - 2026-10-02

### Accessibility

- The HTML report, checked with axe-core (WCAG 2.1 A and AA, and its best-practice rules) in light and dark,
  at desktop and phone widths: no findings now.
  In the light theme the "flaky" stamp and tally were amber on pale paper
  (2.8:1); as text the amber is darker (4.5:1), and the heatmap cells keep
  their colour. The report has a `main` landmark.

## [0.3.4] - 2026-10-02

- The HTML report carries a Content-Security-Policy. It is one file with no
  script in it, and the policy has the browser hold it to that: nothing in it
  may run or be fetched, whatever a test's name or a failure message says.
  Both are escaped; the policy is for the day one is not. Opened from disk in
  Chromium and Firefox: no violations, and the report is pixel for pixel what
  it was.

## [0.3.3] - 2026-10-02

- `flakemap runs --markdown > report.md` on Windows. Before 3.15, Python gives
  a redirected stdout the system's code page (cp1252 in the west), which has
  no emoji, so the Markdown report stopped with `UnicodeEncodeError` at its
  first status marker; the terminal report did the same on a test name outside
  the code page. Output to a pipe or a file is UTF-8 now. (Reproduced on Linux
  by giving the pipe cp1252 with `PYTHONIOENCODING`; the tests do the same.)
- A `meta.json` written by Windows PowerShell: `>` and `Out-File` write UTF-16
  with a byte-order mark, `-Encoding utf8` writes UTF-8 with one. Either was
  reported as an invalid sidecar and the run lost its commit and its place in
  the order. Both are read.

## [0.3.2] - 2026-10-02

- The report in a CI log. Written to a pipe or a file, the terminal report was
  laid out 80 columns wide: a test's name was folded over two lines, so
  searching the log for it found nothing; the summary line broke before its
  last word; and the flip-rate and "since" columns, kept for wide terminals,
  were left out. A pipe now gets every line whole, with all the columns, and
  the names in the `--fail-on-new-flake` message on one line. A terminal is
  laid out as before, and `COLUMNS`, when set, is respected.

## [0.3.1] - 2026-10-01

- Published to PyPI: `pip install flakemap`, or `uvx flakemap <reports>` to run
  it without installing. The README's images and links are rewritten to
  absolute URLs at build time so they work on the project page.

## [0.3.0] - 2026-09-30

- .NET TRX reports (`dotnet test --logger trx`, for MSTest, xUnit and NUnit) are
  read alongside JUnit XML; the default `--pattern` is now `*.xml,*.trx` and
  accepts several comma-separated globs. Data rows stay separate tests, MSTest's
  two-line exception messages are joined for clustering, and a TRX file's own
  start time orders its run when no sidecar does (metadata source `report`).
  Checked against twelve real MSTest runs in `examples/trx_history`, captured by
  `examples/trx_project/capture.py`.
- A regression in a short history was labeled `flaky`: its one pass-to-fail
  switch is a flip rate over the 8% threshold (1 in 12 runs), and the flip rate
  was checked before the change point. A significant change point into mostly
  failing now comes first, so it is `broken`. The demo's labels are unchanged.

## [0.2.0] - 2026-09-30

- Preserve Surefire/Gradle merged retry evidence: distinguish recovered and
  exhausted retries, expose failed records and source testcase positions, and
  count each test/run once. Add `--fail-on-retry` for explicit recovery gating.
- Exclude duplicate identifiers, contradictory outcomes, and runs with conflicting
  shard metadata. Statistics and HTML now use the same observations.
- Honor sequence-only metadata over mtimes and inherit metadata through nested
  shard directories. Scope same-commit rerun comparison by branch/runner/OS.
- Add `--fail-on-incomplete`; carry warnings through every output format. Keep
  JSON stdout valid alongside HTML output and failing CI gates. Return exit 2
  when there are no usable observations.
- JSON schema version 2 adds retry/exclusion evidence and nullable failure rates
  for empty samples; rerun group keys replace the old commit-count keys.
- Add an actual Surefire retry fixture, its Java source and reproduction script,
  parser/history/output regressions, and report evidence views.
- Change points need a significant likelihood-ratio statistic (13.8, the
  approximate 99th percentile under no change; `scripts/changepoint_null.py`).
  A steadily 20-30%-flaky test over 222 runs used to get a change point about
  half the time, and one in its last 10 runs 12-16% of the time, tripping
  `--fail-on-new-flake`; now about 1% and almost never. In the demo history
  the two flaky tests lose their spurious "since" runs; the real regression
  keeps its commit.

## [0.1.0] - 2026-09-24

Initial release.

### Added

- JUnit XML parsing for pytest, Jest (jest-junit), and Maven/Gradle Surefire
  dialects, with a hand-authored-but-documented fixture for go-junit-report.
  Malformed and partial files degrade to a warning instead of raising.
- Run-metadata resolution via sidecar JSON, directory-per-run layout, or file
  mtime fallback.
- Per-test flakiness statistics: Wilson-interval failure rate, flip rate,
  same-commit rerun disagreement, a documented flakiness score, single
  change-point detection, duration trend and duration-vs-failure correlation,
  and per-runner/per-OS failure rate breakdowns.
- `broken` vs `flaky` vs `healthy` vs `insufficient_data` classification.
- Terminal (rich), `--json`, `--markdown`, and self-contained `--html`
  (test x run heatmap) report formats.
- `--fail-on-new-flake` for CI gating.
- A synthetic demo corpus (`examples/demo_project/`) of ~220 real `pytest`
  runs with planted flaky, broken, and healthy tests, plus the script that
  generated it.
