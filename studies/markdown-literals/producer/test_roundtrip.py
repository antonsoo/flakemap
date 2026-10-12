"""Controlled pytest IDs, not a production test-reliability history."""

import os

import pytest

LABELS = [
    "ordinary",
    "**bold**",
    "*glob*",
    "~~kept~~",
    "[source](https://example.invalid/reference)",
    "![literal](https://example.invalid/pixel.png)",
    "www.example.invalid/path",
    "engineer@example.invalid",
    r"literal\*star\*",
    "pipe|`tick` &copy; <tag>",
    "[nested `ticks`](https://example.invalid/nested)",
    "日本語_Δ_🙂",
]


@pytest.mark.parametrize("label", LABELS, ids=LABELS)
def test_roundtrip(label):
    assert label
    assert os.environ["CONTROLLED_OUTCOME"] == "pass", "controlled failure"
