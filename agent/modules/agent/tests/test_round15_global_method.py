"""Synthetic Round15 public contracts, independent reference and scale policy."""

import csv
import hashlib
import importlib
import json
import os
import sys
from pathlib import Path

import pytest
from test_analysis_agent import agent
from test_analysis_product_planner import setup_products, p

np = pytest.importorskip("numpy")
nib = pytest.importorskip("nibabel")
g = importlib.import_module(agent.__package__ + ".analysis_global_method")
host = importlib.import_module(agent.__package__ + ".analysis_global_host")
verifier = importlib.import_module(agent.__package__ + ".analysis_independent_numeric")
operations = importlib.import_module(agent.__package__ + ".analysis_operations")
contract = importlib.import_module(agent.__package__ + ".analysis_output_contract")
worker = importlib.import_module(agent.__package__ + ".analysis_profile_worker")


def fixture(tmp_path, monkeypatch, known=True, mask_only=False, pial=True):
    tools = setup_products(tmp_path, monkeypatch)
    root = tools.input_roots[0]
    (root / "stats").mkdir()
    (root / "mri").mkdir()
    files = []
    if not mask_only:
        target = root / "stats/aseg.stats"
        target.write_text(
            "# Measure BrainSeg, BrainSegVol, Brain Segmentation Volume, 1200.123456, mm^3\n# Measure EstimatedTotalIntraCranialVol, eTIV, Intracranial volume, 1500.987654, mm^3\n"
        )
        files.append(target)
    else:
        target = root / "mri/brainmask.mgz"
        data = np.zeros((4, 4, 4), dtype="float32")
        data[0:2, :, :] = 1
        nib.save(nib.MGHImage(data, np.diag([0.5, 0.5, 0.5, 1.0])), target)
        files.append(target)
    for hemi, area, thick in [("lh", 100.123456, 2.514234), ("rh", 110.9284, 2.711518)]:
        target = root / "stats" / f"{hemi}.aparc.stats"
        target.write_text(
            f"# Measure Cortex, WhiteSurfArea, White Surface Total Area, {area}, mm^2\n# Measure Cortex, MeanThickness, Mean Thickness, {thick}, mm\n"
        )
        files.append(target)
        if pial:
            target = root / "surf" / f"{hemi}.pial"
            nib.freesurfer.write_geometry(
                target,
                np.array([(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)], dtype="float32"),
                np.array([(0, 2, 1), (0, 1, 3), (0, 3, 2), (1, 2, 3)]),
            )
            files.append(target)
    rows = []
    for file in files:
        row = worker.profile_file(file)
        row["path"] = worker.field(
            "/inputs/0/" + file.relative_to(root).as_posix(), file, "synthetic binding"
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
    source = tmp_path / "synthetic_scale_source.json"
    source.write_text('{"rescale_step_executed":false}')
    entry = {
        "subject_id": "synth",
        "path": str(root),
        "species_declared": "human",
        "source": "Synthetic fixture only",
    }
    if known:
        entry["scale_observation"] = {
            "rescaled": False,
            "k": 1,
            "sources": [
                {
                    "path": str(source),
                    "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                }
            ],
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
        "species": "human",
        "measures": ["global_morphometry"],
        "regions": "global",
        "comparison": "describe",
        "method_id": g.METHOD,
    }
    return tools, intent


def sealed(tools, intent):
    result = tools.plan_analysis(intent)
    assert result.get("candidates"), result
    item = p.commit_candidate(
        tools,
        result["candidates"][0]["candidate_id"],
        "Describe actual supplied global products",
        "/work/globals.py",
    )
    assert item["status"] == "committed", item
    return item


def test_discovery_types_and_bounded_card(tmp_path, monkeypatch):
    tools, intent = fixture(tmp_path, monkeypatch)
    payload = sealed(tools, intent)
    assert any(
        "/stats/aseg.stats" in path
        for path in p.discover_paths(
            p.registered_roots(tools, p.validate_intent(intent)[0])
        )
    )
    card = g.execution_card(payload)["execution_card"]
    assert len(card) <= 1500 and "BrainSegVol/eTIV" in card
    assert payload["execution_bundle"]["output_contract"]["table"]["expected_rows"] == 1
    assert not payload["plan"]["atlas"]["applicable"]


def test_independent_match_and_tamper(tmp_path, monkeypatch):
    tools, intent = fixture(tmp_path, monkeypatch)
    payload = sealed(tools, intent)
    tools.last_execution = {
        "status": "success",
        "exit_code": 0,
        "receipt_id": "synthetic-execution",
    }
    rows, keys, cols = host.reference_rows(tools, payload["plan"])
    target = tools.workdir / "global_metrics.csv"

    def write():
        with target.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=g.COLUMNS)
            writer.writeheader()
            writer.writerows(rows)

    write()
    public = contract.validate_csv(
        target.read_bytes(), g.table_contract(payload["plan"]), "global_metrics.csv"
    )
    assert public["status"] == "pass", public
    matched = verifier.verify(tools)
    assert (
        matched["status"] == "pass"
        and matched["identity_mismatch_count"] == matched["numeric_mismatch_count"] == 0
    )
    checks = tools.control_store.latest("global_postexecution_checks")["record"]["rows"]
    assert {r["template"] for r in checks} >= {
        "scale_check",
        "plausibility",
        "cross_species_measure",
    }
    rows[0]["total_area_mm2"] += 1
    write()
    mismatch = verifier.verify(tools)
    assert (
        mismatch["status"] == "fail"
        and mismatch["numeric_mismatch_count"] == 1
        and mismatch["identity_mismatch_count"] == 0
    )


def test_unknown_scale_keeps_physical_blank_and_mask_fallback(tmp_path, monkeypatch):
    tools, intent = fixture(
        tmp_path, monkeypatch, known=False, mask_only=True, pial=False
    )
    payload = sealed(tools, intent)
    tools.last_execution = {
        "status": "success",
        "exit_code": 0,
        "receipt_id": "synthetic-execution",
    }
    rows, _, _ = host.reference_rows(tools, payload["plan"])
    assert all(rows[0][key] is None for key in g.METRICS)
    assert rows[0]["stored_brain_volume_mm3"] == 4.0
    assert rows[0]["stored_etiv_mm3"] is None and rows[0]["stored_hull_ratio"] is None
    assert rows[0]["scale_status"] == "unknown"


def test_malformed_public_identity_rejected(tmp_path, monkeypatch):
    tools, intent = fixture(tmp_path, monkeypatch)
    plan = sealed(tools, intent)["plan"]
    text = (
        ",".join(g.COLUMNS)
        + "\n"
        + ",".join(
            ["wrong", "human"] + ["1"] * 5 + ["verified_not_rescaled", "1"] + ["1"] * 5
        )
        + "\n"
    )
    check = contract.validate_csv(text.encode(), g.table_contract(plan))
    assert check["status"] == "fail" and check["identity_mismatch_count"] > 0


def test_scale_sources_cannot_silently_change(tmp_path):
    source = tmp_path / "scale.json"
    source.write_text('{"k":2}')
    entry = {
        "scale_observation": {
            "rescaled": True,
            "k": 2,
            "sources": [
                {
                    "path": str(source),
                    "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                }
            ],
        }
    }
    assert g.trusted_scale(entry)["host_verified"]
    source.write_text('{"k":3}')
    assert g.trusted_scale(entry)["status"] == "unknown"


def test_cross_species_host_ratio_and_unique_subjects(tmp_path):
    storemod = importlib.import_module(agent.__package__ + ".analysis_control_store")
    store = storemod.ControlStore(tmp_path / "protected", [])
    for subject, species, volume in [
        ("h1", "human", 1200000.0),
        ("m1", "macaque", 100000.0),
    ]:
        target = tmp_path / (subject + ".csv")
        target.write_text("synthetic passed result\n")
        checks = [
            {
                "constraint_id": key,
                "severity": "soft",
                "verdict": "pass",
                "tool_observed": {
                    "reason": "Synthetic observed scale/reference checks"
                },
            }
            for key in ["cross:scale_check", "cross:plausibility"]
        ]
        row = {
            "subject": subject,
            "species": species,
            "physical": {"brain_volume_mm3": volume},
            "scale_status": "verified_not_rescaled",
            "scale_k": 1,
            "output_path": str(target),
            "output_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            "checks": checks,
        }
        store.save("eligible_subject", row)
        store.save("eligible_subject", row)
    result = host.aggregate(store)
    assert result["unique_subjects"] == 2
    assert result["summary"][0]["ratio"] == 12
    assert result["summary"][0]["human_n"] == result["summary"][0]["macaque_n"] == 1
    assert result["conclusion_card"]["scope"] == "global_cross_species_ratio"
    assert result["conclusion_card"]["verdict"] == "accepted"
    assert result["homology_required"] is False
    assert (store.root / "cross_species_global.csv").is_file()


def test_only_completed_reviewed_results_enter_host_registry(tmp_path, monkeypatch):
    tools, intent = fixture(tmp_path, monkeypatch)
    plan = sealed(tools, intent)["plan"]
    tools.last_execution = {
        "status": "success",
        "exit_code": 0,
        "receipt_id": "synthetic-execution",
    }
    rows, _, _ = host.reference_rows(tools, plan)
    with (tools.workdir / "global_metrics.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=g.COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    assert verifier.verify(tools)["status"] == "pass"
    response = {"status": "incomplete_review", "validation": {}}
    assert host.publish_eligible(tools, response)["status"] == "not_eligible"
    response = {
        "status": "completed",
        "validation": {
            "public_output_contract": {"status": "pass"},
            "internal_review": {"decision": "pass", "protocol_valid": True},
        },
    }
    result = host.publish_eligible(tools, response)
    assert result["status"] == "waiting_for_both_species"
    assert result["conclusion_card"]["verdict"] == "deferred"
    assert result["summary"] == []


def test_plausibility_warning_qualifies_global_ratio_not_homology(tmp_path):
    policy = importlib.import_module(agent.__package__ + ".analysis_crossspecies")
    rows = [
        {
            "constraint_id": key,
            "severity": "soft",
            "verdict": verdict,
            "tool_observed": {"reason": "Synthetic actual probe"},
        }
        for key, verdict in [
            ("cross:scale_check", "pass"),
            ("cross:cross_species_measure", "pass"),
            ("cross:plausibility", "warn"),
        ]
    ]
    plan = {
        "method": {"method_id": g.METHOD},
        "analysis_scope": {"comparison": "cross_species"},
    }
    assert "global_cross_species_ratio" in policy.supported_scopes(plan, rows)
    assert "cross_species_comparison" not in policy.supported_scopes(plan, rows)
