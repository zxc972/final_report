from pathlib import Path
import json
import subprocess
import time
root=Path('/data/xuancheng/agent_round11_trial_20261022')
assert json.loads((root/'provider_budget.json').read_text())['http_started']==0
assert not (root/'audit/driver_process.json').exists()
with (root/'audit/B_dispatch.log').open('ab') as log:
    process=subprocess.Popen(['/data/software/anaconda3/bin/python','-B',str(root/'run_six_trials.py')],cwd=root,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
(root/'audit/driver_process.json').write_text(json.dumps({'pid':process.pid,'started':time.time(),'maximum_runs':6,'batch_logical_limit':180,'batch_http_limit':540},indent=2))
state=json.loads((root/'state.json').read_text())
state.update(status='running_final_code_cohort',driver_pid=process.pid,paid_backend_commit=json.loads((root/'audit/trial_source_freeze.json').read_text())['backend_head'])
(root/'state.json').write_text(json.dumps(state,indent=2))
print(json.dumps({'started_driver':process.pid,'maximum_runs':6,'batch_logical_limit':180,'batch_http_limit':540}))
