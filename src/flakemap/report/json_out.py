"""Machine-readable output: a plain-data dict, ready for `json.dumps`."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from flakemap.models import TestCaseResult
from flakemap.observations import Observation
from flakemap.stats.activity import Activity
from flakemap.stats.analyze import AnalysisResult, TestStats
from flakemap.stats.cofailure import CoFailureAnalysis, FailureCohort


def record_to_dict(record: TestCaseResult) -> dict[str, Any]:
    return {
        "name": record.name,
        "classname": record.classname,
        "source": {"report": record.source.report, "testcase": record.source.testcase}
        if record.source
        else None,
        "status": record.status.value,
        "message": record.message,
        "reported_duration_seconds": record.duration,
        "issue": record.issue,
        "retry": {
            "outcome": record.retry.outcome,
            "attempts": record.retry.attempts,
            "failures": [
                {"tag": f.tag, "status": f.status.value, "message": f.message}
                for f in record.retry.failures
            ],
        }
        if record.retry
        else None,
    }


def _evidence(obs: Observation) -> dict[str, Any]:
    return {
        "run_id": obs.run.metadata.run_id,
        "commit": obs.run.metadata.commit,
        "reason": obs.result.issue,
        "records": [record_to_dict(r) for r in obs.records],
    }


def cohort_to_dict(group: FailureCohort) -> dict[str, Any]:
    return {
        "id": group.id,
        "tests": list(group.tests),
        "run_states": {state: list(ids) for state, ids in group.states.items()},
        "failed_runs": group.failed_runs,
        "recovered_runs": group.recovered_runs,
        "affected_test_runs": group.affected_test_runs,
        "evidence": [{"test": obs.result.full_name, **_evidence(obs)} for obs in group.evidence],
    }


def cofailure_to_dict(analysis: CoFailureAnalysis) -> dict[str, Any]:
    return {
        "method": "exact_outcome_history",
        "ambiguous_tests_excluded": list(analysis.excluded_tests),
        "runs": [
            {
                "run_id": md.run_id,
                "commit": md.commit,
                "branch": md.branch,
                "timestamp": md.timestamp.isoformat() if md.timestamp else None,
                "runner": md.runner,
                "os": md.os,
                "sequence": md.sequence,
                "metadata_source": md.source,
            }
            for md in analysis.runs
        ],
        "groups": [cohort_to_dict(group) for group in analysis.groups],
    }


def _activity(activity: Activity | None) -> dict[str, Any] | None:
    if activity is None:
        return None
    return {
        "state": activity.state,
        "failures": activity.failures,
        "basis": "runs_with_observed_failures",
        "run_axis": "usable_test_executions",
        "final_failure_runs": activity.failures - activity.recovered_runs,
        "recovered_runs": activity.recovered_runs,
        "events": activity.events,
        "runs_since_last_failure": activity.runs_since_last,
        "runs_since_first_failure": activity.runs_since_first,
        "longest_gap": activity.longest_gap,
        "silence_ratio": None
        if activity.silence_ratio is None
        else round(activity.silence_ratio, 2),
    }


def _test_to_dict(t: TestStats) -> dict[str, Any]:
    return {
        "test": t.full_name,
        "suite": t.suite,
        "classification": t.classification,
        "flakiness_score": round(t.flakiness_score, 4),
        "runs": {
            "total": t.n,
            "pass": t.n_pass,
            "fail": t.n_fail,
            "skip": t.n_skip,
            "unknown": t.n_unknown,
        },
        "failure_rate": {
            "point": round(t.failure_rate.point, 4),
            "wilson_low": round(t.failure_rate.low, 4),
            "wilson_high": round(t.failure_rate.high, 4),
        }
        if t.n
        else None,
        "flip_rate": round(t.flip_rate, 4) if t.flip_pairs else None,
        "flip_pairs": t.flip_pairs,
        "rerun_signal": {
            "value": round(t.rerun_signal, 4),
            "groups_with_reruns": t.rerun_commits_total,
            "groups_with_flip": t.rerun_commits_flaky,
        },
        "retries": {
            "recovered_runs": t.recovered_runs,
            "exhausted_runs": t.exhausted_runs,
            "observed_failed_attempts": sum(
                len(o.result.retry.failures) for o in t.retry_observations if o.result.retry
            ),
            "evidence": [_evidence(o) for o in t.retry_observations],
        },
        "excluded": [_evidence(o) for o in t.excluded_observations],
        "activity": _activity(t.activity),
        "activity_unavailable_reason": t.activity_unavailable_reason,
        "first_failure_run_id": t.first_failure_run_id,
        "history_runs_since_first_failure": t.history_runs_since_first_failure,
        "same_commit": {
            "failures_passed_elsewhere": t.failures_passed_same_commit,
            "failures_failed_everywhere": t.failures_repeated_same_commit,
            "failures_without_another_run": len(t.failures) - t.failures_checked,
        },
        "failures": [
            {
                "run_id": f.run_id,
                "index": f.index,
                "timestamp": f.timestamp.isoformat() if f.timestamp else None,
                "commit": f.commit,
                "status": f.status.value,
                "message": f.message,
                "failed_within": list(f.failed_within),
                "same_commit": f.same_commit,
                "same_commit_other_runs": f.same_commit_runs,
                "other_tests_failed": f.failed_with,
            }
            for f in t.failures
        ],
        "named_failures": [
            {
                "name": named.name,
                "runs": named.runs,
                "first_run_id": named.first_run_id,
                "last_run_id": named.last_run_id,
                "history_runs_since_first_failure": named.history_runs_since_first_failure,
                "passed_same_commit": named.passed_same_commit,
                "checked_same_commit": named.checked,
                "activity": _activity(named.activity),
                "activity_unavailable_reason": t.activity_unavailable_reason,
            }
            for named in t.named_failures
        ],
        "change_point": (
            {
                "run_id": t.change_point_run_id,
                "commit": t.change_point_commit,
                "rate_before": round(t.change_point.rate_before, 4),
                "rate_after": round(t.change_point.rate_after, 4),
                "statistic": round(t.change_point.statistic, 4),
                "runs_since_change": t.runs_since_change,
            }
            if t.change_point
            else None
        ),
        "duration": {
            "observations": t.duration_n,
            "trend_axis": "supplied_history_run_index",
            "trend_seconds_per_run": (
                round(t.duration_trend, 6) if t.duration_trend is not None else None
            ),
            "failure_correlation": (
                round(t.duration_failure_correlation, 4)
                if t.duration_failure_correlation is not None
                else None
            ),
        },
        "runner_rates": [
            {
                "runner": g.label,
                "n": g.n,
                "failure_rate": round(g.interval.point, 4),
                "wilson_low": round(g.interval.low, 4),
                "wilson_high": round(g.interval.high, 4),
            }
            for g in t.runner_rates
        ],
        "os_rates": [
            {
                "os": g.label,
                "n": g.n,
                "failure_rate": round(g.interval.point, 4),
                "wilson_low": round(g.interval.low, 4),
                "wilson_high": round(g.interval.high, 4),
            }
            for g in t.os_rates
        ],
        "top_failure_messages": [
            {"message": c.representative, "count": c.count} for c in t.message_clusters
        ],
        "first_seen": t.first_seen.isoformat() if t.first_seen else None,
        "last_seen": t.last_seen.isoformat() if t.last_seen else None,
        "last_status": t.last_status.value if t.last_status is not None else None,
        "temporal_available": t.temporal_available,
    }


def to_json_dict(result: AnalysisResult) -> dict[str, Any]:
    """Build the `--json` output payload."""
    return {
        "schema_version": 3,
        "summary": {
            "input_complete": not result.warnings,
            "ordering": asdict(result.ordering),
            "total_runs": result.total_runs,
            "run_id_range": list(result.run_id_range) if result.run_id_range else None,
            "timestamp_range": (
                [t.isoformat() for t in result.timestamp_range] if result.timestamp_range else None
            ),
            "total_tests": len(result.tests),
            "cofailure_groups": len(result.cofailure.groups),
            "cofailure_tests": sum(len(group.tests) for group in result.cofailure.groups),
            "recovered_test_runs": sum(t.recovered_runs for t in result.tests),
            "exhausted_test_runs": sum(t.exhausted_runs for t in result.tests),
            "excluded_test_runs": sum(t.n_unknown for t in result.tests),
            "flaky": sum(1 for t in result.tests if t.classification == "flaky"),
            "flaky_new": sum(
                1
                for t in result.tests
                if t.classification == "flaky" and t.activity and t.activity.state == "new"
            ),
            "flaky_quiet": sum(
                1
                for t in result.tests
                if t.classification == "flaky" and t.activity and t.activity.state == "quiet"
            ),
            "broken": sum(1 for t in result.tests if t.classification == "broken"),
            "healthy": sum(1 for t in result.tests if t.classification == "healthy"),
            "insufficient_data": sum(
                1 for t in result.tests if t.classification == "insufficient_data"
            ),
        },
        "warnings": result.warnings,
        "cofailure": cofailure_to_dict(result.cofailure),
        "tests": [_test_to_dict(t) for t in result.tests],
    }
