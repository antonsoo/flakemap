# Failed attempts remain active after a green retry

Flakemap's old activity calculation used only final failures. In a 20-run
history with three early final failures and 15 consecutive passed-on-retry
results, it reported **quiet, last failure 15 runs ago**. Each of those last
15 runs contained an explicit failed attempt. The corrected source reports
**ongoing, last observed failure in the latest run** and keeps the final
failure rate at 3/20 (15%).

This is an unreleased source repair. No package or hosted report was published.

## Reporter evidence

The small [Java test](project/src/test/java/example/ActivityTest.java) was executed
three times on 2026-10-11, using Maven 3.9.11, Surefire 3.5.4, JUnit 4.13.2 and
Temurin OpenJDK 25.0.4.1 on Linux/WSL2. Its modes force an ordinary pass, an
exhausted failure, or a first-attempt failure followed by a pass. The POM allows
two reruns.

| Execution | Maven exit | Final failure markers | Rerun failure markers | Recovered failure markers |
|---|---:|---:|---:|---:|
| pass | 0 | 0 | 0 | 0 |
| failed | 1 | 1 | 2 | 0 |
| recovered | 0 | 0 | 0 | 1 |

[Capture receipt and hashes](fixtures/capture.json), with
[pass](fixtures/pass.xml), [failed](fixtures/failed.xml), and
[recovered](fixtures/recovered.xml) XML. Only machine-specific `<properties>`
were removed. Outcomes, counters, failed-attempt messages and times were retained.
The marker interpretation also agrees with
[Surefire's retry documentation](https://maven.apache.org/surefire/maven-surefire-plugin/examples/rerun-failing-tests.html).

These are controlled executions, not production failures. The four histories
below are **synthetic compositions** of those three files, with explicit sequence
numbers. They do not represent 80 separate Java executions or measured flake
probabilities. `ambiguous_tail` deliberately duplicates a passing testcase in
the last report and adjusts its counter; that perturbation is not reporter output.

## Before and after

Run positions here are zero-based. Every history has 20 recorded runs.

| History | Recorded pattern | Old activity / new-flake exit | Corrected activity / new-flake exit |
|---|---|---|---|
| continuing_retries | Final failures at 0, 2, 4; recovered failures at 5 through 19 | quiet / 0 | ongoing / 0 |
| actually_quiet | Recovered failures at 0, 2, 4; otherwise ordinary passes | none / 0 | quiet / 0 |
| new_retries | Ordinary passes, then recovered failures at 15, 17, 19 | none / 0 | new / 1 |
| ambiguous_tail | Final failures at 0, 2, 4; ambiguous result at 19 | quiet / 0 | unavailable / 2 |

The new-flake exit is from `--fail-on-new-flake`; the separate `--fail-on-retry`
gate still detects any explicit recovery in the supplied history. The ordinary
report command continues to emit the available evidence for an ambiguous input.

[Before capture](results/before.json) at source revision
`466fab0` and [after capture](results/after.json) retain the exact selected CLI
fields, errors, exit codes and implementation hashes. Every final pass/fail count,
failure-rate interval, recovered count and exhausted count agrees between the
two captures. The replay script also writes complete JSON, Markdown, HTML and
terminal output to its work directory.

Activity now counts affected **runs**, not attempts: `failures` is the sum of
`final_failure_runs` and `recovered_runs`, and `basis` states
`runs_with_observed_failures`. The 15 recovered runs and 3 final failures above
produce 18 affected runs, even though the exhausted runs each had three failed
attempts. Final-outcome rates and same-commit comparisons keep their original
meaning. Named Go failures still use the names actually present in their final
failure output; parent retry evidence is not assigned to an inner test.

An explicitly ambiguous outcome can conceal a failure, so activity is withheld
for that test and its named inner tests. JSON explains this with
`activity_unavailable_reason: "ambiguous_outcomes"`; missing chronology has its
own reason. Counts and source records remain available. The new-flake gate
returns 2 when those ambiguous outcomes prevent a complete assessment.

## Reproduce

To recapture the real reporter files (Java 17+ and Maven required):

```bash
python studies/retry-activity/capture.py
```

The script expects the intentionally exhausted execution to fail, checks all
marker counts, and saves only the sanitized XML. To replay with an already
installed Flakemap package, from the repository root:

```bash
python studies/retry-activity/reproduce.py --work /tmp/retry-activity --out /tmp/retry-activity.json
node studies/retry-activity/check_reports.mjs /tmp/retry-activity /tmp/retry-activity-browser
```

The second command uses the repository's Playwright/axe development dependencies
and cached Chromium/Firefox. It checks actual reports offline at 375 and 1200
pixels, including keyboard expansion, retry source records, final counts,
activity labels, horizontal overflow, accessibility and network requests.

## Installation and browser verification

A clean `git archive` of `2abc9d0` passed `uv sync --locked`, `ruff check .`,
`ruff format --check .`, strict `mypy` (30 source files), all 366 tests and
`uv build` on Python 3.12.12. The resulting wheel was installed into fresh
environments on Python 3.12.12 and the minimum supported Python 3.10.21,
with only its required Rich dependencies. Imports came from `site-packages`.
All 30 package files matched the source, and the four scenarios' full JSON,
Markdown, HTML and terminal exports matched the source bytes on both runtimes.

The installed CLI also completed the README demo, top-ten, JSON, Markdown and
HTML commands, the shared-outage example and the TRX history. The existing
retry gate returned 1 and the incomplete-input gate returned 2 as expected.
[Wheel hash, output hashes and verification receipt](results/verification.json).

The wheel's actual HTML reports passed 16 offline scenarios in Chromium and
Firefox: four histories at 375 pixels in light mode and 1200 pixels in dark
mode. Keyboard expansion exposed the correct activity and original source
records; no page errors, HTTP requests, page-width overflow or axe violations
were observed. This is a focused report check, not exhaustive accessibility
certification. [Browser receipt](results/browser.json).

| Report capture | Chromium | Firefox |
|---|---|---|
| Continuing retries, desktop | [Full report](../../docs/assets/retry-activity-chromium-1200-continuing_retries.png) | [Full report](../../docs/assets/retry-activity-firefox-1200-continuing_retries.png) |
| Continuing retries, mobile | [Viewport at test detail](../../docs/assets/retry-activity-chromium-375-continuing_retries.png) | [Viewport at test detail](../../docs/assets/retry-activity-firefox-375-continuing_retries.png) |
| Newly recurring retries, desktop | [Full report](../../docs/assets/retry-activity-chromium-1200-new_retries.png) | [Full report](../../docs/assets/retry-activity-firefox-1200-new_retries.png) |

The captures were inspected: the activity explanation wraps within the narrow
viewport, and desktop reports retain every retry's source record. The long
evidence list requires scrolling. `uv run --locked python scripts/build_demo_site.py`
also rebuilt the existing five-page gallery into `site/`; its nine output files
matched the clean archive's build. The Kubernetes example is copied from its
previously committed static report, not regenerated from a new corpus replay.
Nothing was pushed, released or deployed.

## Limits

This repairs interpretation of recorded failures; it does not establish a cause,
prove a repair, or infer retries a reporter omitted. Quiet is the existing
descriptive rule, not a significance test. Skips and absent tests remain outside
the usable-run denominator, so its distances are counts of usable observations,
not elapsed time or all CI builds. Any ambiguous outcome in a test's history
currently withholds its activity rather than fitting only a selected suffix.
