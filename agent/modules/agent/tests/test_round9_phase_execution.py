"""Actual Deep Agents phase binding and metered transports; all fixtures offline."""

import importlib
import json
from pathlib import Path

import httpx
import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import PrivateAttr

from test_analysis_agent import agent
from test_round8_closure import sealed, fake_execution
from test_analysis_provider_compat import success, error

phase = importlib.import_module(agent.__package__ + ".analysis_phase_tools")
chat = importlib.import_module(agent.__package__ + ".agent_chat_state")
provider = importlib.import_module(agent.__package__ + ".analysis_provider")


def test_real_toolnode_four_tools_force_write_then_error_read_repair(
    tmp_path, monkeypatch
):
    tools, _, committed = sealed(tmp_path, monkeypatch)
    fake_execution(tools)
    good = tools.executor

    class FailOnce:
        def run(self, script, **kwargs):
            if tools.executions == 1:
                (tools.workdir / "stderr.log").write_text(
                    "Synthetic exception: first attempt"
                )
                return {
                    "status": "failed",
                    "exit_code": 1,
                    "stderr": "Synthetic exception",
                    "stdout": "",
                }
            return good.run(script, **kwargs)

    tools.executor = FailOnce()
    bindings = []

    class Model(BaseChatModel):
        _calls: int = PrivateAttr(default=0)

        @property
        def _llm_type(self):
            return "offline-phase-binding"

        def bind_tools(self, tools, **kwargs):
            return self.bind(
                exposed=[
                    t.name if not isinstance(t, dict) else t.get("name") for t in tools
                ],
                choice=kwargs.get("tool_choice"),
            )

        def get_num_tokens(self, text):
            return max(1, len(text) // 4)

        def get_num_tokens_from_messages(self, messages, tools=None):
            return sum(self.get_num_tokens(str(m.content)) for m in messages)

        def _generate(self, messages, **kwargs):
            i = self._calls
            self._calls += 1
            bindings.append(kwargs)
            if i == 0:
                assert set(kwargs["exposed"]) == set(phase.SEALED_TOOLS)
                assert kwargs['choice'] is None  # The sealed guide is readable before code is written.
                assert tools.resolve('/work/INPUTS.md').is_file()
            if i == 2:
                assert set(kwargs["exposed"]) == set(phase.FAILED_TOOLS)
            sequence = [
                (
                    "write_code",
                    {"path": "/work/analysis.py", "code": "print('fixture')"},
                ),
                ("run_python", {}),
                ("read_file", {"path": "/work/stderr.log"}),
                (
                    "write_code",
                    {"path": "/work/analysis.py", "code": "print('repaired fixture')"},
                ),
                ("run_python", {}),
            ]
            if i >= len(sequence):
                return ChatResult(
                    generations=[
                        ChatGeneration(message=AIMessage(content="Fixture complete."))
                    ]
                )
            name, args = sequence[i]
            return ChatResult(
                generations=[
                    ChatGeneration(
                        message=AIMessage(
                            content="",
                            tool_calls=[
                                {"id": f"phase-{i}", "name": name, "args": args}
                            ],
                        )
                    )
                ]
            )

    coder = agent._build_coding_agent(
        tools,
        model="fixture",
        base_url="https://example.invalid/v1",
        api_key="fixture",
        model_factory=lambda **kw: Model(),
    )
    coder.invoke(
        {
            "messages": [
                {"role": "user", "content": "Exercise the synthetic phase loop."}
            ]
        }
    )
    assert tools.executions == 2
    assert tools.session.state()["phase"] == "finalized"
    assert tools.session.record["automatic_finalizations"] == 1
    assert bindings[1]["choice"] is None
    rows = tools.events.all()
    assert any(r["title"] == "Plan sealed: writing analysis code" for r in rows)
    assert any(
        set(r["detail"].get("available_tools", [])) == set(phase.SEALED_TOOLS)
        for r in rows
    )


@pytest.mark.parametrize(
    "path,allowed",
    [
        ("/inputs/0/a.log", False),
        ("/work/../a.log", False),
        ("/work/summary.csv", False),
        ("/work/tool_results/a.json", True),
        ("/work/stderr.log", True),
        ("/work/analysis.py", False),
    ],
)
def test_failed_reads_are_work_error_only(tmp_path, monkeypatch, path, allowed):
    tools, _, _ = sealed(tmp_path, monkeypatch)
    try:
        actual = phase.read_error_allowed(tools, {"path": path})
    except ValueError:
        actual = False
    assert actual is allowed


def test_execution_card_is_small_complete_and_exact_return_fields(
    tmp_path, monkeypatch
):
    tools, _, committed = sealed(tmp_path, monkeypatch)
    response = tools.model_context.offload("commit_plan", committed)
    card = response["execution_card"]
    assert len(card) <= 1500
    guide=tools.resolve('/work/INPUTS.md').read_text()
    assert '/work/INPUTS.md' in card
    assert (
        "label_key/name/vertex_count/mean/std_population/median/zero_count/weight_sum"
        in guide
    )
    for path in committed["execution_bundle"]["input_paths"]:
        assert path in json.dumps(committed['execution_bundle'])
    assert "execution_bundle.v000001.json" in card
    assert "plan" not in response and "next_read" not in response


def test_http_usage_with_failed_attempt_matches_native_budget(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_ANALYSIS_STATE_DIR", str(tmp_path / "protected"))
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    session = chat.ChatSession(workspace, "fixture", "usage-fixture", "", 30)
    router = session.budget.reserve("router")
    session.budget.finish(
        router,
        {"prompt_tokens": 10, "completion_tokens": 1, "total_tokens": 11},
        "response_received",
    )
    observed = []

    def transport(request):
        observed.append(json.loads(request.content))
        return (
            httpx.Response(400, json=error('unknown field "thinking"'))
            if len(observed) == 1
            else httpx.Response(200, json=success())
        )

    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        model = provider.CompatibleChatOpenAI(
            model="fixture",
            base_url="https://fixture.invalid/v1",
            api_key="fixture",
            http_client=client,
            max_retries=0,
            extra_body={"thinking": {"type": "disabled"}},
        )
        with session.activate(), pytest.warns(RuntimeWarning):
            model.invoke("fixture")
    budget = session.budget.view(unmetered_analysis_calls=1)
    assert len(observed) == 2 and budget["model_calls"] == 3
    assert budget["known_usage_calls"] == 2 and budget["unknown_usage_calls"] == 1
    assert budget["known_tokens"] == {
        "prompt_tokens": 12,
        "completion_tokens": 2,
        "total_tokens": 14,
    }


def test_per_run_budget_does_not_consume_next_runs_limit(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_ANALYSIS_STATE_DIR", str(tmp_path / "protected"))
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    first = chat.ChatSession(workspace, "fixture", "run1", "", 30)
    for i in range(30):
        first.budget.reserve("analysis")
    with pytest.raises(RuntimeError, match="budget exhausted"):
        first.budget.reserve("analysis")
    second = chat.ChatSession(workspace, "fixture", "run2", "", 30)
    second.budget.reserve("router")
    assert (
        second.budget.view()["model_calls"] == 1
        and first.budget.view()["model_calls"] == 30
    )


def test_current_upstream_has_no_thinking_on_first_request():
    options = importlib.import_module(
        agent.__package__ + ".analysis_profile"
    ).coding_model_options("deepseek-v4-pro", "https://inferaiapi.com/v1")
    bodies = []

    def transport(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json=success())

    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        provider.CompatibleChatOpenAI(
            model="deepseek-v4-pro",
            base_url="https://inferaiapi.com/v1",
            api_key="fixture",
            http_client=client,
            **options,
        ).invoke("fixture")
    assert len(bodies) == 1 and "thinking" not in bodies[0]
