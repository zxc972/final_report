"""Deterministic planning registry, quota, and actual model binding."""
import importlib
from types import SimpleNamespace
import pytest
from test_analysis_agent import agent
from test_analysis_product_planner import setup_products

phase = importlib.import_module(agent.__package__ + ".analysis_phase_tools")
planning = importlib.import_module(agent.__package__ + ".analysis_planning_tools")


def test_initial_four_read_budget_then_forced_plan(tmp_path, monkeypatch):
    tools = setup_products(tmp_path, monkeypatch)
    assert phase.phase_tools(tools.session, []) == planning.INITIAL
    for name in ("read_file", "ls", "read_file", "ls"):
        planning.reserve_action(tools, name)
    assert phase.phase_tools(tools.session, []) == {"plan_analysis"}
    assert planning.selection(tools.session)[1] == "plan_analysis"
    with pytest.raises(ValueError, match="quota exhausted"):
        planning.reserve_action(tools, "ls")
    assert tools.session.record["planning_read_calls"] == 4


def test_plan_to_commit_argument_error_and_two_replans(tmp_path, monkeypatch):
    tools = setup_products(tmp_path, monkeypatch)
    planning.reserve_action(tools, "plan_analysis")
    result = tools.plan_analysis({"measures": ["thickness"], "regions": "aparc"})
    assert result["candidates"]
    assert phase.phase_tools(tools.session, []) == planning.AFTER_PLAN
    assert planning.selection(tools.session)[1] == "commit_plan"
    tools.session.record["commit_argument_error"] = True
    assert phase.phase_tools(tools.session, []) == {"commit_plan", "plan_analysis"}
    planning.reserve_action(tools, "plan_analysis")
    planning.reserve_action(tools, "plan_analysis")
    assert phase.phase_tools(tools.session, []) == {"commit_plan"}
    with pytest.raises(ValueError, match="two replans"):
        planning.reserve_action(tools, "plan_analysis")
