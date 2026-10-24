"""Read-only Round22 report export. Never calls a model or modifies a run."""
from __future__ import annotations
from pathlib import Path
from collections import Counter
from datetime import datetime,timezone
import argparse,csv,hashlib,json,re,shutil


def load(p):return json.loads(p.read_text())
def save(p,d):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
def csvout(p,rows,fields=None):
    if not rows and not fields:return
    p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields or list(rows[0]));w.writeheader();w.writerows(rows)
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def key_values(d,key):
    values=[]
    if isinstance(d,dict):
        if key in d:values.append(d[key])
        for v in d.values():values.extend(key_values(v,key))
    elif isinstance(d,list):
        for v in d:values.extend(key_values(v,key))
    return values


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--batch',required=True);ap.add_argument('--out',required=True);ap.add_argument('--partial',action='store_true');args=ap.parse_args()
    b=Path(args.batch);out=Path(args.out);pub=out/'public';private=out/'private'
    auth=load(b/'authorization.json');ledger=load(b/'http_ledger.json')
    if not args.partial:assert auth['status']=='closed',auth['status']
    summaries=[];stage_rows=[];http_rows=[];tables=[];cards=[];failures=[];alignments=[];science=[]
    for case in auth['launched_cases']:
        folder=b/('case_'+case);p=folder/'summary.json'
        if not p.exists():
            assert args.partial,case
            continue
        summary=load(p);response=load(folder/'agent_response.json');meta=response.get('metadata',{});validation=meta.get('validation',{});budget=meta.get('requestBudget',{});request=load(folder/'request.public.json')
        events=load(folder/'events_response.json').get('events',[]);attempts=[x for x in ledger['attempts'] if x['case']==case]
        logical={x['native_logical_id'] for x in attempts};native={x['native_attempt_id'] for x in attempts}
        assert None not in logical and None not in native and len(native)==len(attempts),case
        prompt=completion=known=0
        for x in attempts:
            req=load(folder/f"http_{x['seq']:03d}_request.json");receipt=load(folder/f"http_{x['seq']:03d}_response.json")
            assert req['model']=='deepseek-v4-pro'
            assert receipt['record']['native_attempt_id']==x['native_attempt_id'] and receipt['record']['native_logical_id']==x['native_logical_id']
            body=receipt['response'] if isinstance(receipt['response'],dict) else {}
            assert receipt['record']['usage']==x['usage'] and body.get('usage')==x['usage']
            u=x.get('usage');ok=isinstance(u,dict) and all(type(u.get(k)) is int and u[k]>=0 for k in ['prompt_tokens','completion_tokens'])
            if ok:prompt+=u['prompt_tokens'];completion+=u['completion_tokens'];known+=1
            http_rows.append({'case':case,'seq':x['seq'],'native_attempt_id':x['native_attempt_id'],'native_logical_id':x['native_logical_id'],'source_node':x['source_node'],'analysis_phase':x['analysis_phase'],'started_utc':x['started_utc'],'status':x['status'],'status_code':x.get('status_code'),'elapsed_seconds':x.get('elapsed_seconds'),'model_requested':x.get('model_requested'),'model_returned':x.get('model_returned'),'temperature':req.get('temperature'),'max_tokens':req.get('max_tokens'),'response_format_type':(req.get('response_format') or {}).get('type'),'prompt_tokens':u['prompt_tokens'] if ok else None,'completion_tokens':u['completion_tokens'] if ok else None,'usage_status':'known' if ok else 'unknown','finish_reason':';'.join(str(c.get('finish_reason')) for c in body.get('choices',[]))})
        checks={'unmetered_logical_calls_zero':budget.get('unmetered_logical_calls')==0,'http_count_matches_native_budget':len(attempts)==budget['http_attempts'],'logical_count_matches_native_budget':len(logical)==budget['model_calls'],'prompt_tokens_match_native_budget':prompt==budget['known_tokens']['prompt_tokens'],'completion_tokens_match_native_budget':completion==budget['known_tokens']['completion_tokens'],'unknown_usage_matches_native_budget':len(attempts)-known==budget['unknown_usage_calls'],'all_http_receipts_match_native_ids_and_usage':True}
        assert all(checks.values()),(case,checks)
        alignments.append({'case':case,'checks':checks,'logical_calls':len(logical),'http_attempts':len(attempts),'known_usage_attempts':known,'unknown_usage_attempts':len(attempts)-known,'known_prompt_tokens':prompt,'known_completion_tokens':completion,'http_status_counts':dict(Counter(str(x.get('status_code')) for x in attempts)),'source_node_attempts':dict(Counter(x['source_node'] for x in attempts)),'phase_attempts':dict(Counter(x['analysis_phase'] for x in attempts))})
        phase=[]
        for ev in events:
            stage_rows.append({'case':case,'seq':ev.get('seq'),'time':ev.get('time'),'stage':ev.get('stage'),'status':ev.get('status'),'title':ev.get('title')})
            m=re.match(r'^(?:Phase tools|Analysis phase): (\w+)$',ev.get('title',''))
            if m and (not phase or phase[-1]!=m.group(1)):phase.append(m.group(1))
        review=validation.get('internal_review') or {};contract=validation.get('public_output_contract') or {};ind=validation.get('independent_numeric') or {}
        for filename in ['regional_values.csv','group_results.csv']:
            c=next((x for x in contract.get('files',[]) if x['file']==filename),{});n=ind.get('tables',{}).get(filename,{})
            tables.append({'case':case,'file':filename,'public_contract_status':c.get('status',contract.get('status','not_performed')),'rows':c.get('rows'),'expected_rows':c.get('expected_rows'),'public_identity_mismatches':c.get('identity_mismatch_count') if c else None,'schema_mismatches':c.get('schema_mismatch_count') if c else None,'host_numeric_status':n.get('status',ind.get('status','not_assessed')),'host_identity_mismatches':n.get('identity_mismatch_count'),'host_numeric_mismatches':n.get('numeric_mismatch_count'),'host_checked_scalars':n.get('checked'),'output_sha256':c.get('output_sha256'),'internal_review_decision':review.get('decision','not_performed'),'internal_review_protocol_valid':review.get('protocol_valid')})
        card=meta.get('conclusion_card') or {};cards.append({'case':case,**{k:card.get(k) for k in ['schema','verdict','reason','conclusion_text','scope','rule_id']}})
        summaries.append({k:summary.get(k) for k in ['case','model','source_commit','http_status','status','overall_status','route','routing','model_calls','tool_calls','executions','iterations','elapsed_seconds','phase_budget','event_count','full_chain_passed','client_error']}|{'phase_sequence':phase,'http_attempts':len(attempts),'known_prompt_tokens':prompt,'known_completion_tokens':completion,'unknown_usage_attempts':len(attempts)-known,'internal_review_decision':review.get('decision','not_performed'),'internal_review_protocol_valid':review.get('protocol_valid'),'internal_review_protocol_attempts':review.get('protocol_attempts'),'internal_review_transport_exhausted':review.get('transport_exhausted'),'conclusion_verdict':card.get('verdict')})
        pp=private/case;pp.mkdir(parents=True,exist_ok=True)
        for filename in ['summary.json','agent_response.json','events_response.json','events.jsonl','request.public.json']:
            shutil.copy2(folder/filename,pp/filename)
        for path in folder.glob('http_*.json'):shutil.copy2(path,pp/path.name)
        output=Path(request['context']['workspaceDirectory'])/summary['output_directory'];errors=[]
        for path in (output/'tool_results').glob('run_python_*.json'):
            d=load(path);errors.append({'receipt_file':path.name,'status':d.get('status'),'exit_code':d.get('exit_code'),'automatic_finalization':d.get('automatic_finalization'),'stderr_tail':str(d.get('stderr',''))[-900:]})
        failures.append({'case':case,'classification':meta.get('failure_classification'),'execution_receipts':errors,'internal_review':{k:review.get(k) for k in ['decision','protocol_valid','protocol_attempts','limitations','transport_exhausted']}})
        for filename in ['regional_values.csv','group_results.csv','summary.json','report.md','analysis_manifest.json','self_checks.json','repair_log.json']:
            if (output/filename).is_file():shutil.copy2(output/filename,pp/('output_'+filename))
        if case.startswith('R22_G1'):
            item={'case':case,'numeric_results_available':contract.get('status')=='pass' and ind.get('status')=='pass','reviewed_conclusion_available':summary.get('full_chain_passed',False)}
            if item['numeric_results_available']:
                with (output/'group_results.csv').open() as f:rows=list(csv.DictReader(f))
                assert all(x['effect']=='age' and x['status']=='ok' and x['n']=='20' for x in rows)
                n=len(rows);item.update(n_subjects=20,n_partitions=n,fdr_family_size=n,fdr_significant=sum(float(x['q_fdr'])<.05 for x in rows),negative_age_estimates=sum(float(x['estimate'])<0 for x in rows),negative_age_proportion=sum(float(x['estimate'])<0 for x in rows)/n,df_values=sorted({int(x['df']) for x in rows}),fdr_alpha=.05,age_units='mm/year',design='regional mean thickness ~ age + sex; no site/scanner adjustment')
                sealed=[p for p in (b/'state').glob('**/'+summary['run_id']+'/plan.v*.json') if load(p).get('sha256')==contract['plan_sha256']]
                assert len(sealed)==1,(case,sealed)
                power=sorted({float(x) for x in key_values(load(sealed[0]),'d_min') if isinstance(x,(float,int))})
                assert len(power)==1,power
                item.update(d_min_plan_sha256=contract['plan_sha256'],d_min_plan_version=sealed[0].name)
                item.update(d_min=power[0],d_min_basis='sealed host group design; normal approximation, two-sided alpha=.05, power=.8; standardized continuous slope; not FDR-adjusted power')
                groups={'superior_and_inferior_frontal':['superiorfrontal','parsopercularis','parsorbitalis','parstriangularis'],'superior_temporal':['superiortemporal'],'medial_temporal':['entorhinal','parahippocampal'],'anterior_cingulate':['caudalanteriorcingulate','rostralanteriorcingulate']}
                item['direction_groups']=[]
                for name,labels in groups.items():
                    subset=[x for x in rows if x['name'] in labels]
                    item['direction_groups'].append({'group':name,'labels':labels,'n_hemisphere_partitions':len(subset),'negative':sum(float(x['estimate'])<0 for x in subset),'q_lt_005':sum(float(x['q_fdr'])<.05 for x in subset),'mean_age_estimate_mm_per_year':sum(float(x['estimate']) for x in subset)/len(subset),'mean_absolute_age_estimate_mm_per_year':sum(abs(float(x['estimate'])) for x in subset)/len(subset)})
                item['interpretation']='Descriptive directional comparison only; internal review incomplete, conclusion deferred. No precise one-to-one DKT mapping of temporoparietal junction was asserted.'
            else:item['unavailable_reason']='No pair of tables passed public contract and host numeric verification in this run; partial outputs are not treated as results.'
            science.append(item)
    save(pub/'run_summaries.json',summaries);save(pub/'conclusion_cards.json',cards);save(pub/'failure_details.json',failures);save(pub/'g1_direction_summary.json',science)
    save(pub/'meter_alignment.json',{'created_utc':datetime.now(timezone.utc).isoformat(),'partial':args.partial,'cases':alignments,'actual_analysis_entries':auth['real_analysis_runs'],'completed_cases':len(summaries),'all_completed_case_native_meter_checks_passed':True,'actual_upstream_http_requests':len(ledger['attempts']),'completed_case_http_attempts':sum(x['http_attempts'] for x in alignments),'known_prompt_tokens_completed_cases':sum(x['known_prompt_tokens'] for x in alignments),'known_completion_tokens_completed_cases':sum(x['known_completion_tokens'] for x in alignments),'unknown_usage_attempts_completed_cases':sum(x['unknown_usage_attempts'] for x in alignments),'unknown_is_not_zero':True})
    csvout(pub/'http_attempts.csv',http_rows);csvout(pub/'stages.csv',stage_rows);csvout(pub/'table_verification.csv',tables)
    for filename in ['authorization.json','catalog_scope_audit.json','G1_continue_third_decision.json','G2_continue_third_decision.json','G2_stop_decision.json','offline_release.json','development_launch.json','development_ready.json','http_transport_coverage.json','existing_services_before.json','existing_services_after.json','final_safety_audit.json','shutdown.json']:
        if (b/filename).exists():shutil.copy2(b/filename,pub/filename)
    save(private/'http_ledger.json',ledger)
    files={p.relative_to(out).as_posix():digest(p) for p in sorted(out.rglob('*')) if p.is_file() and p.name!='EXPORT_MANIFEST.json'}
    save(out/'EXPORT_MANIFEST.json',{'files':files,'public_excludes':['per-subject tables','private numeric references','raw model requests/responses','MRI'],'source_batch':str(b),'created_utc':datetime.now(timezone.utc).isoformat(),'partial':args.partial,'analysis_runs':auth['real_analysis_runs'],'paid_model_calls_by_export':0})
    print(json.dumps({'completed_cases':len(summaries),'actual_entries':auth['real_analysis_runs'],'completed_http_attempts':sum(x['http_attempts'] for x in alignments),'public_files':len(list(pub.rglob('*'))),'g1_results':science},ensure_ascii=False))


if __name__=='__main__':main()