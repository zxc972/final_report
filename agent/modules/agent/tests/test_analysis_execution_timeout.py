"""Explicit compute timeouts remain bounded by original total/execution budgets."""
import json,pathlib,time,types
import pytest
from test_analysis_agent import agent,FakeKnowledge

def tools(tmp_path,timeout=False):
 w=tmp_path/'work';w.mkdir();d=tmp_path/'data';d.mkdir();(w/'calculation.py').write_text('print(1)\n');seen=[]
 def run(path,timeout_seconds):
  seen.append(timeout_seconds)
  return {'status':'timeout'if timeout else 'success','exit_code':143 if timeout else 0,'stdout':'','stderr':'','backend':'unit-fixture'}
 e=types.SimpleNamespace(run=run,inspect_runtime=lambda:{'status':'ok','analysis_performed':False})
 return agent.AnalysisTools(w,[d],e,FakeKnowledge()),seen
@pytest.mark.parametrize('requested,expected',[(120,120),(600,600),(1200,900),(3600,900)])
def test_real_requested_timeout_is_not_silently_120(tmp_path,requested,expected):
 t,seen=tools(tmp_path);t.deadline=time.time()+1400;o=t.run_python('/work/calculation.py',requested)
 assert o['status']=='success' and seen==[expected];assert o['execution_limits']['requested_timeout_seconds']==requested and o['execution_limits']['effective_timeout_seconds']==expected
 receipt=next((t.workdir.parent/'.execution_receipts'/t.workdir.name).glob('*.json'));v=json.loads(receipt.read_text());assert v['result']['execution_limits']==o['execution_limits']
def test_default120_and_remaining_total_run_deadline_are_preserved(tmp_path):
 t,seen=tools(tmp_path);o=t.run_python('/work/calculation.py');assert seen==[120]
 t.deadline=time.time()+15;o=t.run_python('/work/calculation.py',900);assert 0<seen[-1]<=15;assert o['execution_limits']['effective_timeout_seconds']<=15
@pytest.mark.parametrize('value',[0,-1,True,1.5,'900',3601])
def test_invalid_timeout_reserves_no_execution(tmp_path,value):
 t,seen=tools(tmp_path);o=t.run_python('/work/calculation.py',value);assert o['status']=='error' and not seen and t.executions==0 and t.tool_calls==1
def test_timeout_feedback_preserves_failed_exit_not_success(tmp_path):
 t,seen=tools(tmp_path,True);o=t.run_python('/work/calculation.py',600)
 assert o['status']=='timeout' and o['exit_code']==143 and o['execution_limits']['effective_timeout_seconds']==600
 assert 'do not change image resolution'in o['runtime_feedback']
def test_runtime_inventory_exposes_budget_and_does_not_run_analysis(tmp_path):
 t,seen=tools(tmp_path);o=t.inspect_analysis_runtime();assert o['execution_policy']['max_script_seconds']==900 and o['execution_policy']['total_run_seconds']==1500 and o['execution_policy']['default_script_seconds']==120;assert not seen and t.executions==0
