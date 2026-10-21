"""Deterministic tool events, incremental owner-scoped reads and legacy isolation."""

import importlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import ToolMessage

from test_analysis_agent import agent
from test_analysis_knowledge_profiles import make_tools, capture_builder
from test_analysis_plans import ready

events = importlib.import_module(agent.__package__ + ".analysis_events")
store_module = importlib.import_module(agent.__package__ + ".analysis_control_store")
api = importlib.import_module(agent.__package__ + ".api")


def test_event_sequence_is_append_only_and_redacts(tmp_path):
    store = store_module.ControlStore(tmp_path / "protected", [tmp_path / "work"])
    log = events.AnalysisEvents(store, secret="fixture-secret")
    a = log.append(
        "data",
        "running",
        "Inspect data",
        {"reason": "fixture-secret", "token": "never persist"},
    )
    b = log.append("data", "done", "Data inspection done")
    assert (a["seq"], b["seq"]) == (1, 2)
    assert "fixture-secret" not in store.path("events.jsonl").read_text(
        encoding="utf-8"
    )
    assert "never persist" not in json.dumps(log.all())
    assert log.view(1)["events"] == [b]
    assert log.view(2)["events"] == []


@pytest.mark.parametrize(
    "name,stage",
    [
        ("ls", "data"),
        ("profile_data", "data"),
        ("search_evidence", "knowledge"),
        ("read_analysis_method", "knowledge"),
        ("compile_constraints", "constraints"),
        ("commit_plan", "plan"),
        ("write_code", "code"),
        ("run_python", "run"),
    ],
)
def test_tool_mapping_uses_actual_handlers(name, stage, tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_ANALYSIS_STATE_DIR", str(tmp_path / "state"))
    tools = make_tools(tmp_path, monkeypatch, "method_graph")
    captured = capture_builder(tools, monkeypatch)
    middleware = captured["middleware"][-1]
    payload = {"status": "ok"}
    if name == "compile_constraints":
        payload = {
            "status": "blocked",
            "summary": {"pass": 2, "warn": 1, "block": 1},
            "rows": [],
        }
    if name == "commit_plan":
        payload = {"status": "committed", "version": 3}
    middleware.wrap_tool_call(
        SimpleNamespace(
            tool_call={
                "name": name,
                "id": "fixture",
                "args": {"path": "/work/test.py", "query": "FreeSurfer lGI"},
            }
        ),
        lambda request: ToolMessage(
            content=json.dumps(payload), tool_call_id="fixture"
        ),
    )
    rows = tools.events.all()
    assert len(rows) == 2 and rows[0]["status"] == "running"
    assert rows[1]["stage"] == stage and len(rows[1]["title"]) <= 40
    assert rows[0]["detail"]["operation_id"] == rows[1]["detail"]["operation_id"]
    if name == "compile_constraints":
        assert rows[1]["status"] == "blocked" and "1 block" in rows[1]["title"]


def test_tool_exceptions_and_actual_exit_are_recorded(tmp_path, monkeypatch):
    tools, plan = ready(tmp_path, monkeypatch)

    def fail():
        raise ValueError("synthetic failure")

    with pytest.raises(ValueError):
        tools.events.call_tool("run_python", {"path": "/work/test.py"}, fail)
    assert tools.events.all()[-1]["status"] == "failed"
    tools.events.call_tool(
        "run_python", {}, lambda: {"status": "failed", "exit_code": 7}
    )
    row = tools.events.all()[-1]
    assert row["detail"]["exit_code"] == 7 and row["detail"]["duration_seconds"] >= 0


def test_committed_plan_summary_comes_from_protected_records(tmp_path, monkeypatch):
    tools, plan = ready(tmp_path, monkeypatch)
    tools.commit_plan(plan)
    summary = tools.events.plan_summary()
    assert summary["version"] == 1 and summary["constraints"]["warn"] == 1
    assert summary["code_path"] == "/work/analysis.py" and len(summary["history"]) == 1
    (tools.workdir / "plan.json").write_text('{"version":999}', encoding="utf-8")
    assert tools.events.plan_summary()["version"] == 1


def test_graph_events_terminal_status_from_real_node_result(tmp_path, monkeypatch):
    tools, plan = ready(tmp_path, monkeypatch)
    wrapped = tools.events.node(
        "report", lambda state: {"status": "failed", "message": "not accepted"}
    )
    wrapped({})
    view = tools.events.view()
    assert view["status"] == "failed" and view["events"][-1]["stage"] == "result"


def test_legacy_has_no_events_or_new_prompt_effects(tmp_path, monkeypatch):
    tools = make_tools(tmp_path, monkeypatch, "legacy_v13")
    captured = capture_builder(tools, monkeypatch)
    assert tools.events is None and tools.control_store is None
    assert "profile_data" not in captured["system_prompt"]
    assert "commit_plan" not in captured["system_prompt"]


def test_events_api_auth_workspace_and_incremental_reads(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_ANALYSIS_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("AGENT_KNOWLEDGE_PROFILE", "method_graph_gated")
    monkeypatch.setattr(api, "ACCESS_TOKEN", "fixture-gateway")
    workspace = tmp_path / "alice/output"
    workspace.mkdir(parents=True)
    (workspace.parent / ".auth.json").write_text(
        json.dumps({"salt": "fixture-salt"}), encoding="utf-8"
    )
    token = api.sign_user_token("alice", "fixture-salt")
    conv = "synthetic-conversation"
    conv_hash = agent._digest("alice\x00" + conv)
    root = (
        tmp_path
        / "state"
        / agent._digest("alice")
        / (conv_hash + ".budget.controls")
        / ("a" * 32)
    )
    store = store_module.ControlStore(root, [workspace])
    store.create(
        "context.json",
        {
            "run_id": "a" * 32,
            "knowledge_profile": "method_graph_gated",
            "workspace_sha256": agent._digest(str(workspace.resolve())),
            "started_time": 1,
        },
    )
    log = events.AnalysisEvents(store)
    log.append("data", "done", "Read synthetic data")
    log.append(
        "constraints",
        "blocked",
        "MATLAB unavailable",
        {
            "reason": "Required command missing",
            "next_steps": ["Choose a feasible method"],
        },
    )
    url = f"/api/agent/analysis/{conv}/events"
    params = {"userId": "alice", "workspaceDirectory": str(workspace), "after": 1}
    headers = {"Authorization": "Bearer fixture-gateway", "X-User-Token": token}
    with TestClient(api.build_app()) as client:
        assert client.get(url, params=params).status_code == 401
        assert (
            client.get(
                url, params=params, headers={"Authorization": "Bearer fixture-gateway"}
            ).status_code
            == 401
        )
        response = client.get(url, params=params, headers=headers)
        assert response.status_code == 200
        assert [row["seq"] for row in response.json()["events"]] == [2]
        assert "X-User-Token" in response.headers
        assert (
            client.get(url, params={**params, "after": -1}, headers=headers).status_code
            == 400
        )
        other = tmp_path / "elsewhere/alice/output"
        other.mkdir(parents=True)
        (other.parent / ".auth.json").write_text(
            json.dumps({"salt": "fixture-salt"}), encoding="utf-8"
        )
        isolated = client.get(
            url, params={**params, "workspaceDirectory": str(other)}, headers=headers
        )
        assert isolated.status_code == 200 and isolated.json()["events"] == []


def test_legacy_capabilities_disable_panel_without_state_creation(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("AGENT_KNOWLEDGE_PROFILE", "legacy_v13")
    monkeypatch.setenv("AGENT_ANALYSIS_STATE_DIR", str(tmp_path / "absent"))
    monkeypatch.setattr(api, "ACCESS_TOKEN", "")
    with TestClient(api.build_app()) as client:
        assert client.get("/api/agent/analysis/process-capabilities").json() == {
            "enabled": False
        }
    assert not (tmp_path / "absent").exists()


def test_disabled_tool_attempt_is_logged_without_running_handler(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_ANALYSIS_STATE_DIR", str(tmp_path / "state"))
    tools = make_tools(tmp_path, monkeypatch, "method_graph_gated")
    captured = capture_builder(tools, monkeypatch)
    calls = []
    response = captured["middleware"][-1].wrap_tool_call(
        SimpleNamespace(tool_call={"name": "execute", "id": "fixture", "args": {}}),
        lambda request: calls.append(request),
    )
    assert response.status == "error" and calls == []
    assert tools.events.all()[-1]["status"] == "failed"
    assert tools.events.all()[-1]["detail"]["tool"] == "execute"


@pytest.mark.parametrize(
    "name,args,result,expected",
    [
        (
            "profile_data",
            {"paths": ["/inputs/0/lh.pial"]},
            {"status": "ok"},
            "Built data profile: 1 file",
        ),
        (
            "compile_constraints",
            {},
            {"summary": {"pass": 2, "warn": 1, "block": 1}},
            "Checks: 2 pass / 1 warn / 1 block",
        ),
        ("commit_plan", {}, {"status": "committed", "version": 1}, "Plan sealed v1"),
        ("commit_plan", {}, {"status": "blocked"}, "Plan blocked: hard checks failed"),
        ("run_python", {"path": "/work/lgi.py"}, None, "Running lgi.py"),
    ],
)
def test_english_titles_match_actual_tool_results(name, args, result, expected):
    title = events.title_for(name, args, result)
    assert title == expected and title.isascii() and len(title) <= 40


def test_event_explanations_are_english_bounded_and_do_not_mutate_receipts(tmp_path):
    store = store_module.ControlStore(tmp_path / "protected", [tmp_path / "work"])
    log = events.AnalysisEvents(store)
    original = {
        "reason": "A required scientific software prerequisite was not observed in the container",
        "next_steps": [
            "换用满足现有条件的方法",
            "补充缺失数据或软件后重新检查",
            "终止分析并报告缺失前提",
        ],
        "constraints_sha256": "a" * 64,
        "path": "/work/" + "x" * 60,
    }
    row = log.append("plan", "blocked", "Plan blocked: hard checks failed", original)
    assert original["next_steps"][0] == "换用满足现有条件的方法"
    assert len(original["reason"]) > 40
    display = row["detail"]
    assert display["constraints_sha256"] == original["constraints_sha256"]
    assert display["path"] == original["path"]
    assert all(
        item.isascii() and len(item) <= 40
        for item in [display["reason"], *display["next_steps"]]
    )
    assert display["next_steps"] == [
        "Choose a feasible method",
        "Add prerequisites and recheck",
        "Stop and report missing prerequisites",
    ]


@pytest.mark.parametrize(
    "name",
    [
        *sorted(events.DATA_TOOLS),
        *sorted(events.KNOWLEDGE_TOOLS),
        "write_code",
        "run_python",
        "submit_pipeline",
        "pipeline_status",
        "finalize_artifacts",
    ],
)
def test_generated_titles_are_english_and_bounded(name):
    title = events.title_for(
        name, {"path": "/work/" + "a" * 100, "query": "方法适用条件"}
    )
    assert title.isascii() and len(title) <= 40


def test_missing_software_explanation_comes_from_probe_result(tmp_path):
    store = store_module.ControlStore(tmp_path / "protected", [tmp_path / "work"])
    log = events.AnalysisEvents(store)
    payload = {
        "status": "blocked",
        "reason": "Hard constraints are not all pass",
        "blocked_constraints": [
            {
                "constraint_id": "software_available",
                "verdict": "block",
                "tool_observed": {
                    "commands": [{"command": "matlab", "executable": False}]
                },
            }
        ],
    }
    returned = log.call_tool("commit_plan", {}, lambda: payload)
    assert (
        returned is payload
        and returned["reason"] == "Hard constraints are not all pass"
    )
    row = log.all()[-1]
    assert row["detail"]["reason"] == "Missing software: MATLAB"
    assert row["title"] == "Plan blocked: hard checks failed"
