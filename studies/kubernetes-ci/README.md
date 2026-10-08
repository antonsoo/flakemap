# 354 failures in 91 days: Kubernetes' CI history, and what it did to flakemap

Kubernetes publishes every build of every CI job: when it started, which commit
it built, whether it passed, and its JUnit report. Two of those jobs build
`master` about once an hour, the unit tests and the integration tests. This
study reads 91 days of both, 4,334 builds, straight from the public bucket and
runs flakemap over them. No Kubernetes code is run.

**What came out**

- **One build in thirteen failed, and every failure that could be checked was a
  flake.** 329 of the 4,334 builds failed (7.6%). The same commit is often built
  again an hour later, so most failures can be put to the direct test: did the
  same code pass? Of 314 failures on a commit built more than once, **310 passed
  in another build of that commit.** The other four are two commits, each built
  twice, where a known flake failed both times.
- **Flakes are episodes, not rates.** Sixteen tests failed five times or more.
  **Nine of them had already stopped** by the end of the window: `TestDRA`
  failed 19 times in ten days and then not once in the next 64. A failure rate
  over the 91 days describes a problem most of them no longer have.
- **Kubernetes' own tracker agrees about when.** For four of those nine a pull
  request that names the test merged between six hours and three days after the
  last failure flakemap saw. The newest flake it flagged, `TestCPGScheduling`,
  first failed on 4 October; its issue was opened on 5 October.
- **flakemap 0.3.7 could show none of this.** Its report of the unit job's
  history was a 687 MB HTML file. It gave every test one rate, printed as "1%"
  or "0%", and every failure message as the word "Failed". Its new-flake gate
  needs a 20-point jump in failure rate; the most frequent flake here fails two
  runs in a hundred.

![One row per frequently failing test, a tick per failed build over 91 days. Nine tests' ticks stop well before the end; for four of them a marker shows a fix merging just after the last tick.](figures/timeline-light.svg)

## The data

`collect.py` lists a job's builds in the `kubernetes-ci-logs` bucket and fetches,
for each, `started.json` (start time and commit), `finished.json` (result) and
the JUnit reports under `artifacts/`. [`manifest.json`](manifest.json) records
every build it found, with each report's size and MD5, as listed on
8 October 2026.

| | integration | unit |
|---|---:|---:|
| Job | `ci-kubernetes-integration-master` | `ci-kubernetes-unit` |
| Builds, 9 July to 8 October | 2,169 | 2,165 |
| failed | 162 | 167 |
| ended in Prow's `error` state, without a result | 4 | 12 |
| Builds with a JUnit report | 2,162 | 2,153 |
| Commits built | 550 | 549 |
| built more than once | 304 | 305 |
| Most builds of one commit | 116 | 115 |
| Records per report (Go packages) | 136 | 1,524 |
| Outcomes read | 284,101 | 3,202,568 |

Both jobs prune their reports: a Go package is one `<testcase>`, passing or
failing, and a failing package's record carries the output of the tests that
failed in it. So the unit of the report is the package, and the names of the
failing tests are in the failure text, on `go test`'s own `--- FAIL:` lines.

## Was it the code?

A periodic job builds whatever `master` is at when it starts. When nothing has
merged in the last hour it builds the same commit again, and over a release
freeze it builds one commit a hundred times. Each failure can then be compared
with the other builds of its commit, which is the ground truth the flaky-test
literature uses: the same code, run again.

| Package failures | integration | unit | both |
|---|---:|---:|---:|
| All | 178 | 176 | 354 |
| passed in another build of the same commit | 160 | 150 | 310 |
| failed in every build of the commit | 0 | 4 | 4 |
| the commit was built once | 18 | 22 | 40 |

The four that failed "every" time are two commits with two builds each.
`TestTimeTravelHealthcheck`, which failed 44 times in the window, failed both
builds of one commit on 14 July. And on 22 July one of the `TestComputePodActions`
tests failed in both builds of a commit, a different one of them each time,
during a twelve-hour burst that issue
[#140815](https://github.com/kubernetes/kubernetes/issues/140815) reported as a
flake and [#140821](https://github.com/kubernetes/kubernetes/pull/140821) fixed
the same day. None of the 354 is a test that broke and stayed broken.

Most failed builds have one cause: 306 of the 326 with a failing package had
exactly one, 19 had two, and one integration build lost ten packages at once.

## Which tests

The failures name 87 tests, 52 in the integration job and 35 in the unit job.
Forty of them failed once. The five that failed most account for 44% of the
integration job's named failures and 56% of the unit job's.

| Test | Job | Failed builds | Passed on the same commit | First | Last | flakemap |
|---|---|---:|---:|---|---|---|
| `TestTimeTravelHealthcheck` | unit | 44 | 41 of 43 | 9 Jul | 2 Sep | quiet |
| `TestWebhookConverterWithWatchCache` | integration | 20 | 19 of 19 | 22 Jul | 4 Oct | ongoing |
| `TestDRA` | integration | 19 | 18 of 18 | 25 Jul | 4 Aug | quiet |
| `TestWaitForAllPodsUnmount` | unit | 17 | 16 of 16 | 16 Jul | 1 Oct | ongoing |
| `TestPodGroupPreemption` | integration | 14 | 12 of 12 | 11 Jul | 15 Jul | quiet |
| `TestCoSchedulingWithPermitPlugin` | integration | 10 | 6 of 6 | 9 Jul | 20 Jul | quiet |
| `TestFullFlow` | unit | 10 | 9 of 9 | 15 Jul | 21 Jul | quiet |
| `TestBatchScenarios` | integration | 9 | 8 of 8 | 15 Jul | 29 Aug | quiet |
| `TestUnReservePreBindPlugins` | integration | 9 | 7 of 7 | 9 Jul | 21 Jul | quiet |
| `TestCheckBindings` | unit | 9 | 9 of 9 | 11 Jul | 1 Oct | ongoing |
| `TestReconstructedVolumeShouldUnmountSucceedAfterSetupFailed` | unit | 8 | 6 of 6 | 13 Jul | 31 Jul | quiet |
| `TestAsyncPreemptionFailure` | unit | 7 | 6 of 6 | 26 Jul | 26 Sep | ongoing |
| `Test_Run_OneVolumeDetachOnUnhealthyNodeWithForceDetachOnUnmountDisabled` | unit | 7 | 7 of 7 | 1 Aug | 21 Aug | quiet |
| `TestAsyncPreemption` | integration | 5 | 5 of 5 | 18 Aug | 27 Sep | ongoing |
| `TestControllerSyncPool` | unit | 5 | 5 of 5 | 10 Jul | 20 Sep | ongoing |
| `TestRatchetingFunctionality` | integration | 5 | 4 of 4 | 11 Aug | 27 Aug | ongoing |

"Passed on the same commit" counts, of a test's failures on a commit built more
than once, those where the package passed in another build of it.
[`results.json`](results.json) has all 87.

## When

A test's failures either keep coming or they stop, and the dates in that table
say which more plainly than any rate. flakemap now makes that call from where
the failures sit in the history. If a test fails at one steady rate, every
placement of its `k` failures among its `n` runs is equally likely, so the
chance that all of them fall before run `L` is `C(L, k) / C(n, k)`. When that
chance is under 1% for the run of the last failure, the test is **quiet**;
when the mirror-image chance for the first failure is under 1%, it is **new**.
Both are exact; nothing is fitted or simulated.
([`src/flakemap/stats/activity.py`](../../src/flakemap/stats/activity.py))

`TestDRA`: 19 failures, the last of them 1,538 runs before the end. The chance
of that from a steady flake is 5 in 10 billion. `TestControllerSyncPool`: 5
failures, the last 412 runs before the end. The chance of that is 35%, so it
stays "ongoing": five failures in three months cannot yet be told from a flake
that is merely due.

Of the sixteen tests, nine are quiet and seven ongoing. Two tests with fewer
failures are new: `TestCPGScheduling` (three failures, all in the last 81 runs
of 2,162; chance 1 in 20,000) and `TestCause` (four, all in the last 597 of
2,153; chance 0.6%).

## Against the tracker

`tracker.py` searches `kubernetes/kubernetes` for issues and pull requests that
mention each of the sixteen tests and saves what it finds, with dates, in
[`tracker.json`](tracker.json). That record was written by the people fixing
the flakes, and flakemap never sees it.

**The nine it calls quiet.**

| Test | Last failure seen | What the tracker records |
|---|---|---|
| `TestDRA` | 4 Aug, 10:25 | [#141060](https://github.com/kubernetes/kubernetes/pull/141060) "fix dra optional node operations podgroup flake" merged 4 Aug, 16:54 |
| `TestTimeTravelHealthcheck` | 2 Sep, 09:39 | [#140575](https://github.com/kubernetes/kubernetes/pull/140575) "deflake TestTimeTravelHealthcheck" merged 3 Sep, 17:52 |
| `TestFullFlow` | 21 Jul, 05:37 | [#140826](https://github.com/kubernetes/kubernetes/pull/140826), a revert of the change that sped the package's tests up, merged 23 Jul, 07:07 |
| `TestReconstructedVolume…SetupFailed` | 31 Jul, 11:55 | [#141062](https://github.com/kubernetes/kubernetes/pull/141062) "Wait for pending state to clear before triggering 2nd unmount" merged 3 Aug, 09:47 |
| `TestPodGroupPreemption` | 15 Jul, 14:26 | Issue [#140486](https://github.com/kubernetes/kubernetes/issues/140486) "[Flaky] TestPodGroupPreemption" closed 14 Jul; two more flake issues for the package closed 16 and 17 Jul |
| `TestCoSchedulingWithPermitPlugin` | 20 Jul, 04:13 | Issue [#140098](https://github.com/kubernetes/kubernetes/issues/140098), the package's flake report, closed 11 Aug |
| `TestUnReservePreBindPlugins` | 21 Jul, 04:34 | The same issue, #140098 |
| `TestBatchScenarios` | 29 Aug, 12:49 | Nothing that names it in a title or description |
| `Test_Run_OneVolumeDetach…Disabled` | 21 Aug, 20:23 | Nothing closed; one open pull request mentions it |

Four have a fix that names the test merging within three days of the last
failure. Three more are covered by a flake issue for their package that was
closed in the days or weeks after. The two with nothing are also the two
closest to the 1% line (0.6% each).

**The seven it calls ongoing.** Five have an issue or pull request that names
them and was still open on 8 October (`TestWebhookConverterWithWatchCache`
[#141909](https://github.com/kubernetes/kubernetes/issues/141909),
`TestWaitForAllPodsUnmount` [#136255](https://github.com/kubernetes/kubernetes/issues/136255),
`TestAsyncPreemption` [#142590](https://github.com/kubernetes/kubernetes/issues/142590),
`TestRatchetingFunctionality` [#137951](https://github.com/kubernetes/kubernetes/issues/137951),
`TestAsyncPreemptionFailure` [#142294](https://github.com/kubernetes/kubernetes/pull/142294)).
`TestControllerSyncPool`'s issue was closed on 21 September, the day after its
last failure: it may be fixed, and five failures are too few for the history to
say so yet. `TestCheckBindings` failed nine times, most recently on 1 October;
the tracker's only open mentions of it are a 2022 issue about the package's
tests running slowly and a comment on an unrelated pull request.

**The two it calls new.** `TestCPGScheduling` first failed in this job on
4 October at 20:17; issue [#142677](https://github.com/kubernetes/kubernetes/issues/142677),
"[Flaking Test] [sig-scheduling] TestCPGScheduling", was opened on 5 October.
`TestCause` has failed four times since 12 September. The search finds three
mentions of it, all from February 2024, when an earlier flake in it was fixed.

One thing the two records disagree on: `TestTimeTravelHealthcheck`'s issue,
[#140526](https://github.com/kubernetes/kubernetes/issues/140526), was still
open on 8 October, 850 builds after the test last failed here.

## What it did to flakemap

The released version read both histories without an error and classified the
same packages as flaky. What it made of them was not usable.

| On these histories | 0.3.7 | this checkout |
|---|---|---|
| HTML report, integration job (136 × 2,162) | 61.9 MB | 1.0 MB |
| HTML report, unit job (1,524 × 2,153) | 687 MB, 3 min 51 s, 3.3 GB of memory | 0.4 MB, 2 min 12 s, 1.2 GB |
| A test's failure rate in the table | "1% (1%–1%)", "0% (0%–1%)" | "0.93% (0.60%–1.4%)", and "20 of 2,162" |
| Which test failed | the package | the tests its output names, each with its own count |
| Failure message | "Failed", 354 times | the failing test's last log line, for 344 of them |
| Was it the code | a share of commits, one per test | per failure: passed, or failed, in the other builds of its commit |
| Still happening? | not said | new, ongoing or quiet, with the chance behind it |
| `--fail-on-new-flake` | needs a change point: a 20-point shift in failure rate. None in either history | also fires when a test's failures all sit at the end of the history |
| Runs without a sidecar | ordered by file modification time | ordered by the report's own `timestamp` when it carries an offset |

[`report-unit.html`](report-unit.html) is the page the checkout writes for the
unit job, as committed here; download it and open it in a browser.

What changed, in the order the data forced it:

- **The page.** A cell per test per run, each carrying its tooltip twice, is
  200 bytes a cell: fine for the 2,664 cells of the demo, 687 MB for three
  million. Past 300 runs a row is now a rail with a mark per failure, and past
  30 healthy tests they are listed by name instead of drawn.
- **The numbers.** Rates print with two significant digits near 0 and 100, and
  next to a count. Every flake here rounds to 0% or 1%.
- **The names.** A `--- FAIL:` line inside a failure names a Go test; a report
  that keeps one record per package names its failed tests nowhere else. Each
  named test gets its own count, same-commit evidence and activity. gotestsum
  gives every failure the message "Failed", so the message is now the last line
  the failing test logged from its own file: `plugins_test.go:2247: Didn't
  expect the first pod to be scheduled. error: context deadline exceeded`, ten
  times out of ten for `TestCoSchedulingWithPermitPlugin`. 344 of the 354
  failures have such a line or a `panic:`; the rest stay "Failed".
- **The evidence per failure.** Each failure records what the other runs of its
  commit did. The older rerun signal counted commits, so a test's score depended
  on how its failures were spread across commits built twice and commits built a
  hundred times; it is now the share of same-commit pairs of runs that disagree,
  weighted by runs. On histories with two runs per commit the two are equal.
- **Quiet and new**, as above, and the gate that uses them.
- **Two smaller ones.** One build had a report and no `started.json`; flakemap
  placed it by its file's modification time, the moment it was downloaded, and
  silently made the oldest build the newest. A report's own suite timestamp
  now orders such a run, and a history that mixes the two kinds of time says so.
  And a test that flaked once could never again be called broken, however long
  it then failed; only a disagreement since the change now counts against that.

## What this does not show

- **How flaky Kubernetes is.** These are two periodic jobs on `master`. The
  presubmit jobs that gate each pull request run the same tests far more often,
  on unmerged code, and are where a flake costs a contributor a retry.
- **That nothing broke.** A periodic job sees a regression only if it merges.
  Kubernetes' presubmits exist to stop that, and on this evidence they did.
- **Recall.** A test must fail in these jobs to be seen at all, and must fail
  about five times before its silence means anything. Forty tests failed once;
  nothing can be said about those.
- **Cause.** "Quiet" says the failures stopped. A fix, a revert, a deleted test
  and a renamed one look the same from here; the tracker comparison is there
  because the history alone cannot tell them apart.
- **Independence.** The 1% bound is for failures that arrive independently.
  Bursts make silence less surprising than the arithmetic says; consecutive
  failing runs are counted once for that reason, and clustered ones are not.
- **Other ecosystems.** Naming failed tests from the output is Go's `--- FAIL:`
  convention. Reports that keep a record per test need none of it.

## Reproduce

```sh
git clone https://github.com/antonsoo/flakemap && cd flakemap && uv sync
uv run python studies/kubernetes-ci/collect.py     # 1.4 GB into studies/kubernetes-ci/cache/
uv run python studies/kubernetes-ci/analyze.py     # results.json
uv run python studies/kubernetes-ci/tracker.py     # tracker.json, from GitHub's search API
uv run python studies/kubernetes-ci/figures.py     # figures/

# the report itself
uv run flakemap studies/kubernetes-ci/cache/ci-kubernetes-integration-master --html integration.html

# what 0.3.7 made of the same files (run from outside the checkout)
uvx --from 'flakemap==0.3.7' flakemap "$PWD/studies/kubernetes-ci/cache/ci-kubernetes-unit" \
    --json --html /tmp/flakemap-0.3.7/ci-kubernetes-unit.html > /tmp/flakemap-0.3.7/ci-kubernetes-unit.json
uv run python studies/kubernetes-ci/analyze.py --released /tmp/flakemap-0.3.7
```

`collect.py` fetches the builds the manifest lists. The bucket keeps about
three months, so the oldest of them will age out; `collect.py --rescan` lists
the jobs as they are now and rewrites the manifest, and the numbers move with
it. The tracker search is a snapshot too: issues close and titles change.

## References

- Lam, Oei, Shi, Marinov and Xie, "iDFlakies: A Framework for Detecting and
  Partially Classifying Flaky Tests", ICST 2019. Rerunning unchanged code as
  the test of flakiness.
- Luo, Hariri, Eloussi and Marinov, "An Empirical Analysis of Flaky Tests",
  FSE 2014.
- Kubernetes' CI results: <https://testgrid.k8s.io> and <https://prow.k8s.io>,
  both views of the `kubernetes-ci-logs` bucket this study reads.
