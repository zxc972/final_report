"""True offline Deep Agents execution verifies the router debit and history bridge."""

import importlib
import json
import sqlite3
from pathlib import Path

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import PrivateAttr

from test_analysis_agent import agent, FakeKnowledge, TestOnlyExecutor, fixture_code


class OfflineModel(BaseChatModel):
    _calls: int = PrivateAttr(default=0)
    _seen: list = PrivateAttr(default_factory=list)

    @property
    def _llm_type(self):
        return "offline-router-budget-integration"

    def bind_tools(self, tools, **kwargs):
        return self

    def get_num_tokens(self, text):
        return max(1, len(text) // 4)

    def get_num_tokens_from_messages(self, messages, tools=None):
        return sum(self.get_num_tokens(str(message.content)) for message in messages)

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self._seen.append(messages)
        call = self._calls
        self._calls += 1
        if kwargs.get("response_format"):
            message = AIMessage(
                content=json.dumps(
                    {
                        "decision": "pass",
                        "findings": [],
                        "limitations": ["Offline fixture only"],
                    }
                )
            )
        elif call == 0:
            message = AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "list_roots",
                        "args": {},
                        "id": "inspect",
                        "type": "tool_call",
                    }
                ],
            )
        else:
            message = AIMessage(content="Inspected the actual synthetic workspace.")
        return ChatResult(generations=[ChatGeneration(message=message)])


def test_analysis_ledger_counts_router_before_coding_and_receives_pipeline_history(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("AGENT_KNOWLEDGE_PROFILE", "legacy_v13")
    monkeypatch.setenv("AGENT_ANALYSIS_STATE_DIR", str(tmp_path / "state"))
    work = tmp_path / "alice/output"
    work.mkdir(parents=True)
    model = OfflineModel()
    result = agent._run_sync(
        message="Inspect the prepared workspace",
        user_id="alice",
        workspace=work,
        conversation_id="shared-history-budget",
        model="offline",
        base_url="https://example.invalid/v1",
        api_key="fixture-private-value",
        input_roots=[],
        resume=False,
        model_factory=lambda **kwargs: model,
        execution_required=False,
        router_model_calls=1,
        conversation_history=[
            {"role": "user", "content": "Prepare raw T1"},
            {"role": "assistant", "content": "Preparation task was submitted."},
        ],
    )
    assert result["status"] == "inspected"
    assert result["model_calls"] == result["request_model_calls"] == 3
    assert model._calls == 2
    assert any(
        message.content == "Preparation task was submitted."
        for message in model._seen[0]
    )
    database = next((tmp_path / "state").rglob("*.budget.sqlite3"))
    with sqlite3.connect(database) as db:
        assert (
            db.execute(
                "SELECT model_calls FROM budgets WHERE run_id=?", (result["run_id"],)
            ).fetchone()[0]
            == 3
        )
    resumed = agent._run_sync(
        message="",
        user_id="alice",
        workspace=work,
        conversation_id="shared-history-budget",
        model="offline",
        base_url="https://example.invalid/v1",
        api_key="fixture-private-value",
        input_roots=[],
        resume=True,
        model_factory=lambda **kwargs: model,
        execution_required=False,
        router_model_calls=1,
    )
    assert resumed["model_calls"] == 4 and resumed["request_model_calls"] == 1
    assert model._calls == 2


def test_route_charge_cannot_be_ignored_at_model_limit(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_KNOWLEDGE_PROFILE", "legacy_v13")
    monkeypatch.setenv("AGENT_ANALYSIS_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setattr(agent, "MAX_MODEL_CALLS", 1)
    work = tmp_path / "alice/output"
    work.mkdir(parents=True)
    model = OfflineModel()
    result = agent._run_sync(
        message="Inspect workspace",
        user_id="alice",
        workspace=work,
        conversation_id="charged-limit",
        model="offline",
        base_url="https://example.invalid/v1",
        api_key="fixture-private-value",
        input_roots=[],
        resume=False,
        model_factory=lambda **kwargs: model,
        execution_required=False,
        router_model_calls=1,
    )
    assert result["status"] == "failed" and model._calls == 0
    assert result["model_calls"] == result["request_model_calls"] == 1


def test_real_api_analysis_events_survive_to_thread_with_fake_model(
    tmp_path, monkeypatch
):
    from fastapi.testclient import TestClient
    from modules.agent.backend import api
    from modules.agent.backend.analysis_events import events_for_conversation
    from test_agent_router import response

    monkeypatch.setenv("AGENT_KNOWLEDGE_PROFILE", "method_graph")
    monkeypatch.setenv("AGENT_ANALYSIS_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("AGENT_DATA_DIRECTORY", "")
    monkeypatch.setenv("AGENT_DATA_ROOTS", "")
    monkeypatch.setattr(api, "ACCESS_TOKEN", "")
    root = tmp_path / "alice/output"
    root.mkdir(parents=True)
    (root.parent / ".auth.json").write_text(json.dumps({"salt": "fixture-salt"}))
    identity = api.sign_user_token("alice", "fixture-salt")
    actual = importlib.import_module(api.__package__ + ".analysis_agent")
    executors = importlib.import_module(api.__package__ + ".analysis_executor")
    knowledge = importlib.import_module(api.__package__ + ".analysis_knowledge")

    class Coder(OfflineModel):
        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            if kwargs.get("response_format"):
                return ChatResult(
                    generations=[
                        ChatGeneration(
                            message=AIMessage(
                                content=json.dumps(
                                    {
                                        "decision": "pass",
                                        "findings": [],
                                        "limitations": [],
                                    }
                                )
                            )
                        )
                    ]
                )
            index = self._calls
            self._calls += 1
            actions = [
                ("write_code", {"path": "/work/analysis.py", "code": fixture_code()}),
                ("run_python", {"path": "/work/analysis.py"}),
            ]
            if index < 2:
                name, args = actions[index]
                msg = AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": name,
                            "args": args,
                            "id": f"offline-{index}",
                            "type": "tool_call",
                        }
                    ],
                )
            else:
                msg = AIMessage(content="Finished the standard-library fixture.")
            return ChatResult(generations=[ChatGeneration(message=msg)])

    async def router(*args, **kwargs):
        assert kwargs["temperature"] == 0
        return response("analysis")

    monkeypatch.setattr(api, "call_chat_completions", router)
    monkeypatch.setattr(actual, "_model_factory", lambda **kwargs: Coder())
    monkeypatch.setattr(executors, "SandboxExecutor", TestOnlyExecutor)
    monkeypatch.setattr(knowledge, "KnowledgeStore", FakeKnowledge)
    with TestClient(api.build_app()) as client:
        reply = client.post(
            "/api/agent/chat",
            json={
                "message": "Run the tiny standard-library fixture",
                "mode": "auto",
                "conversationId": "thread-propagation",
                "provider": "custom",
                "model": "offline",
                "apiKey": "fixture-private-value",
                "context": {
                    "userId": "alice",
                    "workspaceDirectory": str(root),
                    "userToken": identity,
                },
            },
        )
    assert reply.status_code == 200, reply.text
    meta = reply.json()["metadata"]
    assert (
        meta["status"] == "completed"
        and meta["model_calls"] == meta["request_model_calls"] == 5
    )
    assert meta["requestBudget"]["model_calls"] == 5
    assert meta["requestBudget"]["router_calls"] == 1
    assert meta["requestBudget"]["unknown_usage_calls"] == 4
    view = events_for_conversation(root, "alice", "thread-propagation")
    assert view["events"][0]["title"] == "Routed to analysis"
    run = [row for row in view["events"] if row["detail"].get("tool") == "run_python"]
    assert [row["status"] for row in run] == ["running", "done"]
    assert run[0]["detail"]["operation_id"] == run[1]["detail"]["operation_id"]
    assert view["run_id"] == meta["run_id"]
