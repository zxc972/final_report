"""Read-only trial audit after termination: own tool feedback, code lineage and actual receipts."""
from pathlib import Path
import collections,hashlib,json,sys,time
R=Path('/data/xuancheng/agent_overnight_20261020');run=sys.argv[1];D=R/'runs'/run
result=json.loads((D/'agent_result.json').read_text());request=json.loads((D/'request.json').read_text())
workspace=Path(request['workspace_root']);W=workspace/result['output_directory'];assert W.resolve().is_relative_to(workspace.resolve())and W.is_dir()
assert not(D/'autonomy_review.json').exists()
http=[];calls=[];writes=[]
for p in sorted((R/'audit').glob('http_*.json')):
 h=json.loads(p.read_text())
 if h.get('run')!=run:continue
 http.append(h)
 for choice in(h.get('response')or{}).get('choices',[]):
  for tc in(choice.get('message')or{}).get('tool_calls',[]):
   f=tc['function']
   try:a=json.loads(f['arguments'])
   except Exception:a={}
   calls.append({'http_id':h['id'],'name':f['name'],'arguments':a})
   if f['name']=='write_code'and isinstance(a.get('code'),str):
    path=a.get('path','');normal=path if path.startswith('/work/')else'/work/'+path.lstrip('/')
    writes.append({'http_id':h['id'],'path':path,'normal_path':normal,'sha256':hashlib.sha256(a['code'].encode()).hexdigest()})
observations=[]
journal=W.parent/'.analysis_feedback'/W.name
for p in journal.glob('*.json'):observations.append(json.loads(p.read_text()))
observations.sort(key=lambda x:(x['time'],x['id']))
byid={o['id']:o for o in observations}
reflections=[x for x in observations if x['kind']=='reflection'];failures=[x for x in observations if x['kind']=='observation'and x['failed']]
chains=[]
for refl in reflections:
 failure=byid[refl['observation_id']];later=[x for x in observations if x['time']>refl['time']and x['kind']=='observation']
 executions=[x for x in later if x['tool']=='run_python']
 chains.append({'failed_observation_id':failure['id'],'failed_tool':failure['tool'],'failure_result':failure['result'],
   'model_hypothesis':refl['hypothesis'],'model_next_check':refl['next_check'],'knowledge_ids':refl['knowledge_ids'],
   'source_failure_exists_and_precedes_reflection':failure['time']<refl['time'],
   'later_knowledge_calls':[x['tool']for x in later if x['tool'].startswith(('search_','read_analysis_method','read_research_knowledge'))],
   'later_code_writes':sum(x['tool']=='write_code'for x in later),'later_actual_executions':[{'observation_id':x['id'],'failed':x['failed'],'receipt_id':x['result'].get('receipt_id')}for x in executions],
   'any_later_successful_execution':any(not x['failed']for x in executions),
   'resolution_scope':'Temporal execution-feedback chain; not proof that every scientific error was identified or resolved.'})
execs=[]
for p in(W.parent/'.execution_receipts'/W.name).glob('*.json'):
 e=json.loads(p.read_text());matches=[w for w in writes if w['normal_path']==e['script']and w['sha256']==e['script_sha256_before']]
 execs.append({'receipt_id':e['receipt_id'],'script':e['script'],'status':e['result'].get('status'),'exit_code':e['result'].get('exit_code'),'sha256_before':e['script_sha256_before'],'sha256_after':e['script_sha256_after'],'direct_model_write_http_ids':[x['http_id']for x in matches],'direct_model_write_bytes_match':bool(matches)})
changes=[]
for x in json.loads((D/'input_snapshot.json').read_text()):
 p=Path(x['path'])
 if hashlib.sha256(p.read_bytes()).hexdigest()!=x['sha256']:changes.append(x['path'])
roots=json.loads((D/'task_config.json').read_text())['input_roots']
bad_mount=any(any(z in Path(p).parts for z in ['102311','105216','independent_references','runs','audit'])for p in roots)
codepass=bool(execs)and all(x['direct_model_write_bytes_match']and x['sha256_before']==x['sha256_after']for x in execs)
artifacts=[]
for a in result.get('artifacts',[]):
 p=W/a['path'];artifacts.append({'path':a['path'],'bytes':p.stat().st_size if p.exists()else None,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()if p.is_file()else None,'native_sha256':a.get('sha256')})
product_before=json.loads((D/'product_snapshot.json').read_text());product_now={n:hashlib.sha256((Path('/data/xuancheng/agent/modules/agent/backend')/n).read_bytes()).hexdigest()for n in product_before if n not in ['api.py','models.py']}
stable=all(product_before[n]==v for n,v in product_now.items())
usage={'http_requests':len(http),'statuses':dict(collections.Counter(str(x.get('status_code','pending'))for x in http)),'known_input_tokens':sum(((x.get('response')or{}).get('usage')or{}).get('prompt_tokens',0)for x in http),'known_output_tokens':sum(((x.get('response')or{}).get('usage')or{}).get('completion_tokens',0)for x in http),'unknown_usage':sum(x.get('usage_state')!='reported'for x in http)}
out={'run':run,'created':time.time(),'workspace':str(W),'native_status':result['status'],'native_validation':result.get('validation'),'tool_counts':dict(collections.Counter(x['name']for x in calls)),'failure_count':len(failures),'reflection_count':len(reflections),'feedback_chains':chains,'executions':execs,'direct_code_origin_pass':codepass,'inputs_unchanged':not changes,'changed_inputs':changes,'heldout_or_private_reference_mounted':bad_mount,'previous_analysis_scripts_mounted':json.loads((D/'request.json').read_text()).get('prewritten_analysis_code_supplied'),'product_code_unchanged_during_trial':stable,'artifacts':artifacts,'usage':usage,'external_result_based_guidance_during_run':False,'scope':'Known data, fresh analysis code; not blind unseen-data evaluation, expert QC or graph efficacy causal experiment.'}
(D/'autonomy_review.json').write_text(json.dumps(out,ensure_ascii=False,indent=2));(D/'actual_tool_trace.json').write_text(json.dumps(calls,ensure_ascii=False,indent=2))
print(json.dumps({k:out[k]for k in ['run','native_status','tool_counts','failure_count','reflection_count','direct_code_origin_pass','inputs_unchanged','heldout_or_private_reference_mounted','previous_analysis_scripts_mounted','product_code_unchanged_during_trial','usage']},ensure_ascii=False,indent=2))

