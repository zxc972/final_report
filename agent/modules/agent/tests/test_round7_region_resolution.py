"""Exact label resolution must precede human lobar aliases; no gold values."""
import importlib
from test_analysis_agent import agent
from test_analysis_product_planner import setup_products,p
lobes=importlib.import_module(agent.__package__+'.analysis_lobar_mapping')


def test_monkey_exact_insula_and_other_labels_need_no_human_lobes():
    names=['unknown','insula','superiorfrontal']
    selected,evidence,error=lobes.resolve_lobes({'species_declared':'monkey_unknown'},'aparc',['insula','superiorfrontal'],names)
    assert selected==['insula','superiorfrontal'] and not evidence and not error
    _,_,error=lobes.resolve_lobes({'species_declared':'monkey_unknown'},'aparc','frontal lobe',names)
    assert 'CHARM' in error


def test_observed_atlas_name_in_regions_is_audited_not_a_missing_label(tmp_path,monkeypatch):
    tools=setup_products(tmp_path,monkeypatch)
    result=p.plan_analysis(tools,{'measures':['thickness'],'regions':'aparc'})
    candidates=result['candidates']
    assert candidates and {c['atlas']['name'] for c in candidates}=={'aparc'}
    assert set(candidates[0]['label_counts'].values())=={2}
    assert result['intent_resolution']['original_regions']=='aparc'
    assert result['intent_resolution']['effective_regions']=='all regions'
    assert result['intent_resolution']['source_paths']


def test_unmatched_anatomy_is_not_automatically_coerced_to_all(tmp_path,monkeypatch):
    tools=setup_products(tmp_path,monkeypatch)
    result=p.plan_analysis(tools,{'measures':['thickness'],'regions':'imaginary_region'})
    assert not result['candidates'] and result['intent_resolution'] is None
    assert any('Unresolved region labels' in x['reason'] for x in result['infeasible'])
