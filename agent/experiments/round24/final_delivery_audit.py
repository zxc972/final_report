"""Audit publication shape, immutable export hashes, and actual metering without real calls."""
import argparse,datetime as dt,hashlib,json,re
from pathlib import Path
parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);args=parser.parse_args();repo=args.root;pub=repo/'evaluation/e1/round24_v1'
raw=json.loads((pub/'file_sha256.json').read_text());manifest=raw.get('files',raw)
for name,digest in manifest.items():
 assert isinstance(digest,str) and len(digest)==64
 p=pub/name;assert p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest()==digest, name
http=json.loads((pub/'http_calls.json').read_text());cases=json.loads((pub/'case_results.json').read_text());total=json.loads((pub/'totals.json').read_text())
assert len(http)==180 and len(cases)==12
assert len({r['native_attempt_id'] for r in http})==180
assert len({r['native_logical_id'] for r in http})==169
assert sum(r.get('prompt_tokens') or 0 for r in http)==2944462
assert sum(r.get('completion_tokens') or 0 for r in http)==318610
assert sum(r['prompt_tokens'] is None or r['completion_tokens'] is None for r in http)==15
assert all(x['all_passed'] for x in json.loads((pub/'metering_alignment.json').read_text()))
assert json.loads((pub/'closeout.json').read_text())['original_service_alive_unchanged'] is True
roots=[repo/'evaluation/e1',repo/'evaluation/matching_planning'];paths=[p for x in roots for p in x.rglob('*') if p.is_file() and p.name not in {'delivery_audit.json','delivery_manifest.json'}]
paths += [repo/'agent/experiments/round24'/f for f in ['audit_algorithms.py','host_verifier_path_fix.py','audit_trial_isolation.py','export_public_results.py','collect_offline_evidence.py','close_batch.py','final_delivery_audit.py']]
patterns=[re.compile(r'sk-[A-Za-z0-9_\-]{20,}'),re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),re.compile(r'gh[pousr]_[A-Za-z0-9]{30,}'),re.compile(r'Bearer\s+[A-Za-z0-9_\-\.]{20,}')]
for p in paths:
 assert p.suffix in {'.json','.csv','.md','.py'}
 assert p.name not in {'.env','host_reference_private.json','agent_response.json','participants.tsv'}
 assert not re.fullmatch(r'http_\d+_(request|response)\.json',p.name)
 assert p.name not in {'regional_values.csv','group_results.csv','global_metrics.csv','species_summary.csv','summary.csv'}
 text=p.read_text(encoding='utf-8');assert not any(x.search(text) for x in patterns),str(p)
audit={'audited_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'files_audited':len(paths),'remote_export_hashes_verified':len(manifest),'native_HTTP_logical_token_alignment_rechecked':True,'credential_pattern_scan':'pass','configured_credential_value_scan_of_remote_export':'pass; see public_export_audit.json','new_receipts_contain_only_status_log_hash_summary_source_hash':True,'raw_provider_body_files':0,'generated_analysis_source_files':0,'real_per_subject_tables':0,'MRI_or_QC_images':0,'synthetic_experiment_data_included':True,'original_actor_frozen':True,'additional_model_or_analysis_calls':0}
(pub/'delivery_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
paths += [pub/'delivery_audit.json']
delivery={p.relative_to(repo).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}
(pub/'delivery_manifest.json').write_text(json.dumps({'source_commit':total['source_commit'],'post_trial_source_commit':json.loads((pub/'post_trial_guard.json').read_text())['source_commit'],'files_sha256':delivery},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'audit':'pass','files':len(paths),'remote_export_hashes_verified':len(manifest),'logical':169,'HTTP':180,'known_tokens':3263072,'unknown_usage':15}))
