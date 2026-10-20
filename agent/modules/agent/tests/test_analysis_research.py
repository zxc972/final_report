import json,hashlib,pathlib,sys,importlib.util,os
import pytest
spec=importlib.util.spec_from_file_location('under_test',pathlib.Path(__file__).resolve().parents[1]/'backend'/'analysis_research.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);Research=mod.ResearchEvidenceRetriever
@pytest.fixture
def bundle(tmp_path):
 r=tmp_path/'release';r.mkdir();worker="""import sys,json,os
p=json.loads(sys.stdin.read())
if p.get('query')=='FAIL':print(json.dumps({'status':'error','error_type':'test_error'}));sys.exit(1)
if p.get('query')=='BROKEN':print('invalid');sys.exit(0)
print(json.dumps({'status':'ok','query':p.get('query'),'source_id':p.get('source_id'),'credential_present':bool(os.environ.get('OPENAI_API_KEY')),'trust':'untrusted_candidate_evidence','executable':False}))
"""
 for n,t in [('worker.py',worker),('documents.json','[]'),('domain_graph.json','{"nodes":[],"edges":[]}')]: (r/n).write_text(t)
 c={'schema':'primatex.research_retrieval.v1','python':sys.executable}
 for n,k in [('worker.py','worker_sha256'),('documents.json','documents_sha256'),('domain_graph.json','domain_graph_sha256')]:c[k]=hashlib.sha256((r/n).read_bytes()).hexdigest()
 (r/'config.json').write_text(json.dumps(c));return r

def test_query_runs_registered_worker_no_shell(bundle,tmp_path):
 a=Research(bundle);query='; touch '+str(tmp_path/'should_never_exist')
 r=a.search(query);assert r['query']==query and r['executable'] is False and r['retrieval_provider_http_calls']==0
 assert not (tmp_path/'should_never_exist').exists()
def test_credentials_not_passed_to_worker(bundle,monkeypatch):
 monkeypatch.setenv('OPENAI_API_KEY','synthetic-test-only');assert Research(bundle).search('volume')['credential_present'] is False
@pytest.mark.parametrize('target',['worker.py','documents.json','domain_graph.json'])
def test_changed_release_rejected_before_execution(bundle,target):
 a=Research(bundle);(bundle/target).write_text('modified');
 with pytest.raises(ValueError,match='digest'):a.search('volume')
@pytest.mark.parametrize('query,limit',[('',3),('x'*1001,3),('volume',True),('volume',0),('volume',9)])
def test_query_bounds(bundle,query,limit):
 with pytest.raises(ValueError):Research(bundle).search(query,limit)
@pytest.mark.parametrize('terms',[['x'*151],['x']*9,'not-a-list',[12]])
def test_keyword_bounds(bundle,terms):
 with pytest.raises(ValueError):Research(bundle).search('volume',high_level_keywords=terms)
@pytest.mark.parametrize('source',['../../config.json','/etc/passwd','name\\path','a\x00b'])
def test_source_ids_are_not_paths(bundle,source):
 with pytest.raises(ValueError):Research(bundle).read(source)
def test_worker_error_not_success(bundle):
 with pytest.raises(ValueError,match='test_error'):Research(bundle).search('FAIL')
def test_bad_worker_protocol_rejected(bundle):
 with pytest.raises(ValueError,match='invalid JSON'):Research(bundle).search('BROKEN')
def test_relative_runtime_rejected(bundle):
 c=json.loads((bundle/'config.json').read_text());c['python']='python';(bundle/'config.json').write_text(json.dumps(c))
 with pytest.raises(ValueError):Research(bundle)
def test_symlink_source_rejected(bundle,tmp_path):
 outside=tmp_path/'outside';outside.write_text('[]');(bundle/'documents.json').unlink();(bundle/'documents.json').symlink_to(outside)
 with pytest.raises(ValueError):Research(bundle)
def test_source_read_is_bounded_and_marked(bundle):
 r=Research(bundle).read('LONG',0,500);assert r['source_id']=='LONG' and r['executable'] is False and 'release_sha256' in r
