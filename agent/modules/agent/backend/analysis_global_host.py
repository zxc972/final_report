"""Host-only global verification, scale observations and eligible-subject registry."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys

from .analysis_global_method import METRICS, METHOD


def reference_rows(tools, plan):
    binding = plan["analysis_scope"]["global_bindings"]
    scale = plan["analysis_scope"]["global_scale"]
    bound = {
        path
        for key in ("aseg_stats", "mask_volume")
        for path in [binding.get(key)]
        if path
    }
    mapping_keys = ("hemi_stats", "pial", "white", "thickness", "cortex_labels")
    bound.update(path for key in mapping_keys for path in binding.get(key, {}).values())
    if not bound <= set(plan["data"]["files"]):
        raise ValueError("Every global reference input must be sealed and hash-bound")
    request = {}
    for key in ("aseg_stats", "mask_volume"):
        path = binding.get(key)
        request[key] = str(tools.resolve(path)) if path else None
    for key in mapping_keys:
        if key in binding:
            request[key] = {
                h: str(tools.resolve(p)) for h, p in binding[key].items()
            } or None
    request["species"] = plan["data"]["species_declared"]
    request["scale_state"] = scale["status"]
    request.update(scale_k=scale["k"], rescaled=scale["rescaled"])
    source = Path(__file__).with_name("analysis_global_reference_worker.py")
    python = os.environ.get("ANALYSIS_REFERENCE_PYTHON", sys.executable)
    run = subprocess.run(
        [python, "-I", "-B", str(source)],
        input=json.dumps(request).encode(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=240,
        env={
            "PATH": "/usr/bin:/bin",
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
        },
    )
    if run.returncode:
        raise RuntimeError(
            "Independent global reference worker failed: "
            + run.stderr.decode(errors="replace")[-700:]
        )
    values = json.loads(run.stdout)
    row = {
        "subject": plan["data"]["subjects"][0],
        "species": plan["data"]["species_declared"],
        "scale_status": values["scale_status"],
        "scale_k": values["scale_k"],
        **values["physical"],
        **{"stored_" + key: val for key, val in values["stored"].items()},
    }
    tools.control_store.save(
        "global_reference_private",
        {
            "reference": values,
            "row": row,
            "plan_sha256": tools.control_store.latest("plan")["sha256"],
            "execution_receipt_id": tools.last_execution["receipt_id"],
        },
    )
    columns = [
        *METRICS,
        *("stored_" + key for key in METRICS),
        "scale_status",
        "scale_k",
    ]
    return [row], ["subject", "species"], columns


def bind_observations(tools, summary):
    """Only accepted CSV results become observed measurements; never expose oracle rows."""
    if summary.get("status") != "pass" or summary.get("host_verified") is not True:
        return
    plan = tools.control_store.latest("plan")["record"]["plan"]
    target = tools.resolve("/work/global_metrics.csv")
    with target.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != 1:
        raise ValueError("Verified global result must have one row")
    row = rows[0]
    scale = plan["analysis_scope"]["global_scale"]
    measurements = []
    kinds = [
        ("mean_thickness_mm", "thickness", "whole_cortex_mean", "mm", 1),
        ("total_area_mm2", "surface_area", "per_hemisphere", "mm2", 2),
        ("brain_volume_mm3", "brain_volume", "whole_brain", "cm3", 1000),
    ]
    for column, metric, scope, unit, divisor in kinds:
        if row[column] == "" or row["stored_" + column] == "":
            continue
        measurements.append(
            {
                "metric": metric,
                "species": row["species"],
                "scope": scope,
                "unit": unit,
                "value": float(row[column]) / divisor,
                "stored_value": float(row["stored_" + column]) / divisor,
                "physical_scale_verified": scale["host_verified"],
                "physical_calibration_verified": False,
                "sampling_scope": "individual_mean",
                "definition": (
                    "bilateral mean area" if column == "total_area_mm2" else column
                ),
                "source_ref": "global_metrics.csv#" + column,
            }
        )
    previous = tools.control_store.latest("crossspecies_observations")
    record = dict(previous["record"]) if previous else {}
    record.update(
        scale=scale,
        measurements=measurements,
        measure_kind="global_absolute",
        plausibility_required=True,
    )
    tools.control_store.save("crossspecies_observations", record)
    from .analysis_crossspecies import observed_environment, evaluate_policy
    from .analysis_unified_runtime import repository_for

    checks = evaluate_policy(observed_environment(tools, plan), repository_for(tools))
    tools.control_store.save(
        "global_postexecution_checks",
        {
            "plan_sha256": tools.control_store.latest("plan")["sha256"],
            "execution_receipt_id": tools.last_execution["receipt_id"],
            "rows": checks,
        },
    )


def attach_result_card(tools, card):
    saved = tools.control_store.latest("plan")
    if not saved or saved["record"]["plan"]["method"]["method_id"] != METHOD:
        return card
    checks = tools.control_store.latest("global_postexecution_checks")
    if (
        checks
        and checks["record"]["plan_sha256"] == saved["sha256"]
        and checks["record"]["execution_receipt_id"]
        == tools.last_execution.get("receipt_id")
    ):
        from .analysis_crossspecies import conclusion_card
        from .analysis_independent_numeric import current_summary
        from .analysis_constraint_binding import resolve

        bound, _ = resolve(tools)
        rows = [
            r
            for r in (bound["record"]["rows"] if bound else [])
            if not r.get("constraint_id", "").startswith("cross:")
        ]
        rows.extend(checks["record"]["rows"])
        card = conclusion_card(
            card.get("conclusion_text") or "Global result",
            "supplied_descriptive",
            rows,
            {"independent_numeric": current_summary(tools)},
            ["supplied_descriptive"],
        )
    return card


def publish_eligible(tools, response):
    """Admit only fully reviewed current results; repeated subjects never inflate n."""
    saved = tools.control_store.latest("plan")
    if not saved or saved["record"]["plan"]["method"]["method_id"] != METHOD:
        return None
    from .analysis_independent_numeric import current_summary
    from .analysis_overall_status import review_status

    numeric = current_summary(tools)
    validation = response.get("validation", {})
    if (
        response.get("status") != "completed"
        or numeric.get("status") != "pass"
        or review_status(validation) != "reviewed"
        or validation.get("public_output_contract", {}).get("status") != "pass"
    ):
        return {
            "status": "not_eligible",
            "reason": "Full contract, numeric and internal-review completion is required",
        }
    default = tools.control_store.root.parent / "verified_global_subjects"
    root = Path(os.environ.get("AGENT_GLOBAL_RESULTS_DIR", default))
    from .analysis_control_store import ControlStore

    store = ControlStore(root, [tools.workdir, *tools.input_roots])
    path = tools.resolve("/work/global_metrics.csv")
    raw = path.read_bytes()
    row = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))[0]
    record = {
        "subject": row["subject"],
        "species": row["species"],
        "physical": {key: float(row[key]) if row[key] else None for key in METRICS},
        "scale_status": row["scale_status"],
        "scale_k": float(row["scale_k"]) if row["scale_k"] else None,
        "output_path": str(path),
        "output_sha256": hashlib.sha256(raw).hexdigest(),
        "plan_sha256": saved["sha256"],
        "execution_receipt_id": tools.last_execution["receipt_id"],
        "checks": tools.control_store.latest("global_postexecution_checks")["record"][
            "rows"
        ],
    }
    store.save("eligible_subject", record)
    return aggregate(store)


def aggregate(store, numerator="human", denominator="macaque"):
    """Host aggregation of eligible, unchanged results using the independent reference."""
    from .analysis_global_reference import cross_species_summary
    from .analysis_crossspecies import (
        evaluate_policy,
        conclusion_card,
        supported_scopes,
    )

    selected, excluded = {}, []
    for path in store.versions("eligible_subject"):
        row = store.read(path.name)["record"]
        target = Path(row["output_path"])
        if (
            not target.is_file()
            or hashlib.sha256(target.read_bytes()).hexdigest() != row["output_sha256"]
        ):
            excluded.append(
                {
                    "subject": row["subject"],
                    "reason": "Registered output missing or changed",
                }
            )
            continue
        selected[(row["species"], row["subject"])] = row
    rows = list(selected.values())
    summary = cross_species_summary(rows, numerator, denominator)
    fields = [
        "metric",
        numerator + "_n",
        numerator + "_mean",
        denominator + "_n",
        denominator + "_mean",
        "ratio",
    ]
    with (store.root / "cross_species_global.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(summary["summary"])
    species = sorted({r["species"] for r in rows if r["scale_status"] != "unknown"})
    all_scale_known = bool(rows) and all(r["scale_status"] != "unknown" for r in rows)
    observed_checks = [c for r in rows for c in r["checks"]]
    checks = []
    for key in ["cross:scale_check", "cross:plausibility"]:
        matches = [r for r in observed_checks if r["constraint_id"] == key]
        verdict = (
            "block"
            if any(r["verdict"] == "block" for r in matches)
            else (
                "pass"
                if matches and all(r["verdict"] == "pass" for r in matches)
                else "warn"
            )
        )
        checks.append(
            {
                "constraint_id": key,
                "severity": "hard" if key.endswith("scale_check") else "soft",
                "verdict": verdict,
                "tool_observed": {
                    "reason": "All eligible subject checks must have executed",
                    "subject_checks": matches,
                },
            }
        )
    env = {
        "species": species,
        "cross_species": True,
        "global_scope": True,
        "measure_kind": "ratio",
        "atlas": {"applicable": False},
        "scale": {"host_verified": all_scale_known, "rescaled": False, "k": 1},
        "independent_numeric": {
            "host_verified": True,
            "status": "pass",
            "source": "Every admitted subject passed host reference and final review",
        },
    }
    checks += [
        r
        for r in evaluate_policy(env)
        if r["constraint_id"]
        in {"cross:cross_species_measure", "cross:homology_evidence"}
    ]
    plan = {
        "method": {"method_id": METHOD},
        "analysis_scope": {"comparison": "cross_species", "global_scope": True},
    }
    allowed = supported_scopes(plan, checks)
    ready = bool(summary["summary"]) and len(species) >= 2 and all_scale_known
    card = conclusion_card(
        "Host-generated ratios of species means; no population inference or regional homology claim.",
        "global_cross_species_ratio" if ready else "supplied_descriptive",
        checks,
        env,
        allowed,
    )
    if not ready:
        card.update(
            verdict="deferred",
            reason="Awaiting eligible scale-verified subjects from both species",
            must_rewrite=False,
        )
    result = {
        **summary,
        "status": "ready" if ready else "waiting_for_both_species",
        "excluded_changed_outputs": excluded,
        "unique_subjects": len(rows),
        "species": species,
        "conclusion_card": card,
        "csv_path": str(store.root / "cross_species_global.csv"),
    }
    store.save("global_summary", result)
    return result
