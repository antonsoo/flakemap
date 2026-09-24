"""Per-test flakiness statistics: the analysis flakemap's outputs all read from.

This module turns an ordered list of `Run` into one `TestStats` per test. See
`docs/formats.md` and the README's "How it works" section for the reasoning
behind each formula; docstrings here give the short version and the exact
arithmetic.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime

from flakemap.models import Run, Status, TestCaseResult
from flakemap.stats.changepoint import ChangePoint, detect_change_point
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
class Observation:
    run: Run
    result: TestCaseResult


@dataclass(frozen=True, slots=True)
class MessageCluster:
    representative: str
    count: int


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
    duration_failure_correlation: float | None
    runner_rates: list[GroupRate]
    os_rates: list[GroupRate]
    message_clusters: list[MessageCluster]
    first_seen: datetime | None
    last_seen: datetime | None
    last_status: Status
    runs_since_change: int | None
    """Length of the after-change-point segment, i.e. how many of the most
    recent runs reflect the new regime. `None` if no change point was found."""


@dataclass(slots=True)
class AnalysisResult:
    tests: list[TestStats]
    total_runs: int
    run_id_range: tuple[str, str] | None
    timestamp_range: tuple[datetime, datetime] | None
    mtime_fallback_warning: str | None


def _classify(
    n: int,
    failure_point: float,
    flip_rate: float,
    rerun_signal: float,
    change_point: ChangePoint | None,
) -> str:
    if n < MIN_SAMPLES_FOR_SCORE:
        return "insufficient_data"
    if failure_point == 0.0 and flip_rate == 0.0 and rerun_signal == 0.0:
        return "healthy"
    if flip_rate > 0.08 or rerun_signal > 0.0:
        return "flaky"
    if change_point is not None and change_point.rate_after >= 0.75:
        return "broken"
    if failure_point >= 0.6:
        return "broken"
    if failure_point > 0.0:
        return "flaky"
    return "healthy"


def _cluster_messages(observations: list[Observation], top_n: int = 5) -> list[MessageCluster]:
    messages = [
        obs.result.message
        for obs in observations
        if obs.result.status.is_failure and obs.result.message
    ]
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


def _test_stats(full_name: str, observations: list[Observation]) -> TestStats:
    suite = observations[0].result.suite
    non_skip = [o for o in observations if o.result.status != Status.SKIP]
    n = len(non_skip)
    n_skip = len(observations) - n
    outcomes = [1 if o.result.status.is_failure else 0 for o in non_skip]
    n_fail = sum(outcomes)
    n_pass = n - n_fail
    failure_rate = wilson_interval(n_fail, n)

    flips = sum(1 for a, b in zip(outcomes, outcomes[1:], strict=False) if a != b)
    flip_rate = flips / (n - 1) if n > 1 else 0.0

    by_commit: dict[str, list[int]] = defaultdict(list)
    for obs, outcome in zip(non_skip, outcomes, strict=True):
        if obs.run.metadata.commit:
            by_commit[obs.run.metadata.commit].append(outcome)
    reruns = {commit: outs for commit, outs in by_commit.items() if len(outs) > 1}
    rerun_commits_total = len(reruns)
    rerun_commits_flaky = sum(1 for outs in reruns.values() if len(set(outs)) > 1)
    rerun_signal = rerun_commits_flaky / rerun_commits_total if rerun_commits_total else 0.0

    p = failure_rate.point
    intermittency = 2 * min(p, 1 - p)
    confidence = min(1.0, n / 20)
    flakiness_score = confidence * (
        W_FLIP * flip_rate + W_RERUN * rerun_signal + W_INTERMITTENCY * intermittency
    )

    change_point = detect_change_point(outcomes)
    change_point_run_id = None
    change_point_commit = None
    runs_since_change = None
    if change_point is not None:
        change_point_run_id = non_skip[change_point.index].run.metadata.run_id
        change_point_commit = non_skip[change_point.index].run.metadata.commit
        runs_since_change = n - change_point.index

    classification = _classify(n, p, flip_rate, rerun_signal, change_point)

    durations = [o.result.duration for o in non_skip if o.result.duration is not None]
    duration_outcomes = [
        outcome
        for o, outcome in zip(non_skip, outcomes, strict=True)
        if o.result.duration is not None
    ]
    duration_trend = linear_trend(durations) if len(durations) >= 2 else None
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
        duration_failure_correlation=duration_failure_correlation,
        runner_rates=runner_rates,
        os_rates=os_rates,
        message_clusters=_cluster_messages(observations),
        first_seen=min(timestamps) if timestamps else None,
        last_seen=max(timestamps) if timestamps else None,
        last_status=observations[-1].result.status,
        runs_since_change=runs_since_change,
    )


def analyze(runs: list[Run]) -> AnalysisResult:
    """Compute flakiness statistics for every test seen across `runs`.

    `runs` must already be in chronological order (see `flakemap.loader.load_runs`,
    which guarantees this).
    """
    by_test: dict[str, list[Observation]] = defaultdict(list)
    for run in runs:
        for result in run.testcases:
            by_test[result.full_name].append(Observation(run=run, result=result))

    tests = [_test_stats(name, obs) for name, obs in by_test.items()]
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

    return AnalysisResult(
        tests=tests,
        total_runs=len(runs),
        run_id_range=run_id_range,
        timestamp_range=timestamp_range,
        mtime_fallback_warning=mtime_warning,
    )
