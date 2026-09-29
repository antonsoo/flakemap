"""One outcome per test per run, shared by statistics and report rendering.

Repeated identifiers may mean retries, shards, parameter collisions, or a copied
artifact. XML order cannot distinguish these. Keep the records for inspection,
but exclude their ambiguous run outcome instead of counting them as trials.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, replace

from flakemap.models import Run, Status, TestCaseResult


@dataclass(frozen=True, slots=True)
class Observation:
    run: Run
    result: TestCaseResult
    records: tuple[TestCaseResult, ...]


def run_observations(run: Run) -> list[Observation]:
    by_test: dict[str, list[TestCaseResult]] = defaultdict(list)
    for result in run.testcases:
        by_test[result.full_name].append(result)
    observations = []
    for records in by_test.values():
        result = records[0]
        if len(records) > 1 or run.integrity_issue:
            result = replace(
                result,
                status=Status.UNKNOWN,
                duration=None,
                message=None,
                retry=None,
                source=None,
                issue=run.integrity_issue
                or f"{len(records)} records share this test identifier in one run; "
                "cannot distinguish retries, shards, or duplicate artifacts",
            )
        observations.append(Observation(run, result, tuple(records)))
    return observations


def history_observations(runs: list[Run]) -> list[Observation]:
    """Normalize a history, including collisions in the dotted display label."""
    if len({run.metadata.run_id for run in runs}) != len(runs):
        raise ValueError("Run ids must be unique; merge shards before analysis")
    identities: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for run in runs:
        for record in run.testcases:
            identities[record.full_name].add((record.classname, record.name))
    observations = []
    for run in runs:
        for observation in run_observations(run):
            result = observation.result
            if len(identities[result.full_name]) > 1:
                result = replace(
                    result,
                    status=Status.UNKNOWN,
                    duration=None,
                    message=None,
                    retry=None,
                    issue="distinct classname/name pairs share this dotted identifier; "
                    "use unambiguous test identifiers",
                )
                observation = replace(observation, result=result)
            observations.append(observation)
    return observations
