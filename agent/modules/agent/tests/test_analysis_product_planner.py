"""Offline product planning, typed boundaries and isolated profile regressions."""

import copy
import importlib
import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from test_analysis_agent import agent
from test_analysis_knowledge_profiles import make_tools, capture_builder
from test_analysis_constraints import c, f, file, profile

p = importlib.import_module(agent.__package__ + ".analysis_product_planner")
plans = importlib.import_module(agent.__package__ + ".analysis_plans")


@pytest.mark.parametrize("field,bad", [("measures", "thickness"), ("regions", {"name": "frontal"}), ("comparison", ["describe"]), ("subjects", 12), ("space", 1)])
def test_intent_errors_identify_field(field, bad):
    intent, error = p.validate_intent({"measures": ["thickness"], field: bad})
    assert intent is None and error["status"] == "error"
    assert any(row["field"].startswith(field) for row in error["field_errors"])
    assert "AttributeError" not in json.dumps(error)


def test_uniform_cost_is_shortest_and_cycle_safe():
    steps = [
        {"id": "first", "inputs": ["a"], "outputs": ["b"], "input_space": "native", "output_space": "native", "cost": 1},
        {"id": "second", "inputs": ["b"], "outputs": ["c"], "input_space": "native", "output_space": "native", "cost": 1},
        {"id": "direct", "inputs": ["a"], "outputs": ["c"], "input_space": "native", "output_space": "native", "cost": 1},
        {"id": "cycle", "inputs": ["c"], "outputs": ["a"], "input_space": "native", "output_space": "native", "cost": 1},
    ]
    assert p.backward_plan([("a", "native")], ["c"], steps)["steps"] == ["direct"]
    assert p.backward_plan([("a", "native")], ["z"], steps) is None
    assert p.backward_plan([("c", "fsLR_32k")], ["c"], [], "native") is None


def setup_products(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_ANALYSIS_STATE_DIR", str(tmp_path / "state"))
    tools = make_tools(tmp_path, monkeypatch, "product_graph_planner")
    root = tools.input_roots[0]
    rows = []
    for hemi in ("lh", "rh"):
        for name in ("white", "pial", "sphere.reg", "thickness"):
            path = root / "surf" / (hemi + "." + name)
            path.parent.mkdir(exist_ok=True)
            path.write_text("synthetic product " + hemi + name)
            mapped = "/inputs/0/surf/" + path.name
            item = file(mapped, "surface_metric" if name == "thickness" else "surface")
            item["sha256"] = f(p.file_hash(path)[0])
            if name == "thickness":
                item["metric"] = f({"vertex_count": f(4), "finite_count": f(4), "ndim": f(1)})
            else:
                item["surface"] = f({"vertex_count": f(4), "face_count": f(4), "face_width": f(3)})
            rows.append(item)
        for name in ("aparc.annot", "alternate.annot", "cortex.label"):
            path = root / "label" / (hemi + "." + name)
            path.parent.mkdir(exist_ok=True)
            path.write_text("synthetic labels " + name)
            item = file("/inputs/0/label/" + path.name, "label" if name.endswith(".label") else "annot")
            item["sha256"] = f(p.file_hash(path)[0])
            if name.endswith(".annot"):
                item["label"] = f({"vertex_count": f(4), "unassigned_vertices": f(1), "special_vertices": f({"unknown": 1}), "label_names": f(["unknown", "one", "two"]), "label_keys": f([0, 1, 2]), "cortex_retained_label_counts": f({"-1": 1, "1": 1, "2": 2})})
            rows.append(item)
    saved = tools.control_store.save("data_profile", profile(rows))
    monkeypatch.setattr(p, "ensure_profile", lambda tools, paths: (saved, True))
    graph_root = tmp_path / "graph"
    graph_root.mkdir()
    (graph_root / "domain_graph.json").write_text(json.dumps({"nodes": [{"id": "label:one", "name": "ctx-lh-one", "type": "LabelDefinition", "evidence": [{"url": "https://example.invalid/source"}]}]}))
    method_names = {r["method_id"]: r["method_id"].split(":")[-1] for r in p.load_knowledge("method_requirements")[0]["methods"]}
    class Graph:
        root = graph_root
        def read(self, method_id):
            return {"method": {"id": method_id, "name": method_names[method_id], "inputs": [], "conditions": []}, "source_evidence": []}
    tools._method_graph_store = Graph()
    def software(tools, commands, method_id):
        ok = "matlab" not in commands
        return ok, {"commands": [{"command": command, "executable": command != "matlab", "exit_code": 0 if command != "matlab" else None} for command in commands], "reason": "Synthetic software observation"}
    monkeypatch.setattr(c, "software_observation", software)
    return tools


def test_multiple_atlases_exclusions_and_graph_mapping(tmp_path, monkeypatch):
    tools = setup_products(tmp_path, monkeypatch)
    result = p.plan_analysis(tools, {"measures": ["thickness"], "regions": "all regions"})
    rois = [r for r in result["candidates"] if r["method"]["method_id"].endswith("surface_annotation_roi")]
    assert len(rois) == 2
    assert all(set(r["label_counts"].values()) == {2} for r in rois)
    assert all(r["mapping_source_count"] > 0 for r in rois)
    record = tools.control_store.latest(rois[0]["candidate_id"])["record"]
    assert record["plan"]["atlas"]["exclude_labels"] == [-1, "unknown", "medialwall", "corpuscallosum"]
    assert record["condition_snapshot"]["summary"]["block"] == 0


def test_real_observation_blocker_and_nonatlas_alternative(tmp_path, monkeypatch):
    tools = setup_products(tmp_path, monkeypatch)
    result = p.plan_analysis(tools, {"measures": ["lgi"]})
    assert any("MATLAB" in row["reason"] for row in result["infeasible"])
    candidate = result["candidates"][0]
    assert candidate["method"]["method_id"].endswith("global_convex_hull_gyrification")
    assert candidate["atlas"]["applicable"] is False and candidate["atlas"]["version"] is None
    sealed = p.commit_candidate(tools, candidate["candidate_id"], "Use available descriptive hull geometry; it is not lGI.", "/work/folding.py")
    assert sealed["status"] == "committed"
    assert sealed["plan"]["atlas"]["version"] is None
    assert plans.execution_gate(tools, tools.workdir / "folding.py")["allowed"] is True
    again = p.commit_candidate(tools, candidate["candidate_id"], "Keep the same scope after review.", "/work/folding.py")
    assert again["version"] == 2
    (tools.workdir / "other.py").write_text("open('different.csv', 'w').write('x')")
    assert not plans.execution_gate(tools, tools.workdir / "other.py")["allowed"]


def test_unknown_region_and_self_inputs_rejected(tmp_path, monkeypatch):
    tools = setup_products(tmp_path, monkeypatch)
    result = p.plan_analysis(tools, {"measures": ["thickness"], "regions": "invented_homologue"})
    assert not [c for c in result["candidates"] if c["method"]["method_id"].endswith("surface_annotation_roi")]
    _, error = p.validate_intent({"measures": ["custom"], "method_id": "self:custom", "required_inputs": ["invented_product"]})
    assert error["field_errors"][0]["field"] == "required_inputs"


def test_product_tool_schema_and_controls_are_separate(tmp_path, monkeypatch):
    tools = setup_products(tmp_path, monkeypatch)
    captured = capture_builder(tools, monkeypatch)
    registry = {t.name: t for t in captured["tools"]}
    assert {"plan_analysis", "commit_plan"} <= registry.keys()
    assert not {"profile_data", "compile_constraints", "search_analysis_methods"} & registry.keys()
    assert set(registry["commit_plan"].args) == {"candidate_id", "rationale", "code_path"}
    assert "plan_analysis" in captured["system_prompt"]
    for name in ("method_graph_gated", "legacy_v13"):
        other = tmp_path / name
        other.mkdir()
        controls = make_tools(other, monkeypatch, name)
        captured = capture_builder(controls, monkeypatch)
        assert "plan_analysis" not in {t.name for t in captured["tools"]}
        if name == "method_graph_gated":
            assert set(next(t for t in captured["tools"] if t.name == "commit_plan").args) == {"plan"}

def test_missing_pial_products_returns_dependency_steps(tmp_path, monkeypatch):
    tools = setup_products(tmp_path, monkeypatch)
    saved = tools.control_store.latest("data_profile")
    saved["record"]["files"] = [row for row in saved["record"]["files"] if not row["path"]["value"].endswith(".pial")]
    saved = tools.control_store.save("data_profile", saved["record"])
    monkeypatch.setattr(p, "ensure_profile", lambda tools, paths: (saved, True))
    real_load = p.load_knowledge
    step = {"id": "synthetic-surface-supplement", "inputs": [{"type": "type:Surface.White"}], "outputs": [{"type": "type:Surface.Pial"}], "software": [], "cost": 1}
    monkeypatch.setattr(p, "load_knowledge", lambda name, tools=None: ({"steps": [step]}, "a" * 64) if name == "workflow_steps" else real_load(name, tools))
    result = p.plan_analysis(tools, {"measures": ["gyrification"], "regions": "global"})
    assert not result["candidates"]
    route = result["needs_preprocessing"][0]["preprocessing_plan"]
    assert route["steps"] == ["synthetic-surface-supplement"]
    assert {row["scope"].split("/")[-1] for row in route["by_scope"]} == {"lh", "rh"}
    assert route["execution_allowed"] is False


def test_actual_events_bind_same_named_calls_by_tool_id(tmp_path, monkeypatch):
    tools = setup_products(tmp_path, monkeypatch)
    tools.events.call_tool("ls", {"path": "/inputs"}, lambda: {"status": "ok"}, tool_call_id="real-call-one")
    tools.events.call_tool("ls", {"path": "/inputs"}, lambda: {"status": "ok"}, tool_call_id="real-call-two")
    rows = tools.events.all()
    assert [row["detail"]["tool_call_id"] for row in rows] == ["real-call-one", "real-call-one", "real-call-two", "real-call-two"]
