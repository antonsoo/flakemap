# Investigating tests that fail together

Three endpoint tests can fail during the same service outage while a fourth test
fails for an unrelated reason. Ranking each test independently hides that useful
distinction. Flakemap groups **identical observed outcome histories** and retains
the run IDs and source records needed to investigate them.

This feature is in the source checkout. It does not change classifications,
failure rates, flakiness scores or CI exit-code policy.

```bash
uv run flakemap examples/cofailure_history
uv run flakemap examples/cofailure_history --html shared.html --json > shared.json
uv run flakemap examples/cofailure_history --markdown > shared.md
```

The [included capture](../examples/cofailure_project/README.md) runs actual
pytest tests against a loopback HTTP server. Its failures are deliberately
controlled; it is not production reliability data.

| Tests | Evidence across 12 runs | Grouped? |
| --- | --- | --- |
| Inventory, pricing, shipping | HTTP 503 failures in runs 04, 05 and 10; pass in the other nine | One three-test cohort |
| Optional endpoint | Skipped in 04, fails in 05, absent in 10 | No; coverage differs |
| Independent math assertion | Fails in 07 | No; failure positions differ |
| Healthy control | Always passes | No failure or retry signal |

The cohort contains nine affected test-runs, not nine independent incidents.
Open it to see the matching history, members, runner/OS, commit when supplied,
report paths, 1-based result ordinals and failure messages. Member links move
keyboard focus to each test's disclosure. The evidence table scrolls horizontally
on narrow screens. The report needs no script, server or network connection.

## Exact matching rules

A cohort needs at least two tests and at least one final failure or recovered
retry. Every position in the supplied history must agree:

| State | Meaning |
| --- | --- |
| `pass` | Final pass with no explicit failed retry attempts |
| `failed` | Final fail or error without exhausted-retry evidence |
| `recovered` | Final pass after explicitly reported failed attempts |
| `exhausted` | Final fail or error with explicit exhausted retries |
| `skip` | A reported skipped result |
| `absent` | No result for this test in that supplied run |

Any ambiguous observation excludes the **entire test** from grouping; matching
unknown positions are not evidence of agreement. Duplicated test identifiers,
conflicting shard metadata and dotted-identity collisions use the same
normalization as the individual statistics. Their original records remain in
the individual-test evidence, and the group export lists excluded test names.

Fail and error share a grouping state, but the original status is retained in
evidence. Messages, durations, retry-attempt counts and test order within XML do
not define a group. Two recovered tests with two versus three attempts can match;
those attempt counts remain visible and never increase affected test-run counts.
Run positions, not equal failure percentages, define agreement. Same-commit runs
remain distinct runs. The caller's history window determines the grouping.

Cohorts are ordered by affected test-runs, then member count, then member names.
IDs such as `cohort-1` are local report identifiers, not persistent incident IDs.
Each test belongs to at most one cohort. Hashing sparse observed histories avoids
a test-by-test pairwise comparison; absent positions are explicit in the output.

## Evidence and limits

Terminal and Markdown show up to five cohorts, three member names per cohort
and five run IDs per outcome column. HTML shows up to 20 cohorts, 20 members,
40 affected test-runs per cohort and 20 run IDs per state. Text and retry-attempt
lists are previewed with visible omission notices. These limits apply to the new
inspector, not the pre-existing whole-history heatmap or individual test panels.

The HTML **Download all shared-outcome evidence** link contains every cohort,
member, run state and affected source record, including records omitted from
previews. Its JSON envelope has `schema_version: 1`, `input_complete`, `warnings`
and the same `cofailure` object as the CLI's schema-version-2 JSON. It includes
run metadata and all parsed failure/retry records for affected observations.
It does not bundle original XML bytes or expand message text beyond what the
parser already retains. Ordinary passes, skips and absences appear as run-state
lists. Keep source artifacts for a deeper audit.

Exact agreement is a lead, **not a common-cause finding or a statistical
correlation estimate**. Two tests failing once together are a valid shared
observation, but weak evidence for any broader conclusion. This method can miss
related tests that have one additional failure, different scheduling coverage,
or partially overlapping histories. It intentionally does not merge overlapping
groups, infer missing passes, estimate incident probabilities or nominate a root
cause. Warning-free input cannot establish that every CI artifact was collected.

To compare the next piece of evidence, inspect the original failing-run logs
against successful runs, for example with
[Logdelta](https://github.com/antonsoo/logdelta). Flakemap does not fetch those logs.
