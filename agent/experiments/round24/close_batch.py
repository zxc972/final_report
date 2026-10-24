"""Close only the new Round24 loopback process after a closed, immutable batch."""
import collections,datetime as dt,hashlib,json,os,signal,subprocess,time
from pathlib import Path
ROOT=Path('/data/xuancheng/agent_v1'); BATCH=ROOT/'retests/round24_20261024'; SOURCE=ROOT/'round24_source'
def load(name): return json.loads((BATCH/name).read_text())
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
state=load('batch_status.json'); auth=load('authorization.json'); ledger=load('http_ledger.json'); release=load('offline_release.json'); freeze=load('freeze.json')
assert state['status']=='closed' and state['active_case'] is None and len(state['finished'])==12
assert auth['real_analysis_runs']==12 and ledger['http_attempts']==180
assert all(x.get('status')!='started' for x in ledger['attempts'])
assert all(sha(Path(k))==v for k,v in freeze['input_sha256'].items())
assert all(sha(SOURCE/k)==v for k,v in release['runtime_source_sha256'].items())
assert subprocess.check_output(['git','-C',str(SOURCE),'rev-parse','HEAD'],text=True).strip()==freeze['source_commit']
old=Path('/proc/4144167'); assert old.exists()
old_stat=old.joinpath('stat').read_text().split()[21]
pid=551960; proc=Path('/proc')/str(pid)
receipt={'closed_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'batch_closed':True,'entries':12,'http_attempts':180,'frozen_inputs_unchanged':True,'frozen_actor_source_unchanged':True,'frozen_source_commit':freeze['source_commit'],'development_pid':pid,'existing_service_pid':4144167,'existing_service_start_ticks':old_stat,'existing_service_signalled':False,'deployment':False,'restart_existing_service':False,'additional_model_calls':0}
if proc.exists():
 cmd=[x.decode() for x in proc.joinpath('cmdline').read_bytes().split(b'\0') if x]
 assert cmd==[str(ROOT/'.venv-coding/bin/python'),'-B',str(SOURCE/'agent/experiments/round24/dev_server.py')], 'Unexpected process identity; no signal sent'
 os.kill(pid,signal.SIGTERM)
 for i in range(40):
  if not proc.exists() or proc.joinpath('stat').read_text().split()[2]=='Z': break
  time.sleep(.25)
 assert not proc.exists() or proc.joinpath('stat').read_text().split()[2]=='Z', 'Development process still active'
 receipt['development_close_action']='SIGTERM after exact cmdline and closed-ledger checks'
else: receipt['development_close_action']='already absent; no signal'
assert old.exists() and old.joinpath('stat').read_text().split()[21]==old_stat
receipt['original_service_alive_unchanged']=True
receipt['private_records_retained_in_place']=str(BATCH)
(BATCH/'closeout.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt))
