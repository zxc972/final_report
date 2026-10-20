"""Authenticated analysis file access, no model/provider calls."""
import hashlib,json,os,pathlib
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from modules.agent.backend import api,analysis_artifacts

def fixture(tmp_path):
 w=tmp_path/'alice/output';w.mkdir(parents=True);salt='analysis-file-unit-salt';(w.parent/'.auth.json').write_text(json.dumps({'salt':salt}))
 conversation='original-conversation';run='a'*32;h=hashlib.sha256(('alice\0'+conversation).encode()).hexdigest()[:32];out=w/'.analysis_runs'/h/run;out.mkdir(parents=True);(out/'table.tsv').write_bytes(b'id\tvalue\n1\t2.5\n')
 p={'conversationId':conversation,'runId':run,'path':'table.tsv','context':{'userId':'alice','workspaceDirectory':str(w),'userToken':api.sign_user_token('alice',salt)}}
 return w,out,p

def test_authenticated_exact_bytes_and_hash_without_model(tmp_path):
 w,out,p=fixture(tmp_path)
 with patch.object(api,'ACCESS_TOKEN',''):
  with TestClient(api.build_app())as c:r=c.post('/api/agent/analysis/artifact',json=p)
 assert r.status_code==200 and r.content==(out/'table.tsv').read_bytes();assert r.headers['x-content-sha256']==hashlib.sha256(r.content).hexdigest()
 assert r.headers['content-type']=='application/octet-stream' and 'attachment;'in r.headers['content-disposition']and r.headers['cache-control']=='no-store'
 assert p['context']['userToken']not in r.text
@pytest.mark.parametrize('kind',['no_token','wrong_token','different_conversation','different_run','bad_run','traversal','absolute','hidden','receipt','backslash','symlink','directory','fifo'])
def test_auth_and_confined_regular_paths(tmp_path,kind):
 w,out,p=fixture(tmp_path);expected=None
 if kind=='no_token':p['context'].pop('userToken');expected=401
 if kind=='wrong_token':p['context']['userToken']='bad';expected=401
 if kind=='different_conversation':p['conversationId']='another';expected=404
 if kind=='different_run':p['runId']='b'*32;expected=404
 if kind=='bad_run':p['runId']='../alice';expected=422
 if kind=='traversal':p['path']='../table.tsv';expected=400
 if kind=='absolute':p['path']='/etc/passwd';expected=400
 if kind=='hidden':p['path']='.env';(out/'.env').write_text('fixture');expected=400
 if kind=='receipt':p['path']='../.execution_receipts/run.json';expected=400
 if kind=='backslash':p['path']='folder\\table.tsv';expected=400
 if kind=='symlink':
  target=tmp_path/'outside.txt';target.write_text('not downloadable');(out/'link.txt').symlink_to(target);p['path']='link.txt';expected=400
 if kind=='directory':(out/'folder').mkdir();p['path']='folder';expected=404
 if kind=='fifo':os.mkfifo(out/'pipe');p['path']='pipe';expected=400
 with patch.object(api,'ACCESS_TOKEN',''):
  with TestClient(api.build_app())as c:r=c.post('/api/agent/analysis/artifact',json=p)
 assert r.status_code==expected,(kind,r.status_code,r.text)
def test_oversize_response_is_explicit_not_truncated(tmp_path):
 w,out,p=fixture(tmp_path)
 with patch.object(api,'ACCESS_TOKEN',''),patch.object(analysis_artifacts,'MAX_DOWNLOAD_BYTES',4):
  with TestClient(api.build_app())as c:r=c.post('/api/agent/analysis/artifact',json=p)
 assert r.status_code==413


def test_source_catalog_tracks_protected_execution_hashes_and_current_edits(tmp_path):
 w,out,p=fixture(tmp_path);code=out/'analysis.py';code.write_text('print(1)\n');sha=hashlib.sha256(code.read_bytes()).hexdigest();receipts=out.parent/'.execution_receipts'/p['runId'];receipts.mkdir(parents=True)
 receipt={'script':'/work/analysis.py','script_sha256_before':sha,'script_sha256_after':sha,'result':{'status':'success','exit_code':0}}
 (receipts/'receipt.json').write_text(json.dumps(receipt))
 found=analysis_artifacts.list_generated_scripts(w,'alice',p['conversationId'],p['runId']);assert len(found)==1 and found[0]['path']=='analysis.py'and found[0]['matches_executed_code']
 assert found[0]['executions'][0]['exit_code']==0
 code.write_text('print(2)\n');found=analysis_artifacts.list_generated_scripts(w,'alice',p['conversationId'],p['runId']);assert not found[0]['matches_executed_code']
 assert analysis_artifacts.list_generated_scripts(w,'alice','other-conversation',p['runId'])==[]
 assert analysis_artifacts.list_generated_scripts(w,'alice',p['conversationId'],None)==[]
