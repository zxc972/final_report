from pathlib import Path
import csv
import hashlib
import json
import math
import sys
import numpy as np
from nibabel.freesurfer.io import read_annot, read_geometry, read_label, read_morph_data
from scipy.spatial import ConvexHull

import argparse

parser = argparse.ArgumentParser(
    description="Independent read-only input comparison; no primatex_ops or product reference import"
)
parser.add_argument("case")
parser.add_argument("--batch", type=Path, required=True)
parser.add_argument("--audit-output", type=Path, required=True)
args = parser.parse_args()
BATCH = args.batch
case = args.case
folder = BATCH / ("case_" + case)
response = json.loads((folder / "agent_response.json").read_text())
request = json.loads((folder / "request.public.json").read_text())
metadata = response["metadata"]
plan_sha = metadata["conclusion_card"]["plan_sha256"]
matches = []
for path in (BATCH / "state").rglob("plan.v*.json"):
    document = json.loads(path.read_text())
    if document.get("sha256") == plan_sha:
        matches.append((path, document))
assert len(matches) == 1
plan_path, plan_record = matches[0]
plan = plan_record["record"]["plan"]
bundle_path = sorted(plan_path.parent.glob("execution_bundle.v*.json"))[-1]
bundle = json.loads(bundle_path.read_text())["record"]
assert bundle["plan_sha256"] == plan_sha
workspace = Path(request["context"]["workspaceDirectory"])
work = (workspace / metadata["output_directory"]).resolve()
assert work.is_relative_to(workspace / ".analysis_runs")
inputs = [Path(path).resolve() for path in request["inputRoots"]]


def resolve(mapped):
    assert ".." not in Path(mapped).parts
    if mapped.startswith("/inputs/"):
        parts = mapped.split("/")
        root = inputs[int(parts[2])]
        target = root.joinpath(*parts[3:]).resolve()
        assert target.is_relative_to(root)
        return target
    raise ValueError("Only sealed inputs are supported")


csv_files = [
    name for name in bundle["output_contract"]["files"] if name.endswith(".csv")
]
assert len(csv_files) == 1
csv_path = work / csv_files[0]
with csv_path.open(newline="") as stream:
    observed = list(csv.DictReader(stream))
method = plan["method"]["method_id"].rsplit(":", 1)[-1]
expected = []
if method == "surface_annotation_roi":
    keys = ["subject", "hemisphere", "metric", "label_key"]
    columns = ["vertex_count", "mean", "std_population", "median", "zero_count"]
    for scope, group in bundle["label_sets"].items():
        subject, hemi = scope.rsplit("/", 1)
        annotation = resolve(group["annotation"])
        labels, table, names = read_annot(annotation, orig_ids=False)
        cortex = np.asarray(read_label(resolve(group["cortex_label"])), dtype=np.int64)
        assert len(np.unique(cortex)) == len(cortex)
        metric_paths = [
            row["inputs"]["metric_path"]
            for row in bundle["operations"]["calls"]
            if row["function"] == "parcel_summary" and row["scope"] == scope
        ]
        for mapped in metric_paths:
            values = read_morph_data(resolve(mapped)).astype(np.float64)
            assert len(values) == len(labels) and np.isfinite(values).all()
            for selected in group["labels"]:
                label_key = selected["key"]
                assert names[label_key].decode() == selected["name"]
                data = values[cortex[labels[cortex] == label_key]]
                assert data.size > 0
                expected.append(
                    {
                        "subject": subject,
                        "hemisphere": hemi,
                        "metric": mapped.rsplit(".", 1)[-1],
                        "label_key": str(label_key),
                        "name": selected["name"],
                        "vertex_count": int(data.size),
                        "mean": float(np.mean(data, dtype=np.float64)),
                        "std_population": float(np.std(data, ddof=0, dtype=np.float64)),
                        "median": float(np.median(data)),
                        "zero_count": int(np.count_nonzero(data == 0)),
                    }
                )
elif method == "global_convex_hull_gyrification":
    keys = ["subject", "hemisphere"]
    columns = ["surface_area", "hull_area", "area_ratio"]
    for mapped in plan["data"]["files"]:
        if not mapped.endswith(".pial"):
            continue
        hemi = Path(mapped).name[:2]
        index = int(mapped.split("/")[2])
        subject = plan["data"]["subjects"][index]
        vertices, faces = read_geometry(resolve(mapped))
        vertices = vertices.astype(np.float64)
        triangles = vertices[faces]
        areas = (
            np.linalg.norm(
                np.cross(
                    triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]
                ),
                axis=1,
            )
            / 2
        )
        surface_area = float(np.sum(areas, dtype=np.float64))
        hull_area = float(ConvexHull(vertices).area)
        expected.append(
            {
                "subject": subject,
                "hemisphere": hemi,
                "surface_area": surface_area,
                "hull_area": hull_area,
                "area_ratio": surface_area / hull_area,
            }
        )
elif method == "global_morphometry":
    import nibabel as nib

    keys = ["subject", "species"]
    metrics = [
        "brain_volume_mm3",
        "etiv_mm3",
        "total_area_mm2",
        "mean_thickness_mm",
        "hull_ratio",
    ]
    columns = (
        metrics + ["stored_" + name for name in metrics] + ["scale_k", "scale_status"]
    )
    scope = plan["analysis_scope"]
    binding, scale = scope["global_bindings"], scope["global_scale"]

    def measures(path):
        output = {}
        if path:
            for line in resolve(path).read_text().splitlines():
                if line.startswith("# Measure "):
                    fields = [
                        item.strip() for item in line[len("# Measure ") :].split(",")
                    ]
                    if len(fields) >= 5:
                        output[fields[1]] = float(fields[3])
        return output

    aseg = measures(binding.get("aseg_stats"))
    volume = aseg.get("BrainSegVol")
    if volume is None and binding.get("mask_volume"):
        image = nib.load(resolve(binding["mask_volume"]))
        data = np.asanyarray(image.dataobj)
        assert np.isfinite(data).all()
        volume = int(np.count_nonzero(data > 0)) * float(
            np.prod(image.header.get_zooms()[:3])
        )
    hemi_stats = {hemi: measures(path) for hemi, path in binding["hemi_stats"].items()}
    areas = [hemi_stats[hemi].get("WhiteSurfArea") for hemi in ("lh", "rh")]
    thickness = [hemi_stats[hemi].get("MeanThickness") for hemi in ("lh", "rh")]
    area = sum(areas) if all(value is not None for value in areas) else None
    mean = (
        sum(a * t for a, t in zip(areas, thickness)) / area
        if area and all(t is not None for t in thickness)
        else None
    )
    surface_areas, hull_areas = [], []
    for hemi, path in sorted(binding.get("pial", {}).items()):
        vertices, faces = read_geometry(resolve(path))
        triangles = vertices.astype(np.float64)[faces]
        surface_areas.append(
            float(
                np.linalg.norm(
                    np.cross(
                        triangles[:, 1] - triangles[:, 0],
                        triangles[:, 2] - triangles[:, 0],
                    ),
                    axis=1,
                ).sum(dtype=np.float64)
                / 2
            )
        )
        hull_areas.append(float(ConvexHull(vertices.astype(np.float64)).area))
    ratio = sum(surface_areas) / sum(hull_areas) if len(hull_areas) == 2 else None
    stored = dict(zip(metrics, [volume, aseg.get("eTIV"), area, mean, ratio]))
    row = {
        "subject": plan["data"]["subjects"][0],
        "species": plan["data"]["species_declared"],
        "scale_status": scale["status"],
        "scale_k": scale.get("k") if scale["host_verified"] else None,
    }
    for evidence in scale.get("sources", []):
        assert (
            hashlib.sha256(Path(evidence["path"]).read_bytes()).hexdigest()
            == evidence["sha256"]
        )
    for name, power in zip(metrics, [3, 3, 2, 1, 0]):
        row["stored_" + name] = stored[name]
        row[name] = (
            stored[name] / (scale["k"] ** power)
            if stored[name] is not None and scale["host_verified"]
            else None
        )
    expected.append(row)
else:
    raise SystemExit(
        "External comparison not registered for this method; native comparison retained"
    )

if plan.get("analysis_scope", {}).get("comparison") == "asymmetry":
    pairs = {}
    for row in expected:
        pair_key = (row["subject"], row["metric"], row["name"])
        pairs.setdefault(pair_key, {})[row["hemisphere"]] = row["mean"]
    for row in expected:
        pair = pairs[(row["subject"], row["metric"], row["name"])]
        assert set(pair) == {"lh", "rh"}
        denominator = pair["lh"] + pair["rh"]
        assert denominator != 0
        row["asymmetry_index"] = 2 * (pair["lh"] - pair["rh"]) / denominator
    columns.append("asymmetry_index")


def identity(row):
    return tuple(str(row[key]) for key in keys)


left = {identity(row): row for row in expected}
right = {identity(row): row for row in observed}
assert len(right) == len(observed), "Duplicate output identities"
identity_differences = sorted(set(left).symmetric_difference(right))
numeric_differences = []
checked = 0
for key in sorted(set(left).intersection(right)):
    for column in columns:
        checked += 1
        observed_value, reference = right[key][column], left[key][column]
        if reference is None:
            valid = observed_value == ""
            actual = observed_value or None
        elif column == "scale_status":
            actual = observed_value
            valid = actual == reference
        else:
            actual = float(observed_value) if observed_value else None
            valid = (
                actual is not None
                and math.isfinite(actual)
                and math.isclose(actual, reference, abs_tol=1e-9, rel_tol=1e-7)
            )
        if not valid:
            numeric_differences.append(
                {
                    "identity": key,
                    "column": column,
                    "actual": actual,
                    "reference": reference,
                }
            )
artifacts = []
for item in metadata["artifacts"]:
    target = (work / item["path"]).resolve()
    assert target.is_relative_to(work)
    artifacts.append(
        {
            "path": item["path"],
            "sha256_match": hashlib.sha256(target.read_bytes()).hexdigest()
            == item["sha256"],
        }
    )
result = {
    "case": case,
    "method": method,
    "reference": "NiBabel/NumPy/SciPy; no primatex_ops or product stdlib reference imported",
    "versions": {"numpy": np.__version__},
    "reference_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    "plan_sha256": plan_sha,
    "execution_receipt_id": metadata.get("execution", {}).get("receipt_id"),
    "rows_expected": len(expected),
    "rows_observed": len(observed),
    "numeric_checked": checked,
    "identity_mismatch_count": len(identity_differences),
    "numeric_mismatch_count": len(numeric_differences),
    "artifact_hashes": artifacts,
    "status": (
        "pass"
        if not identity_differences
        and not numeric_differences
        and all(r["sha256_match"] for r in artifacts)
        else "fail"
    ),
    "reference_scope": "Arithmetic and mesh area consistency only; no independent anatomical QC",
}
audit_folder = args.audit_output / case
if audit_folder.exists():
    raise ValueError(
        "New audit directory required; do not overwrite historical evidence"
    )
audit_folder.mkdir(parents=True)
(audit_folder / "external_reference_private.json").write_text(
    json.dumps(
        {
            "expected": expected,
            "differences": numeric_differences,
            "identity_differences": identity_differences,
        },
        indent=2,
    )
    + "\n"
)
(audit_folder / "external_verification.json").write_text(
    json.dumps(result, indent=2) + "\n"
)
print(json.dumps(result))
