"""Real reference-worker audit on tiny synthetic MGH/mesh products only."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

np = pytest.importorskip("numpy")
nib = pytest.importorskip("nibabel")


def synthetic_dataset(tmp_path, tamper=False):
    root = tmp_path / "dataset"
    outer = root / "derivatives/synth"
    sid = "SYNTH_RHESUS"
    native = outer / sid
    backup = outer / (sid + "_1mm")
    raw = root / "raw/T1w.nii.gz"
    raw.parent.mkdir(parents=True)
    data = np.ones((4, 4, 4), dtype="float32")
    nib.save(nib.Nifti1Image(data, np.diag([0.5, 0.5, 0.5, 1])), raw)
    outer.mkdir(parents=True)
    nib.save(nib.Nifti1Image(data, np.diag([0.5, 0.5, 0.5, 1])), outer / "T1.nii.gz")
    vertices = np.array([(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)], dtype="float32")
    faces = np.array([(0, 2, 1), (0, 1, 3), (0, 3, 2), (1, 2, 3)], dtype="int32")
    area = (3 + 3**0.5) / 2
    for target, k in [(native, 0.5), (backup, 1.0)]:
        for name in ["mri", "surf", "label", "stats"]:
            (target / name).mkdir(parents=True, exist_ok=True)
        nib.save(
            nib.MGHImage(data, np.diag([k, k, k, 1])), target / "mri/brainmask.mgz"
        )
        for h in ["lh", "rh"]:
            for kind in ["white", "pial", "smoothwm"]:
                factor = 2 if target == backup else 1
                if tamper and target == backup and h == "lh" and kind == "white":
                    factor = 3
                nib.freesurfer.write_geometry(
                    target / "surf" / (h + "." + kind), vertices * factor, faces
                )
            nib.freesurfer.write_morph_data(
                target / "surf" / (h + ".thickness"), np.ones(4, dtype="float32") * 2
            )
            (target / "label" / (h + ".cortex.label")).write_text(
                "# synthetic\n4\n0 0 0 0 0\n1 0 0 0 0\n2 0 0 0 0\n3 0 0 0 0\n"
            )
            (target / "stats" / (h + ".aparc.stats")).write_text(
                f"# Measure Cortex, WhiteSurfArea, White Surface Total Area, {area:.10f}, mm^2\n"
            )
    manifest = root / "manifest.json"
    manifest.write_text(
        json.dumps(
            [
                {
                    "subject_id": sid,
                    "held_out": False,
                    "species": "Macaca mulatta",
                    "t1_file": str(raw),
                    "raw_sha256": hashlib.sha256(raw.read_bytes()).hexdigest(),
                }
            ]
        )
    )
    pilot = root / "provenance/pilot"
    pilot.mkdir(parents=True)
    (pilot / "pilot_status.json").write_text(
        json.dumps(
            {"steps": [{"returncode": 0, "missing_products": []} for _ in range(8)]}
        )
    )
    (pilot / "pilot_plan.json").write_text("{}")
    return root, outer, sid, manifest, pilot


@pytest.mark.parametrize("tamper", [False, True])
def test_generic_auditor_never_certifies_inconsistent_scale(tmp_path, tamper):
    root, outer, sid, manifest, pilot = synthetic_dataset(tmp_path, tamper)
    out = root / "provenance/acceptance"
    tool = Path(__file__).resolve().parents[4] / "tools/accept_macaque_globals.py"
    python = os.environ.get("ANALYSIS_REFERENCE_PYTHON", sys.executable)
    run = subprocess.run(
        [
            python,
            "-B",
            str(tool),
            "--subject",
            sid,
            "--outer",
            str(outer),
            "--manifest",
            str(manifest),
            "--pilot-audit",
            str(pilot),
            "--output",
            str(out),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert run.returncode == 0, run.stderr
    record = json.loads((out / "acceptance.json").read_text())
    scale = json.loads((out / "scale.json").read_text())
    assert (
        scale["producer_tool_sha256"] == hashlib.sha256(tool.read_bytes()).hexdigest()
    )
    assert scale["verified"] is (not tamper)
    # The clean tetra fixture is exactly at the inclusive two-voxel bound.
    assert record["status"] == ("fail" if tamper else "pass")
    if tamper:
        assert all(v is None for v in record["metrics"]["physical"].values())
    else:
        assert record["metrics"]["physical"]["brain_volume_mm3"] == 8.0
    assert not (outer / sid / "acceptance.json").exists()
