"""Human Destrieux/DK overlap bindings and shared host recomputation.

The overlap geometry intentionally reuses algorithm 2 in planning and host
verification; this component is not an independent algorithm implementation.
Existing ROI statistics and numerical comparison tolerances remain separate.
"""
from __future__ import annotations
import hashlib
from pathlib import Path, PurePosixPath
from . import analysis_numeric_reference as nr
from . import analysis_region_resolver as rr
from .analysis_input_links import resolve_input

ROLES = {"analysis_annotation", "reference_annotation", "white_surface"}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def calculate(region, paths, records, provenance):
    reference, reference_names = nr.read_annotation(paths["reference_annotation"])
    analysis, analysis_names = nr.read_annotation(paths["analysis_annotation"])
    vertices, faces = nr.read_surface(paths["white_surface"])
    if len(reference) != len(analysis) or len(analysis) != len(vertices):
        raise ValueError("DK, Destrieux and white surface do not share a vertex mesh")
    regions = rr.regions_from_mapping(rr.named(reference, reference_names), records, "DK")
    return rr.resolve_request(region, regions, rr.named(analysis, analysis_names),
                              rr.vertex_areas(vertices, faces), provenance=provenance)


def resolve_native(entry, hemisphere, annotation_path, region, records, mapping_sha):
    if hemisphere not in {"lh", "rh"} or not all(k in entry for k in ["root", "index", "subject_id"]):
        raise ValueError("Missing explicit subject root and hemisphere for region overlap")
    prefix = f"/inputs/{entry['index']}/"
    relative = {"analysis_annotation": f"label/{hemisphere}.aparc.a2009s.annot",
                "reference_annotation": f"label/{hemisphere}.aparc.annot",
                "white_surface": f"surf/{hemisphere}.white"}
    if annotation_path != prefix + relative["analysis_annotation"]:
        raise ValueError("Destrieux annotation is not bound to this subject and hemisphere")
    paths, inputs = {}, {}
    for role, name in relative.items():
        target = Path(entry["root"]) / name
        if not target.is_file():
            raise ValueError(f"Missing region overlap product {role}: {prefix}{name}")
        paths[role] = resolve_input(target, Path(entry["root"]))
        inputs[role] = {"path": prefix + name, "sha256": sha(paths[role])}
    provenance = {"subject": entry["subject_id"], "hemisphere": hemisphere,
                  "species_declared": "human", "reference_atlas": "DK",
                  "analysis_atlas": "aparc.a2009s", "inputs": inputs,
                  "mapping_sha256": mapping_sha, "algorithm_sha256": sha(Path(rr.__file__))}
    return calculate(region, paths, records, provenance)


def recheck(plan, resolve, records, mapping_sha):
    checks = []
    for evidence in plan.get("analysis_scope", {}).get("region_overlap_evidence", []):
        provenance = evidence["provenance"]
        if plan.get("data", {}).get("species_declared") != "human" or provenance.get("species_declared") != "human":
            raise ValueError("Nonhuman region overlap evidence is not permitted")
        if provenance.get("reference_atlas") != "DK" or provenance.get("analysis_atlas") != "aparc.a2009s":
            raise ValueError("Region overlap protocols are not the sealed DK/Destrieux pair")
        inputs = provenance["inputs"]
        if set(inputs) != ROLES or provenance["mapping_sha256"] != mapping_sha or provenance["algorithm_sha256"] != sha(Path(rr.__file__)):
            raise ValueError("Region overlap source binding changed")
        subject, hemi = provenance["subject"], provenance["hemisphere"]
        if subject not in plan["data"]["subjects"] or hemi not in {"lh", "rh"}:
            raise ValueError("Region overlap subject/hemisphere is not sealed")
        expected_names = {"analysis_annotation": f"{hemi}.aparc.a2009s.annot", "reference_annotation": f"{hemi}.aparc.annot", "white_surface": f"{hemi}.white"}
        paths = {}
        for role, binding in inputs.items():
            if binding["path"] not in plan["data"]["files"] or PurePosixPath(binding["path"]).name != expected_names[role]:
                raise ValueError("Unsealed or wrong-hemisphere region overlap input")
            paths[role] = resolve(binding["path"])
            if sha(paths[role]) != binding["sha256"]:
                raise ValueError("Region overlap input fingerprint changed")
        if len({str(PurePosixPath(row["path"]).parts[:3]) for row in inputs.values()}) != 1:
            raise ValueError("Region overlap inputs are from different registered roots")
        labels, actual, error = calculate(evidence["region"], paths, records, provenance)
        if error or actual != evidence:
            raise ValueError("Region overlap evidence differs from shared algorithm recomputation")
        group = plan["analysis_scope"]["labels"][subject + "/" + hemi]
        if group["annotation"] != inputs["analysis_annotation"]["path"] or not set(labels) <= {row["name"] for row in group["labels"]}:
            raise ValueError("Region overlap labels differ from sealed analysis scope")
        checks.append({"subject": subject, "hemisphere": hemi, "region": evidence["region"],
                       "status": "pass", "independent_implementation": False,
                       "coverage": actual["coverage"], "purity": actual["purity"], "dice": actual["dice"]})
    return checks


def disclosure(evidence):
    p = evidence["provenance"]
    return (f"Region overlap {p['subject']}/{p['hemisphere']} {evidence['region']}: "
            f"{evidence['verdict']}; coverage={evidence['coverage']:.6f}, purity={evidence['purity']:.6f}, "
            f"Dice={evidence['dice']:.6f}; ambiguous labels=" + ", ".join(evidence["ambiguous"]))


def conclusion_checks(plan):
    return [{"constraint_id": "region_overlap:" + e["provenance"]["subject"] + ":" + e["provenance"]["hemisphere"] + ":" + e["region"],
             "severity": "soft", "mandatory": True,
             "verdict": "warn" if e["verdict"] == "qualified" else "pass",
             "tool_observed": {"reason": disclosure(e), "coverage": e["coverage"], "purity": e["purity"],
                               "dice": e["dice"], "ambiguous": e["ambiguous"],
                               "conclusion_ceiling": "qualified" if e["verdict"] == "qualified" else None}}
            for e in plan.get("analysis_scope", {}).get("region_overlap_evidence", [])]


def attach_card(card, plan):
    evidence = plan.get("analysis_scope", {}).get("region_overlap_evidence", [])
    if not evidence:
        return card
    return {**card, "region_resolution": [{"region": e["region"], "subject": e["provenance"]["subject"],
            "hemisphere": e["provenance"]["hemisphere"], "verdict": e["verdict"], "coverage": e["coverage"],
            "purity": e["purity"], "dice": e["dice"], "ambiguous": e["ambiguous"]} for e in evidence],
            "required_disclosures": [*card.get("required_disclosures", []),
                                     *(disclosure(e) for e in evidence if e["verdict"] == "qualified")]}
