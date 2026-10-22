"""Scripted model drives genuine plan/commit/container/code/finalization tools."""

import importlib, json, os
import re
from pathlib import Path
import pytest
from test_analysis_agent import agent
from test_analysis_product_planner import setup_products, p
from test_analysis_runtime_progress import ReviewStub
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import PrivateAttr


@pytest.mark.skipif(
    os.environ.get("PRIMATEX_RUN_SANDBOX_TESTS") != "1",
    reason="Explicit real isolated-container opt-in required",
)
def test_scripted_product_model_executes_ops_then_finalizes(tmp_path, monkeypatch):
    np = pytest.importorskip("numpy")
    nib = pytest.importorskip("nibabel")
    original_profile = p.ensure_profile
    tools = setup_products(tmp_path, monkeypatch)
    monkeypatch.setattr(p, "ensure_profile", original_profile)
    root = tools.input_roots[0]
    vertices = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float64)
    faces = np.array([[0, 1, 2], [0, 3, 1], [0, 2, 3], [1, 3, 2]], dtype=np.int32)
    for hemi in ["lh", "rh"]:
        for name in ["white", "pial", "sphere.reg"]:
            nib.freesurfer.write_geometry(
                str(root / "surf" / f"{hemi}.{name}"), vertices, faces
            )
        nib.freesurfer.write_morph_data(
            str(root / "surf" / f"{hemi}.thickness"),
            np.array([0, 2.123456789, 4.987654321, 6.234567891], dtype=np.float32),
        )
        for atlas in ["aparc", "alternate"]:
            nib.freesurfer.write_annot(
                str(root / "label" / f"{hemi}.{atlas}.annot"),
                np.array([-1, 1, 1, 2]),
                np.array([[0, 0, 0, 0], [20, 30, 40, 0], [50, 60, 70, 0]]),
                [b"unknown", b"one", b"two"],
            )
        (root / "label" / f"{hemi}.cortex.label").write_text(
            "#!ascii label\n4\n0 0 0 0 0\n1 0 0 0 0\n2 0 0 0 0\n3 0 0 0 0\n"
        )
    executor = importlib.import_module(
        agent.__package__ + ".analysis_executor"
    ).SandboxExecutor(tools.workdir, [root])
    ops = importlib.import_module(agent.__package__ + ".analysis_operations")
    executor.enable_operations(ops.SOURCE, ops.operations_manifest()["sha256"])
    tools.executor = executor
    seen = []

    class Model(BaseChatModel):
        _calls: int = PrivateAttr(default=0)

        @property
        def _llm_type(self):
            return "offline-scripted-operations"

        def bind_tools(self, tools, **kwargs):
            return self

        def get_num_tokens(self, text):
            return max(1, len(text) // 4)

        def get_num_tokens_from_messages(self, messages, tools=None):
            return sum(self.get_num_tokens(str(m.content)) for m in messages)

        def _generate(self, messages, **kwargs):
            i = self._calls
            self._calls += 1
            if i == 0:
                name, args = "plan_analysis", {
                    "intent": {"measures": ["thickness"], "regions": "all regions"}
                }
            elif i == 1:
                result = json.loads(
                    [m.content for m in messages if isinstance(m, ToolMessage)][-1]
                )
                assert result["candidates"]
                candidate = next(
                    c for c in result["candidates"] if c["atlas"]["name"] == "aparc"
                )
                name, args = "commit_plan", {
                    "candidate_id": candidate["candidate_id"],
                    "rationale": "Describe the synthetic native cortex with supplied exclusions.",
                    "code_path": "/work/analysis.py",
                }
            elif i == 2:
                result = json.loads(
                    [m.content for m in messages if isinstance(m, ToolMessage)][-1]
                )
                assert result["status"] == "committed"
                label_path = re.search(r"Labels: (\S+)", result["execution_card"])[1]
                code = """import json,csv
from pathlib import Path
import primatex_ops as ops
rows=[]
for scope,group in json.loads(Path(LABEL_PATH).read_text()).items():
    subject,hemi=scope.rsplit('/',1)
    metric=ops.read_surface_metric(group['annotation'].split('/label/')[0]+'/surf/'+hemi+'.thickness')
    labels,names,table=ops.read_annotation(group['annotation'])
    mask=ops.read_label(group['cortex_label'])
    for row in ops.parcel_summary(metric,labels,group['labels'],mask=mask):
        rows.append(dict(subject=subject,hemisphere=hemi,metric='thickness',units='stored; software convention mm; physical scale unverified',**row))
with open('/work/summary.csv','w') as stream:
    writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
Path('/work/summary.json').write_text(json.dumps({'methods':'Synthetic cortex means using primatex_ops','limitations':'Engineering fixture only; units unverified','rows':rows}))
Path('/work/report.md').write_text('Synthetic supplied cortex summary; units and species unverified. Plan v1; exclusions -1 and unknown. Not expert QC.')
print('fixture rows',len(rows))
""".replace(
                    "LABEL_PATH", repr(label_path)
                )
                name, args = "write_code", {"path": "/work/analysis.py", "code": code}
            elif i == 3:
                name, args = "run_python", {"path": "/work/analysis.py"}
            elif i == 4:
                result = json.loads(
                    [m.content for m in messages if isinstance(m, ToolMessage)][-1]
                )
                assert result["exit_code"] == 0, result
                name, args = "finalize_artifacts", {
                    "artifacts": [
                        {
                            "path": "summary.csv",
                            "kind": "csv",
                            "row_count": 4,
                            "finite_columns": ["mean"],
                        },
                        {
                            "path": "summary.json",
                            "kind": "json",
                            "required_keys": ["methods", "limitations"],
                        },
                        {"path": "report.md", "kind": "text"},
                    ]
                }
            else:
                return ChatResult(
                    generations=[
                        ChatGeneration(
                            message=AIMessage(
                                content="Synthetic isolated fixture completed; no scientific performance claim."
                            )
                        )
                    ]
                )
            seen.append(name)
            return ChatResult(
                generations=[
                    ChatGeneration(
                        message=AIMessage(
                            content="",
                            tool_calls=[
                                {
                                    "name": name,
                                    "args": args,
                                    "id": f"fixture-{i}",
                                    "type": "tool_call",
                                }
                            ],
                        )
                    )
                ]
            )

    monkeypatch.setattr(agent, "MAX_MODEL_CALLS", 30)
    monkeypatch.setattr(agent, "MAX_TOOL_CALLS", 60)
    monkeypatch.setattr(agent, "MAX_EXECUTIONS", 8)
    coder = agent._build_coding_agent(
        tools,
        model="offline",
        base_url="https://invalid.test/v1",
        api_key="fixture-not-a-key",
        model_factory=lambda **kw: Model(),
    )
    tools._internal_review_model = ReviewStub(
        json.dumps(
            {
                "decision": "pass",
                "findings": [],
                "hard_block_disclosure": {"complete": True, "undisclosed_constraint_ids": [],
                                          "evidence_files": ["evidence_card"], "reason": "No hard blockers in this synthetic plan"},
                "limitations": ["Synthetic engineering fixture only"],
            }
        )
    )
    validator = importlib.import_module(
        agent.__package__ + ".analysis_validation"
    ).ArtifactValidator()
    result = agent._build_graph(coder, tools, validator, InMemorySaver()).invoke(
        {
            "request": "Summarise synthetic supplied native cortex.",
            "history": [],
            "iterations": 0,
        },
        {"configurable": {"thread_id": "scripted-product-ops"}},
    )
    assert result["status"] == "completed", result
    assert tools.model_calls <= 30 and tools.executions == 1
    assert seen == [
        "plan_analysis",
        "commit_plan",
        "write_code",
        "run_python",
        "finalize_artifacts",
    ]
    assert len(json.loads((tools.workdir / "summary.json").read_text())["rows"]) == 4
