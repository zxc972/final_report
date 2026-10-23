"""Evaluate only HTTP meter functions; never load credentials or start uvicorn."""
import ast
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import threading
import time
from urllib.parse import urlsplit
import httpx
import pytest


def fixture(tmp_path):
    source = Path(__file__).parents[1]/"experiments/round19/dev_server.py"
    tree = ast.parse(source.read_text())
    selected = [n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name in {"scrub","save","begin","finish","metered_send"}]
    scope = dict(dt=dt,hashlib=hashlib,json=json,Path=Path,re=re,threading=threading,time=time,provider=urlsplit("https://fixture.invalid/v1"),LOCK=threading.RLock(),ACTIVE_CASE="R19_G1_1",CASES={"R19_G1_1"},BATCH=tmp_path,LEDGER=tmp_path/"http.json",SECRETS=["fixture-only-secret"],protected={},original_send=httpx.Client.send)
    scope["LEDGER"].write_text(json.dumps({"http_attempts":0,"attempts":[],"known_prompt_tokens":0,"known_completion_tokens":0,"unknown_usage_attempts":0}))
    exec(compile(ast.Module(body=selected,type_ignores=[]),str(source),"exec"),scope)
    return scope


def test_http_meter_preserves_response_and_redacts(tmp_path):
    ns=fixture(tmp_path)
    with httpx.Client(transport=httpx.MockTransport(lambda request:httpx.Response(200,json={"model":"fixture-model","choices":[],"usage":{"prompt_tokens":9,"completion_tokens":3}}))) as client:
        request=client.build_request("POST","https://fixture.invalid/v1/chat/completions",json={"model":"fixture","messages":[{"role":"user","content":"fixture-only-secret"}]})
        response=ns["metered_send"](client,request)
        assert response.json()["model"]=="fixture-model"
    ledger=json.loads(ns["LEDGER"].read_text())
    assert ledger["http_attempts"]==1 and ledger["known_prompt_tokens"]==9 and ledger["known_completion_tokens"]==3
    assert ledger["unknown_usage_attempts"]==0
    assert not any("fixture-only-secret" in path.read_text() for path in tmp_path.rglob("*.json"))


def test_http_meter_counts_transport_failure_as_unknown(tmp_path):
    ns=fixture(tmp_path)
    def fail(request):
        raise httpx.ReadTimeout("fixture timeout",request=request)
    with httpx.Client(transport=httpx.MockTransport(fail)) as client:
        request=client.build_request("POST","https://fixture.invalid/v1/chat/completions",json={"model":"fixture","messages":[]})
        with pytest.raises(httpx.ReadTimeout):
            ns["metered_send"](client,request)
    ledger=json.loads(ns["LEDGER"].read_text())
    assert ledger["http_attempts"]==1 and ledger["unknown_usage_attempts"]==1
    assert ledger["attempts"][0]["status"]=="transport_failed"
