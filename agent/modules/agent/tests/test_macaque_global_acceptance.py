"""Synthetic macaque direct-input policy and independent host calculations."""

import hashlib
import importlib
import json
import os
import sys

import pytest
from test_analysis_agent import agent
from test_analysis_product_planner import setup_products, p

np = pytest.importorskip("numpy")
nib = pytest.importorskip("nibabel")
ref = importlib.import_module(agent.__package__ + ".analysis_global_reference")
global_method = importlib.import_module(agent.__package__ + ".analysis_global_method")
host = importlib.import_module(agent.__package__ + ".analysis_global_host")
policy = importlib.import_module(agent.__package__ + ".analysis_global_policy")
worker = importlib.import_module(agent.__package__ + ".analysis_profile_worker")
ops = importlib.import_module(agent.__package__ + ".analysis_operations")

VERTICES = np.array([(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)], dtype="float32")
FACES = np.array([(0, 2, 1), (0, 1, 3), (0, 3, 2), (1, 2, 3)], dtype="int32")


def inputs(root):
    for name in ["surf", "label", "mri"]:
        (root / name).mkdir(exist_ok=True)
    request = {
        "species": "Macaca mulatta",
        "mask_volume": str(root / "mri/brainmask.mgz"),
        "white": {},
        "pial": {},
        "thickness": {},
        "cortex_labels": {},
        "scale_k": 1.0,
        "rescaled": True,
        "scale_state": "rescale_applied_and_reverted",
    }
    data = np.zeros((2, 2, 2), dtype="float32")
    data[0, :, :] = 1
    nib.save(nib.MGHImage(data, np.diag([0.5, 0.5, 0.5, 1])), request["mask_volume"])
    for hemi in ["lh", "rh"]:
        for kind, factor in [("white", 1.0), ("pial", 1.2)]:
            target = root / "surf" / (hemi + "." + kind)
            nib.freesurfer.write_geometry(target, VERTICES * factor, FACES)
            request[kind][hemi] = str(target)
        target = root / "surf" / (hemi + ".thickness")
        nib.freesurfer.write_morph_data(target, np.array([0, 2, 2, 4], dtype="float32"))
        request["thickness"][hemi] = str(target)
        target = root / "label" / (hemi + ".cortex.label")
        target.write_text(
            "#!ascii label synthetic\n4\n0 0 0 0 0\n1 0 0 0 0\n2 0 0 0 0\n3 0 0 0 0\n"
        )
        request["cortex_labels"][hemi] = str(target)
    return request


def test_macaque_reference_never_reads_aseg_or_parc_stats(tmp_path):
    req = inputs(tmp_path)
    req.update(
        aseg_stats=str(tmp_path / "must_not_open_aseg.stats"),
        hemi_stats={"lh": "must_not_open_lh.stats", "rh": "must_not_open_rh.stats"},
    )
    result = ref.subject_globals(**req)
    assert result["stored"]["brain_volume_mm3"] == 0.5
    assert result["stored"]["etiv_mm3"] is None
    assert result["stored"]["mean_thickness_mm"] == 2.0
    assert result["stored"]["total_area_mm2"] == pytest.approx(3 + 3**0.5)
    assert result["stored"]["hull_ratio"] == pytest.approx(1.0)
    assert result["scale_status"] == "rescale_applied_and_reverted"
    assert result["aseg_derived_values_used"] is False
    assert result["hemispheres"]["lh"]["cortex_zero_count"] == 1


def test_macaque_scale_correction_and_unknown(tmp_path):
    req = inputs(tmp_path)
    req.update(scale_state=None, scale_k=2, rescaled=True)
    result = ref.subject_globals(**req)
    assert result["physical"]["mean_thickness_mm"] == 1
    assert result["physical"]["brain_volume_mm3"] == 0.5 / 8
    assert (
        result["physical"]["total_area_mm2"] == result["stored"]["total_area_mm2"] / 4
    )
    req.update(scale_k=None, rescaled=None)
    assert all(
        value is None for value in ref.subject_globals(**req)["physical"].values()
    )


def test_reverted_status_cannot_be_attached_to_k2(tmp_path):
    req = inputs(tmp_path)
    req["scale_k"] = 2
    with pytest.raises(ValueError, match="Reverted scale"):
        ref.subject_globals(**req)


@pytest.mark.parametrize(
    "case",
    [
        "negative",
        "mesh_mismatch",
        "cortex_out_of_bounds",
        "empty_cortex",
        "missing_hemi",
    ],
)
def test_invalid_native_inputs_fail(tmp_path, case):
    req = inputs(tmp_path)
    if case == "negative":
        nib.freesurfer.write_morph_data(
            req["thickness"]["lh"], np.array([-1, 2, 2, 4], dtype="float32")
        )
    elif case == "mesh_mismatch":
        nib.freesurfer.write_morph_data(
            req["thickness"]["lh"], np.array([1, 2, 3], dtype="float32")
        )
    elif case == "cortex_out_of_bounds":
        from pathlib import Path

        Path(req["cortex_labels"]["lh"]).write_text("# synthetic\n1\n99 0 0 0 0\n")
    elif case == "empty_cortex":
        from pathlib import Path

        Path(req["cortex_labels"]["lh"]).write_text("# synthetic\n0\n")
    else:
        req["white"].pop("rh")
    with pytest.raises(ValueError):
        ref.subject_globals(**req)


def test_species_override_keeps_human_spec_identical():
    spec = {
        "method_id": global_method.METHOD,
        "required_products": ["cortical_parc_stats"],
        "alternative_products": [["aseg_stats", "brainmask"]],
    }
    assert policy.specialize(spec, [{"species_declared": "human"}]) is spec
    changed = policy.specialize(spec, [{"species_declared": "Macaca mulatta"}])
    assert "cortical_parc_stats" not in changed["required_products"]
    assert changed["metric_measures"] == ["thickness"]
    assert changed["alternative_products"] == []
    assert policy.is_macaque("monkey_unknown") is False


def planner_fixture(tmp_path, monkeypatch):
    tools = setup_products(tmp_path, monkeypatch)
    root = tools.input_roots[0]
    req = inputs(root)
    paths = [req["mask_volume"]]
    for name in ["white", "pial", "thickness", "cortex_labels"]:
        paths += list(req[name].values())
    from pathlib import Path

    rows = []
    for name in paths:
        path = Path(name)
        row = worker.profile_file(path)
        row["path"] = worker.field(
            "/inputs/0/" + path.relative_to(root).as_posix(),
            path,
            "synthetic explicit binding",
        )
        rows.append(row)
    profile = tools.control_store.save(
        "data_profile",
        {
            "schema_version": "primatex.data_profile.v1",
            "files": rows,
            "physical_scale_verified": worker.field(None, "fixture", "unverified"),
        },
    )
    monkeypatch.setattr(p, "ensure_profile", lambda *args: (profile, True))
    scale = tmp_path / "scale_source.json"
    scale.write_text('{"final_surface_scale_k":1,"verified":true}')
    entry = {
        "subject_id": "synth",
        "path": str(root),
        "species_declared": "macaque",
        "source": "Synthetic fixture only",
        "scale_observation": {
            "rescaled": True,
            "k": 1,
            "status": "rescale_applied_and_reverted",
            "sources": [
                {
                    "path": str(scale),
                    "sha256": hashlib.sha256(scale.read_bytes()).hexdigest(),
                }
            ],
        },
    }
    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps({"roots": [entry]}))
    monkeypatch.setenv("AGENT_DATA_CATALOG", str(catalog))
    monkeypatch.setenv(
        "ANALYSIS_REFERENCE_PYTHON",
        os.environ.get("ANALYSIS_REFERENCE_PYTHON", sys.executable),
    )
    intent = {
        "subjects": ["synth"],
        "species": "macaque",
        "measures": ["global_morphometry"],
        "regions": "global",
        "comparison": "describe",
        "method_id": global_method.METHOD,
    }
    return tools, intent


def test_planner_seals_direct_macaque_inputs_without_stats(tmp_path, monkeypatch):
    tools, intent = planner_fixture(tmp_path, monkeypatch)
    result = tools.plan_analysis(intent)
    assert result.get("candidates"), result
    sealed = p.commit_candidate(
        tools,
        result["candidates"][0]["candidate_id"],
        "Direct global macaque inputs",
        "/work/global_morphometry.py",
    )
    assert sealed["status"] == "committed", sealed
    plan = sealed["plan"]
    assert len(plan["data"]["files"]) == 9
    assert not any(
        path.endswith((".stats", ".annot")) for path in plan["data"]["files"]
    )
    assert plan["analysis_scope"]["global_bindings"]["aseg_stats"] is None
    assert (
        plan["analysis_scope"]["global_scale"]["status"]
        == "rescale_applied_and_reverted"
    )
    card = global_method.execution_card(sealed)["execution_card"]
    assert len(card) <= 1500 and "no aseg/annot" in card
    functions = {call["function"] for call in ops.suggested_operations(plan)["calls"]}
    assert "read_stats_measures" not in functions and "read_annotation" not in functions
    assert {
        "read_surface",
        "read_surface_metric",
        "read_label",
        "vertex_area",
        "positive_mask_volume",
        "convex_hull_area_ratio",
    } <= functions
    tools.last_execution = {
        "status": "success",
        "exit_code": 0,
        "receipt_id": "synthetic-execution",
    }
    rows, _, _ = host.reference_rows(tools, plan)
    assert rows[0]["etiv_mm3"] is None
    assert rows[0]["mean_thickness_mm"] == 2.0
    assert rows[0]["scale_status"] == "rescale_applied_and_reverted"
