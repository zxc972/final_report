"""Offline authorization, frozen input, and stratified evaluation regressions."""
from pathlib import Path
import json,sys
import httpx
import pytest
ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT))
from tools.knowledge import provider_llm as transport
from tools.knowledge import run_condition_test_v2_evaluation as run


def config():
    return transport.Config(base_url='https://example.invalid/v1',api_key='offline-placeholder',max_attempts=1)


def test_explicit_round23_cap_does_not_expand_legacy_authorization(tmp_path):
    with pytest.raises(ValueError):transport.Provider(config(),tmp_path/'legacy',1201)
    with pytest.raises(ValueError):transport.Provider(config(),tmp_path/'over',1501,authorized_max_requests=1500)
    p=transport.Provider(config(),tmp_path/'approved',1500,authorized_max_requests=1500)
    assert p.max_requests==1500 and p.stats()['http_attempts']==0
    p.close()


def test_meter_resume_cannot_reset_used_authorization(tmp_path):
    calls=[]
    def send(request):
        calls.append(request)
        return httpx.Response(200,json={'choices':[{'message':{'content':'{}'},'finish_reason':'stop'}],
                            'usage':{'prompt_tokens':5,'completion_tokens':2,'total_tokens':7}},request=request)
    for attempt in range(2):
        client=httpx.Client(transport=httpx.MockTransport(send))
        p=transport.Provider(config(),tmp_path,1,client=client)
        with transport.scope('full_v2',1,1):assert p.complete('same frozen prompt')=='{}'
        with transport.scope('full_v2',2,1):
            with pytest.raises(transport.ProviderFailure):p.complete('new prompt over cap')
        assert p.stats()['http_attempts']==1
        p.close()
    assert len(calls)==1


def test_combined_bootstrap_keeps_original_test_sizes():
    class Keys:
        @staticmethod
        def canonical_key(template,parameters):return template+json.dumps(parameters,sort_keys=True)
    items=[{'id':1,'method':'one','gold_template':'software','gold_parameters':{'name':'x'}},
           {'id':2,'method':'two','gold_template':'advisory','gold_parameters':None}]
    preds=[{'id':i['id'],'method':i['method'],'template':'software','parameters':{'name':'x'},'decision':'accepted'} for i in items]
    report=run.stratified_bootstrap(Keys,items,{'full_v2':preds},['v1','v2'],replicates=40)
    assert report['strata_counts']=={'v1':1,'v2':1}
    for ci in report['arms']['full_v2']['intervals_95'].values():assert ci['low']==ci['estimate']==ci['high']
    assert report['arms']['full_v2']['metrics']['template_accuracy']==.5


def test_round23_gold_identity_and_annotation_bytes_are_frozen():
    gold=run.verify_gold()
    assert len(gold['items'])==83
    assert run.base.sha256(ROOT/'evaluation/condition_gold/gold_test_v2.json')==run.GOLD_SHA
    assert run.base.sha256(run.base.BACKEND/'analysis_condition_canonicalizer.py')==run.ALGORITHM_SHA