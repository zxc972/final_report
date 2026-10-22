import csv
from pathlib import Path
from backend.analysis_profile_worker import table_metadata, profile_file
from backend.analysis_template_bindings import product_view
from backend.analysis_condition_templates import design_variable

def test_table_profile_and_design_view(tmp_path):
    p=tmp_path/'participants.csv';p.write_text('subject_id,age,sex,site\ns1,20,F,A\ns2,21,M,A\nextra,,F,B\n')
    m=table_metadata(p,'subject_id',['s1','s2','missing'])
    assert m['row_count']==3 and m['nonempty_counts']['age']==2
    assert m['column_types']['age']=='numeric' and m['levels']['sex']=={'F':2,'M':1}
    assert m['matched_count']==2 and m['unmatched_ids']==['extra']
    assert m['registered_without_row']==['missing']
    view=product_view(profile_file(p))
    assert view['attributes']['columns']==['subject_id','age','sex','site']
    assert design_variable({'slot':'table','variable':'sex'},{'slots':{'table':[view]}})['verdict']=='pass'
    assert design_variable({'slot':'table','variable':'age'},{'slots':{'table':[view]}})['verdict']=='block'

def test_duplicate_ids_rejected(tmp_path):
    import pytest
    p=tmp_path/'participants.tsv';p.write_text('id\tage\ns\t20\ns\t22\n')
    with pytest.raises(ValueError,match='unique'):table_metadata(p,'id')
