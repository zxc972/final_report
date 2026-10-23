"""Single-subject global products and public, non-oracle execution instructions."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from .analysis_profile_worker import value

METHOD = "method:v15:global_morphometry"
METRICS = (
    "brain_volume_mm3",
    "etiv_mm3",
    "total_area_mm2",
    "mean_thickness_mm",
    "hull_ratio",
)
COLUMNS = (
    "subject",
    "species",
    *METRICS,
    "scale_status",
    "scale_k",
    *("stored_" + name for name in METRICS),
)


def candidate(tools, spec, method, entries, files, intent, profile):
    if len(entries) != 1:
        raise ValueError(
            "Global morphometry describes one subject; aggregate verified subject results on the host"
        )
    entry = entries[0]
    prefix = f"/inputs/{entry['index']}/"
    paths = sorted(
        value(row["path"]) for row in files if value(row["path"]).startswith(prefix)
    )
    binding = {"aseg_stats": None, "mask_volume": None, "hemi_stats": {}, "pial": {}}
    binding["aseg_stats"] = next(
        (p for p in paths if p.endswith("/stats/aseg.stats")), None
    )
    binding["mask_volume"] = next(
        (p for p in paths if p.endswith("/mri/brainmask.mgz")), None
    )
    missing = []
    for hemi in ("lh", "rh"):
        matches = [
            p
            for p in paths
            if Path(p).name.startswith(hemi + ".aparc") and p.endswith(".stats")
        ]
        matches.sort(key=lambda p: (Path(p).name != hemi + ".aparc.stats", p))
        if matches:
            binding["hemi_stats"][hemi] = matches[0]
        else:
            missing.append("cortical_parc_stats:" + hemi)
        pial = next((p for p in paths if Path(p).name == hemi + ".pial"), None)
        if pial:
            binding["pial"][hemi] = pial
    if not binding["aseg_stats"] and not binding["mask_volume"]:
        missing.append("aseg_stats_or_brainmask")
    if len(binding["pial"]) != 2:
        binding["pial"] = {}
    selected = [binding["aseg_stats"], binding["mask_volume"]]
    selected = (
        [p for p in selected if p]
        + list(binding["hemi_stats"].values())
        + list(binding["pial"].values())
    )
    scale = trusted_scale(entry)
    tools.control_store.save("global_scale_observation", scale)
    notices = [
        "Single subject; no population inference; anatomical visual QC not independently passed.",
        "BrainSegVol is segmentation volume; eTIV is intracranial volume and must not substitute for brain volume.",
        "Area = bilateral WhiteSurfArea; thickness = area-weighted bilateral MeanThickness, not parcel ThickAvg.",
        "Hull ratio = summed pial area / summed 3D convex-hull area; not lGI.",
        "Scale processing history and physical acquisition calibration are distinct; calibration remains unverified.",
    ]
    if not scale["host_verified"]:
        notices.append(
            "Scale history unknown: physical columns and scale_k must be empty; retain stored values."
        )
    context = {
        "question": "Describe supplied global morphometry for " + entry["subject_id"],
        "data": {
            "files": selected,
            "subjects": [entry["subject_id"]],
            "profile_sha256": profile["sha256"],
            "profile_ref": f"data_profile.v{profile['version']:06d}.json",
            "species_declared": entry.get("species_declared"),
            "species_verified": entry.get("species_verified"),
        },
        "atlas": {
            "name": "not applicable",
            "version": None,
            "space": "native_stored",
            "hemisphere_rule": "Read both hemispheres; sum areas before global ratios",
            "applicable": False,
            "reason": "Global stats and full surfaces do not require regional correspondence",
            "mesh_bindings": [],
        },
        "method": {
            "method_id": METHOD,
            "name": method["name"],
            "reason": "Registered global public-output method",
        },
        "outputs": ["global_metrics.csv", "summary.json", "report.md"],
        "code_path": "/work/global_morphometry.py",
        "analysis_scope": {
            "inference": False,
            "comparison": "describe",
            "scale_policy": "within_input_only",
            "labels": {},
            "notices": notices,
            "global_bindings": binding,
            "global_scale": scale,
        },
    }
    return context, missing, [], {}


def trusted_scale(entry):
    """Re-read registered immutable source records; model declarations are ignored."""
    import hashlib

    raw = copy.deepcopy(entry.get("scale_observation") or {})
    sources = raw.get("sources") or []
    valid = bool(sources) and type(raw.get("rescaled")) is bool
    for source in sources:
        path = Path(source.get("path", ""))
        valid = valid and path.is_file() and not path.is_symlink()
        if valid:
            valid = hashlib.sha256(path.read_bytes()).hexdigest() == source.get(
                "sha256"
            )
    k = raw.get("k")
    valid = valid and type(k) in (int, float) and 0 < k < float("inf")
    valid = valid and (raw.get("rescaled") or k == 1)
    if not valid:
        return {
            "host_verified": False,
            "rescaled": None,
            "k": None,
            "status": "unknown",
            "sources": sources,
            "reason": "No verified source-bound processing-scale record",
        }
    return {
        **raw,
        "host_verified": True,
        "status": "verified" if raw["rescaled"] else "verified_not_rescaled",
        "physical_calibration_verified": False,
    }


def table_contract(plan):
    scope = plan["analysis_scope"]
    scale = scope["global_scale"]
    types = {
        key: "str" if key in {"subject", "species", "scale_status"} else "float"
        for key in COLUMNS
    }
    fixed = {
        "subject": plan["data"]["subjects"][0],
        "species": plan["data"]["species_declared"],
        "scale_status": scale["status"],
    }
    return {
        "schema": "primatex.global_table_contract.v1",
        "columns": types,
        "identity_columns": ["subject", "species"],
        "fixed_values": fixed,
        "allowed_values": {key: [val] for key, val in fixed.items()},
        "expected_rows": 1,
        "expected_identities": [fixed],
        "nullable_columns": [key for key in COLUMNS if key not in fixed],
        "row_rule": "One subject, bilateral global metrics; absent measures must be empty, not zero",
        "extra_columns_allowed": True,
        "alias_mapping": False,
        "source": "Public global method and protected subject-scale observation",
    }


def execution_card(payload):
    plan, bundle = payload["plan"], payload["execution_bundle"]
    scope = plan["analysis_scope"]
    scale = scope["global_scale"]
    lines = [
        "import primatex_ops as ops",
        *bundle["input_paths"],
        "ops.read_stats_measures(path)->dict[name:{value:float,unit:str}]",
        "ops.read_surface(path)->vertices,faces; ops.convex_hull_area_ratio(vertices,faces)->surface_area,hull_area,area_ratio",
        "ops.positive_mask_volume(path)->volume_mm3,positive_voxels (only if BrainSegVol absent)",
        "Code: " + plan["code_path"],
        "Outputs: global_metrics.csv,summary.json,report.md",
        "CSV: " + ",".join(COLUMNS),
        "1 row; subject="
        + plan["data"]["subjects"][0]
        + ";species="
        + str(plan["data"]["species_declared"])
        + ";scale_status="
        + scale["status"],
        "Missing=empty. CSV repr/%.17g; JSON native floats. JSON: methods,limitations.",
        "BrainSegVol/eTIV; total area=sum WhiteSurfArea; thickness=sum(area*MeanThickness)/sum(area).",
        "Hull=sum pial surface_area/sum hull_area, not mean of hemisphere ratios; not lGI.",
        "Physical=stored/k^power: thickness1,area2,volumes3,ratio0. k="
        + str(scale["k"])
        + "; unknown=>physical and k empty.",
        "Disclose software units, scale-history source, unverified physical calibration/QC, descriptive n=1.",
        "Full plan: " + bundle["bundle_ref"],
        "Write sealed script; run_python(); auto-finalize.",
    ]
    card = "\n".join(lines)
    if len(card) > 1500:
        raise ValueError("Global execution card exceeds 1500 characters")
    return {
        "status": "committed",
        "version": payload["version"],
        "execution_card": card,
        "state": payload.get("state"),
    }
