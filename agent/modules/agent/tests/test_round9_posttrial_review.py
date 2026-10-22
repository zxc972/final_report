"""Offline post-trial repairs; paid outcomes and strict review validation unchanged."""

import importlib
import json
import os
import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import PrivateAttr
from test_analysis_agent import agent
from test_round8_closure import sealed, fake_execution

review = importlib.import_module(agent.__package__ + ".analysis_internal_review")


def test_only_actual_execution_receipt_ids_are_registered(tmp_path, monkeypatch):
    tools, _, _ = sealed(tmp_path, monkeypatch)
    fake_execution(tools)
    tools.write_code("/work/analysis.py", "print('fixture')")
    tools.run_python()
    context, registered = review.collect_context(
        tools.workdir,
        "Synthetic fixture",
        {"artifacts": []},
        register_execution_receipts=True,
    )
    rid = tools.last_execution["receipt_id"]
    assert rid in registered
    _, legacy_registered = review.collect_context(
        tools.workdir, "Synthetic fixture", {"artifacts": []}
    )
    assert rid not in legacy_registered
    assert any(
        item["receipt_id"] == rid for item in context["actual_execution_receipts"]
    )
    payload = {
        "decision": "pass",
        "findings": [
            {
                "severity": "warning",
                "claim": "Synthetic fixture",
                "observation": "Actual protected execution receipt",
                "question": "Keep the limitation",
                "evidence_files": [rid],
            }
        ],
        "limitations": ["Synthetic only"],
    }
    assert review.parse_review(json.dumps(payload), registered)["decision"] == "pass"
    payload["findings"][0]["evidence_files"] = ["f" * 32]
    with pytest.raises(ValueError, match="unavailable evidence"):
        review.parse_review(json.dumps(payload), registered)


def test_manual_finalization_cannot_bypass_pending_review(tmp_path, monkeypatch):
    tools, _, _ = sealed(tmp_path, monkeypatch)
    fake_execution(tools)
    tools.write_code("/work/analysis.py", "print('fixture')")
    tools.run_python()
    old = tools.last_execution["automatic_finalization"]["artifact_receipt_id"]
    tools.session.review_failed(
        {"valid": False, "errors": ["Synthetic mandatory revision"]}
    )
    assert tools.session.state()["phase"] == "executed_failed"
    assert (tools.workdir / "tool_results/validation_feedback.json").is_file()
    refused = tools.finalize_artifacts([{"path": "summary.csv", "kind": "csv"}])
    assert refused["status"] == "error" and "new" not in refused.get(
        "artifact_receipt_id", ""
    )
    tools.write_code("/work/analysis.py", "print('new fixture')")
    tools.run_python()
    assert tools.session.state()["phase"] == "finalized"
    assert tools.last_execution["automatic_finalization"]["artifact_receipt_id"] != old


@pytest.mark.parametrize("real_sandbox", [False, True])
def test_real_toolnode_reopens_after_internal_review_revision(
    tmp_path, monkeypatch, real_sandbox
):
    if real_sandbox and os.environ.get("PRIMATEX_RUN_SANDBOX_TESTS") != "1":
        pytest.skip("Explicit synthetic real-container review-repair opt-in required")
    tools, _, _ = sealed(tmp_path, monkeypatch)
    if real_sandbox:
        executor = importlib.import_module(agent.__package__ + ".analysis_executor")
        tools.executor = executor.SandboxExecutor(tools.workdir, tools.input_roots)
    else:
        fake_execution(tools)
    columns = tools.control_store.latest("execution_bundle")["record"][
        "output_contract"
    ]["csv_columns"]
    source = (
        "import csv,json\nfrom pathlib import Path\n"
        + "columns="
        + repr(columns)
        + "\nidentities=" + repr(tools.control_store.latest("execution_bundle")["record"]["output_contract"]["table"]["expected_identities"]) + "\n"
        + "with open('/work/summary.csv','w') as f:\n"
        + " w=csv.DictWriter(f,fieldnames=columns)\n w.writeheader()\n"
        + " for identity in identities:\n  row={**identity,'vertex_count':3,'mean':1.234567891234,'std_population':0.123456789123,'median':1.234567891234,'zero_count':0,'units':'synthetic stored units'}\n  w.writerow({k:row[k] for k in columns})\n"
        + "Path('/work/summary.json').write_text(json.dumps({'methods':'Synthetic control fixture','limitations':'No scientific result'}))\n"
        + "Path('/work/report.md').write_text('Synthetic control fixture; no biological inference.')\n"
    )
    seen = []

    class Model(BaseChatModel):
        _calls: int = PrivateAttr(default=0)

        @property
        def _llm_type(self):
            return "offline-review-repair"

        def bind_tools(self, tools, **kwargs):
            return self

        def get_num_tokens(self, text):
            return max(1, len(text) // 4)

        def get_num_tokens_from_messages(self, messages, tools=None):
            return sum(self.get_num_tokens(str(m.content)) for m in messages)

        def _generate(self, messages, **kwargs):
            i = self._calls
            self._calls += 1
            if i in [2, 6]:
                return ChatResult(
                    generations=[
                        ChatGeneration(
                            message=AIMessage(content="Synthetic fixture report.")
                        )
                    ]
                )
            sequence = {
                0: (
                    "write_code",
                    {
                        "path": "/work/analysis.py",
                        "code": source + "print('first fixture')\n",
                    },
                ),
                1: ("run_python", {}),
                3: (
                    "read_file",
                    {"path": "/work/tool_results/validation_feedback.json"},
                ),
                4: (
                    "write_code",
                    {
                        "path": "/work/analysis.py",
                        "code": source + "print('repaired fixture')\n",
                    },
                ),
                5: ("run_python", {}),
            }
            name, args = sequence[i]
            seen.append(name)
            return ChatResult(
                generations=[
                    ChatGeneration(
                        message=AIMessage(
                            content="",
                            tool_calls=[
                                {"id": f"repair-{i}", "name": name, "args": args}
                            ],
                        )
                    )
                ]
            )

    class Reviewer:
        calls = 0

        def invoke(self, messages):
            self.calls += 1
            rid = tools.last_execution["receipt_id"]
            payload = {
                "decision": "revise" if self.calls == 1 else "pass",
                "findings": (
                    [
                        {
                            "severity": "blocking",
                            "claim": "Synthetic first report needs revision",
                            "observation": "First protected receipt observed",
                            "question": "Revise the synthetic report and execute again",
                            "evidence_files": [rid],
                        }
                    ]
                    if self.calls == 1
                    else []
                ),
                "limitations": ["Engineering fixture only"],
                "hard_block_disclosure": {"complete": True, "undisclosed_constraint_ids": [],
                                          "evidence_files": ["evidence_card"], "reason": "No hard blockers for the committed synthetic fixture"},
            }
            return AIMessage(content=json.dumps(payload))

    coder = agent._build_coding_agent(
        tools,
        model="fixture",
        base_url="https://fixture.invalid/v1",
        api_key="fixture",
        model_factory=lambda **kwargs: Model(),
    )
    reviewer = Reviewer()
    tools._internal_review_model = reviewer
    validator = importlib.import_module(
        agent.__package__ + ".analysis_validation"
    ).ArtifactValidator()
    result = agent._build_graph(coder, tools, validator, InMemorySaver()).invoke(
        {"request": "Synthetic review repair.", "history": [], "iterations": 0},
        {"configurable": {"thread_id": "r9-review-repair"}},
    )
    assert result["status"] == "completed", result
    assert tools.executions == 2 and reviewer.calls == 2
    assert result["validation"]["internal_review"]["protocol_valid"] is True
    assert tools.session.record["automatic_finalizations"] == 2
    assert "read_file" in seen
    phases = [
        tools.control_store.read(path.name)["record"]["phase"]
        for path in tools.control_store.versions("session")
    ]
    assert phases.count("finalized") == 2 and "executed_failed" in phases
