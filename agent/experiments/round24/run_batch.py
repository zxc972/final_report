"""Closed single-shot trial: ten E1 cases plus two original-question retests."""
import datetime as dt,hashlib,json,subprocess,time
from pathlib import Path
ROOT=Path('/data/xuancheng/agent_v1');BATCH=ROOT/'retests/round24_20261024';SOURCE=ROOT/'round24_source';PY=ROOT/'.venv-coding/bin/python';REF=ROOT/'.venv-reference/bin/python'
ORDER=['R24_G1','R24_G2','E1_S1','E1_S2','E1_S3','E1_G1','E1_G2','E1_G3','E1_X1','E1_N1','E1_N2','E1_N3']
def now():return dt.datetime.now(dt.timezone.utc).isoformat()
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def main():
 path=BATCH/'batch_status.json';assert not path.exists(),'Never restart or duplicate a trial'
 cfg=json.loads((BATCH/'cases.runtime.json').read_text());state={'started_utc':now(),'order':ORDER,'finished':[],'skipped':[],'max_real_analysis_runs':12,'model_hints_or_repairs_during_batch':False};save(path,state)
 for case in ORDER:
  auth=json.loads((BATCH/'authorization.json').read_text());assert auth['real_analysis_runs']<12
  group=cfg[case]['question_group'];prior=[]
  for k in auth.get('launched_cases',[]):
   f=BATCH/('case_'+k)/'summary.json'
   if cfg[k]['question_group']==group and f.exists():prior.append(json.loads(f.read_text()))
  if any((r.get('system_defects') or {}).get('events') or (r.get('system_defects') or {}).get('stop') for r in prior):
   state['skipped'].append({'case':case,'reason':'Same original question already produced one system_defect'});save(path,state);continue
  if (BATCH/'safety_stop.json').exists():state['stop_reason']='safety_stop';break
  state.update(active_case=case,active_started_utc=now());save(path,state)
  with (BATCH/(case+'.driver.log')).open('w') as log:
   result=subprocess.run([str(PY),str(SOURCE/'agent/experiments/round24/run_one.py'),case],stdout=log,stderr=subprocess.STDOUT)
  folder=BATCH/('case_'+case);summary=folder/'summary.json'
  if result.returncode or not summary.exists():state['stop_reason']='driver_uncertain_no_retry';save(path,state);break
  data=json.loads(summary.read_text());state['finished'].append(case);state['last_status']=data.get('status');save(path,state)
  subprocess.run([str(REF),str(SOURCE/'agent/experiments/round24/host_verifier.py'),'grade','--batch',str(BATCH),'--case',case],stdout=(folder/'host_grade.log').open('w'),stderr=subprocess.STDOUT,check=True)
  if data.get('client_error') or data.get('http_status')!=200:state['stop_reason']='interface_or_authorization_failure_no_duplicate';break
  ledger=json.loads((BATCH/'http_ledger.json').read_text());attempts=[x for x in ledger['attempts'] if x['case']==case]
  if any(x.get('status_code') in (401,403) for x in attempts):state['stop_reason']='upstream_authentication_failure';break
  # Existing per-question first-defect rule is also enforced inside the model loop.
  time.sleep(1)
 state.update(active_case=None,ended_utc=now(),status='closed');save(path,state)
 auth=json.loads((BATCH/'authorization.json').read_text());auth['status']='closed_batch';auth['batch_ended_utc']=now();save(BATCH/'authorization.json',auth)
 print(json.dumps({'status':'closed','finished':state['finished'],'skipped':state['skipped'],'stop_reason':state.get('stop_reason'),'real_analysis_runs':auth['real_analysis_runs']}))
if __name__=='__main__':main()
