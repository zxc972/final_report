"""Real Deep Agents checkpoint resume must charge another model call."""

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.outputs import ChatResult, ChatGeneration
from langchain_core.messages import AIMessage
from pydantic import PrivateAttr
import pytest
from test_analysis_agent import agent, FakeKnowledge, TestOnlyExecutor


class FailOnce(BaseChatModel):
    _observed: list = PrivateAttr(default_factory=list)

    @property
    def _llm_type(self):
        return "offline-resume-reproducer"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, **kwargs):
        self._observed.append(len(messages))
        if len(self._observed) == 1:
            raise RuntimeError("Synthetic upstream failure; no HTTP")
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="Offline resumed response"))])


def test_checkpoint_resume_charges_model_node_again(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_KNOWLEDGE_PROFILE", "legacy_v13")
    monkeypatch.setenv("ANALYSIS_ENABLE_INTERNAL_REVIEW", "0")
    work, data = tmp_path / "work", tmp_path / "data"
    work.mkdir()
    data.mkdir()
    tools = agent.AnalysisTools(work, [data], TestOnlyExecutor(work, [data]), FakeKnowledge(), "fixture")
    model = FailOnce()
    graph = agent._build_coding_agent(tools, model="fake", base_url="https://example.invalid/v1", api_key="fixture", model_factory=lambda **kwargs: model)
    config = {"configurable": {"thread_id": "offline-resume-proof"}}
    with pytest.raises(RuntimeError, match="Synthetic upstream"):
        graph.invoke({"messages": [{"role": "user", "content": "Inspect synthetic metadata only."}]}, config)
    assert graph.get_state(config).next == ("model",)
    assert tools.model_calls == 1
    graph.invoke(None, config)
    assert len(model._observed) == tools.model_calls == 2


def test_direct_provider_logical_calls_share_phase_budget(tmp_path, monkeypatch):
    import importlib
    from types import SimpleNamespace
    from test_analysis_product_planner import setup_products
    tools = setup_products(tmp_path, monkeypatch)
    chat = importlib.import_module(agent.__package__ + ".agent_chat_state")
    session = SimpleNamespace(request_id="offline-budget-bridge", store=tools.control_store, analysis_tools=tools)
    budget = chat.RequestBudget(session, 30)
    first = budget.reserve("analysis", source_node="analysis.direct")
    assert tools.model_calls == 1
    budget.finish(first, None, "call_failed")
    retry = budget.reserve("analysis", retry_of=first, source_node="analysis.direct")
    budget.finish(retry, {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3}, "response_received")
    assert tools.model_calls == 1
    tools._tick(model=True)  # Normal coding wrapper already reserved this call.
    budget.reserve("analysis", source_node="coding.model")
    assert tools.model_calls == budget.view()["model_calls"] == 2
    assert tools.session.record["planning_model_calls"] == 2
    assert all(row["analysis_phase"] == "unplanned" for row in budget.records)
