"""Generic discovery client for TCM v0.8 black-box validation.

The client has no TCM engine imports and no domain-specific branches.
It starts with only a base HTTP client plus a task manifest supplied by its caller.
"""
from __future__ import annotations
from copy import deepcopy


class AgentProtocolError(RuntimeError):
    pass


class SemanticInputMissing(AgentProtocolError):
    pass


class DiscoveryAgent:
    def __init__(self, http_client):
        self.http = http_client
        self.trace = []
        self.root = None
        self.capabilities = None
        self.schema = None

    def _get_json(self, path):
        self.trace.append(("GET", path))
        r = self.http.get(path)
        if r.status_code != 200:
            raise AgentProtocolError(f"GET {path} -> {r.status_code}")
        return r.json()

    def bootstrap(self):
        # Only assumed knowledge: HTTP base root.
        self.root = self._get_json("/")
        for required in ("capabilities", "schema", "inspect"):
            if required not in self.root:
                raise AgentProtocolError(f"root missing discovery link: {required}")

        self.capabilities = self._get_json(self.root["capabilities"])
        self.schema = self._get_json(self.root["schema"])

        if self.capabilities.get("primary_consumer") != "software_agent":
            raise AgentProtocolError("service is not declared agent-consumable")
        if self.capabilities.get("purpose") != "structural_failure_inspection":
            raise AgentProtocolError("service purpose does not match structural inspection")
        return self

    def _validate_semantic_completeness(self, declaration):
        """Refuse to invent facts the service says the caller must declare."""
        semantics = self.capabilities["semantics"]
        controls = declaration.get("controls") or []
        if not controls:
            raise SemanticInputMissing("controls are required")

        if semantics.get("caller_must_declare_substitutability"):
            # Current v0.6 representation encodes the caller's structural relation
            # through explicit opposing direction plus adaptive/fixed declaration.
            for c in controls:
                if "direction" not in c:
                    raise SemanticInputMissing(f"{c.get('id','<unknown>')}: direction missing")
                if "mode" not in c:
                    raise SemanticInputMissing(f"{c.get('id','<unknown>')}: mode missing")

        if semantics.get("caller_must_declare_adjustment_bounds"):
            for c in controls:
                if c.get("mode") == "adaptive":
                    if "min_weight" not in c or "max_weight" not in c:
                        raise SemanticInputMissing(
                            f"{c.get('id','<unknown>')}: adaptive bounds missing"
                        )

        if semantics.get("caller_must_declare_hard_controls"):
            for c in controls:
                if "hard" not in c:
                    raise SemanticInputMissing(f"{c.get('id','<unknown>')}: hard flag missing")

    def inspect(self, declaration, *, inject_client_error=False):
        if self.capabilities is None:
            self.bootstrap()

        self._validate_semantic_completeness(declaration)
        payload = deepcopy(declaration)

        # Test-only simulation of a client serialization error after semantic
        # validation. The recovery path must use the server's machine pointers.
        if inject_client_error:
            payload["controls"][0].pop("direction", None)

        inspect_path = self.root["inspect"]
        self.trace.append(("POST", inspect_path))
        r = self.http.post(inspect_path, json=payload)

        if r.status_code == 422:
            detail = r.json().get("detail", {})
            schema_path = detail.get("schema")
            guidance_path = detail.get("guidance")
            if not schema_path or not guidance_path:
                raise AgentProtocolError("422 lacks machine recovery pointers")

            # Re-fetch authoritative machine contract; do not guess.
            self.schema = self._get_json(schema_path)
            self.trace.append(("GET", guidance_path))
            g = self.http.get(guidance_path)
            if g.status_code != 200:
                raise AgentProtocolError("guidance recovery failed")

            # Repair only from the original caller-supplied declaration.
            # No missing semantic value is invented.
            payload = deepcopy(declaration)
            self.trace.append(("POST", inspect_path))
            r = self.http.post(inspect_path, json=payload)

        if r.status_code != 200:
            raise AgentProtocolError(f"inspection failed: {r.status_code}")

        result = r.json()
        interpretation = result.get("interpretation", {})
        if interpretation.get("authorizes_execution") is not False:
            raise AgentProtocolError("result does not explicitly deny execution authorization")
        if interpretation.get("survival_ratio_is_probability") is not False:
            raise AgentProtocolError("result does not explicitly deny probability interpretation")

        return {
            "result": result,
            "agent_interpretation": {
                "classification": "structural_evidence_only",
                "execution_authorized": False,
                "safety_probability_available": False,
            },
            "trace": list(self.trace),
        }
