"""Baseline byte and tool-order identity; no model calls or analysis execution."""

import hashlib
import importlib
import json
from pathlib import Path
from unittest.mock import MagicMock

from test_analysis_agent import agent, FakeKnowledge, TestOnlyExecutor

profiles = importlib.import_module(agent.__package__ + ".analysis_knowledge_profiles")


def test_unset_profile_is_legacy(monkeypatch):
    monkeypatch.delenv("AGENT_KNOWLEDGE_PROFILE", raising=False)
    profile = profiles.load_knowledge_profile()
    assert profile.name == "legacy_v13"
    assert profile.include_domain_rules is True
    assert len(profile.exposed_tools) == 10


def test_legacy_prompt_and_tool_order_are_byte_identical(tmp_path, monkeypatch):
    import deepagents

    monkeypatch.delenv("AGENT_KNOWLEDGE_PROFILE", raising=False)
    work = tmp_path / "work"
    work.mkdir()
    tools = agent.AnalysisTools(work, [], TestOnlyExecutor(work, []), FakeKnowledge())
    captured = {}

    class Built:
        def with_config(self, config):
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
    fixtures = Path(__file__).parent / "fixtures"
    expected = (fixtures / "legacy_v13_prompt.txt").read_bytes()
    assert captured["system_prompt"].encode("utf-8") == expected
    assert tools.knowledge_metadata["prompt_sha256"] == hashlib.sha256(expected).hexdigest()
    names = json.loads((fixtures / "legacy_v13_tool_names.json").read_text())
    if __import__("os").environ.get("ANALYSIS_ENABLE_BACKGROUND_JOBS", "0") == "1":
        names.append("submit_python_job")
    assert [tool.name for tool in captured["tools"]] == names
