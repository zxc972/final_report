"""Offline-first cross-species policy and host-owned conclusion cards.

Only typed claims can be checked deterministically. Free prose is retained as
Agent-authored text and is never certified as semantically entailed.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path

from .analysis_control_store import digest
from .analysis_crossspecies_templates import CHECKERS
from .analysis_profile_worker import value


def enabled(tools):
    return (
        tools.knowledge_profile.name == "product_graph_planner"
        and os.environ.get("AGENT_CROSSSPECIES_RULES") == "1"
    )


def load_policy(name, repository=None):
    if repository is not None:
        return repository.document(name)[0]
    path = (
        Path(__file__).resolve().parent.parent / "knowledge_analysis" / (name + ".json")
    )
    raw = path.read_bytes()
    if (
        hashlib.sha256(raw).hexdigest()
        != path.with_suffix(".sha256").read_text().strip()
    ):
        raise ValueError("Cross-species policy digest mismatch: " + name)
    return json.loads(raw)


def evaluate_policy(environment, repository=None):
    policy = load_policy("cross_species_rules", repository)
    references = load_policy("species_reference_values", repository)
    environment = {**environment, "references": references["references"]}
    rows = []
    for instance in policy["templates"]:
        evaluated = CHECKERS[instance["template"]](
            instance["parameters"], environment, instance["severity"]
        )
        severity = instance["severity"]
        if instance["template"] == "scale_check" and evaluated["verdict"] == "warn":
            severity = "soft"
        rows.append(
            {
                "constraint_id": instance["id"],
                "template": instance["template"],
                "severity": severity,
                "verdict": evaluated["verdict"],
                "tool_observed": evaluated,
                "source": instance["source"],
                "model_declared": None,
                "agreement": None,
                "conflict": False,
                "on_fail": "warn_and_disclose" if severity == "soft" else "block",
            }
        )
    return rows


def host_record(tools, kind):
    record = tools.control_store.latest(kind)
    return copy.deepcopy(record["record"]) if record else {}


def observed_environment(tools, plan):
    profile = host_record(tools, "data_profile")
    declared = []
    catalog_path = os.environ.get("AGENT_DATA_CATALOG")
    sources = []
    if catalog_path and Path(catalog_path).is_file():
        roots = json.loads(Path(catalog_path).read_text()).get("roots", [])
        selected = set(plan.get("data", {}).get("subjects", []))
        for row in roots:
            if (
                row.get("subject_id") in selected
                and Path(row["path"]).resolve() in tools.input_roots
            ):
                if row.get("species_declared"):
                    declared.append(row["species_declared"])
                    sources.append(
                        {
                            "path": catalog_path,
                            "method": "Authenticated approved-root declaration",
                            "subject": row["subject_id"],
                        }
                    )
    if not declared:
        explicit = value(profile.get("species", {}).get("declared"))
        if explicit:
            declared = [explicit]
            sources = [
                {
                    "path": "protected data_profile",
                    "method": "Explicit authenticated task declaration",
                }
            ]
    aliases = {
        "homo sapiens": "human",
        "macaca mulatta": "macaque",
        "macaca fascicularis": "macaque",
        "macaca fuscata": "macaque",
    }
    declared = [aliases.get(s.lower(), s.lower()) for s in declared]
    scope = plan.get("analysis_scope", {})
    trusted = host_record(tools, "crossspecies_observations")
    allowed_keys = {
        "scale",
        "measurements",
        "homology",
        "bias_checks",
        "groups",
        "negative_result",
        "normalization_ref",
        "measure_kind",
        "independent_numeric",
        "observed_direction", "plausibility_required",
    }
    observed = {key: val for key, val in trusted.items() if key in allowed_keys}
    numeric = observed.get("independent_numeric")
    saved_plan = tools.control_store.latest("plan")
    if numeric and (
        trusted.get("plan_sha256") != (saved_plan["sha256"] if saved_plan else None)
        or trusted.get("execution_receipt_id") != tools.last_execution.get("receipt_id")
        or not tools.last_execution.get("receipt_id")
    ):
        observed["independent_numeric"] = {
            "host_verified": False,
            "status": "unbound",
            "reason": "Reference result is not bound to the current plan/execution receipt",
        }
    current_binding = (
        saved_plan is not None
        and tools.last_execution.get("receipt_id") is not None
        and trusted.get("plan_sha256") == saved_plan["sha256"]
        and trusted.get("execution_receipt_id") == tools.last_execution["receipt_id"]
    )
    if not current_binding:
        if "observed_direction" in observed:
            observed["observed_direction"] = {
                **observed["observed_direction"],
                "host_verified": False,
            }
        observed["negative_result"] = None
    return {
        **observed,
        "species": sorted(set(declared)),
        "species_source": sources,
        "species_verified": value(profile.get("species", {}).get("verified"))
        is not None,
        "atlas": {**plan.get("atlas", {}), "name": plan.get("atlas", {}).get("canonical_name", plan.get("atlas", {}).get("name"))},
        "cross_species": scope.get("comparison") == "cross_species",
        "asymmetry": scope.get("comparison") == "asymmetry",
        "group_inference": scope.get("inference") is True,
        "scale_check_required": scope.get("comparison") == "cross_species" or scope.get("global_bindings") is not None,
        "global_scope": bool(scope.get("global_bindings") or scope.get("global_scope")),
        "executed": tools.last_execution.get("status") == "success",
    }


def validate_commitment(commitment, context):
    if not isinstance(commitment, dict):
        raise ValueError(
            "Agent-authored success/failure criteria and species/scale fields are required"
        )
    for name in ("success_criteria", "failure_criteria", "scale_status"):
        text = commitment.get(name)
        if not isinstance(text, str) or not text.strip() or len(text) > 1200:
            raise ValueError(name + " must be nonempty and at most1200 characters")
    species = commitment.get("species")
    if (
        not isinstance(species, list)
        or not species
        or any(not isinstance(s, str) or not s.strip() for s in species)
    ):
        raise ValueError(
            "species must list explicit declarations; use unknown when unverified"
        )
    if context["analysis_scope"].get(
        "comparison"
    ) == "cross_species" and not commitment.get("homology_evidence"):
        raise ValueError(
            "Cross-species commitment requires homology_evidence references"
        )
    return copy.deepcopy(commitment)


def conclusion_card(
    text,
    claim_scope,
    checks,
    observations,
    allowed_scopes,
    repository=None,
    direction=None,
):
    if not isinstance(text, str) or not text.strip() or len(text) > 8000:
        raise ValueError("Agent conclusion text must be nonempty and bounded")
    if not isinstance(claim_scope, str) or not claim_scope.strip():
        raise ValueError("A typed claim_scope is required")
    rules = load_policy("conclusion_rules", repository)
    numeric = observations.get("independent_numeric", {})
    verified = numeric.get("host_verified") is True
    numeric_status = (
        "pass"
        if verified and numeric.get("status") == "pass"
        else "block" if verified and numeric.get("status") == "fail" else "warn"
    )
    checks = [
        row for row in checks if row.get("constraint_id") != "independent_numeric"
    ] + [
        {
            "constraint_id": "independent_numeric",
            "severity": "soft" if numeric_status == "warn" else "hard",
            "mandatory": True,
            "verdict": numeric_status,
            "tool_observed": {
                "reason": (
                    "Current host-bound independent comparison"
                    if verified
                    else "Independent comparison is missing or unbound"
                ),
                **numeric,
            },
        }
    ]
    missing_homology = any(
        row.get("tool_observed", {}).get("missing_homology") for row in checks
    )
    missing = any(
        row.get("tool_observed", {}).get("missing_required_evidence") for row in checks
    )
    underpowered = any(
        row.get("tool_observed", {}).get("underpowered_negative") for row in checks
    )
    hard = [
        row
        for row in checks
        if row.get("severity") == "hard" and row.get("verdict") != "pass"
    ]
    mandatory = [
        row
        for row in checks
        if row.get("mandatory") is True and row.get("verdict") == "block"
    ]
    observed_direction = observations.get("observed_direction", {})
    opposite = (
        observed_direction.get("host_verified") is True
        and direction in {"positive", "negative"}
        and observed_direction.get("direction") in {"positive", "negative"}
        and direction != observed_direction["direction"]
    )
    facts = {
        "mandatory_failure": bool(mandatory)
        or (verified and numeric.get("status") == "fail"),
        "opposite_direction": opposite,
        "missing_homology": missing_homology,
        "missing_admission_evidence": any(
            row.get("tool_observed", {}).get("defer_evidence") for row in checks
        ),
        "missing_required_evidence": missing
        or not verified
        or numeric.get("status") not in {"pass", "fail"},
        "underpowered_negative": underpowered,
        "other_hard_block": bool(hard),
        "overclaim": claim_scope not in allowed_scopes,
        "has_warnings": any(row.get("verdict") == "warn" for row in checks),
        "qualified_ceiling": any(
            row.get("tool_observed", {}).get("conclusion_ceiling") == "qualified"
            for row in checks
        ),
        "all_required_pass": bool(checks)
        and not hard
        and verified
        and numeric.get("status") == "pass",
    }
    rule = next(
        row
        for row in rules["rules"]
        if (
            all(facts.get(key, False) for key in row.get("all", []))
            if "all" in row
            else any(facts.get(key, False) for key in row.get("any", []))
        )
    )
    return {
        "schema": "primatex.conclusion_card.v1",
        "conclusion_text": text,
        "text_authorship": "analysis_agent_model_or_explicit_offline_placeholder",
        "verdict": rule["verdict"],
        "rule_id": rule["id"],
        "reason": rule["reason"],
        "scope": claim_scope,
        "allowed_scopes": allowed_scopes,
        "supported_rewrite_scope": rule["supported_scope"],
        "checks_passed": [row for row in checks if row.get("verdict") == "pass"],
        "checks_not_passed": [row for row in checks if row.get("verdict") != "pass"],
        "not_passed_count": sum(row.get("verdict") != "pass" for row in checks),
        "evidence": {
            "independent_numeric": numeric,
            "facts": facts,
            "rules_sha256": digest(rules),
        },
        "must_rewrite": rule["verdict"] == "revised",
        "prose_semantic_entailment": "not_certified; typed scope/direction only",
        "limitations": rules["limitations"],
    }


def supported_scopes(plan, checks, repository=None):
    policy = load_policy("conclusion_rules", repository)
    comparison = plan.get("analysis_scope", {}).get("comparison", "describe")
    blocked = any(
        row.get("severity") == "hard" and row.get("verdict") != "pass" for row in checks
    )
    by_id = {row.get("constraint_id"): row.get("verdict") for row in checks}
    return [
        rule["scope"]
        for rule in policy["scope_rules"]
        if ("*" in rule["comparisons"] or comparison in rule["comparisons"])
        and (not rule.get("global_method_only") or plan.get("method", {}).get("method_id") == "method:v15:global_morphometry")
        and (not rule.get("no_hard_block") or not blocked)
        and all(by_id.get(key) == "pass" for key in rule.get("required_pass", []))
        and all(by_id.get(key) in {"pass", "warn"} for key in rule.get("required_evaluated", []))
    ]


def _submit_conclusion_once(tools, text, claim_scope, direction=None):
    if not enabled(tools):
        raise ValueError("Cross-species conclusion policy is not enabled")
    saved = tools.control_store.latest("plan")
    plan = (
        saved["record"]["plan"]
        if saved
        else {"analysis_scope": {}, "atlas": {"applicable": False}}
    )
    from .analysis_constraint_binding import resolve
    bound, constraint_binding = resolve(tools)
    constraints = bound["record"] if bound else {}
    if not saved:
        failure = tools.control_store.latest("planning_failure")
        if failure and constraint_binding and failure["record"].get("constraints_sha256") == constraint_binding["sha256"]:
            plan = failure["record"]["plan_context"]
    environment = observed_environment(tools, plan)
    # Negative-result power and bias/scale checks can change after execution.
    # Re-evaluate policy against current protected observations, not a stale
    # pre-execution condition snapshot. Preserve earlier versions for audit.
    from .analysis_unified_runtime import repository_for

    repository = repository_for(tools)
    rows = [
        row
        for row in constraints.get("rows", [])
        if not row.get("constraint_id", "").startswith("cross:")
    ]
    posterior_rows = evaluate_policy(environment, repository)
    # A failed observed hard precondition may not disappear when context is
    # incomplete or reconstructed after a refusal. Preserve its exact source.
    original_blocks = {row["constraint_id"]: row for row in constraints.get("rows", [])
                       if row.get("constraint_id", "").startswith("cross:")
                       and row.get("severity") == "hard" and row.get("verdict") == "block"}
    rows.extend(original_blocks.get(row["constraint_id"], row) for row in posterior_rows)
    covered = {row["constraint_id"] for row in rows}
    rows.extend(row for key, row in original_blocks.items() if key not in covered)
    posterior = tools.control_store.save(
        "conclusion_checks",
        {
            "plan_sha256": saved["sha256"] if saved else None,
            "execution_receipt_id": tools.last_execution.get("receipt_id"),
            "rows": rows,
            "source": "Current protected post-execution observations",
        },
    )
    card = conclusion_card(
        text,
        claim_scope,
        rows,
        environment,
        supported_scopes(plan, rows, repository),
        direction=direction,
    )
    card["postexecution_checks_ref"] = (
        f"conclusion_checks.v{posterior['version']:06d}.json"
    )
    card["constraint_binding"] = constraint_binding
    card["plan_sha256"] = saved["sha256"] if saved else None
    card["analysis_execution_receipt_id"] = tools.last_execution.get("receipt_id")
    version = tools.control_store.save("conclusion", card)
    tools.events.append(
        "result",
        "warn" if card["verdict"] != "accepted" else "done",
        "Conclusion: " + card["verdict"],
        {
            "verdict": card["verdict"],
            "not_passed_count": card["not_passed_count"],
            "version": version["version"],
        },
    )
    return {
        "status": "revise" if card["must_rewrite"] else "reviewed",
        "conclusion_card": card,
    }


MAX_CONCLUSION_SUBMISSIONS = 4


def conclusion_scope_options(tools):
    """Only source-bound scopes for the current protected plan and checks."""
    from .analysis_constraint_binding import resolve
    from .analysis_unified_runtime import repository_for

    saved = tools.control_store.latest("plan")
    plan = saved["record"]["plan"] if saved else {"analysis_scope": {}}
    constraints, _ = resolve(tools)
    rows = constraints["record"].get("rows", []) if constraints else []
    repository = repository_for(tools)
    names = supported_scopes(plan, rows, repository)
    policy = load_policy("conclusion_rules", repository)
    return {row["scope"]: row.get("meaning", row["scope"])
            for row in policy["scope_rules"] if row["scope"] in names}


def public_conclusion_feedback(result):
    """No numerical oracle: return typed admission feedback and allowed scopes."""
    card = result["conclusion_card"]
    return {"status": result["status"], "must_rewrite": card["must_rewrite"],
            "verdict": card["verdict"], "reason": card["reason"],
            "allowed_scopes": card["allowed_scopes"],
            "supported_rewrite_scope": card["supported_rewrite_scope"],
            "duplicate": result.get("duplicate", False),
            "submission_count": result.get("submission_count"),
            "review_status": card.get("review_status")}


def submit_conclusion(tools, text, claim_scope, direction=None):
    """Idempotent bounded submission; stale execution results are never reused."""
    if not enabled(tools):
        raise ValueError("Cross-species conclusion policy is not enabled")
    fingerprint = digest({"text": text, "claim_scope": claim_scope})
    receipt = tools.last_execution.get("receipt_id")
    prior = tools.control_store.latest("conclusion_submissions")
    submissions = copy.deepcopy(prior["record"]["items"]) if prior else []
    for item in submissions:
        if item["fingerprint"] == fingerprint and item["execution_receipt_id"] == receipt:
            return {**copy.deepcopy(item["result"]), "duplicate": True,
                    "submission_count": len(submissions)}
    if len(submissions) >= MAX_CONCLUSION_SUBMISSIONS:
        previous = tools.control_store.latest("conclusion")
        card = copy.deepcopy(previous["record"]) if previous else {}
        card.update(verdict="deferred", must_rewrite=False, review_status="unreviewed",
                    reason="Conclusion submission limit reached (4 distinct submissions).",
                    conclusion_text=text, scope=claim_scope,
                    allowed_scopes=list(conclusion_scope_options(tools)),
                    analysis_execution_receipt_id=receipt)
        tools.control_store.save("conclusion", card)
        tools.events.append("result", "warn", "Conclusion review limit reached",
                            {"submission_count": len(submissions), "review_status": "unreviewed"})
        return {"status": "unreviewed", "conclusion_card": card,
                "submission_count": len(submissions)}
    result = _submit_conclusion_once(tools, text, claim_scope, direction)
    submissions.append({"fingerprint": fingerprint, "execution_receipt_id": receipt,
                        "result": copy.deepcopy(result)})
    tools.control_store.save("conclusion_submissions", {"items": submissions})
    return {**result, "duplicate": False, "submission_count": len(submissions)}
