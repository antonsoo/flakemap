# Inspecting incomplete CI artifacts

These are **hand-authored, synthetic** reports, not captured runner output. They
isolate mistakes that are easy to miss in a large history:

| Run | Evidence | Expected treatment |
| --- | --- | --- |
| 00 | JUnit: a pass and a test taking 10 seconds | Two usable outcomes |
| 01 | Truncated JUnit: a closed failure, a retry recovery, XML examples in a comment and CDATA, an unfinished testcase | Keep the two completed records; ignore examples and the unfinished record; warn |
| 02 | TRX: a 14-second pass, a `Completed` result, a pass with `00:99:99` duration | Two usable outcomes, one unknown outcome, one unknown duration |

`C.sparseTiming` has two measurements across three supplied runs. Its slope is
`(14 - 10) / (2 - 0) = 2 seconds/history run`, not 4 seconds/measurement. The
missing middle observation is not zero. `C.qualitativeUnknown` has no usable
outcome and no failure-rate estimate. `C.unfinished` and `imaginary` are absent.
The failure message contains inert HTML as an escaping check.

```bash
uv run flakemap examples/incomplete_history --json --html /tmp/flakemap-incomplete.html
uv run flakemap examples/incomplete_history --json --fail-on-incomplete
```

The first command exits 0 and retains warnings; the second exits 2 with the same
JSON evidence. Other committed histories contain captured pytest, Surefire and
MSTest output; see [formats](../../docs/formats.md) for their provenance.
