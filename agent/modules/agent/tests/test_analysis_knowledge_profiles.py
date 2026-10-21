"""Offline knowledge-profile exposure, byte compatibility and durable audit tests."""

import hashlib
import importlib
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from test_analysis_agent import agent, FakeKnowledge, TestOnlyExecutor

profiles = importlib.import_module(agent.__package__ + ".analysis_knowledge_profiles")
policy = importlib.import_module(agent.__package__ + ".analysis_policy")

LEGACY_TOOLS = (
    "search_method_knowledge", "search_knowledge", "read_knowledge",
    "search_software_graph", "read_software_graph", "search_research_knowledge",
    "read_research_knowledge", "search_analysis_methods", "read_analysis_method",
    "check_method_requirements",
)


def make_tools(tmp_path, monkeypatch, name="legacy_v13"):
    monkeypatch.setenv("AGENT_KNOWLEDGE_PROFILE", name)
    work = tmp_path / "work"
    data = tmp_path / "data"
    work.mkdir(exist_ok=True)
    data.mkdir(exist_ok=True)
    return agent.AnalysisTools(
        work, [data], TestOnlyExecutor(work, [data]), FakeKnowledge(),
    )


def capture_builder(tools, monkeypatch):
    import deepagents

    captured = {}

    class Built:
        def with_config(self, config):
            captured["config"] = config
            return self

    def create(**kwargs):
        captured.update(kwargs)
        return Built()

    monkeypatch.setattr(deepagents, "create_deep_agent", create)
    llm = MagicMock()
    agent._build_coding_agent(
        tools, model="offline", base_url="https://example.invalid/v1",
        api_key="offline-fixture", model_factory=lambda **kwargs: llm,
    )
    return captured




@pytest.mark.parametrize("name", ["", "unknown", "LEGACY_V13", "../legacy_v13"])
def test_unknown_names_fail_before_model_construction(name, tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="Unknown AGENT_KNOWLEDGE_PROFILE"):
        make_tools(tmp_path, monkeypatch, name)


def test_unknown_profile_rejects_application_startup(monkeypatch):
    from modules.agent.backend.api import build_app

    monkeypatch.setenv("AGENT_KNOWLEDGE_PROFILE", "missing-group")
    with pytest.raises(ValueError, match="Unknown AGENT_KNOWLEDGE_PROFILE"):
        build_app()




@pytest.mark.parametrize(
    "name,rules",
    [("no_knowledge", False), ("text_retrieval", False),
     ("text_plus_rules", True), ("method_graph", True)],
)
def test_domain_rules_and_disabled_legacy_names(name, rules, tmp_path, monkeypatch):
    tools = make_tools(tmp_path, monkeypatch, name)
    captured = capture_builder(tools, monkeypatch)
    prompt = captured["system_prompt"]
    assert ("Never infer species from a filename." in prompt) is rules
    for disabled in tools.knowledge_profile.all_knowledge_tools - set(
        tools.knowledge_profile.exposed_tools
    ):
        assert disabled not in prompt
    assert tools.knowledge_metadata["include_domain_rules"] is rules


@pytest.mark.parametrize("background", ["0", "1"])
def test_same_nonknowledge_tools_across_all_groups(background, tmp_path, monkeypatch):
    monkeypatch.setenv("ANALYSIS_ENABLE_BACKGROUND_JOBS", background)
    common = None
    for name in profiles.PROFILE_NAMES:
        directory = tmp_path / name
        directory.mkdir()
        tools = make_tools(directory, monkeypatch, name)
        captured = capture_builder(tools, monkeypatch)
        exposed = [tool.name for tool in captured["tools"]]
        knowledge = set(exposed) & tools.knowledge_profile.all_knowledge_tools
        assert knowledge == set(tools.knowledge_profile.exposed_tools)
        nonknowledge = [
            item for item in exposed if item not in tools.knowledge_profile.all_knowledge_tools
            and item not in {"profile_data", "compile_constraints", "commit_plan"}
        ]
        if common is None:
            common = nonknowledge
        assert common == nonknowledge
        assert ("submit_python_job" in exposed) is (background == "1")


@pytest.mark.parametrize("name", sorted(profiles.PROFILE_NAMES))
def test_middleware_allows_exactly_the_exposed_registry(name, tmp_path, monkeypatch):
    tools = make_tools(tmp_path, monkeypatch, name)
    captured = capture_builder(tools, monkeypatch)
    middleware = captured["middleware"][-1]
    actual = {tool.name for tool in captured["tools"]}
    names = actual | tools.knowledge_profile.all_knowledge_tools | {"task", "execute", "write_file"}
    for tool_name in names:
        calls = []

        def handler(request):
            calls.append(request)
            return object()

        response = middleware.wrap_tool_call(
            SimpleNamespace(tool_call={"name": tool_name, "id": "fixture", "args": {}}),
            handler,
        )
        assert bool(calls) is (tool_name in actual)
        if tool_name not in actual:
            assert response.status == "error"


def test_profile_is_frozen_for_the_tools_instance(tmp_path, monkeypatch):
    tools = make_tools(tmp_path, monkeypatch, "legacy_v13")
    monkeypatch.setenv("AGENT_KNOWLEDGE_PROFILE", "no_knowledge")
    captured = capture_builder(tools, monkeypatch)
    assert "read_knowledge" in [tool.name for tool in captured["tools"]]
    assert tools.knowledge_metadata["knowledge_profile"] == "legacy_v13"


def test_ledger_pins_metadata_without_resetting_attempts(tmp_path):
    ledger = agent.BudgetLedger(tmp_path / "budget.sqlite3", "fixture-run")
    metadata = {
        "knowledge_profile": "legacy_v13", "exposed_tools": ["ls"],
        "prompt_sha256": "a" * 64,
    }
    ledger.reserve("tool_calls", 5)
    before = ledger.snapshot()
    ledger.bind_knowledge_metadata(metadata)
    ledger.bind_knowledge_metadata(metadata)
    assert ledger.snapshot() == before
    with pytest.raises(ValueError, match="original knowledge configuration"):
        ledger.bind_knowledge_metadata({**metadata, "knowledge_profile": "no_knowledge"})
    assert ledger.snapshot() == before


def test_run_checkpoint_ledger_response_and_resume_profile(tmp_path, monkeypatch):
    import deepagents

    monkeypatch.setenv("AGENT_KNOWLEDGE_PROFILE", "no_knowledge")
    monkeypatch.setenv("AGENT_ANALYSIS_STATE_DIR", str(tmp_path / "state"))
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    data = tmp_path / "data"
    data.mkdir()

    class Inspector:
        def __init__(self, structured):
            self.structured = structured

        def with_config(self, config):
            return self

        def invoke(self, payload, config):
            self.structured["list_roots"].func()
            return {"messages": [{"content": "Inspected the actual registered fixture directory."}]}

    monkeypatch.setattr(
        deepagents, "create_deep_agent",
        lambda **kwargs: Inspector({tool.name: tool for tool in kwargs["tools"]}),
    )
    llm = MagicMock()
    arguments = dict(
        message="Inspect registered fixture directories", user_id="offline-user",
        workspace=workspace, conversation_id="profile-fixture", model="offline",
        base_url="https://example.invalid/v1", api_key="offline-fixture",
        input_roots=[data], resume=False, model_factory=lambda **kwargs: llm,
        execution_required=False,
    )
    result = agent._run_sync(**arguments)
    assert result["status"] == "inspected"
    metadata = result["metadata"]
    assert metadata["knowledge_profile"] == "no_knowledge"
    assert not set(metadata["exposed_tools"]) & profiles.load_knowledge_profile().all_knowledge_tools
    assert len(metadata["prompt_sha256"]) == 64
    database = next((tmp_path / "state").rglob("*.budget.sqlite3"))
    with sqlite3.connect(database) as connection:
        encoded = connection.execute(
            "SELECT knowledge_json FROM run_metadata WHERE run_id=?", (result["run_id"],)
        ).fetchone()[0]
    assert json.loads(encoded) == metadata
    resumed = agent._run_sync(**{**arguments, "resume": True})
    assert resumed["metadata"] == metadata
    monkeypatch.setenv("AGENT_KNOWLEDGE_PROFILE", "text_retrieval")
    with pytest.raises(ValueError, match="original knowledge profile"):
        agent._run_sync(**{**arguments, "resume": True})


def test_malformed_profile_manifest_fails_closed(tmp_path, monkeypatch):
    monkeypatch.delenv("AGENT_KNOWLEDGE_PROFILE", raising=False)
    path = tmp_path / "profiles.json"
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="registered experiment groups"):
        profiles.load_knowledge_profile(path)



@pytest.mark.parametrize("name", ["no_knowledge", "text_retrieval", "text_plus_rules"])
def test_internal_reviewer_cannot_reload_hidden_method_graph(name, tmp_path, monkeypatch):
    from langgraph.checkpoint.memory import InMemorySaver
    from test_analysis_internal_review_graph import setup

    monkeypatch.setenv("AGENT_KNOWLEDGE_PROFILE", name)
    tools, coder = setup(tmp_path)
    tools._internal_review_model = object()
    module = importlib.import_module(agent.__package__ + ".analysis_internal_review")
    seen = []

    def forbidden():
        raise AssertionError("A text/no-knowledge group cannot reload method evidence")

    monkeypatch.setattr(tools, "_method_graph", forbidden)

    def review(*args, **kwargs):
        seen.append(kwargs["method_reader"])
        return {"decision": "pass", "protocol_valid": True, "findings": [], "limitations": []}

    monkeypatch.setattr(module, "run_review", review)
    validator = importlib.import_module(agent.__package__ + ".analysis_validation").ArtifactValidator()
    graph = agent._build_graph(coder, tools, validator, InMemorySaver())
    result = graph.invoke(
        {"request": "Run the engineering fixture.", "history": [], "iterations": 0},
        {"configurable": {"thread_id": "profile-review-isolation"}},
    )
    assert result["status"] == "completed" and seen == [None]


def test_public_analysis_metadata_contains_the_effective_profile(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from modules.agent.backend import api
    from unittest.mock import AsyncMock, patch

    monkeypatch.setenv("AGENT_KNOWLEDGE_PROFILE", "no_knowledge")
    monkeypatch.setattr(api, "ACCESS_TOKEN", "")
    monkeypatch.setattr(api, "_read_auth_record", lambda *args: {"salt": "fixture-salt"})
    monkeypatch.setattr(api, "verify_user_token", lambda *args: True)
    monkeypatch.setattr(api, "sign_user_token", lambda *args: "fixture-identity")
    workspace = tmp_path / "offline-user" / "output"
    workspace.mkdir(parents=True)
    metadata = {
        "knowledge_profile": "no_knowledge", "exposed_tools": ["list_roots"],
        "prompt_sha256": "a" * 64,
    }
    with patch("modules.agent.backend.analysis_agent.run_analysis", new_callable=AsyncMock) as run:
        run.return_value = {"message": "Inspected", "status": "inspected", "metadata": metadata}
        with TestClient(api.build_app()) as client:
            response = client.post("/api/agent/analysis", json={
                "message": "Inspect", "mode": "analysis", "provider": "custom",
                "model": "offline", "apiKey": "offline-fixture",
                "context": {"userId": "offline-user", "workspaceDirectory": str(workspace),
                            "userToken": "fixture-identity"},
            })
    assert response.status_code == 200
    actual = response.json()["metadata"]
    assert actual["knowledge_profile"] == "no_knowledge"
    assert actual["prompt_sha256"] == metadata["prompt_sha256"]
    assert actual["exposed_tools"] == ["list_roots"]
    assert "metadata" not in actual



@pytest.mark.parametrize(
    "name",
    [
        "no_knowledge",
        "text_retrieval",
        "text_plus_rules",
        "method_graph",
        "method_graph_gated",
    ],
)
def test_reviewed_sentence_boundaries_are_fair_across_ablations(
    name, tmp_path, monkeypatch
):
    tools = make_tools(tmp_path, monkeypatch, name)
    prompt = capture_builder(tools, monkeypatch)["system_prompt"]
    assert "Inspect the actual approved data before choosing methods." in prompt
    assert "Select a feasible method or report the missing prerequisite." in prompt
    assert (
        "Include actual self-checks of row identities, coverage and finite values."
        in prompt
    )
    include_domain = tools.knowledge_profile.include_domain_rules
    has_knowledge = bool(tools.knowledge_profile.exposed_tools)
    assert (
        "Retrieve relevant official knowledge before choosing methods." in prompt
    ) is (include_domain and has_knowledge)
    assert (
        "Check units, coordinate space and conservation/invariance appropriate to the chosen method."
        in prompt
    ) is include_domain
    for identifier in (27, 31, 44):
        original = next(
            text for i, _, text in policy._POLICY_SENTENCES if i == identifier
        )
        assert original.strip() in prompt
    assert (
        "Inspect the actual approved data and retrieve relevant official knowledge before choosing methods."
        not in prompt
    )


def test_knowledge_instruction_requires_exposed_tools_even_with_rules(monkeypatch):
    from dataclasses import replace

    monkeypatch.setenv("AGENT_KNOWLEDGE_PROFILE", "no_knowledge")
    profile = replace(profiles.load_knowledge_profile(), include_domain_rules=True)
    prompt = policy.build_system_prompt(profile, {}, {})
    assert "Retrieve relevant official knowledge before choosing methods." not in prompt
    assert "Inspect the actual approved data before choosing methods." in prompt
