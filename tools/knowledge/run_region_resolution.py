#!/usr/bin/env python3
"""Algorithm 2 experiment: atlas-to-lobe resolution by vertex overlap.

For every subject/hemisphere with the needed files it runs three conditions:

  C1  reference DK lobes (--lobesStrict sets)  -> analysis DKT
      exact reference: official DKT lobe sets
  C2  reference DKT lobes                       -> analysis DK
      exact reference: official DK lobe sets
  C3  reference DK lobes                        -> analysis Destrieux (a2009s)
      no official set; scored geometrically (Dice / coverage / purity)

Compared methods: overlap resolver (area-weighted and unweighted), the exact
name-set baseline and the keyword baseline. A theta sweep is reported per
condition. Output: one JSON with everything plus a flat CSV summary.

Usage:
  python tools/knowledge/run_region_resolution.py \
      --subjects-dir $FREESURFER_HOME/subjects --subject fsaverage \
      --subject fsaverage6 --subject fsaverage5 --out evaluation/region_resolution
Reads only; never writes into the subjects directory.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "agent" / "modules" / "agent" / "backend"
MAPPING = ROOT / "agent" / "modules" / "agent" / "knowledge_analysis" / "lobar_mapping.json"

DK = ("aparc",)
DKT = ("aparc.DKTatlas", "aparc.DKTatlas40", "aparc.DKTatlas.mapped")
DESTRIEUX = ("aparc.a2009s",)
THETAS = (0.3, 0.4, 0.5, 0.6, 0.7, 0.8)


def load(name):
    spec = importlib.util.spec_from_file_location(name, BACKEND / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


rr = load("analysis_region_resolver")
nr = load("analysis_numeric_reference")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def find_annot(label_dir: Path, hemi: str, stems):
    for stem in stems:
        path = label_dir / f"{hemi}.{stem}.annot"
        if path.exists():
            return path
    return None


def reference_sets(records, atlas):
    out = {}
    for row in records:
        if row["atlas"] == atlas:
            for label in row["labels"]:
                out[label] = row["region"]
    return out


def run_condition(name, ref_names, ref_atlas, ana_names, records, areas, exact_atlas, provenance):
    regions = rr.regions_from_mapping(ref_names, records, ref_atlas)
    present = sorted({n for n in ana_names if n})
    exact = None
    if exact_atlas:
        sets = reference_sets(records, exact_atlas)
        # labels outside every official lobe set (none expected) count as "no lobe"
        exact = {label: sets.get(label) for label in present}
    methods = {
        "overlap_weighted": rr.resolve(regions, ana_names, areas)["assignment"],
        "overlap_unweighted": rr.resolve(regions, ana_names, None)["assignment"],
        "name_exact": rr.name_baseline(present, records, ref_atlas),
        "keyword": rr.keyword_baseline(present),
    }
    detail = rr.resolve(regions, ana_names, areas)
    result = {"condition": name, "provenance": provenance, "n_labels": len(present),
              "regions": detail["regions"], "inclusion": detail["inclusion"], "methods": {}}
    for method, mapping in methods.items():
        entry = {"mapping": mapping,
                 "geometry": rr.geometric_score(mapping, regions, ana_names, areas)}
        if exact is not None:
            entry["exact"] = rr.evaluate(mapping, exact)
        result["methods"][method] = entry
    result["theta_sweep"] = rr.theta_sweep(regions, ana_names, areas, THETAS, reference=exact)
    for row in result["theta_sweep"]:
        row.pop("errors", None)
    return result


def summary_rows(result):
    for method, entry in result["methods"].items():
        geo = entry["geometry"]
        dices = [g["dice"] for g in geo.values()]
        row = {
            "subject": result["provenance"]["subject"], "hemi": result["provenance"]["hemi"],
            "condition": result["condition"], "method": method, "n_labels": result["n_labels"],
            "assigned": sum(v is not None for v in entry["mapping"].values()),
            "mean_dice": sum(dices) / len(dices) if dices else "",
            "min_dice": min(dices) if dices else "",
        }
        if "exact" in entry:
            row["accuracy"] = entry["exact"]["accuracy"]
            row["precision_assigned"] = entry["exact"]["precision_assigned"]
            row["n_errors"] = len(entry["exact"]["errors"])
        yield row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--subjects-dir", required=True, type=Path)
    ap.add_argument("--subject", action="append", required=True)
    ap.add_argument("--hemi", action="append", default=None)
    ap.add_argument("--surface", default="white")
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()
    hemis = args.hemi or ["lh", "rh"]
    records = json.loads(MAPPING.read_text(encoding="utf-8"))["records"]
    args.out.mkdir(parents=True, exist_ok=True)
    results, skipped, rows = [], [], []
    for subject in args.subject:
        base = args.subjects_dir / subject
        for hemi in hemis:
            surf = base / "surf" / f"{hemi}.{args.surface}"
            files = {"DK": find_annot(base / "label", hemi, DK),
                     "DKT": find_annot(base / "label", hemi, DKT),
                     "Destrieux": find_annot(base / "label", hemi, DESTRIEUX)}
            if not surf.exists() or files["DK"] is None:
                skipped.append({"subject": subject, "hemi": hemi, "reason": "surface or DK annotation missing"})
                continue
            vertices, faces = nr.read_surface(surf)
            areas = rr.vertex_areas(vertices, faces)
            names = {}
            for key, path in files.items():
                if path is None:
                    continue
                labels, table = nr.read_annotation(path)
                if len(labels) != len(vertices):
                    raise SystemExit(f"{path} does not match {surf}")
                names[key] = rr.named(labels, table)
            prov = {"subject": subject, "hemi": hemi, "surface": str(surf.name),
                    "surface_sha256": sha256(surf),
                    "annotations": {k: {"file": p.name, "sha256": sha256(p)}
                                    for k, p in files.items() if p is not None},
                    "mapping_sha256": sha256(MAPPING)}
            if "DKT" in names:
                results.append(run_condition("C1_DK_to_DKT", names["DK"], "DK", names["DKT"],
                                             records, areas, "DKT", prov))
                results.append(run_condition("C2_DKT_to_DK", names["DKT"], "DKT", names["DK"],
                                             records, areas, "DK", prov))
            else:
                skipped.append({"subject": subject, "hemi": hemi, "reason": "DKT annotation missing"})
            if "Destrieux" in names:
                results.append(run_condition("C3_DK_to_Destrieux", names["DK"], "DK",
                                             names["Destrieux"], records, areas, None, prov))
            else:
                skipped.append({"subject": subject, "hemi": hemi, "reason": "Destrieux annotation missing"})
    # stability: the weighted overlap mapping of each subject vs the first subject (same condition/hemi)
    stability = []
    anchor = {}
    for res in results:
        key = (res["condition"], res["provenance"]["hemi"])
        mapping = res["methods"]["overlap_weighted"]["mapping"]
        if key not in anchor:
            anchor[key] = (res["provenance"]["subject"], mapping)
            continue
        stability.append({"condition": key[0], "hemi": key[1], "anchor": anchor[key][0],
                          "subject": res["provenance"]["subject"],
                          "agreement": rr.agreement(anchor[key][1], mapping)})
    for res in results:
        rows.extend(summary_rows(res))
    (args.out / "region_resolution_results.json").write_text(
        json.dumps({"results": results, "skipped": skipped, "stability": stability,
                    "parameters": {"theta": rr.THETA, "kappa": rr.KAPPA, "pi": rr.PI, "tau": rr.TAU,
                                   "thetas": THETAS}},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    fields = ["subject", "hemi", "condition", "method", "n_labels", "assigned", "mean_dice",
              "min_dice", "accuracy", "precision_assigned", "n_errors"]
    with (args.out / "region_resolution_summary.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({"conditions": len(results), "skipped": skipped, "stability": stability}, indent=1))


if __name__ == "__main__":
    main()
