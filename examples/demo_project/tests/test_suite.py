"""Synthetic demo suite for flakemap: every failure pattern here is planted.

This file exists to produce **real** `pytest --junitxml` output with known
ground truth, so flakemap's statistics can be checked against reality instead
of just "looking plausible". See `examples/demo_project/generate_demo_data.py`
for how it's run (100+ times, varying `pytest-randomly` seeds, over a fake
commit sequence) and the README's "Accuracy and limitations" section for what
flakemap actually recovers from the resulting data. All data produced from
this file is synthetic and is labelled as such everywhere it's used.
"""

from __future__ import annotations

import os
import random
import time

import pytest

# ---------------------------------------------------------------------------
# Healthy: deterministic, always pass, no shared state.
# ---------------------------------------------------------------------------


def test_addition() -> None:
    assert 2 + 2 == 4


def test_string_formatting() -> None:
    assert f"{'flake':>8}" == "   flake"


def test_sorted_is_stable() -> None:
    assert sorted([3, 1, 2]) == [1, 2, 3]


def test_dict_merge() -> None:
    assert {**{"a": 1}, **{"b": 2}} == {"a": 1, "b": 2}


def test_list_comprehension() -> None:
    assert [x * x for x in range(5)] == [0, 1, 4, 9, 16]


def test_string_split() -> None:
    assert "a,b,c".split(",") == ["a", "b", "c"]  # noqa: SIM905 -- exercising str.split itself


# ---------------------------------------------------------------------------
# Flaky: a timing race against a fixed budget. Modeled on a real pattern (an
# I/O call whose latency varies, checked against a timeout tuned for the
# common case, not the tail) rather than relying on this particular sandbox's
# scheduler jitter, which was measured to be sub-millisecond and wouldn't
# reproduce reliably across machines. `random` is seeded per run by
# pytest-randomly (see generate_demo_data.py), so each run's outcome is
# reproducible given its seed while still being a genuine race against a
# fixed budget rather than a scripted pass/fail.
# ---------------------------------------------------------------------------


def test_tight_timeout_race() -> None:
    budget = 0.0125
    # FLAKEMAP_DEMO_RUNNER_EXTRA_DELAY models one runner class in the fleet
    # being consistently slower than another (a real, common CI phenomenon);
    # generate_demo_data.py sets it per simulated runner. The delay is a real
    # measured sleep either way -- only the offset is scripted.
    extra = float(os.environ.get("FLAKEMAP_DEMO_RUNNER_EXTRA_DELAY", "0"))
    delay = random.uniform(0.005, 0.015) + extra
    start = time.perf_counter()
    time.sleep(delay)
    elapsed = time.perf_counter() - start
    assert elapsed < budget, f"took {elapsed:.4f}s, budget {budget:.4f}s"


# ---------------------------------------------------------------------------
# Flaky: randomness baked directly into the assertion.
# ---------------------------------------------------------------------------


def test_probabilistic_threshold() -> None:
    assert random.random() >= 0.12


# ---------------------------------------------------------------------------
# Flaky: shared mutable state, order-dependent. `_seen` is populated by
# `test_populate_cache_first`; under pytest-randomly's shuffled test order
# this sometimes runs *after* `test_reads_cache_depends_on_order`, which then
# fails. Left unseeded/unordered on purpose -- that's the bug being modeled.
# ---------------------------------------------------------------------------

_seen: set[str] = set()


def test_populate_cache_first() -> None:
    _seen.add("warm")
    assert True


def test_reads_cache_depends_on_order() -> None:
    assert "warm" in _seen, "cache was not warmed before this test ran"


# ---------------------------------------------------------------------------
# Broken, not flaky: fails reliably from a simulated commit onward and never
# recovers. `generate_demo_data.py` sets FLAKEMAP_DEMO_COMMIT_SEQ to each
# run's position in the fake commit sequence; this models a real regression
# landing at commit BUG_INTRODUCED_AT, which is what "broken since <commit>"
# should recover.
# ---------------------------------------------------------------------------

BUG_INTRODUCED_AT = 130


def test_regression_after_commit() -> None:
    seq = int(os.environ.get("FLAKEMAP_DEMO_COMMIT_SEQ", "0"))
    if seq >= BUG_INTRODUCED_AT:
        pytest.fail(f"off-by-one regression introduced at commit {BUG_INTRODUCED_AT}")


# ---------------------------------------------------------------------------
# Healthy but slower: exercises duration tracking without being flaky, so
# duration trend/correlation has a true-negative to be checked against.
# ---------------------------------------------------------------------------


def test_sleep_a_bit() -> None:
    time.sleep(0.004)
    assert True
