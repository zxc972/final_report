"""Fake actor/reviewer, real ToolNode and Singularity, including reserved revision."""
import importlib,json,os
from pathlib import Path
import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration,ChatResult
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import PrivateAttr
from round14_fixture import fixture,p
from test_analysis_agent import agent
ORIGINAL_PROFILE=p.ensure_profile


@pytest.mark.skipif(os.environ.get('PRIMATEX_RUN_SANDBOX_TESTS')!='1',reason='Explicit synthetic sandbox opt-in required')
@pytest.mark.parametrize('comparison',['group','correlation'])
def test_round24_real_container_review_revision(tmp_path,monkeypatch,comparison):
    tools,intent=fixture(tmp_path,monkeypatch,comparison)
    monkeypatch.setattr(agent,'MAX_MODEL_CALLS',30)
    monkeypatch.setattr(p,'ensure_profile',ORIGINAL_PROFILE)
    executor=importlib.import_module(agent.__package__+'.analysis_executor')
    constraints=importlib.import_module(agent.__package__+'.analysis_constraints')
    from backend.analysis_constraints import software_observation
    from backend.analysis_method_graph import MethodGraph
    monkeypatch.setattr(constraints,'software_observation',software_observation)
    tools._method_graph_store=MethodGraph(Path(__file__).resolve().parents[4]/'knowledge/research_v13')
    tools.executor=executor.SandboxExecutor(tools.workdir,tools.input_roots)
    tools.executor.enable_operations(Path(agent.__file__).with_name('primatex_ops.py'),tools.operations_metadata['sha256'])
    program=Path(__file__).with_name('round23_generated_program.py').read_text()
    revised=program+"\nwith Path('/work/report.md').open('a') as stream:stream.write('\\nSynthetic review revision confirmed.\\n')\n"
    needs_revision=comparison=='correlation';calls=[];seen=[]
    class Model(BaseChatModel):
        _calls:int=PrivateAttr(default=0)
        @property
        def _llm_type(self):return 'offline-round24'
        def bind_tools(self,tools,**kwargs):return self
        def get_num_tokens(self,text):return max(1,len(text)//4)
        def get_num_tokens_from_messages(self,messages,tools=None):return sum(self.get_num_tokens(str(m.content)) for m in messages)
        def _generate(self,messages,**kwargs):
            seen.extend(str(m.content) for m in messages);i=self._calls;self._calls+=1
            if i==0:name,args='plan_analysis',{'intent':intent}
            elif i==1:
                candidate=tools.control_store.latest('planning_result')['record']['candidates'][0]
                name,args='commit_plan',{'candidate_id':candidate['candidate_id'],'rationale':'Synthetic design-preserving selection','code_path':'/work/group.py'}
            elif i==2:name,args='read_file',{'path':'/work/INPUTS.md'}
            elif i==3:name,args='write_code',{'path':'/work/group.py','code':program}
            elif needs_revision and 4<=i<=20:name,args='read_file',{'path':'/work/INPUTS.md'}
            elif (needs_revision and i==21) or (not needs_revision and i==4):name,args='run_python',{}
            elif needs_revision and i==23:
                failures=tools.feedback_journal.recent()['failed_observations'];assert failures
                name,args='record_analysis_reflection',{'observation_id':failures[-1]['id'],
                    'hypothesis':'The synthetic report omitted the requested revision marker.',
                    'next_check':'Amend only the report text, rerun unchanged calculations, and request review.'}
            elif needs_revision and i==24:name,args='write_code',{'path':'/work/group.py','code':revised}
            elif needs_revision and i==25:name,args='run_python',{}
            else:return ChatResult(generations=[ChatGeneration(message=AIMessage(content='Synthetic group description; limited power and unverified physical scale disclosed.'))])
            calls.append(name)
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content='',tool_calls=[{'id':f'r24-{i}','name':name,'args':args}]))])
    class Reviewer:
        def __init__(self):self.calls=0
        def invoke(self,messages):
            self.calls+=1;revise=needs_revision and self.calls==1
            if revise:
                budget=importlib.import_module(agent.__package__+'.analysis_review_budget').get(tools).snapshot()
                assert budget['initial_coding_model_calls']==23
            elif needs_revision:
                assert 'Synthetic review revision confirmed.' in (tools.workdir/'report.md').read_text()
            return AIMessage(content=json.dumps({'decision':'revise' if revise else 'pass',
                'findings':[{'severity':'blocking','claim':'Synthetic requested marker absent',
                             'observation':'report.md has no synthetic revision marker',
                             'evidence_files':['report.md'],'question':'Add the synthetic revision marker and rerun'}] if revise else [],
                'limitations':['Synthetic text consistency only'],
                'hard_block_disclosure':{'complete':True,'undisclosed_constraint_ids':[],
                    'evidence_files':['evidence_card'],'reason':'No undisclosed synthetic prerequisite'}}))
    actor=Model();reviewer=Reviewer()
    coder=agent._build_coding_agent(tools,model='fixture',base_url='https://fixture.invalid/v1',api_key='fixture',model_factory=lambda **kwargs:actor)
    tools._internal_review_model=reviewer
    validator=importlib.import_module(agent.__package__+'.analysis_validation').ArtifactValidator()
    result=agent._build_graph(coder,tools,validator,InMemorySaver()).invoke({'request':'Synthetic eight-subject DKT analysis','history':[],'iterations':0},{'configurable':{'thread_id':'r24-'+comparison}})
    assert result['status']=='completed',{'status':result['status'],'validation':result.get('validation'),'execution':tools.last_execution,'error':result.get('error')}
    assert result['validation']['public_output_contract']['status']=='pass'
    numeric=tools.control_store.latest('independent_numeric')['record'];assert numeric['status']=='pass',numeric
    assert set(numeric['tables'])=={'regional_values.csv','group_results.csv'}
    assert result['validation']['internal_review']['decision']=='pass'
    budget=importlib.import_module(agent.__package__+'.analysis_review_budget').get(tools).snapshot()
    if needs_revision:
        assert reviewer.calls==2 and tools.executions==2
        assert budget['initial_coding_model_calls']==23 and budget['revision_model_calls']==3
        assert budget['review_logical_calls']==2 and tools.model_calls==28
        assert calls[-3:]==['record_analysis_reflection','write_code','run_python']
        assert result['iterations']==2
    else:assert reviewer.calls==1 and tools.executions==1
    assert budget['budget_units_used']<=30
    assert not any('independent_numeric_private' in text or 'reference_source_sha256' in text for text in seen)
    bundle=tools.control_store.latest('execution_bundle')['record'];sealed=tools.control_store.latest('plan')
    card=importlib.import_module(agent.__package__+'.analysis_execution_card').execution_card({'plan':sealed['record']['plan'],'version':sealed['version'],'execution_bundle':bundle})['execution_card']
    assert len(card)<=1500 and 'effect_size_kind' in card
    (tools.workdir/'offline_acceptance_round24.json').write_text(json.dumps({'comparison':comparison,'completed':True,'review_calls':reviewer.calls,'executions':tools.executions,'review_budget':budget,'tables':numeric['tables'],'execution_card_length':len(card),'real_provider_requests':0,'review_revision_exercised':needs_revision}))
