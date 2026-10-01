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

from flakemap.models import Run, Status, run_sort_key
from flakemap.observations import Observation, history_observations
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
    n_unknown: int
    flip_pairs: int
    recovered_runs: int
    exhausted_runs: int
    retry_observations: list[Observation]
    excluded_observations: list[Observation]


@dataclass(slots=True)
class AnalysisResult:
    tests: list[TestStats]
    total_runs: int
    run_id_range: tuple[str, str] | None
    timestamp_range: tuple[datetime, datetime] | None
    mtime_fallback_warning: str | None
    warnings: list[str]


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
    # A significant change point into mostly failing is a regression, so it is checked
    # before the flip rate: in a short history the one pass-to-fail switch alone pushes
    # the flip rate over the flaky threshold (1 flip in 12 runs is 0.09).
    if change_point is not None and change_point.rate_after >= 0.75 and rerun_signal == 0.0:
        return "broken"
    if flip_rate > 0.08 or rerun_signal > 0.0:
        return "flaky"
    if failure_point >= 0.6:
        return "broken"
    if failure_point > 0.0:
        return "flaky"
    return "healthy"


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


def _test_stats(full_name: str, observations: list[Observation]) -> TestStats:
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
    rerun_signal = rerun_commits_flaky / rerun_commits_total if rerun_commits_total else 0.0

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
        runs_since_change = n - change_point.index

    classification = _classify(n, p, flip_rate, rerun_signal, change_point)
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
        n_unknown=len(excluded),
        flip_pairs=len(pairs),
        recovered_runs=recovered,
        exhausted_runs=exhausted,
        retry_observations=retries,
        excluded_observations=excluded,
    )


def analyze(runs: list[Run]) -> AnalysisResult:
    """Compute flakiness statistics for every test seen across `runs`.

    `runs` must already be in chronological order (see `flakemap.loader.load_runs`,
    which guarantees this).
    """
    by_test: dict[str, list[Observation]] = defaultdict(list)
    for observation in history_observations(runs):
        by_test[observation.result.full_name].append(observation)

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
    )
