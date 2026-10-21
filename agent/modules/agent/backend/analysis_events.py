"""Append-only, authenticated progress from actual tools and committed plans."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import time
import uuid

from .analysis_control_store import ControlStore, canonical, checked, digest

TERMINAL = {"done", "failed", "blocked"}
DATA_TOOLS = {
    "ls",
    "glob",
    "grep",
    "list_roots",
    "list_data",
    "discover_subjects",
    "read_file",
    "read_data",
    "inspect_analysis_runtime",
    "list-subjects", "list-files", "subject-tree", "find-t1", "list-samples", "use-sample-data",
}
KNOWLEDGE_TOOLS = {
    "search_evidence",
    "read_evidence",
    "search_analysis_methods",
    "read_analysis_method",
    "check_method_requirements",
    "load-skill",
    "read_operations",
}


def redact(value, secret=""):
    if isinstance(value, dict):
        return {
            str(key)[:100]: redact(item, secret)
            for key, item in value.items()
            if not re.search(
                r"api.?key|token|authorization|password|license|environment",
                str(key),
                re.I,
            )
        }
    if isinstance(value, list):
        return [redact(item, secret) for item in value[:128]]
    if isinstance(value, str):
        text = value.replace(secret, "[redacted]") if secret else value
        text = re.sub(
            r"(?i)bearer\s+[^\s,;]+|sk-[A-Za-z0-9_-]{8,}|(?:api[_-]?key|token|password)\s*[:=]\s*[^\s,;]+",
            "[redacted]",
            text,
        )
        return text[:1500]
    if value is None or type(value) in (int, float, bool):
        return value
    return str(type(value).__name__)


PIPELINE_TITLES = {
    "run-pipeline": "Submitting preprocessing task",
    "pipeline-status": "Checking preprocessing status",
    "cancel-pipeline": "Cancelling preprocessing task",
    "preprocess-1": "Submitting T1 preprocessing",
    "preprocess-3": "Submitting surface reconstruction",
    "seg-brain": "Submitting brain extraction",
    "seg-wm": "Submitting tissue segmentation",
    "acpc-alignment": "Submitting ACPC alignment",
    "rescale": "Submitting scale conversion",
    "freesurfer2caret": "Submitting surface export",
}


def tool_stage(name):
    if name in PIPELINE_TITLES:
        return "pipeline"
    if name in DATA_TOOLS or name == "profile_data":
        return "data"
    if name in KNOWLEDGE_TOOLS:
        return "knowledge"
    return {
        "compile_constraints": "constraints",
        "commit_plan": "plan",
        "plan_analysis": "plan",
        "write_code": "code",
        "run_python": "run",
        "submit_python_job": "run",
        "submit_pipeline": "run",
        "pipeline_status": "run",
        "finalize_artifacts": "review",
        "read_analysis_feedback": "repair",
        "record_analysis_reflection": "repair",
    }.get(name, "review")


def short_explanation(value):
    """English display text only; original tool receipts remain unchanged."""
    translations = {
        "换用满足现有条件的方法": "Choose a feasible method",
        "补充缺失数据或软件后重新检查": "Add prerequisites and recheck",
        "终止分析并报告缺失前提": "Stop and report missing prerequisites",
        "调用 profile_data 和 compile_constraints": "Profile data and compile constraints",
        "调用 commit_plan 封存计划后执行对应代码": "Seal a plan, then run its script",
    }
    text = translations.get(value, value)
    if re.search(r"[\u4e00-\u9fff]", text):
        text = "See linked evidence for details"
    return text if len(text) <= 40 else text[:37].rstrip() + "..."


def display_detail(value):
    """Bound narrative fields, preserving identifiers and observed evidence."""
    if not isinstance(value, dict):
        return value
    result = dict(value)
    for key in ("reason", "error", "summary_text"):
        if isinstance(result.get(key), str):
            result[key] = short_explanation(result[key])
    if isinstance(result.get("next_steps"), list):
        result["next_steps"] = [
            short_explanation(item) if isinstance(item, str) else item
            for item in result["next_steps"]
        ]
    return result


def title_for(name, args, result=None):
    """Derive short English titles from tool names and actual results."""
    result = result or {}
    if name == "load-skill":
        prefix = "Loaded skill: " if result else "Loading skill: "
        return (prefix + str(args.get("skillName", "instructions")))[:40]
    if name in PIPELINE_TITLES:
        return PIPELINE_TITLES[name]
    if name in DATA_TOOLS:
        label = str(args.get("path", "/inputs")).rstrip("/").split("/")[-1]
        title = "Inspect data: " + label
    elif name == "profile_data":
        count = len(args.get("paths", []))
        noun = "file" if count == 1 else "files"
        title = (
            f"Built data profile: {count} {noun}"
            if result
            else f"Profiling data: {count} {noun}"
        )
    elif name in KNOWLEDGE_TOOLS:
        label = str(
            args.get("method_id") or args.get("query") or args.get("id") or "evidence"
        )
        action = "Read method: " if name.startswith("read_") else "Search knowledge: "
        title = action + (label if label.isascii() else "source evidence")
    elif name == "compile_constraints":
        summary = result.get("summary")
        title = (
            f"Checks: {summary['pass']} pass / {summary['warn']} warn / {summary['block']} block"
            if summary
            else "Checking method requirements"
        )
    elif name == "plan_analysis":
        title = "Planned analysis candidates"
    elif name == "commit_plan":
        if result.get("status") == "committed":
            title = f"Plan sealed v{result['version']}"
        elif result.get("status") == "blocked":
            title = "Plan blocked: hard checks failed"
        else:
            title = "Checking plan prerequisites"
    elif name in {"write_code", "run_python"}:
        path = str(args.get("path", "script.py")).rstrip("/").split("/")[-1]
        prefix = "Wrote " if name == "write_code" else "Running "
        title = prefix + path
    else:
        title = {
            "submit_python_job": "Submitting background job",
            "submit_pipeline": "Submitting preprocessing task",
            "pipeline_status": "Checking preprocessing status",
            "finalize_artifacts": "Checking analysis outputs",
            "record_analysis_reflection": "Recording repair hypothesis",
            "read_analysis_feedback": "Reading tool feedback",
        }.get(name, "Checking tool result")
    return title[:40]


class AnalysisEvents:
    def __init__(self, store, secret=""):
        self.store = store
        self.secret = secret

    def all(self):
        path = self.store.path("events.jsonl")
        if not path.exists():
            return []
        if not path.is_file() or path.stat().st_size > 16 * 1024 * 1024:
            raise ValueError("Invalid event stream")
        rows = [json.loads(line) for line in path.read_bytes().splitlines() if line]
        if any(row.get("seq") != index + 1 for index, row in enumerate(rows)):
            raise ValueError("Event sequence is not contiguous")
        return rows

    def append(self, stage, status, title, detail=None, refs=None):
        if stage not in {
            "data",
            "knowledge",
            "constraints",
            "plan",
            "code",
            "run",
            "review",
            "repair",
            "result",
            "other",
            "pipeline",
        }:
            raise ValueError("Invalid event stage")
        if status not in {"running", "done", "warn", "blocked", "failed"}:
            raise ValueError("Invalid event status")
        with self.store.locked():
            row = {
                "seq": len(self.all()) + 1,
                "time": datetime.now(timezone.utc).isoformat(),
                "stage": stage,
                "status": status,
                "title": redact(title, self.secret)[:40],
                "detail": redact(display_detail(detail or {}), self.secret),
                "refs": redact(refs or [], self.secret),
            }
            descriptor = os.open(
                self.store.path("events.jsonl"),
                os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
                0o600,
            )
            with os.fdopen(descriptor, "ab") as stream:
                stream.write(canonical(row) + b"\n")
                stream.flush()
                os.fsync(stream.fileno())
        # ContextVars also propagate into asyncio.to_thread analysis workers.
        from .agent_chat_state import ACTIVE_CHAT
        session = ACTIVE_CHAT.get()
        if session is not None and session.store.root != self.store.root:
            session.mirror(row, self)
        return row

    def call_tool(self, name, args, handler, tool_call_id=None):
        stage = tool_stage(name)
        start = time.monotonic()
        operation_id = uuid.uuid4().hex
        identity = {"tool_call_id": tool_call_id} if tool_call_id else {}
        context = self.store.read("context.json") or {}
        post_commit = (context.get("knowledge_profile") == "product_graph_planner"
                       and name in DATA_TOOLS | KNOWLEDGE_TOOLS
                       and self.store.latest("plan") is not None)
        post_count = None
        if post_commit:
            post_count = self.store.save("post_commit_activity", {"tool": name,
                                        "tool_call_id": tool_call_id})["version"]
        safe_args = {
            key: args[key]
            for key in ("path", "query", "id", "method_id", "task_category", "skillName", "subjectId", "taskId")
            if key in args
        }
        self.append(
            stage,
            "running",
            title_for(name, args),
            {"tool": name, "operation_id": operation_id, **identity, **safe_args},
        )
        try:
            response = handler()
        except Exception as exc:
            self.append(
                stage,
                "failed",
                title_for(name, args),
                {"tool": name, "operation_id": operation_id, **identity, "error": str(exc)[:500]},
            )
            raise
        content = getattr(response, "content", response)
        payload = content if isinstance(content, dict) else None
        if isinstance(content, str):
            try:
                payload = json.loads(content)
            except (ValueError, TypeError):
                payload = None
        payload = payload if isinstance(payload, dict) else {}
        if post_commit:
            payload["plan_sealed_notice"] = "Plan sealed: write and run the analysis script next"
            payload["post_commit_retrieval_or_browse_count"] = post_count
            if hasattr(response, "content"):
                response.content = json.dumps(payload, ensure_ascii=False)
            elif isinstance(response, dict):
                response.update(payload)
        status = "done"
        if payload.get("status") == "blocked":
            status = "blocked"
        elif (
            payload.get("status") in {"error", "failed", "timeout"}
            or bool(payload.get("error"))
            or getattr(response, "status", None) == "error"
        ):
            status = "failed"
        elif payload.get("status") == "action_deferred":
            status = "warn"
        elif payload.get("summary", {}).get("warn"):
            status = "warn"
        if name == "plan_analysis" and payload.get("infeasible"):
            status = "warn"
        detail = {
            "tool": name,
            "operation_id": operation_id,
            **identity,
            "duration_seconds": round(time.monotonic() - start, 3),
        }
        for key in (
            "exit_code",
            "executed",
            "version",
            "plan_sha256",
            "profile_sha256",
            "constraints_sha256",
            "summary",
            "next_steps",
            "reason",
            "error",
            "blocked_constraints",
            "candidates",
            "needs_preprocessing",
            "infeasible",
            "plan_sealed_notice",
            "post_commit_retrieval_or_browse_count",
        ):
            if key in payload:
                detail[key] = payload[key]
        if status == "failed" and not detail.get("error") and isinstance(content, str):
            detail["error"] = content[:500]
        if payload.get("status") == "action_deferred":
            detail["reason"] = "Action deferred until skill review"
        if name == "plan_analysis" and payload.get("infeasible"):
            detail["reason"] = "; ".join(row["reason"] for row in payload["infeasible"] if row.get("reason"))
            detail["next_steps"] = ["Choose a feasible candidate", "Review missing prerequisites"]
        if name == "compile_constraints":
            detail["failures"] = [
                row for row in payload.get("rows", []) if row.get("verdict") == "block"
            ]
        # Explain observed missing commands without inventing a model diagnosis.
        if status == "blocked":
            failures = payload.get("blocked_constraints", payload.get("rows", []))
            missing = [
                command.get("command")
                for row in failures
                if row.get("verdict") == "block"
                for command in row.get("tool_observed", {}).get("commands", [])
                if command.get("executable") is False
                and isinstance(command.get("command"), str)
            ]
            if missing:
                names = ["MATLAB" if name == "matlab" else name for name in missing]
                detail["reason"] = "Missing software: " + ", ".join(names)
        if post_commit and status == "done":
            status = "warn"
        refs = [
            payload[key]
            for key in ("path", "protected_ref", "plan_sha256")
            if isinstance(payload.get(key), str)
        ]
        self.append(stage, status, title_for(name, args, payload), detail, refs)
        return response

    def node(self, name, fn, title_override=None):
        stage = {
            "coding": "data",
            "validate": "review",
            "repair": "repair",
            "report": "result",
        }[name]
        title = {
            "coding": "Planning and inspecting data",
            "validate": "Checking execution and outputs",
            "repair": "Repairing from tool feedback",
            "report": "Preparing analysis result",
        }[name]
        title = title_override or title

        def wrapped(state):
            operation_id = uuid.uuid4().hex
            self.append(
                stage,
                "running",
                title,
                {"graph_node": name, "operation_id": operation_id},
            )
            try:
                result = fn(state)
            except Exception as exc:
                self.append(
                    stage,
                    "failed",
                    title,
                    {"error": str(exc)[:500], "operation_id": operation_id},
                )
                raise
            status = "done"
            if name == "validate" and not result.get("validation", {}).get("valid"):
                status = "warn"
            if name == "report":
                status = (
                    "blocked"
                    if result.get("status") == "blocked"
                    else "failed" if result.get("status") == "failed" else "done"
                )
            end_title = title
            if name == "validate":
                end_title = (
                    "Output checks passed"
                    if status == "done"
                    else "Output checks need review"
                )
            self.append(
                stage,
                status,
                end_title,
                {
                    "graph_node": name,
                    "operation_id": operation_id,
                    "run_status": result.get("status"),
                },
            )
            return result

        return wrapped

    def plan_summary(self):
        item = self.store.latest("plan")
        if not item:
            return None
        record = item["record"]
        plan = record["plan"]
        checked_constraints = self.store.read(
            f"constraints.v{plan['constraints']['version']:06d}.json"
        )
        current = self.store.latest("constraints")
        evidence = record.get("method_evidence", {})
        from .analysis_plans import plan_history

        return {
            "version": item["version"],
            "sha256": item["sha256"],
            "data": plan["data"],
            "atlas": plan["atlas"],
            "method": {
                **plan["method"],
                "name": evidence.get("name", plan["method"]["method_id"]),
                "sources": evidence.get("sources", []),
            },
            "constraints": {**checked_constraints["record"]["summary"],
                            "unverified": len(checked_constraints["record"].get("unmapped_conditions", []))},
            "must_disclose": record["must_disclose"],
            "current_constraints_match": bool(
                current and current["sha256"] == record["constraints_sha256"]
            ),
            "code_path": plan["code_path"],
            "history": plan_history(self.store),
        }

    def view(self, after=0):
        rows = self.all()
        increment = [row for row in rows if row["seq"] > after][:200]
        terminal = next(
            (
                row
                for row in reversed(rows)
                if row["stage"] == "result" and row["status"] in TERMINAL
            ),
            None,
        )
        context = self.store.read("context.json") or {}
        return {
            "enabled": True,
            "events": increment,
            "last_seq": increment[-1]["seq"] if increment else after,
            "has_more": bool(increment and increment[-1]["seq"] < len(rows)),
            "status": terminal["status"] if terminal else "running",
            "plan": self.plan_summary(),
            "run_id": context.get("run_id"),
            "knowledge_profile": context.get("knowledge_profile"),
        }


def events_for_conversation(workspace, user_id, conversation_id, after=0):
    if (
        not isinstance(conversation_id, str)
        or not 1 <= len(conversation_id) <= 256
        or any(ord(c) < 32 for c in conversation_id)
    ):
        raise ValueError("Invalid conversation ID")
    if type(after) is not int or after < 0:
        raise ValueError("after must be a nonnegative sequence number")
    from .analysis_agent import _digest
    from .analysis_knowledge_profiles import load_knowledge_profile

    state = checked(
        Path(
            os.environ.get(
                "AGENT_ANALYSIS_STATE_DIR",
                str(Path(__file__).resolve().parent.parent / ".analysis_state"),
            )
        ).absolute()
    )
    from .agent_chat_state import conversation_events
    shared = conversation_events(workspace, user_id, conversation_id, after)
    if shared is not None:
        return shared
    conv = _digest(user_id + "\x00" + conversation_id)
    root = checked(state / _digest(user_id) / (conv + ".budget.controls"))
    candidates = []
    if root.is_dir():
        for path in root.iterdir():
            if re.fullmatch("[a-f0-9]{32}", path.name) and checked(path).is_dir():
                store = ControlStore(path, [workspace])
                context = store.read("context.json")
                if context and context.get("workspace_sha256") == _digest(
                    str(Path(workspace).resolve())
                ):
                    candidates.append((context["started_time"], store))
    if not candidates:
        enabled = load_knowledge_profile().name in {
            "method_graph",
            "method_graph_gated",
            "product_graph_planner",
        }
        return {
            "enabled": enabled,
            "events": [],
            "last_seq": 0,
            "has_more": False,
            "status": "pending" if enabled else "disabled",
            "plan": None,
            "run_id": None,
        }
    _, store = max(candidates, key=lambda item: item[0])
    return AnalysisEvents(store).view(after)
