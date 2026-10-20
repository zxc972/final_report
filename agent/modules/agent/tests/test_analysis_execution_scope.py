import tempfile,pathlib,asyncio
import pytest
from test_analysis_agent import agent,FakeKnowledge,TestOnlyExecutor as FixtureExecutor,fixture_code
from langgraph.checkpoint.memory import InMemorySaver
class MinimalValidator:
 def validate(self,w):
  p=w/'analysis_manifest.json';return {'valid':p.is_file(),'passed':p.is_file(),'artifacts':[],'errors':[]if p.is_file()else ['No real output manifest']}
def make_tools(tmp_path):
 w=tmp_path/'work';d=tmp_path/'data';w.mkdir();d.mkdir();(d/'x.txt').write_text('input')
 return agent.AnalysisTools(w,[d],FixtureExecutor(w,[d]),FakeKnowledge())
def test_analysis_navigation_and_intermediate_prose_cannot_end_as_inspected(tmp_path):
 tools=make_tools(tmp_path)
 class Coder:
  def invoke(self,state,config):
   tools.ls(str(tools.input_roots[0]));return {'messages':[{'role':'assistant','content':'Let me read the remaining headers next.'}]}
 graph=agent._build_graph(Coder(),tools,MinimalValidator(),InMemorySaver())
 res=graph.invoke({'request':'Generate and execute the actual analysis','iterations':0,'execution_required':True},{'configurable':{'thread_id':'analysis'}})
 assert res['status']=='failed' and res['iterations']==agent.MAX_ROUNDS and res['validation']['valid']is False
 assert tools.executions==0

def test_explicit_metadata_mode_keeps_inspection_success(tmp_path):
 tools=make_tools(tmp_path)
 class Coder:
  def invoke(self,state,config):
   tools.ls(str(tools.input_roots[0]));return {'messages':[{'role':'assistant','content':'Observed the approved input listing.'}]}
 graph=agent._build_graph(Coder(),tools,MinimalValidator(),InMemorySaver())
 res=graph.invoke({'request':'Inspect input files only','iterations':0,'execution_required':False},{'configurable':{'thread_id':'inspect'}})
 assert res['status']=='inspected' and res['validation']['scope']=='data_inspection' and tools.executions==0

def test_analysis_continues_after_initial_narration_then_really_executes(tmp_path):
 tools=make_tools(tmp_path)
 class Coder:
  def __init__(self):self.n=0
  def invoke(self,state,config):
   self.n+=1
   if self.n==1:
    tools.ls(str(tools.input_roots[0]));text='Next I will compute the requested result.'
   else:
    tools.write_code('/work/generated.py',fixture_code());tools.run_python('/work/generated.py');text='Observed executed output.'
   return {'messages':[{'role':'assistant','content':text}]}
 coder=Coder();graph=agent._build_graph(coder,tools,MinimalValidator(),InMemorySaver())
 res=graph.invoke({'request':'Compute actual analysis','iterations':0,'execution_required':True},{'configurable':{'thread_id':'continue'}})
 assert res['status']=='completed' and res['iterations']==2 and tools.executions==1
@pytest.mark.parametrize('bad',['false',0,1,None])
def test_public_execution_scope_cannot_be_truthy_coerced(tmp_path,bad):
 with pytest.raises(ValueError,match='explicit boolean'):
  asyncio.run(agent.run_analysis(message='analyze',user_id='test',workspace=tmp_path,conversation_id='x',model='test',base_url='https://invalid.example/v1',api_key='synthetic',input_roots=[],execution_required=bad))

