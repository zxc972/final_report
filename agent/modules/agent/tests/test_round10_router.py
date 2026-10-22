"""New router recovery, retry and no-dispatch regression cases."""
import pytest
from test_agent_router import invoke, response, session
from modules.agent.backend.agent_router import parse_route


@pytest.mark.parametrize("content,warnings", [
    ('{"route":"analysis","reason":"Measure."}."}', ["trailing_text"]),
    ('Some prose {"route":"analysis","reason":"Measure."}', ["leading_text"]),
    ('```json\n{"route":"analysis","reason":"Measure."}\n```', ["leading_text", "trailing_text"]),
])
def test_first_complete_object(content, warnings):
    obj=response()
    obj["choices"][0]["message"]["content"]=content
    result=parse_route(obj)
    assert result["route"]=="analysis" and result["warnings"]==warnings


@pytest.mark.parametrize("bad", ['plain prose', '{"route":"shell","reason":"Measure."}'])
def test_retry_and_total_failure(bad,tmp_path,monkeypatch):
    s=session(tmp_path,monkeypatch)
    calls=[]
    async def model(*args,**kwargs):
        calls.append(args)
        obj=response()
        if len(calls)==1:
            obj["choices"][0]["message"]["content"]=bad
        return obj
    result=invoke(model,s.budget)
    assert result["parse_status"]=="retry_success" and result["model_calls"]==2
    assert "Previous routing attempt failed" in calls[1][3][-1]["content"]
    assert s.budget.view()["model_calls"]==2


def test_unsupported_response_format_uses_second_bounded_attempt(tmp_path,monkeypatch):
    from fastapi import HTTPException
    s=session(tmp_path,monkeypatch)
    seen=[]
    async def model(*args,**kwargs):
        seen.append(kwargs)
        if len(seen)==1:
            raise HTTPException(502,"response_format is unsupported")
        obj=response()
        obj["choices"][0]["message"]["content"]='Prose '+obj["choices"][0]["message"]["content"]+' trailing'
        return obj
    value=invoke(model,s.budget)
    assert value["route"]=="analysis" and not value["json_constraint"]
    assert "response_format" not in seen[1]
    assert s.budget.view()["unknown_usage_calls"]==1
