# Retired tests do not remain inside a recent-build gate

`--fail-on-new-flake --new-flake-window 10` previously failed on a test that had
not executed in the last **20 builds**. The onset gate used the number of that
test's usable executions since its first failure. Skips and absences compressed
that count while the CI history kept growing.

The corrected gate counts every supplied history run. Execution-based activity
rules and all observed outcomes retain their meaning. This is a local source
repair, with no PyPI release or hosted deployment.

## Captured runner history

[`capture.py`](capture.py) executed the included
[pytest input](project/test_history.py) **56 separate times**, on Python 3.12.12
and pytest 9.1.1 under Linux/WSL2. A control test always passes. Two tests fail
deliberately in builds 30, 32 and 34. After build 35, one is deselected and the
other skips. These are controlled executions, not production failures or an
estimate of real-world flakiness.

```text
Build positions: 0........29  30 31 32 33 34 35  36........55
Removed test:    pass....... F  P  F  P  F  P   absent.......
Skipped test:    pass....... F  P  F  P  F  P   skipped......
Control test:    pass......................................
                                            last 10: 46..55
```

The [capture receipt](fixtures/history/capture.json) records reporter versions,
native exit codes and per-report hashes. The XML retains every outcome, counter,
duration and timestamp. Only the absolute repository path prefix in skip text
was removed; both raw and retained XML hashes are recorded. Console captures
also abbreviate the output location. `meta.json` sidecars add explicit capture
sequence numbers; they do not alter reporter outcomes.

Each affected test has 36 executions and three failures. Its activity still says
`new`: the first failure follows 30 passing executions, with three failure events
and one clean execution between events. Its first failure is six **executions**
from the end of its observations, but 26 **builds** from the end of the history.
`new` describes that onset pattern; it does not alone place it in the CI window.

## Before and after

Positions are zero-based. A trailing window of N includes positions
`[total_runs - N, total_runs)`, so build 30 enters this history at N = 26.

| Input and window | First failure in window? | Before exit | Corrected exit |
|---|---|---:|---:|
| All 56 builds, last 10 | No: window starts at 46 | 1 | 0 |
| All 56 builds, last 25 | No: window starts at 31 | 1 | 0 |
| All 56 builds, last 26 | Yes: window starts at 30 | 1 | 1 |
| Original prefix through build 35, last 10 | Yes: window starts at 26 | 1 | 1 |

The [before receipt](results/before.json) was replayed from source `3b0eecd`;
the [after receipt](results/after.json) records the corrected implementation's
hashes. Both commands also use `--fail-on-incomplete`: every report reconciles
and no input/ordering warnings occur. Final counts, failure-rate intervals and
activity decisions agree between the versions. The JSON now names the usable
execution axis and exposes `first_failure_run_id` and
`history_runs_since_first_failure` separately.

Focused regressions also exercise missing and skipped tails with recovered
Surefire markers and names inside Go-style package failures, the inclusive
window boundary, genuinely recent failures, a name whose onset differs from
its parent, and unavailable chronology. Those are explicitly constructed
parser/analysis controls; they are not new Surefire or Go captures. Existing
change-point, ambiguous-input and retry-activity controls remain in the suite.

## Reproduce

After installing this checkout, replay the retained reports:

```bash
python studies/gate-window/reproduce.py --work /tmp/gate-window-replay --out /tmp/gate-window.json
```

The script writes full JSON, terminal, Markdown and standalone HTML exports.
To capture new actual pytest reports, use an empty output directory:

```bash
uv run --locked python studies/gate-window/capture.py /tmp/gate-window-capture
```

Supply `--history /tmp/gate-window-capture` to replay those reports. Native
timestamps and durations will differ. Historical before/after receipts identify
the original retained capture rather than promising identical new bytes.

This correction does not establish why a test is absent, prove it was fixed,
infer unreported outcomes, or change failure-rate denominators. A passing gate
means no supported new onset was detected in the specified supplied window;
missing test coverage does not establish health. Activity distances continue
to count usable executions. Invalid chronology and ambiguous observations keep
their existing unavailable assessments and gate exit 2.
