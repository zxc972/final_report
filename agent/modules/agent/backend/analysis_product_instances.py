"""Observed instance products and declarative workflow metadata propagation."""

from __future__ import annotations

import copy
import re
from pathlib import Path

from .analysis_control_store import digest
from .analysis_template_bindings import product_view, unwrap


def classify(record):
    path = Path(record["path"])
    fmt = record.get("format")
    stem = path.name.lower()
    if fmt == "surface":
        variant = {
            "white": "White",
            "pial": "Pial",
            "sphere": "Sphere",
            "sphere.reg": "SphereReg",
            "inflated": "Inflated",
            "midthickness": "Midthickness",
        }
        for name, subtype in sorted(variant.items(), key=lambda item: -len(item[0])):
            if stem.endswith("." + name) or ("." + name + ".") in stem:
                return "type:Surface." + subtype
        return "type:Surface"
    if fmt in {"surface_metric", "shape.gii"}:
        for name, subtype in {
            "thickness": "Thickness",
            "area": "Area",
            "curv": "Curvature",
            "curvature": "Curvature",
            "sulc": "Sulc",
            "lgi": "LGI",
        }.items():
            if stem.endswith("." + name) or ("." + name + ".") in stem:
                return "type:SurfaceMetric." + subtype
        return "type:SurfaceMetric"
    if fmt == "annot":
        for name, subtype in {
            "dkt": "AparcDKT",
            "a2009s": "AparcA2009s",
            "charm": "CHARM",
            "d99": "D99",
        }.items():
            if name in stem:
                return "type:Annotation." + subtype
        return (
            "type:Annotation.AparcDK" if ".aparc.annot" in stem else "type:Annotation"
        )
    if fmt == "label":
        return "type:Label.Cortex" if "cortex" in stem else "type:Label"
    if fmt == "stats":
        if stem == "aseg.stats":
            return "type:StatsTable.AsegStats"
        if re.fullmatch(r"[lr]h\.aparc.*\.stats", stem):
            return "type:StatsTable.CorticalParcStats"
        return "type:StatsTable"
    if fmt in {"tsv", "csv"}:
        return "type:SubjectTable.Participants"
    if fmt in {"nifti", "mgz"}:
        if stem in {"brainmask.mgz", "brainmask.nii.gz"}:
            # FreeSurfer's brainmask is a skull-stripped intensity image,
            # not a binary mask. This is a sourced naming convention only;
            # the file's producer and anatomical correctness stay unverified.
            return "type:Volume.BrainExtractedT1"
        if stem in {"brain_mask.nii.gz", "brain_mask.nii"}:
            return "type:Volume.BrainMask"
        if "aseg" in stem:
            return "type:Volume.Aseg"
        if any(term in stem for term in ("t1", "orig", "rawavg")):
            return "type:Volume.T1"
        return "type:Volume"
    return product_view(record)["type"]


def registry_entry(path, registry):
    if path.startswith("/inputs/"):
        index = path.split("/")[2]
        return (
            next(
                (
                    row
                    for position, row in enumerate(registry)
                    if row.get("input_index", position) == int(index)
                ),
                {},
            )
            if index.isdigit()
            else {}
        )
    matches = []
    for row in registry:
        root = row.get("path")
        if root and (path == root or path.startswith(root.rstrip("/") + "/")):
            matches.append(row)
    return max(matches, key=lambda row: len(row["path"])) if matches else {}


def import_profile(store, profile, registry, *, activity_id=None):
    with store.transaction():
        return _import_profile(store, profile, registry, activity_id=activity_id)


def profile_products(profile, registry):
    """Yield typed observations; also used by offline matching without a database."""
    raw = unwrap(profile)
    for observed, source_record in zip(raw["files"], profile["files"]):
        path = observed["path"]
        registered = registry_entry(path, registry)
        geometry = observed.get("surface") or {}
        metric = observed.get("metric") or {}
        labels = observed.get("label") or {}
        volume = observed.get("volume") or {}
        fmt = observed.get("format")
        mesh = geometry.get("vertex_count") or metric.get("vertex_count")
        if fmt in {"annot", "label.gii", "shape.gii"} and mesh is None:
            mesh = labels.get("vertex_count")
        if fmt == "label":
            mesh = None
        hemi = geometry.get("hemisphere")
        if isinstance(hemi, dict):
            hemi = hemi.get("value")
        hemi_source = (
            (source_record.get("surface", {}).get("value") or {})
            .get("hemisphere", {})
            .get("source", "unknown")
        )
        if hemi is None and Path(path).name.startswith(("lh.", "rh.")):
            hemi = Path(path).name[:2]
            hemi_source = "filename convention only"
        hemi = {"left": "lh", "right": "rh"}.get(hemi, hemi)
        identifier = "product:" + digest([path, observed.get("sha256")])
        attrs = {
            "subject": registered.get("subject_id"),
            "species": registered.get("species_declared"),
            "species_verified": registered.get("species_verified"),
            "hemisphere": hemi,
            "space": None,
            "mesh": mesh,
            "scale_status": {
                "rescaled": None,
                "factor": None,
                "verified": False,
                "basis": "No trusted processing-history binding",
            },
            "atlas": None,
            "measure": metric.get("measure") or (Path(path).name.rsplit(".", 1)[-1] if fmt == "surface_metric" else None),
            "label_table": labels.get("label_names"),
            "unit": metric.get("units") or volume.get("units"),
            "voxel_size": volume.get("voxel_size_mm"),
            "vector_ndim": metric.get("ndim"),
            "face_width": geometry.get("face_width"),
            "index_count": labels.get("vertex_count") if fmt == "label" else None,
            "columns": (observed.get("table") or {}).get("columns"),
            "n_subjects": (
                len(set(observed.get("subject") or [])) if fmt == "tsv" else None
            ),
            "nonempty_columns": (observed.get("table") or {}).get("nonempty_columns"),
            "column_types": (observed.get("table") or {}).get("column_types"),
        }
        if registered.get("scale_observation"):
            from .analysis_global_method import trusted_scale
            observed_scale = trusted_scale(registered)
            attrs["scale_status"] = {"rescaled": observed_scale["rescaled"], "factor": observed_scale["k"],
                                     "verified": observed_scale["host_verified"], "source": observed_scale.get("sources", []),
                                     "physical_calibration_verified": False}
        if fmt in {"annot", "stats"} and hemi:
            attrs["atlas_file_stem"] = Path(path).name[3:].rsplit(".", 1)[0]
        if fmt == "annot":
            from .analysis_atlas_identity import identify
            identity = identify(Path(path).name[3:-6])
            if identity:
                attrs["atlas"] = identity["canonical_name"]
                attrs["atlas_file_stem"] = identity["file_stem"]
                attrs["atlas_naming_source"] = identity["source_url"]
        attrs.update({k: v for k, v in (observed.get("attributes") or {}).items() if k in attrs})
        properties = {
            "path": path,
            "sha256": observed.get("sha256"),
            "fingerprint": source_record.get("sha256", {}).get("source"),
            "profile_fields": source_record,
            "format": fmt,
            "attributes": attrs,
            "attribute_sources": {
                "mesh": {
                    "path": path,
                    "method": "Actual geometry/vector/annotation count, never filename resolution",
                },
                "hemisphere": {"path": path, "method": hemi_source},
                "species": {
                    "registry_entry": registered,
                    "method": "Explicit registration only",
                },
                "atlas": {
                    "value": attrs.get("atlas"),
                    "reason": "Source-backed filename convention only; atlas protocol/version and correctness unverified",
                },
                "space": {
                    "value": None,
                    "reason": "No independently verified coordinate-space metadata",
                },
            },
            "type_classification": "Format/header plus explicit filename convention for subtype; no species or spatial verification",
            "source_processing_activity": None,
            "read_error": observed.get("read_error"),
            "profile_sha256": digest(profile),
        }
        product_type = classify(observed)
        yield identifier, product_type, properties, registered


def _import_profile(store, profile, registry, *, activity_id=None):
    profile_sha = digest(profile)
    activity = activity_id or "activity:profile:" + profile_sha
    store.node(
        activity,
        "instance",
        "Activity",
        "Read-only data profiling",
        {
            "activity_type": "profile_observation",
            "profile_sha256": profile_sha,
            "scope": "Metadata observation; not creation or reconstruction of source MRI",
        },
    )
    snapshot = "profile:" + profile_sha
    store.node(
        snapshot,
        "instance",
        "ProfileSnapshot",
        snapshot,
        {"profile_sha256": profile_sha, "source_file_generation_claimed": False},
    )
    store.edge(
        snapshot,
        activity,
        "wasGeneratedBy",
        {"prov_namespace": "http://www.w3.org/ns/prov#"},
    )
    products = []
    for identifier, product_type, properties, registered in profile_products(profile, registry):
        path = properties["path"]
        if store.get_node(product_type) is None:
            product_type = "type:Product"
        store.node(identifier, "instance", "Product", Path(path).name, properties)
        store.edge(identifier, product_type, "instanceOf")
        store.edge(
            activity,
            identifier,
            "used",
            {"scope": "File was read for metadata observation"},
        )
        store.edge(snapshot, identifier, "describes")
        if registered.get("subject_id"):
            subject = "subject:" + registered["subject_id"]
            store.node(
                subject,
                "instance",
                "Subject",
                registered["subject_id"],
                {
                    "species_declared": registered.get("species_declared"),
                    "species_verified": registered.get("species_verified"),
                    "source": registered.get("source"),
                },
            )
            store.edge(identifier, subject, "ofSubject")
        products.append(identifier)
    return {
        "profile": snapshot,
        "activity": activity,
        "products": products,
        "source_file_generation_claimed": False,
    }


def expression(value, inputs, parameters):
    if not isinstance(value, dict):
        return value
    if "constant" in value:
        return copy.deepcopy(value["constant"])
    if "parameter" in value:
        return parameters.get(value["parameter"], value.get("default"))
    if "inherit" in value:
        slot, key = value["inherit"].split(".", 1)
        return copy.deepcopy(inputs.get(slot, {}).get("attributes", {}).get(key))
    if "object" in value:
        return {
            key: expression(item, inputs, parameters)
            for key, item in value["object"].items()
        }
    if "when" in value:
        rule = value["when"]
        return (
            expression(value["then"], inputs, parameters)
            if parameters.get(rule["parameter"]) == rule["equals"]
            else None
        )
    raise ValueError("Unknown workflow attribute expression")


def propagate(step, output_index, inputs, parameters):
    output = step["outputs"][output_index]
    parameters = {**step.get("default_parameters", {}), **parameters}
    enabled = output.get("enabled_when")
    if enabled and parameters.get(enabled["parameter"]) != enabled["equals"]:
        return None
    attributes = {
        key: expression(rule, inputs, parameters)
        for key, rule in output.get("attribute_rules", {}).items()
    }
    return {
        "type": output["type"],
        "attributes": attributes,
        "attribute_trust": "Expected workflow output declaration; not observed or verified until a real activity and output checks bind it",
        "source": step["source"],
        "step": step["id"],
    }
