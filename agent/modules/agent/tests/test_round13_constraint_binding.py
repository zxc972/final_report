"""Replay untouched round-12 drafts and immutable failed constraints."""
import importlib
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from test_analysis_agent import agent
from test_analysis_product_planner import setup_products

protocol = importlib.import_module(agent.__package__ + ".analysis_review_protocol")
cross = importlib.import_module(agent.__package__ + ".analysis_crossspecies")
binding = importlib.import_module(agent.__package__ + ".analysis_constraint_binding")


def test_h1_original_block_survives_context_reevaluation(tmp_path, monkeypatch):
    tools = setup_products(tmp_path, monkeypatch)
    monkeypatch.setenv("AGENT_CROSSSPECIES_RULES", "1")
    fixture = json.loads((Path(__file__).parent / "fixtures/round12_h1_constraint_snapshot.json").read_text())
    saved = tools.control_store.save("constraints", fixture["constraints"]["record"])
    assert saved["sha256"] == fixture["execution_constraints_sha256"]
    tools.report_execution = {"constraints_sha256": saved["sha256"], "status": "blocked"}
    tools.control_store.save("constraints", {"rows": [], "summary": {"pass": 0, "warn": 0, "block": 0}})
    actual, ref = binding.resolve(tools)
    assert actual["sha256"] == saved["sha256"]
    monkeypatch.setattr(cross, "observed_environment", lambda *args: {"atlas": {"applicable": False}, "species": ["human"]})
    result = cross.submit_conclusion(tools, "The requested method was blocked; no execution took place.", "unclassified")
    card = result["conclusion_card"]
    blocks = [row for row in card["checks_not_passed"] if row["constraint_id"] == "cross:species_atlas"]
    assert blocks and blocks[0]["verdict"] == "block"
    assert card["constraint_binding"]["sha256"] == saved["sha256"]


def test_executed_plan_binding_ignores_a_newer_proposal(tmp_path, monkeypatch):
    from test_round8_closure import sealed
    tools, _, _ = sealed(tmp_path, monkeypatch)
    original = tools.control_store.latest("plan")
    expected = original["record"]["plan"]["constraints"]["sha256"]
    tools.report_execution = {"status": "success", "plan_gate": {"plan_version": original["version"]}}
    changed = dict(original["record"])
    changed["plan"] = dict(original["record"]["plan"])
    changed["plan"]["constraints"] = {"sha256": "f" * 64, "version": 999}
    tools.control_store.save("plan", changed)
    actual, ref = binding.resolve(tools)
    assert actual["sha256"] == expected and ref["source"] == "executed_plan"
