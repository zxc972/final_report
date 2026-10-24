import csv,io,copy
from round14_fixture import fixture,p
from backend.analysis_operations import execution_bundle
from backend.analysis_output_contract import validate_csv

def encoded(rows,columns):
    out=io.StringIO();w=csv.DictWriter(out,fieldnames=columns);w.writeheader();w.writerows(rows);return out.getvalue().encode()

def test_group_coverage_status_and_effect(tmp_path,monkeypatch):
    tools,intent=fixture(tmp_path,monkeypatch,'group');result=tools.plan_analysis(intent)
    plan=tools.control_store.latest(result['candidates'][0]['candidate_id'])['record']['plan']
    contract=execution_bundle(plan)['output_contract']['tables']['group_results.csv']
    rows=[{**{k:'' for k in contract['columns']},**r,'effect':'group[case]','status':'skipped:singular'} for r in contract['expected_identities']]
    assert validate_csv(encoded(rows,contract['columns']),contract)['status']=='pass'
    assert validate_csv(encoded(rows[:-1],contract['columns']),contract)['identity_mismatch_count']==1
    for field,value in [('status','skip'),('effect','case'),('t','1')]:
        bad=copy.deepcopy(rows);bad[0][field]=value
        assert validate_csv(encoded(bad,contract['columns']),contract)['status']=='fail'
