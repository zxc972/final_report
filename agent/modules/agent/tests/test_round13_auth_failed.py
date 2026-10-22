"""Permission errors are single-attempt environment failures, never model strikes."""

import asyncio
import importlib
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException
from langgraph.checkpoint.memory import InMemorySaver

from test_analysis_agent import agent
from test_agent_auto_dispatch import setup_api, get_events
from test_round11_transport import session
from test_round8_closure import sealed, fake_execution

transport = importlib.import_module('modules.agent.backend.analysis_transport')
provider = importlib.import_module('modules.agent.backend.analysis_provider')
router = importlib.import_module('modules.agent.backend.agent_router')
classification = importlib.import_module('modules.agent.backend.analysis_failure_classification')
CASES = [(403, {'code': 'SUBSCRIPTION_NOT_FOUND'}),
         (401, {'error': {'message': 'Synthetic invalid credentials'}}),
         (403, {'error': {'message': 'Synthetic access denied'}})]


@pytest.mark.parametrize('status,body', CASES)
def test_permission_http_is_charged_once_without_wait(tmp_path, monkeypatch, status, body):
    state = session(tmp_path, monkeypatch)
    calls, delays = [], []
    monkeypatch.setattr(transport, 'sleep_sync', delays.append)

    def handler(request):
        calls.append(1)
        return httpx.Response(status, json=body)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        model = provider.CompatibleChatOpenAI(model='fixture', api_key='fixture',
                    base_url='https://fixture.invalid/v1', http_client=client, max_retries=0)
        with state.activate(), pytest.raises(transport.AuthenticationFailed) as error:
            model.invoke('Synthetic offline permission test')
    assert error.value.status_code == status and error.value.attempts == 1
    assert len(calls) == 1 and delays == []
    counts = state.budget.view()
    assert counts['model_calls'] == counts['http_attempts'] == counts['unknown_usage_calls'] == 1


@pytest.mark.parametrize('status,body', CASES)
def test_router_permission_never_uses_protocol_retry(tmp_path, monkeypatch, status, body):
    state = session(tmp_path, monkeypatch)
    calls = []

    async def caller(*args, **kwargs):
        calls.append(1)
        raise HTTPException(502, 'LLM API error: ' + str(status) + ' ' + str(body))

    result = asyncio.run(router.route_message(message='Synthetic inspection', history=[],
                recent_upload=None, previous_route=None, base_url='https://fixture.invalid/v1',
                api_key='fixture', model='fixture', caller=caller, budget=state.budget))
    assert result['route'] is None and result['fallback'] is False
    assert result['failure_kind'] == result['parse_status'] == 'environment_auth_failed'
    assert result['upstream_status'] == status and len(calls) == result['model_calls'] == 1
    assert 'clarify' not in result['reason'].lower()


@pytest.mark.parametrize('status,body', CASES)
def test_auto_api_permission_reply_and_events(setup_api, status, body):
    client, payload, choices, _, calls, runner, identity, _ = setup_api
    choices[:] = [HTTPException(502, 'LLM API error: ' + str(status) + ' ' + str(body))]
    response = client.post('/api/agent/chat', json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data['message'] == transport.AUTH_FAILURE_MESSAGE
    assert data['metadata']['status'] == 'environment_auth_failed'
    assert data['metadata']['requestBudget']['http_attempts'] == 1
    assert len(calls) == 1
    runner.assert_not_awaited()
    events = get_events(client, payload, identity).json()['events']
    assert any(e['detail'].get('event') == 'environment_auth_failed' for e in events)
    assert not any(e['title'].startswith('Routed to ') for e in events)


def test_permission_does_not_strike_model_but_pauses_whole_batch():
    observed = classification.classify({'status': 'environment_auth_failed', 'route': None})
    assert observed['category'] == 'environment_auth_failed' and not observed['stop_eligible']
    assert not classification.should_stop([observed, observed])
    action = classification.rate_limit_batch_action(0, observed)
    assert action['stop_batch'] and action['pause_seconds'] == 0
    assert action['reason'] == 'environment_auth_failed'


@pytest.mark.parametrize('where', ['coding', 'review'])
def test_outer_graph_does_not_retry_permission(tmp_path, monkeypatch, where):
    tools, _, _ = sealed(tmp_path, monkeypatch)
    local_transport = importlib.import_module(agent.__package__ + '.analysis_transport')
    internal = importlib.import_module(agent.__package__ + '.analysis_internal_review')
    fake_execution(tools)
    calls = []

    class Coder:
        def invoke(self, payload, config=None):
            calls.append('coding')
            if where == 'coding':
                raise local_transport.AuthenticationFailed(1, 403)
            tools.write_code('/work/analysis.py', '# synthetic permission test')
            tools.run_python()
            return {'messages': [SimpleNamespace(content='Synthetic retained result')]}

    if where == 'review':
        tools._internal_review_model = object()
        def unavailable(*args, **kwargs):
            calls.append('review')
            raise local_transport.AuthenticationFailed(1, 401)
        monkeypatch.setattr(internal, 'run_review', unavailable)
    validator = importlib.import_module(agent.__package__ + '.analysis_validation').ArtifactValidator()
    result = agent._build_graph(Coder(), tools, validator, InMemorySaver()).invoke(
        {'request': 'Synthetic permission replay', 'history': [], 'iterations': 0},
        {'configurable': {'thread_id': 'auth-' + where}})
    assert result['status'] == 'environment_auth_failed' and result['iterations'] == 1
    assert result['message'] == local_transport.AUTH_FAILURE_MESSAGE
    assert calls == (['coding'] if where == 'coding' else ['coding', 'review'])
    observed = classification.classify(result)
    assert observed['category'] == 'environment_auth_failed' and not observed['stop_eligible']
