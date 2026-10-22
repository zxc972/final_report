"""Bind existing probe contracts to generic template instances, without reusing their verdicts."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from .analysis_condition_templates import evaluate_all
from .analysis_profile_worker import value

ROOT = Path(__file__).resolve().parent.parent / "knowledge_analysis"


def checked_definitions():
    path = ROOT / "condition_templates.json"
    raw = path.read_bytes()
    if (
        hashlib.sha256(raw).hexdigest()
        != path.with_suffix(".sha256").read_text().strip()
    ):
        raise ValueError("Condition template definitions digest mismatch")
    return json.loads(raw)


def unwrap(record):
    if isinstance(record, dict) and "value" in record:
        return unwrap(record["value"])
    if isinstance(record, dict):
        return {key: unwrap(item) for key, item in record.items()}
    if isinstance(record, list):
        return [unwrap(item) for item in record]
    return record


def product_view(item):
    record = unwrap(item)
    fmt = record.get("format")
    geometry = record.get("surface") or {}
    metric = record.get("metric") or {}
    labels = record.get("label") or {}
    family = {
        "surface": "type:Surface",
        "surface_metric": "type:SurfaceMetric",
        "annot": "type:Annotation",
        "label.gii": "type:Annotation",
        "label": "type:Label",
        "shape.gii": "type:SurfaceMetric",
        "nifti": "type:Volume",
        "mgz": "type:Volume",
        "stats": "type:StatsTable",
        "tsv": "type:SubjectTable",
    }.get(fmt, "type:Product")
    mesh = (
        geometry.get("vertex_count")
        or metric.get("vertex_count")
        or (labels.get("vertex_count") if fmt in {"annot", "label.gii"} else None)
    )
    return {
        "id": record.get("path"),
        "path": record.get("path"),
        "type": family,
        "attributes": {
            "mesh": mesh,
            **labels,
            "vector_ndim": metric.get("ndim"),
            "face_width": geometry.get("face_width"),
            "format": fmt,
        },
        "observations": record,
    }


def environment_for(files, context, parameters):
    rows = [product_view(item) for item in files]
    by_path = {row["path"]: row for row in rows}
    annotations = [row for row in rows if row["type"] == "type:Annotation"]
    reconstruction = [
        row["observations"]["recon"] for row in rows if row["observations"].get("recon")
    ]
    subject_ids = {
        subject
        for row in rows
        for subject in (row["observations"].get("subject") or [])
    }
    volumes = [
        row["observations"]["volume"]
        for row in rows
        if row["observations"].get("volume")
    ]
    units = sorted(
        {
            row.get("units")
            for row in volumes
            if row.get("units") and row["units"] != "unknown"
        }
    )
    markers = set()
    for row in rows:
        path = row["path"] or ""
        if "_1mm" in path or "/1mm/" in path:
            markers.add("1mm_filename_convention")
        elif "native" in path.lower():
            markers.add("native_filename_convention")
    scope = context.get("analysis_scope", {})
    env = {
        "slots": {
            "products": rows,
            "annotations": annotations,
            "metrics": [row for row in rows if row["type"] == "type:SurfaceMetric"],
            "labels": [row for row in rows if row["type"] == "type:Label"],
            "surfaces": [row for row in rows if row["type"] == "type:Surface"],
            "volume_units": [
                {"id": unit, "attributes": {"unit": unit}} for unit in units
            ],
            "named_scales": [
                {"id": tag, "attributes": {"scale_marker": tag}}
                for tag in sorted(markers)
            ],
        },
        "objects": {
            "reconstructions": reconstruction,
            "qforms": [
                {"conflict": row.get("qform_sform_conflict") is True} for row in volumes
            ],
            "subject_ids": sorted(subject_ids),
            "groups": scope.get("groups", {}),
            "separate_scales": scope.get("scale_policy")
            in {"within_input_only", "dimensionless_per_input"},
            "unit_conversion_supplied": bool(scope.get("unit_conversion")),
        },
        "plan": context,
        "is_subtype": lambda actual, requested: actual == requested
        or requested == "type:Product",
        "probe_parameters": parameters,
    }
    views = []
    for annotation in annotations:
        candidates = [
            binding
            for binding in context.get("atlas", {}).get("mesh_bindings", [])
            if binding.get("label") == annotation["path"]
        ]
        binding = candidates[0] if len(candidates) == 1 else {}
        surface = by_path.get(binding.get("surface"))
        registration = by_path.get(binding.get("registration_ref"), {})
        declaration = all(
            isinstance(binding.get(key), str) and binding[key].strip()
            for key in ("mesh_origin", "space", "registration_ref")
        )
        qualifiers = {
            "declared_origin_and_space": declaration,
            "registration_sha256": registration.get("observations", {}).get("sha256"),
            "registration_ref": binding.get("registration_ref"),
            "scope": "Recorded declaration and actual profiled reference fingerprint; not anatomical correspondence",
        }
        views.append(
            {
                **env,
                "slots": {
                    **env["slots"],
                    "annotation": [annotation],
                    "surface": [surface] if surface else [],
                },
                "objects": {
                    **env["objects"],
                    "matching_bindings": candidates,
                    "binding_provenance": [qualifiers],
                },
            }
        )
    env["annotation_views"] = views
    return env


def probe_result(
    name, files, context, parameters, *, definitions=None, software_record=None
):
    definitions = definitions or checked_definitions()
    spec = definitions["legacy_probe_groups"][name]
    env = environment_for(files, context, parameters)
    if software_record is not None:
        commands, observation = software_record
        env["software"] = observation.get("commands", [])
        env["software_execution"] = observation.get("execution")
        env["objects"]["required_commands"] = commands or []
    roots = copy.deepcopy(spec.get("root", []))
    for instance in roots:
        if instance["template"] == "software":
            instance["parameters"]["commands"] = env["objects"].get(
                "required_commands", []
            )
        if instance["template"] == "cardinality" and instance["parameters"].get(
            "groups"
        ):
            instance["parameters"]["minimum"] = parameters.get(
                "minimum_independent_subjects", 2
            )
    active = []
    for instance in roots:
        when = instance.pop("when", None)
        if when is not None:
            from .analysis_condition_templates import lookup

            actual = lookup(env, when["path"])
            if ("equals" in when and actual != when["equals"]) or (
                "in" in when and actual not in when["in"]
            ):
                continue
        active.append(instance)
    results = evaluate_all(active, env)
    per_binding = []
    for view in env["annotation_views"]:
        if spec.get("each_annotation"):
            per_binding.append(evaluate_all(spec["each_annotation"], view))
    passed = results["verdict"] == "pass" and all(
        row["verdict"] == "pass" for row in per_binding
    )
    observed = {
        "reason": spec["scope"],
        "template_evaluations": results["rows"],
        "binding_evaluations": per_binding,
        "evidence_basis": "Actual profile fields plus explicitly labeled plan declarations",
    }
    if software_record is not None:
        observed = {**software_record[1], **observed}
    return passed, observed
