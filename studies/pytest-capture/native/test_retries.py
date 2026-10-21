"""Controlled outcomes emitted by actual pytest, not hand-authored JUnit XML."""

import json
import os
from collections import defaultdict
from pathlib import Path

import pytest

_calls = defaultdict(int)


@pytest.fixture
def attempt(request):
    _calls[request.node.nodeid] += 1
    number = _calls[request.node.nodeid]
    # An independent execution ledger: the companion reporter never reads it.
    destination = os.environ.get("FLAKEMAP_EXECUTION_LOG")
    if destination:
        worker = os.environ.get("PYTEST_XDIST_WORKER", "main")
        with Path(f"{destination}-{worker}.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"nodeid": request.node.nodeid, "attempt": number}) + "\n")
    return number


def test_pass(attempt):
    assert attempt == 1


def test_recovered_call(attempt):
    assert attempt >= 3, "connection not ready"


def test_exhausted_call(attempt):
    pytest.fail("service never ready")


@pytest.fixture
def setup_recovers(attempt):
    assert attempt >= 2, "setup not ready"


def test_recovered_setup(setup_recovers):
    pass


@pytest.fixture
def setup_fails(attempt):
    pytest.fail("setup never ready")


def test_exhausted_setup(setup_fails):
    pytest.fail("call must not execute")


@pytest.fixture
def teardown_recovers(attempt):
    yield
    assert attempt >= 2, "teardown not ready"


def test_recovered_teardown(teardown_recovers):
    pass


@pytest.fixture
def teardown_fails(attempt):
    yield
    pytest.fail("teardown never ready")


def test_exhausted_teardown(teardown_fails):
    pass


@pytest.fixture
def two_phases_recover(attempt):
    yield attempt
    assert attempt >= 2, "teardown failed too"


def test_recovered_call_and_teardown(two_phases_recover):
    assert two_phases_recover >= 2, "call failed first"


def test_exhausted_call_and_teardown(teardown_fails):
    pytest.fail("call never ready either")


@pytest.mark.skip(reason="not executed")
def test_skipped():
    pytest.fail("call must not execute")


@pytest.mark.xfail(reason="known failure")
def test_xfail(attempt):
    pytest.fail("expected failure")


@pytest.mark.xfail(reason="non-strict unexpected pass")
def test_xpass(attempt):
    pass


@pytest.mark.xfail(strict=True, reason="strict unexpected pass")
def test_strict_xpass(attempt):
    pass


@pytest.mark.parametrize("value", ["<xml>&[name]", "ordinary"])
def test_parameter_identity(value, attempt):
    assert value
