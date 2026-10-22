"""Real ToolNode verifies a common 18-call planning boundary and execution reserve."""
import importlib
from types import SimpleNamespace

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import PrivateAttr
from test_analysis_agent import agent
from test_analysis_product_planner import setup_products
from test_round8_closure import fake_execution

budget=importlib.import_module(agent.__package__+'.analysis_planning_budget')
phase=importlib.import_module(agent.__package__+'.analysis_phase_tools')


@pytest.mark.parametrize('model',['deepseek-v4-pro','deepseek-v4.1-flash'])
def test_last_planning_call_can_only_seal_then_execution_is_reserved(tmp_path,monkeypatch,model):
    monkeypatch.setattr(agent,'MAX_MODEL_CALLS',30)
    tools=setup_products(tmp_path,monkeypatch)
    planning=tools.plan_analysis({'measures':['thickness'],'regions':'aparc'})
    candidate=next(row['candidate_id'] for row in planning['candidates'] if row['atlas']['name']=='aparc')
    for _ in range(17):
        tools._tick(model=True)
    fake_execution(tools)
    seen=[]
    class Model(BaseChatModel):
        _calls:int=PrivateAttr(default=0)
        @property
        def _llm_type(self):
            return 'offline-planning-reserve'
        def bind_tools(self,tools,**kwargs):
            return self.bind(exposed=[phase.tool_name(t) for t in tools],choice=kwargs.get('tool_choice'))
        def get_num_tokens(self,text):
            return max(1,len(text)//4)
        def get_num_tokens_from_messages(self,messages,tools=None):
            return sum(self.get_num_tokens(str(m.content)) for m in messages)
        def _generate(self,messages,**kwargs):
            index=self._calls
            self._calls+=1
            seen.append(kwargs['exposed'])
            if index==0:
                assert set(kwargs['exposed'])=={'commit_plan'}
                assert any('Planning budget: 18/18' in str(m.content) for m in messages)
                assert 30-tools.model_calls>=8
                name,args='commit_plan',{'candidate_id':candidate,'rationale':'Synthetic feasible candidate','code_path':'/work/analysis.py'}
            elif index==1:
                assert set(kwargs['exposed'])==set(phase.SEALED_TOOLS)
                name,args='write_code',{'path':'/work/analysis.py','code':'# synthetic engineering fixture'}
            elif index==2:
                name,args='run_python',{}
            else:
                return ChatResult(generations=[ChatGeneration(message=AIMessage(content='Synthetic fixture finalized.'))])
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content='',tool_calls=[{'id':f'budget-{index}','name':name,'args':args}]))])
    coder=agent._build_coding_agent(tools,model=model,base_url='https://fixture.invalid/v1',api_key='fixture',model_factory=lambda **kw:Model())
    coder.invoke({'messages':[{'role':'user','content':'Choose a feasible method and execute the synthetic fixture.'}]})
    assert tools.session.record['planning_model_calls']==18
    assert tools.session.record['postseal_model_calls']==3
    assert tools.executions==1 and tools.session.state()['phase']=='finalized'


def test_no_sealed_plan_cannot_browse_into_execution_reserve(tmp_path,monkeypatch):
    monkeypatch.setattr(agent,'MAX_MODEL_CALLS',30)
    tools=setup_products(tmp_path,monkeypatch)
    for _ in range(18):
        tools._tick(model=True)
    assert tools.model_calls==18
    assert phase.phase_tools(tools.session,['ls','commit_plan','plan_analysis'])==frozenset()
    with pytest.raises(agent.BudgetExceeded,match='Planning stage limit'):
        tools._tick(model=True)
    assert tools.model_calls==18 and tools.executions==0
