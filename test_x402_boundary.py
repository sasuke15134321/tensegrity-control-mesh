import os

# This test suite validates the x402 configuration boundary only.
# It must not contact the facilitator or perform a real payment.
os.environ["TEST_MODE"] = "true"

import x402_runtime as x
from fastapi.testclient import TestClient
from app import app


def _options(route):
    """Normalize x402 single/multiple PaymentOption representations."""
    accepts = route.accepts
    if isinstance(accepts, (list, tuple)):
        return list(accepts)
    return [accepts]


def test_only_inspect_is_x402_protected():
    assert set(x._x402_routes.keys()) == {"POST /inspect"}


def test_x402_price_scheme_and_network():
    route = x._x402_routes["POST /inspect"]
    options = _options(route)

    assert len(options) == 1

    option = options[0]

    assert option.scheme == "exact"
    assert option.price == "$0.01"
    assert option.network == "eip155:8453"


def test_x402_route_metadata():
    route = x._x402_routes["POST /inspect"]

    assert route.mime_type == "application/json"
    assert route.description
    assert "0.01 USDC" in route.description
    assert "never authorizes execution" in route.description


def test_bazaar_extension_is_declared():
    route = x._x402_routes["POST /inspect"]

    assert isinstance(route.extensions, dict)
    assert "bazaar" in route.extensions

    bazaar = route.extensions["bazaar"]

    assert "info" in bazaar
    assert "schema" in bazaar

    info = bazaar["info"]

    assert "input" in info
    assert "output" in info
    assert info["input"]["type"] == "http"
    assert info["input"]["bodyType"] == "json"

    output = info["output"]
    assert output["type"] == "json"
    assert "example" in output


def test_public_x402_discovery_endpoint():
    client = TestClient(app)

    response = client.get("/.well-known/x402.json")

    assert response.status_code == 200

    data = response.json()
    assert data["endpoints"]

    endpoint = data["endpoints"][0]

    assert endpoint["path"] == "/inspect"
    assert endpoint["method"] == "POST"
    assert endpoint["price"] == "0.01"
    assert endpoint["currency"] == "USDC"


def test_discovery_endpoints_remain_free_in_test_mode():
    client = TestClient(app)

    for path in (
        "/capabilities",
        "/schema",
        "/llms.txt",
        "/.well-known/x402.json",
    ):
        response = client.get(path)
        assert response.status_code == 200


def test_test_mode_does_not_claim_payment_required():
    client = TestClient(app)

    capabilities = client.get("/capabilities").json()

    assert capabilities["commercial_policy"]["planned_price"] == {
        "amount": "0.01",
        "currency": "USDC",
        "unit": "inspection",
    }

    assert capabilities["commercial_policy"]["payment_enforced"] is False
    assert capabilities["payment"]["required"] is False
    assert capabilities["payment"]["protocol"] == "x402"
    assert capabilities["payment"]["network"] == "eip155:8453"
    assert capabilities["payment"]["price"] == "0.01"
    assert capabilities["payment"]["bazaar_extension"] is True
