# A green result with failed attempts

This is a controlled Java test suite for checking actual Maven Surefire retry
output. It is intentionally not a production benchmark. The source forces two
recoveries, two exhausted retries, an ordinary pass and a skip.

```bash
mvn -f examples/retry_project/pom.xml test
uv run python examples/retry_project/capture.py
uv run flakemap examples/retry_history --html retry-report.html
```

The Maven command **must fail**: `alwaysFails` and `alwaysErrors` exhaust their
two retries. Run the subsequent commands separately, rather than chaining them
with `&&`. The capture script checks the expected marker counts before writing
the fixture. It removes `<properties>` (machine paths/environment information)
and retains outcomes, attempt messages and timings. `meta.json` supplies a
synthetic sequence label for this one real test execution.

Captured on 2026-09-29 using Maven 3.9.11, Surefire 3.5.4, JUnit 4.13.2 and
Temurin OpenJDK 25.0.4.1 on Linux/WSL2. Tool versions are pinned in the POM where
applicable. Java 17+ and Maven are needed only to regenerate the fixture, not to
run Flakemap or its Python tests.

Surefire's console summary from that run:

```text
Tests run: 6, Failures: 1, Errors: 1, Skipped: 1, Flakes: 2
```

Its XML has a `tests="13"` counter but only six `<testcase>` elements; failed
attempts contribute to that counter. This is why Flakemap reads the individual
testcase/retry records rather than treating suite totals as independent samples.

| Test | Failed records | Additional result | Flakemap classification |
|---|---|---|---|
| `recoversAfterTwoFailures` | 2 `flakyFailure` | pass | flaky: explicit recovery |
| `recoversFromError` | 1 `flakyError` | pass | flaky: explicit recovery |
| `alwaysFails` | 1 `failure` + 2 `rerunFailure` | no pass | insufficient data: one run |
| `alwaysErrors` | 1 `error` + 2 `rerunError` | no pass | insufficient data: one run |
| `alwaysPasses` | none | pass | insufficient data: one run |
| `skipped` | none | skipped | insufficient data: no executed outcomes |

This validates reporter compatibility. It does not validate a long-term
flakiness probability, distinguish infrastructure from application failures, or
prove how other test runners serialize retries.
