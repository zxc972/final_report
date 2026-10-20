"""Focused checks for method evidence bounds, condition unknowns, and actual-feedback provenance."""
import hashlib,importlib.util,json,pathlib,sys
import pytest
from backend.analysis_method_graph import MethodGraph
from backend.analysis_feedback import FeedbackJournal
@pytest.fixture
def release(tmp_path):
 r=tmp_path/'release';r.mkdir()
 claim={'id':'condition:pial','statement':'Pial surface must exist','source_id':'s','quote':'pial surface','claim_type':'direct'}
 method={'id':'method:lgi','name':'local gyrification','purpose':'folding','source_ids':['s'],'software':['FreeSurfer'],'inputs':[claim],'conditions':[],'steps':[]}
 obj={'schema':'primatex.method_graph.v1','methods':[method],'nodes':[{'id':method['id'],'type':'AnalysisMethod'},{'id':claim['id'],'type':'InputRequirement'}],'edges':[{'source':method['id'],'target':claim['id'],'type':'REQUIRES_INPUT'}],'sources':[{'id':'s','url':'https://example.org/source','evidence_class':'official_documentation','text_sha256':'0'*64}]}
 raw=json.dumps(obj).encode();(r/'method_graph.json').write_bytes(raw);(r/'config.json').write_text(json.dumps({'method_graph_sha256':hashlib.sha256(raw).hexdigest()}))
 return r
def test_method_has_explicit_source_and_relations(release):
 x=MethodGraph(release).read('method:lgi')
 assert x['relations'][0]['type']=='REQUIRES_INPUT' and x['source_evidence'][0]['url'].startswith('https://') and not x['executable']
def test_missing_observations_stay_unknown(release):
 x=MethodGraph(release).assess('method:lgi',[])
 assert x['condition_coverage_status']=='unknown' and len(x['unresolved'])==1 and x['eligible_for_automatic_execution']is False
def test_declarations_do_not_become_trusted_measurements(release):
 x=MethodGraph(release).assess('method:lgi',[{'condition_id':'condition:pial','status':'supported','observation_ref':'actual_execution:abc','reason':'observed'}])
 assert x['condition_coverage_status']=='all_declared_supported'and x['eligible_for_automatic_execution']is False and 'Model-declared'in x['observation_trust']
def test_contradiction_is_not_lost(release):
 x=MethodGraph(release).assess('method:lgi',[{'condition_id':'condition:pial','status':'contradicted','observation_ref':'tool:abc'}])
 assert x['condition_coverage_status']=='contradicted'
@pytest.mark.parametrize('items',[[{'condition_id':'invented','status':'supported'}],[{'condition_id':'condition:pial','status':'supported'}],[{'condition_id':'condition:pial','status':'success'}]])
def test_unregistered_or_unsubstantiated_conditions_rejected(release,items):
 with pytest.raises(ValueError):MethodGraph(release).assess('method:lgi',items)
def test_duplicate_observations_rejected(release):
 v={'condition_id':'condition:pial','status':'unknown'}
 with pytest.raises(ValueError):MethodGraph(release).assess('method:lgi',[v,v])
def test_changed_graph_fails_closed(release):
 g=MethodGraph(release);(release/'method_graph.json').write_text('{}')
 with pytest.raises(ValueError,match='digest'):g.search('area')
def test_unknown_id_not_arbitrary_path(release):
 with pytest.raises(ValueError):MethodGraph(release).read('../../secret')
def test_symlink_graph_rejected(release,tmp_path):
 (release/'method_graph.json').rename(tmp_path/'g.json');(release/'method_graph.json').symlink_to(tmp_path/'g.json')
 with pytest.raises(ValueError):MethodGraph(release)
@pytest.mark.parametrize('q,k',[('',1),('area',True),('x'*1001,2),('area',9)])
def test_query_bounds(release,q,k):
 with pytest.raises(ValueError):MethodGraph(release).search(q,k)
def test_no_study_answer_in_feedback(tmp_path):
 w=tmp_path/'work';w.mkdir();j=FeedbackJournal(w)
 o=j.observe('run_python',{'path':'/work/main.py'},{'status':'failed','returncode':1,'stderr':'ValueError: invalid argument'})
 r=j.reflect(o['id'],'The argument may have the wrong type.','Inspect actual CLI help and log before changing the argument.',[])
 assert r['verification_status']=='hypothesis_only_not_yet_verified'
 q=j.recent();assert q['total_failures']==1 and q['total_reflections']==1 and j.root.parent.parent==w.parent
 assert not j.root.is_relative_to(w)
 assert 'expected_values'not in json.dumps(q)
def test_reflecting_success_is_not_failure_recovery(tmp_path):
 w=tmp_path/'w';w.mkdir();j=FeedbackJournal(w);o=j.observe('run_python',{}, {'status':'success','returncode':0})
 with pytest.raises(ValueError):j.reflect(o['id'],'A supposed failure occurred.','I should inspect the logs before another attempt.')
@pytest.mark.parametrize('oid',['../../key','unknown','0'*32])
def test_cannot_forge_failure_id(tmp_path,oid):
 w=tmp_path/'w';w.mkdir();j=FeedbackJournal(w)
 with pytest.raises((ValueError,FileNotFoundError)):j.reflect(oid,'An unverified failure hypothesis.','Inspect actual tool output before drawing conclusions.')
def test_later_success_does_not_erase_original_failure(tmp_path):
 w=tmp_path/'w';w.mkdir();j=FeedbackJournal(w)
 j.observe('run_python',{}, {'status':'failed','returncode':1})
 j.observe('run_python',{}, {'status':'success','returncode':0})
 r=j.recent();assert r['total_failures']==1 and len(r['recent_execution_observations'])==2
def test_no_code_dump_or_reflection_of_reflection(tmp_path):
 w=tmp_path/'w';w.mkdir();j=FeedbackJournal(w)
 x=j.observe('write_code',{'code':'print(123)','path':'main.py'},{'status':'ok'})
 assert 'code'not in x['arguments']and len(x['arguments']['declared_code_sha256'])==64
 assert j.observe('read_analysis_feedback',{}, {'status':'ok'})is None

