"""Actual installed OpenAI SDK -> local HTTP server; no provider or mocked transport."""
import asyncio
import importlib
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
from types import SimpleNamespace
import pytest
from openai import OpenAI, AsyncOpenAI, RateLimitError
from backend.analysis_http_observer import HTTPObserver, current_native_charge
from backend.analysis_call_context import HTTP_ATTEMPT
from backend.agent_chat_state import ACTIVE_CHAT, RequestBudget


@pytest.mark.parametrize('asynchronous,status',[(False,200),(True,200),(False,429)])
@pytest.mark.parametrize('activate_chat',[False,True])
def test_real_sdk_httpx2_send_matches_native_charge_id_and_usage(monkeypatch,asynchronous,status,activate_chat):
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
        assert ACTIVE_CHAT.get() is (session if activate_chat else None)
        attempt=HTTP_ATTEMPT.get();record=current_native_charge()
        assert record['id']==attempt
        return {'native_attempt_id':attempt,'logical_id':record['logical_id']}
    def finish(ticket,response=None,error=None):
        assert ticket is not None
        ticket.update(http_status=response.status_code if response is not None else None,usage=response.json().get('usage') if response is not None else None,error_type=type(error).__name__ if error else None);observed.append(ticket)
    url='http://127.0.0.1:'+str(server.server_port)+'/v1'
    async def execute():
        token=ACTIVE_CHAT.set(session if activate_chat else None);attempt=session.budget.reserve('router')
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


@pytest.mark.parametrize("transport", ["backend_httpx", "sdk_httpx2"])
def test_auto_router_before_chat_activation_and_concurrent_requests(monkeypatch, transport):
    """Real router reserves before API activates ACTIVE_CHAT; two turns stay distinct."""
    from backend.agent_router import route_message
    from backend.llm import call_chat_completions
    from backend.analysis_call_context import HTTP_BUDGET

    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    received, observed = [], []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            received.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            route = {"route": "analysis", "task_kind": "analysis_compute", "reason": "Analyse registered fixture outputs"}
            payload = {"id": "local-route", "model": "local-fixture", "choices": [{"index": 0, "message": {"role": "assistant", "content": json.dumps(route)}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 13, "completion_tokens": 7, "total_tokens": 20}}
            raw = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=.01), daemon=True)
    thread.start()

    class Store:
        def save(self, *args):
            pass

    sessions = [SimpleNamespace(request_id=f"offline-auto-{i}", store=Store(), analysis_tools=None) for i in range(2)]
    for session in sessions:
        session.budget = RequestBudget(session, 30)

    def begin(request):
        assert request.url.host == "127.0.0.1"
        assert ACTIVE_CHAT.get() is None
        record = current_native_charge()
        return {"native_attempt_id": record["id"], "request_id": record["request_id"], "source_node": record["source_node"]}

    def finish(ticket, response=None, error=None):
        assert error is None
        ticket["status_code"] = response.status_code
        ticket["usage"] = response.json()["usage"]
        observed.append(ticket)

    async def sdk_caller(base_url, api_key, model, messages, tools, **options):
        assert not tools
        async with AsyncOpenAI(base_url=base_url, api_key=api_key, max_retries=0, timeout=5) as client:
            return (await client.chat.completions.create(model=model, messages=messages, **options)).model_dump()

    async def route(session):
        assert ACTIVE_CHAT.get() is None
        result = await route_message(message="Analyse the registered fixture", history=[], recent_upload=None, previous_route=None, base_url=f"http://127.0.0.1:{server.server_port}/v1", api_key="fake-local-only", model="local-fixture", caller=call_chat_completions if transport == "backend_httpx" else sdk_caller, budget=session.budget)
        assert result["route"] == "analysis" and result["parse_status"] == "first_success"
        assert HTTP_ATTEMPT.get() is None and HTTP_BUDGET.get() is None
        return result

    async def execute():
        token = ACTIVE_CHAT.set(None)
        try:
            return await asyncio.gather(*(route(s) for s in sessions))
        finally:
            ACTIVE_CHAT.reset(token)

    try:
        with HTTPObserver(begin, finish):
            results = asyncio.run(execute())
        assert len(received) == len(observed) == len(results) == 2
        charges = {s.request_id: s.budget.records[0] for s in sessions}
        assert all(len(s.budget.records) == 1 for s in sessions)
        for item in observed:
            charge = charges[item["request_id"]]
            assert item["native_attempt_id"] == charge["id"]
            assert item["source_node"] == "router"
            assert item["usage"] == charge["usage"]
            assert item["status_code"] == 200
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.parametrize("invalid", ["missing_budget", "wrong_id", "finished"])
def test_native_binding_rejects_missing_stale_or_different_reservation(invalid):
    from backend.analysis_call_context import HTTP_BUDGET

    record = {"id": "bound-id", "status": "response_received" if invalid == "finished" else "started"}
    owner = None if invalid == "missing_budget" else SimpleNamespace(records=[record])
    budget_token = HTTP_BUDGET.set(owner)
    attempt_token = HTTP_ATTEMPT.set("different-id" if invalid == "wrong_id" else "bound-id")
    try:
        with pytest.raises(RuntimeError, match="Exact native HTTP charge binding unavailable"):
            current_native_charge()
    finally:
        HTTP_ATTEMPT.reset(attempt_token)
        HTTP_BUDGET.reset(budget_token)
