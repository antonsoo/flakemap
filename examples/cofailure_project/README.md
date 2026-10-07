# Controlled shared-service failures

This capture demonstrates a concrete investigation: three tests fail during the
same service outages; another fails independently; a fifth has different coverage.
The HTTP requests, pytest execution and JUnit output are real. The outage schedule
and failing assertions are planted, not observed production incidents.

From the repository root:

```bash
uv run python examples/cofailure_project/capture.py scratch/new-cofailure-history
uv run flakemap scratch/new-cofailure-history --html scratch/shared.html --json
```

The destination must be new or empty. The script starts an HTTP server on an
ephemeral loopback port and stops it in a `finally` block. It runs pytest twelve
times with external plugins disabled, checks pytest's exit codes and parses the
XML independently before writing metadata. It does not rewrite the XML.

| Run(s) | Service | Additional behavior |
| --- | --- | --- |
| 04, 05, 10 | All requested endpoints return HTTP 503 | Optional check skipped in 04 and deselected in 10 |
| 07 | HTTP 200 | Independent math assertion fails |
| All other runs | HTTP 200 | All six tests pass |

There are 46 HTTP requests, ten of which return 503, and 71 reported testcases
across the twelve runs. The three consistently scheduled endpoint tests share
the same history: nine passes and failures in runs 04, 05 and 10. The optional
test fails only in run 05, with one skip and one absent result. It must not join
the three-test cohort. The healthy control never fails.

The committed [history](../cofailure_history/) includes original reports,
sidecars with actual capture timestamps, sequence and local environment, and a
capture manifest with the source hash, outcomes, exit codes and request log.
No fictitious commit IDs are assigned. Timestamps, durations, pytest headers
and host details may vary when recaptured; the specified outcomes must not.

See [matching rules and limits](../../docs/shared-outcomes.md). These fixture
tests intentionally fail under the controlled capture; ordinary project tests
are under the repository's top-level `tests/` directory.
