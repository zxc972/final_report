"""Accept explicitly selected macaque global products without editing derivatives.

This is a deterministic host audit, not an Agent or model request. A separate
release policy decides whether a conditional result may unlock another subject.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import itertools
import json
from pathlib import Path
import subprocess
import sys

import nibabel as nib
import numpy as np


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def save(path, body):
    raw = json.dumps(body, ensure_ascii=False, indent=2, allow_nan=False)
    path.write_text(raw + "\n", encoding="utf-8")


def area(vertices, faces):
    triangle = vertices[faces]
    cross = np.cross(triangle[:, 1] - triangle[:, 0], triangle[:, 2] - triangle[:, 0])
    return float(np.linalg.norm(cross, axis=1).sum(dtype=np.float64) / 2)


def stats_white_area(path):
    for number, line in enumerate(path.read_text().splitlines(), 1):
        if line.startswith("# Measure ") and ", WhiteSurfArea," in line:
            fields = [part.strip() for part in line[10:].split(",")]
            raw = fields[3]
            decimals = len(raw.partition(".")[2])
            tolerance = 0.5 * 10 ** (-decimals) + 1e-8
            return {
                "value": float(raw),
                "unit": fields[4],
                "line": number,
                "path": str(path),
                "display_rounding_tolerance_mm2": tolerance,
            }
    return None


def inspect(subject, outer, manifest, pilot_audit, output, reference_worker):
    if output.exists():
        raise ValueError("Refuse to overwrite an existing acceptance record")
    if not output.resolve().is_relative_to(manifest.resolve().parent / "provenance"):
        raise ValueError("Acceptance output must be in the dataset provenance tree")
    if output.resolve().is_relative_to(outer.resolve()):
        raise ValueError("Acceptance must be separate from original derivative output")
    selected = [
        r for r in json.loads(manifest.read_text()) if r["subject_id"] == subject
    ]
    if len(selected) != 1 or selected[0]["held_out"] not in (False, "否", "no"):
        raise ValueError("Subject must be explicitly registered and non-held-out")
    output.mkdir(parents=True)
    person = selected[0]
    if person["species"] != "Macaca mulatta":
        raise ValueError(
            "This batch only authorizes individually declared rhesus subjects"
        )
    native, backup = outer / subject, outer / (subject + "_1mm")
    if output.resolve().is_relative_to(outer.resolve()):
        raise ValueError("Acceptance must be separate from original derivative output")
    state = json.loads((pilot_audit / "pilot_status.json").read_text())
    plan = json.loads((pilot_audit / "pilot_plan.json").read_text())
    execution_ok = len(state["steps"]) == 8 and all(
        s.get("returncode") == 0 and not s.get("missing_products")
        for s in state["steps"]
    )
    raw_unchanged = sha256(Path(person["t1_file"])) == person["raw_sha256"]
    mask_path = native / "mri/brainmask.mgz"
    image = nib.load(mask_path)
    data = np.asanyarray(image.dataobj)
    if not np.isfinite(data).all() or np.any(data < 0):
        raise ValueError("Nonfinite or negative mask support cannot be certified")
    support = np.array(np.where(data > 0))
    if not support.size:
        raise ValueError("Empty brainmask support")
    lower, upper = support.min(axis=1), support.max(axis=1)
    corners = np.array(list(itertools.product(*zip(lower - 0.5, upper + 0.5))))
    tkr = image.header.get_vox2ras_tkr()
    transformed = nib.affines.apply_affine(tkr, corners)
    mask_size = transformed.max(axis=0) - transformed.min(axis=0)
    centre_corners = np.array(list(itertools.product(*zip(lower, upper))))
    centre_points = nib.affines.apply_affine(tkr, centre_corners)
    centre_size = centre_points.max(axis=0) - centre_points.min(axis=0)
    zooms = np.array(image.header.get_zooms()[:3], dtype=float)
    pre_image = nib.load(outer / "T1.nii.gz")
    pre_zooms = np.array(pre_image.header.get_zooms()[:3], dtype=float)
    fake_image = nib.load(backup / "mri/brainmask.mgz")
    fake_zooms = np.array(fake_image.header.get_zooms()[:3], dtype=float)
    volume_observation = {
        "selected_file": str(mask_path),
        "selected_affine": image.affine.tolist(),
        "vox2ras_tkr": tkr.tolist(),
        "voxel_size_mm": zooms.tolist(),
        "voxel_volume_mm3": float(abs(np.linalg.det(image.affine[:3, :3]))),
        "positive_voxel_count": int(support.shape[1]),
        "support_extent_tkr_mm": mask_size.tolist(),
        "voxel_centre_bbox_extent_tkr_mm": centre_size.tolist(),
        "bbox_uses_voxel_edges": True,
        "pre_fake_T1_voxel_size_mm": pre_zooms.tolist(),
        "fake_mgz_voxel_size_mm": fake_zooms.tolist(),
        "nifti_used_for_volume": False,
    }
    bbox, surfaces, medians, areas, fingerprints = [], [], [], [], []
    restore_factors = []
    restored_exact = True
    for kind in ["white", "pial", "smoothwm"]:
        combined = []
        for hemi in ["lh", "rh"]:
            path = native / "surf" / (hemi + "." + kind)
            a, faces = nib.freesurfer.read_geometry(path)
            b, old_faces = nib.freesurfer.read_geometry(backup / "surf" / path.name)
            factor = float(np.sum(a * b) / np.sum(b * b))
            error = float(np.max(np.abs(a - factor * b)))
            valid = (
                len(a) == len(b) and np.array_equal(faces, old_faces) and error <= 1e-5
            )
            restored_exact = restored_exact and valid
            restore_factors.append(factor)
            combined.append(a)
            surface = {
                "hemisphere": hemi,
                "kind": kind,
                "path": str(path),
                "vertices": len(a),
                "faces": len(faces),
                "native_over_fake1mm_linear_factor": factor,
                "max_coordinate_residual": error,
                "same_faces": bool(np.array_equal(faces, old_faces)),
            }
            surfaces.append(surface)
            fingerprints.append({"path": str(path), "sha256": sha256(path)})
            if kind == "white":
                computed = area(a, faces)
                stats = stats_white_area(native / "stats" / (hemi + ".aparc.stats"))
                matches = bool(
                    stats
                    and abs(computed - stats["value"])
                    <= stats["display_rounding_tolerance_mm2"]
                )
                areas.append(
                    {
                        "hemisphere": hemi,
                        "direct_white_area_mm2": computed,
                        "stats_WhiteSurfArea": stats,
                        "stats_matches_final_native": matches,
                        "stats_over_final_ratio": (
                            stats["value"] / computed if stats else None
                        ),
                        "independent_fake1mm_area": area(b, old_faces),
                        "interpretation": "post_restore" if matches else "not_verified",
                    }
                )
        if kind in ["white", "pial"]:
            vertices = np.concatenate(combined)
            size = vertices.max(axis=0) - vertices.min(axis=0)
            difference = size - mask_size
            bbox.append(
                {
                    "surface": kind,
                    "extent_tkr_mm": size.tolist(),
                    "surface_over_mask_extent": (size / mask_size).tolist(),
                    "difference_mm": difference.tolist(),
                    "centre_span_difference_mm": (size - centre_size).tolist(),
                    "centre_span_two_voxel_pass": bool(
                        np.all(np.abs(size - centre_size) <= 2 * min(zooms))
                    ),
                    "difference_in_0_5mm_voxels": (difference / 0.5).tolist(),
                    "literal_two_voxel_pass": bool(
                        np.all(np.abs(difference) <= 2 * min(zooms))
                    ),
                    "note": "white is an inner white/gray boundary; mask and pial are different outer tissue supports. This note does not relabel a failed literal threshold as pass.",
                }
            )
    for hemi in ["lh", "rh"]:
        path = native / "surf" / (hemi + ".thickness")
        metric = nib.freesurfer.read_morph_data(path)
        cortex_path = native / "label" / (hemi + ".cortex.label")
        cortex = nib.freesurfer.read_label(cortex_path)
        finite = bool(np.isfinite(metric).all())
        medians.append(
            {
                "hemisphere": hemi,
                "all_vertex_median_mm": float(np.median(metric)),
                "cortex_median_mm": float(np.median(metric[cortex])),
                "finite": finite,
                "cortex_zero_count": int(np.count_nonzero(metric[cortex] == 0)),
                "median_in_user_expected_1_5_to_2_5_mm": bool(
                    1.5 <= np.median(metric[cortex]) <= 2.5
                ),
            }
        )
        fingerprints += [
            {"path": str(f), "sha256": sha256(f)} for f in [path, cortex_path]
        ]
    fingerprints.append({"path": str(mask_path), "sha256": sha256(mask_path)})
    final_scale = float(np.median(restore_factors) * np.median(fake_zooms / pre_zooms))
    verified = bool(
        execution_ok
        and raw_unchanged
        and restored_exact
        and np.allclose(restore_factors, np.median(restore_factors), atol=1e-6, rtol=0)
        and np.allclose(zooms, pre_zooms, atol=1e-6, rtol=0)
        and all(a["stats_matches_final_native"] for a in areas)
        and all(
            m["finite"] and m["median_in_user_expected_1_5_to_2_5_mm"] for m in medians
        )
        and abs(final_scale - 1.0) <= 1e-6
    )
    pial_bbox_ok = next(
        b["literal_two_voxel_pass"] for b in bbox if b["surface"] == "pial"
    )
    scale = {
        "subject": subject,
        "final_surface_scale_k": final_scale,
        "producer_tool_sha256": sha256(Path(__file__)),
        "pipeline_source_commit": plan.get("source_commit"),
        "pipeline_runner_sha256": plan.get("script_sha256"),
        "basis": {
            "pipeline_execution": execution_ok,
            "raw_unchanged": raw_unchanged,
            "volumes": volume_observation,
            "surface_restore": surfaces,
            "bbox_comparison": bbox,
            "thickness_medians": medians,
            "area_stats_comparison": areas,
        },
        "verified": verified,
        "status": "rescale_applied_and_reverted" if verified else "unverified",
        "verified_scope": "Remaining processing scale relative to native MRI nominal mm; independent scanner calibration not asserted",
        "all_requested_bbox_thresholds_pass": all(
            b["literal_two_voxel_pass"] for b in bbox
        ),
        "pial_two_voxel_pass": pial_bbox_ok,
        "input_fingerprints": fingerprints,
        "voxel_coordinate_frame": "Native MGH affine and its vox2ras_tkr; NIfTI sform not used",
    }
    save(output / "scale.json", scale)
    request = {
        "species": person["species"],
        "mask_volume": str(mask_path),
        "white": {h: str(native / "surf" / (h + ".white")) for h in ["lh", "rh"]},
        "pial": {h: str(native / "surf" / (h + ".pial")) for h in ["lh", "rh"]},
        "thickness": {
            h: str(native / "surf" / (h + ".thickness")) for h in ["lh", "rh"]
        },
        "cortex_labels": {
            h: str(native / "label" / (h + ".cortex.label")) for h in ["lh", "rh"]
        },
        "rescaled": True if verified else None,
        "scale_k": final_scale if verified else None,
        "scale_state": "rescale_applied_and_reverted" if verified else None,
    }
    save(output / "reference_request.json", request)
    command = [sys.executable, "-I", "-B", str(reference_worker)]
    run = subprocess.run(
        command, input=json.dumps(request), capture_output=True, text=True, timeout=240
    )
    (output / "reference.stdout.json").write_text(run.stdout)
    (output / "reference.stderr.log").write_text(run.stderr)
    save(
        output / "reference_execution.json",
        {
            "argv": command,
            "returncode": run.returncode,
            "worker_sha256": sha256(reference_worker),
            "reference_sha256": sha256(
                reference_worker.with_name("analysis_global_reference.py")
            ),
            "ended_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "model_api_requests": 0,
        },
    )
    if run.returncode:
        raise RuntimeError(
            "Independent global reference failed; inspect retained stderr"
        )
    values = json.loads(run.stdout)
    nifti = []
    for path in sorted((native / "mri").glob("*.nii.gz")):
        image_n = nib.load(path)
        q, qc = image_n.get_qform(coded=True)
        s, sc = image_n.get_sform(coded=True)
        nifti.append(
            {
                "path": str(path),
                "pixdim_mm": list(map(float, image_n.header.get_zooms()[:3])),
                "qform_code": int(qc),
                "sform_code": int(sc),
                "qform_voxel_sizes_mm": (
                    np.linalg.norm(q[:3, :3], axis=0).tolist() if qc else None
                ),
                "sform_voxel_sizes_mm": (
                    np.linalg.norm(s[:3, :3], axis=0).tolist() if sc else None
                ),
                "max_qform_sform_difference": (
                    float(np.max(np.abs(q - s))) if qc and sc else None
                ),
                "selected_for_analysis": False,
            }
        )
    save(output / "nifti_geometry_observation.json", nifti)
    coarse = {
        "mean_thickness_mm": {
            "reference": 2.1,
            "observed": values["stored"]["mean_thickness_mm"],
        },
        "area_per_hemisphere_mm2": {
            "reference": 10100.0,
            "observed": values["stored"]["total_area_mm2"] / 2,
        },
        "brain_volume_cm3": {
            "reference": 100.0,
            "observed": values["stored"]["brain_volume_mm3"] / 1000,
        },
        "hull_ratio": {
            "reference_range": [1.75, 1.9],
            "observed": values["stored"]["hull_ratio"],
        },
        "source_status": "User-supplied coarse comparisons attributed to Autio2020; not a gold standard or proof all estimates use the same definition. Thickness/area/volume conventions and hull definitions require source matching.",
    }
    warnings = []
    if not all(b["literal_two_voxel_pass"] for b in bbox):
        warnings.append(
            "Requested two-voxel bounding-box equality is not met in all dimensions; actual differences retained; white and mask are different tissue boundaries."
        )
    if any(
        n["max_qform_sform_difference"] and n["max_qform_sform_difference"] > 1e-5
        for n in nifti
    ):
        warnings.append(
            "Conflicting NIfTI geometry excluded; final MGZ affine used without modifying originals."
        )
    warnings.append(
        "Global metrics only; human-named compatibility labels not used as macaque parcellation. Anatomical expert QC not completed."
    )
    all_boxes = all(b["literal_two_voxel_pass"] for b in bbox)
    outcome = (
        "pass" if verified and all_boxes else "conditional_pass" if verified else "fail"
    )
    acceptance = {
        "subject": subject,
        "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "status": outcome,
        "scale_verified": verified,
        "metrics": values,
        "coarse_reference_comparison": coarse,
        "warnings": warnings,
        "literal_three_check_full_pass": all(b["literal_two_voxel_pass"] for b in bbox)
        and verified,
        "automatic_release_default": outcome == "pass",
        "release_note": "Conditional acceptance must not silently become a full two-voxel pass; release of subsequent subjects follows the separately recorded user gate policy.",
        "scale_record_sha256": sha256(output / "scale.json"),
        "annotation_policy": "人类命名标签，不作猕猴分区",
        "macaque_etiv_or_aseg_used": False,
        "model_api_requests": 0,
        "raw_or_derivative_outputs_modified": False,
    }
    save(output / "acceptance.json", acceptance)
    print(
        json.dumps(
            {
                "subject": subject,
                "status": outcome,
                "scale_k": final_scale,
                "verified": verified,
                "pial_bbox_two_voxel_pass": pial_bbox_ok,
                "metrics": values["physical"],
            },
            ensure_ascii=False,
        )
    )
    return acceptance


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--subject", required=True)
    parser.add_argument("--outer", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--pilot-audit", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--reference-worker",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "agent/modules/agent/backend/analysis_global_reference_worker.py",
    )
    args = parser.parse_args()
    inspect(
        args.subject,
        args.outer,
        args.manifest,
        args.pilot_audit,
        args.output,
        args.reference_worker,
    )


if __name__ == "__main__":
    main()
