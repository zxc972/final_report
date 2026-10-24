"""Round23 host regressions. Synthetic data only; scientific validators unchanged."""
import copy,csv,importlib,json,threading
from pathlib import Path
from types import SimpleNamespace
import pytest
from round14_fixture import fixture,p
from test_round8_closure import sealed
from test_analysis_agent import agent
from test_round21_feedback_planning import coding
from langchain_core.messages import ToolMessage


def mod(name):return importlib.import_module(agent.__package__+'.'+name)

@pytest.mark.parametrize('n',[20,100,200])
@pytest.mark.parametrize('regions',[62,124])
@pytest.mark.parametrize('metrics',[1,2,3])
@pytest.mark.parametrize('kind',['regional','group'])
def test_execution_card_length_grid(tmp_path,monkeypatch,n,regions,metrics,kind):
    if kind=='regional':
        tools,choice,saved=sealed(tmp_path,monkeypatch)
    else:
        tools,intent=fixture(tmp_path,monkeypatch)
        result=tools.plan_analysis(intent);assert result['candidates'],result
        choice=result['candidates'][0]
        saved=p.commit_candidate(tools,choice['candidate_id'],'Synthetic length grid','/work/test.py')
    assert saved['status']=='committed',saved
    plan=copy.deepcopy(saved['plan']);bundle=copy.deepcopy(saved['execution_bundle'])
    plan['data']['subjects']=['s'+str(i) for i in range(n)]
    plan['data']['measures']=['thickness','area','curv'][:metrics]
    # Stress the old input/allowed-values enumeration without changing science.
    template=copy.deepcopy(bundle.get('inputs',[]))
    if template:bundle['inputs']=[copy.deepcopy(template[i%len(template)]) for i in range(n*2*metrics)]
    bundle['output_contract']['allowed_values']={'subject':plan['data']['subjects'],'label_key':[str(i) for i in range(regions)],'metric':plan['data']['measures']}
    text=mod('analysis_execution_guidance').compact_card(plan,bundle)
    assert len(text)<=(1500 if kind=='group' else 2200)
    assert '/work/INPUTS.md' in text and 'write_contract_table' in text
    refs=saved['execution_bundle']['execution_documents']
    assert {r['path'] for r in refs}=={'/work/INPUTS.md','/work/contract_tables.json'}
    assert mod('analysis_execution_guidance').verify_documents(tools,saved['execution_bundle'])


def test_residual_overflow_is_host_defect_and_planning_refund_retains_actual_calls(tmp_path,monkeypatch):
    tools,_,committed=sealed(tmp_path,monkeypatch)
    defects=mod('analysis_system_defects')
    tools.model_calls=7
    tools.session.record.update(phase='planned',planning_model_calls=6,planning_actual_model_calls=6,last_planning_reservation=7)
    plan=copy.deepcopy(committed['plan']);bundle=committed['execution_bundle'];plan['code_path']='/work/'+('x'*2300)+'.py'
    for index in range(2):
        result=tools._call(lambda:mod('analysis_execution_guidance').compact_card(plan,bundle))
        assert result['status']=='system_defect' and not result['reflection_required']
        assert result['same_defect_count']==index+1
        assert 'smaller' not in result['error'] and 'reduce' not in result['error']
    assert tools.model_calls==7 and tools.session.record['planning_model_calls']==5
    assert tools.session.record['planning_actual_model_calls']==6
    with pytest.raises(defects.SystemDefectStop):tools._tick(model=True)
    assert tools.model_calls==7


def test_real_toolnode_no_unavailable_reflection_on_host_failure(tmp_path,monkeypatch):
    from test_analysis_product_planner import setup_products
    tools=setup_products(tmp_path,monkeypatch);seen=[]
    planned=tools.plan_analysis({'measures':['thickness'],'regions':'all regions'})
    candidate=planned['candidates'][0]['candidate_id']
    def broken(*args,**kwargs):raise mod('analysis_system_defects').SystemDefect('execution_card_length','synthetic host overflow',length=2300,limit=2200)
    monkeypatch.setattr(p,'commit_candidate',broken)
    def step(i,messages):
        if i==0:return 'commit_plan',{'candidate_id':candidate,'rationale':'synthetic defect','code_path':'/work/analysis.py'}
        payload=json.loads(next(m for m in reversed(messages) if isinstance(m,ToolMessage)).content);seen.append(payload)
        assert payload['status']=='system_defect' and payload['reflection_required'] is False
        assert 'record_analysis_reflection' not in payload.get('available_tools',[])
    coding(tools,step).invoke({'messages':[{'role':'user','content':'Synthetic failure'}]})
    assert tools.session.record.get('commit_argument_error') is False
    assert len(seen)==1 and mod('analysis_system_defects').latest(tools)['counts']=={'execution_card_length':1}


def test_contract_writer_roundtrip_and_strict_failures(tmp_path,monkeypatch):
    ops=mod('primatex_ops');contract=mod('analysis_output_contract')
    columns={'subject':'str','name':'str','value':'float','count':'int','nullable':'float'}
    spec={'columns':columns,'identity_columns':['subject'],'expected_identities':[{'subject':'s1'}],'allowed_values':{},'expected_rows':1,'extra_columns_allowed':False,'nullable_columns':['nullable']}
    (tmp_path/'contract_tables.json').write_text(json.dumps({'tables':{'canonical.csv':{'columns':list(columns)}}}))
    monkeypatch.setattr(ops,'CONTRACT_WORKDIR',str(tmp_path))
    result=ops.write_contract_table('canonical.csv',[{'count':3,'value':1.2345678901234567,'name':'中文,quoted','subject':'s1','nullable':None,'extra':'ignored'}])
    raw=(tmp_path/'canonical.csv').read_bytes()
    assert raw.decode().splitlines()[0]==','.join(columns)
    assert b'1.2345678901234567' in raw and b'3.0' not in raw
    assert list(csv.DictReader(raw.decode().splitlines()))[0]['nullable']==''
    assert contract.validate_csv(raw,spec,'canonical.csv')['status']=='pass'
    assert result['rows']==1
    for name in ['../canonical.csv','alias.csv','/work/canonical.csv']:
        with pytest.raises((ValueError,KeyError)):ops.write_contract_table(name,[])
    with pytest.raises(ValueError):ops.write_contract_table('canonical.csv',[{'subject':'s1'}])
    (tmp_path/'canonical.csv').unlink();(tmp_path/'canonical.csv').symlink_to(tmp_path/'victim.csv')
    with pytest.raises((ValueError,OSError)):ops.write_contract_table('canonical.csv',[])
    assert not (tmp_path/'victim.csv').exists()

@pytest.mark.parametrize('delimiter',['\t',';'])
def test_delimiter_diagnostics_do_not_change_validation(delimiter):
    d=mod('analysis_contract_diagnostics');c=mod('analysis_output_contract')
    raw=(delimiter.join(['subject','value'])+'\ns1'+delimiter+'1.0\n').encode()
    spec={'columns':{'subject':'str','value':'float'},'identity_columns':['subject'],'expected_identities':[{'subject':'s1'}],'expected_rows':1,'allowed_values':{}}
    result=c.validate_csv(raw,spec)
    info=d.inspect_bytes(raw)
    assert result['status']=='fail'
    assert info['detected_delimiter']==delimiter and info['observed_header']==[delimiter.join(['subject','value'])]
    assert info['diagnostic_only'] is True


def test_review_reserve_cannot_be_borrowed_and_persists(tmp_path,monkeypatch):
    tools,_,_=sealed(tmp_path,monkeypatch);monkeypatch.setattr(agent,'MAX_MODEL_CALLS',30)
    tools._internal_review_model=object();b=mod('analysis_review_budget')
    for _ in range(23):tools._tick(model=True)
    with pytest.raises(b.AgentBudgetExceeded):tools._tick(model=True)
    assert tools.model_calls==23 and not b.coding_available(tools)
    for _ in range(4):tools._tick(model=True,review=True)
    with pytest.raises(b.ReviewBudgetExceeded):tools._tick(model=True,review=True)
    assert tools.model_calls==27
    restored=b.ReviewBudget(tools).snapshot()
    assert restored['review_logical_calls']==4 and restored['budget_units_used']==27
    assert restored['revision_credits_remaining']==3 and not restored['revision_authorized']


def test_reserved_real_sdk_nonjson_revise_504_rereview_after_coding_limit(tmp_path,monkeypatch):
    from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
    native=mod('agent_chat_state');ACTIVE_CHAT,RequestBudget=native.ACTIVE_CHAT,native.RequestBudget
    observer=mod('analysis_http_observer');HTTPObserver,current_native_charge=observer.HTTPObserver,observer.current_native_charge
    tools,_,_=sealed(tmp_path,monkeypatch);monkeypatch.setattr(agent,'MAX_MODEL_CALLS',30)
    tools._internal_review_model=object();b=mod('analysis_review_budget');received=[];observed=[]
    provider=mod('analysis_provider');transport=mod('analysis_transport');monkeypatch.setattr(transport,'sleep_sync',lambda delay:None)
    monkeypatch.setenv('NO_PROXY','127.0.0.1,localhost')
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            received.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))));index=len(received)
            status=504 if index==3 else 200
            review={'decision':'revise' if index==2 else 'pass','findings':[{'severity':'blocking','claim':'Synthetic report mismatch','observation':'Synthetic revision required','evidence_files':['evidence_card'],'question':'Is the synthetic revision documented?'}] if index==2 else [],'limitations':['Synthetic only'],'hard_block_disclosure':{'complete':True,'undisclosed_constraint_ids':[],'evidence_files':['evidence_card'],'reason':'No synthetic hard blocks'}}
            content='not JSON' if index==1 else json.dumps(review)
            payload={'error':{'message':'synthetic upstream timeout','type':'timeout'}} if status==504 else {'id':'offline-review-'+str(index),'model':'offline-review','choices':[{'index':0,'message':{'role':'assistant','content':content},'finish_reason':'stop'}],'usage':{'prompt_tokens':11,'completion_tokens':3,'total_tokens':14}}
            raw=json.dumps(payload).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=lambda:server.serve_forever(poll_interval=.01),daemon=True);thread.start()
    class Store:
        def save(self,*args):pass
    session=SimpleNamespace(request_id='offline-round23-review',store=Store(),analysis_tools=tools,events=SimpleNamespace(append=lambda *args,**kwargs:None))
    session.budget=RequestBudget(session,30)
    token=ACTIVE_CHAT.set(session)
    def begin(request):return {'id':current_native_charge()['id']}
    def finish(ticket,response=None,error=None):observed.append({**ticket,'status':response.status_code if response is not None else None})
    try:
        for _ in range(23):
            tools._tick(model=True);session.budget.reserve('analysis')
        model=provider.CompatibleChatOpenAI(model='offline-review',base_url='http://127.0.0.1:'+str(server.server_port)+'/v1',api_key='synthetic-only',temperature=.7,max_retries=0,timeout=10)
        with HTTPObserver(begin,finish),b.review_scope(tools):
            outputs=[]
            for _ in range(3):
                outputs.append(mod('analysis_internal_review').run_review(tools.workdir,'Synthetic review; no external calls',{},model,lambda:tools._tick(model=True,review=True),evidence_card={'hard_blocks':[]}))
            with pytest.raises(b.ReviewBudgetExceeded):tools._tick(model=True,review=True)
        assert outputs[0]['decision']=='revise' and outputs[0]['protocol_attempts']==2 and outputs[1]['decision']=='pass' and outputs[1]['protocol_attempts']==1
        assert 'Previous review failed strict validation' in str(received[1]['messages'])
        assert [r['status'] for r in observed]==[200,200,504,200,200]
        assert len(received)==5 and len(session.budget.records)==28
        assert [r['id'] for r in observed]==[r['id'] for r in session.budget.records[-5:]]
        snapshot=b.get(tools).snapshot()
        assert snapshot['nonreview_model_calls']==23 and snapshot['review_logical_calls']==4 and snapshot['review_http_attempts']==5 and snapshot['budget_units_used']==27
        assert tools.model_calls==27
    finally:
        ACTIVE_CHAT.reset(token);server.shutdown();server.server_close();thread.join(timeout=2)


@pytest.mark.parametrize('payload,expected',[
    ({'system_defects':{'events':[{'code':'execution_card_length'}]}},'system_defect'),
    ({'execution':{'agent_error':'Agent model budget exhausted'}},'agent_budget_exhausted'),
    ({'validation':{'internal_review':{'decision':'revise','protocol_valid':True}}},'review_incomplete'),
    ({'validation':{'public_output_contract':{'status':'fail'}}},'contract_failed')])
def test_distinct_failure_categories_have_evidence(payload,expected):
    result=mod('analysis_failure_classification').classify({'route':'analysis','status':'failed',**payload})
    assert result['category']==expected and result['reason']
