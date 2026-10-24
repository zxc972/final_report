"""Real ToolNode feedback and separate argument/planner budgets, with zero HTTP."""
import importlib
import json
import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import PrivateAttr
from test_analysis_agent import agent
from test_analysis_product_planner import setup_products, p
from test_round8_closure import sealed

feedback = importlib.import_module(agent.__package__ + '.analysis_feedback')
numeric = importlib.import_module(agent.__package__ + '.analysis_independent_numeric')
overall = importlib.import_module(agent.__package__ + '.analysis_overall_status')


class Scripted(BaseChatModel):
    _index: int = PrivateAttr(default=0)
    _step: object = PrivateAttr()
    def __init__(self, step):
        super().__init__();self._step=step
    @property
    def _llm_type(self):return 'offline-round21'
    def bind_tools(self,tools,**kwargs):return self
    def get_num_tokens(self,text):return max(1,len(text)//4)
    def get_num_tokens_from_messages(self,messages,tools=None):return sum(self.get_num_tokens(str(m.content)) for m in messages)
    def _generate(self,messages,**kwargs):
        result=self._step(self._index,messages);self._index+=1
        message=AIMessage(content='Offline fixture finished.') if result is None else AIMessage(content='',tool_calls=[{'id':'round21-'+str(self._index),'name':result[0],'args':result[1]}])
        return ChatResult(generations=[ChatGeneration(message=message)])


def coding(tools, step):
    return agent._build_coding_agent(tools,model='fixture',base_url='https://fixture.invalid/v1',api_key='fixture',model_factory=lambda **kw:Scripted(step))


def test_real_toolnode_exit_zero_missing_artifact_is_failed_and_reflection_accepted(tmp_path,monkeypatch):
    tools,_,_=sealed(tmp_path,monkeypatch)
    tools.write_code('/work/analysis.py','# synthetic process intentionally produces no artifacts')
    class EmptyExecutor:
        def run(self,*args,**kwargs):return {'status':'success','exit_code':0,'stdout':'synthetic exit0','stderr':''}
    tools.executor=EmptyExecutor()
    seen=[]
    def step(index,messages):
        if index==0:return 'run_python',{}
        last=next(m for m in reversed(messages) if isinstance(m,ToolMessage));payload=json.loads(last.content);seen.append(payload)
        if index==1:
            assert last.status=='error'
            observation=tools.feedback_journal._read(payload['feedback_observation_id'])
            assert observation['failed'] is True
            assert 'summary.csv' in json.dumps(observation['failure_details'])
            assert observation['result']['exit_code']==0
            return 'record_analysis_reflection',{'observation_id':observation['id'],'hypothesis':'The zero-exit script did not create every declared output.','next_check':'Read the sealed output contract and verify the missing file paths.'}
        assert payload['status']=='ok' and payload['verification_status']=='hypothesis_only_not_yet_verified'
    coding(tools,step).invoke({'messages':[{'role':'user','content':'Exercise missing synthetic artifacts and record a failure hypothesis.'}]})
    assert tools.session.state()['phase']=='executed_failed'
    assert tools.feedback_journal.recent()['total_reflections']==1


@pytest.mark.parametrize('value',[{'status':'success','exit_code':0,'public_output_contract':{'status':'fail','files':[{'path':'result.csv','errors':['missing key']}]}},{'status':'finalized','validation':{'valid':False,'errors':['contract mismatch']}}])
def test_nested_contract_failures_retain_actual_reasons(value,tmp_path):
    work=tmp_path/'work';work.mkdir();journal=feedback.FeedbackJournal(work)
    record=journal.observe('run_python',{},value)
    assert record['failed'] and record['failure_details']
    assert 'expected_values' not in json.dumps(record)


def test_success_diagnostic_in_failed_phase_is_not_itself_a_failure(tmp_path):
    work=tmp_path/'work';work.mkdir();journal=feedback.FeedbackJournal(work)
    record=journal.observe('read_file',{}, {'status':'ok','state':{'phase':'executed_failed'}})
    assert record['failed'] is False


def test_real_toolnode_argument_errors_do_not_spend_three_planner_entries(tmp_path,monkeypatch):
    monkeypatch.setattr(agent,'MAX_MODEL_CALLS',30)
    tools=setup_products(tmp_path,monkeypatch)
    tools.control_store.save('data_card',{'subjects':[{'subject':'sample-A','metrics':['curv']},{'subject':'sample-B','metrics':['curv']}]})
    calls=[];observations=[]
    def planner(actual,intent):
        calls.append(intent)
        result={'status':'infeasible','candidates':[],'infeasible':[{'reason':'synthetic no viable candidate'}]}
        actual.control_store.save('planning_result',result);return result
    monkeypatch.setattr(p,'plan_analysis',planner)
    valid={'subjects':'全部已登记被试','measures':['curv'],'comparison':'correlation','design':{'effect':'exposure','covariates':[]}}
    bad0={**valid,'subjects':['sample-A','sample-A','invented'],'measures':['unregistered_metric']}
    bad1={k:v for k,v in valid.items() if k!='design'}
    bad2={**valid,'measures':[],'design':{'covariates':[]}}
    requests=[bad0,bad1,bad2,valid,valid,valid,valid]
    def step(index,messages):
        if index:
            observations.append(json.loads(next(m.content for m in reversed(messages) if isinstance(m,ToolMessage))))
        if index<len(requests):return 'plan_analysis',{'intent':requests[index]}
    coding(tools,step).invoke({'messages':[{'role':'user','content':'Exercise generic synthetic planning arguments without executing.'}]})
    assert len(calls)==3 and tools.session.record['planning_attempts']==3
    assert tools.session.record['planning_argument_errors']==3
    assert all(c.subjects==['sample-A','sample-B'] for c in calls)
    assert observations[0]['available_measures']==['curv']
    assert observations[0]['duplicate_subjects']==['sample-A'] and observations[0]['unknown_subjects']==['invented']
    assert observations[1]['field_errors'][0]['field']=='design.effect'
    assert observations[2]['argument_validation_failed']
    assert tools.tool_calls==7 and tools.executions==0


def test_unassessed_new_record_has_null_differences_even_if_public_contract_checked(tmp_path,monkeypatch):
    tools=setup_products(tmp_path,monkeypatch)
    value=numeric.current_summary(tools)
    assert value['assessment_status']=='not_assessed'
    assert value['identity_mismatch_count'] is value['numeric_mismatch_count'] is None
    card=overall.finalize_card({'verdict':'deferred'},{'public_output_contract':{'status':'pass','identity_mismatch_count':0},'independent_numeric':value},'failed',{})
    states=card['component_statuses']
    assert states['independent_numeric']=='not_assessed'
    assert states['identity_mismatch_count'] is states['numeric_mismatch_count'] is None
    assert states['public_identity_mismatch_count']==0
