import collections,copy,hashlib,json,math,statistics,sys
from pathlib import Path
REPO=Path(__file__).resolve().parents[3];sys.path.insert(0,str(REPO/'tools/knowledge'))
import run_matching_planning_experiments as e
ROOT=REPO/'evaluation/matching_planning';c,p=e.modules();know=REPO/'agent/modules/agent/knowledge_analysis';types=json.loads((know/'product_types.json').read_text());hierarchy=c.TypeHierarchy.from_document(types);steps=p.steps_from_workflow(json.loads((know/'workflow_steps.json').read_text()))
for s in steps:s['cost']=1
software={x:True for s in steps for x in s['software']}
def solutions(row):return {tuple(sorted(x.items())) for x in row['solutions']}
def h(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def audit(name):
 folder=ROOT/name;freeze=json.loads((folder/'input_freeze.json').read_text());proto=json.loads((folder/'protocol.json').read_text());rows=json.loads((folder/'results.json').read_text());assert h(folder/'protocol.json')==freeze['protocol_sha256']
 assert h(folder/'planning_instances.json')==freeze.get('planning_instances_sha256',freeze.get('instances_sha256'))
 if 'csp_instances_sha256' in freeze:assert h(folder/'csp_instances.json')==freeze['csp_instances_sha256']
 for stem,sha in proto['source_sha256'].items():
  f=e.BACKEND/stem
  if not f.exists():f=e.BACKEND/(stem+'.py')
  assert h(f)==sha,(f,h(f),sha)
 cases=json.loads((folder/'planning_instances.json').read_text());bycase={x['id']:x for x in cases};replay=0;incorrect=[];seen=collections.defaultdict(dict)
 for row in rows:
  if row['algorithm']!='ANDOR':continue
  seen[row['case']][row['method']]=row
  if row['status']!='completed' or row['feasible'] is not True:continue
  case=bycase[row['case']];available=p._forward(set(row['steps']),case['products'],steps,hierarchy,software)
  assert all(p.satisfied(t,available,hierarchy) for t in case['targets']),row['case'];replay+=1
  assert row['step_count']==len(set(row['steps']))
 for key,r in seen.items():
  a,b=r['optimal_plan'],r['optimal_plan_goal_closure'];assert a['status']==b['status']=='completed';assert a['feasible']==b['feasible']
  if a['feasible']:assert a['step_count']==b['step_count']
  if r['andor']['feasible']!=a['feasible']:
   case=bycase[key];actual=p.plan(case['targets'],case['products'],steps,hierarchy,software);assert actual['feasible'] is False
   incorrect.append({'case':key,'missing_count':case['missing_count'],'targets':case['targets'],'exact_steps':a['steps'],'exact_cost':a['cost'],'andor_reason_chains':actual.get('per_target',[])})
 result={'protocol_and_input_hashes_match':True,'source_algorithms_unchanged':True,'verified_feasible_step_replays':replay,'full_reduced_exact_comparisons':len(seen),'full_reduced_exact_mismatches':0,'andor_false_infeasible':len(incorrect),'false_infeasible_by_missing_count':dict(collections.Counter(x['missing_count'] for x in incorrect)),'model_calls':0}
 if (folder/'csp_instances.json').exists():
  cases=json.loads((folder/'csp_instances.json').read_text());certificates=0
  for case in cases:
   if case['panel']!='stress':continue
   names=[x['name'] for x in case['slots']];graph={n:set() for n in names}
   for edge in case['constraints']:
    if edge['severity']=='hard':
     assert set(edge['attrs'])=={'subject','mesh'}
     a,b=edge['slots'];graph[a].add(b);graph[b].add(a)
   reached=set();todo=[names[0]]
   while todo:
    x=todo.pop()
    if x in reached:continue
    reached.add(x);todo.extend(graph[x]-reached)
   assert reached==set(names)
   # Slot-specific product types make domains disjoint; connected equality
   # forces a globally shared (subject,mesh) tuple.
   domains={slot['name']:[x for x in case['products'] if c.TypeHierarchy(case['types']).subsumes(slot['type'],x['type'])] for slot in case['slots']}
   common=set.intersection(*[{(x['attrs']['subject'],x['attrs']['mesh']) for x in d} for d in domains.values()])
   assert common=={('0','m0'),('1','m1')}
   for d in domains.values():assert all(sum((x['attrs']['subject'],x['attrs']['mesh'])==v for x in d)==1 for v in common)
   assert len(case['certificate'])==2;certificates+=1
  cs=collections.defaultdict(dict)
  for r in rows:
   if r['algorithm']=='CSP':cs[r['case']][r['method']]=r
  direct=0;cert=0;miss=total=0;false_negative=feasible_truth=0;by_panel=collections.defaultdict(lambda:{'lost':0,'truth':0,'feasible_truth':0,'false_negative':0})
  for case in cases:
   r=cs[case['id']];oracle=r['brute_force'];full=r['full'];assert full['status']=='completed' and not full['truncated']
   truth=solutions(oracle) if oracle['status']=='completed' else {tuple(sorted(x.items())) for x in case['certificate']}
   if oracle['status']=='completed':assert solutions(full)==truth;direct+=1
   if case['certificate'] is not None:
    assert solutions(full)=={tuple(sorted(x.items())) for x in case['certificate']};cert+=1
   for m in ('no_mrv','no_forward_checking'):
    if r[m]['status']=='completed':assert solutions(r[m])==truth and not r[m]['truncated']
   off=solutions(r['no_type_inclusion']);assert off<=truth
   lost=len(truth-off);miss+=lost;total+=len(truth);eligible=bool(truth);fn=eligible and not off;feasible_truth+=eligible;false_negative+=fn
   group=by_panel[case['panel']];group['lost']+=lost;group['truth']+=len(truth);group['feasible_truth']+=eligible;group['false_negative']+=fn
  result.update(csp_certificates_independently_proved=certificates,csp_full_vs_direct_brute_comparisons=direct,csp_full_vs_direct_brute_mismatches=0,csp_full_vs_certificate_comparisons=cert,csp_full_vs_certificate_mismatches=0,type_ablation={'lost_solutions':miss,'true_solutions':total,'weighted_missed_solution_rate':miss/total,'false_negative_feasible_cases':false_negative,'feasible_truth_cases':feasible_truth,'false_negative_feasibility_rate':false_negative/feasible_truth,'by_panel':dict(by_panel)})
 e.save(folder/'independent_audit.json',result);e.save(folder/'andor_false_infeasible_cases.json',incorrect);return result
all_={n:audit(n) for n in ('round24_v1','round24_feasible_v1')};e.save(ROOT/'round24_independent_audit.json',all_);print(json.dumps(all_,indent=2))
