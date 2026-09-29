"""Machine-readable output: a plain-data dict, ready for `json.dumps`."""

from __future__ import annotations

from typing import Any

from flakemap.models import TestCaseResult
from flakemap.observations import Observation
from flakemap.stats.analyze import AnalysisResult, TestStats


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
        "last_status": t.last_status.value,
    }


def to_json_dict(result: AnalysisResult) -> dict[str, Any]:
    """Build the `--json` output payload."""
    return {
        "schema_version": 2,
        "summary": {
            "total_runs": result.total_runs,
            "run_id_range": list(result.run_id_range) if result.run_id_range else None,
            "timestamp_range": (
                [t.isoformat() for t in result.timestamp_range] if result.timestamp_range else None
            ),
            "total_tests": len(result.tests),
            "recovered_test_runs": sum(t.recovered_runs for t in result.tests),
            "exhausted_test_runs": sum(t.exhausted_runs for t in result.tests),
            "excluded_test_runs": sum(t.n_unknown for t in result.tests),
            "flaky": sum(1 for t in result.tests if t.classification == "flaky"),
            "broken": sum(1 for t in result.tests if t.classification == "broken"),
            "healthy": sum(1 for t in result.tests if t.classification == "healthy"),
            "insufficient_data": sum(
                1 for t in result.tests if t.classification == "insufficient_data"
            ),
        },
        "warnings": result.warnings,
        "tests": [_test_to_dict(t) for t in result.tests],
    }
