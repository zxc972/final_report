"""Compile host-owned observations and declared plans into executable constraints.

No expected scientific output or scoring reference is visible to these probes.
Model declarations are retained separately and never override tool observations.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .analysis_control_store import canonical, digest
from .analysis_profile_worker import value

MAPPING = (
    Path(__file__).resolve().parent.parent / "knowledge_analysis/constraint_probes.json"
)
CORE_FIELDS = (
    "question",
    "data",
    "atlas",
    "method",
    "outputs",
    "code_path",
    "analysis_scope",
)


def plan_core(plan):
    return {key: plan.get(key) for key in CORE_FIELDS}


def load_mapping():
    raw = MAPPING.read_bytes()
    expected = MAPPING.with_suffix(".sha256").read_text(encoding="utf-8").split()[0]
    if MAPPING.is_symlink() or hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError("Constraint mapping digest mismatch")
    result = json.loads(raw)
    if result.get("schema_version") != "primatex.constraint_probes.v1":
        raise ValueError("Unknown constraint mapping")
    return result["constraints"], expected


def selected_files(profile, context):
    wanted = context.get("data", {}).get("files", [])
    if not wanted or any(not isinstance(p, str) for p in wanted):
        raise ValueError("Plan data.files must list profiled paths")
    catalog = {value(item["path"]): item for item in profile["files"]}
    if not set(wanted).issubset(catalog):
        raise ValueError("Plan contains files absent from the protected data profile")
    return [catalog[path] for path in wanted]


def recon_complete(files, context, parameters):
    recon = [value(item["recon"]) for item in files if value(item["recon"])]
    ok = bool(recon) and all(
        value(row["done"]) is True and value(row["fatal_count"]) == 0 for row in recon
    )
    return ok, {
        "reconstructions": recon,
        "fatal_explanations_trusted": False,
        "reason": "done marker and readable zero-FATAL log required; model explanations cannot waive a FATAL",
    }


def unassigned_labels_excluded(files, context, parameters):
    annotations = [
        item for item in files if value(item["format"]) in ("annot", "label.gii")
    ]
    exclusions = context.get("atlas", {}).get("exclude_labels", [])
    required = []
    unreadable = []
    for item in annotations:
        label = value(item["label"])
        if not label or value(label["unassigned_vertices"]) is None:
            unreadable.append(value(item["path"]))
            continue
        if value(label["unassigned_vertices"]) > 0:
            required.append(-1)
        special = value(label["special_vertices"]) or {}
        if special.get("unknown"):
            required.append("unknown")
    ok = not unreadable and all(term in exclusions for term in required)
    return ok, {
        "required_exclusions": required,
        "declared_exclusions": exclusions,
        "unreadable": unreadable,
        "scope": "Checks plan declaration against observed labels, not generated-code semantics",
    }


def mesh_label_match(files, context, parameters):
    catalog = {value(item["path"]): item for item in files}
    annotations = [
        path
        for path, item in catalog.items()
        if value(item["format"]) in ("annot", "label.gii")
    ]
    bindings = context.get("atlas", {}).get("mesh_bindings", [])
    observations = []
    for label_path in annotations:
        candidates = [
            binding for binding in bindings if binding.get("label") == label_path
        ]
        if len(candidates) != 1:
            observations.append(
                {
                    "label": label_path,
                    "pass": False,
                    "reason": "One explicit surface/registration binding required",
                }
            )
            continue
        binding = candidates[0]
        surface = catalog.get(binding.get("surface"), {})
        geometry = value(surface.get("surface", {}))
        labels = value(catalog[label_path]["label"])
        provenance = catalog.get(binding.get("registration_ref"), {})
        equal = bool(
            geometry
            and labels
            and value(geometry["vertex_count"]) == value(labels["vertex_count"])
        )
        record = value(provenance.get("sha256", {}))
        declared = all(
            isinstance(binding.get(key), str) and binding[key].strip()
            for key in ("mesh_origin", "space", "registration_ref")
        )
        observations.append(
            {
                "label": label_path,
                "surface": binding.get("surface"),
                "equal_cardinality": equal,
                "declared_origin_and_space": declared,
                "registration_ref": binding.get("registration_ref"),
                "registration_sha256": record,
                "pass": bool(equal and declared and record),
                "scope": "Observed cardinality and recorded provenance; not independent anatomical correspondence validation",
            }
        )
    required = (
        context.get("method", {}).get("method_id")
        == "method:v12:surface_annotation_roi"
    )
    return (bool(annotations) or not required) and all(
        row["pass"] for row in observations
    ), {
        "bindings": observations,
        "annotation_present": bool(annotations),
        "reason": (
            "Annotation required by the selected method"
            if required and not annotations
            else "Observe actual binding cardinality and declared provenance"
        ),
    }


def scale_consistent(files, context, parameters):
    problems = []
    units = set()
    named_scales = set()
    for item in files:
        path = value(item["path"])
        volume = value(item["volume"])
        if volume:
            unit = value(volume["units"])
            if unit and unit != "unknown":
                units.add(unit)
            if value(volume["qform_sform_conflict"]) is True:
                problems.append(
                    {"path": path, "reason": "Conflicting coded qform/sform"}
                )
        if "_1mm" in path or "/1mm/" in path:
            named_scales.add("1mm_filename_convention")
        elif "native" in path.lower():
            named_scales.add("native_filename_convention")
    policy = context.get("analysis_scope", {}).get("scale_policy")
    separate = policy in {"within_input_only", "dimensionless_per_input"}
    if len(named_scales) > 1 and not separate:
        problems.append(
            {
                "reason": "Native/scaled-copy naming conventions mixed without an explicit separate-scale policy",
                "evidence_strength": "filename convention; requires clarification, not a verified scale factor",
            }
        )
    if len(units) > 1 and not context.get("analysis_scope", {}).get("unit_conversion"):
        problems.append(
            {
                "reason": "Different header unit conventions without an explicit conversion"
            }
        )
    return not problems, {
        "problems": problems,
        "scale_policy": policy,
        "note": "Voxel resolution differences alone do not prove physical scale inconsistency",
    }


def group_inference_sample(files, context, parameters):
    scope = context.get("analysis_scope", {})
    if scope.get("inference") is not True:
        return True, {
            "inference": False,
            "scope": "Descriptive analysis only; no group inferential permission",
        }
    ids = set()
    for item in files:
        ids.update(value(item.get("subject", {})) or [])
    groups = scope.get("groups", {})
    group_ids = {
        key: sorted(set(members) & ids)
        for key, members in groups.items()
        if isinstance(members, list)
    }
    minimum = parameters.get("minimum_independent_subjects", 2)
    p = scope.get("design_columns")
    enough = bool(group_ids) and all(
        len(members) >= minimum for members in group_ids.values()
    )
    used = [member for members in group_ids.values() for member in members]
    distinct = len(set(used)) == len(used)
    dof = len(set(used)) - p if type(p) is int and p > 0 else None
    ok = enough and distinct and dof is not None and dof > 0
    return ok, {
        "observed_independent_subjects": sorted(ids),
        "groups": group_ids,
        "group_assignment_trust": "model-declared; subject IDs verified from profiled explicit TSV",
        "design_columns_trust": "model-declared design size; actual design matrix rank not probed",
        "residual_dof": dof,
        "minimum_per_group": minimum,
        "reason": "Repeated scans deduplicated; minimum sample rule is not a power/suitability analysis",
    }


CHECKERS = {
    fn.__name__: fn
    for fn in (
        recon_complete,
        unassigned_labels_excluded,
        mesh_label_match,
        scale_consistent,
        group_inference_sample,
    )
}


def software_observation(tools, commands, method_id):
    # Fixed command/argument catalogue. Never execute a model-supplied shell.
    import tempfile

    from .analysis_software import software_probe_source
    source = software_probe_source(commands, method_id == "method:v12:local_gyrification")
    from .analysis_agent import _write_regular

    script = tools.workdir / ".software_probe.py"
    _write_regular(script, tools.workdir, source)
    with tempfile.NamedTemporaryFile(
        dir=tools.control_store.root, suffix=".py", delete=False
    ) as stream:
        stream.write(source.encode())
        frozen = Path(stream.name)
    with tools._execution_lock:
        execution = tools.executor.run(
            script, timeout_seconds=120, frozen_source=frozen
        )
    if (
        execution.get("status") != "success"
        or execution.get("exit_code") != 0
        or execution.get("stdout_truncated")
    ):
        return False, {
            "execution": execution,
            "reason": "Fixed sandbox software probe failed",
        }
    prefix = "PRIMATEX_CONSTRAINT_PROBE="
    lines = [
        line[len(prefix) :]
        for line in execution.get("stdout", "").splitlines()
        if line.startswith(prefix)
    ]
    observation = json.loads(lines[-1]) if lines else {}
    rows = observation.get("commands", [])
    ok = [row.get("command") for row in rows] == commands and all(
        row.get("executable") is True for row in rows
    )
    return ok, {**observation, "execution": execution}


def compile_constraints(
    tools, method_id, task_category, plan_context, model_declared=None, product_contract=None
):
    saved = tools.control_store.latest("data_profile")
    if saved is None:
        raise ValueError("Call profile_data before compile_constraints")
    profile = saved["record"]
    if not isinstance(plan_context, dict) or len(canonical(plan_context)) > 100_000:
        raise ValueError("Bounded proposed plan required")
    if product_contract is not None and tools.knowledge_profile.name != "product_graph_planner":
        raise ValueError("Product contracts are isolated to product_graph_planner")
    files = (selected_files(profile, plan_context)
             if plan_context.get("data", {}).get("files") else []) if product_contract else selected_files(profile, plan_context)
    if any(item.get("read_error") for item in files):
        raise ValueError(
            "Selected profile contains unreadable inputs; inspect null fields and revise data"
        )
    from .analysis_unified_runtime import repository_for
    from .analysis_template_bindings import probe_result, environment_for
    from .analysis_condition_templates import evaluate
    repository = repository_for(tools)
    mapping_document, sha = repository.document("constraint_probes")
    mapping = mapping_document["constraints"]
    definitions, template_sha = repository.document("condition_templates")
    rows = []
    derived_categories = set()
    if any(value(item["format"]) in ("annot", "label.gii") for item in files):
        derived_categories.add("roi")
    if plan_context.get("analysis_scope", {}).get("inference") is True:
        derived_categories.add("group_inference")
    declarations = model_declared or {}
    for spec in mapping:
        applies = spec["applies_to"]
        if not ({"*", method_id, task_category, *derived_categories} & set(applies)):
            continue
        checker = spec["probe"]["checker"]
        parameters = spec["probe"]["parameters"]
        if checker == "software_available":
            commands = parameters["method_commands"].get(method_id)
            if method_id.startswith("self:"):
                requested = plan_context.get("method", {}).get("required_software")
                allowed = {
                    command
                    for group in parameters["method_commands"].values()
                    for command in group
                } | {"python:json", "python:math", "python:csv"}
                if isinstance(requested, list) and all(
                    isinstance(command, str) and command in allowed
                    for command in requested
                ):
                    commands = requested or ["python:json"]
            if commands:
                _, observation = software_observation(tools, commands, method_id)
                passed, observed = probe_result(checker, files, plan_context, parameters,
                    definitions=definitions, software_record=(commands, observation))
            else:
                passed, observed = False, {
                    "mapped_commands": [],
                    "status": "unverified",
                    "reason": "No executable software mapping. A self-written method must declare required_software using registered commands (explicit [] means standard library only).",
                }
        else:
            context = plan_context
            if (
                checker == "group_inference_sample"
                and task_category == "group_inference"
            ):
                context = {
                    **plan_context,
                    "analysis_scope": {
                        **plan_context.get("analysis_scope", {}),
                        "inference": True,
                    },
                }
            passed, observed = probe_result(checker, files, context, parameters,
                                            definitions=definitions)
        # Historical generic recon rules also covered pure derivative readers.
        # The method's actual input facts do not require reconstructing the source
        # again. Retain missing history as a warning, never as completed recon.
        if (product_contract and checker == "recon_complete"
                and product_contract["execution_scope"] == "supplied_derivatives"):
            spec = {**spec, "id": "recon_history:disclosure", "severity": "soft",
                    "on_fail": "warn_and_disclose", "source": product_contract["source"]}
            observed = {**observed, "reason": "Supplied-derivative read only; reconstruction history is not certified",
                        "policy": "Product contract scope, grounded in the selected method inputs"}
        if checker == "software_available":
            if product_contract:
                spec = {**spec, "source": product_contract["source"]}
            elif not method_id.startswith("self:"):
                card = tools._method_graph().read(method_id)
                spec = {**spec, "source": card.get("source_evidence", [])}
        declared = declarations.get(spec["id"])
        verdict = "pass" if passed else ("warn" if spec["severity"] == "soft" else "block")
        agreement = None if declared is None else declared == verdict
        rows.append(
            {
                "constraint_id": spec["id"],
                "severity": spec["severity"],
                "tool_observed": {
                    **observed,
                    "evidence_ref": f"data_profile.v{saved['version']:06d}.json",
                    "profile_sha256": saved["sha256"],
                },
                "model_declared": declared,
                "agreement": agreement,
                "conflict": agreement is False,
                "verdict": verdict,
                "on_fail": spec["on_fail"],
                "source": spec["source"],
            }
        )
    if product_contract:
        issues = []
        by_path = {value(f["path"]): f for f in files}
        for f in files:
            metric = value(f.get("metric"))
            if not metric:
                continue
            path = value(f["path"])
            hemi = Path(path).name[:2]
            mesh = [g for p, g in by_path.items() if str(Path(p).parent) == str(Path(path).parent)
                    and Path(p).name == hemi + ".white" and value(g.get("surface"))]
            n = value(metric["vertex_count"])
            if value(metric["finite_count"]) != n or not mesh or value(value(mesh[0]["surface"])["vertex_count"]) != n:
                issues.append({"path": path, "reason": "Metric must be finite and match observed native mesh cardinality"})
        rows.append({"constraint_id": "product_metric_mesh_identity", "severity": "hard",
                     "verdict": "block" if issues else "pass", "tool_observed": {"issues": issues,
                     "evidence_ref": f"data_profile.v{saved['version']:06d}.json",
                     "reason": "Actual metric/mesh lengths and finite counts; not anatomical validation"},
                     "source": product_contract["source"], "model_declared": None,
                     "agreement": None, "conflict": False, "on_fail": "block"})
    verified = value(profile.get("physical_scale_verified", {}))
    if verified is not True:
        rows.append(
            {
                "constraint_id": "scale_consistent:physical_scale",
                "severity": "soft",
                "tool_observed": {
                    "verified": verified,
                    "evidence_ref": f"data_profile.v{saved['version']:06d}.json",
                    "reason": "Physical acquisition scale not independently verified; disclose stored-coordinate interpretation",
                },
                "model_declared": declarations.get("scale_consistent:physical_scale"),
                "agreement": None,
                "conflict": False,
                "verdict": "warn",
                "on_fail": "warn_and_disclose",
            }
        )
    templated_ids = set()
    environment = environment_for(files, plan_context, {})
    for instance in definitions["extra_method_conditions"]:
        if instance["method_id"] != method_id:
            continue
        result = evaluate(instance, environment)
        declared = declarations.get(instance["id"])
        rows.append({
            "constraint_id": instance["id"], "severity": instance.get("severity", "hard"),
            "template": instance["template"], "verdict": result["verdict"],
            "tool_observed": {**result, "evidence_ref": f"data_profile.v{saved['version']:06d}.json"},
            "model_declared": declared, "agreement": None if declared is None else declared == result["verdict"],
            "conflict": declared is not None and declared != result["verdict"],
            "source": instance.get("source", []),
            "on_fail": "warn_and_disclose" if instance["template"] == "advisory" else "block",
        })
        templated_ids.update(source["method_fact_id"] for source in instance.get("source", []) if "method_fact_id" in source)
    unmapped = []
    if not method_id.startswith("self:"):
        method = tools._method_graph().read(method_id)["method"]
        mapped_ids = {
            source["method_fact_id"]
            for row in (rows if product_contract else mapping)
            for source in row.get("source", [])
            if "method_fact_id" in source
        }
        for condition in method.get("conditions", []) + method.get("inputs", []):
            if condition["id"] not in mapped_ids | templated_ids:
                unmapped.append(
                    {
                        "condition_id": condition["id"],
                        "statement": condition["statement"],
                        "status": "unverified",
                        "model_declared": declarations.get(condition["id"]),
                        "trust": "model-declared only; no executable probe mapping",
                    }
                )
    from .analysis_crossspecies import enabled as cross_enabled
    if cross_enabled(tools):
        from .analysis_crossspecies import observed_environment, evaluate_policy
        rows.extend(evaluate_policy(observed_environment(tools, plan_context), repository))
    record = {
        "schema_version": "primatex.constraints.v1",
        "method_id": method_id,
        "task_category": task_category,
        "derived_task_categories": sorted(derived_categories),
        "profile_sha256": saved["sha256"],
        "profile_version": saved["version"],
        "plan_context_sha256": digest(plan_core(plan_context)),
        "mapping_sha256": sha,
        "condition_templates_sha256": template_sha,
        "knowledge_store_sha256": repository.knowledge_digest(),
        "rows": rows,
        "unmapped_conditions": unmapped,
        "summary": {
            verdict: sum(row["verdict"] == verdict for row in rows)
            for verdict in ("pass", "warn", "block")
        },
    }
    sealed = tools.control_store.save("constraints", record)
    from .analysis_agent import _write_regular

    _write_regular(
        tools.workdir / "constraints.json", tools.workdir, canonical(record).decode()
    )
    return {
        "status": "blocked" if record["summary"]["block"] else "ok",
        "path": "/work/constraints.json",
        "constraints_sha256": sealed["sha256"],
        "version": sealed["version"],
        **record,
    }
