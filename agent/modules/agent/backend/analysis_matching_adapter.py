"""Shared typed matching boundary for plan_analysis and frozen offline experiments."""

from __future__ import annotations

from . import analysis_csp_matching as csp
from .analysis_product_instances import profile_products

HEMI = {
    "surface",
    "white_surface",
    "pial_surface",
    "surface_metric",
    "annotation",
    "cortex_label",
    "registration_surface",
    "cortical_parc_stats",
}
TYPE_MAP = {
    "surface": "type:Surface",
    "white_surface": "type:Surface.White",
    "pial_surface": "type:Surface.Pial",
    "registration_surface": "type:Surface.SphereReg",
    "surface_metric": "type:SurfaceMetric",
    "annotation": "type:Annotation",
    "cortex_label": "type:Label.Cortex",
    "subject_table": "type:SubjectTable",
    "volume": "type:Volume",
    "t1_volume": "type:Volume.T1",
    "t2_volume": "type:Volume.T2",
    "brainmask": "type:Volume.BrainExtractedT1",
    "aseg_presurf": "type:Volume.Aseg",
    "wm_segmentation": "type:Volume.TissuePVE.WM",
    "gm_4d": "type:Volume.GM4D",
    "gm_mask": "type:Volume.GMMask",
    "design_matrix": "type:StatsTable.DesignMatrix",
    "contrast": "type:StatsTable.ContrastMatrix",
    "aseg_stats": "type:StatsTable.AsegStats",
    "cortical_parc_stats": "type:StatsTable.CorticalParcStats",
}
METRIC_TYPES = {
    "thickness": "Thickness",
    "area": "Area",
    "curv": "Curvature",
    "sulc": "Sulc",
    "lgi": "LGI",
}


def inventory(profile, entries):
    registry = [
        {
            **{k: v for k, v in e.items() if k != "root"},
            "input_index": e.get("index", e.get("input_index")),
            "path": str(e.get("root", e.get("path", ""))),
        }
        for e in entries
    ]
    result = []
    for identifier, kind, props, registered in profile_products(profile, registry):
        if props.get("read_error") or props["profile_fields"].get("read_error"):
            continue
        result.append(
            {
                "id": props["path"],
                "type": kind,
                "attrs": props["attributes"],
                "profile_product_id": identifier,
            }
        )
    return result


def hierarchy(document, required=()):
    # Unsupported recipe requirements have explicit types with no observed instances
    # or producer. They cannot accidentally bind to an arbitrary Product.
    known = {t["id"] for t in document["types"]}
    extra = [
        {"id": "requirement:" + r, "parent": "type:Product"}
        for r in required
        if r not in TYPE_MAP and "requirement:" + r not in known
    ]
    return csp.TypeHierarchy([*document["types"], *extra])


def problem(spec, entries, products, intent, atlas, definitions, types):
    """Expand method slots once per subject/hemisphere and requested metric.

    A sparse cortex.label is checked for subject/hemisphere identity; its length
    is never compared with a full mesh. Full meshes bind metric/annotation/white.
    """
    slots, constraints = [], []
    measures = spec.get("metric_measures", intent["measures"])
    h = hierarchy(types, spec["required_products"])

    def add(need, entry=None, hemi=None, measure=None, alternatives=None):
        scope = (entry["subject_id"] + "/" + (hemi or "global")) if entry else "cohort"
        name = scope + "/" + need + ((":" + measure) if measure else "")
        kind = TYPE_MAP.get(need, "requirement:" + need)
        if measure in METRIC_TYPES:
            kind = "type:SurfaceMetric." + METRIC_TYPES[measure]
        preference = spec.get("slot_preferences", {}).get(need, {})
        kind = preference.get("required_type", kind)
        scoped = [
            p
            for p in products
            if h.subsumes(kind, p["type"])
            and (not entry or p["attrs"].get("subject") == entry["subject_id"])
            and (not hemi or p["attrs"].get("hemisphere") == hemi)
        ]
        if preference.get("type_priority"):
            kind = next(
                (
                    t
                    for t in preference["type_priority"]
                    if any(h.subsumes(t, p["type"]) for p in scoped)
                ),
                kind,
            )
        unary = []
        if preference.get("attribute") and scoped:
            attr = preference["attribute"]
            choices = {p["attrs"].get(attr) for p in scoped} - {None}
            preferred = preference.get("preferred_values", [])
            if choices:
                best = min(
                    choices,
                    key=lambda x: (
                        preferred.index(x) if x in preferred else len(preferred),
                        x,
                    ),
                )
                unary.append({"kind": "attr_equals", "attr": attr, "value": best})
        if entry:
            unary.append(
                {"kind": "attr_equals", "attr": "subject", "value": entry["subject_id"]}
            )
            # Preserve unknown declarations for descriptive analyses; never infer species.
            if entry.get("species_declared") is not None:
                unary.append(
                    {
                        "kind": "attr_equals",
                        "attr": "species",
                        "value": entry["species_declared"],
                    }
                )
        if hemi:
            unary.append({"kind": "attr_equals", "attr": "hemisphere", "value": hemi})
        if measure and measure not in METRIC_TYPES:
            unary.append({"kind": "attr_equals", "attr": "measure", "value": measure})
        if need == "annotation" and atlas:
            unary.append(
                {"kind": "attr_equals", "attr": "atlas_file_stem", "value": atlas}
            )
        # Native/stored is the existing within-input policy, not evidence of a
        # verified coordinate system. Explicit standard spaces require observation.
        if intent.get("space") and intent["space"] not in {
            "native",
            "native_stored",
            "stored",
        }:
            if need in HEMI:
                unary.append(
                    {"kind": "attr_equals", "attr": "space", "value": intent["space"]}
                )
        elif need in HEMI:
            unary.append(
                {
                    "kind": "attr_in",
                    "attr": "space",
                    "values": [None, "native", "native_stored", "stored"],
                }
            )
        slot = {
            "name": name,
            "type": kind,
            "unary": unary,
            "need": need,
            "scope": scope,
            "subject": entry["subject_id"] if entry else None,
            "hemisphere": hemi,
        }
        if alternatives:
            slot.update(type="type:Product", types=[TYPE_MAP[a] for a in alternatives])
        slots.append(slot)
        return slot

    for need in spec["required_products"]:
        if need == "subject_table":
            add(need)
            continue
        for e in entries:
            for hemi in ("lh", "rh") if need in HEMI else (None,):
                for measure in measures if need == "surface_metric" else (None,):
                    add(need, e, hemi, measure)
    for alternatives in spec.get("alternative_products", []):
        for e in entries:
            proposed = [add(need, e) for need in alternatives]
            dom = csp.domains(proposed, products, h)
            valid = [s for s in proposed if dom[s["name"]]]
            slots[:] = [s for s in slots if s not in proposed or s in valid]
            # Retain every valid source as a sealed fallback. An invalid optional
            # alternative cannot make a valid OR requirement unsatisfiable.
            if not valid:
                add("_or_".join(alternatives), e, alternatives=alternatives)
    for need in spec.get("optional_products", []):
        for e in entries:
            optional = [
                add(need, e, hemi)
                for hemi in (("lh", "rh") if need in HEMI else (None,))
            ]
            if not all(csp.domains(optional, products, h).values()):
                slots[:] = [s for s in slots if s not in optional]

    instances = list(spec.get("conditions", [])) + list(
        spec.get("matching_conditions", [])
    )
    if spec.get("needs_parcellation"):
        instances += definitions["legacy_probe_groups"]["mesh_label_match"][
            "each_annotation"
        ]
    scopes = sorted({s["scope"] for s in slots if s["hemisphere"]})
    for instance in instances:
        if instance.get("template") != "attr_equal":
            continue
        params = instance["parameters"]
        attrs = params.get("attributes", [params.get("attribute")])
        attrs = [{"species_declared": "species"}.get(a, a) for a in attrs if a]
        if params.get("across_subjects"):
            for attr in attrs:
                names = [s["name"] for s in slots if s["need"] == "annotation"]
                if len(names) > 1:
                    constraints.append(
                        {
                            "kind": "attr_equal",
                            "slots": names,
                            "attrs": ["atlas_file_stem" if attr == "atlas" else attr],
                            "severity": instance.get("severity", "hard"),
                            "source_id": instance.get("id", "group_identity"),
                        }
                    )
            continue
        for scope in scopes:
            for attr in attrs:
                names = [
                    s["name"]
                    for s in slots
                    if s["scope"] == scope
                    and s["need"] in params.get("slots", [])
                    and not (attr == "mesh" and s["need"] == "cortex_label")
                ]
                if len(names) > 1:
                    constraints.append(
                        {
                            "kind": "attr_equal",
                            "slots": names,
                            "attrs": [attr],
                            "severity": instance.get("severity", "hard"),
                            "source_id": instance.get("id", "method_attr_equal"),
                        }
                    )
    return {"slots": slots, "constraints": constraints, "hierarchy": h}


def match(spec, entries, products, intent, atlas, definitions, types):
    task = problem(spec, entries, products, intent, atlas, definitions, types)
    result = csp.solve(
        task["slots"],
        products,
        task["constraints"],
        task["hierarchy"],
        preferred_space=intent.get("space"),
    )
    result["matching_stats"] = {
        "domain_sizes": result["domain_sizes"],
        "search_nodes": result["stats"]["nodes"],
        "pruned": result["stats"]["pruned"],
        "truncated": result["truncated"],
    }
    result["problem"] = task
    result["conflicts"] = []
    if not result["solutions"] and not result["missing"]:
        result["conflicts"] = [
            {
                "constraint_id": c.get("source_id"),
                "slots": c["slots"],
                "attributes": c["attrs"],
            }
            for c in task["constraints"]
            if c.get("severity", "hard") == "hard"
        ]
        if not result["conflicts"]:
            result["conflicts"] = [
                {
                    "constraint_id": "slot_product_injectivity",
                    "slots": [s["name"] for s in task["slots"]],
                    "attributes": [],
                }
            ]
    return result


def missing_targets(result):
    """Keep alternatives typed; no filename-derived type/space goals."""
    out = []
    by_name = {s["name"]: s for s in result["problem"]["slots"]}
    for missing in result["missing"]:
        slot = by_name[missing["slot"]]
        attrs = {}
        for c in missing["unary"]:
            if c["kind"] == "attr_equals":
                attrs[c["attr"]] = c["value"]
            elif c["kind"] == "attr_in":
                attrs[c["attr"]] = {"in": c["values"]}
        out.append(
            {
                "type": missing["type"],
                "attrs": attrs,
                "slot": missing["slot"],
                "need": slot["need"],
                **({"types": missing["types"]} if "types" in missing else {}),
            }
        )
    return out


def planning_targets(result, spec, entries):
    targets = missing_targets(result)
    if spec["execution_scope"] == "full_processing":
        kind = (
            "type:SurfaceMetric.LGI"
            if spec["method_id"].endswith("local_gyrification")
            else "requirement:complete_analysis_recipe"
        )
        for entry in entries:
            for hemi in ("lh", "rh"):
                attrs = {"subject": entry["subject_id"], "hemisphere": hemi}
                if entry.get("species_declared"):
                    attrs["species"] = entry["species_declared"]
                targets.append(
                    {
                        "type": kind,
                        "attrs": attrs,
                        "slot": entry["subject_id"] + "/" + hemi + "/recipe",
                    }
                )
    return targets
