"""Round23 frozen test-v2 evaluation and stratified v1+v2 reporting.

Uses the unchanged Round18 prediction/retry/scoring code. No analysis runs,
label edits, parameter tuning, or development-set repairs.
"""
from __future__ import annotations
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
import hashlib,json,random,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tools.knowledge import run_condition_test_evaluation as old
from tools.knowledge import condition_evaluation_statistics as stats
base,v2,transport=old.base,old.v2,old.transport
CAP=1500
GOLD_SHA='2ca5ca7492d9f09569372085a0cf75715d41a8e78e8bd24a0fc5c38015d84e3e'
ALGORITHM_SHA='140669418d7a6603df4dbe55be7a677d9f0d8bff92d7255a7aadff1892bb07d8'
PENDING=[2008,2009,2014,2015,2017,2031,2039]
ARMS=old.ARMS
SEED=20261023


def verify_gold(root=ROOT):
    path=root/'evaluation/condition_gold/gold_test_v2.json'
    assert base.sha256(path)==GOLD_SHA
    gold=json.loads(path.read_text(encoding='utf-8'))
    packet=root/'evaluation/condition_test_v2/claude_annotation_packet'
    original=json.loads((packet/'statements_unlabelled.json').read_text(encoding='utf-8'))
    assert len(gold['items'])==83
    assert [i['id'] for i in gold['items']]==list(range(2001,2084))
    assert [i['id'] for i in gold['items'] if i['pending_user_decision']]==PENDING
    assert Counter(i['gold_template']!='advisory' for i in gold['items'])=={True:15,False:68}
    for item,unlabelled in zip(gold['items'],original['items']):
        assert all(item[k]==v for k,v in unlabelled.items()),item['id']
        text=(packet/'sources'/(item['source_id']+'.txt')).read_text(encoding='utf-8')
        span=item['source_span'];assert text[span['start']:span['end']]==item['quote']
        assert hashlib.sha256(text.encode()).hexdigest()==span['text_sha256']
    gold['slots']=original['slots']
    return gold


def stratified_bootstrap(c,items,predictions,strata,replicates=2000,seed=SEED):
    assert len(items)==len(strata) and items
    assert all([p['id'] for p in ps]==[i['id'] for i in items] for ps in predictions.values())
    groups={s:[j for j,v in enumerate(strata) if s==v] for s in dict.fromkeys(strata)}
    point={arm:base.score_with_details(c,items,ps) for arm,ps in predictions.items()}
    draws={arm:{k:[] for k in stats.METRICS} for arm in predictions};rng=random.Random(seed)
    for _ in range(replicates):
        indices=[j for group in groups.values() for j in rng.choices(group,k=len(group))]
        sample=[items[j] for j in indices]
        for arm,ps in predictions.items():
            values=stats.flatten(base.score_with_details(c,sample,[ps[j] for j in indices]))
            for k,v in values.items():draws[arm][k].append(v)
    result={arm:{'metrics':point[arm],'intervals_95':{k:{'estimate':stats.flatten(point[arm])[k],
            'low':stats.percentile(vals,.025),'high':stats.percentile(vals,.975)} for k,vals in draws[arm].items()}} for arm in predictions}
    return {'n':len(items),'replicates':replicates,'seed':seed,'strata_counts':dict(Counter(strata)),
            'interval_method':'paired statement percentile bootstrap stratified by original test set; linear quantiles',
            'key_set_policy':'unchanged unique (method,key) sets recomputed in each resample; repeats collapse', 'arms':result}


def write_reports(c,out,gold,previous,predictions):
    v1=old.verify_gold();items=v1['items']+gold['items'];assert len(items)==128
    assert sum(i['gold_template']!='advisory' for i in items)==24
    combined={a:previous[a]+predictions[a] for a in ARMS};strata=['v1']*45+['v2']*83
    splits={
      'v2_83':(gold['items'],predictions,None),
      'v2_nonpending_76':([i for i in gold['items'] if not i['pending_user_decision']],
          {a:[p for i,p in zip(gold['items'],ps) if not i['pending_user_decision']] for a,ps in predictions.items()},None),
      'combined_128':(items,combined,strata)}
    for name,exclude in [('combined_exclude_v2_pending_121',set(PENDING)),
                         ('combined_exclude_all_pending_115',{i['id'] for i in items if i['pending_user_decision']})]:
        positions=[j for j,i in enumerate(items) if i['id'] not in exclude]
        splits[name]=([items[j] for j in positions],{a:[ps[j] for j in positions] for a,ps in combined.items()},[strata[j] for j in positions])
    paired={};lines=['# Round23 condition test v2 and combined evaluation','',
        'Algorithm, prompts, vocabulary, slots, score definitions and settings match Round18. V1 predictions are reused byte-for-byte; only the 83 new statements receive model calls.',
        'Bootstrap: 2000 paired statement resamples, seed 20261023; combined sets preserve each test set size in every resample. Pending labels are scored as supplied.','',
        'Primary sensitivity excludes the seven pending v2 items; an additional combined sensitivity excludes all thirteen pending v1+v2 items. No defaults are adjusted.','']
    for name,(its,ps,strat) in splits.items():
        report=stats.bootstrap(c,its,ps,seed=SEED) if strat is None else stratified_bootstrap(c,its,ps,strat)
        report['gold_class_counts']=dict(Counter('advisory' if i['gold_template']=='advisory' else 'executable' for i in its))
        base.save_json(out/('metrics_'+name+'.json'),report)
        paired[name]=stats.paired_comparisons(c,its,ps)
        lines+=['## '+name,'',*stats.point_table(report),'',*stats.ci_table(report),'']
        base.write_csv(out/('intervals_'+name+'.csv'),[{'arm':arm,'metric':metric,**ci} for arm,r in report['arms'].items() for metric,ci in r['intervals_95'].items()])
    base.save_json(out/'mcnemar.json',paired)
    errors=stats.full_errors(c,gold['items'],predictions['full_v2']);base.save_json(out/'errors_full_v2.json',errors)
    base.write_csv(out/'errors_full_v2.csv',[{k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in row.items()} for row in errors])
    lines+=['## McNemar exact paired tests','','```json',json.dumps(paired,ensure_ascii=False,indent=2),'```','',
            'Full-v2 error statements, supplied gold, predictions and reasons: errors_full_v2.json / .csv.']
    (out/'REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',required=True);ap.add_argument('--provider-config',required=True);ap.add_argument('--workers',type=int,default=4);ap.add_argument('--prepare-only',action='store_true');ap.add_argument('--resume',action='store_true');args=ap.parse_args();assert 1<=args.workers<=4
    config=transport.load_config(args.provider_config,model='deepseek-v4.1-flash',temperature=.7,max_tokens=8192,thinking='disabled',json_output=True,timeout=180)
    gold=verify_gold();c=base.load_canon();assert base.sha256(base.BACKEND/'analysis_condition_canonicalizer.py')==ALGORITHM_SHA
    olddir=ROOT/'results/condition_canon_test_v1';prior_frozen=json.loads((olddir/'frozen.json').read_text(encoding='utf-8'));assert config.public()==prior_frozen['provider']
    vocab,vocab_sha=v2.load_vocab();assert vocab==prior_frozen['vocabulary'] and gold['slots']==prior_frozen['slots']
    for n,value in prior_frozen['parameters'].items():assert getattr(c,n)==value
    previous={a:json.loads((olddir/f'predictions_{a}.json').read_text(encoding='utf-8')) for a in ARMS}
    texts={method:base.sources(ROOT/'evaluation/condition_test_v2/method_extractions',method) for method in {i['method'] for i in gold['items']}}
    for item in gold['items']:assert item['quote'] in texts[item['method']][item['source_id']]
    sources={f'evaluation/condition_test_v2/method_extractions/{m}.input.json':base.sha256(ROOT/f'evaluation/condition_test_v2/method_extractions/{m}.input.json') for m in texts}
    code=[base.BACKEND/'analysis_condition_canonicalizer.py',Path(__file__),Path(transport.__file__),Path(v2.__file__),Path(base.__file__),Path(old.__file__),Path(stats.__file__)]
    frozen={'schema':'primatex.condition_test_run.v2','gold_sha256':GOLD_SHA,'gold_freeze':json.loads((ROOT/'evaluation/condition_test_v2/ROUND23_GOLD_FREEZE.json').read_text(encoding='utf-8')),'provider':config.public(),'slots':gold['slots'],'vocabulary':vocab,'vocabulary_sha256':vocab_sha,'parameters':prior_frozen['parameters'],'workers':args.workers,'code_sha256':{p.relative_to(ROOT).as_posix():base.sha256(p) for p in code},'source_sha256':sources,'historical_prediction_sha256':{a:base.sha256(olddir/f'predictions_{a}.json') for a in ARMS},'retry_policy':old.ResilientSamples.__doc__,'shared_http_cap':CAP,'nominal_samples':581,'minimum_interval_seconds':2.,'arms':list(ARMS),'bootstrap_replicates':2000,'bootstrap_seed':SEED,'combined_bootstrap_stratified_by_test_set':True,'analysis_runs':0}
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    with base.run_lock(out):
        frozen_sha=base.freeze_or_verify(out,frozen,args.resume)
        if args.prepare_only:print(json.dumps({'status':'frozen','frozen_sha256':frozen_sha,'gold_sha256':GOLD_SHA,'nominal':581,'http_cap':CAP}),flush=True);return
        provider=transport.Provider(config,out/'requests',CAP,minimum_interval=2.,authorized_max_requests=CAP)
        try:
            predictions={}
            for arm in ARMS:
                phase={};started=time.monotonic()
                def one(item):
                    assert base.sha256(ROOT/'evaluation/condition_gold/gold_test_v2.json')==GOLD_SHA
                    for name,sha in frozen['code_sha256'].items():assert base.sha256(ROOT/name)==sha,('Frozen evaluation source changed',name)
                    path=out/'checkpoints'/f'{arm}_{item["id"]}.json'
                    if path.exists():
                        saved=json.loads(path.read_text(encoding='utf-8'));assert saved['frozen_sha256']==frozen_sha;return saved['prediction']
                    pred=old.predict_one(c,item,texts,gold['slots'],vocab,arm,provider)
                    base.save_json(path,{'frozen_sha256':frozen_sha,'prediction':pred});return pred
                with ThreadPoolExecutor(max_workers=args.workers) as pool:
                    futures=[pool.submit(one,item) for item in gold['items']]
                    for done,future in enumerate(as_completed(futures),1):
                        pred=future.result();phase[pred['id']]=pred;print(f'{arm}: {done}/83; HTTP={provider.stats()["http_attempts"]}',flush=True)
                predictions[arm]=[phase[i['id']] for i in gold['items']]
                base.save_json(out/f'predictions_{arm}.json',predictions[arm]);base.save_json(out/f'phase_{arm}.json',{'elapsed_seconds_this_execution':time.monotonic()-started,'completed_utc':datetime.now(timezone.utc).isoformat(),'usage':provider.stats(arm)})
            base.write_csv(out/'call_usage.csv',old.usage_rows(provider));base.save_json(out/'usage.json',provider.stats())
            failures=[{'arm':a,'id':p['id'],'sampling':p.get('sampling')} for a,ps in predictions.items() for p in ps if p.get('sampling',{}).get('interface_failures') or p.get('sampling',{}).get('unavailable_positions')]
            base.save_json(out/'interface_failures.json',failures)
            write_reports(c,out,gold,previous,predictions)
            base.save_json(out/'run_status.json',{'status':'completed','gold_sha256':GOLD_SHA,'frozen_sha256':frozen_sha,'usage':provider.stats(),'analysis_runs':0,'preprocessing_submissions':0,'held_out_processed':False})
            print(json.dumps({'status':'completed','usage':provider.stats()}),flush=True)
        finally:provider.close()


if __name__=='__main__':main()