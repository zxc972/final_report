"""Read-only raw group rows and identity-based BH across 62 regions x 2 hemispheres."""
import csv
import importlib
import json
from pathlib import Path
import random
import numpy as np
import pytest
import nibabel as nib
from backend import primatex_ops as ops
from backend.analysis_group_stats import fdr_bh


def inputs(tmp_path):
    labels=tmp_path/'labels.json';groups={};bindings=[]
    for h in ['rh','lh']:
        metric=tmp_path/(h+'.curv');nib.freesurfer.write_morph_data(str(metric),np.array([9,0,np.nan,3],dtype=np.float32))
        annot=tmp_path/(h+'.annot');nib.freesurfer.write_annot(str(annot),np.array([0,1,1,1]),np.array([[0,0,0,0],[20,40,80,0]]),[b'unknown',b'same_name'])
        mask=tmp_path/(h+'.label');mask.write_text('#!ascii label\n3\n1 0 0 0 0\n2 0 0 0 0\n3 0 0 0 0\n')
        scope='synthetic/'+h;groups[scope]={'labels':[{'key':1,'name':'same_name'}]}
        bindings.append({'hemisphere':h,'metric':'curv','metric_path':str(metric),'annotation_path':str(annot),'mask_path':str(mask),'label_set_scope':scope})
    labels.write_text(json.dumps(groups));path=tmp_path/'manifest.json';path.write_text(json.dumps({'subjects':{'subject-B':bindings,'subject-A':bindings},'label_sets_ref':{'path':str(labels)}}));return path


def test_group_reader_returns_sorted_raw_values_and_never_writes_inputs(tmp_path):
    path=inputs(tmp_path);before={str(p):p.read_bytes() for p in tmp_path.iterdir() if p.is_file()}
    rows=ops.read_group_inputs(path)
    keys=[tuple(r[k] for k in ['subject','hemisphere','metric','label_key']) for r in rows]
    assert keys==sorted(keys) and len(set(keys))==4
    assert rows[0]['values'][0]==0 and np.isnan(rows[0]['values'][1])
    assert rows[0]['values'].flags.writeable is False
    assert 'mean' not in rows[0] and 'p' not in rows[0]
    assert before=={str(p):p.read_bytes() for p in tmp_path.iterdir() if p.is_file()}


def test_reader_rejects_duplicate_identity_and_wrong_structure(tmp_path):
    path=inputs(tmp_path);d=json.loads(path.read_text());d['subjects']['subject-A']*=2;path.write_text(json.dumps(d))
    with pytest.raises(ValueError,match='Duplicate regional identity'):ops.read_group_inputs(path)
    d['subjects']=[];path.write_text(json.dumps(d))
    with pytest.raises(ValueError,match='dict'):ops.read_group_inputs(path)


def test_fdr_62_by_two_hemispheres_csv_roundtrip_has_no_name_or_position_join(tmp_path):
    rows=[{'hemisphere':h,'metric':'curv','label_key':i,'name':'same_'+str(i),'p':((i*13+(0 if h=='lh' else 7))%127+1)/128.} for h in ['lh','rh'] for i in range(1,63)]
    random.Random(21).shuffle(rows)
    keys=[(r['hemisphere'],r['metric'],r['label_key']) for r in rows]
    expected=dict(zip(keys,fdr_bh([r['p'] for r in rows])))
    q=ops.fdr_bh_by_identity({k:r['p'] for k,r in zip(keys,rows)})
    random.Random(73).shuffle(rows)
    for r in rows:r['q_fdr']=q[(r['hemisphere'],r['metric'],r['label_key'])]
    path=tmp_path/'results.csv'
    with path.open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    with path.open() as f:observed=list(csv.DictReader(f))
    assert len(observed)==124 and len({r['name'] for r in observed})==62
    for r in observed:assert float(r['q_fdr'])==pytest.approx(expected[(r['hemisphere'],r['metric'],int(r['label_key']))],abs=1e-15)


@pytest.mark.parametrize('p',[float('nan'),float('inf'),-0.1,1.1,True,'0.1'])
def test_fdr_rejects_invalid_fitted_probability(p):
    with pytest.raises(ValueError):ops.fdr_bh_by_identity({('lh','curv',1):p})


def test_fdr_unfitted_partition_stays_none_and_family_is_global():
    values={('lh','curv',1):.01,('rh','curv',1):.04,('lh','other',1):.02,('rh','other',2):None}
    result=ops.fdr_bh_by_identity(values)
    assert result[('rh','other',2)] is None
    assert result[('lh','curv',1)]==pytest.approx(.03)
    assert result[('lh','other',1)]==pytest.approx(.03)
    assert result[('rh','curv',1)]==pytest.approx(.04)


def test_host_group_reference_never_imports_sandbox_fdr(tmp_path,monkeypatch):
    from round14_fixture import fixture,p
    from test_analysis_agent import agent
    numeric=importlib.import_module(agent.__package__+'.analysis_independent_numeric')
    tools,intent=fixture(tmp_path,monkeypatch)
    planned=tools.plan_analysis(intent)
    p.commit_candidate(tools,planned['candidates'][0]['candidate_id'],'Synthetic boundary regression','/work/group.py')
    plan=tools.control_store.latest('plan')['record']['plan']
    bundle=tools.control_store.latest('execution_bundle')['record']
    def forbidden(*args,**kwargs):raise AssertionError('Host reference must not share sandbox BH')
    monkeypatch.setattr(ops,'fdr_bh_by_identity',forbidden)
    rows=numeric.reference_rows(tools,plan,bundle,'group_regional_glm')
    assert set(rows)=={'regional_values.csv','group_results.csv'}
    assert any(r['q_fdr'] is not None for r in rows['group_results.csv'][0])
