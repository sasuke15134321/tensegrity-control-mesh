import json
import pytest
from tensegrity_control_mesh import (
    DECLARATION_SCHEMA_VERSION,
    agent_guidance,
    declaration_json_schema,
    mesh_from_declaration,
    inspect_declaration,
)


def valid_decl():
    return {
        "schema_version": "tcm.control.v0.6",
        "system_id": "agent-test",
        "controls": [
            {"id": "a", "direction": "negative", "weight": 0.3, "capacity": 1.0,
             "mode": "adaptive", "min_weight": 0.1, "max_weight": 0.8},
            {"id": "b", "direction": "negative", "weight": 0.3, "capacity": 1.0,
             "mode": "adaptive", "min_weight": 0.1, "max_weight": 0.8},
            {"id": "c", "direction": "positive", "weight": 0.3, "capacity": 1.0,
             "mode": "adaptive", "min_weight": 0.1, "max_weight": 0.8},
            {"id": "d", "direction": "positive", "weight": 0.3, "capacity": 1.0,
             "mode": "adaptive", "min_weight": 0.1, "max_weight": 0.8},
        ],
        "inspection": {"max_depth": 2},
    }


def test_agent_one_call_inspection():
    r = inspect_declaration(valid_decl())
    assert r["schema_version"] == DECLARATION_SCHEMA_VERSION
    assert r["system_id"] == "agent-test"
    assert r["initial_state"]["balanced"]
    assert r["inspection"]["tested_cases"] == 16


def test_output_explicitly_denies_authorization_interpretation():
    r = inspect_declaration(valid_decl())
    assert r["interpretation"]["structural_only"] is True
    assert r["interpretation"]["authorizes_execution"] is False
    assert r["interpretation"]["survival_ratio_is_probability"] is False


def test_schema_is_machine_readable_and_closed():
    s = declaration_json_schema()
    assert s["$schema"].endswith("2020-12/schema")
    assert s["additionalProperties"] is False
    assert "controls" in s["required"]


def test_guidance_is_compact():
    g = agent_guidance()
    assert len(g.split()) < 220
    assert "does not authorize execution" in g.lower()


def test_unknown_fields_fail_closed():
    d = valid_decl()
    d["mystery"] = 1
    with pytest.raises(ValueError, match="unknown fields"):
        inspect_declaration(d)


def test_missing_direction_fails_closed():
    d = valid_decl()
    del d["controls"][0]["direction"]
    with pytest.raises(ValueError, match="missing required"):
        inspect_declaration(d)


def test_no_semantic_direction_inference():
    d = valid_decl()
    d["controls"][0]["direction"] = "camera"
    with pytest.raises(ValueError, match="direction"):
        inspect_declaration(d)


def test_both_directions_are_required():
    d = valid_decl()
    for c in d["controls"]:
        c["direction"] = "negative"
    with pytest.raises(ValueError, match="both negative and positive"):
        inspect_declaration(d)


def test_fixed_control_cannot_smuggle_bounds():
    d = valid_decl()
    d["controls"][0]["mode"] = "fixed"
    with pytest.raises(ValueError, match="require mode='adaptive'"):
        inspect_declaration(d)


def test_hard_control_is_not_adjusted():
    d = valid_decl()
    d["controls"][0]["hard"] = True
    mesh = mesh_from_declaration(d)
    m = next(x for x in mesh.members if x.member_id == "a")
    assert m.hard is True


def test_wrong_schema_version_rejected():
    d = valid_decl()
    d["schema_version"] = "tcm.control.v9"
    with pytest.raises(ValueError, match="unsupported schema_version"):
        inspect_declaration(d)


def test_duplicate_ids_rejected():
    d = valid_decl()
    d["controls"][1]["id"] = "a"
    with pytest.raises(ValueError, match="duplicate control id"):
        inspect_declaration(d)


def test_reserved_ids_rejected():
    d = valid_decl()
    d["controls"][0]["id"] = "__action__"
    with pytest.raises(ValueError, match="cannot start"):
        inspect_declaration(d)


def test_weight_above_capacity_rejected():
    d = valid_decl()
    d["controls"][0]["weight"] = 2.0
    with pytest.raises(ValueError, match="cannot exceed capacity"):
        inspect_declaration(d)


def test_example_file_roundtrip():
    with open("example.declaration.json", encoding="utf-8") as f:
        d = json.load(f)
    r = inspect_declaration(d)
    assert r["initial_state"]["balanced"]
