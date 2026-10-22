"""Real HTTP client mocks: distinct logical calls and bounded, charged attempts."""
import asyncio
import importlib
import json

import httpx
import pytest
from fastapi import HTTPException
from test_analysis_agent import agent
from test_analysis_provider_compat import success
from test_agent_router import response

chat=importlib.import_module('modules.agent.backend.agent_chat_state')
provider=importlib.import_module('modules.agent.backend.analysis_provider')
transport=importlib.import_module('modules.agent.backend.analysis_transport')
router=importlib.import_module('modules.agent.backend.agent_router')


def session(tmp_path,monkeypatch,limit=30):
    monkeypatch.setenv('AGENT_ANALYSIS_STATE_DIR',str(tmp_path/'protected'))
    workspace=tmp_path/'workspace'
    workspace.mkdir()
    return chat.ChatSession(workspace,'fixture','retry-fixture','',limit)


@pytest.mark.parametrize('status',[502,503,504,'read_timeout'])
def test_one_transient_then_success_is_one_logical_two_http(tmp_path,monkeypatch,status):
    delays=[]
    monkeypatch.setattr(transport,'sleep_sync',delays.append)
    s=session(tmp_path,monkeypatch,limit=1)
    seen=[]
    def handler(request):
        seen.append(request)
        if len(seen)==1:
            if status=='read_timeout':
                raise httpx.ReadTimeout('synthetic',request=request)
            return httpx.Response(status,json={'error':{'message':'synthetic gateway error'}})
        return httpx.Response(200,json=success())
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        model=provider.CompatibleChatOpenAI(model='fixture',api_key='fixture',base_url='https://fixture.invalid/v1',http_client=client,max_retries=0)
        with s.activate():
            assert model.invoke('synthetic').content=='OK'
    view=s.budget.view()
    assert len(seen)==2 and delays==[5]
    assert view['model_calls']==1 and view['http_attempts']==2 and view['retry_http_attempts']==1
    assert view['known_usage_calls']==1 and view['unknown_usage_calls']==1
    with pytest.raises(RuntimeError,match='budget exhausted'):
        s.budget.reserve('analysis')


def test_three_504_attempts_are_unreviewed_and_all_accounted(tmp_path,monkeypatch):
    delays=[]
    monkeypatch.setattr(transport,'sleep_sync',delays.append)
    s=session(tmp_path,monkeypatch)
    seen=[]
    def handler(request):
        seen.append(request)
        return httpx.Response(504,json={'error':{'message':'synthetic'}})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        model=provider.CompatibleChatOpenAI(model='fixture',api_key='fixture',base_url='https://fixture.invalid/v1',http_client=client,max_retries=0)
        with s.activate(),pytest.raises(transport.TransportExhausted) as raised:
            model.invoke('synthetic')
    assert raised.value.attempts==3 and delays==[5,15] and len(seen)==3
    view=s.budget.view()
    assert view['model_calls']==1 and view['http_attempts']==3 and view['unknown_usage_calls']==3


def test_async_router_retry_keeps_one_decision(tmp_path,monkeypatch):
    s=session(tmp_path,monkeypatch)
    delays=[]
    async def sleep(value):
        delays.append(value)
    monkeypatch.setattr(transport,'sleep_async',sleep)
    seen=[]
    async def caller(*args,**kwargs):
        seen.append(kwargs)
        if len(seen)==1:
            raise HTTPException(502,'LLM API error: 504 synthetic')
        return response()
    result=asyncio.run(router.route_message(message='synthetic',history=[],recent_upload=None,previous_route=None,base_url='https://fixture.invalid/v1',api_key='fixture',model='fixture',caller=caller,budget=s.budget))
    assert result['route']=='analysis' and result['model_calls']==1 and result['parse_status']=='first_success'
    assert s.budget.view()['http_attempts']==2 and delays==[5]


def test_wrapped_400_is_not_retried(monkeypatch):
    seen=[]
    def call(index):
        seen.append(index)
        raise HTTPException(502,'LLM API error: 400 invalid argument')
    with pytest.raises(HTTPException):
        transport.retry_sync(call)
    assert seen==[0]


def test_review_exhaustion_has_incomplete_native_status(tmp_path,monkeypatch):
    from test_round11_review_loop import execute_loop
    # The graph uses the same package alias as the product's isolated tests.
    internal=importlib.import_module(agent.__package__+'.analysis_internal_review')
    local_transport=importlib.import_module(agent.__package__+'.analysis_transport')
    from test_round8_closure import sealed,fake_execution
    from langgraph.checkpoint.memory import InMemorySaver
    from types import SimpleNamespace
    tools,_,_=sealed(tmp_path,monkeypatch)
    fake_execution(tools)
    tools._internal_review_model=object()
    def unavailable(*args,**kwargs):
        raise local_transport.TransportExhausted(3,504)
    monkeypatch.setattr(internal,'run_review',unavailable)
    class Coder:
        def invoke(self,payload,config=None):
            tools.write_code('/work/analysis.py','# synthetic')
            tools.run_python()
            return {'messages':[SimpleNamespace(content='Synthetic draft') ]}
    validator=importlib.import_module(agent.__package__+'.analysis_validation').ArtifactValidator()
    result=agent._build_graph(Coder(),tools,validator,InMemorySaver()).invoke({'request':'synthetic','history':[],'iterations':0},{'configurable':{'thread_id':'transport'}})
    assert result['status']=='incomplete_review'
    assert result['validation']['internal_review']['decision']=='unreviewed'
    assert tools.last_execution['exit_code']==0


def test_pipeline_retry_is_metered_without_nested_retries(tmp_path,monkeypatch):
    s=session(tmp_path,monkeypatch)
    seen=[]
    delays=[]
    async def sleep(value):
        delays.append(value)
    monkeypatch.setattr(transport,'sleep_async',sleep)
    async def caller():
        seen.append(1)
        if len(seen)==1:
            raise HTTPException(502,'LLM API error: 504 synthetic')
        return success()
    initial=s.budget.reserve('pipeline')
    value=asyncio.run(transport.metered_async_call(caller,s.budget,'pipeline',initial))
    assert value['choices'][0]['message']['content']=='OK'
    assert s.budget.view()['model_calls']==1 and s.budget.view()['http_attempts']==2
    assert delays==[5] and len(seen)==2
