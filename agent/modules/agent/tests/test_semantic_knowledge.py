"""Read-only knowledge tool integration; no API calls or participant execution."""
import hashlib,importlib.util,json,shutil,sys,tempfile,types,unittest
from pathlib import Path
BACKEND=Path(__file__).resolve().parents[1]/'backend'
package=types.ModuleType('_semantic_integration_backend');package.__path__=[str(BACKEND)]
sys.modules[package.__name__]=package
def load(name):
    spec=importlib.util.spec_from_file_location(package.__name__+'.'+name,BACKEND/(name+'.py'))
    m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m);return m
knowledge=load('analysis_knowledge');agent=load('analysis_agent')
class SemanticKnowledgeTests(unittest.TestCase):
    def test_reviewed_cards_search_read_and_no_execution(self):
        store=knowledge.KnowledgeStore()
        result=store.search_method_knowledge('组间比较 多站点 被试关联 表型 缺失 质量控制 统计设计',10)
        ids={x['id'] for x in result['results']}
        self.assertTrue({'cohort.identity','cohort.phenotype-missing','cohort.image-qc','cohort.design-scope'}<=ids)
        record=store.read('ft01.sd-conflict-qc')
        self.assertEqual(record['trust'],'untrusted_evidence')
        self.assertFalse(record['content']['executable'])
        self.assertIn('standard error',record['summary'])
        self.assertEqual(record['scientific_status'],'not_evaluated')
        for e in record['content']['evidence']:
            self.assertEqual(hashlib.sha256(e['text'].encode()).hexdigest(),e['text_sha256'])
    def test_real_analysis_tool_calls_without_executor(self):
        class ForbiddenExecutor:
            def run(self,*args,**kwargs):raise AssertionError('Knowledge lookup cannot execute analysis')
        with tempfile.TemporaryDirectory() as d:
            tools=agent.AnalysisTools(Path(d),[],ForbiddenExecutor(),knowledge.KnowledgeStore())
            result=tools.search_method_knowledge('DK DKT 名称 合并 软件版本 映射',10)
            self.assertEqual(result['status'],'ok');self.assertFalse(result['eligible_for_automatic_analysis'])
            self.assertIn('atlas.dk-dkt-difference',[x['id'] for x in result['results']])
            read=tools.read_knowledge('atlas.dk-dkt-difference')
            self.assertEqual(read['id'],'atlas.dk-dkt-difference')
            self.assertEqual(tools.executions,0);self.assertEqual(tools.tool_calls,2)
            self.assertEqual(list(Path(d).iterdir()),[])
    def test_missing_receipt_and_tampered_bundle_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'software_catalog.json').write_text('{"entries":[]}',encoding='utf-8')
            shutil.copy2(knowledge.DEFAULT_ROOT/'semantic_knowledge.json',root/'semantic_knowledge.json')
            with self.assertRaises((ValueError,FileNotFoundError)):knowledge.KnowledgeStore(root)
            shutil.copy2(knowledge.DEFAULT_ROOT/'semantic_acceptance.json',root/'semantic_acceptance.json')
            data=json.loads((root/'semantic_knowledge.json').read_text());data['records'][0]['summary']='unreviewed replacement'
            (root/'semantic_knowledge.json').write_text(json.dumps(data),encoding='utf-8')
            with self.assertRaises(ValueError):knowledge.KnowledgeStore(root)
    def test_bounded_search_and_no_match(self):
        s=knowledge.KnowledgeStore()
        self.assertEqual(s.search_method_knowledge('zzzznotpresent987')['results'],[])
        for limit in [0,11,True,'10']:
            with self.assertRaises(ValueError):s.search_method_knowledge('DKT',limit)
        with self.assertRaises(ValueError):s.search_method_knowledge('x'*1001)
    def test_real_deep_agent_dispatches_new_tool(self):
        from langchain_core.language_models.chat_models import BaseChatModel
        from langchain_core.messages import AIMessage,ToolMessage
        from langchain_core.outputs import ChatGeneration,ChatResult
        from pydantic import PrivateAttr
        class ScriptedModel(BaseChatModel):
            _calls:int=PrivateAttr(default=0)
            @property
            def _llm_type(self):return 'offline-semantic-integration'
            def bind_tools(self,tools,**kwargs):
                assert 'search_method_knowledge' in [t.name for t in tools]
                return self
            def get_num_tokens(self,text):return max(1,len(text)//4)
            def get_num_tokens_from_messages(self,messages,tools=None):return sum(self.get_num_tokens(str(m.content)) for m in messages)
            def _generate(self,messages,stop=None,run_manager=None,**kwargs):
                sequence=[('search_method_knowledge',{'query':'DK DKT 名称合并','limit':10}),('read_knowledge',{'knowledge_id':'atlas.dk-dkt-difference'})]
                i=self._calls;self._calls+=1
                m=AIMessage(content='',tool_calls=[{'name':sequence[i][0],'args':sequence[i][1],'id':f'semantic-{i}','type':'tool_call'}]) if i<len(sequence) else AIMessage(content='Evidence read; no analysis executed.')
                return ChatResult(generations=[ChatGeneration(message=m)])
        with tempfile.TemporaryDirectory() as d:
            tools=agent.AnalysisTools(Path(d),[],None,knowledge.KnowledgeStore())
            coder=agent._build_coding_agent(tools,model='offline',base_url='https://example.invalid/v1',api_key='offline-not-a-key',model_factory=lambda **kwargs:ScriptedModel())
            result=coder.invoke({'messages':[{'role':'user','content':'Inspect DK/DKT evidence only.'}]})
            outputs=[m for m in result['messages'] if isinstance(m,ToolMessage)]
            self.assertEqual(len(outputs),2)
            for m in outputs:self.assertNotEqual(m.status,'error');self.assertIn('atlas.dk-dkt-difference',str(m.content))
            self.assertEqual(tools.executions,0);self.assertEqual(tools.tool_calls,2)
            self.assertEqual(list(Path(d).iterdir()),[])
if __name__=='__main__':unittest.main()
