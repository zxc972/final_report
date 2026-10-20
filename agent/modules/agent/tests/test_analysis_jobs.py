"""Offline job/Agent/API contract tests; fixtures are not real analysis trials."""
import hashlib,importlib,json,os,pathlib,subprocess,sys,time,types
from unittest.mock import patch
import pytest
from test_analysis_agent import agent,FakeKnowledge,TestOnlyExecutor as FixtureOnlyExecutor
jobs=importlib.import_module(agent.__package__+'.analysis_jobs')
def setup(tmp_path,code=None):
 w=tmp_path/'work';w.mkdir();d=tmp_path/'data';d.mkdir();(d/'values.txt').write_text('2\n3\n')
 (w/'calc.py').write_text(code or "import json\nfrom pathlib import Path\nPath('summary.json').write_text(json.dumps({'value':5,'scope':'unit fixture'}))\n")
 count=[];spec=[{'path':'summary.json','kind':'json','required_keys':['value','scope']}]
 def submit(**kw):
  return jobs.submit(w,[d],w/'calc.py',kw.pop('timeout',180),kw.pop('spec',spec),kw.pop('required',['summary.json']),lambda:count.append(1),launcher=kw.pop('launcher',lambda p:os.getpid()),**kw)
 return w,d,count,spec,submit
class FixtureExecutor:
 calls=[]
 def __init__(self,w,roots):self.w=w
 def run(self,script,timeout_seconds,frozen_source):
  assert frozen_source.read_bytes()==script.read_bytes()
  self.calls.append(timeout_seconds)
  p=subprocess.run([sys.executable,str(script)],cwd=self.w,capture_output=True,text=True,timeout=5)
  return {'status':'success'if p.returncode==0 else'failed','exit_code':p.returncode,'stdout':p.stdout,'stderr':p.stderr,'backend':'unit-fixture-not-namespace'}
@pytest.fixture(autouse=True)
def enable(monkeypatch):monkeypatch.setenv('ANALYSIS_ENABLE_BACKGROUND_JOBS','1')
def directory(w,r):return jobs._job_root(w)/r['job_id']
def execute(w,r,cls=FixtureExecutor):return jobs.worker(directory(w,r),executor_factory=cls)
def test_disabled_reserves_nothing(tmp_path,monkeypatch):
 w,d,count,spec,submit=setup(tmp_path);monkeypatch.delenv('ANALYSIS_ENABLE_BACKGROUND_JOBS')
 with pytest.raises(ValueError,match='not enabled'):submit()
 assert not count and not(w/'job_outputs').exists()
@pytest.mark.parametrize('arg',[0,-1,True,1.2,'180',jobs.MAX_JOB_SECONDS+1])
def test_invalid_timeout_reserves_nothing(tmp_path,arg):
 w,d,count,spec,submit=setup(tmp_path)
 with pytest.raises(ValueError):submit(timeout=arg)
 assert not count
@pytest.mark.parametrize('spec',[
 [],[{'path':'../x','kind':'json'}],[{'path':'.env','kind':'json'}],
 [{'path':'x','kind':'invented'}],[{'path':'summary.json','kind':'json','made_up':1}],
 [{'path':'summary.json','kind':'json'},{'path':'summary.json','kind':'json'}],
 [{'path':'calc.py','kind':'json'}]])
def test_bad_artifact_contract_reserves_nothing(tmp_path,spec):
 w,d,count,base,submit=setup(tmp_path)
 with pytest.raises(ValueError):submit(spec=spec)
 assert not count
def test_required_coverage_cannot_be_weakened(tmp_path):
 w,d,count,spec,submit=setup(tmp_path)
 with pytest.raises(ValueError,match='caller-required'):submit(required=['summary.json','report.md'])
 assert not count
def test_submit_not_completed_replay_idempotent_then_real_fixture_completion(tmp_path):
 w,d,count,spec,submit=setup(tmp_path);r=submit()
 assert r['status']=='queued' and not r['computed'] and r['provider_requests_in_worker']==0
 assert submit()['job_id']==r['job_id'] and len(count)==1
 state=execute(w,r)
 assert state['status']=='completed' and state['validation']['valid'],state
 public=jobs.status(w,r['job_id'])
 assert public['artifacts'][0]['path'].startswith('job_outputs/'+r['job_id']+'/')
 assert public['validation']['independent_numeric_status']=='not_performed' and public['validation']['scientific_status']=='not_evaluated'
 assert public['source_matches_executed_code'] and submit()['reused'] and len(count)==1
 assert execute(w,r)['finished']==state['finished']
def test_stale_declared_outputs_are_never_inherited(tmp_path):
 w,d,count,spec,submit=setup(tmp_path,'pass\n');(w/'summary.json').write_text('{"value":5,"scope":"old"}');(w/'analysis_manifest.json').write_text('{}')
 r=submit();out=w/r['output_relative']
 assert not(out/'summary.json').exists()and not(out/'analysis_manifest.json').exists()
 state=execute(w,r);assert state['status']=='failed' and not(out/'summary.json').exists()
def test_changed_staging_prevents_signature_reuse_or_second_active_job(tmp_path):
 w,d,count,spec,submit=setup(tmp_path);(w/'intermediate.txt').write_text('one');r=submit();(w/'intermediate.txt').write_text('two')
 with pytest.raises(ValueError,match='active or unaccounted'):submit()
 assert len(count)==1
def test_preparation_failure_is_recorded_and_does_not_poison_future_scan(tmp_path):
 w,d,count,spec,submit=setup(tmp_path)
 with patch.object(jobs.shutil,'copyfile',side_effect=OSError('fixture copy failure')):r=submit()
 assert r['status']=='failed' and(directory(w,r)/'job.json').exists()
 assert submit()['job_id']==r['job_id'] and len(count)==1
 (w/'calc.py').write_text((w/'calc.py').read_text()+'# new program\n')
 assert submit()['job_id']!=r['job_id'] and len(count)==2
def test_launch_failure_replay_does_not_restart(tmp_path):
 w,d,count,spec,submit=setup(tmp_path)
 def failed(p):raise OSError('fixture launch failure')
 r=submit(launcher=failed);assert r['status']=='failed';assert submit()['reused']and len(count)==1
@pytest.mark.parametrize('target',['input','frozen','staged'])
def test_changed_preexecution_source_or_input_blocks_computation(tmp_path,target):
 w,d,count,spec,submit=setup(tmp_path);r=submit();private=directory(w,r)
 if target=='input':(d/'values.txt').write_text('changed')
 elif target=='frozen':(private/'source.py').chmod(0o600);(private/'source.py').write_text('pass\n')
 else:(w/r['output_relative']/'calc.py').write_text('pass\n')
 assert execute(w,r)['status']=='failed'
 assert not(private/'execution_receipt.json').exists()
@pytest.mark.parametrize('target',['summary.json','analysis_manifest.json','calc.py','private_receipt'])
def test_mutated_completed_artifacts_or_receipts_never_stay_success(tmp_path,target):
 w,d,count,spec,submit=setup(tmp_path);r=submit();assert execute(w,r)['status']=='completed'
 p=directory(w,r)/'execution_receipt.json'if target=='private_receipt'else w/r['output_relative']/target;p.write_text('{}')
 current=jobs.status(w,r['job_id'])
 assert current['status']=='output_integrity_failed' and not current['validation']['valid']
def test_failed_exit_never_finalized_even_if_output_exists(tmp_path):
 w,d,count,spec,submit=setup(tmp_path)
 class Failed(FixtureExecutor):
  def run(self,*a,**kw):super().run(*a,**kw);return {'status':'failed','exit_code':1,'stdout':'','stderr':'fixture'}
 r=submit();state=execute(w,r,Failed)
 assert state['status']=='failed'and not(directory(w,r)/'artifact_receipt.json').exists()
def test_input_changed_during_computation_is_detected(tmp_path):
 w,d,count,spec,submit=setup(tmp_path)
 class Changing(FixtureExecutor):
  def run(self,*a,**kw):
   result=super().run(*a,**kw);(d/'values.txt').write_text('mutated');return result
 r=submit();assert execute(w,r,Changing)['status']=='failed'
def test_dead_or_recycled_worker_is_unknown_and_blocks_new_jobs(tmp_path):
 w,d,count,spec,submit=setup(tmp_path);r=submit();private=directory(w,r)
 meta=jobs._read(private/'job.json',private);meta['created']-=60;jobs._write(private/'job.json',private,meta)
 jobs._write(private/'launch.json',private,{'pid':os.getpid(),'start_ticks':'invalid-old-start'})
 assert jobs.status(w,r['job_id'])['status']=='unknown_after_worker_exit'
 (w/'calc.py').write_text('pass\n')
 with pytest.raises(ValueError,match='unaccounted'):submit()
 assert len(count)==1
def test_cancel_is_owner_job_specific_and_prevents_queued_execution(tmp_path):
 w,d,count,spec,submit=setup(tmp_path);r=submit()
 with patch.object(jobs.os,'kill')as kill:
  assert jobs.cancel(w,r['job_id'])['cancel_requested'];kill.assert_called_once_with(os.getpid(),jobs.signal.SIGTERM)
 assert execute(w,r)['status']=='cancelled'
 with patch.object(jobs.os,'kill')as kill:assert jobs.cancel(w,r['job_id'])['status']=='cancelled';kill.assert_not_called()
def test_cancel_never_signals_a_recycled_pid(tmp_path):
 w,d,count,spec,submit=setup(tmp_path);r=submit();private=directory(w,r)
 jobs._write(private/'launch.json',private,{'pid':os.getpid(),'start_ticks':'old'})
 with patch.object(jobs.os,'kill')as kill:jobs.cancel(w,r['job_id']);kill.assert_not_called()
def test_frozen_source_cannot_be_symlinked(tmp_path):
 w,d,count,spec,submit=setup(tmp_path);r=submit();p=directory(w,r)/'source.py';p.unlink();p.symlink_to(w/'calc.py')
 assert execute(w,r)['status']=='failed'
def test_agent_tool_reserves_one_execution_and_blocks_competing_writes(tmp_path):
 w,d,count,spec,submit=setup(tmp_path);tools=agent.AnalysisTools(w,[d],FixtureOnlyExecutor(w,[d]),FakeKnowledge());tools.required_artifacts=['summary.json']
 with patch.object(jobs,'_launch',lambda p:os.getpid()):
  r=tools.submit_python_job('/work/calc.py',spec,180)
  r2=tools.submit_python_job('/work/calc.py',spec,180)
 assert tools.executions==1 and r2['reused']and r['job_id']==r2['job_id']
 assert tools.write_code('/work/another.py','pass\n')['status']=='error'
 assert tools.run_python('/work/calc.py')['status']=='error'
def test_real_deep_agent_return_direct_checkpoints_submitted_not_completed(tmp_path,monkeypatch):
 from langchain_core.language_models.chat_models import BaseChatModel
 from langchain_core.messages import AIMessage
 from langchain_core.outputs import ChatGeneration,ChatResult
 from pydantic import PrivateAttr
 w,d,count,spec,submit=setup(tmp_path);monkeypatch.setenv('AGENT_ANALYSIS_STATE_DIR',str(tmp_path/'protected-state'))
 class Model(BaseChatModel):
  _calls:int=PrivateAttr(default=0)
  @property
  def _llm_type(self):return 'offline-job-fixture'
  def bind_tools(self,tools,**kwargs):return self
  def get_num_tokens(self,text):return max(1,len(text)//4)
  def get_num_tokens_from_messages(self,messages,tools=None):return sum(self.get_num_tokens(str(m.content))for m in messages)
  def _generate(self,messages,**kwargs):
   sequence=[('write_code',{'path':'/work/calc.py','code':(w/'calc.py').read_text()}),('submit_python_job',{'path':'/work/calc.py','artifacts':spec,'timeout_seconds':180})]
   index=self._calls;self._calls+=1;assert index<2,'return_direct must not call another model after submission'
   name,args=sequence[index]
   return ChatResult(generations=[ChatGeneration(message=AIMessage(content='',tool_calls=[{'name':name,'args':args,'id':f'job-{index}','type':'tool_call'}]))])
 model=Model();knowledge=importlib.import_module(agent.__package__+'.analysis_knowledge');executor=importlib.import_module(agent.__package__+'.analysis_executor')
 with patch.object(jobs,'_launch',lambda p:os.getpid()),patch.object(knowledge,'KnowledgeStore',FakeKnowledge),patch.object(executor,'SandboxExecutor',FixtureOnlyExecutor):
  result=agent._run_sync(message='Unit job',user_id='alice',workspace=w,conversation_id='job-fixture',model='offline',base_url='https://example.invalid/v1',api_key='fixture-no-secret',resume=False,input_roots=[d],model_factory=lambda**kw:model,required_artifacts=['summary.json'])
 assert result['status']=='submitted'and not result['validation']['valid']and result['executions']==1 and len(result['analysis_jobs'])==1
 assert model._calls==2 and not result['artifacts']