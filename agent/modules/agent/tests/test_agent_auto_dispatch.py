"""Authenticated auto dispatch and shared event/history integration, without real APIs."""

import copy
import importlib
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from modules.agent.backend import api
from modules.agent.backend.agent_chat_state import ChatSession, conversation_events
from modules.agent.backend.analysis_control_store import ControlStore
from modules.agent.backend.analysis_events import AnalysisEvents
from test_agent_router import response


@pytest.fixture
def setup_api(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_ANALYSIS_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("AGENT_KNOWLEDGE_PROFILE", "legacy_v13")
    monkeypatch.setenv("AGENT_DATA_ROOTS", "")
    monkeypatch.setenv("AGENT_DATA_DIRECTORY", "")
    monkeypatch.setattr(api, "ACCESS_TOKEN", "")
    monkeypatch.setattr(api, "list_generated_scripts", lambda *args: [])
    work = tmp_path / "alice/output"
    work.mkdir(parents=True)
    (work.parent / ".auth.json").write_text(json.dumps({"salt": "fixture-salt"}))
    identity = api.sign_user_token("alice", "fixture-salt")
    payload = {
        "message": "Inspect existing reconstructed outputs",
        "mode": "auto",
        "provider": "custom",
        "model": "offline",
        "apiKey": "fixture-private-value",
        "conversationId": "shared-conversation",
        "context": {
            "userId": "alice",
            "workspaceDirectory": str(work),
            "userToken": identity,
        },
    }
    calls = []
    choices = ["analysis"]
    pipeline_replies = []

    async def provider(*args, **kwargs):
        calls.append((copy.deepcopy(args), copy.deepcopy(kwargs)))
        if kwargs.get("response_format"):
            choice = choices.pop(0)
            if isinstance(choice, Exception):
                raise choice
            if isinstance(choice, dict):
                return choice
            return response(choice, "Choose the requested workflow.")
        if pipeline_replies:
            return pipeline_replies.pop(0)
        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "Preprocessing request inspected.",
                    }
                }
            ],
            "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
        }

    monkeypatch.setattr(api, "call_chat_completions", provider)
    analysis = importlib.import_module(api.__package__ + ".analysis_agent")
    runner = AsyncMock(
        return_value={
            "message": "Analysis response.",
            "status": "completed",
            "run_id": "a" * 32,
            "model_calls": 3,
            "metadata": {},
        }
    )
    monkeypatch.setattr(analysis, "run_analysis", runner)
    with TestClient(api.build_app()) as client:
        yield client, payload, choices, pipeline_replies, calls, runner, identity, work


def get_events(client, payload, identity, after=0):
    return client.get(
        f"/api/agent/analysis/{payload['conversationId']}/events",
        params={
            "userId": "alice",
            "workspaceDirectory": payload["context"]["workspaceDirectory"],
            "after": after,
        },
        headers={"X-User-Token": identity},
    )


@pytest.mark.parametrize("route", ["pipeline", "analysis"])
def test_auto_routes_metadata_and_legacy_events_are_actual(setup_api, route):
    client, payload, choices, _, calls, runner, identity, work = setup_api
    choices[:] = [route]
    result = client.post("/api/agent/chat", json=payload)
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["conversationId"] == payload["conversationId"]
    assert body["metadata"]["route"] == route and body["metadata"]["routeReason"]
    assert body["metadata"]["routing"]["modelCalls"] == 1
    assert body["metadata"]["requestBudget"]["router_calls"] == 1
    assert len([row for row in calls if row[1].get("response_format")]) == 1
    view = get_events(client, payload, identity).json()
    assert view["enabled"] is True
    expected = (
        "Routed to analysis" if route == "analysis" else "Routed to preprocessing"
    )
    assert (
        view["events"][0]["title"] == expected and view["events"][0]["stage"] == "other"
    )
    assert "fixture-private-value" not in json.dumps(view)
    if route == "analysis":
        assert body["metadata"]["mode"] == "analysis"
        assert runner.call_args.kwargs["router_model_calls"] == 1
        assert (
            len(view["events"]) == 1
        )  # Legacy analysis adds no analysis-control events.
        assert body["metadata"]["requestBudget"]["unknown_usage_calls"] == 2


def test_cross_route_turns_share_id_and_server_history(setup_api):
    client, payload, choices, _, calls, runner, identity, _ = setup_api
    choices[:] = ["pipeline", "analysis", "pipeline"]
    first = client.post(
        "/api/agent/chat", json={**payload, "message": "Preprocess the uploaded T1"}
    )
    second = client.post(
        "/api/agent/chat", json={**payload, "message": "Measure those existing outputs"}
    )
    assert first.status_code == second.status_code == 200
    history = runner.call_args.kwargs["conversation_history"]
    assert history[0]["content"] == "Preprocess the uploaded T1"
    assert history[1]["content"] == "Preprocessing request inspected."
    third = client.post(
        "/api/agent/chat",
        json={**payload, "message": "Check the preprocessing task again"},
    )
    assert third.status_code == 200
    pipeline_messages = calls[-1][0][3]
    assert any(row.get("content") == "Analysis response." for row in pipeline_messages)
    assert all(
        r.json()["conversationId"] == payload["conversationId"]
        for r in (first, second, third)
    )
    view = get_events(client, payload, identity).json()
    assert [row["seq"] for row in view["events"]] == list(
        range(1, len(view["events"]) + 1)
    )
    assert len([row for row in view["events"] if row["stage"] == "other"]) == 3


def test_pipeline_tools_and_skill_disclosure_have_paired_events(setup_api, monkeypatch):
    client, payload, choices, replies, calls, runner, identity, _ = setup_api
    choices[:] = ["pipeline"]
    replies[:] = [
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "id": "discover",
                                "type": "function",
                                "function": {
                                    "name": "discover_subjects",
                                    "arguments": "{}",
                                },
                            }
                        ],
                    }
                }
            ]
        },
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "Synthetic discovery finished.",
                    }
                }
            ]
        },
    ]
    observed = []
    monkeypatch.setattr(
        api,
        "invoke_tool",
        lambda *args: observed.append(args[2]) or {"status": "ok", "subjects": []},
    )
    result = client.post("/api/agent/chat", json=payload)
    assert result.status_code == 200 and observed == ["discover_subjects"]
    assert result.json()["metadata"]["llmIterations"] == 3
    assert result.json()["metadata"]["requestBudget"]["model_calls"] == 3
    view = get_events(client, payload, identity).json()
    rows = [
        row
        for row in view["events"]
        if row["detail"].get("tool") == "discover_subjects"
    ]
    assert [row["status"] for row in rows] == ["running", "done"]
    assert rows[0]["detail"]["operation_id"] == rows[1]["detail"]["operation_id"]
    assert all(
        row["title"].isascii() and len(row["title"]) <= 40 for row in view["events"]
    )


@pytest.mark.parametrize("mode", ["pipeline", "analysis"])
def test_explicit_modes_do_not_call_router(setup_api, mode):
    client, payload, choices, _, calls, runner, identity, _ = setup_api
    result = client.post("/api/agent/chat", json={**payload, "mode": mode})
    assert result.status_code == 200
    assert not [row for row in calls if row[1].get("response_format")]
    assert result.json()["metadata"]["route"] == mode
    assert choices == ["analysis"]
    if mode == "analysis":
        assert "router_model_calls" not in runner.call_args.kwargs
        assert "conversation_history" not in runner.call_args.kwargs
        assert get_events(client, payload, identity).json()["enabled"] is False


def test_direct_analysis_bypasses_auto_even_if_payload_mode_auto(setup_api):
    client, payload, choices, _, calls, runner, identity, _ = setup_api
    result = client.post("/api/agent/analysis", json=payload)
    assert result.status_code == 200
    assert not calls and choices == ["analysis"]
    assert "router_model_calls" not in runner.call_args.kwargs


def test_auth_is_checked_before_paid_routing(setup_api):
    client, payload, _, _, calls, runner, identity, _ = setup_api
    payload["context"]["userToken"] = "invalid-fixture"
    assert client.post("/api/agent/chat", json=payload).status_code == 401
    assert not calls and runner.call_count == 0


def test_failed_route_does_not_reuse_protected_last_route(setup_api):
    client, payload, choices, _, calls, runner, identity, _ = setup_api
    choices[:] = ["analysis", {"choices": [{"message": {"content": "invalid"}}]}, {"choices": [{"message": {"content": "invalid"}}]}]
    assert client.post("/api/agent/chat", json=payload).status_code == 200
    result = client.post("/api/agent/chat", json=payload)
    assert result.status_code == 200
    assert result.json()["metadata"]["route"] is None
    assert result.json()["metadata"]["routing"]["parseStatus"] == "route_failed"
    assert result.json()["metadata"]["requestBudget"]["model_calls"] == 2
    assert runner.call_count == 1


def test_conversation_owner_and_workspace_are_isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_ANALYSIS_STATE_DIR", str(tmp_path / "state"))
    a = tmp_path / "a/alice/output"
    a.mkdir(parents=True)
    b = tmp_path / "b/alice/output"
    b.mkdir(parents=True)
    s = ChatSession(a, "alice", "same-id", "", 64)
    s.start("analysis", "Inspect outputs.", True)
    other = ChatSession(b, "alice", "same-id", "", 64)
    assert other.prior_route() is None
    assert conversation_events(b, "alice", "same-id", 0) is None


def test_controlled_analysis_events_mirror_to_same_monotonic_stream(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("AGENT_ANALYSIS_STATE_DIR", str(tmp_path / "state"))
    work = tmp_path / "alice/output"
    work.mkdir(parents=True)
    s = ChatSession(work, "alice", "same-id", "", 64)
    s.start("analysis", "Inspect output geometry.", True)
    native_root = s.store.root.parent / ("a" * 32 + ".budget.controls") / ("b" * 32)
    native = ControlStore(native_root, [work])
    context = {
        "workspace_sha256": __import__("hashlib")
        .sha256(str(work.resolve()).encode())
        .hexdigest()[:32],
        "knowledge_profile": "method_graph",
        "run_id": "b" * 32,
    }
    native.create("context.json", context)
    with s.activate():
        AnalysisEvents(native).call_tool(
            "write_code", {"path": "/work/fixture.py"}, lambda: {"status": "ok"}
        )
    view = conversation_events(work, "alice", "same-id", 0)
    assert len(view["events"]) == 3 and view["events"][0]["stage"] == "other"
    assert view["run_id"] == "b" * 32 and view["knowledge_profile"] == "method_graph"
    assert len(AnalysisEvents(native).all()) == 2
    assert len(conversation_events(work, "alice", "same-id", 1)["events"]) == 2


def test_skill_load_defers_actions_and_records_real_pipeline_tool_outcomes(
    setup_api, monkeypatch
):
    client, payload, choices, replies, calls, runner, identity, _ = setup_api
    choices[:] = ["pipeline"]

    def tool(name, args, call_id):
        return {
            "id": call_id,
            "type": "function",
            "function": {"name": name, "arguments": json.dumps(args)},
        }

    args = {
        "subjectId": "sub-01",
        "workspaceDirectory": payload["context"]["workspaceDirectory"],
        "segSpecies": "rhesus",
    }
    replies[:] = [
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "tool_calls": [
                            tool("load-skill", {"skillName": "seg-brain"}, "load"),
                            tool("seg-brain", args, "deferred"),
                        ],
                    }
                }
            ]
        },
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "tool_calls": [tool("seg-brain", args, "actual")],
                    }
                }
            ]
        },
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "Synthetic task submission acknowledged.",
                    }
                }
            ]
        },
    ]
    executed = []
    monkeypatch.setattr(
        api,
        "execute_tool",
        lambda name, args, **kwargs: executed.append(name)
        or {"taskId": "fixture-task", "status": "pending"},
    )
    result = client.post("/api/agent/chat", json=payload)
    assert result.status_code == 200, result.text
    assert executed == ["seg-brain"]
    assert result.json()["metadata"]["llmIterations"] == 4
    assert result.json()["metadata"]["budgetedIterations"] == 3
    rows = get_events(client, payload, identity).json()["events"]
    loaded = [row for row in rows if row["detail"].get("tool") == "load-skill"]
    assert [row["status"] for row in loaded] == ["running", "done"]
    assert loaded[0]["detail"]["operation_id"] == loaded[1]["detail"]["operation_id"]
    actions = [row for row in rows if row["detail"].get("tool") == "seg-brain"]
    assert len(actions) == 4
    assert actions[1]["status"] == "warn" and actions[1]["detail"]["executed"] is False
    assert actions[1]["detail"]["reason"] == "Action deferred until skill review"
    assert actions[-1]["status"] == "done"
    assert actions[0]["detail"]["operation_id"] != actions[2]["detail"]["operation_id"]


def test_auto_conversation_turns_are_serialized(tmp_path, monkeypatch):
    import asyncio
    from modules.agent.backend.agent_chat_state import conversation_turn

    monkeypatch.setenv("AGENT_ANALYSIS_STATE_DIR", str(tmp_path / "state"))
    work = tmp_path / "alice/output"
    work.mkdir(parents=True)
    order = []

    async def one(label):
        async with conversation_turn(work, "alice", "shared"):
            order.append(label + ":start")
            await asyncio.sleep(0)
            order.append(label + ":end")

    async def both():
        await asyncio.gather(one("a"), one("b"))

    asyncio.run(both())
    assert order == ["a:start", "a:end", "b:start", "b:end"]


def test_new_explicit_analysis_is_not_hidden_by_previous_auto_timeline(
    tmp_path, monkeypatch
):
    import hashlib
    import time
    from modules.agent.backend.analysis_events import events_for_conversation

    monkeypatch.setenv("AGENT_ANALYSIS_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("AGENT_KNOWLEDGE_PROFILE", "method_graph")
    work = tmp_path / "alice/output"
    work.mkdir(parents=True)
    s = ChatSession(work, "alice", "same-id", "", 64)
    s.load_history([])
    s.start("pipeline", "List sample data.", True)
    s.complete("List sample data", "Listed data", "completed")
    digest = lambda text: hashlib.sha256(text.encode()).hexdigest()[:32]
    native_root = (
        s.store.root.parent
        / (digest("alice" + chr(0) + "same-id") + ".budget.controls")
        / ("b" * 32)
    )
    native = ControlStore(native_root, [work])
    native.create(
        "context.json",
        {
            "workspace_sha256": digest(str(work.resolve())),
            "knowledge_profile": "method_graph",
            "run_id": "b" * 32,
            "started_time": time.time() + 1,
        },
    )
    AnalysisEvents(native).append("data", "done", "Inspected explicit analysis data")
    view = events_for_conversation(work, "alice", "same-id")
    assert view["enabled"] is True and view["run_id"] == "b" * 32
    assert [row["title"] for row in view["events"]] == [
        "Inspected explicit analysis data"
    ]
