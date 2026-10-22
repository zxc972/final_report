"""Public paired-ROI definition and an independent host calculation."""
from pathlib import Path
import hashlib
import json
import math


def applies(plan):
    return (plan.get("analysis_scope", {}).get("comparison") == "asymmetry"
            and plan.get("method", {}).get("method_id", "").endswith("surface_annotation_roi"))


def definition():
    path = Path(__file__).resolve().parent.parent / "knowledge_analysis/asymmetry_contract_r13.json"
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != path.with_suffix(".sha256").read_text().strip():
        raise ValueError("Asymmetry contract digest mismatch")
    return json.loads(raw)


def independent_indices(rows):
    pairs = {}
    for row in rows:
        key = (row["subject"], row["metric"], row["name"])
        group = pairs.setdefault(key, {})
        if row["hemisphere"] in group:
            raise ValueError("Duplicate hemisphere in paired ROI")
        group[row["hemisphere"]] = row["mean"]
    result = {}
    for key, pair in pairs.items():
        if set(pair) != {"lh", "rh"}:
            raise ValueError("Both hemispheres are required for each named parcel")
        denominator = math.fsum([pair["lh"], pair["rh"]]) / 2
        if denominator == 0:
            raise ValueError("Undefined zero-denominator asymmetry")
        result[key] = (pair["lh"] - pair["rh"]) / denominator
    return result
