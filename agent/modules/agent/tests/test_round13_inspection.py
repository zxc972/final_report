"""Inspection claims are exact protected values, not execution artifacts."""
import importlib
import json
import pytest
from test_analysis_agent import agent
from test_analysis_product_planner import setup_products

inspection = importlib.import_module(agent.__package__ + ".analysis_inspection")
router = importlib.import_module(agent.__package__ + ".agent_router")
phase = importlib.import_module(agent.__package__ + ".analysis_phase_tools")


def test_p3_kind_and_disallowed_dispatch():
    response = {"choices": [{"message": {"content": json.dumps({"route": "analysis", "reason": "Inspect metadata only.", "task_kind": "data_inspection"})}}]}
    assert router.parse_route(response, require_task_kind=True)["task_kind"] == "data_inspection"
    value = json.loads(response["choices"][0]["message"]["content"])
    value["route"] = "pipeline"
    response["choices"][0]["message"]["content"] = json.dumps(value)
    with pytest.raises(ValueError, match="disagree"):
        router.parse_route(response, require_task_kind=True)


def test_inspection_exact_values_and_no_execution(tmp_path, monkeypatch):
    tools = setup_products(tmp_path, monkeypatch)
    tools.execution_required = False
    rows = [{"subject": "fixture", "root": "/inputs/0", "files": 7, "formats": ["annot", "surface_metric"],
             "atlases": ["aparc"], "species_declared": "human", "species_verified": None, "space": "native_stored"}]
    tools.control_store.save("data_card", {"subjects": rows, "software": {}, "scope": "fixture"})
    claims = {"claims": [{"record_id": "data_card.v000001.json", "pointer": "/subjects", "value": rows}]}
    result = inspection.validate(tools, json.dumps(claims))
    assert result["passed"] and result["scope"] == "data_inspection"
    assert "7 observed files" in inspection.render(result)
    assert phase.phase_tools(tools.session, ["run_python"]) == {"ls", "read_file"}
    claims["claims"][0]["value"][0]["files"] = 8
    assert not inspection.validate(tools, json.dumps(claims))["passed"]
    assert tools.executions == 0 and tools.control_store.latest("plan") is None
