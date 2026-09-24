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

Where a dialect couldn't be run locally, the fixture is marked as hand-authored
in `tests/test_junit_parsing.py`'s module docstring too -- this is stated
rather than silently presented as "verified".

## What the parser normalizes

- **Root shape**: `<testsuites><testsuite>...</testsuite></testsuites>` (pytest,
  Jest) and a bare `<testsuite>` (Surefire, one file per class) are both
  accepted; a `<testsuite>` with no `<testsuites>` wrapper is treated as a
  single-element suite list.
- **Status**: a `<skipped>` child wins over everything else; `<failure>` and
  `<error>` are kept as distinct statuses in the raw model (`Status.FAIL` /
  `Status.ERROR`) but treated identically ("not green") by every flakiness
  statistic, since the distinction is dialect-specific and not reliable (pytest
  reports uncaught exceptions in test bodies as `<failure>`, not `<error>` --
  see `tests/fixtures/pytest_real.xml`).
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
   `meta.json` shared by a directory of reports (the specific file wins over
   the shared one). Recognized keys, all optional: `run_id`, `commit`,
   `branch`, `timestamp` (ISO 8601), `runner`, `os`, `sequence` (an integer
   used to order runs when there's no timestamp). Unknown keys are kept and
   shown in `--json` output under `extra` but not used statistically.

   ```
   runs/
     run-0001/
       report.xml
       meta.json      # {"commit": "a1b2c3d", "branch": "main", "timestamp": "2026-06-01T09:00:00Z", ...}
   ```

2. **Directory-per-run layout, no sidecar.** `<root>/<run_id>/*.xml` -- the
   immediate parent directory's name becomes `run_id` even with nothing else.
   This is the natural shape of "download each CI run's artifact into its own
   folder", e.g. from `actions/download-artifact` with a matrix build.

3. **File mtime fallback.** If nothing above supplies a timestamp, the
   report file's filesystem modification time is used, and `flakemap`'s CLI
   warns when more than half the runs in a batch fall back to mtime -- a
   fresh `git clone` or artifact re-download can collapse many files to the
   same mtime, which would silently corrupt run ordering (and therefore flip
   rate, change-point, and duration trend) without the warning.

`examples/demo_project/generate_demo_data.py` uses layout 1 (a sidecar
`meta.json` per run directory) and is the reference implementation for a CI
job that wants to produce flakemap-ready output directly.

## Recommended CI recipe

Collect JUnit XML as a build artifact on every run, accumulate a rolling
window of them (e.g. the last 200 runs, via `actions/upload-artifact` +
`actions/download-artifact` or a dedicated storage step), and run `flakemap
--fail-on-new-flake` on a schedule. See the README's CI recipe section for a
worked example workflow.
