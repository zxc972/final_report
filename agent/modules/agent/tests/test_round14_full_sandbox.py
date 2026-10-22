"""Fake model, real isolation/runtime and automatic finalization; no provider HTTP."""
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
def test_group_full_real_container(tmp_path,monkeypatch,comparison):
    tools,intent=fixture(tmp_path,monkeypatch,comparison)
    if comparison == 'correlation':
        original = tools.input_roots[0]/'surf/lh.white'
        target = original.with_name('lh.white.T1')
        original.rename(target);original.symlink_to(target)
    monkeypatch.setattr(p,'ensure_profile',ORIGINAL_PROFILE)
    executor=importlib.import_module(agent.__package__+'.analysis_executor')
    constraints=importlib.import_module(agent.__package__+'.analysis_constraints')
    # Restore the actual fixed container software probe, not the fixture's stub.
    from backend.analysis_constraints import software_observation
    monkeypatch.setattr(constraints,'software_observation',software_observation)
    from backend.analysis_method_graph import MethodGraph
    tools._method_graph_store=MethodGraph(Path(__file__).resolve().parents[4]/'knowledge/research_v13')
    tools.executor=executor.SandboxExecutor(tools.workdir,tools.input_roots)
    tools.executor.enable_operations(Path(agent.__file__).with_name('primatex_ops.py'),tools.operations_metadata['sha256'])
    program=Path(__file__).with_name('round14_generated_program.py').read_text()
    calls=[];messages_seen=[]
    class Model(BaseChatModel):
        _calls:int=PrivateAttr(default=0)
        @property
        def _llm_type(self):return 'offline-round14-group'
        def bind_tools(self,tools,**kwargs):return self
        def get_num_tokens(self,text):return max(1,len(text)//4)
        def get_num_tokens_from_messages(self,messages,tools=None):return sum(self.get_num_tokens(str(m.content)) for m in messages)
        def _generate(self,messages,**kwargs):
            messages_seen.extend(str(m.content) for m in messages);index=self._calls;self._calls+=1
            if index==0:name,args='plan_analysis',{'intent':intent}
            elif index==1:
                result=tools.control_store.latest('planning_result')['record'];assert result['candidates'],result
                name,args='commit_plan',{'candidate_id':result['candidates'][0]['candidate_id'],'rationale':'Synthetic DKT group analysis with explicit design','code_path':'/work/group.py'}
            elif index==2:name,args='write_code',{'path':'/work/group.py','code':program}
            elif index==3:name,args='run_python',{}
            else:return ChatResult(generations=[ChatGeneration(message=AIMessage(content='Synthetic group estimate only; FDR over both hemispheres, low power and unverified physical scale disclosed.'))])
            calls.append(name);return ChatResult(generations=[ChatGeneration(message=AIMessage(content='',tool_calls=[{'id':f'r14-{index}','name':name,'args':args}]))])
    class Reviewer:
        def invoke(self,messages):return AIMessage(content=json.dumps({'decision':'pass','findings':[],'limitations':['Synthetic text consistency only'],'hard_block_disclosure':{'complete':True,'undisclosed_constraint_ids':[],'evidence_files':['evidence_card'],'reason':'All hard prerequisites observed for synthetic data'}}))
    coder=agent._build_coding_agent(tools,model='fixture',base_url='https://fixture.invalid/v1',api_key='fixture',model_factory=lambda **kwargs:Model())
    tools._internal_review_model=Reviewer()
    validator=importlib.import_module(agent.__package__+'.analysis_validation').ArtifactValidator()
    result=agent._build_graph(coder,tools,validator,InMemorySaver()).invoke({'request':'Synthetic eight-subject DKT analysis','history':[],'iterations':0},{'configurable':{'thread_id':'r14-'+comparison}})
    assert result['status']=='completed',{'status':result['status'],'validation':result.get('validation'),'execution':tools.last_execution,'errors':result.get('error')}
    assert result['validation']['public_output_contract']['status']=='pass'
    numeric=tools.control_store.latest('independent_numeric')['record'];assert numeric['status']=='pass',numeric
    assert set(numeric['tables'])=={'regional_values.csv','group_results.csv'}
    assert result['validation']['internal_review']['decision']=='pass'
    assert calls==['plan_analysis','commit_plan','write_code','run_python']
    assert not any('independent_numeric_private' in s or 'reference_source_sha256' in s for s in messages_seen)
    card=importlib.import_module(agent.__package__+'.analysis_execution_card').execution_card
    # Keep only synthetic public acceptance evidence in the run directory.
    sealed=tools.control_store.latest('plan');bundle=tools.control_store.latest('execution_bundle')['record']
    text=card({'plan':sealed['record']['plan'],'version':sealed['version'],'execution_bundle':bundle})['execution_card']
    assert len(text)<=1500
    (tools.workdir/'offline_acceptance.json').write_text(json.dumps({'comparison':comparison,'completed':True,'tables':numeric['tables'],'execution_card_length':len(text),'provider_http_calls':0,'review':'pass'}))
