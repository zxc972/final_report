"""Observe actual httpx/httpx2 SDK sends without changing transport/retry policy."""
from contextvars import ContextVar
from functools import wraps
import importlib

_IN_SEND = ContextVar("primatex_http_observer_send", default=False)


def current_native_charge():
    """Resolve this send's exact reservation, including before chat activation.

    Automatic routing receives a budget before ACTIVE_CHAT is activated. Bind
    the reservation owner directly instead of inferring a current/latest row.
    """
    from .analysis_call_context import HTTP_ATTEMPT, HTTP_BUDGET

    attempt, budget = HTTP_ATTEMPT.get(), HTTP_BUDGET.get()
    charge = next((row for row in budget.records if row["id"] == attempt), None) if budget is not None else None
    if charge is None or charge.get("status") != "started":
        raise RuntimeError("Exact native HTTP charge binding unavailable; request not sent")
    return charge


class HTTPObserver:
    """Install only in an isolated process; callbacks own redaction and storage.

    begin(request) returns an observation ticket or None for out-of-scope traffic.
    finish(ticket, response=None, error=None) is called exactly once. No headers,
    credentials, prompts or response bodies are logged by this transport hook.
    """
    def __init__(self, begin, finish):
        self.begin, self.finish = begin, finish
        self.originals = []
        self.coverage = []

    def _sync(self, original):
        @wraps(original)
        def send(client, request, *args, **kwargs):
            if _IN_SEND.get():
                return original(client, request, *args, **kwargs)
            token = _IN_SEND.set(True)
            try:
                ticket = self.begin(request)
                try:
                    response = original(client, request, *args, **kwargs)
                    if ticket is not None:
                        response.read()
                except Exception as error:
                    self.finish(ticket, error=error)
                    raise
                self.finish(ticket, response=response)
                return response
            finally:
                _IN_SEND.reset(token)
        return send

    def _async(self, original):
        @wraps(original)
        async def send(client, request, *args, **kwargs):
            if _IN_SEND.get():
                return await original(client, request, *args, **kwargs)
            token = _IN_SEND.set(True)
            try:
                ticket = self.begin(request)
                try:
                    response = await original(client, request, *args, **kwargs)
                    if ticket is not None:
                        await response.aread()
                except Exception as error:
                    self.finish(ticket, error=error)
                    raise
                self.finish(ticket, response=response)
                return response
            finally:
                _IN_SEND.reset(token)
        return send

    def install(self):
        if self.originals:
            raise RuntimeError("Observer is already installed")
        seen = set()
        for name in ["httpx", "httpx2"]:
            try:
                module = importlib.import_module(name)
            except ImportError:
                continue
            for class_name, asynchronous in [("Client", False), ("AsyncClient", True)]:
                cls = getattr(module, class_name, None)
                if cls is None or id(cls) in seen:
                    continue
                seen.add(id(cls))
                original = cls.send
                self.originals.append((cls, original))
                cls.send = self._async(original) if asynchronous else self._sync(original)
                self.coverage.append({"module": name, "class": class_name,
                                      "original_send_module": original.__module__})
        if not self.originals:
            raise RuntimeError("No supported HTTP transport found")
        return self

    def close(self):
        for cls, original in reversed(self.originals):
            cls.send = original
        self.originals.clear()

    def __enter__(self):
        return self.install()

    def __exit__(self, *args):
        self.close()
