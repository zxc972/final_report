"""Complete prerequisite summaries from protected records, never model claims."""

from __future__ import annotations
from .analysis_control_store import digest


def build_evidence_card(tools, validation):
    from .analysis_constraint_ids import qualified
    store = tools.control_store
    checks, commands, disclosures = {}, {}, []
    for path in store.versions("constraints"):
        saved = store.read(path.name)
        if saved["sha256"] != digest(saved["record"]):
            raise ValueError("Constraint evidence digest mismatch")
        record = saved["record"]
        for row in record.get("rows", []):
            observed = row.get("tool_observed", {})
            method = record.get("method_id")
            checks[qualified(method, row["constraint_id"])] = {
                "method_id": method,
                "constraint_id": row["constraint_id"],
                "severity": row["severity"],
                "verdict": row["verdict"],
                "reason": observed.get("reason"),
                "evidence_ref": path.name,
            }
            for command in observed.get("commands", []):
                commands[(method, command.get("command"))] = {
                    "method_id": method,
                    "command": command.get("command"),
                    "available": command.get("executable"),
                    "executed": command.get("executed"),
                    "returncode": command.get("returncode", command.get("exit_code")),
                    "evidence_ref": path.name,
                }
    runtime = store.latest("data_card_runtime")
    if runtime:
        for name, command in (
            runtime["record"].get("inventory", {}).get("commands", {}).items()
        ):
            commands[("runtime_inventory", name)] = {
                "method_id": "runtime_inventory",
                "command": name,
                "available": command.get("executable"),
                "executed": command.get("executed"),
                "returncode": command.get("returncode", command.get("exit_code")),
                "evidence_ref": "data_card_runtime.v%06d.json" % runtime["version"],
            }
    plan = store.latest("plan")
    if plan:
        disclosures = list(plan["record"].get("must_disclose", []))
        disclosures += (
            plan["record"].get("plan", {}).get("analysis_scope", {}).get("notices", [])
        )
    numeric = store.latest("independent_numeric")
    profile = store.latest("data_profile")
    profile_summary = None
    if profile:
        from .analysis_profile_worker import value
        profile_summary = {
            "record_id": "data_profile.v%06d.json" % profile["version"],
            "sha256": profile["sha256"],
            "species": profile["record"].get("species"),
            "recon": profile["record"].get("recon"),
            "files": [{
                "path": value(item.get("path")),
                "format": value(item.get("format")),
                "sha256": value(item.get("sha256")),
                "surface": value(item.get("surface")),
                "metric": value(item.get("metric")),
                "label_summary": {key: value(val) for key, val in (value(item.get("label")) or {}).items()
                                  if key not in {"label_vertex_counts", "cortex_retained_label_counts", "label_keys"}},
            } for item in profile["record"].get("files", [])],
            "scope": "Protected metadata summary; not raw images, independent reference values or expert QC",
        }
    from .analysis_constraint_ids import canonical_row
    checks = {key: canonical_row(row) for key, row in checks.items()}
    return {
        "schema": "primatex.review_evidence_card.v2",
        "protected_profile": profile_summary,
        "software_observations": list(commands.values()),
        "hard_conditions": [
            row for row in checks.values() if row["severity"] == "hard"
        ],
        "hard_blocks": [
            row
            for row in checks.values()
            if row["severity"] == "hard" and row["verdict"] == "block"
        ],
        "group_report_requirements": ({key: plan["record"]["plan"]["analysis_scope"].get(key) for key in ("n", "excluded_subjects", "d_min", "power_assumptions", "site_scanner_composition", "effect")} if plan and plan["record"]["plan"]["method"]["method_id"] == "method:v14:group_regional_glm" else None),
        "public_contract": validation.get("public_output_contract", {}),
        "independent_numeric": (
            {
                key: numeric["record"].get(key)
                for key in (
                    "status",
                    "identity_mismatch_count",
                    "numeric_mismatch_count",
                    "checked",
                )
            }
            if numeric
            else {"status": "not_configured"}
        ),
        "must_disclose": disclosures,
        "plan_sha256": plan["sha256"] if plan else None,
        "scope": "All observed method prerequisites for this run; no reference values or private scores.",
        "not_truncated": True,
    }
