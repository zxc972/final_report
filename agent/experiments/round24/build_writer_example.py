"""Refresh only the generic writer example using a real synthetic call."""
from pathlib import Path
import hashlib,importlib.util,json,tempfile
ROOT=Path(__file__).resolve().parents[3]
BACKEND=ROOT/'agent/modules/agent/backend'
def main():
    source=BACKEND/'primatex_ops.py'
    spec=importlib.util.spec_from_file_location('round24_example_ops',source)
    ops=importlib.util.module_from_spec(spec);spec.loader.exec_module(ops)
    with tempfile.TemporaryDirectory(prefix='round24_writer_') as temporary:
        base=Path(temporary);ops.CONTRACT_WORKDIR=temporary
        schema={'columns':['subject','value','units'],'enums':{'units':['synthetic']},
                'fixed_values':{'units':'synthetic'},'identity_columns':['subject'],
                'expected_identities':[{'subject':'synthetic_1'}],'expected_rows':1}
        (base/'contract_tables.json').write_text(json.dumps({'tables':{'example.csv':schema}}))
        result=ops.write_contract_table('example.csv',[{'subject':'synthetic_1','value':1.2345678901234567,'units':'synthetic'}])
        original=(base/'example.csv').read_bytes()
        try:ops.write_contract_table('example.csv',[{'subject':'invented','value':0,'units':'invalid'}])
        except ValueError:pass
        else:raise AssertionError('Invalid row accepted')
        assert (base/'example.csv').read_bytes()==original
    path=ROOT/'agent/modules/agent/knowledge_analysis/operation_examples.json'
    payload=json.loads(path.read_text());old=dict(payload['examples'])
    payload['examples']['write_contract_table']=result
    assert all(old[k]==payload['examples'][k] for k in old if k!='write_contract_table')
    payload['library_sha256']=hashlib.sha256(source.read_bytes()).hexdigest()
    payload['round24_writer_example']={'synthetic_only':True,'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'invalid_row_left_existing_file_unchanged':True,'new_model_calls':0}
    raw=(json.dumps(payload,ensure_ascii=False,indent=2)+'\n').encode()
    path.write_bytes(raw);path.with_suffix('.sha256').write_bytes((hashlib.sha256(raw).hexdigest()+'\n').encode())
    print('Generic writer example refreshed; other 14 examples retained')
if __name__=='__main__':main()
