"""Collect only offline exit receipts, log digests/tails, and tested source digests."""
import datetime as dt,hashlib,json
from pathlib import Path
ROOT=Path('/data/xuancheng/agent_v1'); WORK=ROOT/'round24_work'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
files=[]
for stage in ['v5','post_v6']:
 for name in ['chain_targeted','sdk_binding','synthetic_container','backend_default']:
  base=WORK/(name+'_'+stage); status=Path(str(base)+'.status.json');log=Path(str(base)+'.txt')
  x=json.loads(status.read_text()); assert x['exit_code']==0 and x['real_provider_requests']==0
  lines=log.read_text(errors='replace').splitlines()
  tails=[x for x in lines[-14:] if any(w in x for w in ['passed','skipped','subtest','warning'])]
  assert tails
  files.append({'name':base.name,'status':x,'log_sha256':sha(log),'summary_lines':tails})
tested=ROOT/'round24_posttrial_source'; paths=['agent/modules/agent/backend/analysis_product_planner.py','agent/modules/agent/tests/test_round24_caller_scope.py']
x={'collected_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'checks':files,'post_trial_tested_source_sha256':{p:sha(tested/p) for p in paths},'real_provider_requests':0,'real_analysis_entries':0,'all_exit_codes_zero':True}
(WORK/'offline_validation_evidence.json').write_text(json.dumps(x,indent=2)+'\n')
print(json.dumps({'checks':len(files),'all_passed':True,'post_trial_tested_source_sha256':x['post_trial_tested_source_sha256']}))
