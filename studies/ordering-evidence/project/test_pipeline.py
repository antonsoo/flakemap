"""Controlled pytest failures for Flakemap's ordering study, not a real service."""

import os


def test_pipeline() -> None:
    capture_index = int(os.environ.get("FLAKEMAP_CAPTURE_INDEX", "0"))
    assert capture_index < 20, "controlled pipeline failure"


def test_dependency() -> None:
    capture_index = int(os.environ.get("FLAKEMAP_CAPTURE_INDEX", "0"))
    assert capture_index < 20, "same controlled failure condition"
