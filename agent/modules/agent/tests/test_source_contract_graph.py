import tempfile,json,hashlib
from pathlib import Path
from unittest.mock import patch
from backend.source_contract_graph import SourceContractGraph

def fixture(root):
 p=root/'sources'/'interface.py';p.parent.mkdir();p.write_text('class InputSpec:\n    mask = File(exists=True, argstr="--mask %s")\n')
 source={'path':'interface.py','url':'https://example.invalid/pinned/interface.py','sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'line_start':1,'line_end':2}
 nodes=[{'id':id,'type':type,'name':name,'family':family,'source':source,'executable':False,'metadata':meta} for id,type,name,family,meta in [('a','SoftwareInterface','Registration','ants',{}),('p','InputParameter','mask','ants',{'requires':['fixed_image'],'argstr':'--mask %s'}),('f','SoftwareInterface','FLIRT','fsl',{})]]
 graph={'schema':'primatex.software_contract_graph.v1','nodes':nodes,'edges':[{'source':'a','target':'p','relation':'HAS_INPUT_PARAMETER','executable':False}]}
 (root/'graph.json').write_text(json.dumps(graph));return p,graph

def test_graph_retrieval_retains_candidate_scope_edges_and_exact_source():
 with tempfile.TemporaryDirectory() as td:
  root=Path(td);p,_=fixture(root);g=SourceContractGraph(root)
  r=g.search('ants Registration mask');assert r['results'] and all(x['family']=='ants' for x in r['results'])
  e=g.read('p');assert '--mask %s' in e['evidence']['text'] and e['node']['metadata']['requires']==['fixed_image']
  assert e['relations'] and e['executable'] is False and e['review_status']=='source_parsed_candidate'
  assert e['evidence']['sha256']==hashlib.sha256(p.read_bytes()).hexdigest()

def test_source_checksum_and_ids_are_enforced():
 import pytest
 with tempfile.TemporaryDirectory() as td:
  root=Path(td);p,_=fixture(root);g=SourceContractGraph(root)
  with pytest.raises(KeyError):g.read('../private')
  p.write_text('changed')
  with pytest.raises(ValueError,match='checksum'):g.read('p')

def test_source_path_escape_and_undeclared_edges_rejected():
 import pytest
 with tempfile.TemporaryDirectory() as td:
  root=Path(td);_,graph=fixture(root);graph['nodes'][0]['source']['path']='../../private'
  (root/'graph.json').write_text(json.dumps(graph));g=SourceContractGraph(root)
  with pytest.raises(ValueError):g.read('a')
  graph['edges'].append({'source':'a','target':'absent','relation':'requires'});(root/'graph.json').write_text(json.dumps(graph))
  with pytest.raises(ValueError,match='endpoint'):SourceContractGraph(root)

def test_real_deep_agent_can_search_and_read_graph_source():
 from backend.analysis_knowledge import KnowledgeStore
 from backend.analysis_agent import AnalysisTools,_build_coding_agent
 from langchain_core.language_models.chat_models import BaseChatModel
 from langchain_core.messages import AIMessage,ToolMessage
 from langchain_core.outputs import ChatGeneration,ChatResult
 from pydantic import PrivateAttr
 class Model(BaseChatModel):
  _calls:int=PrivateAttr(default=0)
  @property
  def _llm_type(self):return 'offline-source-graph-tools'
  def bind_tools(self,tools,**kw):
   assert {'search_software_graph','read_software_graph'}<=set(t.name for t in tools);return self
  def get_num_tokens(self,text):return max(1,len(text)//4)
  def get_num_tokens_from_messages(self,messages,tools=None):return sum(self.get_num_tokens(str(m.content)) for m in messages)
  def _generate(self,messages,stop=None,run_manager=None,**kw):
   i=self._calls;self._calls+=1
   if i<2:
    name,args=[('search_software_graph',{'query':'ants Registration mask'}),('read_software_graph',{'node_id':'p'})][i]
    m=AIMessage(content='',tool_calls=[{'name':name,'args':args,'id':f'graph-{i}','type':'tool_call'}])
   else:
    assert any(isinstance(x,ToolMessage) and '--mask %s' in str(x.content) for x in messages)
    m=AIMessage(content='Original source read; candidate contract only.')
   return ChatResult(generations=[ChatGeneration(message=m)])
 with tempfile.TemporaryDirectory() as td:
  root=Path(td);groot=root/'graph';groot.mkdir();fixture(groot);work=root/'work';work.mkdir()
  with patch.dict('os.environ',{'AGENT_SOURCE_GRAPH_ROOT':str(groot)}):
   tools=AnalysisTools(work,[],None,KnowledgeStore());coder=_build_coding_agent(tools,model='offline',base_url='https://example.invalid/v1',api_key='not-a-secret-key',model_factory=lambda **kw:Model());out=coder.invoke({'messages':[{'role':'user','content':'Read the candidate software contract and original source.'}]})
   assert 'candidate' in out['messages'][-1].content.lower() and tools.executions==0
