"""TCM v1.0 Bounded Public Candidate HTTP surface.

No payment layer is implemented here. This is a local discovery/inspection API.
Primary consumer: software agents. Human-readable docs are secondary.
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse, JSONResponse
from pydantic import BaseModel
from typing import Any, Dict

from tensegrity_control_mesh import (
    DECLARATION_SCHEMA_VERSION,
    agent_guidance,
    declaration_json_schema,
    inspect_declaration,
)

SERVICE_ID = "tcm.structural-inspection.v1.0"

app = FastAPI(
    title="Tensegrity Control Mesh",
    version="1.0.0",
    description=(
        "Deterministic structural inspection for declared control meshes. "
        "Injects ordered control losses and tests bounded re-equilibration. "
        "Structural evidence only; never authorizes execution."
    ),
    contact={"name": "Service operator"},
)

# Compact discovery object intended for autonomous clients.
CAPABILITIES = {
    "service_id": SERVICE_ID,
    "purpose": "structural_failure_inspection",
    "primary_consumer": "software_agent",
    "input_schema_version": DECLARATION_SCHEMA_VERSION,
    "deterministic": True,
    "uses_llm": False,
    "mutates_target_system": False,
    "authorizes_execution": False,
    "failure_model": {
        "type": "ordered_member_loss_injection",
        "supports_single_loss": True,
        "supports_cascading_loss": True,
        "bounded_re_equilibration": True,
    },
    "semantics": {
        "caller_must_declare_substitutability": True,
        "caller_must_declare_adjustment_bounds": True,
        "caller_must_declare_hard_controls": True,
        "service_infers_domain_semantics": False,
    },
    "interpretation": {
        "survival_ratio_is_probability": False,
        "feasible_means": "declared_structure_can_re_equilibrate_within_declared_bounds",
        "feasible_does_not_mean": "safe_or_authorized_to_execute",
    },
    "discovery": {
        "llms_txt": "/llms.txt",
        "schema": "/schema",
        "capabilities": "/capabilities",
        "openapi": "/openapi.json",
        "inspect": "/inspect",
    },
    "resource_limits": {
        "max_controls": 20,
        "max_depth": 2,
        "max_cases": 1000,
    },
    "commercial_policy": {
        "planned_price": {"amount": "0.01", "currency": "USDC", "unit": "inspection"},
        "payment_enforced": False,
        "note": "Price is fixed for the future paid endpoint; v1.0 public-candidate testing does not yet enforce payment."
    },
    "payment": {
        "required": False,
        "protocol": None,
        "note": "v1.0 does not yet enforce x402 or any payment protocol",
    },
}

LLMS_TXT = """# Tensegrity Control Mesh (TCM) v1.0
> Agent-first deterministic structural failure inspection.

Use when you need to test whether a declared control structure can remain mathematically balanced after one or more declared controls are removed.

DO:
1. GET /capabilities
2. GET /schema
3. Build a tcm.control.v0.6 declaration.
4. POST it to /inspect.
5. Treat the result as structural evidence only.

DO NOT:
- infer that `feasible=true` authorizes execution;
- treat survival_ratio as a probability or safety score;
- assume semantic substitutability that was not declared;
- expect this service to mutate, repair, stop, or control the target system.

Important fields:
- direction: abstract balance sign, `negative` or `positive`; not physical direction.
- mode: `fixed` or `adaptive`.
- adaptive bounds: min_weight and max_weight.
- hard=true: non-adjustable; excluded from injected losses by default.
- inspection.max_depth: ordered failure depth.

Endpoints:
GET /capabilities
GET /schema
GET /openapi.json
POST /inspect

No payment is enforced in v1.0 public-candidate testing.
"""


@app.get("/", include_in_schema=False)
def root():
    return {
        "service_id": SERVICE_ID,
        "agent_discovery": "/llms.txt",
        "capabilities": "/capabilities",
        "schema": "/schema",
        "inspect": "/inspect",
    }


@app.get("/llms.txt", response_class=PlainTextResponse, tags=["discovery"])
def llms_txt():
    return LLMS_TXT


@app.get("/capabilities", tags=["discovery"])
def capabilities():
    return CAPABILITIES


@app.get("/schema", tags=["discovery"])
def schema():
    return JSONResponse(content=declaration_json_schema())


@app.post(
    "/inspect",
    tags=["inspection"],
    openapi_extra={
        "x-agent-guidance": (
            "Fetch /capabilities and /schema first. Submit a tcm.control.v0.6 "
            "declaration. Result is structural evidence only and never grants execution."
        )
    },
)
def inspect(payload: Dict[str, Any]):
    try:
        return inspect_declaration(payload)
    except (ValueError, KeyError) as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "invalid_control_declaration",
                "message": str(exc),
                "schema": "/schema",
                "guidance": "/llms.txt",
            },
        ) from exc
