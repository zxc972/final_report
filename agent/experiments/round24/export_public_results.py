"""Metadata-only export; raw model bodies, code, subject rows and credentials stay on6007."""
from __future__ import annotations
import ast,collections,csv,datetime as dt,hashlib,json,math,subprocess,tarfile
from pathlib import Path
ROOT=Path('/data/xuancheng/agent_v1');BATCH=ROOT/'retests/round24_20261024';OUT=ROOT/'round24_work/public_export'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def scalar(value):return value is None or isinstance(value,(bool,str,int,float))
def counters(record):return {k:v for k,v in (record or {}).items() if scalar(v) or k in ('review_http_by_logical','review_authorization_ids')}
def public_numeric(x):
 if not isinstance(x,dict):return x
 fields=('status','host_verified','assessment_status','checked','mismatch_count','identity_mismatch_count','numeric_mismatch_count','error_type','output_sha256','source','file','rows','expected_rows','schema_mismatch_count')
 out={k:x[k] for k in fields if k in x}
 if isinstance(x.get('tables'),dict):out['tables']={k:public_numeric(v) for k,v in x['tables'].items()}
 if isinstance(x.get('files'),list):out['files']=[public_numeric(v) for v in x['files']]
 return out

def main():
 state=json.loads((BATCH/'batch_status.json').read_text());assert state.get('status')=='closed','Do not finalize an active batch'
 auth=json.loads((BATCH/'authorization.json').read_text());ledger=json.loads((BATCH/'http_ledger.json').read_text());cfg=json.loads((BATCH/'cases.runtime.json').read_text());freeze=json.loads((BATCH/'freeze.json').read_text());source=ROOT/'round24_source'
 assert all(sha(Path(k))==v for k,v in freeze['input_sha256'].items()),'Frozen inputs changed'
 protected=json.loads((BATCH/'protected_source_before.json').read_text());assert all(sha(Path(k))==v for k,v in protected.items()),'Runtime source changed'
 OUT.mkdir(exist_ok=False)
 rows=[];meter=[];case_meta=[];table_rows=[];alignments=[];programs=[];review_history=[];component_history=[]
 for case in auth['launched_cases']:
  folder=BATCH/('case_'+case);summary=json.loads((folder/'summary.json').read_text());response=json.loads((folder/'agent_response.json').read_text());metadata=response.get('metadata') or {};validation=metadata.get('validation') or {};grade_path=folder/'host_grade_path_corrected.json';grade=json.loads((grade_path if grade_path.exists() else folder/'host_grade.json').read_text());review=validation.get('internal_review') or {};card=metadata.get('conclusion_card') or {};attempts=[x for x in ledger['attempts'] if x['case']==case]
  code_by_sha={}
  for observed in attempts:
   number=observed['seq'];rq=json.loads((folder/f'http_{number:03d}_request.json').read_text());rp=folder/f'http_{number:03d}_response.json';body=json.loads(rp.read_text()).get('response') or {} if rp.exists() else {}
   messages=[*(rq.get('messages') or []),*[x.get('message') or {} for x in body.get('choices',[])]]
   for message in messages:
    for call in message.get('tool_calls',[]) or []:
     function=call.get('function') or {};name=function.get('name',call.get('name',''));args=function.get('arguments',call.get('args',{}))
     if not str(name).endswith('write_code'):continue
     if isinstance(args,str):
      try:args=json.loads(args)
      except ValueError:continue
     code=args.get('code') if isinstance(args,dict) else None
     if isinstance(code,str):code_by_sha[hashlib.sha256(code.encode()).hexdigest()]=code
  source_counts=collections.Counter(x.get('source_node') or 'unbound' for x in attempts)
  ids=[x.get('native_attempt_id') for x in attempts];logical={x.get('native_logical_id') for x in attempts if x.get('native_logical_id')}
  p=sum((x.get('usage') or {}).get('prompt_tokens',0) for x in attempts);c=sum((x.get('usage') or {}).get('completion_tokens',0) for x in attempts);unknown=sum(not isinstance(x.get('usage'),dict) or not all(type(x['usage'].get(k)) is int for k in ('prompt_tokens','completion_tokens')) for x in attempts)
  row={k:summary.get(k) for k in ('case','C','status','overall_status','route','model_calls','tool_calls','executions','iterations','elapsed_seconds','internal_review_decision','internal_review_protocol_valid','full_chain_passed','source_commit','http_status','client_error')}
  row.update(http_attempts=len(attempts),known_prompt_tokens=p,known_completion_tokens=c,known_total_tokens=p+c,unknown_usage_attempts=unknown,observed_native_logical_calls=len(logical),all_http_bound_to_native=all(ids) and len(set(ids))==len(ids),public_output_contract=public_numeric(summary.get('public_output_contract') or {}),independent_numeric=public_numeric(summary.get('independent_numeric') or {}),request_budget=counters(summary.get('request_budget')),review_budget=counters(summary.get('review_budget')),phase_budget=counters(summary.get('phase_budget')),system_defect_codes=[x.get('code') for x in (summary.get('system_defects') or {}).get('events',[])],failure_category=(summary.get('failure_classification') or {}).get('category'),source_nodes=dict(source_counts),tables=grade.get('tables'),fixed_scope_numeric_pass=grade.get('fixed_scope_numeric_pass'),conclusion_card={'overall_status':card.get('overall_status'),'verdict':card.get('verdict'),'review_status':card.get('review_status'),'scope':card.get('scope'),'component_statuses':card.get('component_statuses')},semantic_audit_required=True)
  row['analysis_model_calls_reported']=row.get('model_calls')
  row['model_calls']=(metadata.get('requestBudget') or {}).get('model_calls',row.get('model_calls'))
  row['logical_call_count_source']='native RequestBudget including router; analysis-only field retained separately'
  case_meta.append(row)
  flat={k:v for k,v in row.items() if scalar(v)}
  flat['public_contract_status']=(row['public_output_contract'] or {}).get('status');flat['independent_numeric_status']=(row['independent_numeric'] or {}).get('status');flat['system_defect_codes']=';'.join(row['system_defect_codes']);flat['table_statuses']=';'.join(k+':'+v.get('status','unknown') for k,v in (row['tables'] or {}).items());flat['conclusion_verdict']=card.get('verdict');rows.append(flat)
  for x in attempts:
   request=json.loads((folder/f"http_{x['seq']:03d}_request.json").read_text());body=json.loads((folder/f"http_{x['seq']:03d}_response.json").read_text()).get('response') or {};usage=x.get('usage') or {};meter.append({k:x.get(k) for k in ('seq','case','started_utc','model_requested','model_returned','native_attempt_id','native_logical_id','source_node','analysis_phase','status','status_code','elapsed_seconds','error_type')}|{'prompt_tokens':usage.get('prompt_tokens'),'completion_tokens':usage.get('completion_tokens'),'total_tokens':usage.get('total_tokens'),'temperature':request.get('temperature'),'max_tokens':request.get('max_tokens'),'response_format_type':(request.get('response_format') or {}).get('type'),'finish_reasons':';'.join(str(choice.get('finish_reason')) for choice in body.get('choices',[]))})
  selected=[]
  run_id=summary.get('run_id')
  for plan_path in sorted((BATCH/'state').glob('**/'+run_id+'/plan.v*.json')) if run_id else []:
   sealed=json.loads(plan_path.read_text());plan=sealed['record']['plan'];scope=plan.get('analysis_scope') or {}
   selected.append({'version':sealed['version'],'sha256':sealed['sha256'],'method_id':plan['method']['method_id'],'subject_count':len(plan.get('data',{}).get('subjects',[])),'atlas':plan.get('atlas',{}).get('name'),'design':scope.get('design'),'comparison':scope.get('comparison'),'effect':scope.get('effect'),'n':scope.get('n'),'df':scope.get('df'),'metrics':scope.get('metrics'),'regions':scope.get('regions')})
  row['selected_plans']=selected
  if run_id:
   for family in ('public_output_validation','independent_numeric'):
    for history_path in sorted((BATCH/'state').glob('**/'+run_id+'/'+family+'.v*.json')):
     saved=json.loads(history_path.read_text());record=saved['record'];component_history.append({'case':case,'component':family,'version':saved.get('version'),'record_sha256':saved.get('sha256'),'plan_sha256':record.get('plan_sha256'),'execution_receipt_id':record.get('execution_receipt_id'),'summary':public_numeric(record)})
  for filename in cfg[case]['required_artifacts']:
   public=next((x for x in (validation.get('public_output_contract') or {}).get('files',[]) if x.get('file')==filename),{})
   native=(validation.get('independent_numeric') or {}).get('tables',{}).get(filename,{})
   if not native and len((validation.get('public_output_contract') or {}).get('files',[]))==1 and public.get('file')==filename:
    native=validation.get('independent_numeric') or {}
   fixed=(grade.get('tables') or {}).get(filename,{})
   table_rows.append({'case':case,'file':filename,'public_contract_status':public.get('status','not_assessed'),'public_rows':public.get('rows'),'expected_public_rows':public.get('expected_rows'),'public_identity_mismatches':public.get('identity_mismatch_count'),'public_schema_mismatches':public.get('schema_mismatch_count'),'native_independent_status':native.get('status','not_assessed'),'fixed_scope_host_status':fixed.get('status','not_assessed'),'fixed_scope_checked':fixed.get('checked'),'fixed_scope_identity_mismatches':fixed.get('identity_mismatch_count'),'fixed_scope_numeric_mismatches':fixed.get('numeric_mismatch_count'),'output_sha256':fixed.get('output_sha256') or public.get('output_sha256')})
  native_budget=metadata.get('requestBudget') or {};rb=metadata.get('review_budget') or {};known=native_budget.get('known_tokens') or {}
  checks={'all_native_attempt_ids_present_unique':all(ids) and len(set(ids))==len(ids),'observed_HTTP_matches_native':len(attempts)==native_budget.get('http_attempts'),'observed_logical_matches_native':len(logical)==native_budget.get('model_calls'),'prompt_tokens_match':p==known.get('prompt_tokens',0),'completion_tokens_match':c==known.get('completion_tokens',0),'unknown_usage_matches':unknown==native_budget.get('unknown_usage_calls'),'unmetered_logical_calls_zero':native_budget.get('unmetered_logical_calls')==0}
  if rb.get('enabled'):
   checks.update(initial_within_23=rb.get('initial_coding_model_calls',0)<=23,review_logical_within_4=rb.get('review_logical_calls',0)<=4,revision_within_3=rb.get('revision_model_calls',0)<=3,total_within_30=rb.get('budget_units_used',0)<=30,revision_only_authorized=not rb.get('revision_model_calls') or rb.get('revision_authorized') is True,review_HTTP_matches_observer=rb.get('review_http_attempts')==source_counts['internal_review'],each_review_HTTP_within_3=all(n<=3 for n in rb.get('review_http_by_logical',[])))
  alignments.append({'case':case,'checks':checks,'all_passed':all(checks.values())})
  output=Path('/data/xuancheng/agent_v1/workspaces/env-smoke/output')/(summary.get('output_directory') or '__no_output__')
  for receipt_path in sorted((output.parent/'.execution_receipts'/output.name).glob('*.json')):
   executed=json.loads(receipt_path.read_text());code_path=output/str(executed.get('script','')).removeprefix('/work/');matched=code_path.is_file() and sha(code_path)==executed.get('script_sha256_before');writer=None;generated=code_by_sha.get(executed.get('script_sha256_before'));source_for_ast=generated if generated is not None else code_path.read_text() if matched else None
   if source_for_ast is not None:
    try:writer=any(isinstance(x,ast.Call) and ((isinstance(x.func,ast.Attribute) and x.func.attr=='write_contract_table') or (isinstance(x.func,ast.Name) and x.func.id=='write_contract_table')) for x in ast.walk(ast.parse(source_for_ast)))
    except (ValueError,SyntaxError):writer=None
   programs.append({'case':case,'receipt_id':executed.get('receipt_id'),'script_sha256':executed.get('script_sha256_before'),'current_source_matches_execution':matched,'source_recovered_from_actual_model_tool_call':generated is not None,'generic_writer_present_if_source_matched':writer,'exit_code':(executed.get('result') or {}).get('exit_code'),'status':(executed.get('result') or {}).get('status')})
  for review_path in sorted((output.parent/'.analysis_reviews'/output.name).glob('*.json')):
   recorded=json.loads(review_path.read_text());history={'case':case,'review_id':recorded.get('id'),'final_review':recorded.get('id')==review.get('review_id'),'decision':(recorded.get('review') or {}).get('decision'),'observed_hard_block_constraint_ids':[x.get('constraint_id') for x in (recorded.get('evidence_card') or {}).get('hard_blocks',[])],'attempts':[]}
   for item in recorded.get('attempts',[]):
    history['attempts'].append({'attempt':item.get('attempt'),'error_type':item.get('error_type'),'protocol_error_present':bool(item.get('protocol_error')),'transport_present':bool(item.get('transport'))})
   review_history.append(history)
  save(OUT/'cases'/(case+'.json'),row)
 save(OUT/'table_verification.json',table_rows);save(OUT/'metering_alignment.json',alignments);save(OUT/'execution_metadata.json',programs);save(OUT/'review_history_metadata.json',review_history);save(OUT/'component_history.json',component_history)
 save(OUT/'case_results.json',case_meta);save(OUT/'http_calls.json',meter)
 for name,data in [('case_results.csv',rows),('http_calls.csv',meter),('table_verification.csv',table_rows)]:
  fields=sorted({k for r in data for k in r})
  with (OUT/name).open('w',encoding='utf-8',newline='') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(data)
 for f in ('freeze.json','offline_release.json','guard_preflight.json','host_reference_preflight.json','verifier_fixtures.json','preflight_data.json','batch_status.json','batch_launch.json','development_launch.json','http_transport_coverage.json','path_fix_audit.json','trial_isolation_audit.json','router_format_audit.json'):
  x=json.loads((BATCH/f).read_text())
  if f=='offline_release.json':x.pop('runtime_source_sha256',None);x.pop('closed_inputs_sha256',None)
  save(OUT/f,x)
 total={'real_analysis_entries':auth['real_analysis_runs'],'authorized_max':12,'http_attempts':ledger['http_attempts'],'known_prompt_tokens':ledger['known_prompt_tokens'],'known_completion_tokens':ledger['known_completion_tokens'],'unknown_usage_attempts':ledger['unknown_usage_attempts'],'per_case_model_reservations_sum':sum(x.get('model_calls') or 0 for x in rows),'all_http_native_ids_bound_and_unique':all(x['all_http_bound_to_native'] for x in case_meta),'all_metering_alignment_checks_passed':all(x['all_passed'] for x in alignments),'algorithm_model_calls':0,'frozen_inputs_unchanged':True,'runtime_source_unchanged':True,'original_existing_service_alive':Path('/proc/4144167').exists(),'preprocessing_submission_attempted':(BATCH/'preprocessing_submission_blocked.json').exists(),'held_out_roots_included':False,'private_trace_archive':str(BATCH),'raw_provider_bodies_exported':False,'generated_code_exported':False,'per_subject_tables_exported':False,'raw_mri_exported':False,'key_values_exported':False,'source_commit':subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip(),'exported_utc':dt.datetime.now(dt.timezone.utc).isoformat()}
 save(OUT/'totals.json',total)
 # Export is an explicit whitelist of scalar metadata. Check against configured credentials without printing any value.
 secrets=[]
 env=dict(x.decode().split('=',1) for x in Path('/proc/4144167/environ').read_bytes().split(b'\0') if b'=' in x)
 secrets.extend(v for k,v in env.items() if k.endswith(('_KEY','_TOKEN')) and len(v)>=12)
 for line in (ROOT/'.env').read_text().splitlines():
  line=line.strip().removeprefix('export ')
  if '=' not in line or line.startswith('#'):continue
  k,v=line.split('=',1)
  if k.strip().endswith(('_KEY','_TOKEN')):secrets.append(v.strip().strip('"'+chr(39)))
 files=[f for f in OUT.rglob('*') if f.is_file()]
 assert all(not any(s and s in f.read_text() for s in secrets) for f in files),'Credential match; export blocked'
 save(OUT/'public_export_audit.json',{'credential_scan':'pass','files_before_audit':len(files),'source':'Whitelisted metadata only','private_raw_files_excluded':True})
 manifest={str(f.relative_to(OUT)):sha(f) for f in OUT.rglob('*') if f.is_file()};save(OUT/'file_sha256.json',manifest)
 with tarfile.open(ROOT/'round24_work/e1_public_metadata.tar.gz','w:gz') as t:
  for f in OUT.rglob('*'):
   if f.is_file():t.add(f,arcname=str(f.relative_to(OUT)))
 print(json.dumps(total))
if __name__=='__main__':main()
