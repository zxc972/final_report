"""Algorithm 2: geometric region resolution by area-weighted vertex overlap.

Problem. A request names a region R (e.g. "frontal lobe") that is defined in a
*reference* parcellation (DK grouped by FreeSurfer --lobesStrict), while the
data carry a different *analysis* parcellation (DKT, Destrieux, ...). Name
matching cannot translate between atlases whose label vocabularies differ, so
the translation is computed on a shared mesh M (fsaverage or the subject's own
surface) where both parcellations exist.

Definitions (a_v = vertex area, A(S) = sum of a_v over S, V_l = vertices of
analysis label l, V_R = vertices of reference region R):

    inclusion   w(l, R) = A(V_l ∩ V_R) / A(V_l)
    assignment  g(l)    = argmax_R w(l, R)   if max_R w(l, R) >= theta
                        = ⊥ (ambiguous)      otherwise
    estimate    Ṽ_R     = ∪ {V_l : g(l) = R}
    coverage    cov(R)  = A(Ṽ_R ∩ V_R) / A(V_R)
    purity      pur(R)  = A(Ṽ_R ∩ V_R) / A(Ṽ_R)
    Dice        D(R)    = 2 A(Ṽ_R ∩ V_R) / (A(Ṽ_R) + A(V_R))

Verdict for R: "resolved" when cov >= kappa and pur >= pi and no ambiguous
label has w(l, R) >= tau; "qualified" when an estimate exists but one of these
fails (the conclusion must disclose cov/pur and the ambiguous labels);
"unresolvable" when Ṽ_R is empty. Unassigned vertices (-1) and non-cortical
labels (unknown, medial wall, corpus callosum) are excluded from every area.

Complexity O(|V| + |L|·|R|). Stdlib only; never imported into Agent images.
Cross-species use (macaque CHARM ↔ human lobes) would require a registered
common mesh (e.g. Yerkes19 ↔ fs_LR); without one the resolver is not applied
and the existing nonhuman policy (report missing products) stands.
"""
from __future__ import annotations

import math
from typing import Dict, Iterable, List, Mapping, Optional, Sequence

THETA = 0.5
KAPPA = 0.8
PI = 0.8
TAU = 0.2

EXCLUDED = {
    "unknown", "???", "medial_wall", "medial_wall_", "corpuscallosum",
    "corpus_callosum", "medial wall",
}


def _cortical(name: Optional[str]) -> bool:
    return bool(name) and name.strip().casefold() not in EXCLUDED


def vertex_areas(vertices: Sequence[Sequence[float]], faces: Sequence[Sequence[int]]) -> List[float]:
    """Per-vertex area: one third of every incident triangle (FreeSurfer convention)."""
    areas = [0.0] * len(vertices)
    for i, j, k in faces:
        a, b, c = vertices[i], vertices[j], vertices[k]
        u = [b[n] - a[n] for n in range(3)]
        v = [c[n] - a[n] for n in range(3)]
        cross = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
        third = math.sqrt(math.fsum(x * x for x in cross)) / 6.0
        areas[i] += third
        areas[j] += third
        areas[k] += third
    return areas


def named(labels: Sequence[int], names: Mapping[int, str]) -> List[Optional[str]]:
    """Turn annotation indices into names; -1 / excluded labels become None."""
    out: List[Optional[str]] = []
    for index in labels:
        name = names.get(index) if index != -1 else None
        out.append(name if _cortical(name) else None)
    return out


def regions_from_mapping(reference_names: Sequence[Optional[str]],
                         records: Iterable[Mapping[str, object]], atlas: str) -> List[Optional[str]]:
    """Per-vertex reference region from sourced name sets (lobar_mapping.json records)."""
    lookup: Dict[str, str] = {}
    for row in records:
        if row.get("atlas") != atlas:
            continue
        for label in row.get("labels", []):
            if label in lookup and lookup[label] != row["region"]:
                raise ValueError(f"Label {label} mapped to two regions")
            lookup[str(label)] = str(row["region"])
    return [lookup.get(name) if name else None for name in reference_names]


def overlap_table(regions: Sequence[Optional[str]], labels: Sequence[Optional[str]],
                  weights: Optional[Sequence[float]] = None):
    """A(V_l ∩ V_R), A(V_l), A(V_R) over vertices where both sides are cortical."""
    if len(regions) != len(labels):
        raise ValueError("Reference and analysis parcellations are on different meshes")
    if weights is not None and len(weights) != len(labels):
        raise ValueError("Weights do not match the mesh")
    joint: Dict[str, Dict[str, float]] = {}
    label_area: Dict[str, float] = {}
    region_area: Dict[str, float] = {}
    for v, (region, label) in enumerate(zip(regions, labels)):
        a = 1.0 if weights is None else float(weights[v])
        if label is not None:
            label_area[label] = label_area.get(label, 0.0) + a
        if region is not None:
            region_area[region] = region_area.get(region, 0.0) + a
        if label is not None and region is not None:
            row = joint.setdefault(label, {})
            row[region] = row.get(region, 0.0) + a
    return joint, label_area, region_area


def resolve(regions: Sequence[Optional[str]], labels: Sequence[Optional[str]],
            weights: Optional[Sequence[float]] = None, theta: float = THETA,
            kappa: float = KAPPA, pi: float = PI, tau: float = TAU):
    """Induce the analysis-label set of every reference region, with diagnostics."""
    if not 0.0 < theta <= 1.0:
        raise ValueError("theta must be in (0, 1]")
    joint, label_area, region_area = overlap_table(regions, labels, weights)
    inclusion = {
        label: {region: (joint.get(label, {}).get(region, 0.0) / label_area[label])
                for region in region_area}
        for label in label_area if label_area[label] > 0
    }
    assignment: Dict[str, Optional[str]] = {}
    for label, row in sorted(inclusion.items()):
        best = max(sorted(row), key=lambda r: row[r]) if row else None
        assignment[label] = best if best is not None and row[best] >= theta else None
    report = {}
    for region in sorted(region_area):
        members = sorted(l for l, r in assignment.items() if r == region)
        est = math.fsum(label_area[l] for l in members)
        inter = math.fsum(joint.get(l, {}).get(region, 0.0) for l in members)
        ref = region_area[region]
        ambiguous = sorted(l for l, r in assignment.items()
                           if r is None and inclusion[l].get(region, 0.0) >= tau)
        cov = inter / ref if ref else 0.0
        pur = inter / est if est else 0.0
        dice = 2 * inter / (est + ref) if (est + ref) else 0.0
        if not members:
            verdict = "unresolvable"
        elif cov >= kappa and pur >= pi and not ambiguous:
            verdict = "resolved"
        else:
            verdict = "qualified"
        report[region] = {
            "labels": members,
            "weights": {l: round(inclusion[l][region], 6) for l in members},
            "coverage": cov, "purity": pur, "dice": dice,
            "ambiguous": ambiguous, "verdict": verdict,
        }
    return {
        "regions": report,
        "assignment": assignment,
        "inclusion": inclusion,
        "unassigned": sorted(l for l, r in assignment.items() if r is None),
        "parameters": {"theta": theta, "kappa": kappa, "pi": pi, "tau": tau,
                       "weighted": weights is not None},
    }


def theta_sweep(regions, labels, weights=None, thetas=(0.3, 0.4, 0.5, 0.6, 0.7, 0.8), reference=None):
    """Sensitivity of the induced mapping to theta (optionally scored against a reference)."""
    rows = []
    for theta in thetas:
        result = resolve(regions, labels, weights, theta=theta)
        row = {
            "theta": theta,
            "unassigned": len(result["unassigned"]),
            "mean_dice": _mean(r["dice"] for r in result["regions"].values()),
            "resolved": sum(r["verdict"] == "resolved" for r in result["regions"].values()),
        }
        if reference is not None:
            row.update(evaluate(result["assignment"], reference))
        rows.append(row)
    return rows


# ---------------------------------------------------------------- baselines
KEYWORDS = {
    "frontal": ("front", "orbit", "precentral", "paracentral", "pars", "rectus"),
    "temporal": ("tempor", "fusiform", "parahippocamp", "entorhinal", "bankssts", "transverse"),
    "parietal": ("pariet", "postcentral", "supramarginal", "precuneus", "angular"),
    "occipital": ("occipit", "cuneus", "lingual", "calcarine", "pericalcarine"),
    "cingulate": ("cingul",),
    "insula": ("insula", "insular"),
}


def name_baseline(names: Iterable[str], records: Iterable[Mapping[str, object]], atlas: str):
    """Exact sourced name sets: only works when the analysis atlas is the one the sets were written for."""
    lookup = {}
    for row in records:
        if row.get("atlas") == atlas:
            for label in row.get("labels", []):
                lookup[str(label)] = str(row["region"])
    return {name: lookup.get(name) for name in names if _cortical(name)}


def keyword_baseline(names: Iterable[str], keywords: Mapping[str, Sequence[str]] = KEYWORDS):
    """Substring heuristic; a label matching zero or several regions stays unassigned."""
    out = {}
    for name in names:
        if not _cortical(name):
            continue
        low = name.casefold()
        hits = sorted({region for region, keys in keywords.items() if any(k in low for k in keys)})
        out[name] = hits[0] if len(hits) == 1 else None
    return out


# ---------------------------------------------------------------- evaluation
def evaluate(predicted: Mapping[str, Optional[str]], reference: Mapping[str, Optional[str]]):
    """Label-level agreement with a reference mapping (None counts as its own class)."""
    keys = sorted(set(reference))
    if not keys:
        raise ValueError("Empty reference mapping")
    correct = sum(predicted.get(k) == reference[k] for k in keys)
    covered = [k for k in keys if predicted.get(k) is not None]
    precise = sum(predicted[k] == reference[k] for k in covered)
    return {
        "n_labels": len(keys),
        "accuracy": correct / len(keys),
        "assigned": len(covered),
        "precision_assigned": precise / len(covered) if covered else 0.0,
        "errors": [{"label": k, "predicted": predicted.get(k), "reference": reference[k]}
                   for k in keys if predicted.get(k) != reference[k]],
    }


def geometric_score(mapping: Mapping[str, Optional[str]], regions, labels, weights=None):
    """Dice/coverage/purity of any label→region mapping (e.g. a baseline) on the mesh."""
    joint, label_area, region_area = overlap_table(regions, labels, weights)
    out = {}
    for region in sorted(region_area):
        members = [l for l, r in mapping.items() if r == region and l in label_area]
        est = math.fsum(label_area[l] for l in members)
        inter = math.fsum(joint.get(l, {}).get(region, 0.0) for l in members)
        ref = region_area[region]
        out[region] = {
            "coverage": inter / ref if ref else 0.0,
            "purity": inter / est if est else 0.0,
            "dice": 2 * inter / (est + ref) if (est + ref) else 0.0,
        }
    return out


def agreement(first: Mapping[str, Optional[str]], second: Mapping[str, Optional[str]]):
    """Fraction of shared labels mapped identically (fsaverage vs per-subject stability)."""
    keys = sorted(set(first) & set(second))
    return sum(first[k] == second[k] for k in keys) / len(keys) if keys else float("nan")


# ---------------------------------------------------------------- agent hook
def resolve_request(region: str, regions, labels, weights=None, theta: float = THETA,
                    provenance: Optional[Mapping[str, object]] = None):
    """Expand one requested reference region into analysis labels plus evidence."""
    result = resolve(regions, labels, weights, theta=theta)
    row = result["regions"].get(region)
    if row is None or row["verdict"] == "unresolvable":
        return [], None, f"Region {region} cannot be resolved on the analysis parcellation"
    evidence = {
        "kind": "region_overlap",
        "region": region,
        "labels": row["labels"],
        "coverage": round(row["coverage"], 6),
        "purity": round(row["purity"], 6),
        "dice": round(row["dice"], 6),
        "ambiguous": row["ambiguous"],
        "verdict": row["verdict"],
        "parameters": result["parameters"],
        "provenance": dict(provenance or {}),
    }
    return row["labels"], evidence, None


def _mean(values):
    values = list(values)
    return math.fsum(values) / len(values) if values else float("nan")
