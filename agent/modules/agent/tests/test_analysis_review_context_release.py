"""Engineering regressions for long feedback and trusted server knowledge default."""
import hashlib,importlib.util,json,pathlib,types
import pytest
BASE=pathlib.Path(__file__).resolve().parents[1]/'backend'
def load(name,file):
 s=importlib.util.spec_from_file_location(name,BASE/file);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
m=load('review_v2','analysis_internal_review.py')
h=load('release_candidate','analysis_release.py')
@pytest.fixture
def w(tmp_path):
 p=tmp_path/'workspace';p.mkdir()
 r=p.parent/'.execution_receipts'/p.name;r.mkdir(parents=True)
 j=p.parent/'.analysis_feedback'/p.name;j.mkdir(parents=True)
 for i in range(24):
  name='script_'+str(i)+'.py';raw=('print("engineering fixture")\n'+'# long fixture\n'*1800).encode();(p/name).write_bytes(raw)
  (r/(str(i)+'.json')).write_text(json.dumps({'receipt_id':str(i),'timestamp':i,'script':'/work/'+name,'script_sha256_before':hashlib.sha256(raw).hexdigest(),'result':{'status':'success','exit_code':0,'stdout':'x'*12000,'stderr':'y'*9000}}))
  (j/(str(i)+'.json')).write_text(json.dumps({'id':str(i),'time':i,'kind':'observation','tool':'write_code','failed':True,'arguments':{'code':'x'*20000},'result':{'error':'x'*15000}}))
 (p/'report.md').write_text('z'*24000);(p/'.env').write_text('not part of evidence')
 return p
def test_long_context_is_bounded_with_explicit_omissions(w):
 c,ids=m.collect_context(w,'engineering'*2000,{'artifacts':[]})
 assert len(json.dumps(c,ensure_ascii=False))<=180000
 assert len(c['actual_execution_receipts'])==24
 assert len([f for f in c['files'].values()if f['role']=='executed_code'])==24
 assert any(f.get('truncated')for f in c['files'].values())
 assert c['task_truncated']and '.env'not in c['files']
 assert all(len(x['result']['stdout']['json_preview'])<=320 for x in c['actual_execution_receipts'])
def test_unknown_failed_method_is_not_reloaded(w):
 j=w.parent/'.analysis_feedback'/w.name
 (j/'failedmethod.json').write_text(json.dumps({'id':'bad','time':99,'kind':'observation','tool':'read_analysis_method','failed':True,'arguments':{'method_id':'unknown'},'result':{'error':'Unknown method'}}))
 def no(mid):raise AssertionError('failed read cannot be evidence')
 c,_=m.collect_context(w,'fixture',{'artifacts':[]},no)
 assert not c['method_source_evidence']
def test_duplicate_execution_does_not_duplicate_source_text(w):
 r=w.parent/'.execution_receipts'/w.name
 data=json.loads((r/'1.json').read_text());data['receipt_id']='repeat';data['timestamp']=100
 (r/'repeat.json').write_text(json.dumps(data))
 c,_=m.collect_context(w,'fixture',{'artifacts':[]})
 assert len(c['actual_execution_receipts'])==25
 assert len([f for f in c['files'].values()if f['role']=='executed_code'])==24
def fixture_manifest(tmp_path):
 root=tmp_path/'public_release';root.mkdir();raw=b'{"candidate":true}';(root/'config.json').write_bytes(raw)
 p=tmp_path/'pointer.json';p.write_text(json.dumps({'schema':'primatex.research_release_pointer.v1','root':str(root),'config_sha256':hashlib.sha256(raw).hexdigest()}))
 return p,root
def test_default_pointer_is_hash_pinned_without_env(monkeypatch,tmp_path):
 monkeypatch.delenv('AGENT_RESEARCH_EVIDENCE_ROOT',raising=False);p,root=fixture_manifest(tmp_path)
 assert h.configured_research_root(p)==root
def test_default_tampering_fails_closed(monkeypatch,tmp_path):
 monkeypatch.delenv('AGENT_RESEARCH_EVIDENCE_ROOT',raising=False);p,root=fixture_manifest(tmp_path)
 (root/'config.json').write_text('changed')
 with pytest.raises(ValueError,match='digest'):h.configured_research_root(p)
def test_explicit_empty_disables_default(monkeypatch,tmp_path):
 p,root=fixture_manifest(tmp_path);monkeypatch.setenv('AGENT_RESEARCH_EVIDENCE_ROOT','')
 assert h.configured_research_root(p)is None
def test_trusted_env_preserves_existing_override(monkeypatch,tmp_path):
 monkeypatch.setenv('AGENT_RESEARCH_EVIDENCE_ROOT',str(tmp_path))
 assert h.configured_research_root(tmp_path/'missing.json')==tmp_path
def test_symlink_pointer_rejected(monkeypatch,tmp_path):
 monkeypatch.delenv('AGENT_RESEARCH_EVIDENCE_ROOT',raising=False);p,root=fixture_manifest(tmp_path)
 link=tmp_path/'link.json';link.symlink_to(p)
 with pytest.raises(ValueError):h.configured_research_root(link)

