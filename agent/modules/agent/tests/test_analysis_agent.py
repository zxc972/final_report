"""Security boundaries and an offline, deterministic Deep Agents coding loop."""

import importlib
import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import types
import threading
import time
from concurrent.futures import ThreadPoolExecutor
import unittest
from pathlib import Path
from unittest.mock import patch

# Do not import backend.__init__ (which eagerly starts the unrelated FastAPI app).
_backend = Path(__file__).resolve().parents[1] / "backend"
_package_name = "_analysis_test_backend"
_package = types.ModuleType(_package_name)
_package.__path__ = [str(_backend)]
sys.modules[_package_name] = _package
_spec = importlib.util.spec_from_file_location(_package_name + ".analysis_agent",
                                              _backend / "analysis_agent.py")
agent = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = agent
_spec.loader.exec_module(agent)


class FakeKnowledge:
    def search(self, query, limit=5):
        return [{"id": "fixture", "content": "Sum the observed fixture values."}]

    def read(self, record_id):
        if record_id != "fixture":
            raise ValueError("Unknown knowledge ID")
        return {"id": "fixture", "trust": "untrusted_evidence", "content": "fixture"}


class TestOnlyExecutor:
    """Runs only the hard-coded test fixture, never used by production code."""
    def __init__(self, workdir, input_roots):
        self.workdir = workdir

    def run(self, script_path, timeout_seconds=120):
        result = subprocess.run([sys.executable, str(script_path)], cwd=self.workdir,
                                capture_output=True, text=True, timeout=timeout_seconds)
        return {"status": "success" if result.returncode == 0 else "failed",
                "exit_code": result.returncode, "stdout": result.stdout,
                "stderr": result.stderr, "backend": "test-only-fixture"}


def fixture_code():
    manifest = {"schema_version": "primatex.analysis_manifest.v1", "artifacts": [
        {"path": "summary.json", "kind": "json", "required_keys": ["methods", "limitations"]}]}
    return ("import json\nfrom pathlib import Path\n"
            "values = [2.0, 3.0]\n"
            "summary = {'methods': 'sum of the two observed fixture values', "
            "'limitations': 'fixture only; scientific validity not evaluated', 'sum': sum(values)}\n"
            "Path('summary.json').write_text(json.dumps(summary), encoding='utf-8')\n"
            f"Path('analysis_manifest.json').write_text({json.dumps(json.dumps(manifest))}, encoding='utf-8')\n"
            "print(summary['sum'])\n")


class AnalysisToolBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.work = self.root / "work"
        self.data = self.root / "data"
        self.work.mkdir()
        self.data.mkdir()
        (self.data / "values.csv").write_text("value\n2\n3\n", encoding="utf-8")
        self.tools = agent.AnalysisTools(self.work, [self.data],
                                        TestOnlyExecutor(self.work, [self.data]), FakeKnowledge(),
                                        secret="private-provider-key")

    def tearDown(self):
        self.temp.cleanup()

    def test_approved_mapping_and_host_path_rejection(self):
        self.assertEqual(self.tools.resolve("/inputs/0/values.csv"), self.data / "values.csv")
        self.assertIn("2", self.tools.read_data("/inputs/0/values.csv")["content"])
        self.assertEqual(self.tools.resolve(str(self.data / "values.csv")), self.data / "values.csv")
        with self.assertRaises(ValueError): self.tools.resolve(str(self.data / "values.csv"), writable=True)
        for path in ("/etc/passwd", "/work/../outside",
                     "/inputs/1/values.csv", "C:\\secrets.txt"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.tools.resolve(path)
        with self.assertRaises(ValueError):
            self.tools.resolve("/inputs/0/new.py", writable=True)

    def test_write_requires_python_and_valid_syntax(self):
        self.assertEqual(self.tools.write_code("/work/run.sh", "echo hi")["status"], "error")
        self.assertEqual(self.tools.write_code("/work/run.py", "if:")["status"], "error")
        self.assertFalse((self.work / "run.py").exists())
        result = self.tools.write_code("/work/run.py", fixture_code())
        self.assertTrue(result["syntax_valid"])
        self.assertEqual(self.tools.run_python("/work/run.py")["status"], "success")
        self.assertEqual(json.loads((self.work / "summary.json").read_text())["sum"], 5.0)

    def test_symlink_cannot_escape_workdir(self):
        target = self.root / "outside.txt"
        target.write_text("private", encoding="utf-8")
        try:
            (self.work / "linked.txt").symlink_to(target)
        except OSError:
            self.skipTest("This OS/user cannot create symlinks")
        self.assertEqual(self.tools.read_data("/work/linked.txt")["status"], "error")

    def test_executor_exception_does_not_reuse_previous_success(self):
        self.tools.write_code("run.py", fixture_code())
        self.assertEqual(self.tools.run_python("run.py")["status"], "success")
        with patch.object(self.tools.executor, "run", side_effect=RuntimeError(
                "failure private-provider-key")):
            result = self.tools.run_python("run.py")
        self.assertEqual(result["status"], "failed")
        self.assertNotIn("private-provider-key", json.dumps(result))
        self.assertEqual(self.tools.last_execution["status"], "failed")

    def test_zero_exit_cannot_reuse_previous_manifest(self):
        self.tools.write_code("run.py", fixture_code())
        self.assertEqual(self.tools.run_python("run.py")["status"], "success")
        self.assertTrue((self.work / "analysis_manifest.json").exists())
        self.tools.write_code("empty.py", "pass\n")
        self.assertEqual(self.tools.run_python("empty.py")["status"], "success")
        self.assertFalse((self.work / "analysis_manifest.json").exists())
        validation_module = importlib.import_module(agent.__package__ + ".analysis_validation")
        self.assertFalse(validation_module.ArtifactValidator().validate(self.work)["valid"])

    def test_python_execution_budget_is_hard_bounded(self):
        self.tools.write_code("run.py", "print(1)")
        with patch.object(agent, "MAX_EXECUTIONS", 1):
            self.assertEqual(self.tools.run_python("run.py")["status"], "success")
            self.assertEqual(self.tools.run_python("run.py")["status"], "error")
        self.assertEqual(self.tools.executions, 1)

    def test_budget_survives_tool_object_recreation(self):
        ledger = agent.BudgetLedger(self.root / "protected-budget.sqlite3", "test-run")
        tools = agent.AnalysisTools(self.work, [self.data], self.tools.executor,
                                    FakeKnowledge(), ledger=ledger)
        tools._tick(model=True)
        tools.list_data()
        recreated = agent.AnalysisTools(self.work, [self.data], self.tools.executor,
                                        FakeKnowledge(), ledger=ledger)
        self.assertEqual(recreated.model_calls, 1)
        self.assertEqual(recreated.tool_calls, 1)
        with patch.object(agent, "MAX_MODEL_CALLS", 1), self.assertRaises(agent.BudgetExceeded):
            recreated._tick(model=True)
        with agent.closing(sqlite3.connect(str(ledger.path))) as db, db:
            db.execute("UPDATE budgets SET deadline=? WHERE run_id=?", (time.time() - 1, "test-run"))
        with self.assertRaises(agent.BudgetExceeded):
            ledger.reserve("tool_calls", 40)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFO test requires POSIX")
    def test_fifos_are_rejected_without_open_blocking(self):
        os.mkfifo(self.work / "pipe.csv")
        os.mkfifo(self.work / "pipe.py")
        started = time.monotonic()
        self.assertEqual(self.tools.read_data("/work/pipe.csv")["status"], "error")
        self.assertEqual(self.tools.write_code("/work/pipe.py", "pass")["status"], "error")
        self.assertLess(time.monotonic() - started, 2)

    def test_parallel_execution_is_serial_and_timeout_uses_remaining_budget(self):
        active = 0
        maximum = 0
        observed_timeouts = []
        lock = threading.Lock()

        def execute(*args, timeout_seconds=120):
            nonlocal active, maximum
            with lock:
                active += 1
                maximum = max(maximum, active)
                observed_timeouts.append(timeout_seconds)
            time.sleep(0.04)
            with lock:
                active -= 1
            return {"status": "success", "exit_code": 0}

        self.tools.write_code("run.py", "pass")
        self.tools.deadline = time.time() + 5
        with patch.object(self.tools.executor, "run", side_effect=execute), ThreadPoolExecutor(2) as pool:
            results = list(pool.map(lambda _: self.tools.run_python("run.py", 120), range(2)))
        self.assertEqual(maximum, 1)
        self.assertTrue(all(result["status"] == "success" for result in results))
        self.assertTrue(all(0 < value <= 5 for value in observed_timeouts))

    def test_owner_conversation_hash_and_checkpoint_separation(self):
        state_root = self.root / "server-state"
        with patch.dict(os.environ, {"AGENT_ANALYSIS_STATE_DIR": str(state_root)}):
            alice_work, alice_db, alice_thread = agent._paths(self.work, "alice", "same")
            bob_work, bob_db, bob_thread = agent._paths(self.work, "bob", "same")
        self.assertNotEqual(alice_work, bob_work)
        self.assertNotEqual(alice_db, bob_db)
        self.assertNotEqual(alice_thread, bob_thread)
        self.assertFalse(agent._inside(alice_db, alice_work))
        self.assertNotIn("alice", alice_db.name)
        with patch.dict(os.environ, {"AGENT_ANALYSIS_STATE_DIR": str(alice_work / "state")}):
            with self.assertRaises(ValueError):
                agent._paths(self.work, "alice", "same")


def framework_available():
    try:
        return all(importlib.util.find_spec(name) is not None for name in (
            "langgraph", "deepagents", "langchain_core", "langgraph.checkpoint.sqlite"))
    except ModuleNotFoundError:
        return False


@unittest.skipUnless(framework_available(), "Run with the coding framework venv")
class AnalysisGraphTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.workspace = self.root / "workspace"
        self.data = self.root / "data"
        self.workspace.mkdir()
        self.data.mkdir()
        (self.data / "values.csv").write_text("value\n2\n3\n", encoding="utf-8")
        self.environment = patch.dict(os.environ, {
            "AGENT_ANALYSIS_STATE_DIR": str(self.root / "protected-state")})
        self.environment.start()

    def tearDown(self):
        self.environment.stop()
        self.temp.cleanup()

    def test_validation_failure_repairs_and_nonexecution_is_not_success(self):
        from langgraph.checkpoint.memory import InMemorySaver

        class Coder:
            def __init__(self, tools):
                self.tools = tools
                self.calls = 0

            def invoke(self, state, config):
                self.calls += 1
                self.tools.write_code("analysis.py", fixture_code())
                self.tools.run_python("analysis.py")
                return {"messages": [{"role": "assistant", "content": "Observed sum 5."}]}

        class Validator:
            def __init__(self):
                self.calls = 0

            def validate(self, workdir):
                self.calls += 1
                valid = self.calls > 1
                return {"valid": valid, "passed": valid, "artifacts": [],
                        "errors": [] if valid else ["fixture correction needed"]}

        tools = agent.AnalysisTools(self.workspace, [self.data],
                                    TestOnlyExecutor(self.workspace, [self.data]), FakeKnowledge())
        coder = Coder(tools)
        graph = agent._build_graph(coder, tools, Validator(), InMemorySaver())
        result = graph.invoke({"request": "fixture", "iterations": 0, "history": []},
                              {"configurable": {"thread_id": "test"}})
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["iterations"], 2)
        self.assertEqual(result["validation"]["scientific_status"], "not_evaluated")

        class NonExecutingCoder:
            def invoke(self, state, config):
                return {"messages": [{"role": "assistant", "content": "Done"}]}

        graph = agent._build_graph(NonExecutingCoder(), tools, Validator(), InMemorySaver())
        result = graph.invoke({"request": "fixture", "iterations": 0},
                              {"configurable": {"thread_id": "other"}})
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["iterations"], agent.MAX_ROUNDS)

    def test_real_deep_agent_offline_tool_execution_checkpoint_and_resume(self):
        from langchain_core.language_models.chat_models import BaseChatModel
        from langchain_core.messages import AIMessage
        from langchain_core.outputs import ChatGeneration, ChatResult
        from pydantic import PrivateAttr

        class ScriptedModel(BaseChatModel):
            _calls: int = PrivateAttr(default=0)

            @property
            def _llm_type(self):
                return "deterministic-analysis-test"

            def bind_tools(self, tools, **kwargs):
                return self

            def get_num_tokens(self, text):
                return max(1, len(text) // 4)

            def get_num_tokens_from_messages(self, messages, tools=None):
                return sum(self.get_num_tokens(str(message.content)) for message in messages)

            def _generate(self, messages, stop=None, run_manager=None, **kwargs):
                # The new internal reviewer is a separate structured-output call.
                # Keep every original actor/executor/checkpoint assertion unchanged.
                if messages and str(messages[0].content).startswith("You are the internal verifier in a scientific coding Agent"):
                    self._calls += 1
                    return ChatResult(generations=[ChatGeneration(message=AIMessage(content=json.dumps({
                        "decision": "pass", "findings": [], "limitations": ["Synthetic engineering test model only"]})))])
                sequence = [
                    ("search_knowledge", {"query": "fixture sum", "limit": 1}),
                    ("read_data", {"path": "/inputs/0/values.csv"}),
                    ("write_code", {"path": "/work/analysis.py", "code": fixture_code()}),
                    ("run_python", {"path": "/work/analysis.py"}),
                ]
                index = self._calls
                self._calls += 1
                if index < len(sequence):
                    name, args = sequence[index]
                    message = AIMessage(content="", tool_calls=[{
                        "name": name, "args": args, "id": f"call-{index}", "type": "tool_call"}])
                else:
                    message = AIMessage(content="Observed fixture sum is 5. Scientific validity not evaluated.")
                return ChatResult(generations=[ChatGeneration(message=message)])

        executor_module = importlib.import_module(agent.__package__ + ".analysis_executor")
        knowledge_module = importlib.import_module(agent.__package__ + ".analysis_knowledge")
        model = ScriptedModel()
        arguments = dict(message="Sum the values in the approved fixture table.", user_id="alice",
                         workspace=self.workspace, conversation_id="conversation", model="offline",
                         base_url="https://example.invalid/v1", api_key="key-not-for-checkpoint",
                         input_roots=[self.data], resume=False,
                         model_factory=lambda **kwargs: model)
        with patch.object(executor_module, "SandboxExecutor", TestOnlyExecutor), \
                patch.object(knowledge_module, "KnowledgeStore", FakeKnowledge):
            result = agent._run_sync(**arguments)
            calls_before_resume = model._calls
            arguments["resume"] = True
            resumed = agent._run_sync(**arguments)
            arguments["resume"] = False
            arguments["model_factory"] = lambda **kwargs: ScriptedModel()
            next_run = agent._run_sync(**arguments)
        self.assertEqual(result["status"], "completed", result)
        self.assertEqual(result["executions"], 1)
        self.assertEqual(result["validation"]["independent_numeric_status"], "not_configured")
        self.assertEqual(resumed["run_id"], result["run_id"])
        self.assertEqual(resumed["output_directory"], result["output_directory"])
        self.assertEqual(Path(result["output_directory"]).parts[-1], result["run_id"])
        self.assertTrue((self.workspace / result["output_directory"] / "summary.json").is_file())
        self.assertEqual(model._calls, calls_before_resume)
        self.assertEqual(next_run["status"], "completed", next_run)
        self.assertNotEqual(next_run["run_id"], result["run_id"])
        self.assertEqual(len(list(self.workspace.rglob("summary.json"))), 2)
        databases = list((self.root / "protected-state").rglob("*.sqlite3"))
        self.assertEqual(len([p for p in databases if not p.name.endswith(".budget.sqlite3")]), 1)
        for database in databases:
            self.assertNotIn(b"key-not-for-checkpoint", database.read_bytes())


if __name__ == "__main__":
    unittest.main()
