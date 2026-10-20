"""Discover elsewhere, submit into the authenticated output namespace."""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import threading
from contextlib import closing
from pathlib import Path
from typing import Any

from .data_tools import DataTools, checked_path

_SUBMISSION_LOCK = threading.RLock()


class PipelineBridge:
    def __init__(self, data: DataTools, threads: int = 2):
        self.data = data
        self.threads = max(1, min(int(threads), 4))
        self.receipts: list[dict] = []

    def _database(self) -> Path:
        state = Path(os.getenv("AGENT_ANALYSIS_STATE_DIR", str(
            Path(__file__).resolve().parent.parent / ".analysis_state")))
        owner = hashlib.sha256(str(self.data.workspace).encode()).hexdigest()[:32]
        directory = checked_path(state / "pipeline_submissions" / owner)
        if any(directory == p or p in directory.parents for p in self.data.input_roots):
            raise ValueError("Pipeline receipts must be outside data inputs")
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = directory / "submissions.sqlite3"
        checked_path(path)
        return path

    def submit_pipeline(self, subject_id: str, t1_path: str, steps: list[str],
                        species: str, seg_species: str = "", brain_size: int | None = None,
                        denoise: bool = True) -> dict[str, Any]:
        """Submit requested PrimateX steps for a discovered T1; input stays in its data directory.

        Use only when the user has requested processing. Give a unique output subject_id.
        Species is required and must come from the user or metadata, not filename guessing.
        Existing nonempty output directories are preserved. Repeated identical submissions
        return their original task ID instead of rerunning the subject.
        """
        from .models import RunPipelineArgs
        from .pipeline import ensure_primx_exists, run_pipeline_task
        from .tools import init_task, validate_run_pipeline_args
        from . import tasks

        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,95}", subject_id):
            raise ValueError("subject_id must be 1–96 letters, digits, underscores or dashes")
        source = self.data.resolve(t1_path)
        if not source.is_file() or not source.name.endswith((".nii", ".nii.gz")):
            raise ValueError("t1_path must be an actual discovered NIfTI file")
        if source == self.data.workdir or self.data.workdir in source.parents:
            raise ValueError("Pipeline inputs must come from registered source data")
        if not species.strip():
            raise ValueError("Species must be supplied from user instructions or dataset metadata")
        output = checked_path(self.data.workspace / subject_id)
        args = RunPipelineArgs(subjectId=subject_id, workspaceDirectory=str(self.data.workspace),
            t1Path=str(source), steps=steps, species=species, segSpecies=seg_species or None,
            brainSize=brain_size, denoise=denoise, threads=self.threads, out_path=str(output))
        validate_run_pipeline_args(args)
        ensure_primx_exists()
        # Preserve a stable source identity without reading/hashing a large MRI volume.
        info = source.stat()
        payload = args.model_dump(by_alias=True, exclude_none=True)
        payload["sourceIdentity"] = [info.st_size, info.st_mtime_ns]
        signature = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        with _SUBMISSION_LOCK, closing(sqlite3.connect(str(self._database()), timeout=30)) as db, db:
            db.execute("CREATE TABLE IF NOT EXISTS submissions (signature TEXT PRIMARY KEY, "
                       "subject_id TEXT UNIQUE, task_id TEXT NOT NULL, receipt TEXT NOT NULL)")
            db.execute("BEGIN IMMEDIATE")
            previous = db.execute("SELECT receipt FROM submissions WHERE signature=?", (signature,)).fetchone()
            if previous:
                receipt = {**json.loads(previous[0]), "reused": True}
                self.receipts.append(receipt)
                return receipt
            if db.execute("SELECT 1 FROM submissions WHERE subject_id=?", (subject_id,)).fetchone():
                raise ValueError("This output subject already has a submission; choose a new subject_id")
            if output.exists() and (not output.is_dir() or any(output.iterdir())):
                raise ValueError("Output subject already contains results; choose a new subject_id")
            task = init_task(args)
            receipt = {"taskId": task.task_id, "subjectId": subject_id, "status": "pending",
                       "inputPath": str(source), "outPath": str(output), "steps": steps,
                       "reused": False}
            db.execute("INSERT INTO submissions VALUES (?, ?, ?, ?)",
                       (signature, subject_id, task.task_id, json.dumps(receipt)))
            # Commit the receipt before queueing: recovery never silently duplicates jobs.
            db.commit()
            tasks.TASKS.create(task)
            try:
                task.future = tasks.submit_pipeline_task(run_pipeline_task, task, args)
            except Exception as exc:
                task.status, task.error, task.message = "failed", str(exc), "Queue submission failed"
                receipt["status"] = "failed"
                receipt["error"] = "Queue submission failed; inspect this task before retrying"
            self.receipts.append(receipt)
            return receipt

    def pipeline_status(self, task_id: str) -> dict[str, Any]:
        """Read a submitted task's state and bounded log tail in this user's output namespace."""
        from .tasks import TASKS
        from .pipeline import task_response
        task = TASKS.get(task_id)
        if task:
            if checked_path(Path(task.workspace_directory)) != self.data.workspace:
                raise ValueError("Task belongs to another output workspace")
            result = task_response(task)
            if task.log_path:
                try:
                    output_reader = DataTools(self.data.workspace, [])
                    result["log"] = output_reader.read_file(task.log_path, max_lines=100)["content"]
                except (OSError, ValueError):
                    pass
            return result
        with closing(sqlite3.connect(str(self._database()), timeout=30)) as db:
            try:
                row = db.execute("SELECT receipt FROM submissions WHERE task_id=?", (task_id,)).fetchone()
            except sqlite3.OperationalError:
                row = None
        if row:
            return {**json.loads(row[0]), "status": "unknown_after_restart",
                    "message": "Submission receipt retained; inspect output logs before rerunning"}
        raise ValueError("No task found in this output workspace")


DATA_TOOL_NAMES = {"list_roots", "ls", "glob", "grep", "read_file", "discover_subjects",
                   "submit_pipeline", "pipeline_status"}


def tool_functions(data: DataTools, bridge: PipelineBridge):
    return [data.list_roots, data.ls, data.glob, data.grep, data.read_file,
            data.discover_subjects, bridge.submit_pipeline, bridge.pipeline_status]


def function_specs(data: DataTools, bridge: PipelineBridge) -> list[dict]:
    """Use the same typed schemas in the legacy pipeline loop and coding agent."""
    import inspect
    from typing import get_type_hints
    from pydantic import create_model
    specs = []
    for function in tool_functions(data, bridge):
        hints = get_type_hints(function)
        fields = {p.name: (hints[p.name], ... if p.default is inspect.Parameter.empty else p.default)
                  for p in inspect.signature(function).parameters.values()}
        schema = create_model(function.__name__ + "Args", **fields).model_json_schema()
        specs.append({"type": "function", "function": {"name": function.__name__,
            "description": inspect.getdoc(function), "parameters": schema}})
    return specs


def invoke_tool(data: DataTools, bridge: PipelineBridge, name: str, arguments: dict) -> dict:
    if name not in DATA_TOOL_NAMES:
        raise ValueError("Unknown data tool")
    functions = {f.__name__: f for f in tool_functions(data, bridge)}
    return functions[name](**arguments)
