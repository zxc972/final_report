"""Runtime discovery boundary tests, not scientific analysis tests."""
import pathlib,sys,json,types,time
import pytest
from test_analysis_executor import SandboxExecutor,PROBE_MARKER,GOOD_CHECKS
from test_analysis_agent import agent,FakeKnowledge
MARKER='PRIMATEX_RUNTIME_INVENTORY='
def make(tmp_path,runner):
 data=tmp_path/'data';data.mkdir();(data/'private_study.txt').write_text('must not mount for inventory')
 env=tmp_path/'runtime';(env/'bin').mkdir(parents=True);(env/'bin/python').write_text('fixture')
 image=tmp_path/'image.sif';image.write_text('fixture')
 return SandboxExecutor(tmp_path/'work',[data],runtime_image=image,runtime_env=env,apptainer_binary=sys.executable,platform_name='linux',command_runner=runner)
def test_inventory_is_confined_without_real_study_mounts_and_not_a_computation(tmp_path):
 calls=[]
 def runner(cmd,**kw):
  calls.append((cmd,kw))
  if any(PROBE_MARKER in x for x in cmd):return {'exit_code':0,'stdout':PROBE_MARKER+json.dumps(GOOD_CHECKS),'stderr':''}
  return {'exit_code':0,'stdout':MARKER+json.dumps({'schema_version':1,'commands':{'fast':{'executed':False}}}),'stderr':''}
 e=make(tmp_path,runner);o=e.inspect_runtime();assert o['status']=='ok' and not o['analysis_performed'] and not o['command_execution_verified']
 assert not o['study_inputs_mounted_for_inventory'];cmd,kw=calls[-1]
 assert not any(str(e.input_roots[0])in x for x in cmd);assert not any('/inputs/'in x for x in cmd)
 assert '--containall'in cmd and '--net'in cmd and 'none'in cmd and '--cleanenv'in cmd
 assert kw['timeout_seconds']==30;assert set(kw['env'])=={'PATH','LANG','HOME'}
 assert not list(e.workdir.glob('.runtime-inventory-*'))
def test_isolation_failure_never_runs_inventory(tmp_path):
 calls=[]
 def runner(cmd,**kw):calls.append(cmd);return {'exit_code':1,'stdout':'','stderr':'namespace denied'}
 o=make(tmp_path,runner).inspect_runtime();assert o['status']=='blocked';assert len(calls)==1
@pytest.mark.parametrize('response',[{},[],{'schema_version':2},'bad json'])
def test_malformed_inventory_cannot_claim_ready(tmp_path,response):
 def runner(cmd,**kw):
  if any(PROBE_MARKER in x for x in cmd):return {'exit_code':0,'stdout':PROBE_MARKER+json.dumps(GOOD_CHECKS),'stderr':''}
  return {'exit_code':0,'stdout':MARKER+(response if isinstance(response,str)else json.dumps(response)),'stderr':''}
 assert make(tmp_path,runner).inspect_runtime()['status']=='error'
def test_inventory_respects_tool_budget_without_execution_or_manifest_mutation(tmp_path):
 work=tmp_path/'work';work.mkdir();data=tmp_path/'data';data.mkdir();p=work/'analysis_manifest.json';p.write_text('previous-finalization')
 ex=types.SimpleNamespace(inspect_runtime=lambda:{'status':'ok','analysis_performed':False})
 t=agent.AnalysisTools(work,[data],ex,FakeKnowledge());before=t.executions;o=t.inspect_analysis_runtime()
 assert o['status']=='ok';assert t.tool_calls==1 and t.executions==before and t.last_execution=={};assert p.read_text()=='previous-finalization'
 t.deadline=time.time()-1;assert t.inspect_analysis_runtime()['status']=='error';assert t.tool_calls==1
