"""Isolated Round 11 development server: instrumentation, no fixed analysis code."""

from __future__ import annotations

import ast
import contextvars
import functools
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import sys
import threading
import time
from urllib.parse import parse_qsl, urlencode, urlparse
import uuid

ROOT = Path("/data/xuancheng/agent_round11_trial_20261022")
REVIEW = ROOT / "backend_review"
ORIGINAL = Path("/data/xuancheng/agent/modules/agent")
USER = "round11b-trial"
WORKSPACE = ROOT / "workspace" / USER / "output"
DATA = [
    "/data/xuancheng/featurize_20261011/data/KM002/KM002",
    "/data/xuancheng/human_fastsurfer/subjects/100610",
    "/data/xuancheng/human_fastsurfer/subjects/101309",
    "/data/xuancheng/human_fastsurfer/subjects/101410",
]
QUESTIONS = {
    "R11B_P1_1": "Summarise cortical thickness for each region of the aparc parcellation in both hemispheres of the macaque reconstruction in the registered data. Keep the native stored scale, restrict to cortex, and report units and limitations.",
    "R11B_P1_2": "Summarise cortical thickness for each region of the aparc parcellation in both hemispheres of the macaque reconstruction in the registered data. Keep the native stored scale, restrict to cortex, and report units and limitations.",
    "R11B_P2_1": "For the macaque reconstruction in the registered data, compute a true local gyrification index if its prerequisites are met. If they are not met, explain what is missing and complete any feasible related descriptive analysis instead.",
    "R11B_P2_2": "For the macaque reconstruction in the registered data, compute a true local gyrification index if its prerequisites are met. If they are not met, explain what is missing and complete any feasible related descriptive analysis instead.",
    "R11B_P3_1": "Which subjects and reconstruction outputs are available in my registered data? Do not start any processing.",
}
CONFIG_SOURCE = Path("/data/xuancheng/eval/ft01_20261018/config/.env")
configuration = {}
for line in CONFIG_SOURCE.read_text().splitlines():
    if "=" in line and not line.lstrip().startswith("#"):
        key, value = line.split("=", 1)
        configuration[key.strip()] = value.strip().strip("\"'")
SECRET = configuration["PLATFORM_API_KEY"]
BASE = configuration.get("FT01_BASE_URL", "https://inferaiapi.com/v1").rstrip("/")
if BASE == "https://inferaiapi.com":
    BASE += "/v1"
MODEL = "deepseek-v4-pro"
MODELS = [MODEL, "deepseek-v4.1-flash"]
QUESTIONS.update({"R11B_FLASH_P1_1": QUESTIONS["R11B_P1_1"]})
BATCH_PLANNED_RUNS = 6
BATCH_LOGICAL_LIMIT = BATCH_PLANNED_RUNS * 30
BATCH_HTTP_LIMIT = BATCH_LOGICAL_LIMIT * 3
assert BASE.startswith("https://") and BASE.endswith("/v1") and SECRET
HOST = urlparse(BASE).netloc
assert all(
    value == 0
    for value in json.loads((ROOT / "audit/preflight_tests.json").read_text()).values()
)
assert json.loads((ROOT / "stage0/offline_ready.json").read_text())["passed"]

for key in list(os.environ):
    if key.startswith(("LANGSMITH_", "LANGCHAIN_TRACING", "OPENAI_", "ANTHROPIC_")):
        os.environ.pop(key, None)
os.environ.update(
    {
        "AGENT_ANALYSIS_STATE_DIR": str(ROOT / "state"),
        "AGENT_KNOWLEDGE_PROFILE": "product_graph_planner",
        "AGENT_DATA_CATALOG": str(ROOT / "data_catalog.json"),
        "AGENT_DATA_ROOTS": os.pathsep.join(DATA),
        "AGENT_DATA_DIRECTORY": "",
        "AGENT_DEFAULT_WORKSPACE": str(ROOT / "workspace"),
        "AGENT_RESEARCH_EVIDENCE_ROOT": "/data/xuancheng/agent_overnight_20261020/research_evidence_v13",
        "AGENT_SOURCE_GRAPH_ROOT": "/data/xuancheng/agent_overnight_20261020/software_graph",
        "ANALYSIS_MAX_MODEL_CALLS": "30",
        "ANALYSIS_MAX_TOOL_CALLS": "60",
        "ANALYSIS_MAX_EXECUTIONS": "8",
        "ANALYSIS_MAX_EXECUTION_SECONDS": "1200",
        "ANALYSIS_ENABLE_BACKGROUND_JOBS": "0",
        "AGENT_CROSSSPECIES_RULES": "0",
        "ANALYSIS_REFERENCE_PYTHON": "/data/software/anaconda3/bin/python",
        "ANALYSIS_ENABLE_INTERNAL_REVIEW": "1",
        "PRIMATEX_PIPELINE_IMAGE": "",
        "PRIMX_ACCESS_TOKEN": "",
        "PLATFORM_API_KEY": SECRET,
        "PLATFORM_API_BASE_URL": BASE,
        "PYTHONDONTWRITEBYTECODE": "1",
        "LANGSMITH_TRACING": "false",
        "LANGCHAIN_TRACING_V2": "false",
    }
)
budget_path = ROOT / "experiment_budget.json"
budget_config = json.loads(budget_path.read_text())
assert budget_config["model_calls"] == 30 and budget_config["tool_calls"] == 60
assert budget_config["executions"] == 8 and budget_config["wall_seconds"] == 1200
assert budget_config["repair_rounds"] == 3
for name, key in [
    ("ANALYSIS_MAX_MODEL_CALLS", "model_calls"),
    ("ANALYSIS_MAX_TOOL_CALLS", "tool_calls"),
    ("ANALYSIS_MAX_EXECUTIONS", "executions"),
    ("ANALYSIS_MAX_EXECUTION_SECONDS", "wall_seconds"),
]:
    os.environ[name] = str(budget_config[key])
WORKSPACE.mkdir(parents=True, exist_ok=True)
auth_path = WORKSPACE.parent / ".auth.json"
if not auth_path.exists():
    auth_path.write_text(json.dumps({"salt": uuid.uuid4().hex}))
SALT = json.loads(auth_path.read_text())["salt"]
sys.path.insert(0, str(REVIEW))
from backend import api
from backend import analysis_agent as analysis
from backend.analysis_events import AnalysisEvents
from backend.pipeline_bridge import PipelineBridge
from langchain_core.callbacks import BaseCallbackHandler
import httpx
from starlette.responses import JSONResponse

TOKEN = api.sign_user_token(USER, SALT)
api.ACCESS_TOKEN = ""
api.PLATFORM_MODELS_PATH = ROOT / "platform_models.json"
api.PLATFORM_MODELS_PATH.write_text(json.dumps([{"id": name, "name": name} for name in MODELS]))
analysis.MAX_RUN_SECONDS = 1200
ACTIVE = contextvars.ContextVar("round11_request", default=None)
ACTIVE_GLOBAL = None
LOCK = threading.RLock()
BASELINE = json.loads((ROOT / "audit/protection_baseline.json").read_text())[
    "protected_hashes"
]
STOP = ROOT / "audit/safety_stop.json"
HTTP_LEDGER = ROOT / "provider_budget.json"
if not HTTP_LEDGER.exists():
    HTTP_LEDGER.write_text(
        json.dumps(
            {
                "http_started": 0,
                "logical_started": 0,
                "known_input_tokens": 0,
                "known_output_tokens": 0,
                "unknown_usage_requests": 0,
            }
        )
    )


def current():
    return ACTIVE.get() or ACTIVE_GLOBAL


def clean(value):
    if isinstance(value, dict):
        return {
            str(key): (
                "[REDACTED]"
                if str(key).lower()
                in {
                    "api_key",
                    "apikey",
                    "authorization",
                    "password",
                    "access_token",
                    "usertoken",
                    "user_token",
                }
                else clean(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, (tuple, list)):
        return [clean(item) for item in value]
    if hasattr(value, "model_dump"):
        return clean(value.model_dump())
    if isinstance(value, str):
        return value.replace(SECRET, "[REDACTED]").replace(TOKEN, "[REDACTED]")
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return clean(str(value))


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(clean(value), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


def trace(event, **values):
    context = current()
    if context:
        with LOCK:
            with (context["folder"] / "trace.jsonl").open("a") as stream:
                stream.write(
                    json.dumps(
                        clean({"event": event, "time": time.time(), **values}),
                        ensure_ascii=False,
                    )
                    + "\n"
                )


def stop(reason, **details):
    if not STOP.exists():
        save(
            STOP,
            {
                "reason": reason,
                "case": (current() or {}).get("case"),
                "time": time.time(),
                **details,
            },
        )
    raise RuntimeError("Round 11 safety stop: " + reason)


def check_protection():
    changed = [
        name
        for name, expected in BASELINE.items()
        if hashlib.sha256(Path(name).read_bytes()).hexdigest() != expected
    ]
    if changed:
        stop("Protected file changed", count=len(changed))
    frozen_path = ROOT / "audit/trial_source_freeze.json"
    if frozen_path.exists():
        frozen = json.loads(frozen_path.read_text())
        if any(hashlib.sha256((REVIEW / path).read_bytes()).hexdigest() != expected
               for path, expected in frozen["source_hashes"].items()):
            stop("Frozen source changed during the cohort")


def before_http(request):
    context = current()
    if not context:
        stop("Unscoped provider request")
    if STOP.exists():
        raise RuntimeError("Trial stopped; no further provider requests permitted")
    if request.url.host != HOST or request.url.path != "/v1/chat/completions":
        stop("Unexpected outbound network destination")
    if time.monotonic() - context["started"] >= 1200:
        stop("Request wall-clock budget exhausted")
    body = json.loads(request.content)
    if "thinking" in body:
        stop("Unexpected thinking field in provider request")
    if body.get("model") != context["model"]:
        stop("Provider model escaped case binding")
    raw = json.dumps(body)
    if re.search(r"(?<![0-9])(?:102311|105216)(?![0-9])", raw):
        stop("Excluded participant identifier in outbound payload")
    with LOCK:
        from backend.agent_chat_state import ACTIVE_CHAT
        from budget_policy import reserve_counts, RunLimitReached, BatchLimitReached
        from budget_policy import active_budget
        budget = active_budget(context, ACTIVE_CHAT.get())
        if budget is None or not budget.records:
            stop("Provider request has no native accounting reservation")
        native = budget.records[-1]
        logical_id = native["logical_id"]
        attempts = context["logical_ids"].get(logical_id, 0)
        if attempts and not native.get("retry_of"):
            stop("Duplicate HTTP attempt without a retry reservation")
        ledger = json.loads(HTTP_LEDGER.read_text())
        try:
            counts = reserve_counts(
                context["logical_started"], ledger["logical_started"],
                context["http_started"], ledger["http_started"],
                BATCH_PLANNED_RUNS, attempts,
            )
        except RunLimitReached:
            save(context["folder"] / "case_limit.json", {"reason": "Per-run logical/HTTP cap reached"})
            raise
        except BatchLimitReached:
            stop("Batch logical/HTTP budget exhausted", logical_limit=BATCH_LOGICAL_LIMIT)
        context["logical_started"], ledger["logical_started"], context["http_started"], ledger["http_started"] = counts
        context["logical_ids"][logical_id] = attempts + 1
        ordinal = context["http_started"]
        save(HTTP_LEDGER, ledger)
    remaining = max(0.1, 1200 - (time.monotonic() - context["started"]))
    timeouts = request.extensions.get("timeout", {})
    request.extensions["timeout"] = {
        name: min(value, remaining) if isinstance(value, (float, int)) else remaining
        for name, value in (
            timeouts or {"connect": None, "read": None, "write": None, "pool": None}
        ).items()
    }
    record = {
        "ordinal": ordinal,
        "logical_id": logical_id,
        "retry_of": native.get("retry_of"),
        "native_phase": native["phase"],
        "started": time.time(),
        "url": str(request.url),
        "request": body,
        "usage_status": "pending",
    }
    path = context["folder"] / f"http_{ordinal:03d}.json"
    save(path, record)
    trace("http_start", ordinal=ordinal)
    return path, record


def after_http(path, record, response=None, error=None):
    context = current()
    record["ended"] = time.time()
    if response is not None:
        record["status_code"] = response.status_code
        try:
            record["response"] = response.json()
        except Exception:
            record["response_text"] = response.text[:4000]
    if error is not None:
        record["error"] = type(error).__name__
    usage = record.get("response", {}).get("usage")
    record["usage_status"] = "reported" if isinstance(usage, dict) else "unknown"
    with LOCK:
        ledger = json.loads(HTTP_LEDGER.read_text())
        if isinstance(usage, dict):
            ledger["known_input_tokens"] += usage.get("prompt_tokens", 0)
            ledger["known_output_tokens"] += usage.get("completion_tokens", 0)
        else:
            ledger["unknown_usage_requests"] += 1
        save(HTTP_LEDGER, ledger)
        save(path, record)
    trace(
        "http_end",
        ordinal=record["ordinal"],
        status_code=record.get("status_code"),
        usage=usage,
    )
    if context and record["ordinal"] == 1:
        analysis.MAX_RUN_SECONDS = max(
            1, int(1200 - (time.monotonic() - context["started"]))
        )
    if context and time.monotonic() - context["started"] >= 1200:
        stop("Request wall-clock budget exceeded")


OriginalClient = httpx.Client
OriginalAsyncClient = httpx.AsyncClient


class AuditedClient(OriginalClient):
    def send(self, request, *args, **kwargs):
        path, record = before_http(request)
        try:
            response = super().send(request, *args, **kwargs)
            response.read()
        except Exception as error:
            after_http(path, record, error=error)
            raise
        after_http(path, record, response=response)
        return response


class AuditedAsyncClient(OriginalAsyncClient):
    async def send(self, request, *args, **kwargs):
        path, record = before_http(request)
        try:
            response = await super().send(request, *args, **kwargs)
            await response.aread()
        except Exception as error:
            after_http(path, record, error=error)
            raise
        after_http(path, record, response=response)
        return response


httpx.Client = AuditedClient
httpx.AsyncClient = AuditedAsyncClient


class TraceCallback(BaseCallbackHandler):
    def on_chat_model_start(self, serialized, messages, *, run_id, **kwargs):
        trace("model_start", run_id=str(run_id), messages=messages)

    def on_llm_end(self, response, *, run_id, **kwargs):
        trace("model_end", run_id=str(run_id), response=response)

    def on_llm_error(self, error, *, run_id, **kwargs):
        trace("model_error", run_id=str(run_id), error=str(error))


# Explicit injection bypasses LangChain's cached default SDK clients.
SHARED_HTTP = AuditedClient(timeout=120)
SHARED_ASYNC_HTTP = AuditedAsyncClient(timeout=120)
original_factory = analysis._model_factory


def audited_factory(**kwargs):
    kwargs["callbacks"] = [TraceCallback()]
    kwargs["http_client"] = SHARED_HTTP
    kwargs["http_async_client"] = SHARED_ASYNC_HTTP
    return original_factory(**kwargs)


analysis._model_factory = audited_factory
original_event_call = AnalysisEvents.call_tool


@functools.wraps(original_event_call)
def observed_tool(self, name, arguments, handler, tool_call_id=None):
    trace_id = uuid.uuid4().hex
    trace(
        "tool_start",
        trace_id=trace_id,
        tool_call_id=tool_call_id,
        name=name,
        arguments=arguments,
    )
    if name in {"submit_pipeline", "run-pipeline", "cancel-task", "cancel_pipeline"}:
        stop("Preprocessing or original-task mutation attempted", tool=name)
    before = self.all()
    last_sequence = before[-1]["seq"] if before else 0
    try:
        result = original_event_call(
            self, name, arguments, handler, tool_call_id=tool_call_id
        )
    except Exception as error:
        trace("tool_error", trace_id=trace_id, name=name, error=str(error))
        raise
    events = [
        row
        for row in self.all()
        if row["seq"] > last_sequence
        and row.get("detail", {}).get("tool") == name
        and (
            not tool_call_id
            or row.get("detail", {}).get("tool_call_id") == tool_call_id
        )
    ]
    trace(
        "tool_end",
        trace_id=trace_id,
        tool_call_id=tool_call_id,
        name=name,
        output=result,
        native_event_sequences=[row["seq"] for row in events],
        operation_ids=sorted(
            {
                row["detail"]["operation_id"]
                for row in events
                if "operation_id" in row["detail"]
            }
        ),
    )
    return result


AnalysisEvents.call_tool = observed_tool
original_run = analysis.AnalysisTools.run_python


@functools.wraps(original_run)
def guarded_run(self, path=None, *args, **kwargs):
    try:
        source = self.resolve(self.session.execution_path(path) if self.session else path).read_text()
        tree = ast.parse(source)
    except (OSError, ValueError, SyntaxError):
        return original_run(self, path, *args, **kwargs)
    forbidden = {
        "requests",
        "httpx",
        "socket",
        "urllib.request",
        "urllib3",
        "ftplib",
        "paramiko",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(
            alias.name in forbidden for alias in node.names
        ):
            stop("Network code attempted before sandbox execution")
        if isinstance(node, ast.ImportFrom) and node.module in forbidden:
            stop("Network code attempted before sandbox execution")
    result = original_run(self, path, *args, **kwargs)
    check_protection()
    if isinstance(result, dict) and re.search(
        r"Read-only file system|PermissionError", str(result.get("stderr", ""))
    ):
        stop("Potential out-of-work write attempted; inspect the retained execution")
    return result


analysis.AnalysisTools.run_python = guarded_run
OriginalSession = api.ChatSession


class TrialSession(OriginalSession):
    def __init__(self, workspace, user_id, conversation_id, secret, limit):
        super().__init__(workspace, user_id, conversation_id, secret, min(limit, 30))
        context = current()
        if context is not None:
            context["chat_budget"] = self.budget


api.ChatSession = TrialSession
app = api.build_app()


def payload_model_stopped(request):
    case = request.headers.get("x-trial-case", "")
    name = MODELS[1] if case.startswith("R11B_FLASH") else MODEL
    return name in json.loads((ROOT / "audit/model_stops.json").read_text())


@app.middleware("http")
async def isolated_trial(request, call_next):
    global ACTIVE_GLOBAL
    if request.method == "GET" and re.fullmatch(
        r"/api/agent/analysis/[^/]+/events", request.url.path
    ):
        # Read-only local viewer binding. The real user token never leaves this server.
        query = dict(parse_qsl(request.scope.get("query_string", b"").decode()))
        if query.get("userId") == USER and query.get("workspaceDirectory") == str(
            WORKSPACE
        ):
            headers = [
                (key, value)
                for key, value in request.scope["headers"]
                if key != b"x-user-token"
            ]
            headers.append((b"x-user-token", TOKEN.encode()))
            request.scope["headers"] = headers
    if request.method != "POST" or request.url.path != "/api/agent/chat":
        response = await call_next(request)
        for header in list(response.headers):
            if "user-token" in header.lower():
                del response.headers[header]
        return response
    case = request.headers.get("x-trial-case")
    if (
        case not in QUESTIONS
        or STOP.exists()
        or (ROOT / "audit/model_stops.json").is_file() and payload_model_stopped(request)
    ):
        return JSONResponse(
            {"detail": "Only the six operator-controlled trial requests are enabled"},
            status_code=403,
        )
    if case in {"R11B_P2_1", "R11B_P2_2", "R11B_P3_1"}:
        gate = ROOT / "audit/p1_continuation_gate.json"
        if not gate.is_file() or not json.loads(gate.read_text()).get("allowed"):
            return JSONResponse(
                {"detail": "P1 independent acceptance gate has not passed"},
                status_code=403,
            )
    payload = await request.json()
    if payload.get("message") != QUESTIONS[case] or payload.get("mode") != "auto":
        return JSONResponse(
            {"detail": "The trial question and automatic mode must be unchanged"},
            status_code=400,
        )
    expected_model = MODELS[1] if case.startswith("R11B_FLASH") else MODEL
    if payload.get("model") != expected_model:
        return JSONResponse({"detail": "Case/model binding mismatch"}, status_code=400)
    folder = ROOT / "trials" / case
    if folder.exists():
        return JSONResponse(
            {"detail": "This trial has already been dispatched; no duplicate allowed"},
            status_code=409,
        )
    if ACTIVE_GLOBAL is not None:
        return JSONResponse(
            {"detail": "Only one paid trial may run at once"}, status_code=409
        )
    folder.mkdir(parents=True)
    context = {
        "case": case,
        "folder": folder,
        "started": time.monotonic(),
        "http_started": 0,
        "logical_started": 0,
        "logical_ids": {},
        "model": payload["model"],
    }
    token = ACTIVE.set(context)
    ACTIVE_GLOBAL = context
    save(
        folder / "dispatch.json",
        {
            "case": case,
            "conversation_id": payload.get("conversationId"),
            "question": payload["message"],
            "model": payload["model"],
            "base_url": BASE,
            "knowledge_profile": "product_graph_planner",
            "approved_input_roots": DATA,
            "reference_exposed": False,
            "prewritten_analysis_code_supplied": False,
            "started": time.time(),
            "budgets": {
                "rounds": 3,
                "model_calls": 30,
                "tool_calls": 60,
                "production_executions": 8,
                "wall_seconds": 1200,
            },
            "status": "running",
        },
    )
    analysis.MAX_RUN_SECONDS = 1200
    try:
        check_protection()
        response = await call_next(request)
        check_protection()
        elapsed = time.monotonic() - context["started"]
        if elapsed >= 1200:
            stop("Request wall-clock budget exceeded")
        save(
            folder / "request_end.json",
            {
                "http_status": response.status_code,
                "http_started": context["http_started"],
                "logical_started": context["logical_started"],
                "elapsed_seconds": elapsed,
                "finished": time.time(),
            },
        )
        return response
    finally:
        ACTIVE_GLOBAL = None
        ACTIVE.reset(token)


class RedactedStream:
    def __init__(self, wrapped):
        self.wrapped = wrapped

    def write(self, value):
        return self.wrapped.write(
            str(value).replace(SECRET, "[REDACTED]").replace(TOKEN, "[REDACTED]")
        )

    def flush(self):
        return self.wrapped.flush()

    def isatty(self):
        return False


sys.stdout = RedactedStream(sys.stdout)
sys.stderr = RedactedStream(sys.stderr)
save(
    ROOT / "operator_config.json",
    {
        "model": MODEL,
        "base_url": BASE,
        "configuration_source": str(CONFIG_SOURCE),
        "backend_source": str(REVIEW),
        "profile": "product_graph_planner",
        "port": 8127,
        "workspace": str(WORKSPACE),
        "user_id": USER,
        "input_roots": DATA,
        "pipeline_image_configured": False,
        "preprocessing_guard_enabled": True,
        "logical_call_cap_per_trial": 30,
        "outbound_http_cap_per_trial": 90,
        "batch_logical_cap": BATCH_LOGICAL_LIMIT,
        "planned_runs": BATCH_PLANNED_RUNS, "batch_http_cap": BATCH_HTTP_LIMIT, "models": MODELS,
        "sdk_http_clients": "explicit shared synchronous/asynchronous audited clients; no cached defaults",
        "readonly_viewer_auth_binding": "loopback events GET for fixed trial workspace only; no token sent to browser",
    },
)
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8127, access_log=False, log_level="warning")
