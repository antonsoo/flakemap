"""Controlled failures against the capture script's real loopback HTTP service."""

import json
import os
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest


def request(endpoint: str) -> tuple[int, dict[str, object]]:
    try:
        response = urlopen(os.environ["CAPTURE_SERVICE_URL"] + endpoint, timeout=2)
    except HTTPError as error:
        response = error
    with response:
        return response.status, json.loads(response.read())


def test_inventory_endpoint() -> None:
    status, body = request("/inventory")
    assert status == 200, f"Inventory endpoint returned HTTP {status}"
    assert body["quantity"] == 3


def test_shipping_endpoint() -> None:
    status, body = request("/shipping")
    assert status == 200, f"Shipping endpoint returned HTTP {status}"
    assert body["days"] == 2


def test_pricing_endpoint() -> None:
    status, body = request("/pricing")
    assert status == 200, f"Pricing endpoint returned HTTP {status}"
    assert body["cents"] == 1200


def test_optional_endpoint() -> None:
    if os.environ["CAPTURE_RUN"] == "4":
        pytest.skip("Deliberately unscheduled optional check in capture run 4")
    status, body = request("/optional")
    assert status == 200, f"Optional endpoint returned HTTP {status}"
    assert body["enabled"] is True


def test_independent_math() -> None:
    # An intentionally incorrect expectation creates one independent failure.
    expected = 5 if os.environ["CAPTURE_RUN"] == "7" else 4
    actual = 2 + 2
    assert actual == expected


def test_healthy_control() -> None:
    assert "invoice".upper() == "INVOICE"
