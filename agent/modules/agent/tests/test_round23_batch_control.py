"""Stop rules never relaunch a case or exceed the user's per-question cap."""
import importlib.util
from pathlib import Path
import pytest
p=Path(__file__).resolve().parents[3]/'experiments/round23/round23_control.py'
spec=importlib.util.spec_from_file_location('round23_stop_rules',p);control=importlib.util.module_from_spec(spec);spec.loader.exec_module(control)

def rows(categories):return [{'case':'R23_G1_'+str(i+1),'failure_classification':{'category':c,'stop_eligible':c not in [None,'upstream_transport_error']}} for i,c in enumerate(categories)]

@pytest.mark.parametrize('categories,stop,reason',[
 (['system_defect'],False,'continue'),
 (['system_defect','contract_failed','system_defect'],True,'same_question_two_system_defects'),
 (['contract_failed','contract_failed'],True,'consecutive_same_question_failure_chain'),
 (['contract_failed',None,'contract_failed'],True,'three_run_limit'),
 (['contract_failed',None],False,'continue'),
 (['upstream_transport_error','upstream_transport_error'],False,'continue')])
def test_round23_stop_decision(categories,stop,reason):
 result=control.decision(rows(categories));assert result['stop']==stop and result['reason']==reason
