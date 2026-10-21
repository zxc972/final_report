# Copyright (C) 2026 Wang Zheng Lab, Peking University
#
# This file is part of PrimateX.
#
# PrimateX is free software: you can redistribute it and/or modify it under the
# terms of the GNU Affero General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option) any
# later version.
#
# PrimateX is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR
# A PARTICULAR PURPOSE. See the GNU Affero General Public License for more
# details.
#
# If you use PrimateX in academic work, please cite:
# Xiaohui Yao*, Yichun Huang*, Kailong Cui*, ..., Shan Cong#, Zheng Wang#.
# Multi-agentic routing with PrimateX: standardized structural MRI analysis
# for non-human primates and humans.
#
# * Equal contribution.
# Correspondence (#): Shan Cong (shan.cong@hrbeu.edu.cn), Zheng Wang
# (zheng.wang@pku.edu.cn).
#
# See CITATION.cff for full citation details.

"""FastAPI app wiring for the agent backend."""

import base64
import hashlib
import hmac
import json
import os
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from urllib.parse import quote
from .analysis_artifacts import AnalysisFileRequest, read_analysis_file, list_generated_scripts, AnalysisJobStatusRequest
from pydantic import ValidationError

from .llm import call_chat_completions
from .agent_router import route_message
from .agent_chat_state import ChatSession, conversation_turn
from .models import AgentChatRequest, AgentChatResponse
from .skills import (
    deferred_action_result,
    load_knowledge,
    load_skills,
    parse_skill_load_requests,
    skill_catalog,
    skill_loaded_result,
    skill_loader_tool,
    skill_tools,
)
from .config import (
    DEFAULT_CUSTOM_BASE_URL,
    MAX_AGENT_ITERS,
    PLATFORM_API_BASE_URL,
    PLATFORM_API_KEY,
    PLATFORM_MODELS_PATH,
)
from .tasks import cancel_task, ensure_executor, normalize_max_workers, shutdown_cleanup, TASKS
from .tools import execute_tool
from .analysis_access import public_context, analysis_workspace, approved_input_roots
from .data_tools import DataTools
from .pipeline_bridge import PipelineBridge, DATA_TOOL_NAMES, function_specs, invoke_tool

ACCESS_TOKEN = os.getenv("PRIMX_ACCESS_TOKEN", "")
SAFE_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{2,31}$")


def task_duration_seconds(start_time: Optional[str], end_time: Optional[str]) -> Optional[int]:
    start = parse_task_datetime(start_time)
    if not start:
        return None
    end = parse_task_datetime(end_time) or datetime.now(timezone.utc)
    seconds = round((end - start).total_seconds())
    return seconds if seconds >= 0 else None


def parse_task_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def load_platform_models() -> List[Dict[str, str]]:
    """Models available through the server's own API key. Edit platform_models.json to change them."""
    try:
        return json.loads(PLATFORM_MODELS_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _derive_user_signing_key(salt_hex: str) -> bytes:
    """Mirrors server.js's deriveUserSigningKey: HMAC(ACCESS_TOKEN, salt), as a hex
    string, then used as the key for the next HMAC step (Node treats a string key as
    its UTF-8 bytes, so we encode the hex digest the same way here)."""
    digest_hex = hmac.new(ACCESS_TOKEN.encode("utf-8"), salt_hex.encode("utf-8"), hashlib.sha256).hexdigest()
    return digest_hex.encode("utf-8")


def _read_auth_record(user_dir: str) -> Optional[Dict[str, Any]]:
    try:
        with open(os.path.join(user_dir, ".auth.json"), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def verify_user_token(token: Optional[str], expected_user_id: str, salt_hex: Optional[str]) -> bool:
    """Verify a per-user session token issued by the Node pipeline backend's
    POST /api/users/auth, signed with a key derived from that user's current
    password salt — so a password change (which rotates the salt) immediately
    invalidates tokens issued before the change, without any shared session state."""
    if not token or not isinstance(token, str) or not salt_hex:
        return False
    parts = token.split(".")
    if len(parts) != 2:
        return False
    payload_b64, sig = parts
    expected_sig = hmac.new(_derive_user_signing_key(salt_hex), payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected_sig):
        return False
    try:
        padded = payload_b64 + "=" * (-len(payload_b64) % 4)
        payload = base64.urlsafe_b64decode(padded).decode("utf-8")
    except Exception:
        return False
    idx = payload.rfind(":")
    if idx == -1:
        return False
    user_id = payload[:idx]
    try:
        expires_at = int(payload[idx + 1:])
    except ValueError:
        return False
    if expires_at < int(time.time()):
        return False
    return user_id == expected_user_id


def sign_user_token(user_id: str, salt_hex: str) -> str:
    expires_at = int(time.time()) + 24 * 60 * 60
    payload = f"{user_id}:{expires_at}".encode("utf-8")
    payload_b64 = base64.urlsafe_b64encode(payload).decode("utf-8").rstrip("=")
    sig = hmac.new(_derive_user_signing_key(salt_hex), payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{sig}"


def require_user_token(token: Optional[str], user_id: str, user_dir: str) -> bool:
    record = _read_auth_record(user_dir)
    if not record or not record.get("salt"):
        return False
    return verify_user_token(token, user_id, record["salt"])


def build_app() -> FastAPI:
    """Create the FastAPI app with routes and middleware."""
    from .analysis_knowledge_profiles import load_knowledge_profile

    load_knowledge_profile()  # Invalid experiment names must fail before serving requests.
    app = FastAPI(title="PrimateX Agent Backend", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-User-Token"],
    )

    app.on_event("shutdown")(shutdown_cleanup)

    @app.middleware("http")
    async def attach_refreshed_user_token(request: Request, call_next):
        response = await call_next(request)
        refreshed = getattr(request.state, "refreshed_user_token", None)
        if refreshed:
            response.headers["X-User-Token"] = refreshed
        return response

    def require_token(request: Request) -> None:
        if not ACCESS_TOKEN:
            return
        auth = request.headers.get("authorization", "")
        if not auth.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Unauthorized")
        token = auth[7:].strip()
        if token != ACCESS_TOKEN:
            raise HTTPException(status_code=401, detail="Unauthorized")

    def request_user_token(request: Request) -> Optional[str]:
        return request.headers.get("x-user-token") or request.query_params.get("userToken")

    def require_safe_user_id(user_id: Optional[str]) -> str:
        if not user_id or not SAFE_ID_RE.match(user_id):
            raise HTTPException(
                status_code=400,
                detail="Invalid User ID: use 3-32 characters, letters, numbers, underscore, or dash; start with a letter or number",
            )
        return user_id

    def require_agent_task_access(request: Request, task: Any) -> None:
        # Agent task.workspace_directory is the user's output directory:
        # <workspaceRoot>/<userId>/output. The auth record lives one level above.
        workspace = Path(task.workspace_directory).resolve()
        user_dir = workspace.parent if workspace.name == "output" else workspace
        user_id = user_dir.name
        record = _read_auth_record(str(user_dir))
        if not record or not verify_user_token(request_user_token(request), user_id, record.get("salt")):
            raise HTTPException(status_code=401, detail="Please verify your User ID first on the Configuration page")
        request.state.refreshed_user_token = sign_user_token(user_id, record["salt"])

    @app.get("/api/agent/skills")
    async def list_skills(request: Request) -> Dict[str, Any]:
        require_token(request)
        skills = load_skills()
        return {
            "skills": [
                {"name": skill.name, "description": skill.description, "parameters": skill.parameters}
                for skill in skills
            ]
        }

    @app.get("/api/agent/models")
    async def list_models(request: Request) -> Dict[str, Any]:
        """List models available via the platform's own API key.
        Never returns the key itself — only model id/label pairs."""
        require_token(request)
        return {
            "models": load_platform_models(),
            "platformAvailable": bool(PLATFORM_API_KEY),
        }

    @app.get("/api/agent/tasks")
    async def list_agent_tasks(request: Request) -> Dict[str, Any]:
        """Return all agent-submitted pipeline tasks (running and pending).
        Used by Task Management to show tasks submitted via the Workflow Assistant."""
        require_token(request)
        user_id = request.query_params.get("userId")
        workspace_directory = request.query_params.get("workspaceDirectory")
        output_workspace: Optional[str] = None
        if user_id and workspace_directory:
            safe_user_id = require_safe_user_id(user_id)
            base_path = Path(workspace_directory).resolve()
            user_dir = (base_path / safe_user_id).resolve()
            try:
                user_dir.relative_to(base_path)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "The Workspace Directory is not valid for this User ID. "
                        "Please return to Configuration and use the default Workspace Directory."
                    ),
                )
            record = _read_auth_record(str(user_dir))
            if not record or not verify_user_token(request_user_token(request), safe_user_id, record.get("salt")):
                raise HTTPException(status_code=401, detail="Please verify your User ID first on the Configuration page")
            request.state.refreshed_user_token = sign_user_token(safe_user_id, record["salt"])
            output_workspace = str((user_dir / "output").resolve())

        with TASKS._lock:
            all_tasks = list(TASKS._tasks.values())
        if output_workspace:
            all_tasks = [
                t for t in all_tasks
                if str(Path(t.workspace_directory).resolve()) == output_workspace
            ]
        result = [
            {
                "taskId": t.task_id,
                "subjectId": t.subject_id,
                "workspaceDirectory": t.workspace_directory,
                "status": t.status,
                "currentStep": t.current_step,
                "message": t.message,
                "progress": t.progress,
                "steps": t.steps,
                "threads": t.threads,
                "startTime": t.start_time,
                "endTime": t.end_time,
                "durationSeconds": task_duration_seconds(t.start_time, t.end_time),
                "logPath": t.log_path,
                "source": "agent",
            }
            for t in all_tasks
        ]
        return {"tasks": result}

    @app.get("/api/agent/tasks/{task_id}/log")
    async def get_agent_task_log(task_id: str, request: Request) -> Dict[str, Any]:
        """Return the tail of an agent-submitted pipeline task log."""
        require_token(request)
        task = TASKS.get(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        require_agent_task_access(request, task)
        if not task.log_path:
            return {"taskId": task_id, "log": "(log not yet available)"}

        log_path = Path(task.log_path)
        if not log_path.exists():
            return {"taskId": task_id, "log": "(log not yet available)"}
        if not log_path.is_file():
            raise HTTPException(status_code=400, detail="Task log path is not a file")

        max_bytes = 64 * 1024
        size = log_path.stat().st_size
        with log_path.open("rb") as f:
            f.seek(max(0, size - max_bytes))
            data = f.read(max_bytes)
        return {"taskId": task_id, "log": data.decode("utf-8", errors="replace"), "size": size}

    @app.post("/api/agent/tasks/{task_id}/cancel")
    async def cancel_agent_task(task_id: str, request: Request) -> Dict[str, Any]:
        """Cancel an agent-submitted pipeline task."""
        require_token(request)
        task = TASKS.get(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        require_agent_task_access(request, task)

        cancel_task(task)
        return {"taskId": task.task_id, "status": task.status}

    @app.get("/api/agent/analysis/health")
    async def analysis_health(request: Request) -> Dict[str, Any]:
        require_token(request)
        import importlib.metadata
        versions = {}
        for package in ("langchain", "langgraph", "deepagents", "langchain-openai", "langgraph-checkpoint-sqlite"):
            try:
                versions[package] = importlib.metadata.version(package)
            except importlib.metadata.PackageNotFoundError:
                versions[package] = None
        return {"mode": "analysis", "dependenciesReady": all(versions.values()),
                "versions": versions, "execution": "isolated-python",
                "foundationTools": sorted(DATA_TOOL_NAMES),
                "pipelineImageConfigured": bool(os.getenv("PRIMATEX_PIPELINE_IMAGE")),
                "scientificValidation": "task-specific; not implied by successful execution"}

    @app.post("/api/agent/analysis/job/status")
    @app.post("/api/agent/analysis/job/cancel")
    async def analysis_job_status(payload: AnalysisJobStatusRequest, request: Request) -> Dict[str, Any]:
        require_token(request)
        context = payload.context
        user_id = require_safe_user_id(context.get("userId"))
        try:
            workspace = analysis_workspace(context.get("workspaceDirectory") or "", user_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        record = _read_auth_record(str(workspace.parent))
        if not record or not verify_user_token(context.get("userToken"), user_id, record.get("salt")):
            raise HTTPException(status_code=401, detail="Please verify your User ID first on the Configuration page")
        request.state.refreshed_user_token = sign_user_token(user_id, record["salt"])
        digest = hashlib.sha256((user_id + "\x00" + payload.conversation_id).encode()).hexdigest()[:32]
        workdir = workspace / ".analysis_runs" / digest / payload.run_id
        try:
            from .analysis_agent import _no_links
            from .analysis_jobs import status, cancel
            _no_links(workdir, workspace)
            operation = cancel if request.url.path.endswith("/cancel") else status
            job = operation(workdir, payload.job_id)
        except ImportError:
            raise HTTPException(status_code=503, detail="Background execution requires the Linux analysis runtime")
        except (OSError, ValueError):
            raise HTTPException(status_code=404, detail="No analysis job found in this user/conversation/run")
        source = job["output_relative"] + "/" + job["source_path"]
        return {"metadata": {"mode": "analysis", "status": job["status"],
            "run_id": payload.run_id, "output_directory": workdir.relative_to(workspace).as_posix(),
            "executions": 1 if job.get("execution") else 0, "analysis_jobs": [job],
            "validation": job.get("validation", {}), "artifacts": job.get("artifacts", []),
            "generated_scripts": [{"path": source, "sha256_current": job.get("source_sha256_current"),
                "matches_executed_code": job.get("source_matches_executed_code", False),
                "executions": ([{"status": job["execution"].get("status"),
                                "exit_code": job["execution"].get("exit_code"),
                                "sha256_executed": job["source_sha256"]}]
                               if job.get("execution") else [])}]},
            "conversationId": payload.conversation_id}

    @app.post("/api/agent/analysis/artifact")
    async def analysis_artifact(payload: AnalysisFileRequest, request: Request) -> Response:
        require_token(request)
        context = payload.context
        user_id = require_safe_user_id(context.get("userId"))
        try:
            workspace = analysis_workspace(context.get("workspaceDirectory") or "", user_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        record = _read_auth_record(str(workspace.parent))
        if not record or not verify_user_token(context.get("userToken"), user_id, record.get("salt")):
            raise HTTPException(status_code=401, detail="Please verify your User ID first on the Configuration page")
        request.state.refreshed_user_token = sign_user_token(user_id, record["salt"])
        try:
            data, name = read_analysis_file(workspace, user_id, payload.conversation_id,
                                            payload.run_id, payload.path)
        except OverflowError:
            raise HTTPException(status_code=413, detail="Analysis file exceeds the download limit")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid analysis output path")
        except OSError:
            raise HTTPException(status_code=404, detail="Analysis output file not found")
        return Response(content=data, media_type="application/octet-stream", headers={
            "Content-Disposition": "attachment; filename*=UTF-8''" + quote(name, safe=""),
            "X-Content-Type-Options": "nosniff", "Cache-Control": "no-store",
            "X-Content-SHA256": hashlib.sha256(data).hexdigest(),
        })

    @app.get("/api/agent/analysis/process-capabilities")
    async def analysis_process_capabilities(request: Request) -> Dict[str, Any]:
        require_token(request)
        from .analysis_knowledge_profiles import load_knowledge_profile
        profile = load_knowledge_profile()
        return {"enabled": profile.name in {"method_graph", "method_graph_gated", "product_graph_planner"}}

    @app.get("/api/agent/analysis/{conversation_id}/events")
    async def analysis_process_events(conversation_id: str, request: Request) -> Dict[str, Any]:
        require_token(request)
        user_id = require_safe_user_id(request.query_params.get("userId"))
        try:
            workspace = analysis_workspace(request.query_params.get("workspaceDirectory") or "", user_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        record = _read_auth_record(str(workspace.parent))
        if not record or not verify_user_token(request_user_token(request), user_id, record.get("salt")):
            raise HTTPException(status_code=401, detail="Please verify your User ID first on the Configuration page")
        request.state.refreshed_user_token = sign_user_token(user_id, record["salt"])
        try:
            after = int(request.query_params.get("after", "0"))
            from .analysis_events import events_for_conversation
            return events_for_conversation(workspace, user_id, conversation_id, after)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.post("/api/agent/analysis", response_model=AgentChatResponse, response_model_by_alias=True)
    async def analysis_chat(payload: AgentChatRequest, request: Request) -> AgentChatResponse:
        require_token(request)
        context = payload.context or {}
        user_id = require_safe_user_id(context.get("userId"))
        try:
            workspace = analysis_workspace(context.get("workspaceDirectory") or "", user_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        record = _read_auth_record(str(workspace.parent))
        if not record or not verify_user_token(context.get("userToken"), user_id, record.get("salt")):
            raise HTTPException(status_code=401, detail="Please verify your User ID first on the Configuration page")
        request.state.refreshed_user_token = sign_user_token(user_id, record["salt"])
        if payload.provider == "platform":
            if not PLATFORM_API_KEY:
                raise HTTPException(status_code=400, detail="Platform API key is not configured on the server")
            if payload.model not in {m.get("id") for m in load_platform_models()}:
                raise HTTPException(status_code=400, detail="Please select a valid platform model")
            base_url, api_key, model = PLATFORM_API_BASE_URL, PLATFORM_API_KEY, payload.model
        elif payload.provider == "custom" and payload.api_key and payload.model:
            base_url, api_key, model = payload.base_url or DEFAULT_CUSTOM_BASE_URL, payload.api_key, payload.model
        else:
            raise HTTPException(status_code=400, detail="Configure a platform model or custom provider credentials")
        workspace.mkdir(parents=True, exist_ok=True)
        try:
            input_roots = approved_input_roots(workspace, payload.input_roots)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        conv_id = payload.conversation_id or f"analysis_{uuid.uuid4().hex}"
        try:
            from .analysis_agent import run_analysis
            result = await run_analysis(message=payload.message, user_id=user_id,
                workspace=workspace, conversation_id=conv_id, model=model,
                base_url=base_url, api_key=api_key, input_roots=input_roots, resume=payload.resume,
                threads=max(1, min(int(context.get("threads", 2)), 4)),
                required_artifacts=context.get("requiredArtifacts"),
                **getattr(request.state, "auto_analysis_arguments", {}))
        except ImportError:
            raise HTTPException(status_code=503, detail="Analysis dependencies unavailable; use the coding environment")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc).replace(api_key, "[redacted]"))
        except Exception:
            raise HTTPException(status_code=500, detail="Analysis run failed; its checkpoint and artifacts are retained for diagnosis")
        result["generated_scripts"] = list_generated_scripts(workspace, user_id, conv_id, result.get("run_id", ""))
        return AgentChatResponse(message=result.get("message", "Analysis run finished"),
            conversationId=conv_id, metadata={
                "mode": "analysis",
                **{key: value for key, value in result.items() if key not in {"message", "metadata"}},
                **result.get("metadata", {}),
                "route": "analysis", "routeReason": "Explicit analysis mode",
            })

    async def pipeline_chat(payload: AgentChatRequest, request: Request,
                            session: ChatSession | None = None) -> AgentChatResponse:
        require_token(request)
        owns_session = False

        if payload.provider == "platform":
            if not PLATFORM_API_KEY:
                raise HTTPException(status_code=400, detail="Platform API key is not configured on the server")
            allowed_models = {m.get("id") for m in load_platform_models()}
            if not payload.model or payload.model not in allowed_models:
                raise HTTPException(status_code=400, detail="Please select a valid platform model")
            base_url, api_key, model = PLATFORM_API_BASE_URL, PLATFORM_API_KEY, payload.model
        elif payload.provider == "custom":
            if not payload.api_key:
                raise HTTPException(status_code=400, detail="apiKey is required for the custom provider")
            if not payload.model:
                raise HTTPException(status_code=400, detail="model is required for the custom provider")
            base_url = payload.base_url or DEFAULT_CUSTOM_BASE_URL
            api_key, model = payload.api_key, payload.model
        else:
            raise HTTPException(status_code=400, detail="provider must be 'platform' or 'custom'")

        skills = load_skills()
        if not skills:
            raise HTTPException(status_code=500, detail="No skills available")
        skills_by_name = {skill.name: skill for skill in skills}
        tools = [skill_loader_tool(skills)]

        system_message = {
            "role": "system",
            "content": (
                "You are the PrimateX T1 preprocessing and cortical reconstruction assistant. "
                "Skills and action tools use two distinct phases. First choose the relevant Skill "
                "from the catalog and call `load-skill`; this only loads trusted instructions and "
                "does not perform the action. Then review the loaded instructions, plan, and call "
                "the newly available action tool once if appropriate. Never claim that loading a "
                "Skill executed its action. "
                "If required parameters are missing, ask a concise clarification question. "
                "If any new Skill is loaded in a response containing other tool calls, every action "
                "in that response is deferred; re-plan and issue actions in the next response.\n\n"
                "AVAILABLE SKILLS (metadata only):\n"
                f"{skill_catalog(skills)}\n\n"
                "CRITICAL WORKSPACE RULES — follow these exactly:\n"
                "1. Always use the `workspaceDirectory` value from Context as the workspace root "
                "for ALL tool calls (run-pipeline, list-subjects, list-files, etc.). "
                "Never substitute a different path even if you discover data elsewhere.\n"
                "2. The `workspaceDirectory` in Context already encodes the user's namespace "
                "(e.g. /data/tests/<userId>/output). Pass it verbatim to every tool call.\n"
                "3. Source data and output workspace are independent. Use list_roots, ls, "
                "glob, grep, read_file and discover_subjects to locate actual inputs in "
                "registered data directories. These tools accept absolute server paths. "
                "Use submit_pipeline to process a discovered T1 directly, without copying "
                "it into output. Supply species from user instructions or metadata; never "
                "guess species or silently select one of multiple candidate scans. "
                "Only submit processing when the user requested it; otherwise report discovery.\n"
                "4. If `userId` is present in Context, treat it as the owner of all tasks; "
                "outputs must live inside the configured workspaceDirectory, not the repo root.\n"
                "5. If the user wants to try/test the pipeline with sample or demo data instead of "
                "uploading their own, call `list-samples` to see what's available, then `use-sample-data` "
                "to copy the chosen sample into the user's own workspace, and use the returned t1Path for "
                "run-pipeline. NEVER browse or use the raw sample pool path directly (e.g. via subject-tree "
                "or find-t1 against the default test workspace) — that bypasses the user's own namespace.\n"
                "6. Use the `threads` value from Context for Preprocess-3. It is the configured CPU thread "
                "count for each task (1-4), not the number of tasks to run concurrently. Do not replace it "
                "with `maxConcurrentTasks`."
            ),
        }
        knowledge = load_knowledge().strip()
        if knowledge:
            system_message["content"] += f"\n\nProject knowledge:\n{knowledge}"
        enforced_workspace: Optional[str] = None
        enforced_threads = 2
        data_tools = None
        pipeline_bridge = None
        data_specs: list[dict] = []
        if payload.context:
            max_workers_value = payload.context.get("maxConcurrentTasks")
            if max_workers_value is not None:
                ensure_executor(normalize_max_workers(max_workers_value))
            enforced_workspace = payload.context.get("workspaceDirectory") or None
            context_threads = payload.context.get("threads", 2)
            parsed_threads = (
                context_threads
                if isinstance(context_threads, int) and not isinstance(context_threads, bool)
                else 2
            )
            if 1 <= parsed_threads <= 4:
                enforced_threads = parsed_threads
            context_user_id = payload.context.get("userId")
            if context_user_id:
                # enforced_workspace is always "<root>/<userId>/output" (see InputArea.tsx),
                # so the user's own namespace — where .auth.json lives — is its parent dir.
                user_dir = str(Path(enforced_workspace).resolve().parent) if enforced_workspace else None
                record = _read_auth_record(user_dir) if user_dir else None
                if not record or not verify_user_token(payload.context.get("userToken"), context_user_id, record.get("salt")):
                    raise HTTPException(
                        status_code=401,
                        detail="Please verify your User ID first on the Configuration page",
                    )
                request.state.refreshed_user_token = sign_user_token(context_user_id, record["salt"])
                try:
                    output = analysis_workspace(enforced_workspace or "", context_user_id)
                    output.mkdir(parents=True, exist_ok=True)
                    roots = approved_input_roots(output, payload.input_roots)
                    data_tools = DataTools(output, roots)
                    pipeline_bridge = PipelineBridge(data_tools, enforced_threads)
                    data_specs = function_specs(data_tools, pipeline_bridge)
                except (ValueError, OSError) as exc:
                    raise HTTPException(status_code=400, detail=str(exc))
            system_message["content"] += f"\n\nContext: {json.dumps(public_context(payload.context), ensure_ascii=False)}"

        if session is None and data_tools is not None:
            session = ChatSession(output, context_user_id,
                                  payload.conversation_id or f"conv_{uuid.uuid4().hex}",
                                  api_key, 64)
            session.load_history(payload.history)
            session.start("pipeline", "Explicit preprocessing mode", automatic=False)
            owns_session = True

        tools = [*tools, *data_specs]

        messages: List[Dict[str, Any]] = [system_message]
        if payload.history:
            messages.extend(payload.history)
        messages.append({"role": "user", "content": payload.message})

        conv_id = (session.conversation_id if session is not None else
                   payload.conversation_id or f"conv_{uuid.uuid4().hex[:8]}")
        all_tool_results: List[Dict[str, Any]] = []
        loaded_skills: set[str] = set()
        final_text = ""
        hit_limit = False
        completed = False
        precharged = session.budget.view()["router_calls"] if session else 0
        budgeted_iterations = precharged
        total_iterations = precharged
        max_total_iterations = MAX_AGENT_ITERS + len(skills)
        wrap_requested = False

        while (
            budgeted_iterations < MAX_AGENT_ITERS
            and total_iterations < max_total_iterations
        ):
            total_iterations += 1
            attempt = session.budget.reserve("pipeline") if session else None
            try:
                response = await call_chat_completions(base_url, api_key, model, messages, tools)
            except Exception:
                if session:
                    session.budget.finish(attempt, None, "call_failed")
                    if owns_session:
                        session.complete(payload.message, "Preprocessing request failed", "failed")
                raise
            if session:
                session.budget.finish(attempt, response.get("usage"), "response_received")
            choice = response.get("choices", [{}])[0]
            model_message = choice.get("message", {})
            tool_calls = model_message.get("tool_calls") or []

            if not tool_calls:
                budgeted_iterations += 1
                final_text = model_message.get("content") or ""
                completed = True
                break

            messages.append(model_message)
            requested_skills, load_errors = parse_skill_load_requests(
                tool_calls,
                skills_by_name,
            )
            newly_loaded = requested_skills - loaded_skills

            if newly_loaded:
                for skill_name in sorted(newly_loaded):
                    skill = skills_by_name[skill_name]
                    system_message["content"] += (
                        "\n\nTRUSTED LOADED SKILL INSTRUCTIONS "
                        f"(`{skill.name}`, source `{skill.filename}`):\n"
                        "<loaded-skill>\n"
                        f"{skill.content}\n"
                        "</loaded-skill>"
                    )
                loaded_skills.update(newly_loaded)
                tools = [
                    skill_loader_tool(skills),
                    *data_specs,
                    *skill_tools(
                        [skills_by_name[name] for name in sorted(loaded_skills)]
                    ),
                ]

            def process_tool_call(call):
                tool_name = call.get("function", {}).get("name")
                call_id = call.get("id", "")

                # Strict phase barrier: once any new Skill is loaded, no action
                # from the same model response is allowed to execute.
                if newly_loaded:
                    if tool_name == "load-skill":
                        if call_id in load_errors:
                            result = {"error": load_errors[call_id], "executed": False}
                        else:
                            raw_args = call.get("function", {}).get("arguments", "{}")
                            skill_name = json.loads(raw_args).get("skillName")
                            result = skill_loaded_result(
                                skills_by_name[skill_name],
                                already_loaded=skill_name not in newly_loaded,
                            )
                            print(f"[agent][skill] loaded trusted instructions for {skill_name}")
                    else:
                        result = deferred_action_result(tool_name or "unknown")
                    return result

                if tool_name == "load-skill":
                    if call_id in load_errors:
                        result = {"error": load_errors[call_id], "executed": False}
                    else:
                        raw_args = call.get("function", {}).get("arguments", "{}")
                        skill_name = json.loads(raw_args).get("skillName")
                        result = skill_loaded_result(
                            skills_by_name[skill_name],
                            already_loaded=True,
                        )
                    return result

                if tool_name in skills_by_name and tool_name not in loaded_skills:
                    result = {
                        "error": (
                            f"Skill `{tool_name}` is not loaded. Call `load-skill` "
                            "with this Skill name before using its action tool."
                        ),
                        "executed": False,
                    }
                    return result

                raw_args = call.get("function", {}).get("arguments", "{}")
                try:
                    arguments = json.loads(raw_args)
                except json.JSONDecodeError as exc:
                    print(f"[agent][tool-error] {tool_name}: invalid arguments: {exc}")
                    result: Dict[str, Any] = {"error": f"Invalid tool arguments: {exc}"}
                    all_tool_results.append(result)
                    return result

                try:
                    if tool_name in DATA_TOOL_NAMES:
                        if data_tools is None or pipeline_bridge is None:
                            raise ValueError("Verify your user session and output workspace first")
                        result = invoke_tool(data_tools, pipeline_bridge, tool_name, arguments)
                    else:
                        result = execute_tool(
                            tool_name,
                            arguments,
                            enforced_workspace=enforced_workspace,
                            enforced_threads=enforced_threads,
                        )
                except (ValidationError, HTTPException, RuntimeError, ValueError, TypeError, OSError) as exc:
                    if isinstance(exc, HTTPException):
                        error_message = str(exc.detail)
                    else:
                        error_message = str(exc)
                    print(f"[agent][tool-error] {tool_name}: {error_message}")
                    result = {"error": error_message}
                all_tool_results.append(result)
                return result


            for call in tool_calls:
                name = call.get("function", {}).get("name") or "unknown"
                try:
                    observed_args = json.loads(call.get("function", {}).get("arguments", "{}"))
                    if not isinstance(observed_args, dict):
                        observed_args = {}
                except (ValueError, TypeError):
                    observed_args = {}
                result = (session.events.call_tool(name, observed_args, lambda: process_tool_call(call), tool_call_id=call.get("id"))
                          if session else process_tool_call(call))
                messages.append(_tool_result(call.get("id", ""), result))
            if not newly_loaded:
                budgeted_iterations += 1

            # Pure Skill-disclosure rounds do not consume the original Agent
            # iteration budget. Once normal work approaches that budget, ask the
            # model to reserve the final counted round for a text response.
            if (
                not wrap_requested
                and budgeted_iterations == MAX_AGENT_ITERS - 1
            ):
                wrap_requested = True
                messages.append({
                    "role": "user",
                    "content": (
                        "You are approaching the maximum number of iterations. "
                        "Please wrap up now: summarize what has been accomplished "
                        "and provide your final response without calling any more tools."
                    ),
                })
        if not completed:
            hit_limit = True
            print(
                "[agent] reached iteration limit "
                f"(budgeted={budgeted_iterations}/{MAX_AGENT_ITERS}, "
                f"total={total_iterations}/{max_total_iterations}), stopping"
            )

        if final_text:
            message = final_text
        elif hit_limit:
            n_ok = sum(1 for r in all_tool_results if not r.get("error"))
            n_err = sum(1 for r in all_tool_results if r.get("error"))
            parts = []
            if n_ok:
                parts.append(f"{n_ok} tool call(s) succeeded")
            if n_err:
                parts.append(f"{n_err} failed")
            summary = ("; ".join(parts) + ".") if parts else "No tools were executed."
            message = (
                f"The agent reached the iteration limit ({MAX_AGENT_ITERS}) "
                f"without producing a final response. {summary}"
            )
        elif all_tool_results:
            message = "Tool executed."
        else:
            message = "No response from model."

        budget = None
        if owns_session:
            session.events.node("report", lambda state: {"status": "failed" if hit_limit else "completed"}, "Preparing preprocessing response")({})
            budget = session.complete(payload.message, message, "failed" if hit_limit else "completed")
        return AgentChatResponse(
            message=message,
            conversationId=conv_id,
            metadata={
                "route": "pipeline", "routeReason": "Explicit preprocessing mode",
                **({"requestBudget": budget} if budget else {}),
                "tools": all_tool_results,
                "disclosedSkills": sorted(loaded_skills),
                "loadedSkills": sorted(loaded_skills),
                "llmIterations": total_iterations,
                "budgetedIterations": budgeted_iterations,
                "hitIterationLimit": hit_limit,
            },
        )

    @app.post(
        "/api/agent/chat", response_model=AgentChatResponse, response_model_by_alias=True
    )
    async def agent_chat(payload: AgentChatRequest, request: Request) -> AgentChatResponse:
        require_token(request)
        if payload.mode == "analysis":
            return await analysis_chat(payload, request)
        if payload.mode == "pipeline":
            return await pipeline_chat(payload, request)

        # Authenticate ownership and provider settings before any paid routing call.
        context = payload.context or {}
        user_id = require_safe_user_id(context.get("userId"))
        try:
            workspace = analysis_workspace(context.get("workspaceDirectory") or "", user_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        auth = _read_auth_record(str(workspace.parent))
        if not auth or not verify_user_token(
            context.get("userToken"), user_id, auth.get("salt")
        ):
            raise HTTPException(
                status_code=401,
                detail="Please verify your User ID first on the Configuration page",
            )
        request.state.refreshed_user_token = sign_user_token(user_id, auth["salt"])
        if payload.provider == "platform":
            if not PLATFORM_API_KEY or payload.model not in {
                row.get("id") for row in load_platform_models()
            }:
                raise HTTPException(
                    status_code=400, detail="Configure a valid platform model"
                )
            base_url, api_key, model = (
                PLATFORM_API_BASE_URL,
                PLATFORM_API_KEY,
                payload.model,
            )
        elif payload.provider == "custom" and payload.api_key and payload.model:
            base_url, api_key, model = (
                payload.base_url or DEFAULT_CUSTOM_BASE_URL,
                payload.api_key,
                payload.model,
            )
        else:
            raise HTTPException(
                status_code=400,
                detail="Configure a platform model or custom provider credentials",
            )
        conv_id = payload.conversation_id or f"conv_{uuid.uuid4().hex}"
        async with conversation_turn(workspace, user_id, conv_id):
            try:
                session = ChatSession(workspace, user_id, conv_id, api_key, 64)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc))
            history = session.load_history(payload.history)
            decision = await route_message(
                message=payload.message,
                history=history,
                recent_upload=public_context(context).get("recentUpload"),
                previous_route=session.prior_route(),
                base_url=base_url,
                api_key=api_key,
                model=model,
                caller=call_chat_completions,
                budget=session.budget,
            )
            session.start(decision["route"], decision["reason"], automatic=True)
            if decision.get("reason_truncated"):
                session.events.append("route", "warn", "Router reason truncated",
                                      {"reason": "reason truncated", "route": decision["route"]})
            routed = payload.model_copy(
                update={"conversation_id": conv_id, "history": history}
            )
            try:
                with session.activate():
                    if decision["route"] == "analysis":
                        request.state.auto_analysis_arguments = {
                            "conversation_history": history,
                            "router_model_calls": 1,
                        }
                        response = await analysis_chat(routed, request)
                    else:
                        response = await pipeline_chat(routed, request, session)
            except Exception:
                session.store.save(
                    "request",
                    {
                        "request_id": session.request_id,
                        "route": decision["route"],
                        "status": "failed",
                        "budget": session.budget.view(),
                    },
                )
                raise
            status = response.metadata.get("status", "completed")
            if response.metadata.get("hitIterationLimit"):
                status = "failed"
            # The analysis ledger includes the precharged route call. Its other model
            # usages are not exposed by the legacy SDK path, and remain unknown here.
            analysis_calls = (
                max(
                    0,
                    (
                        response.metadata.get(
                            "request_model_calls", response.metadata.get("model_calls")
                        )
                        or 1
                    )
                    - 1,
                )
                if decision["route"] == "analysis"
                else 0
            )
            if decision["route"] == "pipeline":
                session.events.node(
                    "report",
                    lambda state: {"status": status},
                    "Preparing preprocessing response",
                )({})
            budget = session.complete(
                payload.message, response.message, status, analysis_calls
            )
            response.metadata.update(
                {
                    "route": decision["route"],
                    "routeReason": decision["reason"],
                    "routing": {"fallback": decision["fallback"], "modelCalls": 1},
                    "requestBudget": budget,
                }
            )
            return response

    return app


def _tool_result(tool_call_id: str, content: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "content": json.dumps(content, ensure_ascii=False),
    }


app = build_app()
