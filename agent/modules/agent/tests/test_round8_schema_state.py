"""Real Deep Agents tool-node validation without model HTTP or image operations."""

import json
import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import PrivateAttr
from test_analysis_agent import agent
from test_analysis_knowledge_profiles import make_tools


@pytest.mark.parametrize("profile", ["product_graph_planner", "legacy_v13"])
def test_schema_error_has_state_and_budget_only_in_product_profile(
    tmp_path, monkeypatch, profile
):
    monkeypatch.setenv("AGENT_ANALYSIS_STATE_DIR", str(tmp_path / "state"))
    tools = make_tools(tmp_path, monkeypatch, profile)
    if profile == "product_graph_planner":
        # Reflection is now available only after an actual failed phase. Keep
        # the schema/state assertions in that permitted engineering fixture.
        tools.session._save("executed_failed", "Exercise malformed reflection")
    seen = []

    class Scripted(BaseChatModel):
        _calls: int = PrivateAttr(default=0)

        @property
        def _llm_type(self):
            return "offline-schema-state-fixture"

        def bind_tools(self, tools, **kwargs):
            return self

        def get_num_tokens(self, text):
            return max(1, len(text) // 4)

        def get_num_tokens_from_messages(self, messages, tools=None):
            return sum(
                self.get_num_tokens(str(message.content)) for message in messages
            )

        def _generate(self, messages, **kwargs):
            self._calls += 1
            if self._calls == 1:
                reply = AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "id": "fixture-invalid-reflection",
                            "name": "record_analysis_reflection",
                            "args": {
                                "feedback_observation_id": "wrong parameter name",
                                "hypothesis": "synthetic hypothesis",
                                "next_check": "synthetic check",
                            },
                        }
                    ],
                )
            else:
                seen.extend(
                    message for message in messages if isinstance(message, ToolMessage)
                )
                reply = AIMessage(
                    content="Fixture finished without production execution."
                )
            return ChatResult(generations=[ChatGeneration(message=reply)])

    coder = agent._build_coding_agent(
        tools,
        model="fixture",
        base_url="https://example.invalid/v1",
        api_key="offline-fixture",
        model_factory=lambda **kwargs: Scripted(),
    )
    coder.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": "Exercise a malformed reflection; do not read data or execute analysis.",
                }
            ]
        }
    )
    assert len(seen) == 1 and seen[0].status == "error"
    if profile == "product_graph_planner":
        payload = json.loads(seen[0].content)
        assert (
            payload["status"] == "error"
            and payload["argument_validation_failed"] is True
        )
        assert "observation_id" in payload["error"]
        assert payload["state"]["phase"] == "executed_failed"
        assert (
            len(json.dumps(payload["state"], ensure_ascii=False, separators=(",", ":")))
            <= 400
        )
        assert tools.tool_calls == 1
    else:
        assert seen[0].content.startswith("Error invoking tool")
        assert tools.tool_calls == 0 and tools.session is None
    assert tools.executions == 0


def test_disallowed_tool_does_not_execute_and_keeps_state(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from test_analysis_knowledge_profiles import capture_builder

    monkeypatch.setenv("AGENT_ANALYSIS_STATE_DIR", str(tmp_path / "state"))
    tools = make_tools(tmp_path, monkeypatch, "product_graph_planner")
    captured = capture_builder(tools, monkeypatch)
    middleware = next(
        item
        for item in captured["middleware"]
        if type(item).__name__ == "BudgetMiddleware"
    )

    def forbidden(request):
        raise AssertionError("Disallowed tool handler must not run")

    response = middleware.wrap_tool_call(
        SimpleNamespace(
            tool_call={
                "name": "execute_host_shell",
                "id": "fixture-disabled",
                "args": {},
            }
        ),
        forbidden,
    )
    payload = json.loads(response.content)
    assert response.status == "error" and payload["state"]["phase"] == "unplanned"
    assert tools.tool_calls == 1 and tools.executions == 0
