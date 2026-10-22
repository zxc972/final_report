import pytest
from backend.analysis_product_planner import validate_intent

@pytest.mark.parametrize('design,field', [({'effect':12},'design.effect'),({'effect':'age','covariates':'sex'},'design.covariates'),({'effect':'sex','reference':12},'design.reference')])
def test_design_field_errors(design,field):
    intent,error=validate_intent({'measures':['thickness'],'comparison':'correlation','design':design})
    assert intent is None and error['field_errors'][0]['field'].startswith(field)

def test_duplicate_terms_rejected():
    _,error=validate_intent({'measures':['thickness'],'design':{'effect':'age','covariates':['age']}})
    assert error['field_errors'][0]['field']=='design.covariates'
