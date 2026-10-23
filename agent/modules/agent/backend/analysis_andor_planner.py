"""Backward completion planning on the preprocessing dependency graph (algorithm 4).

The workflow layer is an AND-OR graph: a product requirement is an OR node
(already present, or produced by any step whose outputs satisfy it); a step is
an AND node (all of its inputs must be satisfied).

  cost(q) = 0                                   if an observed product satisfies q
          = min over steps t producing q of     c(t) + sum cost(q') over inputs q' of t
          = infinity                            if no step applies (with reasons)

Attribute constraints propagate backwards (WINGS style): attributes an output
inherits from its inputs (subject, hemisphere, species, ...) are pushed down to
the input requirements; attributes an output sets (e.g. space=fsLR_32k) must
match the requirement directly. Steps are excluded when required software is
observed missing or the requirement's species is not allowed.

Two solvers:
  plan()          memoised recursion with cycle guard; returns a step list in
                  dependency order and a reason chain for every infeasible goal.
                  Several targets are merged and shared steps counted once.
  optimal_plan()  exact minimum-cost step set by subset enumeration with forward
                  closure (the PrimateX graph has 14 steps, so 2^14 subsets);
                  used to certify plan() and in the planning experiment.
"""
from __future__ import annotations

import itertools
import math
from typing import Iterable, Mapping, Sequence

from .analysis_csp_matching import TypeHierarchy

INF = math.inf


def _matches(attrs: Mapping[str, object], constraint: Mapping[str, object]) -> bool:
    for attr, want in constraint.items():
        have = attrs.get(attr)
        if isinstance(want, Mapping) and "in" in want:
            if have not in set(want["in"]):
                return False
        elif have != want:
            return False
    return True


def satisfied(requirement: Mapping[str, object], products: Iterable[Mapping[str, object]],
              hierarchy: TypeHierarchy) -> bool:
    return any(hierarchy.subsumes(str(requirement["type"]), str(p["type"]))
               and _matches(p.get("attrs", {}), requirement.get("attrs", {}))
               for p in products)


def _key(requirement: Mapping[str, object]) -> tuple:
    def norm(v):
        if isinstance(v, Mapping):
            return tuple(sorted((k, tuple(sorted(map(str, x))) if isinstance(x, (list, tuple, set)) else str(x))
                                for k, x in v.items()))
        return str(v)
    return (str(requirement["type"]), tuple(sorted((k, norm(v)) for k, v in requirement.get("attrs", {}).items())))


def _output_for(step: Mapping[str, object], requirement: Mapping[str, object],
                hierarchy: TypeHierarchy):
    """Return (output, pushed_down_attrs) if one output can satisfy the requirement."""
    for output in step["outputs"]:
        if not hierarchy.subsumes(str(requirement["type"]), str(output["type"])):
            continue
        sets = output.get("set", {})
        inherits = set(output.get("inherit", []))
        pushed, ok = {}, True
        for attr, want in requirement.get("attrs", {}).items():
            if attr in sets:
                if not _matches({attr: sets[attr]}, {attr: want}):
                    ok = False
                    break
            elif attr in inherits:
                pushed[attr] = want
            else:
                ok = False  # attribute neither set nor inherited: cannot be guaranteed
                break
        if ok:
            return output, pushed
    return None, None


def _step_blocked(step, requirement, software) -> str | None:
    missing = [s for s in step.get("software", []) if software.get(s) is False]
    if missing:
        return f"software unavailable: {', '.join(missing)}"
    species = requirement.get("attrs", {}).get("species")
    allowed = step.get("species_allowed")
    if allowed and isinstance(species, str) and species not in allowed:
        return f"species {species} not allowed"
    return None


def plan(targets: Sequence[Mapping[str, object]], products: Sequence[Mapping[str, object]],
         steps: Sequence[Mapping[str, object]], hierarchy: TypeHierarchy,
         software: Mapping[str, bool] | None = None) -> dict:
    software = software or {}
    memo: dict[tuple, tuple] = {}

    def solve(req, stack):
        key = _key(req)
        if satisfied(req, products, hierarchy):
            return 0.0, [], []
        if key in memo:
            return memo[key]
        if key in stack:
            return INF, [], [f"cycle at {req['type']}"]
        best = (INF, [], [])
        reasons = []
        for step in steps:
            output, pushed = _output_for(step, req, hierarchy)
            if output is None:
                continue
            blocked = _step_blocked(step, req, software)
            if blocked:
                reasons.append(f"{step['id']}: {blocked}")
                continue
            total, order, sub_reasons = float(step.get("cost", 1)), [], []
            for inp in step["inputs"]:
                sub = {"type": inp["type"], "attrs": {**inp.get("attrs", {}), **pushed}}
                c, o, r = solve(sub, stack | {key})
                if c == INF:
                    total = INF
                    sub_reasons.extend(f"{step['id']} <- {x}" for x in r)
                    break
                total += c
                order.extend(x for x in o if x not in order)
            if total == INF:
                reasons.extend(sub_reasons)
                continue
            order = order + [step["id"]]
            # shared steps in the subtree are counted once
            unique = sum(float(next(s for s in steps if s["id"] == sid).get("cost", 1)) for sid in order)
            if unique < best[0]:
                best = (unique, order, [])
        if best[0] == INF:
            best = (INF, [], reasons or [f"no step produces {req['type']}"])
        memo[key] = best
        return best

    merged, results = [], []
    for target in targets:
        c, order, reasons = solve(target, frozenset())
        results.append({"target": target, "cost": c, "steps": order, "reasons": reasons})
        if c < INF:
            merged.extend(s for s in order if s not in merged)
    cost = sum(float(next(s for s in steps if s["id"] == sid).get("cost", 1)) for sid in merged)
    feasible = all(r["cost"] < INF for r in results)
    return {"feasible": feasible, "steps": merged if feasible else [], "cost": cost if feasible else INF,
            "per_target": results}


def _forward(selected, products, steps, hierarchy):
    available = [dict(p) for p in products]
    changed = True
    applied = set()
    while changed:
        changed = False
        for step in steps:
            if step["id"] not in selected or step["id"] in applied:
                continue
            sources = []
            for inp in step["inputs"]:
                match = next((p for p in available if hierarchy.subsumes(str(inp["type"]), str(p["type"]))
                              and _matches(p.get("attrs", {}), inp.get("attrs", {}))), None)
                if match is None:
                    break
                sources.append(match)
            else:
                for output in step["outputs"]:
                    attrs = {a: sources[0].get("attrs", {}).get(a) for a in output.get("inherit", [])} if sources else {}
                    attrs.update(output.get("set", {}))
                    available.append({"id": f"{step['id']}:{output['type']}", "type": output["type"], "attrs": attrs})
                applied.add(step["id"])
                changed = True
    return available


def optimal_plan(targets, products, steps, hierarchy, software=None, max_steps=20) -> dict:
    software = software or {}
    usable = [s for s in steps
              if not any(software.get(x) is False for x in s.get("software", []))]
    if len(usable) > max_steps:
        raise ValueError("Too many steps for exact enumeration")
    best = (INF, None)
    ids = [s["id"] for s in usable]
    cost_of = {s["id"]: float(s.get("cost", 1)) for s in usable}
    for r in range(len(ids) + 1):
        for subset in itertools.combinations(ids, r):
            c = sum(cost_of[i] for i in subset)
            if c >= best[0]:
                continue
            avail = _forward(set(subset), products, usable, hierarchy)
            if all(satisfied(t, avail, hierarchy) for t in targets):
                best = (c, set(subset))
    return {"feasible": best[1] is not None, "cost": best[0], "steps": sorted(best[1]) if best[1] else []}


def steps_from_workflow(document: Mapping[str, object]) -> list[dict]:
    """Normalise knowledge_analysis/workflow_steps.json into the planner format."""
    out = []
    for step in document["steps"]:  # type: ignore[index]
        inputs = []
        for inp in step.get("inputs") or []:
            attrs = {}
            for name, rule in (inp.get("attributes") or {}).items():
                if isinstance(rule, Mapping) and isinstance(rule.get("in"), (list, tuple)):
                    attrs[name] = {"in": list(rule["in"])}
            inputs.append({"type": inp["type"], "attrs": attrs})
        outputs = []
        for o in step.get("outputs") or []:
            sets, inherit = {}, []
            for name, rule in (o.get("attribute_rules") or {}).items():
                if isinstance(rule, Mapping):
                    if "inherit" in rule:
                        inherit.append(name)
                    elif "value" in rule:
                        sets[name] = rule["value"]
                    elif "set" in rule:
                        sets[name] = rule["set"]
            for name in ("subject", "species", "hemisphere"):
                if name not in sets and name not in inherit:
                    inherit.append(name)
            outputs.append({"type": o["type"], "set": sets, "inherit": inherit})
        cost = step.get("cost")
        out.append({"id": step["id"], "inputs": inputs, "outputs": outputs,
                    "software": list(step.get("software") or []),
                    "species_allowed": list(step.get("species_allowed") or []),
                    "cost": float(cost.get("steps", 1)) if isinstance(cost, Mapping) else float(cost or 1)})
    return out
