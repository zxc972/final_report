import hashlib, json, tempfile
from pathlib import Path
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import PrivateAttr
from test_analysis_agent import agent, TestOnlyExecutor, FakeKnowledge, fixture_code


class ReviewStub:
    def __init__(self, content):
        self.content = content
        self.calls = 0

    def invoke(self, messages):
        self.calls += 1
        return AIMessage(content=self.content)


def test_real_coder_repair_keeps_prior_tool_observations_and_receipts(monkeypatch):
    monkeypatch.setenv("ANALYSIS_ENABLE_INTERNAL_REVIEW", "1")
    observed = []

    class Model(BaseChatModel):
        _calls: int = PrivateAttr(default=0)

        @property
        def _llm_type(self):
            return "offline-progress-regression"

        def bind_tools(self, tools, **kw):
            return self

        def get_num_tokens(self, text):
            return max(1, len(text) // 4)

        def get_num_tokens_from_messages(self, messages, tools=None):
            return sum(self.get_num_tokens(str(m.content)) for m in messages)

        def _generate(self, messages, stop=None, run_manager=None, **kw):
            i = self._calls
            self._calls += 1
            if i == 3:
                # Second outer validation iteration must still see the first execution.
                old = [m for m in messages if isinstance(m, ToolMessage)]
                assert any(
                    "exit_code" in str(m.content) and "receipt_id" in str(m.content)
                    for m in old
                )
                assert any("analysis.py" in str(m.content) for m in old)
                observed.append(True)
            seq = {
                0: (
                    "write_code",
                    {"path": "/work/analysis.py", "code": fixture_code()},
                ),
                1: ("run_python", {"path": "/work/analysis.py"}),
                3: (
                    "write_code",
                    {"path": "/work/analysis.py", "code": fixture_code()},
                ),
                4: ("run_python", {"path": "/work/analysis.py"}),
            }
            msg = AIMessage(content="Observed completed fixture.")
            if i in seq:
                name, args = seq[i]
                msg = AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": name,
                            "args": args,
                            "id": f"progress-{i}",
                            "type": "tool_call",
                        }
                    ],
                )
            return ChatResult(generations=[ChatGeneration(message=msg)])

    class Validator:
        calls = 0

        def validate(self, w):
            self.calls += 1
            ok = self.calls == 2
            return {
                "valid": ok,
                "passed": ok,
                "artifacts": [],
                "errors": [] if ok else ["Additional declared output required"],
            }

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        work = root / "work"
        data = root / "data"
        work.mkdir()
        data.mkdir()
        tools = agent.AnalysisTools(
            work, [data], TestOnlyExecutor(work, [data]), FakeKnowledge()
        )
        coder = agent._build_coding_agent(
            tools,
            model="offline",
            base_url="https://example.invalid/v1",
            api_key="never-in-model-state",
            model_factory=lambda **kw: Model(),
        )
        reviewer = ReviewStub(
            json.dumps(
                {
                    "decision": "pass",
                    "findings": [],
                    "limitations": ["Offline fixture review only"],
                }
            )
        )
        tools._internal_review_model = reviewer
        graph = agent._build_graph(coder, tools, Validator(), InMemorySaver())
        result = graph.invoke(
            {
                "request": "test bounded analysis progress",
                "history": [],
                "iterations": 0,
            },
            {"configurable": {"thread_id": "outer-progress"}},
        )
        assert result["status"] == "completed"
        assert (
            result["iterations"] == 2 and tools.executions == 2 and observed == [True]
        )
        receipts = list(
            (work.parent / ".execution_receipts" / work.name).glob("*.json")
        )
        assert len(receipts) == 2
        for p in receipts:
            r = json.loads(p.read_text())
            assert r["result"]["exit_code"] == 0
            assert (
                r["script_sha256_before"]
                == r["script_sha256_after"]
                == hashlib.sha256((work / "analysis.py").read_bytes()).hexdigest()
            )
            assert "never-in-model-state" not in p.read_text()
        assert not list(work.glob("*receipt*"))
        assert reviewer.calls == 1
        assert result["validation"]["internal_review"]["protocol_valid"] is True


def test_real_graph_rejects_invalid_json_from_separate_reviewer(tmp_path, monkeypatch):
    monkeypatch.setenv("ANALYSIS_ENABLE_INTERNAL_REVIEW", "1")
    from test_analysis_internal_review_graph import setup
    import importlib

    tools, coder = setup(tmp_path)
    reviewer = ReviewStub("not valid JSON")
    tools._internal_review_model = reviewer
    validator = importlib.import_module(
        agent.__package__ + ".analysis_validation"
    ).ArtifactValidator()
    graph = agent._build_graph(coder, tools, validator, InMemorySaver())
    result = graph.invoke(
        {
            "request": "Inspect the executed engineering fixture",
            "history": [],
            "iterations": 0,
        },
        {"configurable": {"thread_id": "invalid-review-regression"}},
    )
    assert result["status"] == "failed"
    assert result["validation"]["internal_review"]["protocol_valid"] is False
    assert result["validation"]["artifact_structural_passed"] is True
    assert tools.executions == 1 and reviewer.calls == 1
