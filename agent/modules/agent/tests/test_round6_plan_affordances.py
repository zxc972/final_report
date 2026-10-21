import importlib
import json
from pathlib import Path
import pytest
from test_analysis_agent import agent
from test_analysis_evidence import gateway

def test_planning_candidates_supply_real_unified_ids(tmp_path, monkeypatch):
    from test_analysis_product_planner import setup_products
    p = importlib.import_module(agent.__package__ + '.analysis_product_planner')
    ev = importlib.import_module(agent.__package__ + '.analysis_evidence')
    tools = setup_products(tmp_path, monkeypatch)
    result = p.plan_analysis(tools, {'measures': ['thickness'], 'regions': 'all regions'})
    for candidate in result['candidates']:
        assert ev.split_evidence_id(candidate['method']['evidence_id']) == ('method', candidate['method']['method_id'])

def test_shared_stage_is_globally_minimal_and_subject_cost_not_duplicated():
    p = importlib.import_module(agent.__package__ + '.analysis_product_planner')
    steps = [
        {'id': 'left-only', 'inputs': ['raw'], 'outputs': ['left'], 'cost': 1},
        {'id': 'right-only', 'inputs': ['raw'], 'outputs': ['right'], 'cost': 1},
        {'id': 'both', 'inputs': ['raw'], 'outputs': ['left', 'right'], 'cost': 1},
    ]
    result = p.uniform_cost_search(['raw'], ['left', 'right'], steps)
    assert result['cost'] == 1 and result['steps'] == ['both']

def test_matching_label_names_cannot_authorize_crossspecies_roi_comparison(tmp_path, monkeypatch):
    from test_analysis_product_planner import setup_products
    p = importlib.import_module(agent.__package__ + '.analysis_product_planner')
    tools = setup_products(tmp_path, monkeypatch)
    result = p.plan_analysis(tools, {'measures': ['thickness'], 'regions': 'all regions', 'comparison': 'cross_species'})
    assert not result['candidates']
    assert any('do not establish homology' in item['reason'] for item in result['infeasible'])

