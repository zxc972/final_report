"""Nine generic condition templates evaluated on observed product bindings."""

from __future__ import annotations

import json
import re


def lookup(environment, path):
    current = environment
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def products(environment, slot):
    value = environment.get("slots", {}).get(slot)
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def outcome(passed, reason, evidence, severity="hard"):
    return {
        "verdict": "pass" if passed else ("warn" if severity == "soft" else "block"),
        "reason": reason,
        "evidence": evidence,
    }


def product_present(parameters, environment, severity="hard"):
    rows = products(environment, parameters["slot"])
    requested = parameters.get("type")
    matches = []
    for row in rows:
        if requested and not environment["is_subtype"](row.get("type"), requested):
            continue
        if any(
            row.get("attributes", {}).get(key) != val
            for key, val in parameters.get("attributes", {}).items()
        ):
            continue
        matches.append(row.get("id", row.get("path")))
    return outcome(
        bool(matches) or (not rows and parameters.get("optional") is True),
        "Observed typed slot candidates",
        {
            "slot": parameters["slot"],
            "matches": matches,
            "optional": parameters.get("optional", False),
        },
        severity,
    )


def attr_equal(parameters, environment, severity="hard"):
    values, identities = [], []
    for slot in parameters["slots"]:
        for row in products(environment, slot):
            values.append(lookup(row.get("attributes", {}), parameters["attribute"]))
            identities.append(row.get("id", row.get("path")))
    allow_empty = parameters.get("allow_empty", False)
    ok = (not values and allow_empty) or (
        bool(values)
        and all(value is not None for value in values)
        and all(value == values[0] for value in values)
    )
    return outcome(
        ok,
        "Compare observed attribute values; unknown is not equality",
        {
            "attribute": parameters["attribute"],
            "values": values,
            "products": identities,
        },
        severity,
    )


def attr_in(parameters, environment, severity="hard"):
    rows = products(environment, parameters["slot"])
    values = [
        lookup(row.get("attributes", {}), parameters["attribute"]) for row in rows
    ]
    ok = bool(rows) and all(
        value is not None and value in parameters["values"] for value in values
    )
    if not rows and parameters.get("optional") is True:
        ok = True
    return outcome(
        ok,
        "Observed attributes must belong to the registered value domain",
        {
            "attribute": parameters["attribute"],
            "values": values,
            "allowed": parameters["values"],
        },
        severity,
    )


def label_policy(parameters, environment, severity="hard"):
    rows = products(environment, parameters["slot"])
    exclusions = (
        lookup(
            environment, parameters.get("exclusions_ref", "plan.atlas.exclude_labels")
        )
        or []
    )
    required, unreadable, retained = [], [], {}
    for row in rows:
        attrs = row.get("attributes", {})
        unassigned = attrs.get("unassigned_vertices")
        if unassigned is None:
            unreadable.append(row.get("path", row.get("id")))
            continue
        if unassigned > 0:
            required.append(-1)
        if (attrs.get("special_vertices") or {}).get("unknown"):
            required.append("unknown")
        names = attrs.get("label_names") or []
        keys = attrs.get("label_keys") or list(range(len(names)))
        counts = attrs.get("cortex_retained_label_counts")
        excluded_names = {
            re.sub("[^a-z]", "", str(value).lower())
            for value in exclusions
            if isinstance(value, str)
        }
        kept = [
            key
            for key, name in zip(keys, names)
            if key not in exclusions
            and re.sub("[^a-z]", "", name.lower()) not in excluded_names
            and (counts is None or counts.get(str(key), 0) > 0)
        ]
        retained[row.get("id", row.get("path"))] = kept
        if parameters.get("require_nonempty", True) and not kept:
            unreadable.append(
                str(row.get("path", row.get("id"))) + ": empty retained label set"
            )
    ok = not unreadable and all(term in exclusions for term in required)
    if not rows and not parameters.get("allow_absent", False):
        ok = False
    return outcome(
        ok,
        "Observed labels, explicit exclusions and retained label sets",
        {
            "required_exclusions": required,
            "declared_exclusions": exclusions,
            "unreadable": unreadable,
            "retained_label_sets": retained,
            "scope": "Declaration/observation checks do not verify generated-code semantics",
        },
        severity,
    )


def cardinality(parameters, environment, severity="hard"):
    active = parameters.get("when")
    if active and lookup(environment, active) is not True:
        return outcome(
            True,
            "Condition inactive for descriptive analysis",
            {"active": False},
            severity,
        )
    items = lookup(environment, parameters["object"])
    minimum = parameters.get("minimum", 1)
    maximum = parameters.get("maximum")
    if isinstance(items, dict) and parameters.get("groups") is True:
        observed = set(
            lookup(environment, parameters.get("observed_ids", "objects.subject_ids"))
            or []
        )
        groups = {
            key: sorted(set(members) & observed)
            for key, members in items.items()
            if isinstance(members, list)
        }
        used = [member for members in groups.values() for member in members]
        design = lookup(
            environment,
            parameters.get("design_size", "plan.analysis_scope.design_columns"),
        )
        dof = len(set(used)) - design if type(design) is int and design > 0 else None
        ok = bool(groups) and all(
            len(members) >= minimum for members in groups.values()
        )
        ok = ok and len(set(used)) == len(used) and dof is not None and dof > 0
        return outcome(
            ok,
            "Distinct observed subjects, disjoint declared groups and positive declared residual degrees of freedom",
            {
                "groups": groups,
                "observed_subject_ids": sorted(observed),
                "residual_dof": dof,
                "design_rank_verified": False,
                "minimum_per_group": minimum,
            },
            severity,
        )
    if not isinstance(items, (list, tuple, set)):
        items = []
    count = (
        len({json.dumps(item, sort_keys=True, default=str) for item in items})
        if parameters.get("distinct", True)
        else len(items)
    )
    ok = count >= minimum and (maximum is None or count <= maximum)
    return outcome(
        ok,
        "Observed cardinality",
        {"count": count, "minimum": minimum, "maximum": maximum},
        severity,
    )


def design_variable(parameters, environment, severity="hard"):
    tables = products(environment, parameters["slot"])
    column = parameters["variable"]
    observations = []
    for table in tables:
        attrs = table.get("attributes", {})
        observations.append(
            {
                "table": table.get("id"),
                "column_present": column in (attrs.get("columns") or []),
                "all_rows_nonempty": (attrs.get("nonempty_columns") or {}).get(column)
                is True,
            }
        )
    ok = bool(observations) and all(
        row["column_present"] and row["all_rows_nonempty"] for row in observations
    )
    return outcome(
        ok,
        "Observed table header and nonempty cells; no design-rank inference",
        {"variable": column, "tables": observations},
        severity,
    )


def software(parameters, environment, severity="hard"):
    commands = parameters.get("commands") or []
    rows = environment.get("software", [])
    actual = {row.get("command"): row for row in rows}
    ok = (
        bool(commands)
        and [row.get("command") for row in rows] == commands
        and all(
            command in actual and actual[command].get("executable") is True
            for command in commands
        )
    )
    execution = environment.get("software_execution")
    if execution is not None:
        ok = (
            ok
            and execution.get("status") == "success"
            and execution.get("exit_code") == 0
        )
    return outcome(
        ok,
        "Actual fixed sandbox command probes",
        {"commands": commands, "observations": rows, "execution": execution},
        severity,
    )


def provenance(parameters, environment, severity="hard"):
    if "evidence_ref" in parameters:
        records = lookup(environment, parameters["evidence_ref"])
        records = records if isinstance(records, list) else []
        required = parameters.get("required_values", {})
        ok = bool(records) or parameters.get("allow_empty", False)
        for record in records:
            ok = ok and all(
                lookup(record, key) == value for key, value in required.items()
            )
            ok = ok and all(
                isinstance(lookup(record, key), str) and lookup(record, key).strip()
                for key in parameters.get("nonempty_fields", [])
            )
        return outcome(
            bool(ok),
            "Source-bound provenance observations; declarations are labeled separately",
            {"records": records, "scope": parameters.get("scope")},
            severity,
        )
    rows = products(environment, parameters["slot"])
    observed = []
    for row in rows:
        activities = environment.get("provenance", {}).get(row.get("id"), [])
        matched = [
            activity
            for activity in activities
            if activity.get("step") == parameters["step"]
            and activity.get("verified") is True
        ]
        observed.append({"product": row.get("id"), "matched_activities": matched})
    return outcome(
        bool(observed) and all(row["matched_activities"] for row in observed),
        "Verified wasGeneratedBy/used activity records required",
        {"products": observed},
        severity,
    )


def advisory(parameters, environment, severity="soft"):
    return {
        "verdict": "warn",
        "reason": parameters["text"],
        "evidence": {
            "executable": False,
            "status": parameters.get("status", "advisory"),
            "reason_not_executable": parameters.get("reason_not_executable"),
        },
    }


CHECKERS = {
    function.__name__: function
    for function in (
        product_present,
        attr_equal,
        attr_in,
        label_policy,
        cardinality,
        design_variable,
        software,
        provenance,
        advisory,
    )
}


def evaluate(instance, environment):
    template = instance.get("template")
    from .analysis_crossspecies_templates import CHECKERS as cross_checkers
    registry = {**CHECKERS, **cross_checkers}
    if template not in registry:
        raise ValueError("Unknown condition template: " + str(template))
    result = registry[template](
        instance["parameters"], environment, instance.get("severity", "hard")
    )
    return {
        "condition_id": instance["id"],
        "template": template,
        "source": instance.get("source", []),
        **result,
    }


def evaluate_all(instances, environment):
    rows = [evaluate(instance, environment) for instance in instances]
    verdict = (
        "block"
        if any(row["verdict"] == "block" for row in rows)
        else ("warn" if any(row["verdict"] == "warn" for row in rows) else "pass")
    )
    return {"verdict": verdict, "rows": rows}
