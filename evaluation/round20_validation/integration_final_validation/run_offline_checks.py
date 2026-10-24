from pathlib import Path
from datetime import datetime,timezone
import subprocess,os,json
w=Path('/data/xuancheng/agent_v1/round20_source');work=w.parent/'round20_work/integration_final_validation'
env=dict(os.environ);env.update(PYTHONPATH=f'{w}:{w}/agent:{w}/agent/modules/agent:/data/xuancheng/agent_v1/.venv-reference/lib/python3.11/site-packages',ANALYSIS_REFERENCE_PYTHON='/data/xuancheng/agent_v1/.venv-reference/bin/python',AGENT_RESEARCH_EVIDENCE_ROOT=str(w/'knowledge/research_v13'),PYTHONDONTWRITEBYTECODE='1')
prior=dict(p.decode().split('=',1) for p in Path('/proc/4144167/environ').read_bytes().split(b'\0') if b'=' in p)
for key in ['ANALYSIS_RUNTIME_IMAGE','ANALYSIS_RUNTIME_ENV','ANALYSIS_CONTAINER_CMD','PATH','TMPDIR']:
 if key in prior:env[key]=prior[key]
py='/data/xuancheng/agent_v1/.venv-coding/bin/python'
checks=[('new_integration',['-m','pytest','-q','modules/agent/tests/test_round20_region_integration.py','modules/agent/tests/test_round20_condition_cards_v2.py'],False),('region_algorithm',['-m','pytest','-q','modules/agent/tests/test_round20_region_resolver.py'],False),('sdk_binding',['-m','pytest','-vv','modules/agent/tests/test_round21_sdk_http_observer.py','--junitxml',str(work/'sdk_binding.junit.xml')],False),('targeted_merged',['-m','pytest','-q','modules/agent/tests/test_round21_feedback_planning.py','modules/agent/tests/test_round21_group_interfaces.py','modules/agent/tests/test_round21_sdk_http_observer.py','modules/agent/tests/test_round8_closure.py','modules/agent/tests/test_round13_planning.py','modules/agent/tests/test_round14_group_planner.py'],False),('backend_default_merged',['-m','pytest','-q','modules/agent/tests'],False),('synthetic_singularity_merged',['-m','pytest','-q','modules/agent/tests/test_round21_full_sandbox.py','--basetemp',str(work/'synthetic_container_runs_merged')],True)]
for name,args,sandbox in checks:
 local=dict(env)
 if sandbox:local['PRIMATEX_RUN_SANDBOX_TESTS']='1'
 started=datetime.now(timezone.utc).isoformat()
 with (work/(name+'.log')).open('w') as log:
  p=subprocess.run([py,*args],cwd=w/'agent',env=local,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT)
 status={'check':name,'exit_code':p.returncode,'started_utc':started,'ended_utc':datetime.now(timezone.utc).isoformat(),'provider_requests':0}
 (work/(name+'.status.json')).write_text(json.dumps(status,indent=2)+'\n');print(json.dumps(status),flush=True)
 if p.returncode:raise SystemExit(p.returncode)
(work/'offline_all_passed.json').write_text(json.dumps({'status':'passed','checks':[x[0] for x in checks],'provider_requests':0,'real_analysis_requests':0},indent=2)+'\n')
