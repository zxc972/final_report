"""Synthetic control-flow tests: actual fixture execution, AI review gate, automatic re-entry."""
from pathlib import Path
import json,sys,types
sys.path.insert(0,str(Path(__file__).parent))
from test_analysis_agent import agent,FakeKnowledge,TestOnlyExecutor,fixture_code
from langgraph.checkpoint.memory import InMemorySaver
import importlib
V=importlib.import_module(agent.__package__+'.analysis_validation').ArtifactValidator
def setup(tmp_path):
 work=tmp_path/'work';work.mkdir();tools=agent.AnalysisTools(work,[],TestOnlyExecutor(work,[]),FakeKnowledge())
 class Coder:
  calls=0
  def invoke(self,payload,config):
   self.calls+=1
   if self.calls>1:assert 'Internal Agent consistency review'in json.dumps(payload)
   report='sum=4 (synthetic stale report)'if self.calls==1 else'sum=5 (synthetic corrected report)'
   code=fixture_code()+'\nfrom pathlib import Path\nPath("report.md").write_text('+repr(report)+')\n'
   assert tools.write_code('/work/fixture.py',code)['syntax_valid'] is True
   assert tools.run_python('/work/fixture.py')['status']=='success'
   return {'messages':[{'content':'Fixture files produced; no scientific performance claim.'}]}
 return tools,Coder()
def test_internal_review_loops_to_coding_and_reserves_shared_model_budget(tmp_path):
 tools,coder=setup(tmp_path)
 class Reviewer:
  calls=0
  def invoke(self,messages):
   self.calls+=1;ctx=json.loads(messages[1]['content'])
   stale='sum=4'in ctx['files']['report.md']['text']
   return types.SimpleNamespace(content=json.dumps({'decision':'revise'if stale else'pass','findings':[{'severity':'blocking','claim':'Synthetic report says4.','observation':'Current fixture execution says5.','evidence_files':['report.md'],'question':'Does the current report agree with the actual executed fixture?'}]if stale else[],'limitations':['Synthetic engineering test only']}))
 reviewer=Reviewer();tools._internal_review_model=reviewer
 graph=agent._build_graph(coder,tools,V(),InMemorySaver())
 result=graph.invoke({'request':'Run fixture and report actual observed value.','history':[],'iterations':0},{'configurable':{'thread_id':'review-loop'}})
 assert result['status']=='completed'and result['iterations']==2
 assert coder.calls==2 and reviewer.calls==2 and tools.executions==2 and result['model_calls']==2
 assert (tools.workdir/'report.md').read_text().startswith('sum=5')
 reviews=list((tools.workdir.parent/'.analysis_reviews'/tools.workdir.name).glob('*.json'))
 assert len(reviews)==2 and len(list((tools.workdir.parent/'.execution_receipts'/tools.workdir.name).glob('*.json')))==2
def test_protocol_failure_reports_partial_without_reexecuting_fixture(tmp_path):
 tools,coder=setup(tmp_path)
 class Reviewer:
  def invoke(self,messages):return types.SimpleNamespace(content='unstructured assertion')
 tools._internal_review_model=Reviewer()
 result=agent._build_graph(coder,tools,V(),InMemorySaver()).invoke({'request':'Run fixture.','history':[],'iterations':0},{'configurable':{'thread_id':'review-unavailable'}})
 assert result['status']=='failed'and coder.calls==1 and tools.executions==1
 assert result['validation']['artifact_structural_passed']is True
 assert result['validation']['internal_review']['protocol_valid']is False

