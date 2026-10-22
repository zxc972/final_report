import pytest
from round14_fixture import fixture,p
from backend.analysis_execution_card import execution_card

def test_group_candidate_and_card(tmp_path,monkeypatch):
    tools,intent=fixture(tmp_path,monkeypatch)
    planned=tools.plan_analysis(intent)
    assert planned['candidates'],[r.get('reason') for r in planned['infeasible']]
    choice=planned['candidates'][0]
    sealed=p.commit_candidate(tools,choice['candidate_id'],'Synthetic DKT continuous design with sex covariate','/work/group.py')
    assert sealed['status']=='committed',sealed
    text=execution_card(sealed)['execution_card']
    assert len(text)<=1500 and '/work/inputs_manifest.json' in text
    assert (tools.workdir/'inputs_manifest.json').is_file()

@pytest.mark.parametrize('comparison',['group','correlation'])
def test_actual_design_sample(tmp_path,monkeypatch,comparison):
    tools,intent=fixture(tmp_path,monkeypatch,comparison)
    result=tools.plan_analysis(intent);assert result['candidates'],[r.get('reason') for r in result['infeasible']]
    scope=tools.control_store.latest(result['candidates'][0]['candidate_id'])['record']['plan']['analysis_scope']
    assert scope['n']==8 and scope['design_columns']==(2 if comparison=='group' else 3)
    assert all(len(v)>=2 for v in scope['groups'].values())

@pytest.mark.parametrize('kind',['missing_design','missing_column','singleton','unmatched'])
def test_design_explanations(tmp_path,monkeypatch,kind):
    tools,intent=fixture(tmp_path,monkeypatch,'group',missing='group' if kind=='missing_column' else None,singleton=kind=='singleton',unmatched=kind=='unmatched')
    if kind=='missing_design':intent.pop('design')
    result=tools.plan_analysis(intent)
    assert result['status']=='needs_design' and result['available_columns'] and not result['candidates']

def test_execution_card_stays_bounded_at_128_subjects(tmp_path,monkeypatch):
    import copy
    from backend.analysis_group_manifest import card
    from backend.analysis_operations import execution_bundle
    tools,intent=fixture(tmp_path,monkeypatch)
    result=tools.plan_analysis(intent)
    plan=copy.deepcopy(tools.control_store.latest(result['candidates'][0]['candidate_id'])['record']['plan'])
    plan['data']['subjects']=['synthetic_'+str(i) for i in range(128)]
    bundle=execution_bundle(plan)
    assert len(card(plan,bundle))<=1500
