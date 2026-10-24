"""Frozen, model-free experiments for the existing matching/planning algorithms.

The stress CSPs have two planted solutions and a connected equality graph.
An additional small random panel has exhaustive brute-force truth. Large
exhaustive timeouts are censored, never counted as agreement. No backend
algorithm file is written. Ablations remove only MRV or forward checking in
an isolated function body; the full solver and oracle keep their bytecode.
"""
from __future__ import annotations
import argparse,ast,builtins,copy,csv,hashlib,importlib.util,itertools,json,math
import os,platform,random,signal,statistics,sys,time,types
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BACKEND=ROOT/'agent/modules/agent/backend'
CSP=PLANNER=None


def modules():
    global CSP,PLANNER
    if CSP is None:
        package=types.ModuleType('_round24_algorithms');package.__path__=[str(BACKEND)]
        sys.modules[package.__name__]=package
        for stem in ['analysis_csp_matching','analysis_andor_planner']:
            name=package.__name__+'.'+stem
            spec=importlib.util.spec_from_file_location(name,BACKEND/(stem+'.py'))
            module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)
            if stem.endswith('csp_matching'):CSP=module
            else:PLANNER=module
    return CSP,PLANNER


def clean(value):
    if isinstance(value,float) and not math.isfinite(value):return None
    if isinstance(value,dict):return {str(k):clean(v) for k,v in value.items()}
    if isinstance(value,(tuple,list,set)):return [clean(v) for v in value]
    return value


def save(path,value):
    path.write_text(json.dumps(clean(value),ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')


def signature(value):return hashlib.sha256(json.dumps(clean(value),sort_keys=True,separators=(',',':')).encode()).hexdigest()


def csvout(path,rows):
    if not rows:return
    columns=list(dict.fromkeys(key for row in rows for key in row))
    with path.open('w',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=columns);writer.writeheader()
        for row in rows:writer.writerow({k:json.dumps(clean(v),ensure_ascii=False,sort_keys=True) if isinstance(v,(dict,list,tuple)) else clean(v) for k,v in row.items()})


class TimeLimit(Exception):pass


def timed(operation,seconds,counter=None):
    def expired(*args):raise TimeLimit('predeclared wall-time limit')
    previous=signal.signal(signal.SIGALRM,expired)
    started=time.perf_counter();cpu=time.process_time();result=None;status='completed';error=None;partial_stats={}
    signal.setitimer(signal.ITIMER_REAL,seconds)
    try:result=operation()
    except TimeLimit as exc:
        status='timeout';error=str(exc);frame=exc.__traceback__
        while frame:
            candidate=frame.tb_frame.f_locals.get('stats')
            if isinstance(candidate,dict) and {'nodes','pruned'}<=set(candidate):partial_stats=dict(candidate);break
            frame=frame.tb_next
    except Exception as exc:status='error';error=type(exc).__name__+': '+str(exc)[:300]
    finally:
        signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,previous)
    row={'status':status,'wall_seconds':time.perf_counter()-started,'cpu_seconds':time.process_time()-cpu,
         'timeout_seconds':seconds,'error':error,'constraint_evaluations':(counter or {}).get('checks'),
         'search_nodes':partial_stats.get('nodes',(counter or {}).get('nodes')),
         'pruned':partial_stats.get('pruned')}
    return row,result


def isolated_solver(kind,counter):
    import inspect
    csp,_=modules();environment=dict(csp.__dict__);original=csp._nary_status
    def counted(*args):counter['checks']+=1;return original(*args)
    environment['_nary_status']=counted
    if kind=='brute_force':
        original_import=builtins.__import__;custom=dict(vars(builtins))
        def product(*args):
            for item in itertools.product(*args):counter['nodes']+=1;yield item
        proxy=types.SimpleNamespace(product=product)
        def imports(name,*args,**kwargs):return proxy if name=='itertools' else original_import(name,*args,**kwargs)
        custom['__import__']=imports;environment['__builtins__']=custom
        return types.FunctionType(csp.brute_force.__code__,environment,csp.brute_force.__name__,csp.brute_force.__defaults__)
    if kind in {'full','no_type_inclusion'}:
        function=types.FunctionType(csp.solve.__code__,environment,csp.solve.__name__,csp.solve.__defaults__)
        assert function.__code__.co_code==csp.solve.__code__.co_code
        return function
    tree=ast.parse(inspect.getsource(csp.solve));edits=[]
    class Ablate(ast.NodeTransformer):
        def visit_Assign(self,node):
            if kind=='no_mrv' and any(isinstance(t,ast.Name) and t.id=='name' for t in node.targets) and isinstance(node.value,ast.Call) and isinstance(node.value.func,ast.Name) and node.value.func.id=='min':
                edits.append('MRV choice -> declared slot order');node.value=ast.Subscript(value=ast.Name(id='free',ctx=ast.Load()),slice=ast.Constant(value=0),ctx=ast.Load())
            return self.generic_visit(node)
        def visit_For(self,node):
            if kind=='no_forward_checking' and isinstance(node.target,ast.Name) and node.target.id=='other' and isinstance(node.iter,ast.Name) and node.iter.id=='free':
                edits.append('remove forward domain filtering loop');return None
            return self.generic_visit(node)
    tree=Ablate().visit(tree);ast.fix_missing_locations(tree);assert len(edits)==1,(kind,edits)
    exec(compile(tree,str(BACKEND/'analysis_csp_matching.py')+':'+kind,'exec'),environment)
    return environment['solve']


def solution_set(result,brute=False):
    if result is None:return set()
    rows=result if brute else result['solutions']
    return {tuple(sorted((k,str(v)) for k,v in (row if brute else row['assignment']).items())) for row in rows}


def csp_instance(seed,index,density,panel):
    rng=random.Random(seed);n=rng.randint(2,8) if panel=='stress' else rng.randint(2,4)
    counts=[rng.choice([5,10,25,50,100,200]) if panel=='stress' else rng.randint(5,9) for _ in range(n)]
    types_=[{'id':'type:Product'}]+[{'id':f'type:S{i}','parent':'type:Product'} for i in range(n)]+[{'id':f'type:S{i}.Derived','parent':f'type:S{i}'} for i in range(n)]
    slots=[{'name':f's{i}','type':f'type:S{i}','unary':[{'kind':'attr_present','attr':'subject'}]} for i in range(n)]
    products=[]
    for i,count in enumerate(counts):
        for j in range(count):
            common=str(j) if j<2 else f'private_{i}_{j}_{rng.randrange(10**9)}'
            attrs={'subject':common if panel=='stress' else str(rng.randrange(4)),
                   'mesh':('m'+common) if panel=='stress' and j<2 else ('m0' if panel=='correctness' else 'private'),
                   'hemisphere':'lh','space':rng.choice(['native','registered'])}
            specific=panel=='stress' and j==0 or rng.random()<.65
            products.append({'id':f'p{i}_{j}','type':f'type:S{i}'+('.Derived' if specific else ''),'attrs':attrs})
    order=list(range(n));rng.shuffle(order);edges=set()
    for i in range(1,n):edges.add(tuple(sorted((order[i],rng.choice(order[:i])))))
    extra={'sparse':0.,'medium':.4,'dense':.85}[density]
    for pair in itertools.combinations(range(n),2):
        if pair not in edges and rng.random()<extra:edges.add(pair)
    constraints=[{'kind':'attr_equal','severity':'hard','slots':[f's{i}',f's{j}'],'attrs':['subject','mesh']} for i,j in sorted(edges)]
    if n>1:constraints.append({'kind':'attr_equal','severity':'soft','slots':['s0',f's{n-1}'],'attrs':['space']})
    certificate=[{f's{i}':f'p{i}_{j}' for i in range(n)} for j in range(2)] if panel=='stress' else None
    return {'id':f'CSP_{panel}_{density}_{index:03d}','panel':panel,'density':density,'actual_hard_density':len(edges)/(n*(n-1)/2),
            'slots':slots,'products':products,'constraints':constraints,'types':types_,'domain_counts':counts,
            'cartesian_combinations':math.prod(counts),'certificate':certificate,'seed':seed}


def csp_one(arguments):
    problem,timeout=arguments;csp,_=modules();rows=[];sets={}
    names=['full','no_mrv','no_forward_checking','brute_force','no_type_inclusion']
    random.Random(problem['seed']+19).shuffle(names)
    for method in names:
        counter={'nodes':0,'checks':0};function=isolated_solver(method,counter)
        hierarchy=csp.TypeHierarchy(problem['types'])
        if method=='no_type_inclusion':
            hierarchy.subsumes=lambda general,specific:general==specific and specific in hierarchy.parent
        kwargs={} if method=='brute_force' else {'max_solutions':100000 if problem['panel']=='correctness' else 256}
        row,result=timed(lambda:function(problem['slots'],problem['products'],problem['constraints'],hierarchy,**kwargs),timeout,counter)
        found=solution_set(result,method=='brute_force');sets[method]=found
        if isinstance(result,dict):row.update(search_nodes=result['stats']['nodes'],pruned=result['stats']['pruned'])
        row.update(case=problem['id'],algorithm='CSP',method=method,panel=problem['panel'],density=problem['density'],slots=len(problem['slots']),
                   domains=problem['domain_counts'],cartesian_combinations=problem['cartesian_combinations'],
                   solution_count=len(found),truncated=bool(result and isinstance(result,dict) and result.get('truncated')),
                   solution_set_sha256=signature(sorted(found)),solutions=[dict(x) for x in sorted(found)])
        rows.append(row)
    by={r['method']:r for r in rows};oracle=by['brute_force']
    certificate={tuple(sorted(x.items())) for x in problem['certificate']} if problem['certificate'] is not None else None
    for row in rows:
        name=row['method'];complete=row['status']=='completed' and not row['truncated']
        compared=complete and oracle['status']=='completed'
        row['brute_force_comparison']='equal' if compared and sets[name]==sets['brute_force'] else 'different' if compared else 'not_assessed_timeout_or_incomplete'
        if certificate is not None and complete:
            row['certificate_comparison']='equal' if sets[name]==certificate else 'different'
            row['missed_certificate_solution_rate']=len(certificate-sets[name])/len(certificate)
        if name=='no_type_inclusion':
            truth=sets['brute_force'] if oracle['status']=='completed' else certificate
            row['missed_solution_rate']=len(truth-sets[name])/len(truth) if complete and truth else None
            row['type_ablation_truth']='brute_force' if oracle['status']=='completed' else 'planted_certificate' if certificate is not None else 'not_assessed'
    return rows


def planning_population(steps,hierarchy):
    _,planner=modules();pool={}
    def add(kind,attrs):
        if kind not in hierarchy.parent:raise ValueError('Unknown real workflow type '+kind)
        product={'type':kind,'attrs':attrs};pool[planner._key(product)]=product
    defaults={'subject':'synthetic_0','species':'human','hemisphere':'lh','mesh':'synthetic_mesh','space':'native','scale_status':'unknown'}
    for step in steps:
        for item in step['inputs']:
            hemis=['lh','rh'] if item['type'].startswith(('type:Surface','type:Scalar','type:Annotation','type:Label')) else [None]
            for hemi in hemis:
                attrs={'subject':'synthetic_0','species':'human'}
                if hemi:attrs.update(hemisphere=hemi,mesh='synthetic_mesh',space='native')
                for key,value in item.get('attrs',{}).items():
                    if isinstance(value,dict) and 'in' in value:
                        attrs[key]=attrs[key] if attrs.get(key) in value['in'] else value['in'][0]
                    else:attrs[key]=value
                add(item['type'],attrs)
        for item in step['outputs']:
            for hemi in ['lh','rh'] if 'hemisphere' in item.get('inherit',[]) else [None]:
                attrs={key:defaults.get(key) for key in item.get('inherit',[])}
                attrs.update(subject='synthetic_0',species='human')
                if hemi:attrs['hemisphere']=hemi
                attrs.update(item.get('set',{}));add(item['type'],attrs)
    population=[{'id':'observed_'+str(i),**value} for i,value in enumerate(pool.values())]
    eligible=[p for p in population if not planner.satisfied({'type':p['type'],'attrs':p['attrs']},[x for x in population if x['id']!=p['id']],hierarchy)]
    assert len(eligible)>=5,len(eligible)
    return population,eligible


def goal_type_closure(targets,steps,hierarchy):
    """Safe oracle reduction: retain every producer of every ancestral type.

    A positive-cost step outside this closure cannot supply any goal input.
    All possible producers are retained; attributes never prune a producer.
    This changes only the exact oracle input, not the measured full planner.
    """
    pending=[target['type'] for target in targets];seen=set();chosen=set()
    while pending:
        wanted=pending.pop()
        if wanted in seen:continue
        seen.add(wanted)
        for step in steps:
            if any(hierarchy.subsumes(wanted,output['type']) for output in step['outputs']):
                chosen.add(step['id']);pending.extend(item['type'] for item in step['inputs'])
    return [step for step in steps if step['id'] in chosen]


def planning_one(arguments):
    problem,steps,type_document,timeout=arguments;csp,planner=modules();hierarchy=csp.TypeHierarchy.from_document(type_document)
    software={name:True for step in steps for name in step['software']};rows=[]
    names=['andor','optimal_plan','optimal_plan_goal_closure','forward_all'];random.Random(problem['seed']).shuffle(names)
    closure=goal_type_closure(problem['targets'],steps,hierarchy)
    for method in names:
        def operation():
            if method=='andor':return planner.plan(problem['targets'],problem['products'],steps,hierarchy,software)
            if method=='optimal_plan':return planner.optimal_plan(problem['targets'],problem['products'],steps,hierarchy,software)
            if method=='optimal_plan_goal_closure':return planner.optimal_plan(problem['targets'],problem['products'],closure,hierarchy,software)
            available,order=planner._forward({s['id'] for s in steps},problem['products'],steps,hierarchy,software,return_order=True)
            return {'feasible':all(planner.satisfied(t,available,hierarchy) for t in problem['targets']),'steps':order,'cost':len(order)}
        row,result=timed(operation,timeout)
        row.update(case=problem['id'],algorithm='ANDOR',method=method,missing_count=problem['missing_count'],
                   feasible=result['feasible'] if result else None,oracle_goal_closure_steps=len(closure),steps=result['steps'] if result else None,
                   step_count=len(result['steps']) if result else None,cost=clean(result.get('cost')) if result else None)
        rows.append(row)
    oracle=next(r for r in rows if r['method']=='optimal_plan')
    reduced=next(r for r in rows if r['method']=='optimal_plan_goal_closure')
    oracle_crosscheck=None
    if oracle['status']==reduced['status']=='completed':
        oracle_crosscheck=(oracle['feasible']==reduced['feasible'] and (not oracle['feasible'] or oracle['step_count']==reduced['step_count']))
    if oracle['status']!='completed' and reduced['status']=='completed':oracle=reduced
    for row in rows:
        row['verification_oracle']=oracle['method'] if oracle['status']=='completed' else None
        row['full_vs_reduced_exact_oracle_agrees']=oracle_crosscheck
        assessed=row['status']==oracle['status']=='completed'
        row['feasibility_agrees']=row['feasible']==oracle['feasible'] if assessed else None
        both=assessed and row['feasible'] and oracle['feasible']
        row['step_delta_to_optimal']=row['step_count']-oracle['step_count'] if both else None
        row['optimal_step_count']=row['step_delta_to_optimal']==0 if both else None
    return rows


def summarize(rows,group_keys):
    groups={}
    for row in rows:groups.setdefault(tuple(row.get(k) for k in group_keys),[]).append(row)
    output=[]
    for key,values in sorted(groups.items(),key=lambda x:str(x[0])):
        complete=[r for r in values if r['status']=='completed']
        item=dict(zip(group_keys,key));item.update(n=len(values),completed=len(complete),timeouts=sum(r['status']=='timeout' for r in values),errors=sum(r['status']=='error' for r in values))
        for name in ['wall_seconds','cpu_seconds','search_nodes','constraint_evaluations','step_count','step_delta_to_optimal','missed_solution_rate']:
            numbers=[r[name] for r in complete if r.get(name) is not None]
            if numbers:item.update({name+'_median':statistics.median(numbers),name+'_mean':statistics.mean(numbers),name+'_min':min(numbers),name+'_max':max(numbers)})
        for name in ['feasibility_agrees','optimal_step_count']:
            known=[r[name] for r in values if r.get(name) is not None]
            if known:item[name+'_rate']=sum(known)/len(known);item[name+'_denominator']=len(known)
        item['brute_force_exact_comparisons']=sum(r.get('brute_force_comparison') in {'equal','different'} for r in values)
        item['brute_force_exact_mismatches']=sum(r.get('brute_force_comparison')=='different' for r in values)
        item['certificate_comparisons']=sum(r.get('certificate_comparison') in {'equal','different'} for r in values)
        item['certificate_mismatches']=sum(r.get('certificate_comparison')=='different' for r in values)
        output.append(item)
    return output


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--seed',type=int,default=20261024);parser.add_argument('--instances-per-stratum',type=int,default=50)
    parser.add_argument('--workers',type=int,default=4);parser.add_argument('--csp-timeout',type=float,default=3.)
    parser.add_argument('--planning-timeout',type=float,default=30.);args=parser.parse_args()
    if not hasattr(signal,'SIGALRM'):raise RuntimeError('Run on the controlled Linux host for enforceable per-call limits')
    assert not args.out.exists(),'Preserve previous experiments; use a fresh output directory'
    csp,planner=modules();knowledge=ROOT/'agent/modules/agent/knowledge_analysis'
    workflow=json.loads((knowledge/'workflow_steps.json').read_text());types_=json.loads((knowledge/'product_types.json').read_text())
    steps=[{**step,'cost':1.} for step in planner.steps_from_workflow(workflow)]
    digests={name:hashlib.sha256((BACKEND/name).read_bytes()).hexdigest() for name in ['analysis_csp_matching.py','analysis_andor_planner.py']}
    protocol={'seed':args.seed,'per_stratum':args.instances_per_stratum,'workers':args.workers,'csp_timeout_seconds':args.csp_timeout,'planning_timeout_seconds':args.planning_timeout,
              'csp_stress':{'slots':[2,8],'candidate_bins':[5,10,25,50,100,200],'densities':['random spanning tree','tree plus .4 of remaining edges','tree plus .85 of remaining edges'],'instances_per_density':args.instances_per_stratum,'planted_solutions':2,'max_solutions':256},
              'csp_auxiliary_correctness':{'slots':[2,4],'candidates':[5,9],'subject_values':4,'instances_per_density':args.instances_per_stratum,'max_solutions':100000},
              'node_definitions':{'backtracking':'attempted slot-product bindings, existing stats.nodes','brute_force':'complete Cartesian bindings visited; not prefix-node equivalents'},
              'ablations':'isolated source-derived heuristic removals; original module files never written; full/oracle bytecode unchanged',
              'planning':{'missing_counts':[1,2,3,4,5],'instances_per_count':args.instances_per_stratum,'real_workflow_steps':len(steps),'unit_step_costs':True,'additional_verification_oracle':'existing optimal_plan on the complete type-ancestor producer closure; full-graph optimal_plan remains a separate measured baseline','forward_baseline':'run all enabled steps whose inputs bind, including unnecessary stages'},
              'source_sha256':digests,'workflow_sha256':hashlib.sha256((knowledge/'workflow_steps.json').read_bytes()).hexdigest(),
              'product_types_sha256':hashlib.sha256((knowledge/'product_types.json').read_bytes()).hexdigest(),
              'machine':{'platform':platform.platform(),'python':sys.version,'logical_cpus':os.cpu_count()},'model_calls':0,
              'fairness':'Timeouts are censored, not agreement; equality only for complete sets. Stress certificate and direct brute-force checks reported separately.'}
    args.out.mkdir(parents=True);save(args.out/'protocol.json',protocol)
    rng=random.Random(args.seed);csp_cases=[]
    for panel in ['stress','correctness']:
        for density in ['sparse','medium','dense']:
            for index in range(args.instances_per_stratum):csp_cases.append(csp_instance(rng.randrange(2**32),index,density,panel))
    population,eligible=planning_population(steps,csp.TypeHierarchy.from_document(types_));planning_cases=[]
    for count in range(1,6):
        for index in range(args.instances_per_stratum):
            seed=rng.randrange(2**32);chosen=random.Random(seed).sample(eligible,count);removed={p['id'] for p in chosen}
            products=[p for p in population if p['id'] not in removed];targets=[{'type':p['type'],'attrs':p['attrs']} for p in chosen]
            assert all(not planner.satisfied(t,products,csp.TypeHierarchy.from_document(types_)) for t in targets)
            planning_cases.append({'id':f'PLAN_{count}_{index:03d}','seed':seed,'missing_count':count,'removed_ids':sorted(removed),'targets':targets,'products':products})
    save(args.out/'csp_instances.json',csp_cases);save(args.out/'planning_instances.json',planning_cases)
    save(args.out/'input_freeze.json',{'protocol_sha256':hashlib.sha256((args.out/'protocol.json').read_bytes()).hexdigest(),'csp_instances_sha256':hashlib.sha256((args.out/'csp_instances.json').read_bytes()).hexdigest(),'planning_instances_sha256':hashlib.sha256((args.out/'planning_instances.json').read_bytes()).hexdigest(),'frozen_before_first_solver_or_oracle_call':True})
    rows=[]
    with (args.out/'progress.jsonl').open('w',encoding='utf-8') as progress,ProcessPoolExecutor(max_workers=args.workers) as pool:
        jobs=[pool.submit(csp_one,(case,args.csp_timeout)) for case in csp_cases]
        jobs += [pool.submit(planning_one,(case,steps,types_,args.planning_timeout)) for case in planning_cases]
        for index,job in enumerate(as_completed(jobs),1):
            result=job.result();rows.extend(result);progress.write(json.dumps(clean({'job':index,'rows':result}),allow_nan=False)+'\n');progress.flush()
    rows.sort(key=lambda r:(r['algorithm'],r['case'],r['method']))
    crows=[r for r in rows if r['algorithm']=='CSP'];prows=[r for r in rows if r['algorithm']=='ANDOR']
    save(args.out/'results.json',rows);csvout(args.out/'csp_results.csv',crows);csvout(args.out/'planning_results.csv',prows)
    cs=summarize(crows,['panel','density','method']);ps=summarize(prows,['missing_count','method'])
    save(args.out/'summary.json',{'csp':cs,'planning':ps,'model_calls':0,'csp_instances':len(csp_cases),'planning_instances':len(planning_cases)})
    csvout(args.out/'csp_summary.csv',cs);csvout(args.out/'planning_summary.csv',ps)
    assert all(hashlib.sha256((BACKEND/name).read_bytes()).hexdigest()==digest for name,digest in digests.items())
    save(args.out/'completed.json',{'status':'completed','source_algorithms_unchanged':True,'model_calls':0,'result_rows':len(rows),'csp_instances':len(csp_cases),'planning_instances':len(planning_cases),'protocol_sha256':hashlib.sha256((args.out/'protocol.json').read_bytes()).hexdigest()})
    print(json.dumps({'completed':True,'csp_instances':len(csp_cases),'planning_instances':len(planning_cases),'rows':len(rows),'model_calls':0}))

if __name__=='__main__':main()
