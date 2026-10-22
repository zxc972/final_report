import importlib,json
from round14_fixture import fixture,p
from test_round14_group_contract import encoded
from backend.analysis_operations import execution_bundle
from test_analysis_agent import agent

numeric=importlib.import_module(agent.__package__+'.analysis_independent_numeric')

def test_two_tables_pass_and_t_mutation_fails(tmp_path,monkeypatch):
    tools,intent=fixture(tmp_path,monkeypatch)
    planned=tools.plan_analysis(intent);choice=planned['candidates'][0]
    sealed=p.commit_candidate(tools,choice['candidate_id'],'Synthetic group fixture','/work/group.py')
    plan=sealed['plan'];bundle=tools.control_store.latest('execution_bundle')['record']
    refs=numeric.reference_rows(tools,plan,bundle,'group_regional_glm')
    for name,(rows,keys,columns) in refs.items():
        (tools.workdir/name).write_bytes(encoded(rows,bundle['output_contract']['tables'][name]['columns']))
    tools.last_execution={'status':'success','exit_code':0,'receipt_id':'a'*32}
    passed=numeric.verify(tools)
    assert passed['status']=='pass' and len(passed['tables'])==2
    assert all(r['mismatch_count']==0 for r in passed['tables'].values())
    rows,_,_=refs['group_results.csv'];rows[0]['t']+=.1
    (tools.workdir/'group_results.csv').write_bytes(encoded(rows,bundle['output_contract']['tables']['group_results.csv']['columns']))
    failed=numeric.verify(tools)
    assert failed['status']=='fail' and failed['tables']['group_results.csv']['mismatch_count']==1
    assert numeric.result_card(tools,'Synthetic group analysis')['verdict']=='blocked'
    assert 'expected' not in json.dumps(failed) and 'differences' not in json.dumps(failed)
