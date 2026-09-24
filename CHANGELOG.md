# Changelog

All notable changes to this project are documented in this file.

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
