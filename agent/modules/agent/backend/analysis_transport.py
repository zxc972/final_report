"""Bounded model-transport retries. They never repair content or scientific code."""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from contextvars import ContextVar
import re
import time
from email.utils import parsedate_to_datetime
import math

import httpx

RETRY_DELAYS = (5, 15)
RATE_DELAYS = (10, 30, 60)
sleep_sync = time.sleep
sleep_async = asyncio.sleep
DEADLINE = ContextVar('primatex_model_deadline', default=None)
TRANSPORT_RETRY_LIMIT = ContextVar('primatex_transport_retry_limit', default=None)


class TransportExhausted(RuntimeError):
    def __init__(self, attempts, status_code=None, reason='upstream_transport_error'):
        self.attempts = attempts
        self.status_code = status_code
        self.reason = reason
        super().__init__(f'Model transport unavailable after {attempts} HTTP attempts ({status_code or reason})')


AUTH_FAILURE_MESSAGE = "分析服务暂时不可用（上游权限错误），请稍后重试"


class AuthenticationFailed(TransportExhausted):
    def __init__(self, attempts, status_code):
        super().__init__(attempts, status_code, "environment_auth_failed")


def authentication_status(error):
    """Recognize real upstream statuses, including compatibility wrappers."""
    seen = set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        detail = str(getattr(error, "detail", ""))
        match = re.search(r"LLM API error:\s*(\d{3})", detail)
        status = int(match.group(1)) if match else getattr(error, "status_code", None)
        if status in {401, 403}:
            return status
        error = getattr(error, "__cause__", None)
    return None


class RateLimited(TransportExhausted):
    def __init__(self, attempts, status_code=429, reason="environment_rate_limited"):
        super().__init__(attempts, status_code, reason)


def retry_after(error, fallback):
    response = getattr(error, "response", None)
    headers = getattr(response, "headers", None) or getattr(error, "headers", None) or {}
    raw = headers.get("Retry-After", headers.get("retry-after"))
    if raw is None:
        return fallback
    try:
        value = float(raw)
    except (ValueError, TypeError):
        try:
            value = parsedate_to_datetime(raw).timestamp() - time.time()
        except (ValueError, TypeError, OverflowError):
            return fallback
    return max(0.0, value) if math.isfinite(value) else fallback


def transient_status(error):
    # Some compatibility helpers wrap upstream statuses in an HTTPException(502).
    # Inspect the original "LLM API error: NNN" first; never retry 400/401.
    detail = getattr(error, 'detail', '')
    if 'response_format' in str(detail).lower() and any(word in str(detail).lower() for word in ['unsupported', 'not support', 'unknown field']):
        return None
    match = re.search(r'LLM API error:\s*(\d{3})', str(detail))
    status = int(match.group(1)) if match else getattr(error, 'status_code', None)
    if status in {429, 502, 503, 504}:
        return status
    seen = set()
    current = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, httpx.ReadTimeout):
            return 'read_timeout'
        current = getattr(current, '__cause__', None)
    return None


@contextmanager
def model_deadline(deadline):
    token = DEADLINE.set(deadline)
    try:
        yield
    finally:
        DEADLINE.reset(token)


def retry_sync(operation, on_retry=None):
    for attempt in range(4):
        try:
            return operation(attempt)
        except Exception as error:
            auth_status = authentication_status(error)
            if auth_status is not None:
                raise AuthenticationFailed(attempt + 1, auth_status) from error
            status = transient_status(error)
            if status is None:
                raise
            limited = status == 429
            maximum = 3 if limited else 2
            override = TRANSPORT_RETRY_LIMIT.get()
            if override is not None:
                maximum = min(maximum, override)
            exhausted = RateLimited if limited else TransportExhausted
            if attempt >= maximum:
                raise exhausted(attempt+1, status) from error
            delay = retry_after(error, RATE_DELAYS[attempt]) if limited else RETRY_DELAYS[attempt]
            deadline = DEADLINE.get()
            if deadline is not None and time.time()+delay >= deadline:
                raise exhausted(attempt+1, status, 'run_deadline') from error
            if on_retry is not None:
                on_retry(attempt+1, delay, status)
            waited = time.monotonic()
            sleep_sync(delay)
            record_wait(status, delay, time.monotonic() - waited)


async def retry_async(operation, on_retry=None, session=None):
    for attempt in range(4):
        try:
            return await operation(attempt)
        except Exception as error:
            auth_status = authentication_status(error)
            if auth_status is not None:
                raise AuthenticationFailed(attempt + 1, auth_status) from error
            status = transient_status(error)
            if status is None:
                raise
            limited = status == 429
            maximum = 3 if limited else 2
            override = TRANSPORT_RETRY_LIMIT.get()
            if override is not None:
                maximum = min(maximum, override)
            exhausted = RateLimited if limited else TransportExhausted
            if attempt >= maximum:
                raise exhausted(attempt+1, status) from error
            delay = retry_after(error, RATE_DELAYS[attempt]) if limited else RETRY_DELAYS[attempt]
            deadline = DEADLINE.get()
            if deadline is not None and time.time()+delay >= deadline:
                raise exhausted(attempt+1, status, 'run_deadline') from error
            if on_retry is not None:
                on_retry(attempt+1, delay, status)
            waited = time.monotonic()
            await sleep_async(delay)
            record_wait(status, delay, time.monotonic() - waited, session)


async def metered_async_call(caller, budget, phase, initial_attempt):
    """Used by the preprocessing chat path; no nested provider retry wrapper."""
    current = initial_attempt
    async def operation(index):
        nonlocal current
        if index and budget:
            current = budget.reserve(phase, retry_of=initial_attempt)
        try:
            response = await caller()
        except Exception:
            if budget:
                budget.finish(current, None, "call_failed")
            raise
        if budget:
            budget.finish(current, response.get("usage"), "response_received")
        return response
    def on_retry(number, delay, status):
        session = getattr(budget, "session", None)
        if session:
            session.events.append("other", "warn", "Retrying upstream model request", {
                "retry": number, "delay_seconds": delay, "upstream_status": status,
                "logical_call_reused": True,
            })
    return await retry_async(operation, on_retry)


def record_wait(status, requested, actual, session=None):
    from .agent_chat_state import ACTIVE_CHAT
    from .analysis_call_context import source_node
    session = session or ACTIVE_CHAT.get()
    if session is not None:
        session.store.save("model_retry_wait", {
            "request_id": session.request_id, "source_node": source_node(),
            "upstream_status": status, "requested_seconds": requested,
            "actual_wait_seconds": actual,
        })
