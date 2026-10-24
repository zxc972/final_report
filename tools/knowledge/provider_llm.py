"""Small, metered adapter for the development instance's chat-completions API.

Credentials stay in memory. Every HTTP attempt reserves the shared budget before
sending; successful logical calls can be replayed after interruption without
issuing another request. This adapter never invokes an analysis agent or tool.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import threading
import time
from urllib.parse import urlsplit
import uuid

import httpx

_SCOPE = ContextVar("condition_canon_scope", default=None)
_PROVIDER = None


class ProviderFailure(RuntimeError):
    """Sanitised provider failure; no upstream response or credential attached."""


@dataclass(frozen=True)
class Config:
    base_url: str
    api_key: str = field(repr=False)
    model: str = "deepseek-v4.1-flash"
    temperature: float = 0.7
    timeout: float = 120.0
    max_tokens: int = 2048
    max_attempts: int = 3
    thinking: str | None = None
    json_output: bool = False

    def public(self):
        u = urlsplit(self.base_url)
        public = {
            "endpoint_host": u.hostname,
            "endpoint_path": u.path,
            "model": self.model,
            "temperature": self.temperature,
            "timeout": self.timeout,
            "max_tokens": self.max_tokens,
            "max_attempts": self.max_attempts,
        }
        if self.thinking is not None:
            public["thinking"] = {"type": self.thinking}
        if self.json_output:
            public["response_format"] = {"type": "json_object"}
        return public

    def request(self, prompt):
        body = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if self.thinking is not None:
            if self.thinking not in {"enabled", "disabled"}:
                raise ValueError("Unsupported thinking setting")
            body["thinking"] = {"type": self.thinking}
        if self.json_output:
            body["response_format"] = {"type": "json_object"}
        return body


def load_config(config_path=None, **overrides):
    values = {
        name: os.environ[name]
        for name in ("PLATFORM_API_BASE_URL", "PLATFORM_API_KEY")
        if os.environ.get(name)
    }
    if config_path:
        for line in Path(config_path).read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.lstrip().startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip().strip("\"'")
    base = values.get("PLATFORM_API_BASE_URL", "").rstrip("/")
    if not base.endswith("/v1"):
        base += "/v1"
    u = urlsplit(base)
    if (
        u.scheme != "https"
        or not u.hostname
        or u.username
        or u.password
        or u.query
        or u.fragment
    ):
        raise ProviderFailure(
            "A credential-free HTTPS development endpoint is required"
        )
    key = values.get("PLATFORM_API_KEY", "")
    if not key:
        raise ProviderFailure("Development provider credential is not configured")
    return Config(base_url=base, api_key=key, **overrides)


@contextmanager
def scope(arm, item_id, sample):
    token = _SCOPE.set(
        {
            "arm": arm,
            "item_id": item_id,
            "sample": sample,
            "logical_id": f"{arm}:{item_id}:{sample}",
        }
    )
    try:
        yield
    finally:
        _SCOPE.reset(token)


def _number(value):
    return (
        value
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0
        else None
    )


def usage_counts(usage):
    if not isinstance(usage, dict):
        return {"input_tokens": None, "output_tokens": None, "total_tokens": None}
    return {
        "input_tokens": _number(usage.get("prompt_tokens", usage.get("input_tokens"))),
        "output_tokens": _number(
            usage.get("completion_tokens", usage.get("output_tokens"))
        ),
        "total_tokens": _number(usage.get("total_tokens")),
    }


class Provider:
    def __init__(
        self,
        config,
        ledger_dir,
        max_requests=800,
        client=None,
        sleep=time.sleep,
        minimum_interval=0.0,
        authorized_max_requests=1200,
    ):
        # Preserve legacy authorization unless a later round explicitly raises it.
        if not 1 <= max_requests <= authorized_max_requests <= 1500:
            raise ValueError("HTTP cap exceeds the explicit round authorization")
        self.config, self.max_requests, self.sleep = config, max_requests, sleep
        self.folder = Path(ledger_dir)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.ledger = self.folder / "calls.jsonl"
        self.lock = threading.RLock()
        self.events = []
        if self.ledger.exists():
            for line in self.ledger.read_text(encoding="utf-8").splitlines():
                self.events.append(json.loads(line))
        self.client = client or httpx.Client(
            timeout=config.timeout, follow_redirects=False
        )
        self.cache_hits = 0
        self.cooldown_until = 0.0
        self.pace_lock = threading.Lock()
        self.minimum_interval = float(minimum_interval)
        self.current_interval = float(minimum_interval)
        self.next_start = 0.0
        self.success_streak = 0

    def _append(self, event):
        event = {"time": datetime.now(timezone.utc).isoformat(), **event}
        # No headers, URL query, credential, raw exception or upstream error body.
        raw = json.dumps(event, ensure_ascii=False).replace(
            self.config.api_key, "[REDACTED]"
        )
        with self.ledger.open("a", encoding="utf-8") as stream:
            stream.write(raw + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        self.events.append(json.loads(raw))

    def complete(self, prompt):
        context = _SCOPE.get()
        if context is None:
            raise ProviderFailure("Algorithm call scope is required")
        digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        config_digest = hashlib.sha256(
            json.dumps(self.config.public(), sort_keys=True).encode()
        ).hexdigest()
        logical = context["logical_id"]
        with self.lock:
            previous = [e for e in self.events if e.get("logical_id") == logical]
            if any(
                e.get("prompt_sha256") != digest
                or e.get("config_sha256") != config_digest
                for e in previous
                if e["event"] == "start"
            ):
                raise ProviderFailure(
                    "A cached logical call has different frozen input"
                )
            done = [
                e
                for e in previous
                if e["event"] == "end"
                and (
                    e.get("status") == "ok"
                    or (
                        e.get("status") == "invalid_response"
                        and e.get("finish_reason") == "length"
                    )
                )
            ]
            if done:
                self.cache_hits += 1
                return done[-1].get("text", "")
            prior_attempts = sum(e["event"] == "start" for e in previous)
        for attempt in range(prior_attempts + 1, self.config.max_attempts + 1):
            # Serialize departure times, not HTTP responses. This prevents all
            # workers from issuing a new burst when a shared cooldown expires.
            with self.pace_lock:
                with self.lock:
                    delay = max(
                        0.0,
                        max(self.cooldown_until, self.next_start) - time.monotonic(),
                    )
                if delay:
                    self.sleep(delay)
                with self.lock:
                    self.next_start = time.monotonic() + self.current_interval
            with self.lock:
                count = sum(e["event"] == "start" for e in self.events)
                if count >= self.max_requests:
                    raise ProviderFailure("The shared HTTP attempt budget is exhausted")
                request_id = uuid.uuid4().hex
                self._append(
                    {
                        "event": "start",
                        "request_id": request_id,
                        **context,
                        "ordinal": count + 1,
                        "attempt": attempt,
                        "prompt_sha256": digest,
                        "config_sha256": config_digest,
                        "model": self.config.model,
                        "temperature": self.config.temperature,
                        "settings": self.config.public(),
                        "transport_interval": self.current_interval,
                    }
                )
            started = time.monotonic()
            status, http_status, text, observed, finish, usage = (
                "transport_error",
                None,
                None,
                None,
                None,
                None,
            )
            reasoning_present, reasoning_tokens = None, None
            try:
                response = self.client.post(
                    self.config.base_url + "/chat/completions",
                    headers={"Authorization": "Bearer " + self.config.api_key},
                    json=self.config.request(prompt),
                )
                http_status = response.status_code
                status = "http_error"
                if 200 <= http_status < 300:
                    status = "invalid_response"
                    try:
                        data = response.json()
                        usage = data.get("usage") if isinstance(data, dict) else None
                        observed = data.get("model") if isinstance(data, dict) else None
                        choices = (
                            data.get("choices", []) if isinstance(data, dict) else []
                        )
                        first = choices[0] if choices else {}
                        finish = first.get("finish_reason")
                        text = first.get("message", {}).get("content")
                        reasoning_present = bool(
                            first.get("message", {}).get("reasoning_content")
                        )
                        if isinstance(usage, dict):
                            detail = usage.get("completion_tokens_details") or {}
                            if isinstance(detail, dict):
                                reasoning_tokens = _number(
                                    detail.get("reasoning_tokens")
                                )
                        # A length-limited reasoning response can contain no answer.
                        # Preserve it as an empty model answer, never retry a bad answer.
                        if text is None and finish == "length":
                            text = ""
                        if isinstance(text, str):
                            status = "ok"
                    except (ValueError, TypeError, AttributeError, IndexError):
                        pass
            except httpx.HTTPError:
                pass
            event = {
                "event": "end",
                "request_id": request_id,
                **context,
                "attempt": attempt,
                "status": status,
                "http_status": http_status,
                "seconds": round(time.monotonic() - started, 4),
                "observed_model": observed,
                "finish_reason": finish,
                "reasoning_content_present": reasoning_present,
                "reasoning_tokens": reasoning_tokens,
                **usage_counts(usage),
            }
            if status == "ok":
                event["text"] = text
            with self.lock:
                self._append(event)
                if status == "ok":
                    self.success_streak += 1
                    if self.success_streak >= 32:
                        self.current_interval = max(
                            self.minimum_interval, self.current_interval * 0.9
                        )
                        self.success_streak = 0
                if http_status == 429:
                    self.success_streak = 0
                    self.current_interval = min(
                        6.0, max(self.minimum_interval, self.current_interval * 1.25)
                    )
                    # Transport backoff only; no change to sampling or scoring.
                    self.cooldown_until = max(
                        self.cooldown_until, time.monotonic() + 15.0
                    )
            if status == "ok":
                return text
            retryable = status == "transport_error" or http_status in {
                429,
                500,
                502,
                503,
                504,
            }
            if not retryable or attempt == self.config.max_attempts:
                raise ProviderFailure(
                    f"Provider request failed ({status}, HTTP {http_status}); see metered ledger"
                )
            self.sleep(min(8, 2 ** (attempt - 1)))
        raise ProviderFailure(
            "Maximum attempts for this logical call were already consumed"
        )

    def response_info(self, arm, item_id, sample):
        """Read only whitelisted metadata for a received or cached logical call."""
        logical = f"{arm}:{item_id}:{sample}"
        with self.lock:
            ends = [
                e
                for e in self.events
                if e["event"] == "end" and e.get("logical_id") == logical
            ]
        if not ends:
            return {}
        return {
            key: ends[-1].get(key)
            for key in [
                "request_id",
                "finish_reason",
                "status",
                "reasoning_content_present",
                "reasoning_tokens",
            ]
        }

    def stats(self, arm=None):
        with self.lock:
            events = [e for e in self.events if arm is None or e.get("arm") == arm]
        starts = [e for e in events if e["event"] == "start"]
        ended = {e["request_id"]: e for e in events if e["event"] == "end"}
        requests = [ended.get(s["request_id"], {}) for s in starts]
        received = lambda r: r.get("status") == "ok" or (
            r.get("status") == "invalid_response" and r.get("finish_reason") == "length"
        )
        return {
            "logical_calls": len({s["logical_id"] for s in starts}),
            "http_attempts": len(starts),
            "successful_requests": sum(received(r) for r in requests),
            "failed_requests": sum(bool(r) and not received(r) for r in requests),
            "unfinished_requests": sum(not r for r in requests),
            "length_limited_responses": sum(
                r.get("finish_reason") == "length" for r in requests
            ),
            "historical_null_length_responses": sum(
                r.get("status") == "invalid_response"
                and r.get("finish_reason") == "length"
                for r in requests
            ),
            "unknown_usage_requests": sum(
                any(
                    r.get(k) is None
                    for k in ["input_tokens", "output_tokens", "total_tokens"]
                )
                for r in requests
            ),
            **{
                k: sum(r.get(k) or 0 for r in requests)
                for k in ["input_tokens", "output_tokens", "total_tokens"]
            },
            "observed_models": sorted(
                {
                    r["observed_model"]
                    for r in requests
                    if isinstance(r.get("observed_model"), str)
                }
            ),
        }

    def close(self):
        self.client.close()


def configure(config=None, **kwargs):
    global _PROVIDER
    _PROVIDER = Provider(config or load_config(), **kwargs)
    return _PROVIDER


def complete(prompt):
    if _PROVIDER is None:
        raise ProviderFailure(
            "Configure the development adapter before calling complete"
        )
    return _PROVIDER.complete(prompt)
