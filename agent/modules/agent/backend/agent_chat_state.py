"""Protected conversation history, request accounting and a shared event timeline."""

from __future__ import annotations

from contextlib import contextmanager, asynccontextmanager
import asyncio
import threading
import weakref
from contextvars import ContextVar
import hashlib
import json
import os
from pathlib import Path
import time
import uuid

from .analysis_control_store import ControlStore, checked
from .analysis_events import AnalysisEvents, redact

ACTIVE_CHAT = ContextVar("primatex_active_chat", default=None)
_TURN_LOCKS = weakref.WeakValueDictionary()
_TURN_GUARD = threading.Lock()


@asynccontextmanager
async def conversation_turn(workspace, user_id, conversation_id):
    """Serialize turns in the configured single-worker backend without blocking its loop."""
    key = str(chat_store_path(workspace, user_id, conversation_id))
    with _TURN_GUARD:
        lock = _TURN_LOCKS.get(key)
        if lock is None:
            lock = asyncio.Lock()
            _TURN_LOCKS[key] = lock
    async with lock:
        yield


def _digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]


def chat_store_path(workspace, user_id, conversation_id):
    if not isinstance(conversation_id, str) or not 1 <= len(conversation_id) <= 256:
        raise ValueError("Invalid conversation ID")
    if any(ord(char) < 32 for char in conversation_id):
        raise ValueError("Invalid conversation ID")
    state = checked(
        Path(
            os.environ.get(
                "AGENT_ANALYSIS_STATE_DIR",
                str(Path(__file__).resolve().parent.parent / ".analysis_state"),
            )
        ).absolute()
    )
    # Workspace is part of the key, so the same user cannot collide across projects.
    scope = _digest(
        user_id + "\x00" + str(Path(workspace).resolve()) + "\x00" + conversation_id
    )
    return checked(state / _digest(user_id) / (scope + ".chat_controls"))


def bounded_history(history, secret=""):
    result = []
    for row in (history or [])[-12:]:
        if not isinstance(row, dict) or row.get("role") not in {"user", "assistant"}:
            continue
        if isinstance(row.get("content"), str):
            content = redact(row["content"], secret)
            result.append({"role": row["role"], "content": content})
    return result


def usage_summary(records):
    totals = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    unknown = 0
    known = 0
    for row in records:
        usage = row.get("usage")
        if not isinstance(usage, dict) or not all(
            type(usage.get(key)) is int and usage[key] >= 0 for key in totals
        ):
            unknown += 1
            continue
        known += 1
        for key in totals:
            totals[key] += usage[key]
    return {
        "known_usage_calls": known,
        "unknown_usage_calls": unknown,
        "known_tokens": totals,
        "cost": None,
        "cost_status": "No verified monetary price; unknown usage is not zero",
    }


class RequestBudget:
    def __init__(self, session, limit):
        self.session = session
        self.limit = limit
        self.records = []

    def reserve(self, phase):
        if len(self.records) >= self.limit:
            raise RuntimeError("Chat request model-call budget exhausted")
        record = {
            "id": uuid.uuid4().hex,
            "phase": phase,
            "status": "started",
            "request_id": self.session.request_id,
            "time": time.time(),
            "usage": None,
        }
        self.records.append(record)
        self.session.store.save("model_charge", record)
        return record["id"]

    def finish(self, attempt_id, usage, status):
        row = next(item for item in self.records if item["id"] == attempt_id)
        row["status"] = status
        if isinstance(usage, dict):
            row["usage"] = {
                key: usage[key]
                for key in ("prompt_tokens", "completion_tokens", "total_tokens")
                if type(usage.get(key)) is int and usage[key] >= 0
            }
        self.session.store.save("model_charge", row)

    def view(self, unmetered_analysis_calls=0):
        summary = usage_summary(self.records)
        summary["unknown_usage_calls"] += unmetered_analysis_calls
        return {
            "model_calls": len(self.records) + unmetered_analysis_calls,
            "router_calls": sum(row["phase"] == "router" for row in self.records),
            "limit": self.limit,
            **summary,
        }


class ChatSession:
    def __init__(self, workspace, user_id, conversation_id, secret, limit):
        self.workspace = Path(workspace).resolve()
        self.user_id = user_id
        self.conversation_id = conversation_id
        self.request_id = uuid.uuid4().hex
        self.secret = secret
        self.store = ControlStore(
            chat_store_path(workspace, user_id, conversation_id), [self.workspace]
        )
        expected = {
            "workspace_sha256": _digest(str(self.workspace)),
            "owner_sha256": _digest(user_id),
        }
        with self.store.locked():
            context = self.store.read("context.json")
            if context is None:
                self.store.create("context.json", expected)
            elif context != expected:
                raise ValueError(
                    "Conversation state belongs to a different owner or workspace"
                )
        self.events = AnalysisEvents(self.store, secret)
        self.budget = RequestBudget(self, limit)
        self.analysis_root = None
        self.route = None
        self.history = []

    def prior_route(self):
        saved = self.store.latest("route")
        return saved["record"]["route"] if saved else None

    def load_history(self, client_history):
        saved = self.store.latest("history")
        history = saved["record"]["messages"] if saved else client_history
        self.history = bounded_history(history, self.secret)
        return self.history

    def start(self, route, reason, automatic):
        self.route = route
        self.store.save(
            "route", {"route": route, "reason": reason, "request_id": self.request_id}
        )
        self.store.save(
            "request",
            {
                "request_id": self.request_id,
                "status": "running",
                "route": route,
                "started_time": time.time(),
            },
        )
        if automatic:
            title = (
                "Routed to analysis"
                if route == "analysis"
                else "Routed to preprocessing"
            )
            self.events.append(
                "other",
                "done",
                title,
                {"reason": reason, "route": route, "request_id": self.request_id},
            )

    @contextmanager
    def activate(self):
        token = ACTIVE_CHAT.set(self)
        try:
            yield self
        finally:
            ACTIVE_CHAT.reset(token)

    def mirror(self, row, source):
        if self.store.root == source.store.root:
            return
        if self.analysis_root != source.store.root:
            self.analysis_root = source.store.root
            self.store.save(
                "analysis_link",
                {"request_id": self.request_id, "root": str(source.store.root)},
            )
        self.events.append(
            row["stage"], row["status"], row["title"], row["detail"], row["refs"]
        )

    def complete(self, message, response, status, analysis_calls=0):
        history = self.history + [
            {"role": "user", "content": message},
            {"role": "assistant", "content": response},
        ]
        self.store.save("history", {"messages": bounded_history(history, self.secret)})
        budget = self.budget.view(analysis_calls)
        self.store.save(
            "request",
            {
                "request_id": self.request_id,
                "status": status,
                "route": self.route,
                "finished_time": time.time(),
                "budget": budget,
            },
        )
        return budget


def conversation_events(workspace, user_id, conversation_id, after):
    root = chat_store_path(workspace, user_id, conversation_id)
    if not root.is_dir() or not (root / "events.jsonl").is_file():
        return None
    store = ControlStore(root, [Path(workspace)])
    context = store.read("context.json")
    expected = {
        "workspace_sha256": _digest(str(Path(workspace).resolve())),
        "owner_sha256": _digest(user_id),
    }
    if context != expected:
        raise ValueError("Conversation workspace or owner mismatch")
    log = AnalysisEvents(store)
    if not log.all():
        return None
    request = store.latest("request")
    record = request["record"] if request else {}
    # Explicit analysis keeps its original native event path. Do not mask a
    # newer explicit run with an older automatic/preprocessing conversation log.
    if record.get("status") != "running":
        native_folder = root.parent / (
            _digest(user_id + "\x00" + conversation_id) + ".budget.controls"
        )
        updated = record.get("finished_time", record.get("started_time", 0))
        if native_folder.is_dir():
            for candidate in native_folder.iterdir():
                if (
                    not candidate.is_dir()
                    or len(candidate.name) != 32
                    or any(char not in "0123456789abcdef" for char in candidate.name)
                ):
                    continue
                native = ControlStore(checked(candidate), [Path(workspace)])
                native_context = native.read("context.json") or {}
                if (
                    native_context.get("workspace_sha256")
                    == expected["workspace_sha256"]
                    and native_context.get("started_time", 0) > updated
                ):
                    return None
    view = log.view(after)
    view["status"] = record.get("status", "running")
    view["run_id"] = record.get("request_id")
    link = store.latest("analysis_link")
    if link and link["record"]["request_id"] == record.get("request_id"):
        source = checked(Path(link["record"]["root"]))
        # A source binding is written by the server's actual analysis event hook.
        # It must remain inside this user's protected analysis state.
        owner = root.parent
        if not source.is_relative_to(owner) or source == root:
            raise ValueError("Analysis event source escaped owner state")
        native = ControlStore(source, [Path(workspace)])
        native_context = native.read("context.json") or {}
        if native_context.get("workspace_sha256") != expected["workspace_sha256"]:
            raise ValueError("Analysis event source workspace mismatch")
        view["plan"] = AnalysisEvents(native).plan_summary()
        view["run_id"] = native_context.get("run_id", view["run_id"])
        view["knowledge_profile"] = native_context.get("knowledge_profile")
    view["enabled"] = True
    return view
