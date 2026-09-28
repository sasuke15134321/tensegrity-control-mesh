"""x402 payment boundary for Tensegrity Control Mesh."""

from __future__ import annotations

import json
import os
from pathlib import Path

from payment_verifier import _generate_cdp_jwt
from tensegrity_control_mesh import inspect_declaration

from x402 import x402ResourceServer
from x402.http.middleware.fastapi import payment_middleware
from x402.http.types import RouteConfig, PaymentOption
from x402.http.facilitator_client import HTTPFacilitatorClient
from x402.http.facilitator_client_base import FacilitatorConfig, CreateHeadersAuthProvider
from x402.mechanisms.evm.exact.register import register_exact_evm_server
from x402.extensions.bazaar import declare_discovery_extension, OutputConfig


TEST_MODE = os.getenv("TEST_MODE", "false").lower() == "true"
WALLET_ADDRESS = os.getenv("WALLET_ADDRESS", "")
PRICE_USDC = os.getenv("PRICE_USDC", "0.01")

NETWORK = "eip155:8453"
CDP_BASE_URL = "https://api.cdp.coinbase.com/platform/v2/x402"


def _create_cdp_headers():
    return {
        "supported": {
            "Authorization": "Bearer " + _generate_cdp_jwt(
                "GET", "/platform/v2/x402/supported"
            )
        },
        "verify": {
            "Authorization": "Bearer " + _generate_cdp_jwt(
                "POST", "/platform/v2/x402/verify"
            )
        },
        "settle": {
            "Authorization": "Bearer " + _generate_cdp_jwt(
                "POST", "/platform/v2/x402/settle"
            )
        },
    }


_cdp_auth = CreateHeadersAuthProvider(_create_cdp_headers)

_facilitator = HTTPFacilitatorClient(
    FacilitatorConfig(
        url=CDP_BASE_URL,
        auth_provider=_cdp_auth,
    )
)

_x402_server = x402ResourceServer(_facilitator)
register_exact_evm_server(_x402_server, NETWORK)


_fixture_path = Path(__file__).parent / "agent_task_fixture.json"

with _fixture_path.open(encoding="utf-8") as f:
    _bazaar_input = json.load(f)

_bazaar_output = inspect_declaration(_bazaar_input)


_bazaar_extension = declare_discovery_extension(
    input=_bazaar_input,
    body_type="json",
    output=OutputConfig(
        example=_bazaar_output,
        schema={
            "type": "object",
            "required": [
                "schema_version",
                "system_id",
                "initial_state",
                "inspection",
                "interpretation",
            ],
            "properties": {
                "schema_version": {"type": "string"},
                "system_id": {"type": "string"},
                "initial_state": {"type": "object"},
                "inspection": {"type": "object"},
                "interpretation": {"type": "object"},
            },
        },
    ),
)


_x402_routes = {
    "POST /inspect": RouteConfig(
        accepts=PaymentOption(
            scheme="exact",
            pay_to=WALLET_ADDRESS,
            price="$" + PRICE_USDC,
            network=NETWORK,
            max_timeout_seconds=300,
        ),
        description=(
            "Deterministic structural failure inspection of a caller-declared "
            "control mesh. Structural evidence only; never authorizes execution. "
            "0.01 USDC per request."
        ),
        mime_type="application/json",
        extensions=_bazaar_extension,
    )
}


async def enforce_x402(request, call_next):
    if TEST_MODE:
        return await call_next(request)

    return await payment_middleware(
        _x402_routes,
        _x402_server,
    )(request, call_next)
