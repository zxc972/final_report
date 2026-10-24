"""Loopback-only Round22 runtime and independent HTTP meter; no analysis answers."""

from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import threading
import time
from urllib.parse import urlsplit

ROOT = Path("/data/xuancheng/agent_v1")
BATCH = ROOT / "retests/round22_20261024"
SOURCE = ROOT / "round22_source"
PORT = 8122
CASES = {f"R22_{question}_{index}" for question in ("G1", "G2") for index in range(1, 4)}

APPROVAL = json.loads((BATCH / "offline_release.json").read_text())
if APPROVAL.get("status") != "offline_passed_protected_reviewed":
    raise RuntimeError("Offline approval is required before enabling any real request")
if subprocess.check_output(["git", "-C", str(SOURCE), "rev-parse", "HEAD"], text=True).strip() != APPROVAL["source_commit"]:
    raise RuntimeError("Approved source commit changed")

prior = dict(
    part.decode().split("=", 1)
    for part in Path("/proc/4144167/environ").read_bytes().split(b"\0")
    if b"=" in part
)
for name, value in prior.items():
    if name.startswith(("ANALYSIS_", "PLATFORM_", "PRIMX_", "AGENT_")) or name in {
        "PATH",
        "TMPDIR",
    }:
        os.environ[name] = value
configuration = {}
for line in (ROOT / ".env").read_text().splitlines():
    line = line.strip().removeprefix("export ")
    if not line or line.startswith("#") or "=" not in line:
        continue
    name, value = line.split("=", 1)
    if re.fullmatch(r"[A-Z_][A-Z0-9_]*", name.strip()):
        configuration[name.strip()] = value.strip().strip("\"'")
secret = next(
    (
        configuration[k]
        for k in ["PLATFORM_API_KEY", "INFERAI_API_KEY", "OPENAI_API_KEY", "API_KEY"]
        if configuration.get(k)
    ),
    None,
)
base = next(
    (
        configuration[k]
        for k in [
            "PLATFORM_API_BASE_URL",
            "INFERAI_BASE_URL",
            "OPENAI_BASE_URL",
            "FT01_BASE_URL",
            "BASE_URL",
        ]
        if configuration.get(k)
    ),
    None,
)
if not secret:
    raise RuntimeError("Configured provider credential unavailable; no request sent")
base = (base or "https://inferaiapi.com/v1").rstrip("/")
if base == "https://inferaiapi.com":
    base += "/v1"
provider = urlsplit(base)
if (
    provider.scheme != "https"
    or not provider.hostname
    or not provider.path.endswith("/v1")
    or provider.username
    or provider.password
    or provider.query
):
    raise RuntimeError("Provider URL validation failed; no request sent")
for name in list(os.environ):
    if name.startswith(("LANGSMITH_", "LANGCHAIN_TRACING")):
        os.environ.pop(name, None)
os.environ.update(
    PLATFORM_API_KEY=secret,
    PLATFORM_API_BASE_URL=base,
    AGENT_DATA_CATALOG=str(BATCH / "catalog.ixi20.json"),
    AGENT_DATA_ROOTS=os.pathsep.join(
        row["path"]
        for row in json.loads((BATCH / "catalog.ixi20.json").read_text())["roots"]
    ),
    AGENT_DATA_DIRECTORY="",
    AGENT_KNOWLEDGE_PROFILE="product_graph_planner",
    AGENT_CROSSSPECIES_RULES="0",
    AGENT_ANALYSIS_STATE_DIR=str(BATCH / "state"),
    AGENT_RESEARCH_EVIDENCE_ROOT=str(SOURCE / "knowledge/research_v13"),
    ANALYSIS_REFERENCE_PYTHON=str(ROOT / ".venv-reference/bin/python"),
    ANALYSIS_MAX_MODEL_CALLS="30",
    ANALYSIS_MAX_TOOL_CALLS="60",
    ANALYSIS_MAX_EXECUTIONS="8",
    ANALYSIS_MAX_EXECUTION_SECONDS="1200",
    ANALYSIS_ENABLE_BACKGROUND_JOBS="0",
    ANALYSIS_ENABLE_INTERNAL_REVIEW="1",
    PRIMATEX_PIPELINE_IMAGE="",
    PYTHONDONTWRITEBYTECODE="1",
    LANGSMITH_TRACING="false",
    LANGCHAIN_TRACING_V2="false",
)
sys.path.insert(0, str(SOURCE / "agent/modules/agent"))
sys.path.insert(0, str(SOURCE / "agent"))
for host_port in [PORT]:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", host_port))

ACTIVE_CASE = None
LOCK = threading.RLock()
AUTH = BATCH / "authorization.json"
LEDGER = BATCH / "http_ledger.json"
if LEDGER.exists():
    raise RuntimeError("HTTP meter exists; inspect rather than reset")
SECRETS = [secret, os.environ.get("PRIMX_ACCESS_TOKEN", "")]


def scrub(value):
    if isinstance(value, dict):
        return {
            str(k): (
                "[REDACTED]"
                if str(k).lower()
                in {"api_key", "authorization", "usertoken", "user_token", "password"}
                else scrub(v)
            )
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [scrub(v) for v in value]
    if isinstance(value, str):
        for item in SECRETS:
            if item:
                value = value.replace(item, "[REDACTED]")
        return re.sub(
            r"[A-Za-z0-9_-]{16,}\.[0-9a-f]{64}", "[REDACTED_USER_TOKEN]", value
        )
    return value


def save(path, value):
    text = json.dumps(scrub(value), ensure_ascii=False, indent=2)
    for item in SECRETS:
        if item and item in text:
            raise RuntimeError("Secret redaction failed")
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text + "\n")
    temporary.replace(path)


protected = {
    str(path): hashlib.sha256(path.read_bytes()).hexdigest()
    for directory in [
        SOURCE / "agent/modules/agent/backend",
        SOURCE / "knowledge/research_v13",
        SOURCE / "agent/modules/agent/knowledge_analysis",
        SOURCE / "agent/experiments/round22",
    ]
    for path in directory.rglob("*")
    if path.is_file()
    and path.suffix not in {".pyc"}
    and "__pycache__" not in path.parts
}
if protected != APPROVAL["runtime_source_sha256"]:
    raise RuntimeError("Approved runtime source fingerprints changed")
save(BATCH / "protected_source_before.json", protected)
save(
    LEDGER,
    {
        "http_attempts": 0,
        "attempts": [],
        "known_prompt_tokens": 0,
        "known_completion_tokens": 0,
        "unknown_usage_attempts": 0,
    },
)


def begin(request):
    if request.url.host != provider.hostname:
        return None
    with LOCK:
        if ACTIVE_CASE not in CASES:
            raise RuntimeError("Provider call outside an authorized analysis request")
        if (
            request.url.path.rstrip("/")
            != provider.path.rstrip("/") + "/chat/completions"
        ):
            raise RuntimeError("Unexpected provider endpoint")
        changed = [
            path
            for path, sha in protected.items()
            if hashlib.sha256(Path(path).read_bytes()).hexdigest() != sha
        ]
        if changed:
            save(
                BATCH / "safety_stop.json",
                {"reason": "Protected code/release changed", "paths": changed},
            )
            raise RuntimeError("Source protection changed; paid requests stopped")
        payload = json.loads(request.content)
        from backend.analysis_http_observer import current_native_charge
        charge = current_native_charge()
        ledger = json.loads(LEDGER.read_text())
        number = ledger["http_attempts"] + 1
        row = {
            "seq": number,
            "case": ACTIVE_CASE,
            "started_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "started_epoch": time.time(),
            "model_requested": payload.get("model"),
            "native_attempt_id": charge.get("id"),
            "native_logical_id": charge.get("logical_id"),
            "source_node": charge.get("source_node"),
            "analysis_phase": charge.get("analysis_phase"),
            "status": "started",
            "usage": None,
        }
        ledger["http_attempts"] = number
        ledger["attempts"].append(row)
        save(LEDGER, ledger)
        folder = BATCH / ("case_" + ACTIVE_CASE)
        folder.mkdir(exist_ok=True)
        save(
            folder / f"http_{number:03d}_request.json",
            {
                key: payload[key]
                for key in [
                    "model",
                    "messages",
                    "tools",
                    "tool_choice",
                    "response_format",
                    "max_tokens",
                    "temperature",
                    "stream",
                ]
                if key in payload
            },
        )
        return number, folder, row["started_epoch"]


def finish(ticket, response=None, error=None):
    if ticket is None:
        return
    number, folder, started = ticket
    parsed = {}
    if response is not None:
        try:
            parsed = response.json()
        except Exception:
            parsed = {}
    with LOCK:
        ledger = json.loads(LEDGER.read_text())
        row = next(x for x in ledger["attempts"] if x["seq"] == number)
        usage = parsed.get("usage") if isinstance(parsed, dict) else None
        row.update(
            status_code=response.status_code if response is not None else None,
            status="response_received" if response is not None else "transport_failed",
            elapsed_seconds=time.time() - started,
            usage=usage,
            model_returned=parsed.get("model") if isinstance(parsed, dict) else None,
            error_type=type(error).__name__ if error else None,
        )
        if isinstance(usage, dict) and all(type(usage.get(key)) is int and usage[key] >= 0 for key in ('prompt_tokens', 'completion_tokens')):
            ledger["known_prompt_tokens"] += usage["prompt_tokens"]
            ledger["known_completion_tokens"] += usage["completion_tokens"]
        else:
            ledger["unknown_usage_attempts"] += 1
        save(LEDGER, ledger)
        save(
            folder / f"http_{number:03d}_response.json",
            {"record": row, "response": parsed},
        )


from backend.analysis_http_observer import HTTPObserver
observer = HTTPObserver(begin, finish).install()
save(BATCH / "http_transport_coverage.json", observer.coverage)
from backend import api
from backend import analysis_agent
from backend.pipeline_bridge import PipelineBridge
from starlette.responses import JSONResponse

analysis_agent.MAX_RUN_SECONDS = 1200


def forbidden_preprocessing(*args, **kwargs):
    save(
        BATCH / "preprocessing_submission_blocked.json",
        {"case": ACTIVE_CASE, "time": time.time(), "submitted": False},
    )
    raise PermissionError("Preprocessing submissions are forbidden in Round22")


PipelineBridge.submit_pipeline = forbidden_preprocessing


@api.app.middleware("http")
async def guard_analysis(request, call_next):
    global ACTIVE_CASE
    if request.url.path != "/api/agent/chat":
        return await call_next(request)
    case = request.headers.get("X-Round22-Case")
    with LOCK:
        authorization = json.loads(AUTH.read_text())
        if (
            APPROVAL.get("source_commit") != json.loads((BATCH / "development_launch.json").read_text())["source_head"]
            or case not in CASES
            or ACTIVE_CASE is not None
            or authorization["real_analysis_runs"]
            >= authorization["rules"]["model_requests_max_analysis_runs"]
            or (BATCH / "safety_stop.json").exists()
        ):
            return JSONResponse(
                {"error": "Round22 authorization guard"}, status_code=409
            )
        previous = authorization.setdefault("launched_cases", [])
        if case in previous:
            return JSONResponse({"error": "Duplicate case forbidden"}, status_code=409)
        previous.append(case)
        authorization["real_analysis_runs"] += 1
        authorization["status"] = "running_" + case
        save(AUTH, authorization)
        ACTIVE_CASE = case
    try:
        return await call_next(request)
    finally:
        with LOCK:
            ACTIVE_CASE = None


logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("httpx2").setLevel(logging.WARNING)
logging.getLogger("httpcore2").setLevel(logging.WARNING)
save(
    BATCH / "development_ready.json",
    {
        "pid": os.getpid(),
        "port": PORT,
        "host": "127.0.0.1",
        "started_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "provider_hostname": provider.hostname,
        "model": "deepseek-v4-pro",
        "profile": "product_graph_planner",
        "C": False,
        "budget": [30, 60, 8, 1200],
        "outer_iterations": 3,
        "no_existing_service_restarted": True,
        "credentials_printed_or_written": False,
    },
)
import uvicorn

uvicorn.run(api.app, host="127.0.0.1", port=PORT, reload=False, log_level="warning")
