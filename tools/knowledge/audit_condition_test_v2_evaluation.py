"""Offline v2/combined audit: replay prompts/results, independent NumPy CIs and SciPy exact tests."""
from pathlib import Path
import argparse,hashlib,json,math,sys
parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);parser.add_argument('--out',type=Path,required=True);parser.add_argument('--provider-config',required=True)
args=parser.parse_args();ROOT=args.root.resolve();out=args.out.resolve();sys.path.insert(0,str(ROOT))
from tools.knowledge import run_condition_test_v2_evaluation as run
from tools.knowledge import condition_evaluation_statistics as statistics
from tools.knowledge.audit_condition_test_evaluation import ReadOnlyReplay
base,v2,transport=run.base,run.v2,run.transport
def verify_intervals_independently(c, items, predictions, expected, strata=None):
    """NumPy confusion arrays/key sets, independent of the original score function."""
    import numpy as np
    import random
    prepared = {}
    for arm, preds in predictions.items():
        prepared[arm] = {
            "gold": np.array([i["gold_template"] != "advisory" for i in items]),
            "pred": np.array([p.get("decision") == "accepted" and p.get("template") != "advisory" for p in preds]),
            "template": np.array([i["gold_template"] == p.get("template") for i, p in zip(items, preds)]),
            "review": np.array([p.get("decision") == "review" for p in preds]),
            "gold_keys": [(i["method"], c.canonical_key(i["gold_template"], i["gold_parameters"] or {})) if i["gold_template"] != "advisory" else None for i in items],
            "pred_keys": [(i["method"], c.canonical_key(p["template"], p["parameters"])) if p.get("decision") == "accepted" and p.get("parameters") is not None and p.get("template") != "advisory" else None for i, p in zip(items, preds)],
        }
    def three(tp, fp, fn):
        precision = tp / (tp + fp) if tp + fp else 0.
        recall = tp / (tp + fn) if tp + fn else 0.
        return [precision, recall, 2 * precision * recall / (precision + recall) if precision + recall else 0.]
    def calculate(data, indices):
        g, p = data["gold"][indices], data["pred"][indices]
        tp, fp, fn, tn = [int(x.sum()) for x in [g & p, ~g & p, g & ~p, ~g & ~p]]
        gk = {data["gold_keys"][j] for j in indices} - {None}
        pk = {data["pred_keys"][j] for j in indices} - {None}
        ktp = len(gk & pk)
        return [float(data["template"][indices].mean()), *three(tp, fp, fn),
                *three(tn, fn, fp), *three(ktp, len(pk) - ktp, len(gk) - ktp),
                int(data["review"][indices].sum())]
    seed, reps = expected["seed"], expected["replicates"]
    rng = random.Random(seed)
    if strata is None:
        draws = [rng.choices(range(len(items)), k=len(items)) for _ in range(reps)]
    else:
        groups={s:[i for i,v in enumerate(strata) if v==s] for s in dict.fromkeys(strata)}
        draws=[[j for group in groups.values() for j in rng.choices(group,k=len(group))] for _ in range(reps)]
        assert all(all(sum(strata[j]==s for j in draw)==len(group) for s,group in groups.items()) for draw in draws)
    for arm, data in prepared.items():
        estimates = calculate(data, list(range(len(items))))
        distribution = np.array([calculate(data, sample) for sample in draws])
        low, high = np.quantile(distribution, [.025, .975], axis=0, method="linear")
        for j, metric in enumerate(statistics.METRICS):
            ci = expected["arms"][arm]["intervals_95"][metric]
            assert np.allclose([ci["estimate"], ci["low"], ci["high"]],
                               [estimates[j], low[j], high[j]], rtol=1e-12, atol=1e-12), (arm, metric)
    return len(prepared) * len(statistics.METRICS)

def main():
 frozen=json.loads((out/'frozen.json').read_text());digest=base.sha256(out/'frozen.json');assert (out/'frozen.sha256').read_text().strip()==digest
 assert frozen['gold_sha256']==run.GOLD_SHA and frozen['shared_http_cap']==1500
 for name,expected in {**frozen['code_sha256'],**frozen['source_sha256']}.items():assert base.sha256(ROOT/name)==expected,name
 olddir=ROOT/'results/condition_canon_test_v1'
 for a,expected in frozen['historical_prediction_sha256'].items():assert base.sha256(olddir/f'predictions_{a}.json')==expected
 gold=run.verify_gold(ROOT);v1=run.old.verify_gold();c=base.load_canon();vocab,vocab_sha=v2.load_vocab()
 assert vocab==frozen['vocabulary'] and vocab_sha==frozen['vocabulary_sha256']
 for name,value in frozen['parameters'].items():assert getattr(c,name)==value
 events=[json.loads(line) for line in (out/'requests/calls.jsonl').read_text().splitlines()]
 starts=[e for e in events if e['event']=='start'];ends={e['request_id']:e for e in events if e['event']=='end'}
 assert len(starts)<=1500 and len(starts)==len(ends)
 assert {s['request_id'] for s in starts}==set(ends) and [s['ordinal'] for s in starts]==list(range(1,len(starts)+1))
 assert all(s['arm'] in set(run.ARMS)-{'retrieval_only'} and s['settings']==frozen['provider'] for s in starts)
 predictions={a:json.loads((out/f'predictions_{a}.json').read_text()) for a in run.ARMS}
 previous={a:json.loads((olddir/f'predictions_{a}.json').read_text()) for a in run.ARMS}
 failures={f"{a}:{p['id']}:{f['sample']}":f['error_summary'] for a,ps in predictions.items() for p in ps for f in p.get('sampling',{}).get('interface_failures',[])}
 replay=ReadOnlyReplay(events,failures);texts={m:base.sources(ROOT/'evaluation/condition_test_v2/method_extractions',m) for m in {i['method'] for i in gold['items']}}
 checked=0
 for a,ps in predictions.items():
  for item,pred in zip(gold['items'],ps):
   assert item['id']==pred['id']
   assert run.old.predict_one(c,item,texts,gold['slots'],vocab,a,replay)==pred,(a,item['id']);checked+=1
 byid={i['id']:i for i in gold['items']}
 for start in starts:
  item=byid[start['item_id']];prompt=v2.prompt_for(c,item,gold['slots'],vocab,direct=start['arm']=='direct_v2')
  assert hashlib.sha256(prompt.encode()).hexdigest()==start['prompt_sha256']
  stripped={k:v for k,v in item.items() if not k.startswith('gold_') and k not in ['annotation_note','pending_user_decision']}
  assert v2.prompt_for(c,stripped,gold['slots'],vocab,direct=start['arm']=='direct_v2')==prompt
 combined_items=v1['items']+gold['items'];combined={a:previous[a]+predictions[a] for a in run.ARMS};strata=['v1']*45+['v2']*83
 nonpending=[j for j,i in enumerate(gold['items']) if not i['pending_user_decision']]
 splits={'v2_83':(gold['items'],predictions,None),'v2_nonpending_76':([gold['items'][j] for j in nonpending],{a:[ps[j] for j in nonpending] for a,ps in predictions.items()},None),'combined_128':(combined_items,combined,strata)}
 for name,exclude in [('combined_exclude_v2_pending_121',set(run.PENDING)),('combined_exclude_all_pending_115',{i['id'] for i in combined_items if i['pending_user_decision']})]:
  indices=[j for j,i in enumerate(combined_items) if i['id'] not in exclude]
  splits[name]=([combined_items[j] for j in indices],{a:[ps[j] for j in indices] for a,ps in combined.items()},[strata[j] for j in indices])
 independent=0;paired=json.loads((out/'mcnemar.json').read_text());scipy_checks=0
 from scipy.stats import binomtest
 for name,(items,ps,st) in splits.items():
  expected=json.loads((out/f'metrics_{name}.json').read_text())
  observed=statistics.bootstrap(c,items,ps) if st is None else run.stratified_bootstrap(c,items,ps,st)
  observed['gold_class_counts']=dict(__import__('collections').Counter('advisory' if i['gold_template']=='advisory' else 'executable' for i in items))
  assert observed==expected,name
  independent+=verify_intervals_independently(c,items,ps,expected,st)
  assert paired[name]==statistics.paired_comparisons(c,items,ps)
  for value in paired[name].values():
   p=binomtest(value['first_only_correct'],value['discordant'],p=.5).pvalue if value['discordant'] else 1.
   assert math.isclose(p,value['p_exact_two_sided'],rel_tol=1e-12);scipy_checks+=1
 assert statistics.full_errors(c,gold['items'],predictions['full_v2'])==json.loads((out/'errors_full_v2.json').read_text())
 config=transport.load_config(args.provider_config)
 for folder in [out,ROOT/'evaluation/condition_gold']:
  for path in folder.rglob('*'):
   if path.is_file():assert config.api_key.encode() not in path.read_bytes(),'Configured secret matched publication'
 result={'status':'audited','frozen_sha256':digest,'gold_sha256':run.GOLD_SHA,'predictions_replayed_without_http':checked,'prompt_hashes_and_no_gold_leakage_checks':len(starts),'test_v1_predictions_unchanged':True,'all_five_bootstraps_reproduced':True,'combined_sampling_stratified_by_test_set':True,'independent_numpy_CI_crosschecks':independent,'scipy_exact_binomial_crosschecks':scipy_checks,'http_attempts':len(starts),'http_cap':1500,'unfinished_requests':0,'new_http_calls_in_audit':0,'secret_scan_matches':0,'raw_ledger_sha256':base.sha256(out/'requests/calls.jsonl')}
 base.save_json(out/'audit.json',result);print(json.dumps(result),flush=True)
if __name__=='__main__':main()
