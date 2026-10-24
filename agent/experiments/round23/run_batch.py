"""Sequential authorized original-question runs, after the immutable offline gate."""
from pathlib import Path
import datetime,json,subprocess,sys,time
from round23_control import decision
ROOT=Path('/data/xuancheng/agent_v1');BATCH=ROOT/'retests/round23_20261024'
SOURCE=ROOT/'round23_source';PY=ROOT/'.venv-coding/bin/python'
assert json.loads((BATCH/'offline_release.json').read_text())['status']=='offline_passed_protected_reviewed'
assert not (BATCH/'batch_completed.json').exists()
consecutive_rate_limits=0
for question in ['G1','G2']:
    for index in range(1,4):
        completed=[json.loads(p.read_text()) for p in BATCH.glob('case_R23_'+question+'_*/summary.json')]
        stop=decision(completed)
        if stop['stop']:
            (BATCH/('stop_'+question+'.json')).write_text(json.dumps(stop,indent=2)+'\n');break
        case=f'R23_{question}_{index}'
        assert not (BATCH/('case_'+case)).exists()
        with (BATCH/(case+'.driver.log')).open('w') as log:
            result=subprocess.run([str(PY),str(SOURCE/'agent/experiments/round23/run_one_round23.py'),case],stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT)
        if result.returncode:raise RuntimeError('Driver failed; inspect paid request before continuing: '+case)
        summary=json.loads((BATCH/('case_'+case)/'summary.json').read_text())
        print(json.dumps({k:summary.get(k) for k in ['case','status','full_chain_passed','model_calls','failure_classification']},ensure_ascii=False),flush=True)
        category=(summary.get('failure_classification') or {}).get('category')
        if category=='environment_auth_failed':raise RuntimeError('Upstream authentication failure; stop entire batch')
        if summary.get('client_error'):raise RuntimeError('Client result is uncertain; inspect current server/native request before any further run')
        consecutive_rate_limits=consecutive_rate_limits+1 if category=='environment_rate_limited' else 0
        if consecutive_rate_limits>=2:raise RuntimeError('Two consecutive environment rate limits; stop batch')
        if consecutive_rate_limits:time.sleep(300)
(BATCH/'batch_completed.json').write_text(json.dumps({'completed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'actual_real_runs':json.loads((BATCH/'authorization.json').read_text())['real_analysis_runs'],'maximum':6},indent=2)+'\n')
