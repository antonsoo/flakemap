# Changelog

All notable changes to this project are documented in this file.

## Unreleased

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
