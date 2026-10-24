"""Preregistered recoverable-state supplement; preserves the unfiltered primary run.
Eligibility is proved by exhaustive forward closure, not the AND-OR solver.
All sampled missing sets are screened by that reachability definition. This
conditional panel tests optimality on feasible states and cannot estimate their
frequency in nature. No backend algorithm or original experiment is modified.
"""
import argparse,copy,hashlib,json,random
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import run_matching_planning_experiments as e

def main():
 a=argparse.ArgumentParser();a.add_argument('--out',type=Path,required=True);args=a.parse_args();out=args.out;out.mkdir(parents=True,exist_ok=False)
 c,p=e.modules();k=e.ROOT/'agent/modules/agent/knowledge_analysis';types=json.loads((k/'product_types.json').read_text());h=c.TypeHierarchy.from_document(types);steps=p.steps_from_workflow(json.loads((k/'workflow_steps.json').read_text()))
 for s in steps:s['cost']=1
 software={x:True for s in steps for x in s['software']};ids={s['id'] for s in steps};population,_=e.planning_population(steps,h)
 closure=p._forward(ids,population,steps,h,software);population=[dict(x,id='pool_'+str(i)) for i,x in enumerate(closure)]
 unique=[x for x in population if not p.satisfied({'type':x['type'],'attrs':x['attrs']},[y for y in population if y['id']!=x['id']],h)]
 eligible=[]
 for x in unique:
  remain=[y for y in population if y['id']!=x['id']]
  if p.satisfied({'type':x['type'],'attrs':x['attrs']},p._forward(ids,remain,steps,h,software),h):eligible.append(x)
 assert len(eligible)>=5
 protocol={'seed':20261025,'missing_counts':[1,2,3,4,5],'per_count':50,'workers':4,'timeout_seconds':30,'workflow_steps':len(steps),'population_count':len(population),'recoverable_single_deletion_candidates':len(eligible),'conditional_sampling':'Uniform missing sets from single-deletion recoverable products, accept only if full forward closure can recover all; not filtered by AND-OR or oracle outputs','selection_bias_disclosed':'Feasible-only supplementary panel, not a feasibility-prevalence estimate','primary_unfiltered_run_retained':'round24_v1','model_calls':0,'source_sha256':{f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in e.BACKEND.glob('analysis_*planner.py')},'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
 e.save(out/'protocol.json',protocol);rng=random.Random(protocol['seed']);cases=[];rejected={}
 for n in range(1,6):
  rejected[n]=0
  for i in range(50):
   for attempt in range(10000):
    seed=rng.randrange(2**32);chosen=random.Random(seed).sample(eligible,n);removed={x['id'] for x in chosen};products=[x for x in population if x['id'] not in removed];targets=[{'type':x['type'],'attrs':x['attrs']} for x in chosen]
    assert all(not p.satisfied(t,products,h) for t in targets)
    f=p._forward(ids,products,steps,h,software)
    if all(p.satisfied(t,f,h) for t in targets):break
    rejected[n]+=1
   else:raise ValueError('Recoverable-set generator exhausted')
   cases.append({'id':f'FEASIBLE_{n}_{i:03d}','seed':seed,'missing_count':n,'removed_ids':sorted(removed),'targets':targets,'products':products,'forward_reachability_certificate':True})
 e.save(out/'planning_instances.json',cases);e.save(out/'input_freeze.json',{'frozen_before_algorithms':True,'protocol_sha256':hashlib.sha256((out/'protocol.json').read_bytes()).hexdigest(),'instances_sha256':hashlib.sha256((out/'planning_instances.json').read_bytes()).hexdigest(),'rejected_unreachable_sets':rejected})
 rows=[]
 with ProcessPoolExecutor(max_workers=4) as executor:
  futures={executor.submit(e.planning_one,(x,steps,types,30)):x['id'] for x in cases}
  for future in as_completed(futures):
   result=future.result();rows.extend(result)
   with (out/'progress.jsonl').open('a') as f:f.write(json.dumps({'case':futures[future],'done':len(rows)//4})+'\n')
 rows.sort(key=lambda x:(x['case'],x['method']));e.save(out/'results.json',rows);e.csvout(out/'planning_results.csv',rows);summary=e.summarize(rows,['missing_count','method']);e.save(out/'summary.json',{'planning':summary,'model_calls':0,'planning_instances':len(cases)});e.csvout(out/'planning_summary.csv',summary)
 assert protocol['source_sha256']=={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in e.BACKEND.glob('analysis_*planner.py')}
 e.save(out/'completed.json',{'source_unchanged':True,'model_calls':0,'instances':len(cases),'result_rows':len(rows)})
if __name__=='__main__':main()
