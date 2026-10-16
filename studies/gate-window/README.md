# Retired tests do not remain inside a recent-build gate

`--fail-on-new-flake --new-flake-window 10` previously failed on a test that had
not executed in the last **20 builds**. The onset gate used the number of that
test's usable executions since its first failure. Skips and absences compressed
that count while the CI history kept growing.

The corrected gate counts every supplied history run. Execution-based activity
rules and all observed outcomes retain their meaning. The source repair is now public.
[Pinned-file verification](results/public-source.json) compares the tested code
and receipts with GitHub. No PyPI release or hosted deployment is included.

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

## Clean package and report checks

A clean archive of `6aa738d` passed locked installation, Ruff, formatting,
strict mypy (30 source files), all **388 tests**, wheel/sdist builds and
`npm ci`. `uv run --locked python scripts/build_demo_site.py` rebuilt the
existing gallery into `site/`. Nothing was released or deployed.
The existing browser suite also passed all **112 offline report scenarios**
from that clean archive. [Complete browser receipt](results/browser-full.json).
The Kubernetes gallery page is copied from the existing committed report;
the separate corpus replay below re-reads the underlying XML.

The wheel was installed into fresh Python **3.10.21** and **3.14.7** environments,
with only its required dependencies. Imports came from `site-packages`; all
30 runtime files matched the clean source. Each installation passed 14 documented
CLI workflows and the four study scenarios, including the normal demo, JSON,
Markdown, HTML, TRX, shared failures, retry/incomplete gates and a widened
new-flake gate. [Artifact hash and command receipt](results/verification.json).
The four study scenarios retain byte-identical terminal, Markdown and HTML
exports before and after this repair; the JSON adds the explicit window fields.

The installed wheel's actual reports passed **16 offline scenarios** in
Chromium and Firefox, at 375 and 1200 pixels in both color schemes. Keyboard
expansion exposed all three failures, twenty absent/skipped cells and their
original run IDs. No page errors, HTTP requests, page-width overflow or axe
violations were observed. [Browser receipt](results/browser.json). All four
captures were inspected: narrow details wrap, and the wide failure table scrolls
inside the page. This is a focused check, not exhaustive accessibility validation.

| Actual report | Chromium | Firefox |
|---|---|---|
| Desktop, dark | [Capture](../../docs/assets/gate-window/chromium-1200.png) | [Capture](../../docs/assets/gate-window/firefox-1200.png) |
| Mobile, light | [Capture](../../docs/assets/gate-window/chromium-375.png) | [Capture](../../docs/assets/gate-window/firefox-375.png) |

To repeat those browser checks with the repository's development dependencies:

```bash
node studies/gate-window/check_reports.mjs /tmp/gate-window-replay /tmp/gate-window-browser
```

## Retained public corpus replay

The earlier Kubernetes corpus was re-read from its actual cached files. All
**10,774 XML files** matched the sizes and MD5 values in that study's manifest,
with no listed report missing from the cache. This is a replay of the retained
8 October capture, not a fresh download or a claim about current Kubernetes CI.
[Input verification](results/corpus-inputs.json).

The [baseline](results/corpus-before.json) and [corrected](results/corpus-after.json)
each analyzed 4,315 reported runs and 3,486,669 usable test-run observations.
Every pre-existing JSON field has the same canonical hash in both versions.
Candidate sets for windows 10, 30 and 100 also agree: this corpus does not supply
an additional observed false-alert case. The controlled retirement capture above
establishes the bug; the public replay checks that existing evidence survives.
Warnings and unavailable states are retained in the receipts rather than
silently treated as successful coverage. Replay with:

```bash
uv run --locked python studies/gate-window/audit_corpus.py studies/kubernetes-ci --out /tmp/gate-window-corpus.json
```

This correction does not establish why a test is absent, prove it was fixed,
infer unreported outcomes, or change failure-rate denominators. A passing gate
means no supported new onset was detected in the specified supplied window;
missing test coverage does not establish health. Activity distances continue
to count usable executions. Invalid chronology and ambiguous observations keep
their existing unavailable assessments and gate exit 2.
