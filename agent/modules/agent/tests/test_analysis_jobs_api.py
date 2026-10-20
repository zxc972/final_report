"""Authenticated job status/cancellation tests; no provider calls."""
import hashlib,json,os,sys
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from modules.agent.backend import api,analysis_jobs as jobs
def fixture(tmp_path):
 w=tmp_path/'alice/output';w.mkdir(parents=True);salt='job-status-fixture';(w.parent/'.auth.json').write_text(json.dumps({'salt':salt}))
 conv='owner-conversation';run='a'*32;digest=hashlib.sha256(('alice\0'+conv).encode()).hexdigest()[:32]
 work=w/'.analysis_runs'/digest/run;work.mkdir(parents=True);(work/'calc.py').write_text('pass\n')
 d=tmp_path/'data';d.mkdir();(d/'x').write_text('fixture')
 with patch.dict(os.environ,{'ANALYSIS_ENABLE_BACKGROUND_JOBS':'1'}):
  job=jobs.submit(work,[d],work/'calc.py',180,[{'path':'summary.json','kind':'json'}],['summary.json'],lambda:None,launcher=lambda p:os.getpid())
 payload={'conversationId':conv,'runId':run,'jobId':job['job_id'],'context':{'userId':'alice','workspaceDirectory':str(w),'userToken':api.sign_user_token('alice',salt)}}
 return w,work,job,payload
@pytest.mark.parametrize('endpoint',['status','cancel'])
def test_authenticated_real_routes_without_model(tmp_path,endpoint):
 w,work,job,p=fixture(tmp_path)
 with patch.object(api,'ACCESS_TOKEN',''),patch.object(jobs.os,'kill')as kill:
  with TestClient(api.build_app())as c:r=c.post('/api/agent/analysis/job/'+endpoint,json=p)
 assert r.status_code==200,r.text
 assert r.json()['metadata']['status']=='queued' and not r.json()['metadata']['validation'].get('valid')
 assert r.json()['metadata']['analysis_jobs'][0]['job_id']==job['job_id']
 assert 'provider_requests_in_worker' in r.text and p['context']['userToken']not in r.text
 if endpoint=='cancel':kill.assert_called_once_with(os.getpid(),jobs.signal.SIGTERM)
 else:kill.assert_not_called()
@pytest.mark.parametrize('endpoint',['status','cancel'])
@pytest.mark.parametrize('change,expected',[('no_token',401),('bad_token',401),('other_conversation',404),('other_run',404),('other_job',404),('bad_job',422),('bad_run',422),('symlink_run',404)])
def test_job_owner_and_identifier_scope(tmp_path,endpoint,change,expected):
 w,work,job,p=fixture(tmp_path)
 if change=='no_token':p['context'].pop('userToken')
 if change=='bad_token':p['context']['userToken']='invalid'
 if change=='other_conversation':p['conversationId']='other'
 if change=='other_run':p['runId']='b'*32
 if change=='other_job':p['jobId']='b'*32
 if change=='bad_job':p['jobId']='../other'
 if change=='bad_run':p['runId']='../other'
 if change=='symlink_run':
  alias=work.parent/('b'*32);alias.symlink_to(work,target_is_directory=True);p['runId']='b'*32
 with patch.object(api,'ACCESS_TOKEN',''),patch.object(jobs.os,'kill')as kill:
  with TestClient(api.build_app())as c:r=c.post('/api/agent/analysis/job/'+endpoint,json=p)
 assert r.status_code==expected,(endpoint,change,r.status_code,r.text)
 kill.assert_not_called()
def test_wrong_pid_identity_never_cancelled(tmp_path):
 w,work,job,p=fixture(tmp_path);root=jobs._job_root(work)/job['job_id'];jobs._write(root/'launch.json',root,{'pid':os.getpid(),'start_ticks':'wrong'})
 with patch.object(api,'ACCESS_TOKEN',''),patch.object(jobs.os,'kill')as kill:
  with TestClient(api.build_app())as c:r=c.post('/api/agent/analysis/job/cancel',json=p)
 assert r.status_code==200;kill.assert_not_called()
def test_lower_executor_reaps_own_child_on_interruption():
 from modules.agent.backend.analysis_executor import _run_bounded
 process=type('P',(),{'stdout':None,'stderr':None})()
 with patch('modules.agent.backend.analysis_executor.subprocess.Popen',return_value=process),patch('modules.agent.backend.analysis_executor.threading.Thread')as th,patch('modules.agent.backend.analysis_executor._terminate_group')as stop:
  process.wait=lambda timeout:(_ for _ in ()).throw(KeyboardInterrupt())
  with pytest.raises(KeyboardInterrupt):_run_bounded(['fixture'],timeout_seconds=1,env={},output_limit_bytes=1024)
  stop.assert_called_once_with(process)