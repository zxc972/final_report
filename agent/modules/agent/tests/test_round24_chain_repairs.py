"""Round24 regression of observed identity, protected pools and CSV preflight."""
import copy,csv,json,threading
from pathlib import Path
from types import SimpleNamespace
import pytest
from test_round23_system_repairs import mod
from test_round8_closure import sealed
from round14_fixture import fixture,p
from test_analysis_agent import agent


def review_payload(ids):
    return {'decision':'revise' if ids else 'pass',
            'findings':[{'severity':'blocking','claim':'Undisclosed blocker','observation':'Synthetic source blocker',
                         'question':'Disclose it','evidence_files':['evidence_card']}] if ids else [],
            'limitations':['Synthetic only'],
            'hard_block_disclosure':{'complete':not ids,'undisclosed_constraint_ids':ids,
                                     'evidence_files':['evidence_card'],'reason':'Observed synthetic constraints'}}


@pytest.mark.parametrize('identity',['c1','method:synthetic:a:c1'])
def test_review_resolves_only_unique_observed_aliases(identity):
    card={'hard_blocks':[{'method_id':'method:synthetic:a','constraint_id':'c1'}]}
    result,_=mod('analysis_review_protocol').parse_structured_review(json.dumps(review_payload([identity])),{'evidence_card'},card)
    assert result['hard_block_disclosure']['undisclosed_constraint_ids']==['method:synthetic:a:c1']


@pytest.mark.parametrize('identity',['c1','method:forged:c1','nonexistent'])
def test_review_rejects_ambiguous_or_forged_ids(identity):
    card={'hard_blocks':[{'method_id':'method:synthetic:'+m,'constraint_id':'c1'} for m in ['a','b']]}
    with pytest.raises(ValueError,match='observed hard-block ids'):
        mod('analysis_review_protocol').parse_structured_review(json.dumps(review_payload([identity])),{'evidence_card'},card)


def test_qualified_constraint_is_valid_evidence_and_disambiguates():
    card={'hard_blocks':[{'method_id':'method:synthetic:'+m,'constraint_id':'c1'} for m in ['a','b']]}
    payload=review_payload(['method:synthetic:b:c1']);payload['findings'][0]['evidence_files']=['method:synthetic:b:c1']
    parsed,_=mod('analysis_review_protocol').parse_structured_review(json.dumps(payload),{'evidence_card'},card)
    assert parsed['findings'][0]['evidence_files']==['method:synthetic:b:c1']
    assert mod('analysis_constraint_ids').canonical_row({'method_id':'method:synthetic:a','constraint_id':'method:synthetic:a:c1'})['constraint_id']=='method:synthetic:a:c1'


def test_initial_review_revision_disjoint_and_restored(tmp_path,monkeypatch):
    tools,_,_=sealed(tmp_path,monkeypatch);monkeypatch.setattr(agent,'MAX_MODEL_CALLS',30)
    tools._internal_review_model=object();budget=mod('analysis_review_budget');b=budget.get(tools)
    for _ in range(23):tools._tick(model=True)
    with pytest.raises(budget.AgentBudgetExceeded):tools._tick(model=True)
    for invalid in [{'decision':'revise','protocol_valid':False},{'decision':'pass','protocol_valid':True}]:
        with pytest.raises(ValueError):b.authorize_revision(invalid)
    assert b.revision_open is False and tools.model_calls==23
    tools._tick(model=True,review=True)
    b.authorize_revision({'decision':'revise','protocol_valid':True,'review_id':'synthetic-review'})
    for _ in range(3):tools._tick(model=True)
    with pytest.raises(budget.AgentBudgetExceeded):tools._tick(model=True)
    b.authorize_revision({'decision':'revise','protocol_valid':True,'review_id':'another-review'})
    with pytest.raises(budget.AgentBudgetExceeded):tools._tick(model=True)
    for _ in range(3):tools._tick(model=True,review=True)
    with pytest.raises(budget.ReviewBudgetExceeded):tools._tick(model=True,review=True)
    restored=budget.ReviewBudget(tools).snapshot()
    assert tools.model_calls==30 and restored['initial_coding_model_calls']==23
    assert restored['revision_model_calls']==3 and restored['review_logical_calls']==4
    assert restored['revision_authorized'] and restored['budget_units_used']==30


def test_review_transport_cap_keeps_rate_limit_cause_and_general_policy(tmp_path,monkeypatch):
    tools,_,_=sealed(tmp_path,monkeypatch);monkeypatch.setattr(agent,'MAX_MODEL_CALLS',30)
    tools._internal_review_model=object();budget=mod('analysis_review_budget');transport=mod('analysis_transport')
    monkeypatch.setattr(transport,'sleep_sync',lambda delay:None)
    class Limited(RuntimeError):status_code=429
    seen=[]
    def call(index):
        budget.reserve_http_attempt(bool(index));seen.append(index);raise Limited('Synthetic only')
    tools._tick(model=True,review=True)
    with budget.review_scope(tools),pytest.raises(transport.RateLimited) as caught:transport.retry_sync(call)
    assert caught.value.attempts==3 and seen==[0,1,2]
    assert budget.get(tools).snapshot()['review_logical_calls']==1
    assert budget.get(tools).snapshot()['review_http_attempts']==3
    seen=[]
    def ordinary(index):seen.append(index);raise Limited('Synthetic only')
    with pytest.raises(transport.RateLimited) as caught:transport.retry_sync(ordinary)
    assert caught.value.attempts==4 and seen==[0,1,2,3]


def test_writer_rejects_semantic_identity_before_any_write(tmp_path,monkeypatch):
    ops=mod('primatex_ops');monkeypatch.setattr(ops,'CONTRACT_WORKDIR',str(tmp_path))
    spec={'columns':['subject','label_key','effect','effect_size_kind'],
          'column_types':{'label_key':'int'},'fixed_values':{'effect':'age'},
          'enums':{'effect_size_kind':['cohens_d','pearson_r','partial_r']},
          'identity_columns':['subject','label_key'],
          'expected_identities':[{'subject':'s1','label_key':1}],'expected_rows':1}
    (tmp_path/'contract_tables.json').write_text(json.dumps({'tables':{'canonical.csv':spec}}))
    valid={'subject':'s1','label_key':1,'effect':'age','effect_size_kind':'partial_r'}
    for change in [{'effect_size_kind':'hedges_g'},{'effect':'sex'},{'subject':'invented'},{'label_key':2}]:
        with pytest.raises(ValueError):ops.write_contract_table('canonical.csv',[{**valid,**change}])
        assert not (tmp_path/'canonical.csv').exists()
    ops.write_contract_table('canonical.csv',[valid]);original=(tmp_path/'canonical.csv').read_bytes()
    with pytest.raises(ValueError,match='cohens_d'):ops.write_contract_table('canonical.csv',[{**valid,'effect_size_kind':'hedges_g'}])
    assert (tmp_path/'canonical.csv').read_bytes()==original
    with pytest.raises(ValueError,match='Duplicate'):ops.write_contract_table('canonical.csv',[valid,valid])
    assert (tmp_path/'canonical.csv').read_bytes()==original
    assert list(csv.DictReader(original.decode().splitlines()))[0]=={k:str(v) for k,v in valid.items()}


def test_group_design_ranks_glm_and_marks_roi(tmp_path,monkeypatch):
    tools,intent=fixture(tmp_path,monkeypatch,'correlation');intent.pop('method_id',None)
    result=tools.plan_analysis(intent);assert result['candidates'],result
    assert result['candidates'][0]['method']['method_id']=='method:v14:group_regional_glm'
    roi=[x for k in ['candidates','needs_preprocessing','infeasible'] for x in result[k] if x.get('method',{}).get('method_id')=='method:v12:surface_annotation_roi']
    assert roi and all(not x['group_design_match']['supported'] for x in roi)
    assert all(x['group_design_match']['commit_requires_mismatch_reason'] for x in roi)
    candidate=result['candidates'][0];saved=tools.control_store.latest(candidate['candidate_id'])
    record=copy.deepcopy(saved['record']);record['group_design_match']={'commit_requires_mismatch_reason':True}
    tools.control_store.save(candidate['candidate_id'],record)
    with pytest.raises(ValueError,match='design_mismatch_reason'):p.commit_candidate(tools,candidate['candidate_id'],'Synthetic choice','/work/model.py')
    sealed_plan=p.commit_candidate(tools,candidate['candidate_id'],'Synthetic choice','/work/model.py',design_mismatch_reason='Synthetic mismatch explanation; no scientific prerequisites are waived')
    assert sealed_plan['status']=='committed'
    assert 'Synthetic mismatch explanation' in sealed_plan['plan']['selection_rationale']
    card=mod('analysis_execution_guidance').compact_card(sealed_plan['plan'],sealed_plan['execution_bundle'])
    assert 'effect_size_kind' in card and 'cohens_d' in card and 'partial_r' in card and 'age' in card
    assert len(card)<=1500


def test_real_sdk_review_and_revision_finish_after_initial_limit(tmp_path,monkeypatch):
    from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
    from collections import Counter
    native=mod('agent_chat_state');observer=mod('analysis_http_observer');provider=mod('analysis_provider')
    budget=mod('analysis_review_budget');transport=mod('analysis_transport')
    monkeypatch.setattr(transport,'sleep_sync',lambda delay:None);monkeypatch.setenv('NO_PROXY','127.0.0.1,localhost')
    tools,_,_=sealed(tmp_path,monkeypatch);monkeypatch.setattr(agent,'MAX_MODEL_CALLS',30);tools._internal_review_model=object()
    requests=[];observed=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            requests.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))));index=len(requests)
            status={3:504,4:429}.get(index,200)
            content='not JSON' if index==1 else json.dumps(review_payload([]))
            if index==2:
                value=review_payload(['c1']);content=json.dumps(value)
            payload={'error':{'message':'synthetic transient'}} if status!=200 else {'id':'offline-'+str(index),'model':'offline',
                     'choices':[{'index':0,'message':{'role':'assistant','content':content},'finish_reason':'stop'}],
                     'usage':{'prompt_tokens':11,'completion_tokens':3,'total_tokens':14}}
            raw=json.dumps(payload).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=lambda:server.serve_forever(poll_interval=.01),daemon=True);thread.start()
    class Store:
        def save(self,*args):pass
    session=SimpleNamespace(request_id='synthetic-round24',store=Store(),analysis_tools=tools,events=SimpleNamespace(append=lambda *args,**kwargs:None))
    session.budget=native.RequestBudget(session,30);token=native.ACTIVE_CHAT.set(session)
    def begin(request):return {'id':observer.current_native_charge()['id']}
    def finish(ticket,response=None,error=None):observed.append({**ticket,'status':response.status_code if response is not None else None})
    def coding():
        tools._tick(model=True);charge=session.budget.reserve('analysis');session.budget.finish(charge,{'prompt_tokens':1,'completion_tokens':1,'total_tokens':2},'response_received')
    try:
        for _ in range(23):coding()
        model=provider.CompatibleChatOpenAI(model='offline',base_url='http://127.0.0.1:'+str(server.server_port)+'/v1',api_key='synthetic-only',temperature=.7,max_retries=0,timeout=10)
        def review():
            with budget.review_scope(tools):return mod('analysis_internal_review').run_review(tools.workdir,'Synthetic only',{},model,lambda:tools._tick(model=True,review=True),evidence_card={'hard_blocks':[{'method_id':'method:synthetic','constraint_id':'c1'}]})
        with observer.HTTPObserver(begin,finish):
            first=review();assert first['decision']=='revise' and first['protocol_valid']
            budget.get(tools).authorize_revision(first)
            for _ in range(3):coding()
            second=review();assert second['decision']=='pass' and second['protocol_valid']
            third=review();assert third['decision']=='pass' and third['protocol_valid']
        assert tools.model_calls==30 and len(requests)==6
        assert [x['status'] for x in observed]==[200,200,504,429,200,200]
        state=budget.get(tools).snapshot()
        assert state['initial_coding_model_calls']==23 and state['revision_model_calls']==3
        assert state['review_logical_calls']==4 and state['review_http_attempts']==6
        assert state['review_http_by_logical']==[1,1,3,1] and state['budget_units_used']==30
        assert session.budget.view()['model_calls']==30 and session.budget.view()['http_attempts']==32
        assert all(x['id'] in {r['id'] for r in session.budget.records} for x in observed)
    finally:
        native.ACTIVE_CHAT.reset(token);server.shutdown();server.server_close();thread.join(timeout=2)


def test_fitted_kind_cannot_use_skipped_nullable_exception(tmp_path,monkeypatch):
    ops=mod('primatex_ops');monkeypatch.setattr(ops,'CONTRACT_WORKDIR',str(tmp_path))
    spec={'columns':['status','effect_size_kind'],'schema':'primatex.group_table_contract.v1',
          'enums':{'effect_size_kind':['cohens_d','pearson_r','partial_r']},'nullable_columns':['effect_size_kind']}
    (tmp_path/'contract_tables.json').write_text(json.dumps({'tables':{'fit.csv':spec}}))
    with pytest.raises(ValueError,match='cohens_d'):ops.write_contract_table('fit.csv',[{'status':'ok','effect_size_kind':None}])
    assert not (tmp_path/'fit.csv').exists()
    ops.write_contract_table('fit.csv',[{'status':'skipped:synthetic','effect_size_kind':None}])


def test_closed_evaluation_stops_after_first_system_defect(monkeypatch):
    from backend import analysis_system_defects as defects
    from types import SimpleNamespace
    from threading import RLock
    saved = {}
    class Store:
        def latest(self, key):
            return {"record": saved[key]} if key in saved else None
        def save(self, key, value):
            saved[key] = value
    tools = SimpleNamespace(control_store=Store(), session=None, model_calls=1,
                            events=None, _lock=RLock())
    monkeypatch.setattr(defects, "STOP_AFTER", 1)
    result = defects.record(tools, defects.SystemDefect("synthetic_defect", "offline"))
    assert result["stop_required"] is True
    with pytest.raises(defects.SystemDefectStop):
        defects.check_stop(tools)
    assert tools.model_calls == 1
