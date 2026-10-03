# Changelog

All notable changes to this project are documented in this file.

## Unreleased

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
