"""Memoised AND-OR completion and an independent subset-enumeration oracle.

Plans describe typed workflow declarations, never permission to execute. Costs
count unique subject-stage invocations; shared derivations are paid once.
"""

from __future__ import annotations
import itertools
import json
import math
from functools import lru_cache
from collections.abc import Mapping
from .analysis_csp_matching import TypeHierarchy

INF = math.inf


def _matches(attrs, constraint):
    for attr, want in constraint.items():
        have = attrs.get(attr)
        if isinstance(want, Mapping) and "in" in want:
            if have not in want["in"]:
                return False
        elif have != want:
            return False
    return True


def _key(requirement):
    return (
        str(requirement["type"]),
        json.dumps(requirement.get("attrs", {}), sort_keys=True),
    )


def satisfied(requirement, products, hierarchy):
    return any(
        hierarchy.subsumes(requirement["type"], p["type"])
        and _matches(p.get("attrs", {}), requirement.get("attrs", {}))
        for p in products
    )


def _output_options(step, requirement, hierarchy):
    for output in step["outputs"]:
        if not hierarchy.subsumes(requirement["type"], output["type"]):
            continue
        pushed = {}
        for attr, want in requirement.get("attrs", {}).items():
            if attr in output.get("set", {}):
                if not _matches(output["set"], {attr: want}):
                    break
            elif attr in output.get("inherit", []):
                pushed[attr] = want
            elif _matches({}, {attr: want}):
                continue  # an explicitly allowed unknown attribute needs no guarantee
            else:
                break
        else:
            yield output, pushed


def _step_blocked(step, requirement, software):
    if step.get("eligible_for_planning") is False:
        return "step disabled: " + step.get(
            "implementation_status", "not eligible for planning"
        )
    missing = [s for s in step.get("software", []) if software.get(s) is False]
    if missing:
        return "software unavailable: " + ", ".join(missing)
    species = requirement.get("attrs", {}).get("species")
    allowed = step.get("species_allowed")
    if allowed and isinstance(species, str) and species not in allowed:
        return f"species {species} not allowed"
    return None


def _intersect(left, right):
    result = dict(left)
    for attr, want in right.items():
        if attr not in result:
            result[attr] = want
            continue
        old = result[attr]
        a = old.get("in") if isinstance(old, Mapping) and "in" in old else [old]
        b = want.get("in") if isinstance(want, Mapping) and "in" in want else [want]
        common = [x for x in a if x in b]
        if not common:
            return None
        result[attr] = common[0] if len(common) == 1 else {"in": common}
    return result


def _minimal(sets):
    kept = []
    for choice in sorted(set(sets), key=lambda s: (len(s), tuple(sorted(s)))):
        if not any(k <= choice for k in kept):
            kept.append(choice)
    return kept


def plan(targets, products, steps, hierarchy, software=None):
    """Retain nondominated AND-OR alternatives to minimise shared-step cost."""
    software = software or {}
    costs = {s["id"]: float(s.get("cost", 1)) for s in steps}

    def cost(ids):
        return sum(costs[x] for x in ids)

    @lru_cache(None)
    def solve(key, stack):
        req = {"type": key[0], "attrs": json.loads(key[1])}
        if satisfied(req, products, hierarchy):
            return (frozenset(),), ()
        if key in stack:
            return (), (f"cycle at {req['type']}",)
        choices, reasons = [], []
        for step in steps:
            for output, pushed in _output_options(step, req, hierarchy):
                blocked = _step_blocked(step, req, software)
                if blocked:
                    reasons.append(f"{req['type']} <- {step['id']} <- {blocked}")
                    continue
                combined = [frozenset({step["id"]})]
                for inp in step["inputs"]:
                    attrs = _intersect(inp.get("attrs", {}), pushed)
                    if attrs is None:
                        reasons.append(
                            f"{req['type']} <- {step['id']} <- incompatible input attributes"
                        )
                        combined = []
                        break
                    sub, why = solve(
                        _key({"type": inp["type"], "attrs": attrs}), stack | {key}
                    )
                    if not sub:
                        reasons.extend(
                            f"{req['type']} <- {step['id']} <- {x}" for x in why
                        )
                        combined = []
                        break
                    combined = _minimal(a | b for a in combined for b in sub)
                choices.extend(combined)
        return tuple(_minimal(choices)), tuple(
            dict.fromkeys(
                reasons or [f"no step produces {req['type']} with requested attributes"]
            )
        )

    combined, results = [frozenset()], []
    for target in targets:
        choices, reasons = solve(_key(target), frozenset())
        best = (
            min(choices, key=lambda x: (cost(x), tuple(sorted(x)))) if choices else None
        )
        results.append(
            {
                "target": target,
                "cost": cost(best) if best is not None else INF,
                "steps": sorted(best) if best else [],
                "reasons": [] if choices else list(reasons),
            }
        )
        combined = _minimal(a | b for a in combined for b in choices)
    for selected in sorted(combined, key=lambda x: (cost(x), tuple(sorted(x)))):
        available, order = _forward(
            selected, products, steps, hierarchy, software, return_order=True
        )
        if all(satisfied(t, available, hierarchy) for t in targets):
            return {
                "feasible": True,
                "steps": order,
                "cost": cost(selected),
                "per_target": results,
            }
    if all(r["cost"] < INF for r in results):
        for r in results:
            r["reasons"] = ["No jointly compatible workflow input binding"]
    return {"feasible": False, "steps": [], "cost": INF, "per_target": results}


def _bindings(inputs, available, hierarchy, bound=(), all_inputs=None):
    all_inputs = inputs if all_inputs is None else all_inputs
    if not inputs:
        yield bound
        return
    inp = inputs[0]
    for p in available:
        if not hierarchy.subsumes(inp["type"], p["type"]) or not _matches(
            p.get("attrs", {}), inp.get("attrs", {})
        ):
            continue
        # Subject and species are shared stage identity. Bilateral inputs may
        # deliberately have different hemispheres and mesh cardinalities.
        if any(
            any(
                a.get("attrs", {}).get(k) is not None
                and p.get("attrs", {}).get(k) is not None
                and a["attrs"][k] != p["attrs"][k]
                for k in ("subject", "species")
            )
            for a in bound
        ):
            continue
        compatible = True
        for index, prior in enumerate(bound):
            a, b = prior.get("attrs", {}), p.get("attrs", {})
            left = all_inputs[index].get("attrs", {}).get("hemisphere")
            right = inp.get("attrs", {}).get("hemisphere")
            bilateral = (
                isinstance(left, str) and isinstance(right, str) and left != right
            )
            if a.get("hemisphere") and b.get("hemisphere"):
                if a["hemisphere"] != b["hemisphere"] and not bilateral:
                    compatible = False
                if (
                    a["hemisphere"] == b["hemisphere"]
                    and a.get("mesh") is not None
                    and b.get("mesh") is not None
                    and a["mesh"] != b["mesh"]
                ):
                    compatible = False
        if compatible:
            yield from _bindings(
                inputs[1:], available, hierarchy, (*bound, p), all_inputs
            )


def _forward(selected, products, steps, hierarchy, software=None, return_order=False):
    available = list(products)
    known = {_key(p) for p in available}
    applications, order = set(), []
    changed = True
    while changed:
        changed = False
        for step in steps:
            if step["id"] not in selected:
                continue
            for sources in list(_bindings(step["inputs"], available, hierarchy)):
                signature = (step["id"], tuple(_key(p) for p in sources))
                if signature in applications:
                    continue
                identity = sources[0].get("attrs", {}) if sources else {}
                if _step_blocked(step, {"attrs": identity}, software or {}):
                    continue
                applications.add(signature)
                for output in step["outputs"]:
                    attrs = {a: identity.get(a) for a in output.get("inherit", [])}
                    attrs.update(output.get("set", {}))
                    product = {"type": output["type"], "attrs": attrs}
                    key = _key(product)
                    if key not in known:
                        known.add(key)
                        available.append(
                            {"id": step["id"] + ":" + str(len(available)), **product}
                        )
                        changed = True
                if step["id"] not in order:
                    order.append(step["id"])
    return (available, order) if return_order else available


def optimal_plan(targets, products, steps, hierarchy, software=None, max_steps=20):
    """Independent exact subset search with compatible, repeated forward closure."""
    software = software or {}
    usable = [
        s
        for s in steps
        if s.get("eligible_for_planning") is not False
        and not any(software.get(x) is False for x in s.get("software", []))
    ]
    if len(usable) > max_steps:
        raise ValueError("Too many steps for exact enumeration")
    best = (INF, None, [])
    ids = [s["id"] for s in usable]
    costs = {s["id"]: float(s.get("cost", 1)) for s in usable}
    if any(c < 0 or not math.isfinite(c) for c in costs.values()):
        raise ValueError("Workflow costs must be finite and nonnegative")
    for r in range(len(ids) + 1):
        for subset in itertools.combinations(ids, r):
            cost = sum(costs[x] for x in subset)
            if cost >= best[0]:
                continue
            available, order = _forward(
                set(subset), products, usable, hierarchy, software, return_order=True
            )
            if all(satisfied(t, available, hierarchy) for t in targets):
                best = (cost, set(subset), order)
    return {"feasible": best[1] is not None, "cost": best[0], "steps": best[2]}


def steps_from_workflow(document):
    """Normalise all declared steps, preserving constants and eligibility."""
    out = []
    for step in document["steps"]:
        inputs = []
        for inp in step.get("inputs") or []:
            attrs = {}
            for name, rule in (inp.get("attributes") or {}).items():
                if isinstance(rule, Mapping) and isinstance(
                    rule.get("in"), (list, tuple)
                ):
                    attrs[name] = {"in": list(rule["in"])}
            inputs.append({"type": inp["type"], "attrs": attrs})
        outputs = []
        parameters = step.get("default_parameters", {})
        for o in step.get("outputs") or []:
            enabled = o.get("enabled_when")
            if enabled and parameters.get(enabled["parameter"]) != enabled["equals"]:
                continue
            sets, inherit = {}, []
            for name, rule in (o.get("attribute_rules") or {}).items():
                if not isinstance(rule, Mapping):
                    continue
                if "inherit" in rule:
                    inherit.append(name)
                elif any(k in rule for k in ("constant", "value", "set")):
                    sets[name] = next(
                        rule[k] for k in ("constant", "value", "set") if k in rule
                    )
            for name in ("subject", "species"):
                if name not in sets and name not in inherit:
                    inherit.append(name)
            # Hemispheres are instantiated by the integration boundary when a
            # bilateral volume-to-surface stage has no hemisphere-bearing source.
            if (
                any("hemisphere" in i.get("attrs", {}) for i in inputs)
                and "hemisphere" not in sets
                and "hemisphere" not in inherit
            ):
                inherit.append("hemisphere")
            kind = {"type:StatsTable.Aparc": "type:StatsTable.CorticalParcStats"}.get(
                o["type"], o["type"]
            )
            if kind.startswith("type:Annotation."):
                stem = next(
                    (
                        p.split("{hemi}.", 1)[1][:-6]
                        for p in o.get("path_patterns", [])
                        if "{hemi}." in p and p.endswith(".annot")
                    ),
                    None,
                )
                if stem:
                    sets["atlas_file_stem"] = stem
            outputs.append({"type": kind, "set": sets, "inherit": inherit})
        cost = step.get("cost", 1)
        out.append(
            {
                "id": step["id"],
                "inputs": inputs,
                "outputs": outputs,
                "software": list(step.get("software") or []),
                "species_allowed": list(step.get("species_allowed") or []),
                "eligible_for_planning": step.get("eligible_for_planning", True),
                "implementation_status": step.get("implementation_status", ""),
                "cost": float(
                    cost.get("value", 1) if isinstance(cost, Mapping) else cost
                ),
            }
        )
    return out
