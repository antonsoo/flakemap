"""Controlled outcomes for real pytest JUnit serialization; failures are intentional."""

from collections.abc import Iterator

import pytest


def test_pass() -> None:
    assert 2 + 2 == 4


def test_failure() -> None:
    pytest.fail("controlled assertion failure")


@pytest.fixture
def setup_error() -> None:
    raise RuntimeError("controlled setup error")


def test_error(setup_error: None) -> None:
    pass


def test_skip() -> None:
    pytest.skip("controlled skip")


@pytest.fixture
def teardown_error() -> Iterator[None]:
    yield
    raise RuntimeError("controlled teardown error")


def test_pass_then_teardown_error(teardown_error: None) -> None:
    assert True


def test_failure_then_teardown_error(teardown_error: None) -> None:
    pytest.fail("controlled call failure before teardown")


def test_subtests(subtests: pytest.Subtests) -> None:
    for number in range(3):
        with subtests.test(number=number):
            assert number == 0
