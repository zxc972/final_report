"""Transport-level tests: every attempted request remains observable; no network."""
import asyncio,json
import httpx,pytest
from openai import BadRequestError,AuthenticationError,RateLimitError
from modules.agent.backend.analysis_provider import CompatibleChatOpenAI

def success():return {'id':'chatcmpl-fixture','object':'chat.completion','created':0,'model':'fixture','choices':[{'index':0,'message':{'role':'assistant','content':'OK'},'finish_reason':'stop'}],'usage':{'prompt_tokens':2,'completion_tokens':1,'total_tokens':3}}
def error(message,param='thinking',kind='invalid_request_error'):return {'error':{'message':message,'param':param,'type':kind}}
def model(client,**kw):return CompatibleChatOpenAI(model='fixture',base_url='https://fixture.invalid/v1',api_key='test-only-key',http_client=client,max_retries=0,max_tokens=1024,extra_body={'thinking':{'type':'disabled'},'retained_option':7},**kw)
def test_exact_unsupported_field_retries_once_and_preserves_other_options():
 seen=[];events=[]
 def handler(req):
  seen.append(json.loads(req.content))
  return httpx.Response(400,json=error('[unknown_parameter] invalid request body: json: unknown field "thinking"'))if len(seen)==1 else httpx.Response(200,json=success())
 with httpx.Client(transport=httpx.MockTransport(handler),event_hooks={'request':[lambda r:events.append('request')]})as c:
  m=model(c)
  with pytest.warns(RuntimeWarning):a=m.invoke('fixture')
  assert a.content=='OK'and a.response_metadata['provider_compatibility']['retry_in_this_call']is True
  b=m.invoke('another fixture');assert b.response_metadata['provider_compatibility']['retry_in_this_call']is False
 assert len(seen)==3 and len(events)==3
 assert seen[0]['thinking']=={'type':'disabled'}and'thinking'not in seen[1]and'thinking'not in seen[2]
 assert seen[0]['retained_option']==seen[1]['retained_option']==7
 first={k:v for k,v in seen[0].items()if k!='thinking'};assert first==seen[1]
@pytest.mark.parametrize('status,body,cls',[(400,error('context length exceeded','max_tokens'),BadRequestError),(400,error('thinking value invalid'),BadRequestError),(401,error('invalid api key','api_key'),AuthenticationError),(429,error('rate limit','', 'rate_limit_error'),RateLimitError)])
def test_unrelated_failures_never_erase_options_or_silently_replay(status,body,cls):
 seen=[]
 def handler(req):seen.append(json.loads(req.content));return httpx.Response(status,json=body)
 with httpx.Client(transport=httpx.MockTransport(handler))as c:
  m=model(c)
  with pytest.raises(cls):m.invoke('fixture')
  assert m.extra_body['thinking']=={'type':'disabled'}
 assert len(seen)==1
def test_second_unknown_field_failure_is_not_an_unbounded_loop():
 seen=[]
 def handler(req):seen.append(req);return httpx.Response(400,json=error('unknown field "thinking"'))
 with httpx.Client(transport=httpx.MockTransport(handler))as c:
  with pytest.warns(RuntimeWarning),pytest.raises(BadRequestError):model(c).invoke('fixture')
 assert len(seen)==2
def test_async_same_bounded_rule():
 async def run():
  seen=[]
  async def handler(req):
   seen.append(json.loads(req.content));return httpx.Response(400,json=error('unknown field "thinking"'))if len(seen)==1 else httpx.Response(200,json=success())
  async with httpx.AsyncClient(transport=httpx.MockTransport(handler))as c:
   m=CompatibleChatOpenAI(model='fixture',base_url='https://fixture.invalid/v1',api_key='test-only-key',http_async_client=c,max_retries=0,extra_body={'thinking':{'type':'disabled'}})
   with pytest.warns(RuntimeWarning):a=await m.ainvoke('fixture')
   assert a.content=='OK'and len(seen)==2 and'thinking'not in seen[1]
 asyncio.run(run())
