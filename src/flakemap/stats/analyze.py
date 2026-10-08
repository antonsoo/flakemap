"""Per-test flakiness statistics: the analysis flakemap's outputs all read from.

This module turns an ordered list of `Run` into one `TestStats` per test. See
`docs/formats.md` and the README's "How it works" section for the reasoning
behind each formula; docstrings here give the short version and the exact
arithmetic.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from flakemap.models import Run, Status, run_sort_key
from flakemap.observations import Observation, history_observations
from flakemap.stats.activity import Activity, assess
from flakemap.stats.changepoint import ChangePoint, detect_change_point
from flakemap.stats.cofailure import CoFailureAnalysis, group_failures
from flakemap.stats.correlation import GroupRate, group_failure_rates, linear_trend, point_biserial
from flakemap.stats.wilson import Interval, wilson_interval

MIN_SAMPLES_FOR_SCORE = 5

# Flakiness score weights: flip rate and the same-commit rerun signal are the
# direct evidence of non-determinism (the test disagreed with itself on
# identical code); intermittency is a softer signal (the failure rate sits away
# from 0 or 1) that alone doesn't distinguish flaky from "just introduced a
# 30%-reproducible bug", hence its smaller weight.
W_FLIP = 0.4
W_RERUN = 0.4
W_INTERMITTENCY = 0.2

_MSG_NORMALIZE_RE = re.compile(r"\d+")


@dataclass(frozen=True, slots=True)
class MessageCluster:
    representative: str
    count: int


SameCommit = Literal["passed", "failed", "single", "unknown"]


@dataclass(frozen=True, slots=True)
class FailureEvidence:
    """One final failure, and what the rest of the history says about it."""

    run_id: str
    index: int
    """Position of the run among this test's usable runs, from 0."""
    timestamp: datetime | None
    commit: str | None
    status: Status
    message: str | None
    failed_within: tuple[str, ...]
    same_commit: SameCommit
    """What this test did in the other runs of the same commit, branch, runner and OS:
    ``passed`` in at least one of them (the failure did not reproduce on identical
    code), ``failed`` in all of them, ``single`` when there is no other run, and
    ``unknown`` when the run records no commit."""
    same_commit_runs: int
    """Other usable runs of this test in that context."""
    failed_with: int
    """Other tests with a final failure in the same run."""


@dataclass(frozen=True, slots=True)
class NamedFailure:
    """A test the runner's output names as failed inside a rolled-up testcase."""

    name: str
    runs: int
    """Runs in which the testcase's failure names this test."""
    first_run_id: str
    last_run_id: str
    passed_same_commit: int
    """Of those runs, the ones whose commit has another run in which the testcase passed."""
    checked: int
    """Of those runs, the ones whose commit has any other usable run."""
    activity: Activity


@dataclass(slots=True)
class TestStats:
    full_name: str
    suite: str
    n: int
    """Observations counted toward rates (pass + fail + error; skips excluded)."""
    n_pass: int
    n_fail: int
    n_skip: int
    failure_rate: Interval
    flip_rate: float
    rerun_commits_total: int
    rerun_commits_flaky: int
    rerun_signal: float
    flakiness_score: float
    classification: str
    change_point: ChangePoint | None
    change_point_run_id: str | None
    change_point_commit: str | None
    duration_trend: float | None
    duration_n: int
    duration_failure_correlation: float | None
    runner_rates: list[GroupRate]
    os_rates: list[GroupRate]
    message_clusters: list[MessageCluster]
    first_seen: datetime | None
    last_seen: datetime | None
    last_status: Status
    runs_since_change: int | None
    """Runs in the supplied history from the change point through its end,
    including runs where this test is skipped or absent. `None` without a change."""
    n_unknown: int
    flip_pairs: int
    recovered_runs: int
    exhausted_runs: int
    retry_observations: list[Observation]
    excluded_observations: list[Observation]
    failures: list[FailureEvidence] = field(default_factory=list)
    """Every final failure, oldest first."""
    activity: Activity | None = None
    """Where the failures fall in the history; None for a test that never failed."""
    named_failures: list[NamedFailure] = field(default_factory=list)
    """Top-level tests named inside this testcase's failures, most frequent first."""

    @property
    def failures_passed_same_commit(self) -> int:
        return sum(f.same_commit == "passed" for f in self.failures)

    @property
    def failures_repeated_same_commit(self) -> int:
        return sum(f.same_commit == "failed" for f in self.failures)

    @property
    def failures_checked(self) -> int:
        """Failures with another run of the same commit to compare against."""
        return self.failures_passed_same_commit + self.failures_repeated_same_commit


@dataclass(slots=True)
class AnalysisResult:
    tests: list[TestStats]
    total_runs: int
    run_id_range: tuple[str, str] | None
    timestamp_range: tuple[datetime, datetime] | None
    mtime_fallback_warning: str | None
    warnings: list[str]
    cofailure: CoFailureAnalysis = field(default_factory=CoFailureAnalysis)
    observations: dict[str, list[Observation]] = field(default_factory=dict, repr=False)
    """Each test's normalized observations, oldest first, as the statistics read them."""


def _classify(
    n: int,
    failure_point: float,
    flip_rate: float,
    rerun_signal: float,
    change_point: ChangePoint | None,
    disagrees_after_change: bool = False,
) -> str:
    if n < MIN_SAMPLES_FOR_SCORE:
        return "insufficient_data"
    if failure_point == 0.0 and flip_rate == 0.0 and rerun_signal == 0.0:
        return "healthy"
    # A significant change point into mostly failing is a regression, so it is checked
    # before the flip rate: in a short history the one pass-to-fail switch alone pushes
    # the flip rate over the flaky threshold (1 flip in 12 runs is 0.09). Only a rerun
    # that disagrees since the change speaks against it: over months, most tests have
    # flaked once, and that must not stop one from ever being called broken.
    if change_point is not None and change_point.rate_after >= 0.75 and not disagrees_after_change:
        return "broken"
    if flip_rate > 0.08 or rerun_signal > 0.0:
        return "flaky"
    if failure_point >= 0.6:
        return "broken"
    if failure_point > 0.0:
        return "flaky"
    return "healthy"


def _rerun_disagreement(groups: list[list[int]]) -> float:
    """The chance that two runs of the same commit disagree, over commits run 2+ times.

    Within a commit run ``m`` times with ``f`` failures, ``f * (m - f)`` of its
    ``m * (m - 1) / 2`` pairs of runs disagree. Commits are weighted by their runs, so
    one built a hundred times counts a hundred runs' worth, not ten thousand pairs' and
    not, as a plain share of commits would have it, the same as one built twice. For a
    test that fails at a steady rate ``p`` this estimates ``2p(1 - p)``, the same
    quantity as the flip rate, from runs where the code did not change.
    """
    runs = sum(len(outcomes) for outcomes in groups)
    if not runs:
        return 0.0
    disagreement = 0.0
    for outcomes in groups:
        failed = sum(outcomes)
        disagreement += 2.0 * failed * (len(outcomes) - failed) / (len(outcomes) - 1)
    return disagreement / runs


def _cluster_messages(observations: list[Observation], top_n: int = 5) -> list[MessageCluster]:
    messages: list[str] = []
    for obs in observations:
        if obs.result.retry:
            messages.extend(f.message for f in obs.result.retry.failures if f.message)
        elif obs.result.status.is_failure and obs.result.message:
            messages.append(obs.result.message)
    by_key: dict[str, Counter[str]] = defaultdict(Counter)
    for msg in messages:
        key = _MSG_NORMALIZE_RE.sub("#", msg)
        by_key[key][msg] += 1

    clusters = []
    for variants in by_key.values():
        total = sum(variants.values())
        representative = variants.most_common(1)[0][0]
        clusters.append(MessageCluster(representative=representative, count=total))
    clusters.sort(key=lambda c: c.count, reverse=True)
    return clusters[:top_n]


def _test_stats(
    full_name: str,
    observations: list[Observation],
    run_positions: dict[str, int],
    run_failures: dict[str, int] | None = None,
) -> TestStats:
    suite = observations[0].result.suite
    non_skip = [o for o in observations if o.result.status not in (Status.SKIP, Status.UNKNOWN)]
    n = len(non_skip)
    n_skip = sum(o.result.status == Status.SKIP for o in observations)
    excluded = [o for o in observations if o.result.status == Status.UNKNOWN]
    retries = [o for o in non_skip if o.result.retry]
    recovered = sum(
        o.result.retry is not None and o.result.retry.outcome == "recovered" for o in retries
    )
    exhausted = len(retries) - recovered
    outcomes = [1 if o.result.status.is_failure else 0 for o in non_skip]
    n_fail = sum(outcomes)
    n_pass = n - n_fail
    failure_rate = wilson_interval(n_fail, n)

    # Skips keep the existing "consecutive observed outcomes" convention, but
    # an excluded outcome interrupts that sequence: do not bridge ambiguity.
    sequence = [o.result.status for o in observations if o.result.status != Status.SKIP]
    pairs = [
        (a, b) for a, b in zip(sequence, sequence[1:], strict=False) if Status.UNKNOWN not in (a, b)
    ]
    flips = sum(a.is_failure != b.is_failure for a, b in pairs)
    flip_rate = flips / len(pairs) if pairs else 0.0

    by_commit: dict[tuple[str, str | None, str | None, str | None], list[int]] = defaultdict(list)
    for obs, outcome in zip(non_skip, outcomes, strict=True):
        md = obs.run.metadata
        if md.commit:
            by_commit[(md.commit, md.branch, md.runner, md.os)].append(outcome)
    reruns = {commit: outs for commit, outs in by_commit.items() if len(outs) > 1}
    rerun_commits_total = len(reruns)
    rerun_commits_flaky = sum(1 for outs in reruns.values() if len(set(outs)) > 1)
    rerun_signal = _rerun_disagreement(list(reruns.values()))

    failures: list[FailureEvidence] = []
    named: dict[str, list[tuple[int, FailureEvidence]]] = defaultdict(list)
    for index, (obs, outcome) in enumerate(zip(non_skip, outcomes, strict=True)):
        if not outcome:
            continue
        md = obs.run.metadata
        same_commit: SameCommit = "unknown"
        others = 0
        if md.commit:
            context = by_commit[(md.commit, md.branch, md.runner, md.os)]
            others = len(context) - 1
            same_commit = "single" if not others else "passed" if 0 in context else "failed"
        failures.append(
            FailureEvidence(
                run_id=md.run_id,
                index=index,
                timestamp=md.timestamp,
                commit=md.commit,
                status=obs.result.status,
                message=obs.result.message,
                failed_within=obs.result.failed_within,
                same_commit=same_commit,
                same_commit_runs=others,
                failed_with=max(0, (run_failures or {}).get(md.run_id, 1) - 1),
            )
        )
        for top in dict.fromkeys(name.split("/", 1)[0] for name in obs.result.failed_within):
            named[top].append((index, failures[-1]))
    named_failures = []
    for name, records in named.items():
        placed = assess([index for index, _ in records], n, can_be_new=False)
        assert placed is not None
        named_failures.append(
            NamedFailure(
                name=name,
                runs=len(records),
                first_run_id=records[0][1].run_id,
                last_run_id=records[-1][1].run_id,
                passed_same_commit=sum(f.same_commit == "passed" for _, f in records),
                checked=sum(f.same_commit in ("passed", "failed") for _, f in records),
                activity=placed,
            )
        )
    named_failures.sort(key=lambda item: (-item.runs, item.name))

    p = failure_rate.point
    intermittency = 2 * min(p, 1 - p)
    confidence = min(1.0, n / 20)
    flakiness_score = confidence * (
        W_FLIP * flip_rate
        + W_RERUN * max(rerun_signal, recovered / n if n else 0.0)
        + W_INTERMITTENCY * intermittency
    )

    # Incomplete histories cannot locate an onset without guessing across gaps.
    change_point = detect_change_point(outcomes) if not excluded else None
    change_point_run_id = None
    change_point_commit = None
    runs_since_change = None
    if change_point is not None:
        change_point_run_id = non_skip[change_point.index].run.metadata.run_id
        change_point_commit = non_skip[change_point.index].run.metadata.commit
        runs_since_change = len(run_positions) - run_positions[change_point_run_id]

    disagrees_after_change = False
    if change_point is not None:
        since: dict[tuple[str, str | None, str | None, str | None], set[int]] = defaultdict(set)
        for obs, outcome in zip(
            non_skip[change_point.index :], outcomes[change_point.index :], strict=True
        ):
            md = obs.run.metadata
            if md.commit:
                since[(md.commit, md.branch, md.runner, md.os)].add(outcome)
        disagrees_after_change = any(len(seen) > 1 for seen in since.values())

    classification = _classify(n, p, flip_rate, rerun_signal, change_point, disagrees_after_change)
    if recovered:
        classification = "flaky"  # direct runner evidence, even from one run
    elif excluded and classification == "healthy":
        classification = "insufficient_data"

    # Surefire's time describes the last passing or first failing attempt, not
    # retry cost. Mixing it into ordinary-run duration signals would mislead.
    duration_observations = [
        (o, outcome)
        for o, outcome in zip(non_skip, outcomes, strict=True)
        if o.result.duration is not None and o.result.retry is None
    ]
    durations = [
        o.result.duration for o, _ in duration_observations if o.result.duration is not None
    ]
    duration_outcomes = [outcome for o, outcome in duration_observations]
    duration_positions = [run_positions[o.run.metadata.run_id] for o, _ in duration_observations]
    duration_trend = linear_trend(durations, duration_positions) if len(durations) >= 2 else None
    duration_failure_correlation = (
        point_biserial(durations, duration_outcomes) if len(durations) >= 2 else None
    )

    runners = [o.run.metadata.runner for o in non_skip if o.run.metadata.runner]
    runner_rates: list[GroupRate] = []
    if runners:
        runner_outcomes = [
            outcome for o, outcome in zip(non_skip, outcomes, strict=True) if o.run.metadata.runner
        ]
        runner_rates = group_failure_rates(runners, runner_outcomes)

    oses = [o.run.metadata.os for o in non_skip if o.run.metadata.os]
    os_rates: list[GroupRate] = []
    if oses:
        os_outcomes = [
            outcome for o, outcome in zip(non_skip, outcomes, strict=True) if o.run.metadata.os
        ]
        os_rates = group_failure_rates(oses, os_outcomes)

    timestamps = [o.run.metadata.timestamp for o in observations if o.run.metadata.timestamp]

    return TestStats(
        full_name=full_name,
        suite=suite,
        n=n,
        n_pass=n_pass,
        n_fail=n_fail,
        n_skip=n_skip,
        failure_rate=failure_rate,
        flip_rate=flip_rate,
        rerun_commits_total=rerun_commits_total,
        rerun_commits_flaky=rerun_commits_flaky,
        rerun_signal=rerun_signal,
        flakiness_score=flakiness_score,
        classification=classification,
        change_point=change_point,
        change_point_run_id=change_point_run_id,
        change_point_commit=change_point_commit,
        duration_trend=duration_trend,
        duration_n=len(durations),
        duration_failure_correlation=duration_failure_correlation,
        runner_rates=runner_rates,
        os_rates=os_rates,
        message_clusters=_cluster_messages(observations),
        first_seen=min(timestamps) if timestamps else None,
        last_seen=max(timestamps) if timestamps else None,
        last_status=observations[-1].result.status,
        runs_since_change=runs_since_change,
        n_unknown=len(excluded),
        flip_pairs=len(pairs),
        recovered_runs=recovered,
        exhausted_runs=exhausted,
        retry_observations=retries,
        excluded_observations=excluded,
        failures=failures,
        activity=assess([f.index for f in failures], n),
        named_failures=named_failures,
    )


def analyze(runs: list[Run]) -> AnalysisResult:
    """Compute flakiness statistics for every test seen across `runs`.

    `runs` must already be in chronological order (see `flakemap.loader.load_runs`,
    which guarantees this).
    """
    by_test: dict[str, list[Observation]] = defaultdict(list)
    for observation in history_observations(runs):
        by_test[observation.result.full_name].append(observation)

    run_positions = {run.metadata.run_id: i for i, run in enumerate(runs)}
    run_failures: Counter[str] = Counter()
    for observations in by_test.values():
        for obs in observations:
            if obs.result.status.is_failure:
                run_failures[obs.run.metadata.run_id] += 1
    tests = [_test_stats(name, obs, run_positions, run_failures) for name, obs in by_test.items()]
    tests.sort(key=lambda t: t.flakiness_score, reverse=True)

    run_id_range = (runs[0].metadata.run_id, runs[-1].metadata.run_id) if runs else None
    timestamps = [r.metadata.timestamp for r in runs if r.metadata.timestamp]
    timestamp_range = (min(timestamps), max(timestamps)) if timestamps else None

    mtime_sources = sum(1 for r in runs if r.metadata.source == "mtime")
    mtime_warning = None
    if runs and mtime_sources / len(runs) > 0.5:
        mtime_warning = (
            f"{mtime_sources}/{len(runs)} runs have no sidecar timestamp/sequence and were "
            "ordered by file mtime; run order (and therefore flip rate, change-point, and "
            "duration trend) may be inaccurate if mtimes don't reflect CI run order "
            "(e.g. after a fresh checkout)."
        )

    elif mtime_sources and any(r.metadata.source in ("sidecar", "report") for r in runs):
        # A file's modification time is when it was copied; set among runs placed by
        # their recorded time, such a run lands wherever the copy happened to be made.
        strays = [r.metadata.run_id for r in runs if r.metadata.source == "mtime"]
        mtime_warning = (
            f"{mtime_sources} of {len(runs)} runs record no time and are placed by file "
            f"mtime among runs placed by their recorded time ({', '.join(strays[:3])}"
            f"{', ...' if len(strays) > 3 else ''}); give them a timestamp or leave them out."
        )

    warnings = [f"run {r.metadata.run_id}: {w}" for r in runs for w in r.warnings]
    warnings.extend(
        f"run {o.run.metadata.run_id}, {t.full_name}: {o.result.issue}; excluded from rates"
        for t in tests
        for o in t.excluded_observations
    )
    if mtime_warning:
        warnings.append(mtime_warning)
    ordering_tiers = {
        0 if r.metadata.timestamp else 1 if r.metadata.sequence is not None else 2 for r in runs
    }
    if len(ordering_tiers) > 1:
        warnings.append(
            "Mixed ordering sources: timestamped runs sort before sequence-only runs. "
            "Supply a timestamp for every run or a sequence for every run to compare chronology."
        )
    order_keys = [run_sort_key(r)[:3] for r in runs]
    if len(set(order_keys)) != len(order_keys):
        warnings.append(
            "Some runs have tied ordering values; run ids break ties lexically. "
            "Provide distinct timestamps or sequences before interpreting temporal statistics."
        )

    return AnalysisResult(
        tests=tests,
        total_runs=len(runs),
        run_id_range=run_id_range,
        timestamp_range=timestamp_range,
        mtime_fallback_warning=mtime_warning,
        warnings=warnings,
        cofailure=group_failures(runs, by_test),
        observations=dict(by_test),
    )
