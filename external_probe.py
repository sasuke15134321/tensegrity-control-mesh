#!/usr/bin/env python3
"""External black-box probe for TCM.

Uses only Python standard-library HTTP and no service implementation modules.
Give it a base URL and a caller-supplied declaration JSON.
"""
from __future__ import annotations
import argparse, json
from copy import deepcopy
from urllib.request import Request, urlopen
from urllib.error import HTTPError


def request(base, method, path, payload=None):
    url = base.rstrip("/") + path
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=10) as r:
            raw = r.read().decode("utf-8")
            ctype = r.headers.get("content-type", "")
            return r.status, (json.loads(raw) if "json" in ctype else raw)
    except HTTPError as e:
        raw = e.read().decode("utf-8")
        try:
            body = json.loads(raw)
        except Exception:
            body = raw
        return e.code, body


def run_probe(base, declaration, inject_error=False):
    trace = []

    def getj(path):
        trace.append(["GET", path])
        status, body = request(base, "GET", path)
        if status != 200:
            raise RuntimeError(f"GET {path} -> {status}")
        return body

    root = getj("/")
    caps = getj(root["capabilities"])
    schema = getj(root["schema"])

    checks = {
        "agent_consumer": caps.get("primary_consumer") == "software_agent",
        "deterministic": caps.get("deterministic") is True,
        "non_mutating": caps.get("mutates_target_system") is False,
        "non_authorizing": caps.get("authorizes_execution") is False,
        "schema_version_matches": (
            schema.get("properties", {}).get("schema_version", {}).get("const")
            == declaration.get("schema_version")
        ),
    }
    if not all(checks.values()):
        raise RuntimeError(f"discovery contract checks failed: {checks}")

    payload = deepcopy(declaration)
    if inject_error:
        payload["controls"][0].pop("direction", None)

    inspect_path = root["inspect"]
    trace.append(["POST", inspect_path])
    status, body = request(base, "POST", inspect_path, payload)

    recovered = False
    if status == 422:
        detail = body.get("detail", {})
        schema_path = detail.get("schema")
        guidance_path = detail.get("guidance")
        if not schema_path or not guidance_path:
            raise RuntimeError("422 did not provide machine recovery pointers")
        getj(schema_path)
        trace.append(["GET", guidance_path])
        g_status, _ = request(base, "GET", guidance_path)
        if g_status != 200:
            raise RuntimeError("guidance recovery failed")
        # Repair only from original caller declaration, never by guessing.
        trace.append(["POST", inspect_path])
        status, body = request(base, "POST", inspect_path, deepcopy(declaration))
        recovered = True

    if status != 200:
        raise RuntimeError(f"POST {inspect_path} -> {status}")

    interp = body.get("interpretation", {})
    interpretation_ok = (
        interp.get("authorizes_execution") is False
        and interp.get("survival_ratio_is_probability") is False
        and interp.get("structural_only") is True
    )
    if not interpretation_ok:
        raise RuntimeError("unsafe or ambiguous result interpretation contract")

    return {
        "ok": True,
        "network_black_box": True,
        "recovered_from_422": recovered,
        "checks": checks,
        "result_summary": {
            "system_id": body.get("system_id"),
            "balanced": body.get("initial_state", {}).get("balanced"),
            "tested_cases": body.get("inspection", {}).get("tested_cases"),
            "failed_cases": body.get("inspection", {}).get("failed_cases"),
            "single_point_failures": body.get("inspection", {}).get("single_point_failures"),
        },
        "interpretation": {
            "structural_evidence_only": True,
            "execution_authorized": False,
            "safety_probability_available": False,
        },
        "trace": trace,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("base_url")
    p.add_argument("declaration_json")
    p.add_argument("--inject-error", action="store_true")
    args = p.parse_args()
    with open(args.declaration_json, encoding="utf-8") as f:
        declaration = json.load(f)
    print(json.dumps(run_probe(args.base_url, declaration, args.inject_error), indent=2))


if __name__ == "__main__":
    main()
