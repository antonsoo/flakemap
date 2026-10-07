"""Exact shared outcome histories, not a correlation estimate or a causal model.

Tests join a cohort only when their observed run positions and normalized states
match. Absent and skipped results therefore cannot masquerade as passes. Any
ambiguous observation excludes that test from grouping altogether. Final fail and
error share a state; recovered and exhausted retries have distinct states, while
their original records remain evidence. All-pass histories are uninteresting here.

Sparse signatures avoid comparing every pair of tests. Constructing signatures
costs O(observations); materializing run-state lists costs O(cohorts * runs).
Members, groups and affected evidence are additionally sorted for stable output.
Each test belongs to at most one cohort. Exact matching deliberately misses partial
overlap, subsets and similar histories with different observation coverage.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Literal

from flakemap.models import Run, RunMetadata, Status, TestCaseResult
from flakemap.observations import Observation

CohortState = Literal["pass", "failed", "recovered", "exhausted", "skip", "absent"]
STATES: tuple[CohortState, ...] = ("pass", "failed", "recovered", "exhausted", "skip", "absent")
SIGNAL_STATES = frozenset(("failed", "recovered", "exhausted"))


@dataclass(frozen=True, slots=True)
class FailureCohort:
    id: str
    tests: tuple[str, ...]
    states: dict[CohortState, tuple[str, ...]]
    evidence: tuple[Observation, ...]

    @property
    def failed_runs(self) -> int:
        return len(self.states["failed"]) + len(self.states["exhausted"])

    @property
    def recovered_runs(self) -> int:
        return len(self.states["recovered"])

    @property
    def affected_test_runs(self) -> int:
        """Test-runs with a final failure or an explicit recovered retry, not attempts."""
        return len(self.tests) * (self.failed_runs + self.recovered_runs)


@dataclass(slots=True)
class CoFailureAnalysis:
    runs: tuple[RunMetadata, ...] = ()
    groups: list[FailureCohort] = field(default_factory=list)
    excluded_tests: tuple[str, ...] = ()


def outcome_state(result: TestCaseResult) -> CohortState:
    if result.status == Status.UNKNOWN:
        raise ValueError("Ambiguous outcomes cannot be grouped")
    if result.status == Status.SKIP:
        return "skip"
    if result.status == Status.PASS:
        return "recovered" if result.retry and result.retry.outcome == "recovered" else "pass"
    return "exhausted" if result.retry and result.retry.outcome == "exhausted" else "failed"


def group_failures(runs: list[Run], by_test: dict[str, list[Observation]]) -> CoFailureAnalysis:
    positions = {run.metadata.run_id: index for index, run in enumerate(runs)}
    by_signature: dict[tuple[tuple[int, CohortState], ...], list[str]] = defaultdict(list)
    excluded = []
    for name, observations in by_test.items():
        if any(obs.result.status == Status.UNKNOWN for obs in observations):
            excluded.append(name)
            continue
        signature = tuple(
            (positions[obs.run.metadata.run_id], outcome_state(obs.result)) for obs in observations
        )
        if any(state in SIGNAL_STATES for _, state in signature):
            by_signature[signature].append(name)

    # Sort by the count of observed affected test-runs, never a probability.
    candidates = [
        (signature, tuple(sorted(names)))
        for signature, names in by_signature.items()
        if len(names) >= 2
    ]
    candidates.sort(
        key=lambda item: (
            -sum(state in SIGNAL_STATES for _, state in item[0]) * len(item[1]),
            -len(item[1]),
            item[1],
        )
    )
    groups = []
    for index, (signature, names) in enumerate(candidates, 1):
        observed = dict(signature)
        states: dict[CohortState, list[str]] = {state: [] for state in STATES}
        for position, run in enumerate(runs):
            states[observed.get(position, "absent")].append(run.metadata.run_id)
        evidence = [
            obs
            for name in names
            for obs in by_test[name]
            if outcome_state(obs.result) in SIGNAL_STATES
        ]
        evidence.sort(key=lambda obs: (positions[obs.run.metadata.run_id], obs.result.full_name))
        groups.append(
            FailureCohort(
                id=f"cohort-{index}",
                tests=names,
                states={state: tuple(ids) for state, ids in states.items()},
                evidence=tuple(evidence),
            )
        )
    return CoFailureAnalysis(tuple(run.metadata for run in runs), groups, tuple(sorted(excluded)))
