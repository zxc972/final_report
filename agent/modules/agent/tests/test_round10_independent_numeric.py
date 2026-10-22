"""Independent host ROI readers, scope binding, mutation rejection and privacy."""
import copy
import csv
import importlib
import json
from pathlib import Path
import struct
from types import SimpleNamespace

import pytest
from test_analysis_agent import agent

numeric=importlib.import_module(agent.__package__+'.analysis_independent_numeric')
reader=importlib.import_module(agent.__package__+'.analysis_numeric_reference')
control=importlib.import_module(agent.__package__+'.analysis_control_store')


def write_inputs(root,hemi='lh',new_table=False):
    (root/'surf').mkdir(exist_ok=True)
    (root/'label').mkdir(exist_ok=True)
    values=[0.0,1.23456789,1.87654321,2.34567891,3.23456789]
    metric=root/'surf'/(hemi+'.thickness')
    metric.write_bytes(b'\xff\xff\xff'+struct.pack('>iii',5,0,1)+struct.pack('>5f',*values))
    def encoded(text):
        raw=text.encode()+b'\0'
        return struct.pack('>i',len(raw))+raw
    colors=[0,1,1,2,2]
    raw=struct.pack('>i',5)+b''.join(struct.pack('>ii',i,key) for i,key in enumerate(colors))+struct.pack('>i',1)
    if new_table:
        raw+=struct.pack('>ii',-2,3)+encoded('synthetic')+struct.pack('>i',3)
    else:
        raw+=struct.pack('>i',3)+encoded('synthetic')
    for i,name in enumerate(['unknown','one','two']):
        raw+=(struct.pack('>i',i) if new_table else b'')+encoded(name)+struct.pack('>iiii',i,0,0,0)
    (root/'label'/(hemi+'.aparc.annot')).write_bytes(raw)
    (root/'label'/(hemi+'.cortex.label')).write_text('#!ascii synthetic\n5\n'+''.join(f'{i} 0 0 0 1\n' for i in range(5)))


def host_tools(tmp_path):
    work=tmp_path/'work'
    inputs=tmp_path/'inputs'
    work.mkdir()
    inputs.mkdir()
    write_inputs(inputs)
    files=['/inputs/0/surf/lh.thickness','/inputs/0/label/lh.aparc.annot','/inputs/0/label/lh.cortex.label']
    plan={'method':{'method_id':'method:v12:surface_annotation_roi'},'data':{'files':files,'subjects':['fixture']}}
    group={'annotation':files[1],'cortex_label':files[2],'labels':[{'key':1,'name':'one'},{'key':2,'name':'two'}]}
    bundle={'label_sets':{'fixture/lh':group},'operations':{'calls':[{'function':'parcel_summary','scope':'fixture/lh','inputs':{'metric_path':files[0]}}]},'output_contract':{'files':['summary.csv']}}
    store=control.ControlStore(tmp_path/'controls',[work,inputs])
    store.save('plan',{'plan':plan})
    store.save('execution_bundle',bundle)
    store.save('constraints',{'rows':[{'constraint_id':'synthetic_source','severity':'hard','verdict':'pass'}]})
    def resolve(path,**kwargs):
        if path.startswith('/inputs/0/'):
            return inputs/path.removeprefix('/inputs/0/')
        if path.startswith('/work/'):
            return work/path.removeprefix('/work/')
        raise ValueError('Unapproved synthetic path')
    tools=SimpleNamespace(control_store=store,resolve=resolve,workdir=work,last_execution={'receipt_id':'a'*32,'exit_code':0,'status':'success'})
    return tools,plan,bundle


@pytest.mark.parametrize('new_table',[False,True])
def test_independent_readers_accept_both_annotation_layouts(tmp_path,new_table):
    write_inputs(tmp_path,new_table=new_table)
    labels,names=reader.read_annotation(tmp_path/'label/lh.aparc.annot')
    assert labels==[-1,1,1,2,2] and names[2]=='two'
    assert len(reader.read_metric(tmp_path/'surf/lh.thickness'))==5
    assert reader.read_cortex(tmp_path/'label/lh.cortex.label',5)==set(range(5))


def write_csv(tools,rows):
    with (tools.workdir/'summary.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def test_host_pass_fail_card_and_current_receipt_binding(tmp_path):
    tools,plan,bundle=host_tools(tmp_path)
    rows=reader.roi_rows(plan,bundle,tools.resolve)
    write_csv(tools,rows)
    passed=numeric.verify(tools)
    assert passed['status']=='pass' and passed['checked']==10
    assert numeric.result_card(tools,'Synthetic supplied means only.')['verdict']=='accepted'
    altered=copy.deepcopy(rows)
    altered[0]['mean']+=0.1
    write_csv(tools,altered)
    failed=numeric.verify(tools)
    assert failed['status']=='fail' and failed['mismatch_count']==1
    card=numeric.result_card(tools,'Synthetic supplied means only.')
    assert card['verdict']=='blocked'
    assert 'expected' not in json.dumps(failed) and 'differences' not in json.dumps(card)
    private=tools.control_store.latest('independent_numeric_private')['record']
    assert 'expected' in private and private['plan_sha256']==tools.control_store.latest('plan')['sha256']
    assert not list(tools.workdir.glob('*independent*'))
    tools.last_execution['receipt_id']='b'*32
    assert numeric.current_summary(tools)['status']=='not_configured'


def test_unregistered_method_and_model_feedback_have_no_oracle(tmp_path):
    tools,plan,bundle=host_tools(tmp_path)
    plan['method']['method_id']='self:new_method'
    tools.control_store.save('plan',{'plan':plan})
    assert numeric.verify(tools)['status']=='not_configured'
    assert numeric.result_card(tools,'Placeholder')['verdict']=='deferred'
    assert numeric.public_model_validation({'valid':False,'independent_numeric':{'status':'fail'},'independent_numeric_status':'fail'})=={'valid':False}


def test_coverage_and_duplicate_rows_are_not_accepted():
    expected=[{'id':'a','mean':1.234567891}]
    assert numeric.compare_rows(expected,[],['id'],['mean'])['status']=='fail'
    with pytest.raises(ValueError,match='Duplicate'):
        numeric.compare_rows(expected,expected+expected,['id'],['mean'])


def test_triangle_surface_and_hull_primitive(tmp_path):
    vertices=[(0.,0.,0.),(1.,0.,0.),(0.,1.,0.),(0.,0.,1.)]
    faces=[(0,1,2),(0,1,3),(0,2,3),(1,2,3)]
    path=tmp_path/'lh.pial'
    path.write_bytes(b'\xff\xff\xfe'+b'synthetic\n\n'+struct.pack('>ii',4,4)+b''.join(struct.pack('>fff',*v) for v in vertices)+b''.join(struct.pack('>iii',*f) for f in faces))
    coords,triangles=reader.read_surface(path)
    assert coords==vertices and triangles==faces
    assert abs(sum(reader.triangle_area(*(coords[i] for i in face)) for face in faces)-(1.5+3**0.5/2))<1e-12



def test_nonfinite_and_duplicate_outputs_are_failures_not_missing_reference(tmp_path):
    result=numeric.compare_rows([{'id':'a','mean':1.0}],[{'id':'a','mean':'NaN'}],['id'],['mean'])
    assert result['status']=='fail' and result['differences'][0]['observed'] is None
    json.dumps(result,allow_nan=False)
    tools,plan,bundle=host_tools(tmp_path)
    rows=reader.roi_rows(plan,bundle,tools.resolve)
    write_csv(tools,rows+rows)
    assert numeric.verify(tools)['status']=='fail'
    assert numeric.result_card(tools,'Synthetic fixture')['verdict']=='blocked'


def test_host_hull_reference_pass_and_mutation_fail(tmp_path,monkeypatch):
    import os
    executable=os.environ.get('ANALYSIS_REFERENCE_PYTHON')
    if not executable or not Path(executable).is_file():
        pytest.skip('Configured independent host scientific Python required')
    tools,plan,bundle=host_tools(tmp_path)
    vertices=[(0.,0.,0.),(1.,0.,0.),(0.,1.,0.),(0.,0.,1.)]
    faces=[(0,1,2),(0,1,3),(0,2,3),(1,2,3)]
    path=tools.resolve('/inputs/0/surf/lh.pial')
    path.write_bytes(b'\xff\xff\xfe'+b'synthetic\n\n'+struct.pack('>ii',4,4)+b''.join(struct.pack('>fff',*v) for v in vertices)+b''.join(struct.pack('>iii',*f) for f in faces))
    plan['method']['method_id']='method:v13:global_convex_hull_gyrification'
    plan['data']['files']=['/inputs/0/surf/lh.pial']
    bundle['operations']['calls']=[{'function':'convex_hull_area_ratio','inputs':{'surface_path':'/inputs/0/surf/lh.pial'}}]
    tools.control_store.save('plan',{'plan':plan})
    tools.control_store.save('execution_bundle',bundle)
    rows,keys,columns=numeric.reference_rows(tools,plan,bundle,'global_convex_hull_gyrification')
    write_csv(tools,rows)
    assert numeric.verify(tools)['status']=='pass'
    rows[0]['area_ratio']+=0.1
    write_csv(tools,rows)
    assert numeric.verify(tools)['status']=='fail'
