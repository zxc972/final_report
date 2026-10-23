
"""Read-only audit of the frozen draft condition run. No provider calls."""
from pathlib import Path
import json, hashlib, importlib.util, sys
from collections import Counter
ROOT=Path('/data/xuancheng/agent_v1/round16_source')
OUT=ROOT/'results/condition_canon_draft_v1'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
f=read(OUT/'frozen.json')
assert sha(OUT/'frozen.json')==(OUT/'frozen.sha256').read_text().strip()
for name,path in [('canonicalizer',ROOT/'agent/modules/agent/backend/analysis_condition_canonicalizer.py'),('runner',ROOT/'tools/knowledge/run_condition_canonicalization.py'),('provider',ROOT/'tools/knowledge/provider_llm.py')]:assert sha(path)==f['code_sha256'][name]
assert sha(ROOT/'evaluation/condition_gold/gold_draft_v1.json')==f['gold_sha256']
for name,digest in f['source_sha256'].items():assert sha(ROOT/'knowledge/method_extractions'/name)==digest
assert f['parameters']=={'RHO_MIN':.9,'TOP_K':3,'SAMPLES':5,'LAMBDA':.3,'TAU':.6,'DELTA':.2}
gold=read(ROOT/'evaluation/condition_gold/gold_draft_v1.json');items=gold['items'];assert len(items)==108
raw=(OUT/'requests/calls.jsonl').read_bytes();events=[json.loads(line) for line in raw.splitlines()]
starts=[e for e in events if e['event']=='start'];end_list=[e for e in events if e['event']=='end'];ends={e['request_id']:e for e in end_list}
assert len(ends)==len(end_list)
approval=read(OUT/'budget_authorization.json');assert approval['cumulative_http_attempt_cap']==1000
assert len(starts)<=1000 and len({e['ordinal'] for e in starts})==len(starts)
budget=read(OUT/'budget_completion_manifest.json');assert budget['status']=='completed' and budget['primary_attempts']<=800 and budget['completion_attempts']<=200
for arm,protected in budget['preserved_predictions'].items():
 for pred in read(OUT/f'predictions_{arm}.json'):
  if str(pred['id']) in protected:assert hashlib.sha256(json.dumps(pred,sort_keys=True).encode()).hexdigest()==protected[str(pred['id'])]
assert all(e['model']=='deepseek-v4.1-flash' and e['temperature']==.7 for e in starts)
assert all(e['arm'] in {'full','k1','direct'} and e['item_id'] in {i['id'] for i in items} for e in starts)
assert all(1<=e['sample']<= (5 if e['arm']=='full' else 1) for e in starts)
assert all(e['request_id'] in {s['request_id'] for s in starts} for e in end_list)
for s in starts:
 if s['request_id'] in ends:
  e=ends[s['request_id']]
  for key in ['logical_id','arm','item_id','sample','attempt']:assert e[key]==s[key]
  for key in ['input_tokens','output_tokens','total_tokens']:assert e[key] is None or isinstance(e[key],int) and e[key]>=0
# The two implementation repairs preserve raw ledger prefixes and old predictions.
h=read(OUT/'freeze_history/transport_fix.json')
assert hashlib.sha256(raw[:h['initial_ledger_prefix_bytes']]).hexdigest()==h['initial_ledger_prefix_sha256']
for old in h['predictions_retained']:
 current=read(OUT/'checkpoints'/old['checkpoint'])['prediction']
 assert hashlib.sha256(json.dumps(current,sort_keys=True).encode()).hexdigest()==old['prediction_sha256']
h2=read(OUT/'freeze_history/failure_isolation.json')
assert hashlib.sha256(raw[:h2['ledger_prefix_bytes']]).hexdigest()==h2['ledger_prefix_sha256']
summary=read(OUT/'summary.json')
assert set(summary)=={'full','k1','retrieval_only','direct'}
spec=importlib.util.spec_from_file_location('audit_canon',ROOT/'agent/modules/agent/backend/analysis_condition_canonicalizer.py');c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
# Regenerate every prompt from the frozen statements and schema, excluding gold labels.
by_id={item['id']:item for item in items};prompt_hashes={}
for start in starts:
 cache_key=(start['arm'],start['item_id'])
 if cache_key not in prompt_hashes:
  item=by_id[start['item_id']]
  names=list(c.TEMPLATES) if start['arm']=='direct' else [name for name,_ in c.Retriever().rank(item['statement']+' '+item['quote']) if name!='advisory']
  prompt=c.build_prompt(item['statement'],item['quote'],names,gold['slots'])
  prompt_hashes[cache_key]=hashlib.sha256(prompt.encode()).hexdigest()
 assert start['prompt_sha256']==prompt_hashes[cache_key]
independent={}
for arm in ['full','k1','retrieval_only','direct']:
 preds=read(OUT/f'predictions_{arm}.json');assert len(preds)==108
 assert [p['id'] for p in preds]==[i['id'] for i in items]
 correct=sum(p.get('template')==i['gold_template'] for i,p in zip(items,preds))
 tp=fp=fn=tn=0
 for i,p in zip(items,preds):
  g=i['gold_template']!='advisory';q=p.get('decision')=='accepted' and p.get('template')!='advisory'
  tp+=bool(g and q);fp+=bool(not g and q);fn+=bool(g and not q);tn+=bool(not g and not q)
 assert summary[arm]['template_accuracy']==correct/108
 for name,value in [('tp',tp),('fp',fp),('fn',fn)]:assert summary[arm]['executable'][name]==value
 gk={(i['method'],c.canonical_key(i['gold_template'],i['gold_parameters'] or {})) for i in items if i['gold_template']!='advisory'}
 pk={(i['method'],c.canonical_key(p['template'],p['parameters'])) for i,p in zip(items,preds) if p.get('decision')=='accepted' and p.get('template')!='advisory' and p.get('parameters') is not None}
 assert summary[arm]['key']['tp']==len(gk&pk)
 assert summary[arm]['key']['fp']==len(pk-gk) and summary[arm]['key']['fn']==len(gk-pk)
 assert summary[arm]['review_queue']==sum(p['decision']=='review' for p in preds)
 independent[arm]={'template_correct':correct,'n':108,'executable_confusion':{'tp':tp,'fp':fp,'fn':fn,'tn':tn},'gold_keys':len(gk),'predicted_keys':len(pk),'correct_keys':len(gk&pk),'decisions':dict(Counter(p['decision'] for p in preds))}
u=read(OUT/'usage.json')
assert u['http_attempts']==len(starts)
for key in ['input_tokens','output_tokens','total_tokens']:assert u[key]==sum(e.get(key) or 0 for e in end_list)
assert u['unfinished_requests']==len(starts)-len(ends)
# Only inspect credential equality in memory; never display a credential.
secret=None
for line in Path('/data/xuancheng/agent_v1/.env').read_text().splitlines():
 if line.startswith('PLATFORM_API_KEY='):secret=line.split('=',1)[1].strip().strip('"\'')
assert secret
scanned=0
for p in OUT.rglob('*'):
 if p.is_file():assert secret.encode() not in p.read_bytes(),str(p.relative_to(OUT));scanned+=1
mapping=read('/data/xuancheng/agent_v1/audit/protected_source_mapping.json')
matched=sum((ROOT/e['path']).is_file() and sha(ROOT/e['path'])==e['sha256'] for e in mapping['mapped'])
assert matched==len(mapping['mapped'])==100
report={'status':'audited','frozen_sha256':sha(OUT/'frozen.json'),'source_code_and_data_unchanged':True,'all_prompt_hashes_match_label_free_inputs':True,'algorithm_defaults_unchanged':True,'authorised_cumulative_http_cap':1000,'budget_completion':{'items':sum(len(info['items']) for info in budget['runs']),'attempts':budget['completion_attempts'],'all_existing_answers_preserved':True},'preserved_initial_ledger_prefix':True,'preserved_completed_predictions':True,'independent_scoring':independent,'usage':u,'protected':{'original':101,'mapped':100,'matched':100,'historically_unmapped':1},'secret_scan':{'files':scanned,'matches':0},'analysis_runs':0,'preprocessing_submissions':0,'deployments':0,'service_restarts':0,'held_out_processed':0,'formal_gold_created':False,'artifact_sha256':{name:sha(OUT/name) for name in ['summary.json','summary.csv','usage.json','full_errors.json','provider_failures.json']}}
(OUT/'audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'audit':'passed','requests':len(starts),'unfinished':u['unfinished_requests'],'unknown_usage':u['unknown_usage_requests'],'protected_match':matched,'secret_matches':0},indent=2))
