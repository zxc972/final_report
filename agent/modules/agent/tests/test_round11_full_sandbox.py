"""Actual Apptainer synthetic repair loop with a private host reference."""
import importlib
import json
import os
from pathlib import Path
import struct

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import PrivateAttr
from test_analysis_agent import agent
from test_analysis_product_planner import setup_products,p
from test_round10_independent_numeric import write_inputs




def prepare_fixture(tmp_path,monkeypatch):
    tools=setup_products(tmp_path,monkeypatch)
    root=tools.input_roots[0]
    for hemi in ['lh','rh']:
        write_inputs(root,hemi,new_table=True)
        (root/'label'/(hemi+'.alternate.annot')).write_bytes((root/'label'/(hemi+'.aparc.annot')).read_bytes())
        vertices=[(0.,0.,0.),(1.,0.,0.),(0.,1.,0.),(0.,0.,1.),(1.,1.,1.)]
        faces=[(0,1,2),(0,1,3),(0,2,3),(1,2,4),(1,3,4),(2,3,4)]
        raw=b'\xff\xff\xfe'+b'fixture\n\n'+struct.pack('>ii',5,6)+b''.join(struct.pack('>fff',*v) for v in vertices)+b''.join(struct.pack('>iii',*f) for f in faces)
        for suffix in ['white','pial','sphere.reg']:
            (root/'surf'/(hemi+'.'+suffix)).write_bytes(raw)
    saved=tools.control_store.latest('data_profile')['record']
    def field(value):
        return {'value':value,'source':{'path':'synthetic fixture','method':'Actual generated binary inputs'}}
    for item in saved['files']:
        path=item['path']['value']
        item['sha256']=field(p.file_hash(tools.resolve(path))[0])
        for section in ['metric','surface','label']:
            details=item.get(section,{}).get('value')
            if isinstance(details,dict) and 'vertex_count' in details:
                details['vertex_count']=field(5)
                if section=='surface':
                    details['face_count']=field(6)
                if section=='metric':
                    details['finite_count']=field(5)
                if section=='label' and path.endswith('.annot'):
                    details['cortex_retained_label_counts']=field({'-1':1,'1':2,'2':2})
    frozen=tools.control_store.save('data_profile',saved)
    monkeypatch.setattr(p,'ensure_profile',lambda *args:(frozen,True))
    planning=tools.plan_analysis({'measures':['thickness'],'regions':'all regions'})
    candidate=next(row for row in planning['candidates'] if row['atlas']['name']=='aparc')
    committed=tools._call(lambda:p.commit_candidate(tools,candidate['candidate_id'],'Synthetic structural fixture only','/work/analysis.py'))
    assert committed['status']=='committed',committed
    executor=importlib.import_module(agent.__package__+'.analysis_executor')
    tools.executor=executor.SandboxExecutor(tools.workdir,tools.input_roots)
    tools.executor.enable_operations(Path(agent.__file__).with_name('primatex_ops.py'),tools.operations_metadata['sha256'])
    # Rebuilding the coding agent mounts only the mature public operation library.
    source='''import csv,json
from pathlib import Path
import primatex_ops as ops
bundle=json.loads(Path('/work/execution_bundle.v000001.json').read_text())
label_sets=json.loads(Path(bundle['label_sets_ref']['path']).read_text())
rows=[]
for scope,group in label_sets.items():
    subject,hemisphere=scope.rsplit('/',1)
    metric_path=next(c['inputs']['metric_path'] for c in bundle['operations']['calls'] if c['function']=='parcel_summary' and c['scope']==scope)
    metric=ops.read_surface_metric(metric_path)
    labels,names,table=ops.read_annotation(group['annotation'])
    mask=ops.read_label(group['cortex_label'])
    for result in ops.parcel_summary(metric,labels,group['labels'],mask=mask):
        rows.append({'subject':subject,'hemisphere':hemisphere,'metric':'thickness','units':'stored, software convention mm',**result})
columns=bundle['output_contract']['csv_columns']
with open('/work/summary.csv','w',newline='') as stream:
    writer=csv.DictWriter(stream,fieldnames=columns,extrasaction='ignore')
    writer.writeheader()
    writer.writerows(rows)
Path('/work/summary.json').write_text(json.dumps({'methods':'Synthetic ROI fixture','limitations':'No scientific inference'}))
Path('/work/report.md').write_text('REPORT_MARKER synthetic fixture; stored scale only.')
'''
    return tools,source


@pytest.mark.skipif(os.environ.get('PRIMATEX_RUN_SANDBOX_TESTS')!='1',reason='Explicit isolated synthetic-container opt-in required')
def test_container_contract_then_numeric_then_review_revision_completes(tmp_path,monkeypatch):
    tools,source=prepare_fixture(tmp_path,monkeypatch)
    bad=source.replace("'metric':'thickness'", "'metric':'cortical_thickness'")
    assert bad!=source
    seen=[]
    messages_seen=[]
    class Model(BaseChatModel):
        _calls:int=PrivateAttr(default=0)
        @property
        def _llm_type(self):
            return 'offline-r11-full-loop'
        def bind_tools(self,tools,**kwargs):
            return self
        def get_num_tokens(self,text):
            return max(1,len(text)//4)
        def get_num_tokens_from_messages(self,messages,tools=None):
            return sum(self.get_num_tokens(str(m.content)) for m in messages)
        def _generate(self,messages,**kwargs):
            messages_seen.extend(str(m.content) for m in messages)
            index=self._calls
            self._calls+=1
            if index in [5,9]:
                return ChatResult(generations=[ChatGeneration(message=AIMessage(content='Synthetic descriptive draft; no scientific inference.'))])
            steps={
                0:('write_code',{'path':'/work/analysis.py','code':bad.replace('REPORT_MARKER','first')}),
                1:('run_python',{}),
                2:('read_file',{'path':'/work/tool_results/validation_feedback.json'}),
                3:('write_code',{'path':'/work/analysis.py','code':source.replace('REPORT_MARKER','first')}),
                4:('run_python',{}),
                6:('read_file',{'path':'/work/tool_results/validation_feedback.json'}),
                7:('write_code',{'path':'/work/analysis.py','code':source.replace('REPORT_MARKER','revised')}),
                8:('run_python',{}),
            }
            if index==2:
                assert tools.session.state()['phase']=='executed_failed'
                assert tools.control_store.latest('independent_numeric') is None
                feedback=json.loads((tools.workdir/'tool_results/validation_feedback.json').read_text())
                assert feedback['public_output_contract']['identity_mismatch_count']==8
                assert 'thickness' in str(feedback)
            if index==6:
                assert tools.session.state()['phase']=='executed_failed'
                feedback=json.loads((tools.workdir/'tool_results/validation_feedback.json').read_text())
                assert feedback['internal_review']['decision']=='revise'
                assert 'independent_numeric' not in feedback
            name,args=steps[index]
            seen.append(name)
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content='',tool_calls=[{'id':f'r11-{index}','name':name,'args':args}]))])
    class Reviewer:
        calls=0
        def invoke(self,messages):
            self.calls+=1
            rid=tools.last_execution['receipt_id']
            findings=[{'severity':'blocking','claim':'Synthetic report still carries the first marker','observation':'report.md has first instead of the revised fixture marker','question':'Resolve the report fixture inconsistency and rerun','evidence_files':[rid]}] if self.calls==1 else []
            return AIMessage(content=json.dumps({'decision':'revise' if self.calls==1 else 'pass','findings':findings,'hard_block_disclosure':{'complete':True,'undisclosed_constraint_ids':[],'evidence_files':['evidence_card'],'reason':'No hard blockers for the synthetic committed fixture'},'limitations':['Synthetic fixture only']}))
    coder=agent._build_coding_agent(tools,model='fixture',base_url='https://fixture.invalid/v1',api_key='fixture',model_factory=lambda **kwargs:Model())
    reviewer=Reviewer()
    tools._internal_review_model=reviewer
    validator=importlib.import_module(agent.__package__+'.analysis_validation').ArtifactValidator()
    result=agent._build_graph(coder,tools,validator,InMemorySaver()).invoke({'request':'Synthetic contract, numeric and review loop','history':[],'iterations':0},{'configurable':{'thread_id':'round11-synthetic-full'}})
    assert result['status']=='completed',result
    assert result['iterations']==2 and tools.executions==3 and reviewer.calls==2
    assert result['validation']['public_output_contract']['status']=='pass'
    assert result['validation']['independent_numeric_status']=='pass'
    assert tools.control_store.latest('independent_numeric')['record']['checked']==20
    assert tools.session.record['automatic_finalizations']==2
    assert len(tools.control_store.versions('independent_numeric_private'))==2
    assert not any('independent_numeric_private' in text or 'reference_source_sha256' in text for text in messages_seen)
    assert seen.count('read_file')==2 and seen.count('run_python')==3
