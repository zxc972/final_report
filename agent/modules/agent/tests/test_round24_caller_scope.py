
from types import SimpleNamespace
import pytest
from backend import analysis_product_planner as planner

@pytest.mark.parametrize('comparison,design', [('describe',None),('group',None),('describe',{'effect':'variable_x','covariates':[]})])
def test_caller_group_outputs_cannot_silently_become_describe(comparison,design):
    tools=SimpleNamespace(required_artifacts=['regional_values.csv','group_results.csv'])
    result=planner.plan_analysis(tools,{'measures':['thickness'],'comparison':comparison,'design':design})
    assert result['status']=='error'
    assert result['reason']=='Caller group contract and analysis intent disagree'
    assert result['field_errors'][0]['allowed_values']==['group','correlation']
    # It stops before filesystem discovery, does not guess any design or method.
    assert not hasattr(tools,'control_store')

@pytest.mark.parametrize('required,comparison,design', [
    (['summary.csv'],'describe',None),
    (['global_metrics.csv','species_summary.csv'],'cross_species',None),
    (['group_results.csv'],'group',{'effect':'factor_x','covariates':['variable_y']}),
    (['group_results.csv'],'correlation',{'effect':'variable_x','covariates':[]}),
])
def test_consistent_caller_requests_are_unchanged(required,comparison,design):
    intent=planner.AnalysisIntent(measures=['thickness'],comparison=comparison,design=design)
    assert planner.caller_design_consistency(SimpleNamespace(required_artifacts=required),intent) is None


def test_group_design_does_not_force_method_selection():
    intent=planner.AnalysisIntent(measures=['thickness'],comparison='group',design={'effect':'factor_x','covariates':[]},method_id='method:v12:surface_annotation_roi')
    assert planner.caller_design_consistency(SimpleNamespace(required_artifacts=['group_results.csv']),intent) is None
    result=planner.requested_design_match(intent,intent.method_id)
    assert result['commit_requires_mismatch_reason'] is True
