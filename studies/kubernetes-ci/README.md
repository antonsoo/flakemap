# 354 failures in 91 days: Kubernetes' CI history, and what it did to flakemap

Kubernetes publishes every build of every CI job: when it started, which commit
it built, whether it passed, and its JUnit report. Two of those jobs build
`master` about once an hour, the unit tests and the integration tests. This
study reads 91 days of both, 4,334 builds, straight from the public bucket and
runs flakemap over them. No Kubernetes code is run.

**What came out**

- **One build in thirteen failed, and nearly every failure that could be
  checked passed on the same commit.** 329 of the 4,334 builds failed (7.6%),
  with 354 package failures between them. The same commit is often built again
  an hour later, so 314 of those could be compared with another build of the
  same code, and **310 passed there.** The failure does not follow from the
  commit. Whether the test or the machine was at fault, this cannot say.
- **A rate hides when.** Sixteen tests failed five times or more. For ten of
  them the failures sit in a stretch that ended weeks before the window did:
  `TestDRA` failed 19 times between 25 July and 4 August and not once in the
  1,538 builds after. A failure rate over the 91 days gives each of these the
  same kind of number as a test that failed last week.
- **Kubernetes' own tracker has a fix at the right moment for three of the
  ten.** A pull request naming the test merged between six hours and three
  days after its last failure. For a fourth, the fix was a revert that merged
  when the test had already been silent longer than it had ever been between
  failures. For the others the tracker has a closed issue for the package,
  nothing, or an issue that is still open.
- **flakemap first answered "when" with odds, and they did not survive
  review.** They assumed failures arrive independently, in a study whose point
  is that they arrive in bursts. The labels now rest on a rule a reader can
  check on the timeline: quiet means silent for three times the longest gap
  there has been between failures. No probability is printed.
- **flakemap 0.3.7 could show none of this.** Its report of the unit job's
  history was a 687 MB HTML file. It gave every test one rate, and every
  failure message was the word "Failed". Its new-flake gate needs a 20-point
  jump in failure rate; the most frequent flake here fails two runs in a
  hundred.

![One row per frequently failing test, a tick per failed build over 91 days. Ten tests' ticks stop well before the end; for three of them a marker shows a pull request naming the test merging just after the last tick.](figures/timeline-light.svg)

All times in this study are UTC.

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
with the other builds of its commit, which is the test the flaky-test
literature uses: the same code, run again. It shows that a failure is not
determined by the commit. It does not separate a flaky test from a flaky
machine: two builds of one commit also differ in node, load and hour.

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
during a fifteen-hour burst that issue
[#140815](https://github.com/kubernetes/kubernetes/issues/140815) reported as a
flake and [#140821](https://github.com/kubernetes/kubernetes/pull/140821) fixed
the same day. None of the 354 package failures is a test that broke and stayed
broken.

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
| `TestRatchetingFunctionality` | integration | 5 | 4 of 4 | 11 Aug | 27 Aug | quiet |

"Passed on the same commit" counts, of a test's failures on a commit built more
than once, those where the package passed in another build of it.
[`results.json`](results.json) has all 87.

## When

A test's failures either keep coming or they stop, and the dates in that table
say which more plainly than any rate. flakemap makes the call with a rule that
uses nothing but the timeline. Consecutive failing runs are one event. A test
is **quiet** when it has at least three events and the runs since the last one
are at least three times the longest gap there has been between two of them,
and at least ten: it has now been quiet three times longer than it ever was
while it was failing.
([`src/flakemap/stats/activity.py`](../../src/flakemap/stats/activity.py))

| Test | Failed builds | Events | Longest gap between failures | Silent since the last | Ratio | |
|---|---:|---:|---:|---:|---:|---|
| `TestTimeTravelHealthcheck` | 44 | 39 | 125 runs, 5.3 days | 850 runs, 35.8 days | 6.8 | quiet |
| `TestWebhookConverterWithWatchCache` | 20 | 20 | 571 runs, 24.0 days | 88 runs, 3.7 days | 0.2 | ongoing |
| `TestDRA` | 19 | 17 | 33 runs, 1.4 days | 1,538 runs, 64.8 days | 46.6 | quiet |
| `TestWaitForAllPodsUnmount` | 17 | 16 | 462 runs, 19.5 days | 152 runs, 6.4 days | 0.3 | ongoing |
| `TestPodGroupPreemption` | 14 | 12 | 34 runs, 1.5 days | 2,007 runs, 84.6 days | 59.0 | quiet |
| `TestCoSchedulingWithPermitPlugin` | 10 | 10 | 67 runs, 2.9 days | 1,899 runs, 80.0 days | 28.3 | quiet |
| `TestFullFlow` | 10 | 10 | 35 runs, 1.5 days | 1,865 runs, 79.0 days | 53.3 | quiet |
| `TestBatchScenarios` | 9 | 9 | 201 runs, 8.6 days | 944 runs, 39.7 days | 4.7 | quiet |
| `TestUnReservePreBindPlugins` | 9 | 9 | 59 runs, 2.6 days | 1,876 runs, 79.0 days | 31.8 | quiet |
| `TestCheckBindings` | 9 | 9 | 1,037 runs, 43.9 days | 150 runs, 6.3 days | 0.1 | ongoing |
| `TestReconstructedVolume…SetupFailed` | 8 | 8 | 109 runs, 4.7 days | 1,622 runs, 68.7 days | 14.9 | quiet |
| `Test_Run_OneVolumeDetach…Disabled` | 7 | 7 | 176 runs, 7.6 days | 1,124 runs, 47.3 days | 6.4 | quiet |
| `TestAsyncPreemptionFailure` | 7 | 7 | 516 runs, 21.8 days | 289 runs, 12.1 days | 0.6 | ongoing |
| `TestRatchetingFunctionality` | 5 | 5 | 205 runs, 8.7 days | 989 runs, 41.5 days | 4.8 | quiet |
| `TestAsyncPreemption` | 5 | 5 | 532 runs, 22.4 days | 261 runs, 11.0 days | 0.5 | ongoing |
| `TestControllerSyncPool` | 5 | 5 | 616 runs, 26.1 days | 412 runs, 17.3 days | 0.7 | ongoing |

Ten are quiet and six ongoing. The two groups are not close: every quiet test
has been silent between 4.7 and 59 times its longest gap, and every ongoing one
for less than its longest gap.

What the label claims is that the burst is over. It does not claim the test
cannot fail again, or why it stopped. A flake that returns every few weeks has
those weeks on record as its longest gap, and needs a silence three times as
long before it is called quiet; `TestCheckBindings` went 44 days between two
failures in this window and will not be called quiet for months.

**New** is the mirror image, a clean stretch before the first failure three
times the longest gap since, and it is only given to a test whose passing runs
the history records. These reports record a package, not a test: the name of a
Go test appears only when it fails. So for a named test flakemap says when it
first failed and nothing more. Two first failed in the last 30 days and failed
three times or more: `TestCPGScheduling`, three failures within thirteen hours
on 4 and 5 October, and `TestCause`, four since 12 September.

The rule has a known error rate in one case only. For a steady flake, one that
fails independently at a constant rate, the chance that the open silence is at
least 3 times the longest of `n` earlier gaps is `n! / (4 × 5 × … × (n + 3))`:
10% with three events, 5% with four, under 1% from eight. A test in
`tests/test_long_histories.py` checks that by simulation. Nothing of the kind
is claimed for failures that cluster, which these do, and so no probability
appears in any report.

An earlier version of this study gave odds instead ("5 in 10 billion" for
`TestDRA`), from the chance that a steady flake's failures would all fall so
early. Those odds assumed independent failures in the same breath as arguing
that failures come in episodes; counted as episodes, most of them were not
significant at all. They are gone.

## Against the tracker

`tracker.py` searches `kubernetes/kubernetes` for issues and pull requests that
mention each of the sixteen tests, and the two that first failed recently, and
saves what it finds, with dates, in [`tracker.json`](tracker.json). That record
was written by the people fixing the flakes, and flakemap never sees it.

**The ten it calls quiet.**

| Test | Last failure seen | What the tracker records |
|---|---|---|
| `TestDRA` | 4 Aug, 10:25 | [#141060](https://github.com/kubernetes/kubernetes/pull/141060) "test/integration: fix dra optional node operations podgroup flake" merged 4 Aug, 16:54 |
| `TestTimeTravelHealthcheck` | 2 Sep, 09:39 | [#140575](https://github.com/kubernetes/kubernetes/pull/140575) "apiserver: deflake TestTimeTravelHealthcheck" merged 3 Sep, 17:52 |
| `TestReconstructedVolume…SetupFailed` | 31 Jul, 11:55 | [#141062](https://github.com/kubernetes/kubernetes/pull/141062) "Wait for pending state to clear before triggering 2nd unmount" merged 3 Aug, 09:47 |
| `TestFullFlow` | 21 Jul, 05:37 | [#140826](https://github.com/kubernetes/kubernetes/pull/140826), a revert of the change that sped the package's tests up, opened 22 Jul and merged 23 Jul, 07:07 |
| `TestPodGroupPreemption` | 15 Jul, 14:26 | Issue [#140486](https://github.com/kubernetes/kubernetes/issues/140486) "[Flaky] TestPodGroupPreemption" was closed on 14 Jul, the day before; two more flake issues for the package closed on 16 and 17 Jul. An issue for one of its subtests, [#141794](https://github.com/kubernetes/kubernetes/issues/141794), was opened on 2 Sep and is open |
| `TestCoSchedulingWithPermitPlugin` | 20 Jul, 04:13 | Issue [#140098](https://github.com/kubernetes/kubernetes/issues/140098), the package's flake report, closed 11 Aug |
| `TestUnReservePreBindPlugins` | 21 Jul, 04:34 | The same issue, #140098 |
| `TestRatchetingFunctionality` | 27 Aug, 15:37 | Issue [#137951](https://github.com/kubernetes/kubernetes/issues/137951) names it and was still open on 8 October |
| `TestBatchScenarios` | 29 Aug, 12:49 | Nothing that names it in a title or description |
| `Test_Run_OneVolumeDetach…Disabled` | 21 Aug, 20:23 | Nothing recent; one open pull request mentions it |

For three, a pull request that names the test merged after the last failure and
within the test's own longest gap: six hours, 1.3 days and 2.9 days later. Those
are fixes that could explain the stop. `TestFullFlow`'s revert merged 2.1 days
after its last failure, when the test had already been silent longer than its
longest gap of 1.5 days: the failures stopped before the revert landed. Two
more are covered by a flake issue for their package that was closed three weeks
after they stopped. For the other four the tracker either says nothing or
disagrees: two have issues that are still open, though this job has not seen
either test fail since the dates above.

**The six it calls ongoing.** Four have an issue or pull request that names
them and was still open on 8 October (`TestWebhookConverterWithWatchCache`
[#141909](https://github.com/kubernetes/kubernetes/issues/141909),
`TestWaitForAllPodsUnmount` [#136255](https://github.com/kubernetes/kubernetes/issues/136255),
`TestAsyncPreemption` [#142590](https://github.com/kubernetes/kubernetes/issues/142590),
`TestAsyncPreemptionFailure` [#142294](https://github.com/kubernetes/kubernetes/pull/142294)).
`TestControllerSyncPool`'s issue was closed on 21 September, the day after its
last failure: it may be fixed, and five failures spread over ten weeks are too
few for the timeline to say so. `TestCheckBindings` failed nine times, most
recently on 1 October; the tracker's open mentions of it are a 2022 issue about
the package's tests running slowly and a comment on an open pull request,
[#141672](https://github.com/kubernetes/kubernetes/pull/141672), that reports
reproducing the flake. No issue names it.

**The two that first failed recently.** `TestCPGScheduling` first failed in
this job on 4 October at 20:17. Issue [#142677](https://github.com/kubernetes/kubernetes/issues/142677),
"[Flaking Test] [sig-scheduling] TestCPGScheduling", was opened on 5 October,
and it says the test has been flaking since 28 September, "the same day #140670
merged, which added these tests", mostly on another architecture's job. So this
is a test that was flaky from the day it existed, and nothing in a history that
names tests only when they fail could tell that from an old test that had just
turned flaky. It is also where the quiet rule is at its weakest: three failures
in thirteen hours and 67 clean runs since make it quiet by the rule, with the
minimum three events, while its issue is open and a fix is under review.
`TestCause` has failed four times since 12 September. The search finds three
mentions of it, all from February 2024, when an earlier flake in it was fixed.

One more place the two records disagree: `TestTimeTravelHealthcheck`'s issue,
[#140526](https://github.com/kubernetes/kubernetes/issues/140526), was still
open on 8 October, 850 builds after the test last failed here.

## What it did to flakemap

The released version read both histories without an error and classified the
same packages as flaky. What it made of them was not usable.

| On these histories | 0.3.7 | this checkout |
|---|---|---|
| HTML report, integration job (136 × 2,162) | 61.9 MB | 1.0 MB |
| HTML report, unit job (1,524 × 2,153) | 687 MB | 0.4 MB |
| A test's failure rate in the table | "1% (1%–1%)", "0% (0%–1%)" | "0.93% (0.60%–1.4%)", and "20 of 2,162" |
| Which test failed | the package | the tests its output names, each with its own count |
| Failure message | "Failed", 354 times | the failing test's last log line, for 344 of them |
| Was it the code | a share of commits, one per test | per failure: passed, or failed, in the other builds of its commit |
| Still happening? | not said | new, ongoing or quiet, by a rule on the timeline, with the gap and the silence it rests on |
| `--fail-on-new-flake` | needs a change point: a 20-point shift in failure rate. None in either history | also fires for a test that starts failing after a long clean stretch, and for a test named in failure output that first failed inside the window and failed more than once |
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
- **Recall.** A test must fail in these jobs to be seen at all, and on three
  separate occasions before the rule will call it anything. Forty tests failed
  once; nothing can be said about those.
- **Cause.** "Quiet" says the failures stopped. A fix, a revert, a deleted test
  and a renamed one look the same from here; the tracker comparison is there
  because the history alone cannot tell them apart.
- **That a quiet test is fixed.** The rule says a burst is over. With one
  burst on record, nothing says whether another will come; the three tests
  with a fix merged at the right moment are the only ones where there is a
  reason to think not.
- **A flaky test from a flaky machine.** Passing on the same commit rules out
  the commit, not the node the build ran on.
- **A new test from a newly flaky one**, wherever the report names a test only
  when it fails.
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
