"""Offline router classification protocol, conservative fallbacks and request charges."""

import asyncio
import json
from pathlib import Path

import pytest

from modules.agent.backend.agent_router import ROUTER_PROMPT, parse_route, route_message
from modules.agent.backend.agent_chat_state import ChatSession


def response(route="analysis", reason="Measure existing reconstructed outputs."):
    return {
        "choices": [
            {"message": {"content": json.dumps({"route": route, "reason": reason})}}
        ],
        "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
    }


def session(tmp_path, monkeypatch, limit=64):
    monkeypatch.setenv("AGENT_ANALYSIS_STATE_DIR", str(tmp_path / "state"))
    work = tmp_path / "alice/output"
    work.mkdir(parents=True, exist_ok=True)
    return ChatSession(
        work, "alice", "test-conversation", "fixture-private-value", limit
    )


def invoke(caller, budget, previous=None, message="Check the uploaded reconstruction."):
    return asyncio.run(
        route_message(
            message=message,
            history=[{"role": "assistant", "content": "Reconstruction exists."}],
            recent_upload={"subjectId": "sub-01", "t1Path": "/synthetic/T1.nii"},
            previous_route=previous,
            base_url="https://example.invalid/v1",
            api_key="fixture-private-value",
            model="offline",
            caller=caller,
            budget=budget,
        )
    )


@pytest.mark.parametrize("route", ["pipeline", "analysis"])
def test_single_structured_call_is_reserved_before_model(route, tmp_path, monkeypatch):
    s = session(tmp_path, monkeypatch)
    calls = []

    async def model(*args, **kwargs):
        assert len(s.budget.records) == 1
        assert s.budget.records[0]["status"] == "started"
        calls.append((args, kwargs))
        return response(route)

    result = invoke(model, s.budget)
    assert result["route"] == route and not result["fallback"]
    assert len(calls) == 1 and calls[0][1] == {
        "response_format": {"type": "json_object"},
        "temperature": 0,
    }
    assert calls[0][0][4] == []
    sent = json.loads(calls[0][0][3][1]["content"])
    assert sent["history"][0]["content"] == "Reconstruction exists."
    assert sent["recentUpload"]["subjectId"] == "sub-01"
    assert s.budget.view()["model_calls"] == 1
    assert s.budget.view()["known_tokens"]["total_tokens"] == 18
    assert s.budget.view()["unknown_usage_calls"] == 0
    assert "fixture-private-value" not in "".join(
        p.read_text() for p in s.store.root.glob("*.json")
    )


@pytest.mark.parametrize("previous", [None, "analysis"])
@pytest.mark.parametrize(
    "content",
    [
        "not-json",
        '```json\n{"route":"analysis","reason":"Measure."}\n```',
        '{"route":"shell","reason":"Do things."}',
        '{"route":"analysis","reason":"中文"}',
        json.dumps({"route": "analysis", "reason": "x" * 1801}),
        '{"route":"analysis","reason":"Measure.","extra":true}',
    ],
)
def test_invalid_json_or_schema_uses_previous_or_preprocessing(
    content, previous, tmp_path, monkeypatch
):
    s = session(tmp_path, monkeypatch)

    async def model(*args, **kwargs):
        return {"choices": [{"message": {"content": content}}]}

    result = invoke(model, s.budget, previous)
    assert result["route"] == (previous or "pipeline")
    assert result["fallback"] is True and result["reason"].startswith("Fallback:")
    assert len(result["reason"]) <= 120
    assert (
        s.budget.view()["model_calls"] == 1
        and s.budget.view()["unknown_usage_calls"] == 1
    )
    assert s.budget.view()["cost"] is None


@pytest.mark.parametrize("previous", [None, "analysis"])
def test_failed_model_call_is_charged_and_does_not_leak_exception(
    previous, tmp_path, monkeypatch
):
    s = session(tmp_path, monkeypatch)

    async def model(*args, **kwargs):
        raise RuntimeError("fixture-private-value")

    result = invoke(model, s.budget, previous)
    assert result["route"] == (previous or "pipeline") and result["fallback"]
    assert "fixture-private-value" not in json.dumps(result)
    assert s.budget.view()["unknown_usage_calls"] == 1


def test_mixed_request_policy_requires_preprocessing_then_a_later_request(
    tmp_path, monkeypatch
):
    s = session(tmp_path, monkeypatch)

    async def model(*args, **kwargs):
        assert (
            "If one message requests both preprocessing and subsequent analysis, choose pipeline"
            in args[3][0]["content"]
        )
        assert "Do not chain both routes" in ROUTER_PROMPT
        assert "then measure" in json.loads(args[3][1]["content"])["message"]
        return response(
            "pipeline", "Start reconstruction; request analysis after it completes."
        )

    result = invoke(
        model,
        s.budget,
        message="Reconstruct the raw T1 first, then measure cortical thickness.",
    )
    assert result["route"] == "pipeline" and "after" in result["reason"]


def test_router_consumes_the_request_budget(tmp_path, monkeypatch):
    s = session(tmp_path, monkeypatch, limit=1)

    async def model(*args, **kwargs):
        return response("pipeline")

    invoke(model, s.budget)
    with pytest.raises(RuntimeError, match="budget exhausted"):
        s.budget.reserve("pipeline")
    assert s.budget.view()["router_calls"] == 1


@pytest.mark.parametrize(
    "raw", [None, {}, {"choices": []}, {"choices": [{"message": {"content": None}}]}]
)
def test_malformed_provider_shapes_fall_back(raw, tmp_path, monkeypatch):
    s = session(tmp_path, monkeypatch)

    async def model(*args, **kwargs):
        return raw

    result = invoke(model, s.budget)
    assert result["route"] == "pipeline" and result["fallback"]


def test_structured_transport_uses_temperature_zero_without_tool_choice(monkeypatch):
    from types import SimpleNamespace
    from modules.agent.backend import llm

    seen = []

    class Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, json, headers):
            seen.append((url, json))
            return SimpleNamespace(status_code=200, json=lambda: response())

    monkeypatch.setattr(llm.httpx, "AsyncClient", Client)
    asyncio.run(
        llm.call_chat_completions(
            "https://example.invalid/v1",
            "fixture-private-value",
            "offline",
            [],
            [],
            response_format={"type": "json_object"},
            temperature=0,
        )
    )
    assert seen[0][0] == "https://example.invalid/v1/chat/completions"
    wire = seen[0][1]
    assert wire["temperature"] == 0 and wire["response_format"] == {
        "type": "json_object"
    }
    assert "tools" not in wire and "tool_choice" not in wire


def test_long_valid_reason_keeps_route_and_marks_truncation():
    value = parse_route(response("analysis", "Inspect existing data. " * 10))
    assert value["route"] == "analysis"
    assert len(value["reason"]) == 120
    assert value["reason_truncated"] is True
    assert value["notice"] == "reason truncated"
