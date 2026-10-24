"""Narrow, bounded compatibility fallback for optional provider fields.

Only explicit HTTP400 unknown/unsupported thinking is eligible. Other bad
requests, auth/rate/context errors propagate unchanged. Every retry still passes
through the configured audited HTTP client. No scientific output is repaired.
"""

from __future__ import annotations
import threading, warnings
from typing import Any
from pydantic import PrivateAttr
from openai import BadRequestError
from langchain_openai import ChatOpenAI


def unsupported_thinking(error: Exception) -> bool:
    if not isinstance(error, BadRequestError):
        return False
    body = getattr(error, "body", None)
    if not isinstance(body, dict):
        return False
    detail = body.get("error", body)
    if not isinstance(detail, dict):
        return False
    message = str(detail.get("message", "")).lower()
    param = str(detail.get("param", "")).lower()
    named = param == "thinking" or '"thinking"' in message or "'thinking'" in message
    return named and any(
        x in message
        for x in (
            "unknown_parameter",
            "unknown field",
            "unsupported parameter",
            "unrecognized request argument",
        )
    )


class CompatibleChatOpenAI(ChatOpenAI):
    _compat_lock: Any = PrivateAttr(default_factory=threading.RLock)
    _thinking_removed: bool = PrivateAttr(default=False)

    def _remove_rejected_thinking(self, error: Exception) -> bool:
        if self.streaming or not unsupported_thinking(error):
            return False
        with self._compat_lock:
            if (
                self._thinking_removed
                or not isinstance(self.extra_body, dict)
                or "thinking" not in self.extra_body
            ):
                return False
            body = dict(self.extra_body)
            body.pop("thinking")
            self.extra_body = body or None
            self._thinking_removed = True
            warnings.warn(
                "Gateway explicitly rejected optional thinking; one retry omits only that field. Original HTTP error remains auditable.",
                RuntimeWarning,
                stacklevel=2,
            )
            return True

    def _mark(self, result: Any, retried: bool) -> Any:
        if self._thinking_removed:
            for generation in result.generations:
                generation.message.response_metadata = {
                    **generation.message.response_metadata,
                    "provider_compatibility": {
                        "omitted_optional_fields": ["thinking"],
                        "reason": "explicit upstream unknown parameter",
                        "retry_in_this_call": retried,
                    },
                }
        return result

    def _create_chat_result(self, response, generation_info=None):
        # Preserve an actual response identity; the SDK may otherwise fall back
        # to its configured request model when response.model is absent.
        raw = response if isinstance(response, dict) else response.model_dump()
        result = super()._create_chat_result(response, generation_info)
        observed = raw.get("model") if isinstance(raw, dict) else None
        if isinstance(observed, str):
            result.llm_output = {**(result.llm_output or {}), "observed_provider_model": observed}
        return result

    def _reserve_usage(self, retry_of=None):
        from .analysis_review_budget import reserve_http_attempt
        reserve_http_attempt()
        from .agent_chat_state import ACTIVE_CHAT

        session = ACTIVE_CHAT.get()
        from .analysis_call_context import source_node
        return (
            (session.budget, (session.budget.reserve("analysis", retry_of=retry_of, source_node=source_node()) if retry_of else session.budget.reserve("analysis", source_node=source_node())))
            if session
            else (None, None)
        )

    @staticmethod
    def _finish_usage(charge, result=None, error=None):
        budget, attempt = charge
        if budget is None:
            return
        usage = (
            (result.llm_output or {}).get("token_usage") if result is not None else None
        )
        model = (result.llm_output or {}).get("observed_provider_model") if result is not None else None
        budget.finish(attempt, usage, "call_failed" if error else "response_received", model=model)

    @staticmethod
    def _retry_event(attempt, delay, status):
        from .agent_chat_state import ACTIVE_CHAT
        session = ACTIVE_CHAT.get()
        if session:
            session.events.append("other", "warn", "Retrying upstream model request", {
                "retry": attempt, "delay_seconds": delay,
                "upstream_status": status, "logical_call_reused": True,
            })

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        from .analysis_transport import retry_sync
        first_charge = None
        compat_retried = False
        def attempt(index):
            nonlocal first_charge, compat_retried
            charge = self._reserve_usage(first_charge[1] if index and first_charge else None)
            if first_charge is None:
                first_charge = charge
            try:
                result = super(CompatibleChatOpenAI, self)._generate(
                    messages, stop=stop, run_manager=run_manager, **kwargs)
            except Exception as error:
                self._finish_usage(charge, error=error)
                raise
            self._finish_usage(charge, result=result)
            return result
        try:
            result = retry_sync(attempt, self._retry_event)
        except Exception as error:
            if not self._remove_rejected_thinking(error):
                raise
            # Preserve the separately metered historical compatibility attempt.
            first_charge = None
            compat_retried = True
            result = retry_sync(attempt, self._retry_event)
        return self._mark(result, compat_retried)

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        from .analysis_transport import retry_async
        first_charge = None
        compat_retried = False
        async def attempt(index):
            nonlocal first_charge, compat_retried
            charge = self._reserve_usage(first_charge[1] if index and first_charge else None)
            if first_charge is None:
                first_charge = charge
            try:
                result = await super(CompatibleChatOpenAI, self)._agenerate(
                    messages, stop=stop, run_manager=run_manager, **kwargs)
            except Exception as error:
                self._finish_usage(charge, error=error)
                raise
            self._finish_usage(charge, result=result)
            return result
        try:
            result = await retry_async(attempt, self._retry_event)
        except Exception as error:
            if not self._remove_rejected_thinking(error):
                raise
            first_charge = None
            compat_retried = True
            result = await retry_async(attempt, self._retry_event)
        return self._mark(result, compat_retried)
