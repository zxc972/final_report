"""Integration boundaries that the standalone algorithm examples do not cover."""

import copy
import importlib
import json
from pathlib import Path
import pytest
from test_analysis_product_planner import setup_products, p
from backend import analysis_andor_planner as ao
from backend import analysis_csp_matching as csp
from backend import analysis_matching_adapter as matching
from backend import analysis_completion_adapter as completion


def test_actual_planner_uses_csp_and_reports_typed_missing(tmp_path, monkeypatch):
    tools = setup_products(tmp_path, monkeypatch)
    before = p.plan_analysis(
        tools,
        {"measures": ["thickness"], "method_id": "method:v12:surface_annotation_roi"},
    )
    assert len(before["candidates"]) == 2
    assert all(c["matching_stats"]["search_nodes"] > 0 for c in before["candidates"])
    saved = tools.control_store.latest("data_profile")
    saved["record"]["files"] = [
        f
        for f in saved["record"]["files"]
        if not f["path"]["value"].endswith("lh.thickness")
    ]
    monkeypatch.setattr(p, "ensure_profile", lambda *_: (saved, True))
    after = p.plan_analysis(
        tools,
        {"measures": ["thickness"], "method_id": "method:v12:surface_annotation_roi"},
    )
    assert not after["candidates"]
    failures = after["infeasible"] + after["needs_preprocessing"]
    assert failures and all(r["optimality_check"]["consistent"] for r in failures)
    assert all(
        any(
            t["type"] == "type:SurfaceMetric.Thickness"
            and t["attrs"]["hemisphere"] == "lh"
            for t in r["missing_requirements"]
        )
        for r in failures
    )


def test_mesh_conflict_is_not_misreported_as_an_empty_domain(tmp_path, monkeypatch):
    tools = setup_products(tmp_path, monkeypatch)
    saved = tools.control_store.latest("data_profile")
    next(
        f
        for f in saved["record"]["files"]
        if f["path"]["value"].endswith("lh.thickness")
    )["metric"]["value"]["vertex_count"]["value"] = 999
    monkeypatch.setattr(p, "ensure_profile", lambda *_: (saved, True))
    out = p.plan_analysis(
        tools,
        {"measures": ["thickness"], "method_id": "method:v12:surface_annotation_roi"},
    )
    assert not out["candidates"]
    assert all(
        r["matching_conflicts"] and not r["missing_requirements"]
        for r in out["infeasible"]
    )
    assert any(
        c["constraint_id"] == "product_metric_mesh_identity"
        for c in out["infeasible"][0]["matching_conflicts"]
    )


def test_every_solver_assignment_becomes_a_candidate(tmp_path, monkeypatch):
    tools = setup_products(tmp_path, monkeypatch)
    saved = tools.control_store.latest("data_profile")
    alternative = copy.deepcopy(
        next(
            f
            for f in saved["record"]["files"]
            if f["path"]["value"].endswith("lh.pial")
        )
    )
    alternative["path"]["value"] = "/inputs/0/surf/lh.pial.alternative"
    saved["record"]["files"].append(alternative)
    saved = tools.control_store.save("data_profile", saved["record"])
    monkeypatch.setattr(p, "ensure_profile", lambda *_: (saved, True))
    out = p.plan_analysis(
        tools,
        {
            "measures": ["gyrification"],
            "regions": "global",
            "method_id": "method:v13:global_convex_hull_gyrification",
        },
    )
    assert len(out["candidates"]) == 2
    assignments = [
        tools.control_store.latest(c["candidate_id"])["record"]["matching_assignment"]
        for c in out["candidates"]
    ]
    assert assignments[0] != assignments[1]


def test_large_singleton_cohort_does_not_hit_recursion_limit():
    h = csp.TypeHierarchy([{"id": "T"}])
    products = [
        {"id": str(i), "type": "T", "attrs": {"subject": str(i)}} for i in range(1536)
    ]
    slots = [
        {
            "name": str(i),
            "type": "T",
            "unary": [{"kind": "attr_equals", "attr": "subject", "value": str(i)}],
        }
        for i in range(1536)
    ]
    out = csp.solve(slots, products, [], h)
    assert len(out["solutions"]) == 1 and out["stats"]["nodes"] == 1536


def test_shared_step_optimum_is_global_not_per_target_greedy():
    h = csp.TypeHierarchy([{"id": t} for t in ["A", "B", "C"]])
    have = [{"id": "a", "type": "A", "attrs": {}}]
    steps = [
        {"id": "b", "cost": 2, "inputs": [{"type": "A"}], "outputs": [{"type": "B"}]},
        {"id": "c", "cost": 2, "inputs": [{"type": "A"}], "outputs": [{"type": "C"}]},
        {
            "id": "both",
            "cost": 3,
            "inputs": [{"type": "A"}],
            "outputs": [{"type": "B"}, {"type": "C"}],
        },
    ]
    targets = [{"type": "B"}, {"type": "C"}]
    actual = ao.plan(targets, have, steps, h)
    exact = ao.optimal_plan(targets, have, steps, h)
    assert actual["cost"] == exact["cost"] == 3 and actual["steps"] == ["both"]


def test_oracle_excludes_species_and_disabled_steps_and_does_not_use_first_source_only():
    h = csp.TypeHierarchy([{"id": "A"}, {"id": "B"}])
    steps = [
        {
            "id": "make",
            "inputs": [{"type": "A", "attrs": {}}],
            "outputs": [{"type": "B", "inherit": ["subject", "species"]}],
            "species_allowed": ["macaque"],
        }
    ]
    have = [
        {"id": "h", "type": "A", "attrs": {"subject": "h", "species": "human"}},
        {"id": "m", "type": "A", "attrs": {"subject": "m", "species": "macaque"}},
    ]
    human = [{"type": "B", "attrs": {"subject": "h", "species": "human"}}]
    macaque = [{"type": "B", "attrs": {"subject": "m", "species": "macaque"}}]
    assert not ao.optimal_plan(human, have, steps, h)["feasible"]
    assert ao.optimal_plan(macaque, have, steps, h)["cost"] == 1
    steps[0]["eligible_for_planning"] = False
    assert not ao.plan(macaque, have, steps, h)["feasible"]
    assert not ao.optimal_plan(macaque, have, steps, h)["feasible"]


def test_workflow_constants_and_eligibility_survive_normalisation():
    steps = ao.steps_from_workflow(p.load_knowledge("workflow_steps")[0])
    assert len(steps) == 14
    conversion = next(s for s in steps if s["id"] == "freesurfer2caret")
    assert conversion["outputs"][0]["set"]["space"] == "fsLR_32k"
    assert conversion["outputs"][0]["set"]["mesh"] == 32492
    assert (
        next(s for s in steps if s["id"] == "fastsurfer")["eligible_for_planning"]
        is False
    )


def test_oracle_mismatch_emits_event_without_changing_returned_plan(
    tmp_path, monkeypatch
):
    tools = setup_products(tmp_path, monkeypatch)
    route = {
        "cost": 3,
        "steps": ["same"],
        "optimality_check": {"consistent": False, "cost": 2, "feasible": True},
    }
    before = copy.deepcopy(route)
    completion.record_check(tools, route, "synthetic")
    assert route == before
    assert (
        tools.events.all()[-1]["detail"]["event_type"] == "planning_optimality_mismatch"
    )


def test_cohort_level_missing_target_is_not_dropped():
    h = csp.TypeHierarchy([{"id": "A"}, {"id": "Table"}])
    targets = [{"type": "A", "attrs": {"subject": "s"}}, {"type": "Table", "attrs": {}}]
    have = [{"id": "a", "type": "A", "attrs": {"subject": "s"}}]
    out = completion.completion(targets, have, {"steps": []}, h, {})
    assert not out["feasible"] and out["optimality_check"]["consistent"]
    assert any("Table" in r for r in out["reason_chain"])


def test_invalid_or_alternative_does_not_block_valid_global_mask(tmp_path, monkeypatch):
    from test_round15_global_method import fixture

    tools, intent = fixture(tmp_path, monkeypatch)
    saved = tools.control_store.latest("data_profile")
    entries = p.registered_roots(tools, p.AnalysisIntent(**intent))
    products = matching.inventory(saved["record"], entries)
    aseg = next(x for x in products if x["type"] == "type:StatsTable.AsegStats")
    aseg["attrs"]["species"] = "chimpanzee"
    products.append(
        {
            "id": "/inputs/0/mri/brainmask.mgz",
            "type": "type:Volume.BrainExtractedT1",
            "attrs": {**aseg["attrs"], "species": entries[0]["species_declared"]},
        }
    )
    spec = next(
        s
        for s in p.load_knowledge("method_requirements")[0]["methods"]
        if s["method_id"] == "method:v15:global_morphometry"
    )
    out = matching.match(
        spec,
        entries,
        products,
        {"measures": ["globalmorphometry"]},
        None,
        p.load_knowledge("condition_templates")[0],
        p.load_knowledge("product_types")[0],
    )
    assert out["solutions"] and not out["missing"]
    assert all(aseg["id"] not in s["assignment"].values() for s in out["solutions"])


def test_no_selected_inputs_still_returns_a_plan_explanation(tmp_path, monkeypatch):
    tools = setup_products(tmp_path, monkeypatch)
    saved = tools.control_store.latest("data_profile")
    saved["record"]["files"] = [
        f for f in saved["record"]["files"] if not f["path"]["value"].endswith(".pial")
    ]
    saved = tools.control_store.save("data_profile", saved["record"])
    monkeypatch.setattr(p, "ensure_profile", lambda *_: (saved, True))
    result = p.plan_analysis(
        tools,
        {
            "measures": ["gyrification"],
            "regions": "global",
            "method_id": "method:v13:global_convex_hull_gyrification",
        },
    )
    assert not result["candidates"]
    rows = result["infeasible"] + result["needs_preprocessing"]
    assert rows and len(rows[0]["missing_requirements"]) == 2
    assert rows[0]["optimality_check"]["consistent"]


def test_read_errors_cannot_supply_a_csp_domain(tmp_path, monkeypatch):
    tools = setup_products(tmp_path, monkeypatch)
    saved = tools.control_store.latest("data_profile")
    broken = next(
        f for f in saved["record"]["files"] if f["path"]["value"].endswith("lh.pial")
    )
    broken["read_error"] = {
        "value": None,
        "error": "unreadable",
        "source": {"path": broken["path"]["value"]},
    }
    entries = p.registered_roots(tools, p.AnalysisIntent(measures=["gyrification"]))
    assert broken["path"]["value"] not in {
        r["id"] for r in matching.inventory(saved["record"], entries)
    }


def test_forward_closure_does_not_mix_hemispheres_or_meshes():
    h = csp.TypeHierarchy([{"id": x} for x in ["Surface", "Metric", "Result"]])
    steps = [
        {
            "id": "combine",
            "inputs": [{"type": "Surface"}, {"type": "Metric"}],
            "outputs": [{"type": "Result", "inherit": ["subject", "hemisphere"]}],
        }
    ]
    targets = [{"type": "Result", "attrs": {"subject": "s", "hemisphere": "lh"}}]
    for attr, value in [("hemisphere", "rh"), ("mesh", 999)]:
        have = [
            {
                "id": "s",
                "type": "Surface",
                "attrs": {"subject": "s", "hemisphere": "lh", "mesh": 100},
            },
            {
                "id": "m",
                "type": "Metric",
                "attrs": {"subject": "s", "hemisphere": "lh", "mesh": 100},
            },
        ]
        have[1]["attrs"][attr] = value
        assert not ao.plan(targets, have, steps, h)["feasible"]
        assert not ao.optimal_plan(targets, have, steps, h)["feasible"]
