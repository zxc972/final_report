"""A scripted model exercises phase recovery through the real isolated executor."""

import importlib
import json
import os
import re

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import PrivateAttr

from test_analysis_agent import agent
from test_analysis_product_planner import p, setup_products
from test_analysis_runtime_progress import ReviewStub


@pytest.mark.skipif(
    os.environ.get("PRIMATEX_RUN_SANDBOX_TESTS") != "1",
    reason="Explicit isolated-container synthetic-fixture opt-in required",
)
@pytest.mark.parametrize("scenario", ["wrong_path", "reseal", "missing_column"])
def test_scripted_model_recovers_and_auto_finalizes(tmp_path, monkeypatch, scenario):
    np = pytest.importorskip("numpy")
    nib = pytest.importorskip("nibabel")
    original_profile = p.ensure_profile
    tools = setup_products(tmp_path, monkeypatch)
    monkeypatch.setattr(p, "ensure_profile", original_profile)
    root = tools.input_roots[0]
    vertices = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=float)
    faces = np.array([[0, 1, 2], [0, 3, 1], [0, 2, 3], [1, 3, 2]], dtype=np.int32)
    for hemi in ("lh", "rh"):
        for name in ("white", "pial", "sphere.reg"):
            nib.freesurfer.write_geometry(
                str(root / "surf" / (hemi + "." + name)), vertices, faces
            )
        nib.freesurfer.write_morph_data(
            str(root / "surf" / (hemi + ".thickness")),
            np.array([0, 2.123456789, 4.987654321, 6.234567891], dtype=np.float32),
        )
        for atlas in ("aparc", "alternate"):
            nib.freesurfer.write_annot(
                str(root / "label" / (hemi + "." + atlas + ".annot")),
                np.array([-1, 1, 1, 2]),
                np.array([[0, 0, 0, 0], [20, 30, 40, 0], [50, 60, 70, 0]]),
                [b"unknown", b"one", b"two"],
            )
        (root / "label" / (hemi + ".cortex.label")).write_text(
            "#!ascii label\n4\n0 0 0 0 0\n1 0 0 0 0\n2 0 0 0 0\n3 0 0 0 0\n"
        )
    executor_module = importlib.import_module(agent.__package__ + ".analysis_executor")
    ops = importlib.import_module(agent.__package__ + ".analysis_operations")
    tools.executor = executor_module.SandboxExecutor(tools.workdir, [root])
    tools.executor.enable_operations(ops.SOURCE, ops.operations_manifest()["sha256"])
    seen = []

    class Model(BaseChatModel):
        _calls: int = PrivateAttr(default=0)
        _candidate: str = PrivateAttr(default="")
        _label_path: str = PrivateAttr(default="")
        _path: str = PrivateAttr(default="/work/analysis.py")

        @property
        def _llm_type(self):
            return "offline-scripted-round8"

        def bind_tools(self, tools, **kwargs):
            return self

        def get_num_tokens(self, text):
            return max(1, len(text) // 4)

        def get_num_tokens_from_messages(self, messages, tools=None):
            return sum(self.get_num_tokens(str(m.content)) for m in messages)

        def _generate(self, messages, **kwargs):
            i = self._calls
            self._calls += 1
            observations = [
                json.loads(m.content) for m in messages if isinstance(m, ToolMessage)
            ]
            last = observations[-1] if observations else {}
            if i == 0:
                name, args = "plan_analysis", {
                    "intent": {"measures": ["thickness"], "regions": "aparc"}
                }
            elif i == 1:
                self._candidate = next(
                    c["candidate_id"]
                    for c in last["candidates"]
                    if c["atlas"]["name"] == "aparc"
                )
                name, args = "commit_plan", {
                    "candidate_id": self._candidate,
                    "rationale": "Synthetic engineering example",
                    "code_path": self._path,
                }
            else:
                if last.get("status") == "committed":
                    self._label_path = re.search(r"Labels: (\S+)", last["execution_card"])[1]
                if scenario == "wrong_path" and i == 2:
                    name, args = "write_code", {
                        "path": "/work/wrong.py",
                        "code": "print('wrong')",
                    }
                elif scenario == "reseal" and i == 2:
                    name, args = "commit_plan", {
                        "candidate_id": self._candidate,
                        "rationale": "Explicit new script path",
                        "code_path": "/work/resealed.py",
                    }
                elif last.get("state", {}).get("phase") == "finalized":
                    assert last["state"]["outputs_complete"]
                    return ChatResult(
                        generations=[
                            ChatGeneration(
                                message=AIMessage(
                                    content="Synthetic engineering outputs finalized automatically; physical scale unverified."
                                )
                            )
                        ]
                    )
                elif last.get("status") == "written":
                    name, args = "run_python", {}
                else:
                    if scenario == "wrong_path" and i == 3:
                        assert "Edit /work/analysis.py instead" in last["error"]
                    if scenario == "missing_column" and i > 3:
                        assert last["state"]["phase"] == "executed_failed"
                        assert "missing column metric" in json.dumps(last["state"])
                    missing = scenario == "missing_column" and i == 2
                    code = """import csv,json
from pathlib import Path
import primatex_ops as ops
rows=[]
for scope,group in json.loads(Path(LABEL_PATH).read_text()).items():
    subject,hemi=scope.rsplit('/',1)
    metric=ops.read_surface_metric(group['annotation'].split('/label/')[0]+'/surf/'+hemi+'.thickness')
    labels,names,ctab=ops.read_annotation(group['annotation'])
    cortex=ops.read_label(group['cortex_label'])
    for row in ops.parcel_summary(metric,labels,group['labels'],mask=cortex):
        item=dict(subject=subject,hemisphere=hemi,units='stored; software convention mm; physical scale unverified',**row)
        if not MISSING:item['metric']='thickness'
        rows.append(item)
with open('/work/summary.csv','w')as stream:
    w=csv.DictWriter(stream,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
Path('/work/summary.json').write_text(json.dumps({'methods':'Synthetic fixture','limitations':'Not scientific QC','rows':rows}))
Path('/work/report.md').write_text('Synthetic engineering fixture, no rescale in this script; physical scale unverified.')
""".replace(
                        "LABEL_PATH", repr(self._label_path)
                    ).replace(
                        "MISSING", repr(missing)
                    )
                    name, args = "write_code", {"path": self._path, "code": code}
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
                                    "id": f"round8-{i}",
                                    "type": "tool_call",
                                }
                            ],
                        )
                    )
                ]
            )

    for name, value in (
        ("MAX_MODEL_CALLS", 30),
        ("MAX_TOOL_CALLS", 60),
        ("MAX_EXECUTIONS", 8),
    ):
        monkeypatch.setattr(agent, name, value)
    coder = agent._build_coding_agent(
        tools,
        model="offline",
        base_url="https://invalid.test/v1",
        api_key="fixture-not-a-key",
        model_factory=lambda **kwargs: Model(),
    )
    tools._internal_review_model = ReviewStub(
        json.dumps(
            {
                "decision": "pass",
                "findings": [],
                "hard_block_disclosure": {"complete": True, "undisclosed_constraint_ids": [],
                                          "evidence_files": ["evidence_card"], "reason": "No hard blockers in this synthetic plan"},
                "limitations": ["Synthetic engineering only"],
            }
        )
    )
    validator = importlib.import_module(
        agent.__package__ + ".analysis_validation"
    ).ArtifactValidator()
    result = agent._build_graph(coder, tools, validator, InMemorySaver()).invoke(
        {
            "request": "Describe supplied synthetic cortex.",
            "history": [],
            "iterations": 0,
        },
        {"configurable": {"thread_id": "round8-" + scenario}},
    )
    assert result["status"] == "completed", result
    assert "finalize_artifacts" not in seen
    assert tools.session.record["phase"] == "finalized"
    assert tools.session.record["automatic_finalizations"] == 1
    assert tools.executions == (2 if scenario == "missing_column" else 1)
    if scenario == "wrong_path":
        assert tools.session.record["wrong_path_blocks"] == 1
        assert not (tools.workdir / "wrong.py").exists()
    if scenario == "reseal":
        assert len(tools.control_store.versions("plan")) == 1
        assert not (tools.workdir / "resealed.py").exists()
    assert len(json.loads((tools.workdir / "summary.json").read_text())["rows"]) == 4
