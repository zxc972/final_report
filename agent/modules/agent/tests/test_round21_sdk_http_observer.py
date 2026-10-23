"""Actual installed OpenAI SDK -> local HTTP server; no provider or mocked transport."""
import asyncio
import importlib
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
from types import SimpleNamespace
import pytest
from openai import OpenAI, AsyncOpenAI, RateLimitError
from backend.analysis_http_observer import HTTPObserver
from backend.analysis_call_context import HTTP_ATTEMPT
from backend.agent_chat_state import ACTIVE_CHAT, RequestBudget


@pytest.mark.parametrize('asynchronous,status',[(False,200),(True,200),(False,429)])
def test_real_sdk_httpx2_send_matches_native_charge_id_and_usage(monkeypatch,asynchronous,status):
    monkeypatch.setenv('NO_PROXY','127.0.0.1,localhost')
    received=[];observed=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            body=json.loads(self.rfile.read(int(self.headers['Content-Length'])));received.append(body)
            payload={'id':'local-chat','model':'local-fixture','choices':[{'index':0,'message':{'role':'assistant','content':'fixture'},'finish_reason':'stop'}],'usage':{'prompt_tokens':11,'completion_tokens':3,'total_tokens':14}} if status==200 else {'error':{'message':'local simulated rate limit','type':'rate_limit','code':'rate_limit'}}
            raw=json.dumps(payload).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=lambda:server.serve_forever(poll_interval=.01),daemon=True);thread.start()
    class Store:
        def save(self,*args):pass
    session=SimpleNamespace(request_id='local-sdk-request',store=Store(),analysis_tools=None)
    session.budget=RequestBudget(session,3)
    def begin(request):
        assert request.url.host=='127.0.0.1'
        assert ACTIVE_CHAT.get() is session
        attempt=HTTP_ATTEMPT.get();record=next(r for r in session.budget.records if r['id']==attempt)
        return {'native_attempt_id':attempt,'logical_id':record['logical_id']}
    def finish(ticket,response=None,error=None):
        assert ticket is not None
        ticket.update(http_status=response.status_code if response is not None else None,usage=response.json().get('usage') if response is not None else None,error_type=type(error).__name__ if error else None);observed.append(ticket)
    url='http://127.0.0.1:'+str(server.server_port)+'/v1'
    async def execute():
        token=ACTIVE_CHAT.set(session);attempt=session.budget.reserve('router')
        try:
            if asynchronous:
                async with AsyncOpenAI(base_url=url,api_key='local-fake-credential',max_retries=0,timeout=5) as client:
                    response=await client.chat.completions.create(model='local-fixture',messages=[{'role':'user','content':'offline fixture'}])
            else:
                with OpenAI(base_url=url,api_key='local-fake-credential',max_retries=0,timeout=5) as client:
                    response=client.chat.completions.create(model='local-fixture',messages=[{'role':'user','content':'offline fixture'}])
            session.budget.finish(attempt,response.usage.model_dump(),'response_received')
        except RateLimitError:
            assert status==429;session.budget.finish(attempt,None,'call_failed')
        finally:ACTIVE_CHAT.reset(token)
    try:
        with HTTPObserver(begin,finish) as observer:
            asyncio.run(execute())
            assert any(r['module']=='httpx2' for r in observer.coverage)
        assert len(received)==len(observed)==len(session.budget.records)==1
        assert observed[0]['native_attempt_id']==session.budget.records[0]['id']
        assert observed[0]['http_status']==status
        assert observed[0]['usage']==session.budget.records[0]['usage']
        assert 'local-fake-credential' not in json.dumps(observed)
    finally:
        server.shutdown();server.server_close();thread.join(timeout=2)
