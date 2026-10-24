"""Extend public examples by actual synthetic calls; no original operations change."""
from pathlib import Path
import ast
import hashlib
import importlib.util
import json
import subprocess
import tempfile
import numpy as np
import nibabel as nib

ROOT=Path(__file__).resolve().parents[3]
SOURCE=ROOT/'agent/modules/agent/backend/primatex_ops.py'
BASE='a2189f3b3fc5dd05afac12fe9bd49e21a50c6b15'


def main():
    before=subprocess.check_output(['git','show',BASE+':agent/modules/agent/backend/primatex_ops.py'],cwd=ROOT,stdin=subprocess.DEVNULL).decode('utf-8-sig')
    original={n.name:ast.dump(n) for n in ast.parse(before).body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
    current={n.name:ast.dump(n) for n in ast.parse(SOURCE.read_text(encoding='utf-8-sig')).body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
    assert all(current[n]==body for n,body in original.items()),'Original scientific operations must remain unchanged'
    spec=importlib.util.spec_from_file_location('example_ops',SOURCE);ops=importlib.util.module_from_spec(spec);spec.loader.exec_module(ops)
    with tempfile.TemporaryDirectory(prefix='round21-synthetic-') as temp:
        folder=Path(temp)
        metric=folder/'lh.sample_metric';nib.freesurfer.write_morph_data(str(metric),np.array([0,1,2,3],dtype=np.float32))
        annotation=folder/'lh.sample.annot';nib.freesurfer.write_annot(str(annotation),np.array([0,1,1,1]),np.array([[0,0,0,0],[20,40,80,0]]),[b'unknown',b'parcel'])
        mask=folder/'lh.cortex.label';mask.write_text('#!ascii label synthetic\n3\n1 0 0 0 0\n2 0 0 0 0\n3 0 0 0 0\n')
        labels=folder/'labels.json';labels.write_text(json.dumps({f'synthetic-A/{h}':{'labels':[{'key':1,'name':'parcel'}]} for h in ['lh','rh']}))
        manifest={'subjects':{'synthetic-A':[{'hemisphere':h,'metric':'sample_metric','metric_path':str(metric),'annotation_path':str(annotation),'mask_path':str(mask),'label_set_scope':'synthetic-A/'+h} for h in ['rh','lh']]},'label_sets_ref':{'path':str(labels)}}
        path=folder/'inputs.json';path.write_text(json.dumps(manifest));rows=ops.read_group_inputs(path)
        assert len(rows)==2 and rows[0]['hemisphere']=='lh' and rows[0]['values'].tolist()==[1,2,3]
        row_example={**rows[0],'values':{'python_type':'numpy.ndarray','dtype':str(rows[0]['values'].dtype),'shape':list(rows[0]['values'].shape),'example':rows[0]['values'].tolist()}}
    q=ops.fdr_bh_by_identity({('lh','sample_metric',1):.01,('rh','sample_metric',1):.04,('rh','sample_metric',2):None})
    path=ROOT/'agent/modules/agent/knowledge_analysis/operation_examples.json';data=json.loads(path.read_text(encoding='utf-8'))
    data['examples']['read_group_inputs']={'python_type':'list','example':[row_example]}
    data['examples']['fdr_bh_by_identity']={'python_type':'dict','fields':['(hemisphere,metric,label_key)'],'key_type':'tuple[str,str,int]','example':[{'identity':list(k),'q_fdr':v} for k,v in q.items()]}
    data['library_sha256']=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    data['round21_extension']={'synthetic_only':True,'actual_new_function_calls':['read_group_inputs','fdr_bh_by_identity'],'original_operation_functions_ast_unchanged':True}
    raw=(json.dumps(data,ensure_ascii=False,indent=2)+'\n').encode();path.write_bytes(raw);path.with_suffix('.sha256').write_text(hashlib.sha256(raw).hexdigest()+'\n')
    print(json.dumps({'original_operations_unchanged':len(original),'new_actual_examples':2,'library_sha256':data['library_sha256']}))

if __name__=='__main__':main()
