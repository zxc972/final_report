"""Bounded coding agent; credentials stay in closures, outside graph checkpoints.

The Deep Agents filesystem is virtual. Only the explicit tools below touch
approved data or the analysis work directory. Generated Python runs exclusively
through SandboxExecutor, never through a host shell in this module.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sqlite3
import stat
import threading
import time
import uuid
from pathlib import Path, PurePosixPath
from typing import Any, Callable, TypedDict
from contextlib import closing, contextmanager
from .data_tools import DataTools
from .pipeline_bridge import PipelineBridge, DATA_TOOL_NAMES
from .analysis_feedback import FeedbackJournal
from .analysis_product_planner import AnalysisIntent
from .analysis_method_graph import MethodGraph
from .analysis_knowledge_profiles import KnowledgeProfile, load_knowledge_profile, filter_functions
from .analysis_policy import build_system_prompt

MAX_ROUNDS = 3
from .analysis_profile import bounded_setting, coding_model_options

MAX_TOOL_CALLS = bounded_setting("ANALYSIS_MAX_TOOL_CALLS", 128, 1, 256)
MAX_MODEL_CALLS = bounded_setting("ANALYSIS_MAX_MODEL_CALLS", 64, 1, 128)
MAX_EXECUTIONS = bounded_setting("ANALYSIS_MAX_EXECUTIONS", 24, 1, 48)
MAX_RUN_SECONDS = 1500
MAX_CODE_BYTES = 100_000
MAX_EXECUTION_SECONDS = bounded_setting("ANALYSIS_MAX_EXECUTION_SECONDS", 900, 1, 3600)
_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()


class AnalysisState(TypedDict, total=False):
    request: str
    execution_required: bool
    required_artifacts: list[str]
    workspace_id: str
    input_roots_id: str
    run_id: str
    history: list[dict[str, str]]
    draft_message: str
    feedback: str
    validation: dict[str, Any]
    execution: dict[str, Any]
    iterations: int
    executions: int
    model_calls: int
    tool_calls: int
    status: str
    message: str
    artifacts: list[Any]
    pipeline_tasks: list[dict]
    analysis_jobs: list[dict]
    navigation_calls: int
    metadata: dict[str, Any]


class BudgetExceeded(RuntimeError):
    pass


class BudgetLedger:
    """Reserve attempts durably before model/tool/process side effects."""

    def __init__(self, path: Path, run_id: str) -> None:
        self.path, self.run_id = path, run_id
        with closing(sqlite3.connect(str(path), timeout=30)) as db, db:
            db.execute("CREATE TABLE IF NOT EXISTS budgets (run_id TEXT PRIMARY KEY, "
                       "deadline REAL NOT NULL, model_calls INTEGER NOT NULL DEFAULT 0, "
                       "tool_calls INTEGER NOT NULL DEFAULT 0, executions INTEGER NOT NULL DEFAULT 0)")
            db.execute("INSERT OR IGNORE INTO budgets(run_id, deadline) VALUES (?, ?)",
                       (run_id, time.time() + MAX_RUN_SECONDS))

    def snapshot(self) -> dict[str, Any]:
        with closing(sqlite3.connect(str(self.path), timeout=30)) as db, db:
            row = db.execute("SELECT deadline, model_calls, tool_calls, executions "
                             "FROM budgets WHERE run_id=?", (self.run_id,)).fetchone()
        return dict(zip(("deadline", "model_calls", "tool_calls", "executions"), row))

    def bind_knowledge_metadata(self, metadata: dict[str, Any]) -> None:
        """Pin exposure and prompt identity separately from unchanged attempt counts."""
        encoded = json.dumps(metadata, ensure_ascii=False, sort_keys=True)
        with closing(sqlite3.connect(str(self.path), timeout=30)) as db, db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS run_metadata "
                "(run_id TEXT PRIMARY KEY, knowledge_json TEXT NOT NULL)"
            )
            existing = db.execute(
                "SELECT knowledge_json FROM run_metadata WHERE run_id=?", (self.run_id,)
            ).fetchone()
            if existing is not None and existing[0] != encoded:
                raise ValueError("Resume requires the original knowledge configuration")
            db.execute(
                "INSERT OR IGNORE INTO run_metadata(run_id, knowledge_json) VALUES (?, ?)",
                (self.run_id, encoded),
            )

    def reserve(self, kind: str, limit: int) -> dict[str, Any]:
        if kind not in {"model_calls", "tool_calls", "executions"}:
            raise ValueError("Invalid budget category")
        with closing(sqlite3.connect(str(self.path), timeout=30)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT deadline, model_calls, tool_calls, executions "
                             "FROM budgets WHERE run_id=?", (self.run_id,)).fetchone()
            values = dict(zip(("deadline", "model_calls", "tool_calls", "executions"), row))
            remaining = values["deadline"] - time.time()
            if remaining <= (60 if kind == "model_calls" else 0):
                raise BudgetExceeded("Analysis wall-clock budget exhausted")
            if values[kind] >= limit:
                raise BudgetExceeded(f"Analysis {kind} budget exhausted")
            db.execute(f"UPDATE budgets SET {kind}={kind}+1 WHERE run_id=?", (self.run_id,))
            values[kind] += 1
        return values


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]


def _inside(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _no_links(path: Path, root: Path) -> None:
    """Reject existing symlinks at every component, including the final path."""
    if not _inside(path, root):
        raise ValueError("Path is outside its approved root")
    current = root
    if current.is_symlink():
        raise ValueError("Symlink roots are not allowed")
    for part in path.relative_to(root).parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("Symlink paths are not allowed")


@contextmanager
def _parent_fd(path: Path, root: Path):
    """Anchor Linux opens to the approved directory, rejecting symlink parents."""
    _no_links(path, root)
    descriptors = []
    try:
        if os.open in os.supports_dir_fd:
            flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(root, flags)
            descriptors.append(descriptor)
            for part in path.relative_to(root).parts[:-1]:
                descriptor = os.open(part, flags, dir_fd=descriptor)
                descriptors.append(descriptor)
            yield descriptor
        else:
            yield None
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _read_regular(path: Path, root: Path, limit: int) -> bytes:
    with _parent_fd(path, root) as parent:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        descriptor = os.open(path.name if parent is not None else path, flags,
                             **({"dir_fd": parent} if parent is not None else {}))
        with os.fdopen(descriptor, "rb") as handle:
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                raise ValueError("Only regular files may be read")
            return handle.read(limit)


def _write_regular(path: Path, root: Path, content: str) -> None:
    with _parent_fd(path, root) as parent:
        kwargs = {"dir_fd": parent} if parent is not None else {}
        name = path.name if parent is not None else path
        try:
            existing = os.stat(name, follow_symlinks=False, **kwargs)
        except FileNotFoundError:
            existing = None
        if existing and not stat.S_ISREG(existing.st_mode):
            raise ValueError("Only regular Python files may be replaced")
        temporary = ".write-" + uuid.uuid4().hex
        temp_path = temporary if parent is not None else path.parent / temporary
        descriptor = os.open(temp_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                             getattr(os, "O_NOFOLLOW", 0), 0o600, **kwargs)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(content)
            if parent is None:
                os.replace(temp_path, path)
            else:
                os.replace(temporary, path.name, src_dir_fd=parent, dst_dir_fd=parent)
        finally:
            try:
                os.unlink(temp_path, **kwargs)
            except FileNotFoundError:
                pass


def _safe(value: Any, secret: str = "", limit: int = 12_000) -> Any:
    """JSON-only bounded tool/checkpoint content, with the supplied key redacted."""
    if isinstance(value, str):
        if secret:
            value = value.replace(secret, "[REDACTED]")
        return value[:limit]
    if isinstance(value, dict):
        return {str(k): _safe(v, secret, limit) for k, v in list(value.items())[:100]}
    if isinstance(value, (list, tuple)):
        return [_safe(v, secret, limit) for v in value[:100]]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return _safe(str(value), secret, limit)


class AnalysisTools:
    """Only /work and /inputs/N are accepted at the model-facing boundary."""

    def __init__(self, workdir: Path, input_roots: list[Path], executor: Any,
                 knowledge: Any, secret: str = "", ledger: BudgetLedger | None = None,
                 workspace: Path | None = None, threads: int = 2,
                 knowledge_profile: KnowledgeProfile | None = None) -> None:
        self.knowledge_profile = knowledge_profile or load_knowledge_profile()
        self.knowledge_metadata: dict[str, Any] = {}
        self.workdir = workdir.resolve()
        self.input_roots = [p.resolve(strict=True) for p in input_roots]
        self.executor = executor
        self.operations_metadata = None
        if self.knowledge_profile.name in {"method_graph", "method_graph_gated", "product_graph_planner"}:
            from .analysis_operations import operations_manifest, SOURCE
            self.operations_metadata = operations_manifest()
            if hasattr(executor, "enable_operations"):
                executor.enable_operations(SOURCE, self.operations_metadata["sha256"])
        self.knowledge = knowledge
        self.secret = secret
        self.started = time.monotonic()
        self.deadline = time.time() + MAX_RUN_SECONDS
        self.ledger = ledger
        self.tool_calls = 0
        self.model_calls = 0
        self.executions = 0
        self.last_execution: dict[str, Any] = {}
        self.analysis_jobs: list[dict] = []
        self.required_artifacts: list[str] = []
        self._lock = threading.Lock()
        self._execution_lock = threading.RLock()
        self.data = DataTools(workspace or workdir, input_roots, workdir)
        self.data.allow_subject_links = self.knowledge_profile.name == "product_graph_planner"
        self.pipeline = PipelineBridge(self.data, threads) if workspace else None
        self.navigation_calls = 0
        self.feedback_journal = FeedbackJournal(self.workdir)
        self._method_graph_store = None
        self.control_store = None
        self.events = None
        self.task_request = ""
        if self.knowledge_profile.name in {"method_graph", "method_graph_gated", "product_graph_planner"}:
            from .analysis_control_store import ControlStore
            state_root = (ledger.path.parent / (ledger.path.stem + ".controls") / ledger.run_id
                          if ledger else Path(os.environ.get("AGENT_ANALYSIS_STATE_DIR", str(
                              Path(__file__).resolve().parent.parent / ".analysis_state")))
                          / "controls" / _digest(str(self.workdir)))
            self.control_store = ControlStore(state_root, [self.workdir, *self.input_roots])
            from .analysis_events import AnalysisEvents
            self.events = AnalysisEvents(self.control_store, secret)
            context = {"run_id": ledger.run_id if ledger else self.workdir.name,
                       "knowledge_profile": self.knowledge_profile.name,
                       "workspace_sha256": _digest(str((workspace or workdir).resolve())),
                       "started_time": time.time()}
            if self.control_store.read("context.json") is None:
                self.control_store.create("context.json", context)
        if self.control_store is not None and self.knowledge_profile.name == "product_graph_planner":
            from .analysis_participants import register_tables
            register_tables(self)
        if ledger:
            self._load_budget(ledger.snapshot())
        self.session = None
        self.model_context = None
        if self.knowledge_profile.name == "product_graph_planner":
            from .analysis_session import AnalysisSession
            from .analysis_context import ModelContext
            self.session = AnalysisSession(self)
            self.model_context = ModelContext(self)

    def _load_budget(self, values: dict[str, Any]) -> None:
        for key in ("deadline", "tool_calls", "model_calls", "executions"):
            setattr(self, key, values[key])

    def _tick(self, *, model: bool = False) -> None:
        with self._lock:
            phase = None
            if model and self.session is not None:
                from .analysis_planning_budget import before_reserve
                phase = before_reserve(self)
            if self.ledger:
                self._load_budget(self.ledger.reserve("model_calls" if model else "tool_calls",
                                                     MAX_MODEL_CALLS if model else MAX_TOOL_CALLS))
                if phase is not None:
                    from .analysis_planning_budget import after_reserve
                    after_reserve(self, phase)
                return
            if time.time() >= self.deadline:
                raise BudgetExceeded("Analysis wall-clock budget exhausted")
            if model:
                if self.model_calls >= MAX_MODEL_CALLS:
                    raise BudgetExceeded("Analysis model-call budget exhausted")
                self.model_calls += 1
                if phase is not None:
                    from .analysis_planning_budget import after_reserve
                    after_reserve(self, phase)
            else:
                if self.tool_calls >= MAX_TOOL_CALLS:
                    raise BudgetExceeded("Analysis tool-call budget exhausted")
                self.tool_calls += 1

    def _call(self, operation: Callable[[], Any]) -> dict[str, Any]:
        try:
            self._tick()
            result = operation()
            if not isinstance(result, dict):
                result = {"status": "ok", "result": result}
        except Exception as exc:
            result = {"status": "error", "error": _safe(str(exc), self.secret)}
        if self.session is not None:
            result["state"] = self.session.state()
        return _safe(result, self.secret)

    def resolve(self, path: str, *, writable: bool = False) -> Path:
        if not path or "\\" in path or ":" in path or "\x00" in path:
            raise ValueError("Use mapped /work or /inputs/N POSIX paths")
        parts = PurePosixPath(path).parts
        if ".." in parts:
            raise ValueError("Parent traversal is not allowed")
        if path.startswith("/work/") or path == "/work":
            root, relative = self.workdir, path.removeprefix("/work").lstrip("/")
        elif path.startswith("/inputs/"):
            if writable:
                raise ValueError("Approved inputs are read-only")
            values = path.split("/")
            if len(values) < 3 or not values[2].isdigit():
                raise ValueError("Expected /inputs/N/path")
            index = int(values[2])
            if index >= len(self.input_roots):
                raise ValueError("Unknown approved input root")
            root, relative = self.input_roots[index], "/".join(values[3:])
        elif not path.startswith("/"):
            root, relative = self.workdir, path
        else:
            candidate = self.data.resolve(path)
            if writable and not _inside(candidate, self.workdir):
                raise ValueError("Registered source directories are read-only")
            return candidate
        candidate = root / relative
        if root != self.workdir and candidate.exists() and self.knowledge_profile.name == "product_graph_planner":
            from .analysis_input_links import resolve_input
            return resolve_input(candidate, root)
        _no_links(candidate, root)
        resolved = candidate.resolve()
        if not _inside(resolved, root):
            raise ValueError("Resolved path escaped its root")
        return candidate

    def read_operations(self, function: str | None = None) -> dict[str, Any]:
        """Read signatures, return formats and units for the read-only primatex_ops library.

        Use these mature functions in NEW code you write. They are building
        blocks, not a complete analysis script. No reference answers are exposed.
        """
        def operation():
            from .analysis_operations import operations_manifest
            manifest = operations_manifest()
            if function is not None:
                selected = [row for row in manifest["functions"] if row["name"] == function]
                if not selected:
                    raise ValueError("Unknown operation function: " + str(function))
                manifest["functions"] = selected
            return {"status": "ok", **manifest}
        return self._call(operation)

    def plan_analysis(self, intent: AnalysisIntent) -> dict[str, Any]:
        """Get feasible candidates, missing-product recipes and observed blockers.

        Supply only a flat intent: measures, regions, comparison, optional
        subjects/species/space/method_id. This profiles registered inputs and
        checks actual software without calling a model or running preprocessing.
        Select a candidate with commit_plan; never hand-construct nested plans.
        """
        def operation():
            if self.knowledge_profile.name != "product_graph_planner":
                raise ValueError("Product planning is disabled in this profile")
            from .analysis_product_planner import plan_analysis
            with self._execution_lock:
                return plan_analysis(self, intent)
        return self._call(operation)

    def commit_plan(self, plan: dict[str, Any]) -> dict[str, Any]:
        """Seal a checked plan with immutable version, SHA-256 and disclosure notes.

        Required: question; data.files/subjects/profile_sha256; atlas name/version/
        space/hemisphere_rule; method.method_id; constraints version/sha256;
        outputs; code_path. Include analysis_scope and revision_reason on changes.
        Compile the exact proposed plan before committing it.
        """
        def operation():
            if self.control_store is None:
                raise ValueError("Plan commitment requires a method graph profile")
            from .analysis_plans import commit_plan
            with self._execution_lock:
                return commit_plan(self, plan)
        return self._call(operation)

    def compile_constraints(self, method_id: str, task_category: str,
                            plan_context: dict[str, Any],
                            model_declared: dict[str, str] | None = None) -> dict[str, Any]:
        """Run mapped constraints against protected profile observations and a proposed plan.

        Supply the intended plan including data.files, atlas exclusions/mesh
        bindings and analysis_scope. Model verdicts never override actual probes.
        Recompile after changing the plan. Unmapped method facts stay unverified.
        """
        def operation():
            if self.control_store is None:
                raise ValueError("Executable constraints require a method graph profile")
            from .analysis_constraints import compile_constraints
            with self._execution_lock:
                return compile_constraints(self, method_id, task_category, plan_context, model_declared)
        return self._call(operation)

    def profile_data(self, paths: list[str]) -> dict[str, Any]:
        """Generate sourced deterministic file/header/annotation metadata in the sandbox.

        Explicit file paths only. This does not verify species, acquisition scale
        or scientific applicability. Unreadable fields remain null with reasons.
        """
        def operation():
            if self.control_store is None:
                raise ValueError("Data profiling requires a method graph profile")
            from .analysis_data_profile import profile_data
            with self._execution_lock:
                return profile_data(self, paths)
        return self._call(operation)

    def inspect_analysis_runtime(self) -> dict[str, Any]:
        """Discover actual isolated software/Python packages before writing code.

        No study inputs are mounted for this read-only inventory. Executable
        locations are candidates, not proof of functional or scientific validity.
        Counts as a tool call, not a completed analysis execution.
        """
        def operation() -> dict[str, Any]:
            result = self.executor.inspect_runtime()
            result["execution_policy"] = {
                "default_script_seconds": 120, "max_script_seconds": MAX_EXECUTION_SECONDS,
                "remaining_run_seconds": max(0, int(self.deadline - time.time())),
                "total_run_seconds": MAX_RUN_SECONDS,
                "limits": "Actual script timeout is min(requested, server maximum, remaining total run time). Long CLI jobs need an explicit suitable timeout; file presence does not prove command success.",
            }
            from . import analysis_validation as artifact_validation
            result["artifact_policy"] = {
                "maximum_bytes_per_artifact": artifact_validation.MAX_ARTIFACT_BYTES,
                "maximum_rows_per_table": artifact_validation.MAX_ROWS,
                "maximum_artifacts": artifact_validation.MAX_ARTIFACTS,
                "scope": "Actual unchanged structural validator limits, not a scientific sampling policy.",
            }
            if os.environ.get("ANALYSIS_ENABLE_BACKGROUND_JOBS", "0") == "1":
                from .analysis_jobs import MAX_JOB_SECONDS
                result["execution_policy"]["background_job"] = {
                    "enabled": True, "maximum_seconds": MAX_JOB_SECONDS,
                    "provider_requests_in_worker": 0,
                    "scope": "Separate declared compute budget; complete code and all requested outputs must be prepared before submission. Submitted is not completed."}
            return result
        return self._call(operation)

    def _method_graph(self) -> Any:
        if self._method_graph_store is None:
            from .analysis_release import configured_research_root
            root = configured_research_root()
            if not root:
                raise ValueError("Method graph release is not configured")
            unified = None
            if self.control_store is not None:
                from .analysis_unified_runtime import repository_for
                unified = repository_for(self)
            self._method_graph_store = MethodGraph(Path(root), unified_store=unified)
        return self._method_graph_store

    def search_analysis_methods(self, query: str, limit: int = 5) -> dict[str, Any]:
        """Find sourced analysis methods, prerequisites, steps, checks and exceptions."""
        return self._call(lambda: self._method_graph().search(query, limit))

    def read_analysis_method(self, method_id: str) -> dict[str, Any]:
        """Expand one method neighborhood, including ordered steps and source pointers."""
        return self._call(lambda: self._method_graph().read(method_id))

    def check_method_requirements(self, method_id: str,
                                  observed_conditions: list[dict[str, Any]]) -> dict[str, Any]:
        """Compare your observed condition declarations with every registered prerequisite.

        Items need condition_id, status supported/contradicted/unknown, observation_ref
        and reason. This checks coverage, not the truth of model-declared observations.
        Unknown conditions remain unknown and never grant execution/scientific approval.
        """
        return self._call(lambda: self._method_graph().assess(method_id, observed_conditions))

    def read_analysis_feedback(self, limit: int = 6) -> dict[str, Any]:
        """Read actual protected failed tool observations and your recorded hypotheses."""
        return self._call(lambda: self.feedback_journal.recent(limit))

    def record_analysis_reflection(self, observation_id: str, hypothesis: str,
                                   next_check: str,
                                   knowledge_ids: list[str] | None = None) -> dict[str, Any]:
        """Record your own falsifiable diagnosis of an actual failed observation.

        No fix or reference answer is supplied. Perform the proposed check, retrieve
        missing evidence, change your generated code and execute to test recovery.
        """
        return self._call(lambda: self.feedback_journal.reflect(
            observation_id, hypothesis, next_check, knowledge_ids))

    def search_evidence(
        self, query: str, kinds: list[str] | None = None, limit: int = 5,
    ) -> dict[str, Any]:
        """Search typed evidence; the default is registered original source_text only.

        kinds may select source_text, software_contract or method when the profile
        permits them. Prefer specific software and English entrypoint terms.
        Each hit has id, kind, title, snippet, source_url and release_sha256.
        """
        from .analysis_evidence import EvidenceGateway

        gateway = EvidenceGateway(self.knowledge, self._method_graph, self.knowledge_profile)
        return self._call(lambda: gateway.search(query, kinds, limit))

    def read_evidence(
        self, id: str, start_char: int = 0, max_chars: int = 8000,
    ) -> dict[str, Any]:
        """Read a prefixed registered ID, enforcing this profile's allowed evidence kinds.

        Source text supports a bounded cursor; follow next_read when truncated.
        Graph hints and software contracts never establish scientific applicability.
        """
        from .analysis_evidence import EvidenceGateway

        gateway = EvidenceGateway(self.knowledge, self._method_graph, self.knowledge_profile)
        return self._call(lambda: gateway.read(id, start_char, max_chars))

    def search_knowledge(self, query: str, limit: int = 5) -> dict[str, Any]:
        """Search versioned tutorial and method evidence; results are reference data."""
        return self._call(lambda: {"status": "ok", "results": self.knowledge.search(
            query[:2000], limit=max(1, min(limit, 5)))})

    def search_method_knowledge(self, query: str, limit: int = 10) -> dict[str, Any]:
        """Retrieve source-reviewed structural MRI method statements; no execution authorization."""
        return self._call(lambda: self.knowledge.search_method_knowledge(query, limit))

    def search_software_graph(self, query: str, limit: int = 5) -> dict[str, Any]:
        """Find candidate software input/output/parameter nodes and source links."""
        return self._call(lambda: self.knowledge.search_source_graph(query, limit))

    def read_software_graph(self, node_id: str) -> dict[str, Any]:
        """Read a registered candidate graph node, relations and original code span."""
        return self._call(lambda: self.knowledge.read_source_graph(node_id))

    def search_research_knowledge(self, query: str, limit: int = 5,
                                  high_level_keywords: list[str] | None = None,
                                  low_level_keywords: list[str] | None = None) -> dict[str, Any]:
        """Retrieve candidate research source parents, LightRAG hints and domain nodes.

        Prefer explicit software/entrypoint and English technical terms. Supply
        high/low level keywords when useful. Read returned source IDs to inspect
        full registered excerpts and conditions; search hits are not source reading.
        """
        return self._call(lambda: self.knowledge.search_research(
            query, limit, high_level_keywords, low_level_keywords))

    def read_research_knowledge(self, source_id: str, start_char: int = 0,
                                max_chars: int = 8000) -> dict[str, Any]:
        """Read a registered original parent excerpt or domain node with source spans.

        Use the returned cursor if truncated. IDs never become arbitrary paths.
        Candidate graph hints and software labels do not establish applicability,
        installed compatibility, anatomy, or cross-species biological homology.
        """
        return self._call(lambda: self.knowledge.read_research(source_id, start_char, max_chars))

    def read_knowledge(self, knowledge_id: str) -> dict[str, Any]:
        """Read one knowledge record by its catalogue ID, never an arbitrary path."""
        return self._call(lambda: self.knowledge.read(knowledge_id))

    def list_data(self, path: str = "/inputs") -> dict[str, Any]:
        """List approved /inputs/N data or generated /work files; no host paths."""
        def operation() -> dict[str, Any]:
            if path == "/inputs":
                return {"status": "ok", "entries": [
                    {"path": f"/inputs/{i}", "label": root.name,
                     "type": "directory", "read_only": True}
                    for i, root in enumerate(self.input_roots)]}
            directory = self.resolve(path)
            if not directory.is_dir():
                raise ValueError("Expected a directory")
            entries = []
            for item in sorted(directory.iterdir(), key=lambda p: p.name)[:100]:
                if item.is_symlink():
                    continue
                entries.append({"name": item.name, "type": "directory" if item.is_dir()
                                else "file", "size": item.stat().st_size})
            return {"status": "ok", "entries": entries}
        return self._call(operation)

    def _navigate(self, name: str, **arguments: Any) -> dict[str, Any]:
        def operation():
            result = getattr(self.data, name)(**arguments)
            self.navigation_calls += 1
            return result
        return self._call(operation)

    def list_roots(self) -> dict[str, Any]:
        """List actual input directory paths, Python /inputs/N mappings, and the output location."""
        return self._navigate("list_roots")

    def ls(self, path: str = "/inputs", offset: int = 0, limit: int = 100) -> dict[str, Any]:
        """List files/directories with pagination, using a registered absolute path or /inputs/N."""
        return self._navigate("ls", path=path, offset=offset, limit=limit)

    def glob(self, pattern: str = "*.nii*", path: str = "/inputs", max_depth: int = 10,
             limit: int = 200) -> dict[str, Any]:
        """Find files recursively by wildcard filename/path; source and output directories are independent."""
        return self._navigate("glob", pattern=pattern, path=path, max_depth=max_depth, limit=limit)

    def grep(self, pattern: str, path: str = "/inputs", file_pattern: str = "*",
             ignore_case: bool = False, limit: int = 50) -> dict[str, Any]:
        """Search literal text across code, tables, logs and FreeSurfer stats, returning line numbers."""
        return self._navigate("grep", pattern=pattern, path=path, file_pattern=file_pattern,
                              ignore_case=ignore_case, limit=limit)

    def read_file(self, path: str, start_line: int = 1, max_lines: int = 100) -> dict[str, Any]:
        """Read text/code/log/stats with line numbers from a registered directory or /work."""
        return self._navigate("read_file", path=path, start_line=start_line, max_lines=max_lines)

    def discover_subjects(self, path: str = "/inputs", limit: int = 100,
                          max_depth: int = 12) -> dict[str, Any]:
        """Discover BIDS, subject/T1 or flat NIfTI candidates; return ambiguities and actual paths."""
        return self._navigate("discover_subjects", path=path, limit=limit, max_depth=max_depth)

    def submit_pipeline(self, subject_id: str, t1_path: str, steps: list[str], species: str,
                        seg_species: str = "", brain_size: int | None = None,
                        denoise: bool = True) -> dict[str, Any]:
        """Submit user-requested PrimateX processing for a discovered T1 in any registered data directory.

        Pass species from the user or dataset metadata. Outputs use the authenticated
        output directory. Repeated identical requests reuse their task ID. Existing
        outputs are preserved. This queues a task; it does not finish reconstruction.
        """
        def operation():
            if self.pipeline is None:
                raise ValueError("Pipeline submission requires an authenticated output workspace")
            return self.pipeline.submit_pipeline(subject_id, t1_path, steps, species,
                                                  seg_species, brain_size, denoise)
        return self._call(operation)

    def pipeline_status(self, task_id: str) -> dict[str, Any]:
        """Inspect a submitted pipeline task's state and log in this user's output workspace."""
        def operation():
            if self.pipeline is None:
                raise ValueError("No authenticated pipeline workspace")
            result = self.pipeline.pipeline_status(task_id)
            self.navigation_calls += 1
            return result
        return self._call(operation)

    def read_data(self, path: str, max_chars: int = 12_000) -> dict[str, Any]:
        """Read bounded UTF-8 text from approved data or /work; inspect images in Python."""
        def operation() -> dict[str, Any]:
            source = self.resolve(path)
            if source.suffix.lower() not in {".csv", ".tsv", ".json", ".txt", ".md",
                                          ".py", ".log", ".yaml", ".yml"}:
                raise ValueError("Binary images must be inspected by sandboxed Python")
            limit = max(1, min(max_chars, 12_000))
            root = self.workdir if _inside(source, self.workdir) else next(
                root for root in self.input_roots if _inside(source, root))
            data = _read_regular(source, root, limit + 1)
            return {"status": "ok", "content": data[:limit].decode("utf-8", "replace"),
                    "truncated": len(data) > limit}
        return self._call(operation)

    def write_code(self, path: str, code: str) -> dict[str, Any]:
        """Write syntactically valid Python only beneath /work, e.g. /work/analysis.py."""
        def operation() -> dict[str, Any]:
            if self.analysis_jobs:
                raise ValueError("A frozen analysis job was submitted; continue after its recorded result in a new phase")
            target = self.resolve(path, writable=True)
            if target.suffix != ".py":
                raise ValueError("write_code only writes .py files")
            if len(code.encode("utf-8")) > MAX_CODE_BYTES:
                raise ValueError("Python source is too large")
            compile(code, path, "exec")
            with self._execution_lock:
                mapped = "/work/" + target.relative_to(self.workdir).as_posix()
                if self.session is not None:
                    self.session.guard_write(mapped)
                target.parent.mkdir(parents=True, exist_ok=True)
                _write_regular(target, self.workdir, code)
                if self.session is not None:
                    self.session.wrote_code(mapped)
            return {"status": "written", "path": "/work/" + target.relative_to(
                self.workdir).as_posix(), "syntax_valid": True}
        return self._call(operation)

    def finalize_artifacts(self, artifacts: list[dict[str, Any]]) -> dict[str, Any]:
        """Finalize actual files after successful execution with the unchanged validator.

        Supply path, kind and meaningful optional expectations (columns, row_count,
        finite_columns, unique_columns, ranges, required_keys). Never guess image
        dimensions or text lengths. Missing mechanical fields come from actual
        files; explicit expectations remain binding. This tool does no analysis,
        changes no output data, reads no gold values and certifies no science.
        """
        def operation() -> dict[str, Any]:
            if self.session is not None:
                if (self.session.record.get("review_pending")
                        and self.last_execution.get("receipt_id") == self.session.record.get("rejected_execution_receipt_id")):
                    raise ValueError("Review repair requires revising and executing the sealed script before finalization")
                cached = self.session.existing_receipt()
                if cached is not None:
                    return cached
                _, missing = self.session.artifact_contract()
                if missing:
                    raise ValueError("; ".join(missing))
                if self.session.state()["phase"] == "executed_failed":
                    detail = "; ".join(self.session.record.get("missing", []))
                    raise ValueError(detail + "; repair outputs and execute the sealed script again before finalization")
            return self._finalize_artifacts_impl(artifacts)
        return self._call(operation)

    def _finalize_artifacts_impl(self, artifacts: list[dict[str, Any]]) -> dict[str, Any]:
        from .analysis_finalization import derive_manifest
        from .analysis_validation import ArtifactValidator, MANIFEST_NAME
        with self._execution_lock:
            # Every new finalization attempt invalidates its predecessor,
            # including requests rejected before a new manifest is written.
            old_manifest = self.workdir / MANIFEST_NAME
            _no_links(old_manifest, self.workdir)
            if old_manifest.exists():
                old_manifest.rename(self.workdir / (".previous-finalization-" + uuid.uuid4().hex + ".json"))
            rid = self.last_execution.get("receipt_id")
            if (self.last_execution.get("status") != "success"
                    or self.last_execution.get("exit_code") != 0
                    or not isinstance(rid, str) or len(rid) != 32
                    or any(c not in "0123456789abcdef" for c in rid)):
                raise ValueError("A real successful execution receipt is required")
            eroot = self.workdir.parent / ".execution_receipts" / self.workdir.name
            _no_links(eroot, self.workdir.parent)
            eraw = _read_regular(eroot / (rid + ".json"), eroot, 512 * 1024 + 1)
            if len(eraw) > 512 * 1024:
                raise ValueError("Execution receipt exceeds bounds")
            executed = json.loads(eraw)
            if (executed.get("receipt_id") != rid
                    or executed.get("schema_version") != "primatex.execution_receipt.v1"
                    or executed.get("result", {}).get("status") != "success"
                    or executed.get("result", {}).get("exit_code") != 0
                    or executed.get("script_sha256_before") != executed.get("script_sha256_after")):
                raise ValueError("Execution receipt is not a consistent successful run")
            script = self.resolve(executed["script"], writable=True)
            if hashlib.sha256(_read_regular(script, self.workdir, MAX_CODE_BYTES)).hexdigest() != executed["script_sha256_after"]:
                raise ValueError("Executed script changed after its receipt; execute it again")
            manifest, observations = derive_manifest(self.workdir, artifacts)
            content = json.dumps(manifest, ensure_ascii=False, indent=2)
            _write_regular(self.workdir / MANIFEST_NAME, self.workdir, content)
            checked = ArtifactValidator().validate(self.workdir)
            fid = uuid.uuid4().hex
            froot = self.workdir.parent / ".artifact_receipts" / self.workdir.name
            _no_links(froot, self.workdir.parent)
            froot.mkdir(parents=True, exist_ok=True)
            receipt = {"schema_version": "primatex.artifact_receipt.v1", "receipt_id": fid,
                       "timestamp": time.time(), "execution_receipt_id": rid,
                       "manifest_sha256": hashlib.sha256(content.encode()).hexdigest(),
                       "supplied_constraints": artifacts, "observations": observations,
                       "validation": checked}
            _write_regular(froot / (fid + ".json"), froot, json.dumps(receipt, ensure_ascii=False))
            return {"status": "finalized" if checked.get("valid") else "artifact_contract_failed",
                    "artifact_receipt_id": fid, "manifest_sha256": receipt["manifest_sha256"],
                    "last_execution_receipt_id": rid, "observations": observations,
                    "validation": checked, "independent_numeric_status": "not_configured",
                    "scientific_status": "not_evaluated"}

    def submit_python_job(self, path: str, artifacts: list[dict[str, Any]],
                          timeout_seconds: int = 7200) -> dict[str, Any]:
        """Submit one complete generated Python analysis as a detached compute job.

        Operator enablement required. Generate the FULL software/statistics/figure/
        report code first and declare every required output and meaningful rules.
        Uses a fresh /work snapshot with identical readonly /inputs/N. Write outputs
        relative to /work, not to host paths. Source is frozen readonly. Default
        job ceiling7200s is separate from the unchanged foreground time budget.
        Submission ends the coding turn; the status API tracks actual computation
        and unchanged file checks, without further model calls. No success implied.
        """
        def reserve() -> None:
            with self._lock:
                if self.ledger:
                    self._load_budget(self.ledger.reserve("executions", MAX_EXECUTIONS))
                else:
                    if self.executions >= MAX_EXECUTIONS:
                        raise BudgetExceeded("Python execution budget exhausted")
                    self.executions += 1
        def operation() -> dict[str, Any]:
            from . import analysis_jobs as jobs
            with self._execution_lock:
                source = self.resolve(path, writable=True)
                if self.knowledge_profile.name in {"method_graph_gated", "product_graph_planner"}:
                    from .analysis_plans import execution_gate
                    gate = execution_gate(self, source, background=True)
                    if not gate["allowed"]:
                        return gate
                receipt = jobs.submit(self.workdir, self.input_roots, source,
                    timeout_seconds, artifacts, self.required_artifacts, reserve)
                self.analysis_jobs = [receipt]
                return receipt
        return self._call(operation)

    def run_python(self, path: str | None = None, timeout_seconds: int = 120) -> dict[str, Any]:
        """Execute generated Python in isolation, with an explicit bounded timeout.

        Defaults to120 seconds. Request a suitable timeout for long mature CLI
        calculations (integer1..3600); the server maximum and remaining total
        run time still apply. Effective limits are returned, never silently120.
        No analysis input/resolution changes are justified by a clock timeout.
        """
        def operation() -> dict[str, Any]:
            if self.analysis_jobs:
                raise ValueError("A frozen analysis job was submitted; do not execute competing foreground code")
            if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 3600:
                raise ValueError("timeout_seconds must be an integer in1..3600")
            with self._execution_lock:
                return execute()

        def execute() -> dict[str, Any]:
            selected_path = self.session.execution_path(path) if self.session is not None else path
            script = self.resolve(selected_path, writable=True)
            if script.suffix != ".py" or not script.is_file():
                raise ValueError("Expected an existing /work Python script")
            gate = {"allowed": True, "read_only": False}
            if self.knowledge_profile.name in {"method_graph_gated", "product_graph_planner"}:
                from .analysis_plans import execution_gate
                gate = execution_gate(self, script)
                if not gate["allowed"]:
                    self.last_execution = dict(gate)
                    return self.last_execution
            with self._lock:
                if self.ledger:
                    self._load_budget(self.ledger.reserve("executions", MAX_EXECUTIONS))
                else:
                    if self.executions >= MAX_EXECUTIONS:
                        raise BudgetExceeded("Python execution budget exhausted")
                    self.executions += 1
            remaining = int(self.deadline - time.time())
            if remaining < 1:
                raise BudgetExceeded("Analysis wall-clock budget exhausted")
            effective_timeout = min(timeout_seconds, MAX_EXECUTION_SECONDS, remaining)
            # A zero-exit script must not inherit the preceding attempt's contract.
            manifest = self.workdir / "analysis_manifest.json"
            _no_links(manifest, self.workdir)
            if manifest.exists() and not gate["read_only"]:
                manifest.rename(self.workdir / (".previous-manifest-" + uuid.uuid4().hex + ".json"))
            script_hash_before = hashlib.sha256(
                _read_regular(script, self.workdir, MAX_CODE_BYTES)).hexdigest()
            try:
                options = {"work_read_only": True} if gate["read_only"] else {}
                self.last_execution = _safe(self.executor.run(
                    script, timeout_seconds=effective_timeout, **options), self.secret)
                if self.knowledge_profile.name in {"method_graph_gated", "product_graph_planner"}:
                    self.last_execution["plan_gate"] = gate
                    if gate["read_only"] and self.last_execution.get("status") == "success":
                        self.last_execution["status"] = "inspected"
                        self.last_execution["scope"] = "read_only_inspection_not_production_analysis"
            except Exception as exc:
                # Never reuse a previous successful execution after an executor error.
                self.last_execution = {"status": "failed", "error": _safe(str(exc), self.secret)}
            self.last_execution["execution_limits"] = {
                "requested_timeout_seconds": timeout_seconds,
                "effective_timeout_seconds": effective_timeout,
                "server_maximum_seconds": MAX_EXECUTION_SECONDS,
                "remaining_run_seconds_before_execution": remaining,
            }
            if self.last_execution.get("status") == "timeout":
                self.last_execution["runtime_feedback"] = (
                    "The process reached its actual execution time limit. This does not "
                    "prove software/method failure. Inspect command logs and these limits. "
                    "Use an appropriate explicit timeout within the remaining budget for "
                    "long calculations; do not change image resolution or scientific "
                    "parameters merely to fit a time limit.")
            # Receipts live beside, not inside, the model-writable /work mount.
            # Their content comes from the executor, never model declarations.
            receipt_id = uuid.uuid4().hex
            receipt_root = self.workdir.parent / ".execution_receipts" / self.workdir.name
            _no_links(receipt_root, self.workdir.parent)
            receipt_root.mkdir(parents=True, exist_ok=True)
            receipt = {"schema_version": "primatex.execution_receipt.v1",
                       "receipt_id": receipt_id, "timestamp": time.time(),
                       "script": "/work/" + script.relative_to(self.workdir).as_posix(),
                       "script_sha256_before": script_hash_before,
                       "script_sha256_after": hashlib.sha256(
                           _read_regular(script, self.workdir, MAX_CODE_BYTES)).hexdigest(),
                       "result": dict(self.last_execution)}
            _write_regular(receipt_root / (receipt_id + ".json"), receipt_root,
                           json.dumps(receipt, ensure_ascii=False))
            self.last_execution["receipt_id"] = receipt_id
            if self.session is not None:
                self.session.after_execution()
            return self.last_execution
        return self._call(operation)


def _model_factory(**kwargs: Any) -> Any:
    from .analysis_provider import CompatibleChatOpenAI
    return CompatibleChatOpenAI(**kwargs)


def _build_coding_agent(tools: AnalysisTools, *, model: str, base_url: str,
                        api_key: str, model_factory: Callable[..., Any] | None = None) -> Any:
    from deepagents import create_deep_agent
    from deepagents.backends import StateBackend
    from langgraph.checkpoint.memory import InMemorySaver
    from langchain.agents.middleware import AgentMiddleware
    from langchain_core.messages import ToolMessage
    from langchain_core.tools import StructuredTool

    class FilesystemMiddleware(AgentMiddleware):
        """Replace Deep Agents' default virtual FS tools with our real data tools.

        create_deep_agent replaces a base middleware with the same public name.
        This avoids duplicate ls/glob/grep/read_file names pointing at virtual files.
        """

    class BudgetMiddleware(AgentMiddleware):
        def wrap_model_call(self, request: Any, handler: Callable[..., Any]) -> Any:
            # A resumed failed model node skips its completed before_model node.
            # Reserve at each real model invocation instead of that checkpoint.
            from .analysis_call_context import model_source
            tools._tick(model=True)
            with model_source("coding.model"):
                return self._invoke_model(request, handler)

        def _invoke_model(self, request: Any, handler: Callable[..., Any]) -> Any:
            if tools.model_context is None:
                return handler(request)
            view = tools.model_context.messages(request.messages)
            active = request.override(messages=view)
            if tools.session is not None:
                from .analysis_phase_tools import restrict_request, call_with_phase_choice
                active = restrict_request(tools, active)
                from .analysis_transport import model_deadline
                with model_deadline(tools.deadline):
                    return call_with_phase_choice(tools, active, handler)
            return handler(active)

        def wrap_tool_call(self, request: Any, handler: Callable[..., Any]) -> Any:
            if request.tool_call["name"] not in allowed_tool_names:
                if tools.events is not None:
                    tools.events.append("review", "failed", "Tool blocked by active profile",
                                        {"tool": request.tool_call["name"],
                                         "reason": "Tool is outside the filtered approved registry"})
                reason = (
                    "Tool disabled: use only approved analysis tools. "
                    "Subagents, host shells and virtual file writes are disabled."
                )
                if tools.session is not None:
                    tools._tick()
                    return ToolMessage(
                        content=json.dumps({"status": "error", "error": reason,
                                            "state": tools.session.state()}, ensure_ascii=False),
                        tool_call_id=request.tool_call["id"], status="error",
                    )
                return ToolMessage(content=reason, tool_call_id=request.tool_call["id"], status="error")
            from pydantic import ValidationError
            from langgraph.prebuilt.tool_node import ToolInvocationError

            def invoke_validated():
                if tools.session is not None:
                    from .analysis_phase_tools import phase_tools, read_error_allowed
                    name = request.tool_call["name"]
                    phase = tools.session.state()["phase"]
                    permitted = name in phase_tools(tools.session, allowed_tool_names)
                    if phase == "executed_failed" and name == "read_file" and getattr(tools, "execution_required", True):
                        permitted = permitted and read_error_allowed(tools, request.tool_call.get("args", {}))
                    if not permitted:
                        tools._tick()
                        return ToolMessage(content=json.dumps({
                            "status": "blocked", "error": "Tool unavailable in phase " + phase,
                            "available_tools": sorted(phase_tools(tools.session, allowed_tool_names)),
                            "state": tools.session.state(),
                        }), tool_call_id=request.tool_call["id"], status="error")
                # ToolNode may turn validation errors into plain ToolMessages
                # before returning to middleware. Validate the same registered
                # Pydantic schema here so this failure has structured state.
                schema = getattr(getattr(request, "tool", None), "args_schema", None)
                if tools.session is not None and hasattr(schema, "model_validate"):
                    schema.model_validate(request.tool_call.get("args", {}))
                if tools.session is not None:
                    from .analysis_planning_tools import reserve_action
                    reserve_action(tools, request.tool_call["name"])
                return handler(request)

            try:
                response = (
                    tools.events.call_tool(
                        request.tool_call["name"], request.tool_call.get("args", {}),
                        invoke_validated, tool_call_id=request.tool_call["id"],
                    ) if tools.events is not None else invoke_validated()
                )
            except (ToolInvocationError, ValidationError) as exc:
                if tools.session is not None and request.tool_call["name"] == "commit_plan":
                    tools.session.record["commit_argument_error"] = True
                if tools.session is None:
                    raise
                # Schema rejection happens before the tool function can reserve
                # its budget or append state. Count that actual failed attempt.
                tools._tick()
                response = ToolMessage(
                    content=json.dumps({
                        "status": "error", "argument_validation_failed": True,
                        "error": _safe(str(exc), tools.secret),
                    }, ensure_ascii=False),
                    tool_call_id=request.tool_call["id"], status="error",
                )
            if isinstance(response, ToolMessage) and isinstance(response.content, str):
                try:
                    payload = json.loads(response.content)
                except (ValueError, TypeError):
                    payload = None
                if tools.session is not None and not isinstance(payload, dict):
                    payload = {
                        "status": "error" if response.status == "error" else "ok",
                        "message": _safe(response.content, tools.secret),
                    }
                if isinstance(payload, dict) and tools.session is not None:
                    if request.tool_call["name"] == "commit_plan":
                        tools.session.record["commit_argument_error"] = payload.get("status") not in {"committed", "ok"}
                    payload["state"] = tools.session.state()
                    response.content = json.dumps(payload, ensure_ascii=False)
                if isinstance(payload, dict):
                    if (tools.session is not None and getattr(tools, "execution_required", True) is False
                            and request.tool_call["name"] in {"ls", "read_file"}):
                        tools.control_store.save("inspection_observation", {
                            "tool": request.tool_call["name"], "arguments": request.tool_call.get("args", {}),
                            "result": _safe(payload, tools.secret),
                        })
                    observation = tools.feedback_journal.observe(
                        request.tool_call["name"], request.tool_call.get("args", {}),
                        _safe(payload, tools.secret))
                    if observation:
                        payload["feedback_observation_id"] = observation["id"]
                        if observation["failed"]:
                            payload["reflection_required"] = True
                            payload["feedback_scope"] = "Actual tool failure; diagnose with record_analysis_reflection and check your hypothesis. No external fix or expected values supplied."
                        response.content = json.dumps(payload, ensure_ascii=False)
                    if tools.model_context is not None:
                        payload = tools.model_context.offload(request.tool_call["name"], payload)
                        response = response.model_copy(update={"content": json.dumps(payload, ensure_ascii=False)})
            return response

    functions = [tools.search_method_knowledge, tools.search_knowledge, tools.read_knowledge,
                 tools.search_software_graph, tools.read_software_graph, tools.search_research_knowledge,
                 tools.read_research_knowledge, tools.search_analysis_methods,
                 tools.read_analysis_method, tools.check_method_requirements,
                 tools.read_analysis_feedback, tools.record_analysis_reflection, tools.list_data,
                 tools.read_data, tools.write_code, tools.run_python, tools.finalize_artifacts, tools.inspect_analysis_runtime,
                 tools.list_roots, tools.ls, tools.glob, tools.grep, tools.read_file,
                 tools.discover_subjects, tools.submit_pipeline, tools.pipeline_status]
    if os.environ.get("ANALYSIS_ENABLE_BACKGROUND_JOBS", "0") == "1":
        functions.append(tools.submit_python_job)
    profile = tools.knowledge_profile
    if profile.name != "product_graph_planner":
        def run_python(path: str, timeout_seconds: int = 120) -> dict[str, Any]:
            return tools.run_python(path, timeout_seconds)
        run_python.__doc__ = AnalysisTools.run_python.__doc__
        functions = [run_python if fn.__name__ == "run_python" else fn for fn in functions]
    functions.extend([tools.search_evidence, tools.read_evidence])
    if profile.name in {"method_graph", "method_graph_gated", "product_graph_planner"}:
        functions.append(tools.read_operations)
    if profile.name in {"method_graph", "method_graph_gated"}:
        functions.extend([tools.profile_data, tools.compile_constraints, tools.commit_plan])
    if profile.name == "product_graph_planner":
        def record_analysis_reflection(observation_id: str, hypothesis: str = "", next_check: str = "") -> dict[str, Any]:
            """Inspect an actual failed observation. observation_id is the only required argument.

            Optionally record a substantive hypothesis and falsifiable next check.
            Acknowledging an error is not evidence that the error was corrected.
            """
            def operation():
                if hypothesis or next_check:
                    return tools.feedback_journal.reflect(observation_id, hypothesis, next_check)
                original = tools.feedback_journal._read(observation_id)
                if original.get("kind") != "observation" or not original.get("failed"):
                    raise ValueError("observation_id must reference an actual failed observation")
                tools.feedback_journal._write("reflection_acknowledgement", {
                    "observation_id": observation_id, "authorship": "analysis_agent_model",
                    "verification_status": "acknowledged_not_corrected",
                })
                return {"status": "ok", "observation_id": observation_id,
                        "observation": original["result"], "next": "Inspect the error, edit the sealed script and run it again"}
            return tools._call(operation)
        functions = [record_analysis_reflection if fn.__name__ == "record_analysis_reflection" else fn for fn in functions]
        def commit_plan(candidate_id: str, rationale: str, code_path: str) -> dict[str, Any]:
            """Seal one feasible plan_analysis candidate; explain your choice in 1-2 sentences.

            The program fills data, atlas, scope and constraints. Supply the exact
            /work/*.py path you will write and execute. Do not supply nested plans.
            """
            def operation():
                from .analysis_product_planner import commit_candidate
                with tools._execution_lock:
                    return commit_candidate(tools, candidate_id, rationale, code_path)
            return tools._call(operation)
        from .analysis_crossspecies import enabled as cross_enabled
        if cross_enabled(tools):
            def commit_plan(candidate_id: str, rationale: str, code_path: str,
                            success_criteria: str, failure_criteria: str, species: list[str],
                            scale_status: str, homology_evidence: list[str] | None = None) -> dict[str, Any]:
                """Seal the candidate with your nonempty success/failure standards and explicit species/scale declarations.

                Cross-species comparisons also require sourced homology references.
                Declarations cannot override observed hard checks.
                """
                commitment = {"success_criteria": success_criteria, "failure_criteria": failure_criteria,
                              "species": species, "scale_status": scale_status,
                              "homology_evidence": homology_evidence or []}
                def operation():
                    from .analysis_product_planner import commit_candidate
                    with tools._execution_lock:
                        return commit_candidate(tools, candidate_id, rationale, code_path, commitment)
                return tools._call(operation)

            def submit_conclusion(text: str, claim_scope: str, direction: str | None = None) -> dict[str, Any]:
                """Submit your conclusion for deterministic typed-claim review; rewrite when verdict is revised."""
                from .analysis_crossspecies import submit_conclusion as submit
                def operation():
                    result = submit(tools, text, claim_scope, direction)
                    card = result["conclusion_card"]
                    return {"status": result["status"], "must_rewrite": card["must_rewrite"],
                            "supported_rewrite_scope": card["supported_rewrite_scope"]}
                return tools._call(operation)
            functions.append(submit_conclusion)
        functions.extend([tools.plan_analysis, commit_plan])
    functions = filter_functions(functions, profile)
    allowed_tool_names = frozenset(function.__name__ for function in functions)
    manifest_example = {
        "schema_version": "primatex.analysis_manifest.v1",
        "artifacts": [{"path": "summary.json", "kind": "json",
                       "required_keys": ["methods", "limitations"]}],
    }
    from .analysis_validation import _RULES, _METADATA
    artifact_contract = {kind: sorted(fields | _METADATA) for kind, fields in _RULES.items()}
    prompt = build_system_prompt(profile, manifest_example, artifact_contract)
    tools.knowledge_metadata = {
        "knowledge_profile": profile.name,
        "exposed_tools": [function.__name__ for function in functions],
        "knowledge_tools": list(profile.exposed_tools),
        "include_domain_rules": profile.include_domain_rules,
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "profiles_sha256": profile.profiles_sha256,
        "exposure_scope": "Filtered explicit tools; framework-injected tools are denied unless listed",
    }
    if tools.control_store is not None:
        from .analysis_constraints import load_mapping
        tools.knowledge_metadata["constraint_probes_sha256"] = load_mapping()[1]
        if profile.name == "product_graph_planner":
            from .analysis_product_planner import load_knowledge
            tools.knowledge_metadata.update({name + "_sha256": load_knowledge(name)[1]
                                             for name in ("method_requirements", "pipeline_dependencies")})
        tools.knowledge_metadata["operations"] = {k: v for k, v in tools.operations_metadata.items() if k != "functions"}
        tools.knowledge_metadata["control_state_schema"] = "primatex.analysis_controls.v1"
    if tools.ledger is not None:
        tools.ledger.bind_knowledge_metadata(tools.knowledge_metadata)
    llm = (model_factory or _model_factory)(
        model=model, base_url=base_url, api_key=api_key,
        **coding_model_options(model, base_url))
    if os.environ.get("ANALYSIS_ENABLE_INTERNAL_REVIEW", "1") == "1":
        tools._internal_review_model = llm.bind(response_format={"type": "json_object"})
    return create_deep_agent(
        model=llm, tools=[StructuredTool.from_function(fn, return_direct=(fn.__name__ == "submit_python_job")) for fn in functions],
        system_prompt=prompt, backend=StateBackend(),
        middleware=[FilesystemMiddleware(), BudgetMiddleware()],
        checkpointer=InMemorySaver(),
    ).with_config({"configurable": {"thread_id": _digest(str(tools.workdir))}})


def _required_artifact_contract(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > 32:
        raise ValueError("required_artifacts must be a bounded list")
    for name in value:
        if (not isinstance(name, str) or not name or len(name) > 240
                or any(c in name for c in "\\:*?[]")
                or any(ord(c) < 32 or ord(c) == 127 for c in name)
                or name.startswith("/")
                or any(part in ("", ".", "..") or part.startswith(".") for part in name.split("/"))):
            raise ValueError("required_artifacts must contain plain relative output names")
    if len(set(value)) != len(value):
        raise ValueError("required_artifacts cannot contain duplicates")
    return sorted(value)


def _required_artifact_coverage(required: list[str], artifacts: list[dict]) -> dict[str, Any]:
    names = [x.get("path") for x in artifacts if isinstance(x, dict) and isinstance(x.get("path"), str)]
    matches = {name: [path for path in names if
                     (path == name if "/" in name else PurePosixPath(path).name == name)]
               for name in required}
    return {"required": required, "matches": matches,
            "missing": [name for name, paths in matches.items() if not paths],
            "ambiguous": [name for name, paths in matches.items() if len(paths) > 1],
            "complete": all(len(paths) == 1 for paths in matches.values()),
            "scope": "Caller task-output coverage only; not numerical or scientific acceptance"}


def _check_required_artifact_resume(previous: dict, required: list[str], resume: bool) -> None:
    if resume and _required_artifact_contract(previous.get("required_artifacts")) != required:
        raise ValueError("Resume requires the original required artifact contract")


def _build_graph(coding_agent: Any, tools: AnalysisTools, validator: Any,
                 checkpointer: Any) -> Any:
    from langgraph.graph import END, START, StateGraph

    def coding(state: AnalysisState) -> dict[str, Any]:
        before = tools.executions
        before_navigation = tools.navigation_calls
        feedback = state.get("feedback", "")
        required = _required_artifact_contract(state.get("required_artifacts"))
        tools.required_artifacts = required
        if tools.control_store is not None:
            tools.task_request = state["request"]
        request = state["request"]
        tools.execution_required = state.get("execution_required", True)
        if tools.session is not None:
            from .analysis_data_card import prepare_data_card
            try:
                card = prepare_data_card(tools, request)
                request = card["summary"] + "\n\nUSER REQUEST:\n" + request
            except Exception as exc:
                # Failed metadata discovery is observable, never invented success.
                notice = _safe(str(exc), tools.secret, 400)
                tools.control_store.save("data_card_failure", {"reason": notice})
                tools.events.append("data", "warn", "Data card unavailable; inspect inputs", {"reason": notice})
                request = "DATA CARD unavailable: " + notice + "\nInspect approved inputs, then plan.\n" + request
        if tools.session is not None and not tools.execution_required:
            from .analysis_inspection import instructions
            request += "\n\n" + instructions(tools)
        if required:
            request += "\nMandatory final artifact names from the caller task contract: " + json.dumps(required)
        request += ("\n\nValidation feedback to repair:\n" + feedback
                                      if feedback else "")
        coding_config = {"recursion_limit": 8 * MAX_MODEL_CALLS + 32,
                         "configurable": {"thread_id": _digest(str(tools.workdir))}}
        saved_coding = (coding_agent.get_state(coding_config)
                        if hasattr(coding_agent, "get_state") else None)
        has_context = bool(saved_coding and saved_coding.values.get("messages"))
        messages = ([{"role": "user", "content": "Continue in the same /work directory. "
                     "Reuse the observed inputs, generated code and execution results. "
                     "Validation feedback to repair:\n" + feedback}]
                    if has_context and feedback else
                    list(state.get("history", [])) + [{"role": "user", "content": request}])
        limited_failure = False
        try:
            # Resume an interrupted inner step without appending a human message
            # between an AI tool call and its pending tool response.
            result = coding_agent.invoke(None if has_context and saved_coding.next
                                         else {"messages": messages}, coding_config)
            response_messages = result.get("messages", [])
            last = response_messages[-1] if response_messages else None
            content = getattr(last, "content", "") if last is not None else ""
            if isinstance(last, dict):
                content = last.get("content", "")
            text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
            error = ""
        except Exception as exc:
            text, error = "", _safe(str(exc), tools.secret, 2000)
            from .analysis_transport import RateLimited, AuthenticationFailed
            limited_failure = isinstance(exc, RateLimited)
            auth_failure = isinstance(exc, AuthenticationFailed)
        execution = dict(tools.last_execution)
        if tools.executions == before:
            execution = {"status": "not_executed", "error": "No Python execution in this iteration"}
        if error:
            execution = {**execution, "agent_error": error}
            if limited_failure:
                execution["environment_rate_limited"] = True
            if auth_failure:
                execution["environment_auth_failed"] = True
        if tools.control_store is not None and execution.get("status") != "success" and not execution.get("environment_rate_limited") and not execution.get("environment_auth_failed"):
            constraints = tools.control_store.latest("constraints")
            if constraints and constraints["record"]["summary"]["block"]:
                execution = {**execution, "status": "blocked",
                             "reason": "Mapped hard prerequisites were observed blocked",
                             "constraints_sha256": constraints["sha256"],
                             "constraint_summary": constraints["record"]["summary"]}
        return {"draft_message": _safe(text, tools.secret, 6000),
                "execution": execution, "iterations": state.get("iterations", 0) + 1,
                "executions": tools.executions, "tool_calls": tools.tool_calls,
                "model_calls": tools.model_calls,
                "navigation_calls": tools.navigation_calls - before_navigation,
                "pipeline_tasks": tools.pipeline.receipts if tools.pipeline else [],
                "analysis_jobs": list(tools.analysis_jobs),
                "metadata": dict(tools.knowledge_metadata)}

    def validate(state: AnalysisState) -> dict[str, Any]:
        if state.get("execution", {}).get("environment_auth_failed"):
            return {"validation": {"valid": False, "passed": False, "scope": "environment_auth_failed",
                                   "scientific_status": "not_evaluated", "errors": ["Upstream permission denied; no retry"]}}
        if state.get("execution", {}).get("environment_rate_limited"):
            return {"validation": {"valid": False, "passed": False, "scope": "environment_rate_limited",
                                   "scientific_status": "not_evaluated", "errors": ["Upstream 429 retries exhausted; no model-failure verdict"]}}
        if (tools.control_store is not None and state.get("execution", {}).get("status") == "blocked"
                and state.get("execution", {}).get("constraints_sha256")):
            return {"validation": {"valid": False, "passed": False,
                "scope": "method_constraint_block", "scientific_status": "not_evaluated",
                "independent_numeric_status": "not_performed",
                "errors": ["Observed hard prerequisites are blocked; revise the method/data and recompile constraints, or report the missing prerequisites."],
                "constraint_summary": state["execution"]["constraint_summary"]}}
        if state.get("analysis_jobs"):
            return {"validation": {"valid": False, "passed": False,
                "scope": "analysis_job_submission", "scientific_status": "not_evaluated",
                "independent_numeric_status": "not_performed",
                "errors": [], "message": "Submitted work is not completed or numerically validated"}}
        if state.get("pipeline_tasks") and state.get("execution", {}).get("status") == "not_executed":
            passed = all(r.get("status") != "failed" for r in state["pipeline_tasks"])
            return {"validation": {"valid": passed, "passed": passed,
                "scope": "pipeline_submission", "scientific_status": "not_evaluated",
                "errors": [] if passed else ["Pipeline queue submission failed"]}}
        if (tools.session is None and state.get("execution_required", True) is False
                and state.get("navigation_calls", 0) and not tools.executions
                and not state.get("execution", {}).get("agent_error")
                and state.get("draft_message")):
            return {"validation": {"valid": True, "passed": True, "scope": "data_inspection",
                "scientific_status": "not_evaluated", "errors": []}}
        if tools.session is not None and state.get("execution_required", True) is False:
            from .analysis_inspection import validate as validate_inspection
            return {"validation": validate_inspection(tools, state.get("draft_message", ""))}
        try:
            result = dict(validator.validate(tools.workdir))
        except Exception as exc:
            result = {"valid": False, "passed": False, "errors": [_safe(str(exc), tools.secret)]}
        if state.get("execution", {}).get("status") != "success":
            result["valid"] = result["passed"] = False
            result["errors"] = list(result.get("errors", [])) + [
                "A successful sandboxed execution in the current iteration is required"]
        required = _required_artifact_contract(state.get("required_artifacts"))
        coverage = _required_artifact_coverage(required, result.get("artifacts", []))
        result["required_artifact_coverage"] = coverage
        if not coverage["complete"]:
            result["valid"] = result["passed"] = False
            result["errors"] = list(result.get("errors", [])) + [
                "Caller-required artifacts are missing or ambiguous in the validated manifest: "
                + json.dumps({"missing": coverage["missing"], "ambiguous": coverage["ambiguous"]})]
        result.setdefault("scientific_status", "not_evaluated")
        result.setdefault("independent_numeric_status", "not_configured")
        if tools.session is not None:
            from .analysis_output_contract import current_summary as public_summary
            public = public_summary(tools)
            result["public_output_contract"] = public
            if public["status"] == "fail":
                result["valid"] = result["passed"] = False
                result["errors"] = list(result.get("errors", [])) + [
                    error for item in public.get("files", []) for error in item["errors"]]
        if (result.get("valid") is True and result.get("passed", True) is True
                and getattr(tools, "_internal_review_model", None) is not None):
            from .analysis_internal_review import run_review
            result["artifact_structural_passed"] = True
            try:
                from .analysis_release import configured_research_root
                method_reader = None
                if ("read_analysis_method" in tools.knowledge_profile.exposed_tools
                        and configured_research_root()):
                    method_reader = lambda method_id: tools._method_graph().read(method_id)
                evidence_card = None
                if tools.session is not None:
                    from .analysis_review_evidence import build_evidence_card
                    evidence_card = build_evidence_card(tools, result)
                review = run_review(
                    tools.workdir, state["request"], result,
                    model=tools._internal_review_model,
                    reserve=lambda: tools._tick(model=True),
                    method_reader=method_reader, register_execution_receipts=tools.session is not None,
                    deadline=tools.deadline, evidence_card=evidence_card)
            except Exception as exc:
                from .analysis_transport import TransportExhausted, AuthenticationFailed
                unavailable = isinstance(exc, TransportExhausted)
                review = {"decision": "unreviewed" if unavailable else "insufficient_evidence",
                          "status": "unreviewed" if unavailable else "invalid",
                          "transport_exhausted": unavailable, "protocol_valid": False,
                          "findings": [], "limitations": [
                              "Internal review unavailable: " + _safe(str(exc), tools.secret, 1000)],
                          "scope": "AI consistency review not completed; outputs and original structural checks retained"}
                if isinstance(exc, AuthenticationFailed):
                    review["transport"] = {"upstream_status": exc.status_code, "failure_kind": "environment_auth_failed"}
            result["internal_review"] = _safe(review, tools.secret)
            if review.get("transport_exhausted") and review.get("transport", {}).get("upstream_status") in {401, 403}:
                result["scope"] = "environment_auth_failed"
            if review.get("transport_exhausted") and review.get("transport", {}).get("upstream_status") == 429:
                result["scope"] = "environment_rate_limited"
            if review.get("decision") != "pass":
                result["valid"] = result["passed"] = False
                result["errors"] = list(result.get("errors", [])) + [
                    "Internal Agent consistency review: " + json.dumps(review, ensure_ascii=False)]
        if tools.session is not None:
            from .analysis_independent_numeric import current_summary
            numeric = current_summary(tools)
            result["independent_numeric_status"] = numeric["status"]
            result["independent_numeric"] = numeric
            if numeric["status"] == "fail":
                result["valid"] = result["passed"] = False
            review = result.get("internal_review", {})
            if review.get("decision") == "revise" and review.get("protocol_valid") is True:
                # Reopen the phase even if the outer-round limit is now reached.
                # Only public/source review feedback is made visible to the model.
                tools.session.review_failed(result)
        return {"validation": _safe(result, tools.secret),
                "model_calls": tools.model_calls, "tool_calls": tools.tool_calls}

    def route(state: AnalysisState) -> str:
        validation = state.get("validation", {})
        if validation.get("scope") in {"environment_rate_limited", "environment_auth_failed"}:
            return "report"
        repair_available = (state["iterations"] < MAX_ROUNDS
                            and tools.model_calls < MAX_MODEL_CALLS
                            and tools.executions < MAX_EXECUTIONS
                            and tools.tool_calls < MAX_TOOL_CALLS)
        if tools.session is not None:
            from .analysis_planning_budget import planning_limit
            if (tools.session.state()["phase"] in {"unplanned", "planned"}
                    and tools.session.record.get("planning_model_calls", 0) >= planning_limit(MAX_MODEL_CALLS)):
                return "report"
            review = validation.get("internal_review", {})
            public_failed = validation.get("public_output_contract", {}).get("status") == "fail"
            revision = review.get("decision") == "revise" and review.get("protocol_valid") is True
            if public_failed or revision:
                return "repair" if repair_available else "report"
        if validation.get("independent_numeric_status") == "fail":
            return "report"
        if state.get("validation", {}).get("internal_review", {}).get("protocol_valid") is False:
            return "report"
        if state.get("analysis_jobs"):
            return "report"
        if state["validation"].get("valid") is True and state["validation"].get("passed", True) is True:
            return "report"
        if state.get("execution", {}).get("status") == "blocked":
            return "report"
        return "repair" if (state["iterations"] < MAX_ROUNDS
                             and tools.model_calls < MAX_MODEL_CALLS
                             and tools.executions < MAX_EXECUTIONS
                             and tools.tool_calls < MAX_TOOL_CALLS) else "report"

    def repair(state: AnalysisState) -> dict[str, Any]:
        from .analysis_independent_numeric import public_model_validation
        model_validation = (public_model_validation(state["validation"])
                            if tools.session is not None else state["validation"])
        if tools.session is not None and state.get("execution_required", True):
            tools.session.review_failed(model_validation)
        observation = tools.feedback_journal.observe("graph_validate", {}, model_validation)
        return {"feedback": json.dumps({"validation": model_validation,
                                        "execution": state.get("execution"),
                                        "feedback_observation_id": observation["id"] if observation else None,
                                        "next": "Form and test your own diagnosis; consult method/source evidence as needed. No external solution or reference answer is supplied."},
                                       ensure_ascii=False)}

    def report(state: AnalysisState) -> dict[str, Any]:
        validation = state["validation"]
        passed = validation.get("valid") is True and validation.get("passed", True) is True
        status = "completed" if passed else ("blocked" if state.get("execution", {}).get(
            "status") == "blocked" else "failed")
        prefix = ("代码已在隔离环境运行，产物通过结构与声明检查。"
                  if passed else "分析未通过执行或产物检查。")
        message = prefix + "这些检查不等于科学正确性或独立数值验证。"
        if passed and validation.get("scope") == "pipeline_submission":
            status = "submitted"
            message = "已提交 PrimateX 任务；预处理和皮层重建的完成情况请以任务状态及日志为准。"
        elif passed and validation.get("scope") == "data_inspection":
            status = "inspected"
            message = "已读取实际数据目录。"
            if tools.session is not None:
                from .analysis_inspection import render
                message = render(validation)
        if validation.get("scope") == "analysis_job_submission":
            status = "submitted" if all(x.get("status") not in ("failed", "unknown_after_worker_exit")
                for x in state.get("analysis_jobs", [])) else "failed"
            message = "已提交独立后台计算。请以作业完成记录、产物检查和后续数值核对为准；提交不等于分析完成。"
        if tools.session is not None and validation.get("internal_review", {}).get("decision") == "unreviewed":
            status = "incomplete_review"
            message = "Execution and output records are retained; internal review is unfinished after bounded attempts. Agent text below is an unreviewed draft."
        if validation.get("scope") == "method_constraint_block":
            status = "blocked"
            message = "方法前提未满足，分析已阻断。请换用满足条件的方法、补充缺失前提，或终止并报告缺项。尚未通过执行或科学验证。"
        if validation.get("independent_numeric_status") == "fail":
            status = "blocked"
            message = "The host independent comparison did not pass. See the result card; reference values are not exposed to the Agent."
        if validation.get("scope") == "environment_rate_limited":
            status = "environment_rate_limited"
            message = "Upstream rate limit persisted after bounded retries. This run is incomplete; no ability verdict was assigned."
        if state.get("draft_message") and validation.get("scope") != "data_inspection":
            message += "\n\n" + state["draft_message"]
        if not passed:
            message += "\n\n" + json.dumps(validation.get("errors", []), ensure_ascii=False)
        if tools.control_store is not None:
            from .analysis_plans import plan_history
            versions = plan_history(tools.control_store)
            checked = tools.control_store.latest("constraints")
            executed_version = state.get("execution", {}).get("plan_gate", {}).get("plan_version")
            if executed_version is not None:
                executed_plan = tools.control_store.read(f"plan.v{executed_version:06d}.json")
                reference = executed_plan["record"]["plan"]["constraints"]
                checked = tools.control_store.read(f"constraints.v{reference['version']:06d}.json")
                if checked["sha256"] != reference["sha256"]:
                    raise ValueError("Executed plan constraint reference mismatch")
            if checked:
                warnings = [row for row in checked["record"]["rows"] if row["verdict"] == "warn"]
                if any(row["constraint_id"] == "scale_consistent:physical_scale" for row in warnings):
                    message += "\n\n工具记录的范围限定：物理尺度未独立核实，数值仅按文件中存储的坐标与单位解释。"
                other_warnings = [row for row in warnings if row["constraint_id"] != "scale_consistent:physical_scale"]
                for warning in other_warnings:
                    message += "\n警告：" + warning["constraint_id"] + "；" + warning.get("tool_observed", {}).get("reason", "见 constraints.json")
                unresolved = checked["record"].get("unmapped_conditions", [])
                if unresolved:
                    message += f"\n另有 {len(unresolved)} 条方法前提没有检查器映射，仍为 unverified，详见 constraints.json。"
            if versions:
                message += "\n\n计划封存记录：\n" + "\n".join(
                    f"v{item['version']}：{item['revision_reason']}（SHA-256 {item['sha256']}）"
                    for item in versions)
        if validation.get("scope") == "environment_auth_failed":
            from .analysis_transport import AUTH_FAILURE_MESSAGE
            status = "environment_auth_failed"
            message = AUTH_FAILURE_MESSAGE
        history = (list(state.get("history", [])) + [
            {"role": "user", "content": state["request"]},
            {"role": "assistant", "content": message}])[-12:]
        return {"message": message, "status": status, "history": history,
                "artifacts": validation.get("artifacts", [])}

    graph = StateGraph(AnalysisState)
    for name, fn in [("coding", coding), ("validate", validate), ("repair", repair),
                     ("report", report)]:
        graph.add_node(name, tools.events.node(name, fn) if tools.events is not None else fn)
    graph.add_edge(START, "coding")
    graph.add_edge("coding", "validate")
    graph.add_conditional_edges("validate", route, {"repair": "repair", "report": "report"})
    graph.add_edge("repair", "coding")
    graph.add_edge("report", END)
    return graph.compile(checkpointer=checkpointer)


def _paths(workspace: Path, user_id: str, conversation_id: str) -> tuple[Path, Path, str]:
    if not user_id.strip() or not conversation_id.strip():
        raise ValueError("An authenticated owner and conversation ID are required")
    workspace = workspace.resolve(strict=True)
    if not workspace.is_dir():
        raise ValueError("Workspace must be an existing directory")
    conversation_hash = _digest(user_id + "\x00" + conversation_id)
    workdir = workspace / ".analysis_runs" / conversation_hash
    _no_links(workdir, workspace)
    workdir.mkdir(parents=True, exist_ok=True)
    state_root = Path(os.environ.get("AGENT_ANALYSIS_STATE_DIR", str(
        Path(__file__).resolve().parent.parent / ".analysis_state"))).resolve()
    if _inside(state_root, workdir) or _inside(workdir, state_root):
        raise ValueError("Checkpoint root and writable sandbox must not overlap")
    owner_dir = state_root / _digest(user_id)
    _no_links(owner_dir, state_root)
    owner_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    checkpoint = owner_dir / (conversation_hash + ".sqlite3")
    _no_links(checkpoint, state_root)
    return workdir, checkpoint, conversation_hash


def _run_sync(*, message: str, user_id: str, workspace: Path, conversation_id: str,
              model: str, base_url: str, api_key: str, input_roots: list[Path],
              resume: bool, model_factory: Callable[..., Any] | None,
              threads: int = 2, execution_required: bool = True,
              required_artifacts: list[str] | None = None,
              conversation_history: list[dict[str, str]] | None = None,
              router_model_calls: int = 0) -> dict[str, Any]:
    from langgraph.checkpoint.sqlite import SqliteSaver
    from .analysis_executor import SandboxExecutor
    from .analysis_knowledge import KnowledgeStore
    from .analysis_validation import ArtifactValidator

    if type(execution_required) is not bool:
        raise ValueError("execution_required must be an explicit boolean")
    if type(router_model_calls) is not int or router_model_calls not in {0, 1, 2}:
        raise ValueError("Expected zero, one or two precharged router calls")
    required_artifacts = _required_artifact_contract(required_artifacts)
    knowledge_profile = load_knowledge_profile()
    conversation_dir, checkpoint, thread_id = _paths(workspace, user_id, conversation_id)
    for root in input_roots:
        if root.is_symlink() or not root.is_dir():
            raise ValueError("Approved input roots must be existing real directories")
        if (_inside(checkpoint, root.resolve())
                or _inside(root.resolve(), checkpoint.parent.parent)):
            raise ValueError("Approved data must not expose server checkpoint storage")
    with _LOCKS_GUARD:
        lock = _LOCKS.setdefault(str(checkpoint), threading.Lock())
    with lock, closing(sqlite3.connect(str(checkpoint), timeout=30,
                                      check_same_thread=False)) as connection, connection:
        checkpointer = SqliteSaver(connection)
        config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 20}
        saved = checkpointer.get_tuple(config)
        previous = saved.checkpoint.get("channel_values", {}) if saved else {}
        _check_required_artifact_resume(previous, required_artifacts, resume)
        recorded_profile = previous.get("metadata", {}).get("knowledge_profile")
        if resume and recorded_profile is not None and recorded_profile != knowledge_profile.name:
            raise ValueError("Resume requires the original knowledge profile")
        if resume and recorded_profile is None and knowledge_profile.name != "legacy_v13":
            raise ValueError("Historical checkpoints require legacy_v13; exposure was not recorded")
        workspace_id = _digest(str(workspace.resolve()))
        input_roots_id = _digest("\x00".join(str(p.resolve()) for p in input_roots))
        if previous and previous.get("workspace_id") != workspace_id:
            raise ValueError("This conversation belongs to a different analysis workspace")
        if resume and not previous:
            raise ValueError("No saved analysis run exists for this owner/conversation")
        if resume and previous.get("input_roots_id") != input_roots_id:
            raise ValueError("Resume requires the original approved input roots")
        if resume and "execution_required" in previous and previous["execution_required"] != execution_required:
            raise ValueError("Resume requires the original execution scope")
        run_id = previous.get("run_id", "") if resume else uuid.uuid4().hex
        if not isinstance(run_id, str) or len(run_id) != 32 or any(
                char not in "0123456789abcdef" for char in run_id):
            raise ValueError("Invalid saved analysis run ID")
        workdir = conversation_dir / run_id
        _no_links(workdir, conversation_dir)
        workdir.mkdir(exist_ok=True)
        ledger_path = checkpoint.with_name(checkpoint.stem + ".budget.sqlite3")
        _no_links(ledger_path, checkpoint.parent)
        ledger = BudgetLedger(ledger_path, run_id)
        model_calls_before_request = ledger.snapshot()["model_calls"]
        for _ in range(router_model_calls):
            ledger.reserve("model_calls", MAX_MODEL_CALLS)
        executor = SandboxExecutor(workdir, input_roots)
        tools = AnalysisTools(workdir, input_roots, executor, KnowledgeStore(), api_key, ledger,
                              workspace=workspace, threads=threads,
                              knowledge_profile=knowledge_profile)
        tools.execution_required = execution_required
        from .agent_chat_state import ACTIVE_CHAT
        active_chat = ACTIVE_CHAT.get()
        if active_chat is not None and tools.session is not None:
            active_chat.analysis_tools = tools
        coding_agent = _build_coding_agent(tools, model=model, base_url=base_url,
                                           api_key=api_key, model_factory=model_factory)
        graph = _build_graph(coding_agent, tools, ArtifactValidator(), checkpointer)
        def invoke_graph(payload):
            try:
                return graph.invoke(payload, config)
            except Exception as exc:
                if tools.events is not None:
                    tools.events.append("result", "failed", "Run failed; records retained",
                                        {"error": _safe(str(exc), api_key, 500)})
                raise
        snapshot = graph.get_state(config)
        if resume:
            # A completed checkpoint is returned without rerunning code or the model.
            if not snapshot.next:
                result = previous
            else:
                result = invoke_graph(None)
        else:
            result = invoke_graph({"request": _safe(message, api_key, 20_000),
                                   "workspace_id": workspace_id, "input_roots_id": input_roots_id,
                                   "execution_required": execution_required,
                                   "required_artifacts": required_artifacts,
                                   "run_id": run_id,
                                   "history": (conversation_history if conversation_history is not None
                                               else previous.get("history", [])), "feedback": "",
                                   "iterations": 0, "executions": 0, "model_calls": 0,
                                   "tool_calls": 0, "status": "running", "validation": {},
                                   "execution": {}, "artifacts": [], "draft_message": "",
                                   "pipeline_tasks": [], "analysis_jobs": [], "navigation_calls": 0,
                                   "metadata": dict(tools.knowledge_metadata)})
        response = {key: result.get(key) for key in (
            "message", "status", "artifacts", "validation", "iterations", "run_id",
            "model_calls", "tool_calls", "executions", "pipeline_tasks", "analysis_jobs", "execution", "metadata")}
        if router_model_calls:
            response["model_calls"] = ledger.snapshot()["model_calls"]
            response["request_model_calls"] = response["model_calls"] - model_calls_before_request
        tools.report_execution = result.get("execution", {})
        from .analysis_crossspecies import enabled as cross_enabled
        if cross_enabled(tools):
            card = tools.control_store.latest("conclusion")
            if (card is None or card["record"].get("analysis_execution_receipt_id") != tools.last_execution.get("receipt_id")):
                from .analysis_crossspecies import submit_conclusion
                submit_conclusion(tools, result.get("draft_message") or "No Agent conclusion was submitted.", "unclassified")
                card = tools.control_store.latest("conclusion")
            response["conclusion_card"] = card["record"]
        elif tools.session is not None:
            from .analysis_independent_numeric import result_card
            response["conclusion_card"] = result_card(tools, result.get("draft_message", ""))
            from .analysis_overall_status import finalize_card
            response["conclusion_card"] = finalize_card(
                response["conclusion_card"], result.get("validation", {}), result["status"],
                result.get("execution", {}), tools.session.state()["phase"])
            card = response["conclusion_card"]
            saved_plan = tools.control_store.latest("plan")
            card["plan_sha256"] = saved_plan["sha256"] if saved_plan else None
            card["analysis_execution_receipt_id"] = tools.last_execution.get("receipt_id")
            tools.control_store.save("product_conclusion", card)
        if tools.session is not None:
            # Persist the same overall decision for POST and incremental event views.
            from .analysis_overall_status import finalize_card
            if cross_enabled(tools):
                response["conclusion_card"] = finalize_card(
                    response["conclusion_card"], result.get("validation", {}), result["status"],
                    result.get("execution", {}), tools.session.state()["phase"])
            response["overall_status"] = response["conclusion_card"]["overall_status"]
            response["component_statuses"] = response["conclusion_card"]["component_statuses"]
            tools.control_store.save("overall_result", {
                "overall_status": response["overall_status"],
                "component_statuses": response["component_statuses"], "native_status": result["status"],
            })
            from .analysis_planning_budget import planning_limit, EXECUTION_RESERVE
            response["phase_budget"] = {
                "planning_model_calls": tools.session.record.get("planning_model_calls", 0),
                "postseal_model_calls": tools.session.record.get("postseal_model_calls", 0),
                "planning_limit": planning_limit(MAX_MODEL_CALLS),
                "execution_reserve": EXECUTION_RESERVE,
                "model_calls_by_phase": tools.session.record.get("model_calls_by_phase", {}),
                "planning_includes_precharged_router_calls": True,
            }
        if tools.session is not None:
            from .analysis_failure_classification import classify
            response["failure_classification"] = classify({**response, "route": "analysis"})
        response["tools"] = result.get("pipeline_tasks", [])
        response["output_directory"] = workdir.relative_to(workspace.resolve()).as_posix()
        return _safe(response, api_key)


async def run_analysis(*, message: str, user_id: str, workspace: Path,
                       conversation_id: str, model: str, base_url: str,
                       api_key: str, input_roots: list[Path], resume: bool = False,
                       model_factory: Callable[..., Any] | None = None,
                       threads: int = 2, execution_required: bool = True,
                       required_artifacts: list[str] | None = None,
                       conversation_history: list[dict[str, str]] | None = None,
                       router_model_calls: int = 0) -> dict[str, Any]:
    """Run/resume one analysis; output_directory is relative to the approved workspace.

    New requests retain narrative history, but previous runs' files are not implicitly
    mounted. Continuing from those artifacts requires server-approved read-only inputs.
    Analysis requests require real execution and artifacts by default. Only explicit
    metadata-only requests may set execution_required=False. The scope is bound
    to a checkpoint and cannot be changed during resume.
    model_factory enables offline tests without changing the production tool boundary.
    """
    if type(execution_required) is not bool:
        raise ValueError("execution_required must be an explicit boolean")
    if not message.strip() and not resume:
        raise ValueError("Analysis message cannot be empty")
    return await asyncio.to_thread(_run_sync, message=message, user_id=user_id,
                                  workspace=Path(workspace), conversation_id=conversation_id,
                                  model=model, base_url=base_url, api_key=api_key,
                                  input_roots=[Path(p) for p in input_roots], resume=resume,
                                  model_factory=model_factory, threads=threads,
                                  execution_required=execution_required,
                                  required_artifacts=_required_artifact_contract(required_artifacts),
                                  conversation_history=conversation_history,
                                  router_model_calls=router_model_calls)
