"""Offline boundary tests only; fixtures are not real analysis or benchmark claims."""
import importlib,json,hashlib,struct,zlib
from pathlib import Path
import pytest
from test_analysis_agent import agent,TestOnlyExecutor,FakeKnowledge


def png_bytes():
    def chunk(tag,data):
        return struct.pack('>I',len(data))+tag+data+struct.pack('>I',zlib.crc32(tag+data)&0xffffffff)
    return (b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',2,1,8,2,0,0,0))
            +chunk(b'IDAT',zlib.compress(b'\x00\xff\x00\x00\x00\xff\x00'))+chunk(b'IEND',b''))


def code_fixture():
    return ("from pathlib import Path\nimport json\np=Path(__file__).parent\n"
            "(p/'values.tsv').write_text('roi\\tvalue\\nr1\\t2\\nr2\\t3\\n',encoding='utf-8')\n"
            "(p/'report.md').write_text('结果核对',encoding='utf-8')\n"
            "(p/'plan.json').write_text(json.dumps({'methods':'fixture','limitations':'offline only'}))\n"
            f"(p/'plot.png').write_bytes(bytes.fromhex('{png_bytes().hex()}'))\nprint('fixture done')\n")


def tools_fixture(tmp_path):
    work=tmp_path/'work';work.mkdir();data=tmp_path/'data';data.mkdir()
    tools=agent.AnalysisTools(work,[data],TestOnlyExecutor(work,[data]),FakeKnowledge())
    assert tools.write_code('/work/fixture.py',code_fixture())['status']=='written'
    assert tools.run_python('/work/fixture.py')['exit_code']==0
    return tools,work


def declarations():
    return [{'path':'values.tsv','kind':'tsv','columns':['roi','value'],'row_count':2,
             'finite_columns':['value'],'unique_columns':['roi'],'numeric_ranges':{'value':{'min':0,'max':10}}},
            {'path':'plot.png','kind':'png'},{'path':'report.md','kind':'markdown','min_chars':4,'max_chars':4},
            {'path':'plan.json','kind':'json','required_keys':['methods','limitations']}]


def test_actual_metadata_unicode_and_protected_receipt(tmp_path):
    tools,work=tools_fixture(tmp_path);before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in work.iterdir() if p.is_file()}
    supplied=declarations();result=tools.finalize_artifacts(supplied)
    assert result['status']=='finalized' and result['validation']['valid']
    assert result['scientific_status']=='not_evaluated' and result['independent_numeric_status']=='not_configured'
    m=json.loads((work/'analysis_manifest.json').read_text());tsv,png=m['artifacts'][:2]
    assert tsv['shape']==[2,2] and png['shape']==[1,2]
    assert tsv['row_count']==2 and tsv['finite_columns']==['value'] and tsv['numeric_ranges']==supplied[0]['numeric_ranges']
    assert 'shape' not in supplied[0] and 'shape' not in supplied[1]
    assert result['observations']['report.md']['observed']['characters']==4
    assert all(hashlib.sha256((work/name).read_bytes()).hexdigest()==h for name,h in before.items())
    p=work.parent/'.artifact_receipts'/work.name/(result['artifact_receipt_id']+'.json')
    receipt=json.loads(p.read_text());assert receipt['manifest_sha256']==hashlib.sha256((work/'analysis_manifest.json').read_bytes()).hexdigest()
    assert receipt['execution_receipt_id']==tools.last_execution['receipt_id']
    with pytest.raises(ValueError):tools.resolve(str(p),writable=True)


@pytest.mark.parametrize('constraint',[
    {'path':'values.tsv','kind':'tsv','row_count':99},
    {'path':'values.tsv','kind':'tsv','shape':[2,1]},
    {'path':'values.tsv','kind':'tsv','columns':['missing']},
    {'path':'values.tsv','kind':'tsv','numeric_ranges':{'value':{'min':10}}},
    {'path':'plot.png','kind':'png','shape':[2,1]},
    {'path':'plan.json','kind':'json','required_keys':['missing']},
    {'path':'report.md','kind':'markdown','min_chars':5},
])
def test_explicit_wrong_expectations_never_silently_replaced(tmp_path,constraint):
    tools,work=tools_fixture(tmp_path);r=tools.finalize_artifacts([constraint])
    assert r['status']!='finalized'
    V=importlib.import_module(agent.__package__+'.analysis_validation').ArtifactValidator
    assert not V().validate(work)['valid']


def test_failed_latest_request_does_not_reuse_earlier_manifest(tmp_path):
    tools,work=tools_fixture(tmp_path);assert tools.finalize_artifacts(declarations())['status']=='finalized'
    r=tools.finalize_artifacts([{'path':'values.tsv','kind':'tsv','row_count':99}])
    assert r['status']=='error'
    V=importlib.import_module(agent.__package__+'.analysis_validation').ArtifactValidator
    assert not V().validate(work)['valid']


@pytest.mark.parametrize('mode',['nan','invalid_png','traversal','link','duplicate','wrong_kind','unknown_field'])
def test_unusable_or_outside_files_cannot_finalize(tmp_path,mode):
    tools,work=tools_fixture(tmp_path);a=declarations()
    if mode=='nan':(work/'values.tsv').write_text('roi\tvalue\nr1\tNaN\nr2\t3\n')
    elif mode=='invalid_png':(work/'plot.png').write_bytes(png_bytes()[:-7])
    elif mode=='traversal':a=[{'path':'../data/private.tsv','kind':'tsv'}]
    elif mode=='link':
        out=tmp_path/'outside.tsv';out.write_text('value\n3\n');(work/'link.tsv').symlink_to(out);a=[{'path':'link.tsv','kind':'tsv'}]
    elif mode=='duplicate':a=[a[0],a[0]]
    elif mode=='wrong_kind':a=[{'path':'values.tsv','kind':'xlsx'}]
    elif mode=='unknown_field':a=[dict(a[0],reference_manifest='secret.json')]
    assert tools.finalize_artifacts(a)['status']!='finalized'


def test_no_receipt_changed_code_and_later_execution_guards(tmp_path):
    tools,work=tools_fixture(tmp_path);good=dict(tools.last_execution)
    tools.last_execution={};assert tools.finalize_artifacts(declarations())['status']=='error'
    tools.last_execution=dict(good,receipt_id='a'*32);assert tools.finalize_artifacts(declarations())['status']=='error'
    tools.last_execution=good;assert tools.finalize_artifacts(declarations())['status']=='finalized'
    assert tools.write_code('/work/fixture.py',code_fixture()+"print('new version')\n")['status']=='written'
    assert 'changed' in tools.finalize_artifacts(declarations())['error']
    assert tools.write_code('/work/fail.py',"raise RuntimeError('offline fixture failure')\n")['status']=='written'
    assert tools.run_python('/work/fail.py')['exit_code']!=0
    assert not (work/'analysis_manifest.json').exists()
    assert tools.finalize_artifacts(declarations())['status']=='error'


def test_real_deep_agent_selects_new_tool_and_closes_with_existing_validator(tmp_path):
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.messages import AIMessage,ToolMessage
    from langchain_core.outputs import ChatGeneration,ChatResult
    from langgraph.checkpoint.memory import InMemorySaver
    from pydantic import PrivateAttr
    class Model(BaseChatModel):
        _calls:int=PrivateAttr(default=0)
        @property
        def _llm_type(self):return 'offline-finalizer-tool-regression'
        def bind_tools(self,tools,**kw):
            assert 'finalize_artifacts' in {t.name for t in tools};return self
        def get_num_tokens(self,text):return max(1,len(text)//4)
        def get_num_tokens_from_messages(self,messages,tools=None):return sum(self.get_num_tokens(str(m.content)) for m in messages)
        def _generate(self,messages,stop=None,run_manager=None,**kw):
            # Scripted fixture model explicitly implements the new review protocol.
            # This does not weaken validator or original finalizer assertions.
            if messages and str(messages[0].content).startswith("You are the internal verifier in a scientific coding Agent"):
                self._calls+=1
                return ChatResult(generations=[ChatGeneration(message=AIMessage(content=json.dumps({
                    "decision":"pass","findings":[],"limitations":["Synthetic engineering test model only"]})))])
            i=self._calls;self._calls+=1
            seq=[('write_code',{'path':'/work/fixture.py','code':code_fixture()}),('run_python',{'path':'/work/fixture.py'}),('finalize_artifacts',{'artifacts':declarations()})]
            if i<len(seq):
                name,args=seq[i];m=AIMessage(content='',tool_calls=[{'name':name,'args':args,'id':f'final-{i}','type':'tool_call'}])
            else:
                assert any(isinstance(m,ToolMessage) and 'artifact_receipt_id' in str(m.content) for m in messages)
                m=AIMessage(content='Actual files finalized; scientific correctness remains unreviewed.')
            return ChatResult(generations=[ChatGeneration(message=m)])
    work=tmp_path/'work';work.mkdir();tools=agent.AnalysisTools(work,[],TestOnlyExecutor(work,[]),FakeKnowledge())
    coder=agent._build_coding_agent(tools,model='offline',base_url='https://example.invalid/v1',api_key='offline-key',model_factory=lambda **kw:Model())
    V=importlib.import_module(agent.__package__+'.analysis_validation').ArtifactValidator
    graph=agent._build_graph(coder,tools,V(),InMemorySaver())
    r=graph.invoke({'request':'offline fixture only','history':[],'iterations':0},{'configurable':{'thread_id':'finalizer-offline'}})
    assert r['status']=='completed' and r['iterations']==1 and tools.executions==1
