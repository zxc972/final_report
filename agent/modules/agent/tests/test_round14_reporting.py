from backend.analysis_group_reporting import missing_disclosures,enforce_report_review
from backend.analysis_crossspecies import conclusion_card
from backend.analysis_crossspecies_templates import min_detectable_effect

def test_group_decision_rules():
    numeric={'host_verified':True,'status':'pass'}
    checks=[{'constraint_id':'sample','severity':'hard','verdict':'pass'}]
    def card(rows,numeric=numeric):return conclusion_card('Synthetic','group_inference',rows,{'independent_numeric':numeric},['group_inference'])['verdict']
    assert card(checks)=='accepted'
    assert card(checks+[{'constraint_id':'disclosure','severity':'soft','verdict':'warn'}])=='qualified'
    power=min_detectable_effect({'alpha':.05,'power':.8,'defer_threshold':.8},{'group_inference':True,'group_design':{'d_min':1.2,'n':10,'df':7,'power_assumptions':'synthetic design'},'negative_result':True})
    assert card(checks+[{'constraint_id':'power','severity':'soft','verdict':power['verdict'],'tool_observed':power}])=='deferred'
    assert card(checks,{'host_verified':True,'status':'fail'})=='blocked'

def test_every_report_disclosure_is_required(tmp_path):
    phrases=['Sample size n=8','Excluded subjects: none','FDR family: both hemispheres/all metrics','Effect size: partial_r','d_min=1.2','Site/scanner composition: synthetic A/B/C']
    path=tmp_path/'report.md'
    for i in range(len(phrases)):
        path.write_text('\n'.join(phrases[:i]+phrases[i+1:]))
        result=enforce_report_review({'decision':'pass','findings':[]},{'group_report_requirements':{'n':8}},tmp_path)
        assert result['decision']=='revise'
    assert not missing_disclosures('\n'.join(phrases))
