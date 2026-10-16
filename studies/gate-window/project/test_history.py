"""Controlled runner input: an old failure, then missing/skipped coverage."""

import os

import pytest

SEQUENCE = int(os.environ["FLAKEMAP_STUDY_SEQUENCE"])


def test_control():
    assert 2 + 2 == 4


def test_removed_after_build_35():
    assert SEQUENCE not in {30, 32, 34}, "controlled old failure"


def test_skipped_after_build_35():
    if SEQUENCE >= 36:
        pytest.skip("controlled retirement: no execution in later builds")
    assert SEQUENCE not in {30, 32, 34}, "controlled old failure"
