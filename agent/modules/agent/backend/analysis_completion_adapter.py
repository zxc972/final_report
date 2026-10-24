"""Typed, subject-scoped AND-OR planning; no submission or execution endpoint."""

from __future__ import annotations
import copy
import itertools
import math
from . import analysis_andor_planner as andor


def scoped_steps(steps, subject):
    """A workflow stage processes both hemispheres once for one subject."""
    result = []
    for original in steps:
        step = copy.deepcopy(original)
        inputs = []
        for inp in step["inputs"]:
            attrs = inp.get("attrs", {})
            hemis = attrs.get("hemisphere")
            if isinstance(hemis, dict) and hemis.get("in") == ["lh", "rh"]:
                inputs.extend(
                    {
                        "type": inp["type"],
                        "attrs": {**attrs, "subject": subject, "hemisphere": h},
                    }
                    for h in ("lh", "rh")
                )
            else:
                inputs.append(
                    {"type": inp["type"], "attrs": {**attrs, "subject": subject}}
                )
        outputs = []
        for output in step["outputs"]:
            hemispheric = (
                output["type"].startswith(
                    ("type:Surface", "type:Annotation", "type:Label")
                )
                or output["type"] == "type:StatsTable.CorticalParcStats"
            )
            for hemi in ("lh", "rh") if hemispheric else (None,):
                bound = copy.deepcopy(output)
                bound["set"].update(subject=subject)
                if hemi:
                    bound["set"]["hemisphere"] = hemi
                bound["inherit"] = [
                    a for a in bound.get("inherit", []) if a not in bound["set"]
                ]
                outputs.append(bound)
        step.update(inputs=inputs, outputs=outputs)
        result.append(step)
    return result


def completion(targets, products, workflow, hierarchy, software):
    steps = andor.steps_from_workflow(workflow)
    subjects = sorted(
        {
            t.get("attrs", {}).get("subject")
            for t in targets
            if t.get("attrs", {}).get("subject")
        }
    )
    if not subjects or any(t.get("attrs", {}).get("subject") is None for t in targets):
        subjects.append(None)
    results, exacts, scoped, reasons = [], [], [], []
    for subject in subjects:
        wanted = [t for t in targets if t.get("attrs", {}).get("subject") == subject]
        have = (
            [p for p in products if p.get("attrs", {}).get("subject") == subject]
            if subject
            else products
        )
        operators = scoped_steps(steps, subject) if subject else steps
        alternatives = [
            [{**t, "type": kind} for kind in t.get("types", [t["type"]])]
            for t in wanted
        ]
        answers = []
        for variant in itertools.product(*alternatives):
            actual = andor.plan(variant, have, operators, hierarchy, software)
            exact = andor.optimal_plan(variant, have, operators, hierarchy, software)
            answers.append((actual, exact))
        actual, exact = min(
            answers, key=lambda pair: (pair[0]["cost"], tuple(pair[0]["steps"]))
        )
        # The oracle has its own minimum over OR alternatives.
        oracle = min((e for _, e in answers), key=lambda e: e["cost"])
        results.append(actual)
        exacts.append(oracle)
        scoped.extend({"subject": subject, "step": s} for s in actual["steps"])
        reasons.extend(r for t in actual["per_target"] for r in t["reasons"])
    feasible = all(r["feasible"] for r in results)
    cost = sum(r["cost"] for r in results) if feasible else math.inf
    exact_feasible = all(e["feasible"] for e in exacts)
    exact_cost = sum(e["cost"] for e in exacts) if exact_feasible else math.inf
    equal = feasible == exact_feasible and cost == exact_cost
    scopes = sorted(
        {t.get("slot", "").rsplit("/", 1)[0] for t in targets if t.get("slot")}
    )
    return {
        "feasible": feasible,
        "cost": cost if feasible else None,
        "steps": [r["step"] for r in scoped] if feasible else [],
        "scoped_steps": scoped if feasible else [],
        "by_scope": [
            {
                "scope": scope,
                "steps": [
                    r["step"] for r in scoped if r["subject"] == scope.rsplit("/", 1)[0]
                ],
            }
            for scope in scopes
        ],
        "execution_allowed": False,
        "algorithm": "AND-OR",
        "cost_policy": "Unique subject-stage executions; shared hemispheres counted once",
        "scope": "Minimum typed workflow completion; metadata/assets and scientific prerequisites require verification before execution",
        "reason_chain": list(dict.fromkeys(reasons)),
        "optimality_check": {
            "consistent": equal,
            "feasible": exact_feasible,
            "cost": exact_cost if exact_feasible else None,
        },
        "unknown_software": sorted(
            {c for s in steps for c in s.get("software", []) if software.get(c) is None}
        ),
    }


def observed_software(tools, workflow, method_id):
    from .analysis_constraints import software_observation

    commands = sorted(
        {
            c
            for s in workflow["steps"]
            if s.get("eligible_for_planning", True)
            for c in s.get("software", [])
        }
    )
    _, observation = software_observation(tools, commands, method_id)
    software = {
        row["command"]: row["executable"]
        for row in observation.get("commands", [])
        if row.get("command") in commands and type(row.get("executable")) is bool
    }
    saved = tools.control_store.save(
        "planning_software_observation",
        {"commands": observation.get("commands", []), "method_id": method_id},
    )
    return software, saved["sha256"]


def record_check(tools, plan, method_id):
    if not plan["optimality_check"]["consistent"]:
        tools.events.append(
            "plan",
            "running",
            "AND-OR cost differs from exact validation",
            {
                "event_type": "planning_optimality_mismatch",
                "method_id": method_id,
                "actual_cost": plan["cost"],
                "exact": plan["optimality_check"],
                "returned_plan_changed": False,
            },
        )
