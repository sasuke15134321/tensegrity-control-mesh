"""Tensegrity Control Mesh v0.3

Adds deterministic post-failure re-equilibration to v0.2.

This remains a dimensionless digital control-space abstraction, not a
mechanical tensegrity solver.

After a member is lost, v0.3 asks whether adjustable remaining members can
change signed force density within explicit bounds and restore equilibrium at
all free nodes.

No scipy dependency: bounded least-squares is solved deterministically by
enumerating active lower/free/upper states. This is intentionally suitable for
small control meshes, not large physical simulations.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import product
import math
from typing import Iterable, Mapping
import numpy as np


def _finite(x, name):
    x = float(x)
    if not math.isfinite(x):
        raise ValueError(f"{name} must be finite")
    return x


@dataclass(frozen=True)
class Node:
    node_id: str
    position: tuple[float, ...]
    anchored: bool = False
    def __post_init__(self):
        if not self.node_id or not self.position:
            raise ValueError("node_id and position are required")
        for x in self.position:
            _finite(x, "position")


@dataclass(frozen=True)
class Member:
    member_id: str
    a: str
    b: str
    force_density: float
    capacity: float
    adjustable: bool = False
    min_force_density: float | None = None
    max_force_density: float | None = None
    hard: bool = False

    def __post_init__(self):
        if not self.member_id or not self.a or not self.b or self.a == self.b:
            raise ValueError("valid member_id and distinct endpoints are required")
        q = _finite(self.force_density, "force_density")
        cap = _finite(self.capacity, "capacity")
        if q == 0 or cap <= 0:
            raise ValueError("force_density must be non-zero and capacity > 0")
        lo = self.min_force_density
        hi = self.max_force_density
        if self.adjustable:
            if lo is None or hi is None:
                # Preserve sign by default.
                if q > 0:
                    lo, hi = 1e-9, cap
                else:
                    lo, hi = -cap, -1e-9
                object.__setattr__(self, "min_force_density", lo)
                object.__setattr__(self, "max_force_density", hi)
            lo = _finite(self.min_force_density, "min_force_density")
            hi = _finite(self.max_force_density, "max_force_density")
            if lo > hi:
                raise ValueError("min_force_density must be <= max_force_density")
            if not (lo <= q <= hi):
                raise ValueError("initial force_density must lie inside adjustment bounds")
            if q > 0 and lo <= 0:
                raise ValueError("tension adjustment bounds must preserve positive sign")
            if q < 0 and hi >= 0:
                raise ValueError("compression adjustment bounds must preserve negative sign")

    @property
    def utilization(self):
        return abs(self.force_density) / self.capacity


@dataclass(frozen=True)
class RebalanceResult:
    feasible: bool
    residual: float
    force_densities: Mapping[str, float]
    changed_members: tuple[str, ...]
    reason: str

    def to_dict(self):
        return {
            "feasible": self.feasible,
            "residual": _json_finite(self.residual),
            "force_densities": dict(self.force_densities),
            "changed_members": list(self.changed_members),
            "reason": self.reason,
        }


class TensegrityControlMesh:
    def __init__(self, nodes: Iterable[Node], members: Iterable[Member], *, tolerance=1e-9):
        self.nodes = tuple(nodes)
        self.members = tuple(members)
        if not self.nodes or not self.members:
            raise ValueError("nodes and members are required")
        if len({n.node_id for n in self.nodes}) != len(self.nodes):
            raise ValueError("duplicate node_id")
        if len({m.member_id for m in self.members}) != len(self.members):
            raise ValueError("duplicate member_id")
        dims = {len(n.position) for n in self.nodes}
        if len(dims) != 1:
            raise ValueError("all nodes must have the same dimension")
        known = {n.node_id for n in self.nodes}
        for m in self.members:
            if m.a not in known or m.b not in known:
                raise ValueError("unknown member endpoint")
        self.tolerance = _finite(tolerance, "tolerance")
        if self.tolerance < 0:
            raise ValueError("tolerance must be >= 0")

    def _equilibrium_system(self, members):
        """Return A q = 0 for free-node equilibrium."""
        by_node = {n.node_id: n for n in self.nodes}
        free = [n for n in self.nodes if not n.anchored]
        dim = len(self.nodes[0].position)
        rows = len(free) * dim
        A = np.zeros((rows, len(members)), dtype=float)
        free_index = {n.node_id: i for i, n in enumerate(free)}
        for j, m in enumerate(members):
            a, b = by_node[m.a], by_node[m.b]
            delta = np.array(b.position) - np.array(a.position)
            if m.a in free_index:
                base = free_index[m.a] * dim
                A[base:base+dim, j] += delta
            if m.b in free_index:
                base = free_index[m.b] * dim
                A[base:base+dim, j] -= delta
        return A

    def equilibrium_residual(self, force_densities=None):
        qmap = force_densities or {m.member_id: m.force_density for m in self.members}
        A = self._equilibrium_system(self.members)
        q = np.array([qmap[m.member_id] for m in self.members], dtype=float)
        return float(np.linalg.norm(A @ q))

    def rebalance_after_loss(self, member_id: str) -> RebalanceResult:
        remaining = [m for m in self.members if m.member_id != member_id]
        if len(remaining) == len(self.members):
            raise KeyError(member_id)
        if not remaining:
            return RebalanceResult(False, math.inf, {}, (), "no_members_remaining")

        A = self._equilibrium_system(remaining)
        adjustable_idx = [i for i,m in enumerate(remaining) if m.adjustable and not m.hard]
        fixed_idx = [i for i,m in enumerate(remaining) if i not in adjustable_idx]
        base = {m.member_id: m.force_density for m in remaining}

        if not adjustable_idx:
            residual = float(np.linalg.norm(A @ np.array([m.force_density for m in remaining])))
            return RebalanceResult(
                residual <= self.tolerance, residual, base, (),
                "already_balanced" if residual <= self.tolerance else "no_adjustable_members"
            )

        Af = A[:, fixed_idx] if fixed_idx else np.zeros((A.shape[0], 0))
        qf = np.array([remaining[i].force_density for i in fixed_idx], dtype=float)
        b = -(Af @ qf) if fixed_idx else np.zeros(A.shape[0])
        Aa = A[:, adjustable_idx]
        adj = [remaining[i] for i in adjustable_idx]
        lower = np.array([m.min_force_density for m in adj], dtype=float)
        upper = np.array([m.max_force_density for m in adj], dtype=float)
        initial = np.array([m.force_density for m in adj], dtype=float)

        # state: -1 lower bound, 0 free, +1 upper bound.
        # Enumerating all active sets is deterministic and exact enough for small meshes.
        if len(adj) > 10:
            return RebalanceResult(False, math.inf, base, (), "too_many_adjustable_members")

        best = None
        for states in product((-1, 0, 1), repeat=len(adj)):
            x = np.zeros(len(adj), dtype=float)
            bound_cols = []
            free_cols = []
            for k, state in enumerate(states):
                if state == -1:
                    x[k] = lower[k]; bound_cols.append(k)
                elif state == 1:
                    x[k] = upper[k]; bound_cols.append(k)
                else:
                    free_cols.append(k)

            rhs = b.copy()
            if bound_cols:
                rhs = rhs - Aa[:, bound_cols] @ x[bound_cols]
            if free_cols:
                sol, *_ = np.linalg.lstsq(Aa[:, free_cols], rhs, rcond=None)
                x[free_cols] = sol

            if np.any(x < lower - self.tolerance) or np.any(x > upper + self.tolerance):
                continue
            residual = float(np.linalg.norm(Aa @ x - b))
            movement = float(np.linalg.norm(x - initial))
            candidate = (residual, movement, tuple(float(v) for v in x))
            if best is None or candidate < best:
                best = candidate

        if best is None:
            return RebalanceResult(False, math.inf, base, (), "no_bounded_solution")

        residual, _, values = best
        result = dict(base)
        changed = []
        for m, value in zip(adj, values):
            result[m.member_id] = value
            if abs(value - m.force_density) > self.tolerance:
                changed.append(m.member_id)

        feasible = residual <= self.tolerance
        return RebalanceResult(
            feasible=feasible,
            residual=residual,
            force_densities=result,
            changed_members=tuple(sorted(changed)),
            reason="rebalanced" if feasible else "insufficient_adjustment_range",
        )


@dataclass(frozen=True)
class ProgressiveStep:
    lost_member: str
    feasible: bool
    residual: float
    force_densities: Mapping[str, float]
    changed_members: tuple[str, ...]
    reason: str

    def to_dict(self):
        return {
            "lost_member": self.lost_member,
            "feasible": self.feasible,
            "residual": _json_finite(self.residual),
            "force_densities": dict(self.force_densities),
            "changed_members": list(self.changed_members),
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ProgressiveFailureResult:
    survived: bool
    failed_at_step: int | None
    steps: tuple[ProgressiveStep, ...]
    remaining_members: tuple[str, ...]

    def to_dict(self):
        return {
            "survived": self.survived,
            "failed_at_step": self.failed_at_step,
            "steps": [s.to_dict() for s in self.steps],
            "remaining_members": list(self.remaining_members),
        }


def _member_with_q(m: Member, q: float) -> Member:
    return Member(
        member_id=m.member_id,
        a=m.a,
        b=m.b,
        force_density=q,
        capacity=m.capacity,
        adjustable=m.adjustable,
        min_force_density=m.min_force_density,
        max_force_density=m.max_force_density,
        hard=m.hard,
    )


def progressive_failure(mesh: TensegrityControlMesh, loss_sequence) -> ProgressiveFailureResult:
    """Apply member losses sequentially, carrying each feasible rebalance forward.

    The original mesh is never mutated. A failed rebalance stops the sequence.
    Hard members may be lost if the caller explicitly supplies them in the loss
    sequence; this function treats that as structural loss, not as permission.
    A policy layer should normally prevent/route such events before this point.
    """
    current = mesh
    steps = []

    for step_no, lost in enumerate(tuple(loss_sequence), start=1):
        ids = {m.member_id for m in current.members}
        if lost not in ids:
            raise KeyError(lost)

        result = current.rebalance_after_loss(lost)
        steps.append(ProgressiveStep(
            lost_member=lost,
            feasible=result.feasible,
            residual=result.residual,
            force_densities=result.force_densities,
            changed_members=result.changed_members,
            reason=result.reason,
        ))

        remaining = [m for m in current.members if m.member_id != lost]
        if not result.feasible:
            return ProgressiveFailureResult(
                survived=False,
                failed_at_step=step_no,
                steps=tuple(steps),
                remaining_members=tuple(sorted(m.member_id for m in remaining)),
            )

        if not remaining:
            return ProgressiveFailureResult(
                survived=False,
                failed_at_step=step_no,
                steps=tuple(steps),
                remaining_members=(),
            )

        carried = [
            _member_with_q(m, result.force_densities[m.member_id])
            for m in remaining
        ]
        current = TensegrityControlMesh(
            current.nodes,
            carried,
            tolerance=current.tolerance,
        )

    return ProgressiveFailureResult(
        survived=True,
        failed_at_step=None,
        steps=tuple(steps),
        remaining_members=tuple(sorted(m.member_id for m in current.members)),
    )


@dataclass(frozen=True)
class InjectionCase:
    loss_sequence: tuple[str, ...]
    survived: bool
    failed_at_step: int | None
    final_residual: float
    remaining_members: tuple[str, ...]

    def to_dict(self):
        return {
            "loss_sequence": list(self.loss_sequence),
            "survived": self.survived,
            "failed_at_step": self.failed_at_step,
            "final_residual": _json_finite(self.final_residual),
            "remaining_members": list(self.remaining_members),
        }


@dataclass(frozen=True)
class StructuralInspectionReport:
    tested_cases: int
    survived_cases: int
    failed_cases: int
    survival_ratio: float
    max_depth: int
    single_point_failures: tuple[str, ...]
    minimal_failure_sequences: tuple[tuple[str, ...], ...]
    cases: tuple[InjectionCase, ...]

    def to_dict(self):
        return {
            "tested_cases": self.tested_cases,
            "survived_cases": self.survived_cases,
            "failed_cases": self.failed_cases,
            "survival_ratio": self.survival_ratio,
            "max_depth": self.max_depth,
            "single_point_failures": list(self.single_point_failures),
            "minimal_failure_sequences": [list(x) for x in self.minimal_failure_sequences],
            "cases": [c.to_dict() for c in self.cases],
        }


def inspect_structure(
    mesh: TensegrityControlMesh,
    *,
    max_depth: int = 2,
    include_hard: bool = False,
    max_cases: int = 10000,
) -> StructuralInspectionReport:
    """Exhaustively inject ordered member-loss sequences up to max_depth.

    This is a deterministic structural inspection, not a probability model.
    `survival_ratio` is the fraction of tested injection sequences that remain
    mathematically re-equilibratable; it is NOT a reliability probability.

    Hard members are excluded by default because their semantic/safety loss
    should normally be handled by policy/fuse logic rather than interpreted as
    an adjustable degradation scenario.
    """
    from itertools import permutations

    if not isinstance(max_depth, int) or max_depth < 1:
        raise ValueError("max_depth must be an integer >= 1")
    if not isinstance(max_cases, int) or max_cases < 1:
        raise ValueError("max_cases must be an integer >= 1")

    candidates = sorted(
        m.member_id for m in mesh.members
        if include_hard or not m.hard
    )
    if not candidates:
        raise ValueError("no injectable members")

    depth = min(max_depth, len(candidates))
    sequences = []
    for d in range(1, depth + 1):
        for seq in permutations(candidates, d):
            sequences.append(seq)
            if len(sequences) > max_cases:
                raise ValueError("inspection exceeds max_cases; reduce max_depth or mesh size")

    cases = []
    failures = []
    for seq in sequences:
        result = progressive_failure(mesh, seq)
        residual = result.steps[-1].residual if result.steps else 0.0
        case = InjectionCase(
            loss_sequence=tuple(seq),
            survived=result.survived,
            failed_at_step=result.failed_at_step,
            final_residual=residual,
            remaining_members=result.remaining_members,
        )
        cases.append(case)
        if not result.survived:
            failures.append(tuple(seq))

    single = tuple(sorted(seq[0] for seq in failures if len(seq) == 1))

    # Minimal means no proper prefix has already failed. Since progressive
    # failure stops at the first infeasible step, prefix-minimality is the
    # useful causal notion for an ordered cascade.
    failure_set = set(failures)
    minimal = []
    for seq in sorted(failures, key=lambda s: (len(s), s)):
        if not any(seq[:k] in failure_set for k in range(1, len(seq))):
            minimal.append(seq)

    survived = sum(1 for c in cases if c.survived)
    tested = len(cases)
    return StructuralInspectionReport(
        tested_cases=tested,
        survived_cases=survived,
        failed_cases=tested - survived,
        survival_ratio=survived / tested if tested else 0.0,
        max_depth=depth,
        single_point_failures=single,
        minimal_failure_sequences=tuple(minimal),
        cases=tuple(cases),
    )


# ---------------------------------------------------------------------------
# v0.6 Agent-first declaration adapter
# ---------------------------------------------------------------------------

DECLARATION_SCHEMA_VERSION = "tcm.control.v0.6"

def _json_finite(value):
    """Return a JSON-safe finite float, or None for NaN/Infinity."""
    v = float(value)
    return v if math.isfinite(v) else None

MAX_PUBLIC_CONTROLS = 20
MAX_PUBLIC_DEPTH = 2
MAX_PUBLIC_CASES = 1000

_AGENT_GUIDANCE = """TCM control inspection.
Purpose: test whether a declared control structure can re-equilibrate after injected control losses.
Input schema: tcm.control.v0.6.
Required: controls[].id, direction, weight, capacity.
direction is an abstract balance-axis sign: "negative" or "positive"; it is not physical direction.
mode: "fixed" or "adaptive". adaptive requires min_weight/max_weight or uses sign-preserving defaults.
hard=true marks a non-adjustable safety boundary and excludes it from injected losses unless inspection.include_hard=true.
TCM never infers semantic substitutability. The caller must declare direction, adjustability, bounds, and hard controls.
inspection.max_depth controls ordered loss depth. survival_ratio is tested-case coverage, not a safety probability.
A feasible result is structural evidence only; it does not authorize execution.
"""


def agent_guidance() -> str:
    return _AGENT_GUIDANCE


def declaration_json_schema() -> dict:
    """Machine-readable input contract for agents."""
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "urn:tcm:control:v0.6",
        "title": "TCM Agent Control Declaration",
        "type": "object",
        "additionalProperties": False,
        "required": ["schema_version", "system_id", "controls"],
        "properties": {
            "schema_version": {"const": DECLARATION_SCHEMA_VERSION},
            "system_id": {"type": "string", "minLength": 1},
            "controls": {
                "type": "array",
                "minItems": 2,
                "maxItems": MAX_PUBLIC_CONTROLS,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["id", "direction", "weight", "capacity"],
                    "properties": {
                        "id": {"type": "string", "minLength": 1},
                        "direction": {"enum": ["negative", "positive"]},
                        "weight": {"type": "number"},
                        "capacity": {"type": "number", "exclusiveMinimum": 0},
                        "mode": {"enum": ["fixed", "adaptive"], "default": "fixed"},
                        "min_weight": {"type": "number"},
                        "max_weight": {"type": "number"},
                        "hard": {"type": "boolean", "default": False},
                    },
                },
            },
            "inspection": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "max_depth": {"type": "integer", "minimum": 1, "maximum": MAX_PUBLIC_DEPTH, "default": 2},
                    "include_hard": {"type": "boolean", "default": False},
                    "max_cases": {"type": "integer", "minimum": 1, "maximum": MAX_PUBLIC_CASES, "default": MAX_PUBLIC_CASES},
                },
            },
        },
    }


def _require_keys(obj: dict, required: set[str], where: str):
    missing = sorted(required - set(obj))
    if missing:
        raise ValueError(f"{where}: missing required fields: {', '.join(missing)}")


def _reject_unknown(obj: dict, allowed: set[str], where: str):
    unknown = sorted(set(obj) - allowed)
    if unknown:
        raise ValueError(f"{where}: unknown fields: {', '.join(unknown)}")


def mesh_from_declaration(declaration: Mapping) -> TensegrityControlMesh:
    """Convert an agent-facing declaration into the internal 1D balance mesh.

    No semantic inference is performed.
    """
    if not isinstance(declaration, Mapping):
        raise ValueError("declaration must be an object")
    d = dict(declaration)
    allowed_top = {"schema_version", "system_id", "controls", "inspection"}
    _reject_unknown(d, allowed_top, "declaration")
    _require_keys(d, {"schema_version", "system_id", "controls"}, "declaration")

    if d["schema_version"] != DECLARATION_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported schema_version: expected {DECLARATION_SCHEMA_VERSION}"
        )
    if not isinstance(d["system_id"], str) or not d["system_id"].strip():
        raise ValueError("system_id must be a non-empty string")
    controls = d["controls"]
    if not isinstance(controls, list) or len(controls) < 2:
        raise ValueError("controls must be an array with at least 2 items")
    if len(controls) > MAX_PUBLIC_CONTROLS:
        raise ValueError(f"controls exceeds public limit of {MAX_PUBLIC_CONTROLS}")

    nodes = [
        Node("__negative__", (-1.0,), True),
        Node("__action__", (0.0,), False),
        Node("__positive__", (1.0,), True),
    ]
    members = []
    seen = set()
    sides = set()

    allowed_control = {
        "id", "direction", "weight", "capacity", "mode",
        "min_weight", "max_weight", "hard"
    }
    for i, raw in enumerate(controls):
        where = f"controls[{i}]"
        if not isinstance(raw, Mapping):
            raise ValueError(f"{where} must be an object")
        c = dict(raw)
        _reject_unknown(c, allowed_control, where)
        _require_keys(c, {"id", "direction", "weight", "capacity"}, where)

        cid = c["id"]
        if not isinstance(cid, str) or not cid:
            raise ValueError(f"{where}.id must be a non-empty string")
        if cid.startswith("__"):
            raise ValueError(f"{where}.id cannot start with '__'")
        if cid in seen:
            raise ValueError(f"duplicate control id: {cid}")
        seen.add(cid)

        direction = c["direction"]
        if direction not in {"negative", "positive"}:
            raise ValueError(f"{where}.direction must be 'negative' or 'positive'")
        sides.add(direction)

        weight = _finite(c["weight"], f"{where}.weight")
        if weight <= 0:
            raise ValueError(f"{where}.weight must be > 0")
        capacity = _finite(c["capacity"], f"{where}.capacity")
        if capacity <= 0:
            raise ValueError(f"{where}.capacity must be > 0")
        if weight > capacity:
            raise ValueError(f"{where}.weight cannot exceed capacity")

        mode = c.get("mode", "fixed")
        if mode not in {"fixed", "adaptive"}:
            raise ValueError(f"{where}.mode must be 'fixed' or 'adaptive'")
        hard = c.get("hard", False)
        if not isinstance(hard, bool):
            raise ValueError(f"{where}.hard must be boolean")

        adjustable = mode == "adaptive"
        min_w = c.get("min_weight")
        max_w = c.get("max_weight")
        if not adjustable and (min_w is not None or max_w is not None):
            raise ValueError(f"{where}: min_weight/max_weight require mode='adaptive'")
        if adjustable and ((min_w is None) != (max_w is None)):
            raise ValueError(f"{where}: adaptive bounds must provide both min_weight and max_weight")

        endpoint = "__negative__" if direction == "negative" else "__positive__"
        members.append(Member(
            member_id=cid,
            a="__action__",
            b=endpoint,
            force_density=weight,
            capacity=capacity,
            adjustable=adjustable,
            min_force_density=min_w,
            max_force_density=max_w,
            hard=hard,
        ))

    if sides != {"negative", "positive"}:
        raise ValueError("controls must include both negative and positive directions")

    return TensegrityControlMesh(nodes, members)


def inspect_declaration(declaration: Mapping) -> dict:
    """Agent-facing one-call adapter: declaration -> normalized inspection report."""
    mesh = mesh_from_declaration(declaration)
    cfg = dict(declaration.get("inspection") or {})
    _reject_unknown(cfg, {"max_depth", "include_hard", "max_cases"}, "inspection")

    max_depth = cfg.get("max_depth", 2)
    include_hard = cfg.get("include_hard", False)
    max_cases = cfg.get("max_cases", MAX_PUBLIC_CASES)
    if not isinstance(include_hard, bool):
        raise ValueError("inspection.include_hard must be boolean")
    if not isinstance(max_depth, int) or isinstance(max_depth, bool):
        raise ValueError("inspection.max_depth must be an integer")
    if max_depth < 1 or max_depth > MAX_PUBLIC_DEPTH:
        raise ValueError(
            f"inspection.max_depth must be between 1 and {MAX_PUBLIC_DEPTH}"
        )
    if not isinstance(max_cases, int) or isinstance(max_cases, bool):
        raise ValueError("inspection.max_cases must be an integer")
    if max_cases < 1 or max_cases > MAX_PUBLIC_CASES:
        raise ValueError(
            f"inspection.max_cases must be between 1 and {MAX_PUBLIC_CASES}"
        )

    report = inspect_structure(
        mesh,
        max_depth=max_depth,
        include_hard=include_hard,
        max_cases=max_cases,
    )
    initial_residual = mesh.equilibrium_residual()

    return {
        "schema_version": DECLARATION_SCHEMA_VERSION,
        "system_id": declaration["system_id"],
        "initial_state": {
            "balanced": initial_residual <= mesh.tolerance,
            "residual": _json_finite(initial_residual),
        },
        "inspection": report.to_dict(),
        "interpretation": {
            "structural_only": True,
            "authorizes_execution": False,
            "survival_ratio_is_probability": False,
        },
    }
