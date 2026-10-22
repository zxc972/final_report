"""Terminal router transport failures must not count as model format strikes."""
import json

import httpx
import pytest
from fastapi import HTTPException
from test_agent_auto_dispatch import setup_api, get_events
from modules.agent.backend import api
from modules.agent.backend import analysis_transport as transport
from modules.agent.backend.analysis_failure_classification import classify, should_stop
from test_agent_router import response


@pytest.mark.parametrize('status', [502, 503, 504, 'read_timeout'])
def test_router_transport_exhaustion_is_not_a_model_strike(setup_api, monkeypatch, status):
    client, payload, _, _, calls, runner, identity, _ = setup_api
    delays = []
    attempts = []

    async def sleep(delay):
        delays.append(delay)

    async def unavailable(*args, **kwargs):
        attempts.append(1)
        if status == 'read_timeout':
            raise httpx.ReadTimeout('Synthetic transport timeout')
        raise HTTPException(502, f'LLM API error: {status} synthetic')

    monkeypatch.setattr(transport, 'sleep_async', sleep)
    monkeypatch.setattr(api, 'call_chat_completions', unavailable)
    result = client.post('/api/agent/chat', json=payload)
    assert result.status_code == 200
    metadata = result.json()['metadata']
    assert metadata['status'] == 'route_failed' and metadata['route'] is None
    classification = classify(metadata)
    assert classification['category'] == 'upstream_transport_error'
    assert classification['stop_eligible'] is False
    assert should_stop([classification, classification]) is False
    assert metadata['routing']['failureKind'] == 'upstream_transport_error'
    assert metadata['requestBudget']['model_calls'] == 1
    assert metadata['requestBudget']['http_attempts'] == 3
    assert metadata['requestBudget']['unknown_usage_calls'] == 3
    assert len(attempts) == 3 and delays == [5, 15]
    runner.assert_not_called()
    event = get_events(client, payload, identity).json()['events'][-1]
    assert event['detail']['failure_kind'] == 'upstream_transport_error'
    assert 'fixture-private-value' not in json.dumps(event)


def test_json_route_failure_still_counts_as_a_strike(setup_api, monkeypatch):
    client, payload, _, _, _, runner, _, _ = setup_api

    async def malformed(*args, **kwargs):
        value = response()
        value['choices'][0]['message']['content'] = 'Not a routing JSON object'
        return value

    monkeypatch.setattr(api, 'call_chat_completions', malformed)
    metadata = client.post('/api/agent/chat', json=payload).json()['metadata']
    classification = classify(metadata)
    assert classification['category'] == 'route_failed'
    assert classification['stop_eligible'] is True
    assert should_stop([classification, classification]) is True
    assert metadata['requestBudget']['http_attempts'] == 2
    runner.assert_not_called()


def test_recovered_router_transport_stays_a_success(setup_api, monkeypatch):
    client, payload, _, _, _, runner, _, _ = setup_api
    attempts = []

    async def sleep(delay):
        assert delay == 5

    async def recovered(*args, **kwargs):
        attempts.append(1)
        if len(attempts) == 1:
            raise HTTPException(502, 'LLM API error: 504 synthetic')
        return response()

    monkeypatch.setattr(transport, 'sleep_async', sleep)
    monkeypatch.setattr(api, 'call_chat_completions', recovered)
    metadata = client.post('/api/agent/chat', json=payload).json()['metadata']
    assert metadata['route'] == 'analysis' and metadata['status'] == 'completed'
    assert classify(metadata)['category'] is None
    assert 'failureKind' not in metadata['routing']
    assert metadata['requestBudget']['router_http_attempts'] == 2
    runner.assert_called_once()