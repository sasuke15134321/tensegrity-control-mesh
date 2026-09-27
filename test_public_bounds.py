import json
import pytest
from fastapi.testclient import TestClient
from app import app

client = TestClient(app)

def base_control(i, direction):
    return {
        "id": f"c{i}",
        "direction": direction,
        "weight": 0.1,
        "capacity": 1.0,
        "mode": "adaptive",
        "min_weight": 0.01,
        "max_weight": 1.0,
        "hard": False,
    }

def declaration(n=4, depth=2, max_cases=1000):
    controls = []
    for i in range(n):
        controls.append(base_control(i, "negative" if i < n/2 else "positive"))
    return {
        "schema_version": "tcm.control.v0.6",
        "system_id": "bounded-test",
        "controls": controls,
        "inspection": {"max_depth": depth, "max_cases": max_cases},
    }

def test_capabilities_publish_exact_limits():
    c = client.get("/capabilities").json()
    assert c["resource_limits"] == {
        "max_controls": 20, "max_depth": 2, "max_cases": 1000
    }

def test_capabilities_publish_price_without_false_payment_claim():
    c = client.get("/capabilities").json()
    assert c["commercial_policy"]["planned_price"] == {
        "amount": "0.01", "currency": "USDC", "unit": "inspection"
    }
    assert c["commercial_policy"]["payment_enforced"] is False
    assert c["payment"]["required"] is False

def test_schema_matches_runtime_limits():
    s = client.get("/schema").json()
    assert s["properties"]["controls"]["maxItems"] == 20
    p = s["properties"]["inspection"]["properties"]
    assert p["max_depth"]["maximum"] == 2
    assert p["max_cases"]["maximum"] == 1000

def test_twenty_controls_are_accepted_with_bounded_case_budget():
    r = client.post("/inspect", json=declaration(20, depth=1, max_cases=1000))
    assert r.status_code == 200
    assert r.json()["inspection"]["tested_cases"] == 20

def test_twenty_one_controls_fail_before_inspection():
    r = client.post("/inspect", json=declaration(21, depth=1, max_cases=1000))
    assert r.status_code == 422
    assert "public limit of 20" in r.json()["detail"]["message"]

def test_depth_three_is_rejected():
    r = client.post("/inspect", json=declaration(4, depth=3))
    assert r.status_code == 422
    assert "max_depth must be between 1 and 2" in r.json()["detail"]["message"]

def test_max_cases_above_1000_is_rejected():
    r = client.post("/inspect", json=declaration(4, depth=2, max_cases=1001))
    assert r.status_code == 422
    assert "max_cases must be between 1 and 1000" in r.json()["detail"]["message"]

def test_case_explosion_is_stopped_by_declared_case_budget():
    # 20 singles + 380 ordered pairs = 400 cases; caller can set a lower ceiling.
    r = client.post("/inspect", json=declaration(20, depth=2, max_cases=100))
    assert r.status_code == 422
    assert "inspection exceeds max_cases" in r.json()["detail"]["message"]

def test_full_public_maximum_is_bounded_and_succeeds():
    r = client.post("/inspect", json=declaration(20, depth=2, max_cases=1000))
    assert r.status_code == 200
    assert r.json()["inspection"]["tested_cases"] == 400

def test_boolean_is_not_accepted_as_integer_depth():
    d = declaration()
    d["inspection"]["max_depth"] = True
    r = client.post("/inspect", json=d)
    assert r.status_code == 422
    assert "must be an integer" in r.json()["detail"]["message"]

def test_boolean_is_not_accepted_as_integer_max_cases():
    d = declaration()
    d["inspection"]["max_cases"] = True
    r = client.post("/inspect", json=d)
    assert r.status_code == 422
    assert "must be an integer" in r.json()["detail"]["message"]


def test_failed_cases_are_strict_json_safe():
    r = client.post("/inspect", json=declaration(20, depth=2, max_cases=1000))
    assert r.status_code == 200
    # Starlette strict JSON serialization itself is the primary assertion.
    body = r.json()
    failed = [c for c in body["inspection"]["cases"] if not c["survived"]]
    assert failed
    assert all(c["final_residual"] is None or isinstance(c["final_residual"], float)
               for c in failed)
