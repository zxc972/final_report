
"""Complete only budget-omitted answers after explicit cumulative authorisation."""
from pathlib import Path
from datetime import datetime,timezone
import os,sys,json,hashlib,subprocess,shutil,time,traceback
ROOT=Path('/data/xuancheng/agent_v1/round16_source');OUT=ROOT/'results/condition_canon_draft_v1';WORK=Path('/data/xuancheng/agent_v1/round16_work')
sys.path.insert(0,str(ROOT))
from tools.knowledge import run_condition_canonicalization as run,provider_llm
PYTHON='/data/xuancheng/agent_v1/.venv-coding/bin/python'
def read(p):return json.loads(Path(p).read_text())
def events(p):return [json.loads(x) for x in Path(p).read_text().splitlines()] if Path(p).exists() else []
def starts(es):return [e for e in es if e['event']=='start']
def alive(pid):
 try:return (Path('/proc')/str(pid)/'stat').read_text().split()[2]!='Z'
 except FileNotFoundError:return False
approval=read(OUT/'budget_authorization.json');assert approval['cumulative_http_attempt_cap']==1000
pid=read(WORK/'draft_resume2_dispatch.json')['pid']
print('Waiting for primary phase to finish; cumulative authorised cap=1000',flush=True)
while alive(pid):time.sleep(15)
status=read(OUT/'run_status.json');assert status['status'].startswith('completed'),status['status']
c=run.load_canon();frozen=read(OUT/'frozen.json');gold=read(ROOT/'evaluation/condition_gold/gold_draft_v1.json')
assert run.sha256(ROOT/'evaluation/condition_gold/gold_draft_v1.json')==frozen['gold_sha256']
for name,path in [('canonicalizer',ROOT/'agent/modules/agent/backend/analysis_condition_canonicalizer.py'),('runner',ROOT/'tools/knowledge/run_condition_canonicalization.py'),('provider',ROOT/'tools/knowledge/provider_llm.py')]:assert run.sha256(path)==frozen['code_sha256'][name]
archive=OUT/'primary_800';archive.mkdir(exist_ok=True)
for name in ['summary.json','usage.json','run_status.json','provider_failures.json','REPORT.md','frozen.json']+[f'predictions_{a}.json' for a in ['full','k1','retrieval_only','direct']]:
 dest=archive/name
 if not dest.exists():shutil.copyfile(OUT/name,dest)
ledger=OUT/'requests/calls.jsonl';raw=ledger.read_bytes();initial_meta=archive/'ledger_prefix.json'
if not initial_meta.exists():run.save_json(initial_meta,{'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'attempts':len(starts(events(ledger)))})
primary_meta=read(initial_meta);assert primary_meta['attempts']<=800
assert hashlib.sha256(raw[:primary_meta['bytes']]).hexdigest()==primary_meta['sha256']
base_events=[json.loads(line) for line in raw[:primary_meta['bytes']].splitlines()]
base_starts=starts(base_events);base_ends={e['request_id']:e for e in base_events if e['event']=='end'}
all_preds={a:read(archive/f'predictions_{a}.json') for a in ['full','k1','retrieval_only','direct']}
initial={a:json.loads(json.dumps(p)) for a,p in all_preds.items()}
pending={}
for arm,preds in all_preds.items():
 rows=[]
 for item,pred in zip(gold['items'],preds):
  if pred.get('decision')!='provider_error' or 'budget' not in pred.get('error_summary','').lower():continue
  assert arm in {'k1','direct'},'A multi-sample item must not be resampled'
  logical=f"{arm}:{item['id']}:1"
  received=[base_ends[s['request_id']] for s in base_starts if s['logical_id']==logical and s['request_id'] in base_ends]
  assert not any(e.get('status')=='ok' or e.get('status')=='invalid_response' and e.get('finish_reason')=='length' for e in received)
  rows.append(item)
 if rows:pending[arm]=rows
print('Budget-omitted items', {a:len(v) for a,v in pending.items()},flush=True)
completion=OUT/'budget_completion';completion.mkdir(exist_ok=True)
manifest={'schema':'primatex.condition_canon_budget_completion.v1','user_authorisation':approval,'original_frozen_sha256':run.sha256(OUT/'frozen.json'),'original_gold_sha256':frozen['gold_sha256'],'primary_ledger_prefix':primary_meta,'algorithm_prompts_parameters_sampling_unchanged':True,'runs':[],'preserved_predictions':{}}
for arm,preds in initial.items():
 ids={i['id'] for i in pending.get(arm,[])}
 manifest['preserved_predictions'][arm]={str(p['id']):hashlib.sha256(json.dumps(p,sort_keys=True).encode()).hexdigest() for p in preds if p['id'] not in ids}
env=os.environ.copy();env.update(PYTHONDONTWRITEBYTECODE='1',LANGSMITH_TRACING='false',LANGCHAIN_TRACING_V2='false')
used=0
for arm,items in pending.items():
 subset=completion/f'gold_draft_budget_subset_{arm}.json'
 data={**gold,'items':items,'subset_of_sha256':frozen['gold_sha256'],'subset_reason':'Only original budget-exhausted answers; no label edited'}
 if subset.exists():assert read(subset)==data
 else:run.save_json(subset,data)
 folder=completion/arm
 remaining=1000-primary_meta['attempts']-used
 if (folder/'frozen.json').exists():cap=read(folder/'frozen.json')['max_http_attempts']
 else:cap=remaining
 assert 1<=cap<=200 and cap<=remaining
 command=[PYTHON,'-u','tools/knowledge/run_condition_canonicalization.py','--gold',str(subset),'--llm','tools.knowledge.provider_llm:complete','--provider-config','/data/xuancheng/agent_v1/.env','--arms',arm,'--out',str(folder),'--max-requests',str(cap)]
 if not (folder/'frozen.json').exists():subprocess.run(command+['--prepare-only'],cwd=ROOT,env=env,check=True)
 run.save_json(OUT/'completion_phase_status.json',{'status':'running','arm':arm,'items':len(items),'cap':cap,'cumulative_cap':1000})
 if not (folder/'run_status.json').exists() or not read(folder/'run_status.json')['status'].startswith('completed'):
  subprocess.run(command+['--resume'],cwd=ROOT,env=env,check=True)
 sub_events=events(folder/'requests/calls.jsonl');count=len(starts(sub_events));assert count<=cap
 used+=count;assert primary_meta['attempts']+used<=1000
 results=read(folder/f'predictions_{arm}.json');assert [p['id'] for p in results]==[i['id'] for i in items]
 replacement={p['id']:p for p in results};all_preds[arm]=[replacement.get(p['id'],p) for p in all_preds[arm]]
 manifest['runs'].append({'arm':arm,'items':[i['id'] for i in items],'out':str(folder.relative_to(OUT)),'max_http_attempts':cap,'actual_http_attempts':count,'frozen_sha256':run.sha256(folder/'frozen.json'),'ledger_sha256':run.sha256(folder/'requests/calls.jsonl')})
# All sampled answers and empty answers from the first phase remain identical.
for arm,protected in manifest['preserved_predictions'].items():
 for pred in all_preds[arm]:
  if str(pred['id']) in protected:assert hashlib.sha256(json.dumps(pred,sort_keys=True).encode()).hexdigest()==protected[str(pred['id'])]
existing={(e['event'],e.get('request_id')) for e in events(ledger)}
offset=primary_meta['attempts']
with ledger.open('a',encoding='utf-8') as stream:
 for info in manifest['runs']:
  for event in events(OUT/info['out']/'requests/calls.jsonl'):
   key=(event['event'],event.get('request_id'))
   if key in existing:continue
   event={**event,'phase':'budget_completion/'+info['arm']}
   if event['event']=='start':event['phase_ordinal']=event['ordinal'];event['ordinal']=offset+event['ordinal']
   stream.write(json.dumps(event,ensure_ascii=False)+'\n');existing.add(key)
  offset+=info['actual_http_attempts']
 stream.flush();os.fsync(stream.fileno())
assert len(starts(events(ledger)))<=1000
stats=provider_llm.Provider(provider_llm.load_config('/data/xuancheng/agent_v1/.env',model='deepseek-v4.1-flash'),OUT/'requests',max_requests=800)
summary={};old_summary=read(archive/'summary.json')
for arm,preds in all_preds.items():
 run.save_json(OUT/f'predictions_{arm}.json',preds)
 run.save_json(OUT/f'review_queue_{arm}.json',[{'item':i,'prediction':p} for i,p in zip(gold['items'],preds) if p['decision']=='review'])
 merged=[]
 for method in sorted({i['method'] for i in gold['items']}):merged+=c.merge([p for p in preds if p['method']==method and p.get('parameters') is not None],method)
 run.save_json(OUT/f'merged_{arm}.json',merged)
 metrics=run.score_with_details(c,gold['items'],preds);metrics['usage']=stats.stats(arm);metrics['elapsed_seconds']=old_summary[arm]['elapsed_seconds']
 for info in manifest['runs']:
  if info['arm']==arm:metrics['elapsed_seconds']+=read(OUT/info['out']/'summary.json')[arm]['elapsed_seconds']
 summary[arm]=metrics
run.save_json(OUT/'summary.json',summary)
run.write_reports(c,OUT,gold,all_preds,summary,stats,run.sha256(OUT/'frozen.json'))
report=OUT/'REPORT.md';text=report.read_text();text=text.replace('共享的 800 请求上限','授权的累计 1000 请求上限（原批次 800，补跑最多 200）');report.write_text(text)
combined=read(OUT/'run_status.json');combined.update(authorised_cumulative_http_cap=1000,primary_http_cap=800,budget_completion_http_cap=200,budget_completion_items=sum(len(v) for v in pending.values()),budget_completion_http_attempts=used,all_existing_answers_preserved=True)
run.save_json(OUT/'run_status.json',combined)
manifest.update(status='completed',completed_at=datetime.now(timezone.utc).isoformat(),primary_attempts=primary_meta['attempts'],completion_attempts=used,combined_attempts=stats.stats()['http_attempts'])
run.save_json(OUT/'budget_completion_manifest.json',manifest);run.save_json(OUT/'completion_phase_status.json',{'status':'completed','items':sum(len(v) for v in pending.values()),'combined_http_attempts':stats.stats()['http_attempts'],'cumulative_cap':1000})
stats.close()
print('COMBINED_COMPLETED',json.dumps({'completed_items':sum(len(v) for v in pending.values()),'completion_attempts':used,'combined_attempts':manifest['combined_attempts']}),flush=True)
