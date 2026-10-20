"""Opt-in synthetic CSV integration of real Deep Agents and real Apptainer.

The BaseChatModel is deterministic and scripted. This tests orchestration,
actual isolated Python execution, and an independent server-owned numerical
reference. It is not a live LLM, model-quality, biological, or anatomical test.

Run only on the configured Linux server with:
    PRIMATEX_RUN_SANDBOX_TESTS=1 <coding-venv>/bin/python -B -m unittest \
        discover -s tests -p 'test_coding_sandbox_integration.py' -v

Optional operator-controlled runtime overrides:
    PRIMATEX_TEST_RUNTIME_IMAGE, PRIMATEX_TEST_RUNTIME_ENV,
    PRIMATEX_TEST_APPTAINER_BINARY.
No provider credentials or external API are needed.
"""

from __future__ import annotations

import csv
import hashlib
import importlib
import importlib.util
import json
import os
import sys
import tempfile
import types
import unittest
from decimal import Decimal
from pathlib import Path

ENABLED = (
    sys.platform.startswith("linux")
    and os.environ.get("PRIMATEX_RUN_SANDBOX_TESTS") == "1"
)


def _load_backend():
    """Load the real modules without backend.__init__ starting the API."""
    name = "_coding_sandbox_integration_backend"
    folder = Path(__file__).resolve().parents[1] / "backend"
    package = types.ModuleType(name)
    package.__path__ = [str(folder)]
    sys.modules[name] = package
    return (
        importlib.import_module(name + ".analysis_agent"),
        importlib.import_module(name + ".analysis_executor"),
        importlib.import_module(name + ".analysis_knowledge"),
        importlib.import_module(name + ".analysis_validation"),
    )


def _analysis_code() -> str:
    """Fixed program reads the mounted data; no result values are embedded."""
    return '''import json
from pathlib import Path
import numpy as np
import pandas as pd

data = pd.read_csv("/inputs/0/subjects.csv", dtype={"subject_id": str, "group": str})
assert data["subject_id"].is_unique
assert set(data.columns) == {"subject_id", "group", "thickness_mm"}
assert not data[["subject_id", "group"]].isna().any().any()
assert np.isfinite(data["thickness_mm"].to_numpy(dtype=float)).all()
grouped = data.groupby("group", sort=True)["thickness_mm"].agg(["size", "mean"])
rows = [{"group": str(group), "n": int(row["size"]), "mean": float(row["mean"])}
        for group, row in grouped.iterrows()]
rows.append({"group": "all", "n": len(data), "mean": float(data["thickness_mm"].mean())})
pd.DataFrame(rows, columns=["group", "n", "mean"]).to_csv(
    "/work/group_summary.csv", index=False, float_format="%.17g")
summary = {
    "methods": "Arithmetic mean per declared synthetic group and over all independent fixture subjects.",
    "limitations": [
        "Synthetic software integration fixture only.",
        "The model is deterministic scripted BaseChatModel, not a live LLM.",
        "No biological, anatomical, model-quality, or scientific validation claim."
    ],
    "independent_subject_count": int(len(data)),
    "model_kind": "deterministic_scripted_base_chat_model"
}
Path("/work/summary.json").write_text(json.dumps(summary), encoding="utf-8")
manifest = {
    "schema_version": "primatex.analysis_manifest.v1",
    "artifacts": [
        {
            "path": "group_summary.csv", "kind": "csv",
            "columns": ["group", "n", "mean"], "exact_columns": True,
            "row_count": int(len(rows)), "finite_columns": ["n", "mean"],
            "unique_columns": ["group"]
        },
        {
            "path": "summary.json", "kind": "json",
            "required_keys": ["methods", "limitations", "independent_subject_count", "model_kind"]
        }
    ]
}
Path("/work/analysis_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
print("Synthetic grouped means written; independent evaluation is external.")
'''


@unittest.skipUnless(
    ENABLED,
    "Requires Linux and explicit PRIMATEX_RUN_SANDBOX_TESTS=1; no host fallback",
)
class CodingSandboxIntegrationTests(unittest.TestCase):
    def test_scripted_deep_agent_real_sandbox_and_external_reference(self):
        from langchain_core.language_models.chat_models import BaseChatModel
        from langchain_core.messages import AIMessage
        from langchain_core.outputs import ChatGeneration, ChatResult
        from langgraph.checkpoint.memory import InMemorySaver
        from pydantic import PrivateAttr

        agent, execution, knowledge, validation = _load_backend()
        code = _analysis_code()

        class DeterministicCSVModel(BaseChatModel):
            _calls: int = PrivateAttr(default=0)
            _requested_tools: list[str] = PrivateAttr(default_factory=list)

            @property
            def _llm_type(self):
                return "deterministic-scripted-sandbox-integration"

            def bind_tools(self, tools, **kwargs):
                return self

            def get_num_tokens(self, text):
                return max(1, len(text) // 4)

            def get_num_tokens_from_messages(self, messages, tools=None):
                return sum(self.get_num_tokens(str(message.content)) for message in messages)

            def _generate(self, messages, stop=None, run_manager=None, **kwargs):
                sequence = [
                    ("list_data", {"path": "/inputs"}),
                    ("read_data", {"path": "/inputs/0/subjects.csv"}),
                    ("search_knowledge", {"query": "pandas subject merge group table", "limit": 2}),
                    ("read_knowledge", {"knowledge_id": "pandas.subject_table.merge"}),
                    ("write_code", {"path": "/work/analysis.py", "code": code}),
                    ("run_python", {"path": "/work/analysis.py", "timeout_seconds": 120}),
                ]
                index = self._calls
                self._calls += 1
                if index < len(sequence):
                    name, arguments = sequence[index]
                    self._requested_tools.append(name)
                    message = AIMessage(content="", tool_calls=[{
                        "name": name, "args": arguments,
                        "id": "synthetic-call-" + str(index), "type": "tool_call",
                    }])
                else:
                    message = AIMessage(content=(
                        "The synthetic fixture program executed and wrote grouped means. "
                        "The model is deterministic scripted BaseChatModel. "
                        "Scientific validity and live LLM analysis quality are not evaluated."
                    ))
                return ChatResult(generations=[ChatGeneration(message=message)])

        # Only the input directory and the dedicated writable work directory
        # are mounted. The host-controlled reference directory is their sibling.
        with tempfile.TemporaryDirectory(prefix="primx-coding-sandbox-integration-") as folder:
            base = Path(folder)
            data = base / "approved-inputs"
            work = base / "work"
            trusted = base / "server-reference"
            data.mkdir()
            trusted.mkdir(mode=0o700)
            source = data / "subjects.csv"
            source.write_text(
                "subject_id,group,thickness_mm\n"
                "s001,control,1.0\ns002,control,3.0\n"
                "s003,case,2.0\ns004,case,4.0\n"
                "s005,control,5.0\ns006,case,6.0\n",
                encoding="utf-8",
            )
            source_hash = hashlib.sha256(source.read_bytes()).hexdigest()

            # Independent host reference: stdlib CSV + Decimal, not the generated
            # pandas/NumPy implementation, and never a model-visible artifact.
            with source.open(newline="", encoding="utf-8") as handle:
                observations = list(csv.DictReader(handle))
            expected_groups: dict[str, list[Decimal]] = {}
            for row in observations:
                expected_groups.setdefault(row["group"], []).append(Decimal(row["thickness_mm"]))
            expected_groups["all"] = [Decimal(row["thickness_mm"]) for row in observations]
            with (trusted / "means.csv").open("w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(["group", "n", "mean"])
                for name in sorted(expected_groups):
                    values = expected_groups[name]
                    writer.writerow([name, len(values), str(sum(values) / Decimal(len(values)))])
            reference_manifest = trusted / "reference.json"
            reference_manifest.write_text(json.dumps({
                "schema_version": "primatex.analysis_reference.v1",
                "tables": [{
                    "artifact_path": "group_summary.csv", "reference_path": "means.csv",
                    "key_columns": ["group"], "value_columns": ["mean"],
                    "exact_columns": ["n"], "rtol": 1e-12, "atol": 1e-12,
                }],
            }), encoding="utf-8")

            executor = execution.SandboxExecutor(
                work, [data],
                runtime_image=Path(os.environ.get(
                    "PRIMATEX_TEST_RUNTIME_IMAGE", str(execution.DEFAULT_IMAGE))),
                runtime_env=Path(os.environ.get(
                    "PRIMATEX_TEST_RUNTIME_ENV", str(execution.DEFAULT_RUNTIME))),
                apptainer_binary=os.environ.get("PRIMATEX_TEST_APPTAINER_BINARY", "apptainer"),
            )
            probe = executor.probe()
            self.assertEqual(probe["status"], "ready", probe)
            self.assertEqual(probe["backend"], "apptainer")
            self.assertEqual(probe["writable_host_mounts"], ["/work"])
            self.assertTrue(probe["checks"]["input_write_blocked"])
            self.assertTrue(probe["checks"]["network_isolated"])
            self.assertTrue(probe["checks"]["host_path_hidden"])
            self.assertTrue(probe["checks"]["host_gpu_hidden"])

            tools = agent.AnalysisTools(work, [data], executor, knowledge.KnowledgeStore())
            model = DeterministicCSVModel()
            coding_agent = agent._build_coding_agent(
                tools, model="deterministic-scripted-no-api",
                base_url="https://example.invalid/v1", api_key="unused-test-sentinel",
                model_factory=lambda **kwargs: model,
            )
            checker = validation.ArtifactValidator(reference_manifest=reference_manifest)
            graph = agent._build_graph(coding_agent, tools, checker, InMemorySaver())
            result = graph.invoke({
                "request": (
                    "Synthetic software integration test: inspect the approved subject table, "
                    "retrieve pandas evidence, write and execute Python to report per-group and "
                    "overall arithmetic means, and declare generated artifacts. This is not a "
                    "biological analysis or live LLM evaluation."
                ),
                "iterations": 0, "history": [],
            }, {"configurable": {"thread_id": "deterministic-synthetic-csv"}, "recursion_limit": 20})

            self.assertEqual(result["status"], "completed", result)
            self.assertEqual(tools.executions, 1)
            self.assertEqual(result["execution"]["backend"], "apptainer")
            self.assertEqual(result["execution"]["status"], "success")
            self.assertTrue(result["validation"]["valid"])
            self.assertEqual(result["validation"]["independent_numeric_status"], "passed")
            self.assertEqual(result["validation"]["scientific_status"], "not_evaluated")
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), source_hash)
            self.assertEqual(model._requested_tools, [
                "list_data", "read_data", "search_knowledge", "read_knowledge", "write_code", "run_python",
            ])
            self.assertGreaterEqual(model._calls, 7)
            self.assertIn("deterministic", result["message"].lower())
            summary = json.loads((work / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["independent_subject_count"], 6)
            self.assertEqual(summary["model_kind"], "deterministic_scripted_base_chat_model")
            artifact_paths = {item["path"] for item in result["validation"]["artifacts"]}
            self.assertEqual(artifact_paths, {"group_summary.csv", "summary.json"})
            self.assertNotIn("means.csv", executor._artifacts(work / "analysis.py"))

            # A negative control proves that completion was not merely an exit
            # code or structural check: alter one value, retain schema/rows.
            output = work / "group_summary.csv"
            with output.open(newline="", encoding="utf-8") as handle:
                actual_rows = list(csv.DictReader(handle))
            actual_rows[0]["mean"] = str(Decimal(actual_rows[0]["mean"]) + Decimal("0.5"))
            with output.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=["group", "n", "mean"])
                writer.writeheader()
                writer.writerows(actual_rows)
            failed = checker.validate(work)
            self.assertFalse(failed["valid"], failed)
            self.assertEqual(failed["independent_numeric_status"], "failed")
            self.assertEqual(failed["scientific_status"], "not_evaluated")


if __name__ == "__main__":
    unittest.main()

